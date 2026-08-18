"""
Sync/projection service: MongoDB (source of truth) -> PostGIS (GIS layer).

Nguyên tắc:
- KHÔNG đọc/ghi field mới vào MongoDB.
- Idempotent: chạy lại nhiều lần không tạo duplicate (dùng upsert theo source_id).
- Batch theo settings.GIS_SYNC_BATCH_SIZE để tránh N+1 query / tránh 1 câu
  lệnh khổng lồ.
- Điểm không có vi_do/kinh_do hợp lệ sẽ bị bỏ qua (không thể tạo geometry),
  được log lại trong kết quả trả về để người vận hành biết cần bổ sung tọa độ.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

import asyncpg
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.database import COLLECTION_POINTS, COLLECTION_CABLES
from app.repositories import gis_repository


def _valid_coord(lng: Any, lat: Any) -> bool:
    try:
        lng_f, lat_f = float(lng), float(lat)
    except (TypeError, ValueError):
        return False
    return -180.0 <= lng_f <= 180.0 and -90.0 <= lat_f <= 90.0


async def sync_points(db: AsyncIOMotorDatabase, pool: asyncpg.pool.Pool) -> Dict[str, Any]:
    """Đồng bộ toàn bộ điểm active (is_deleted=false) từ Mongo sang geo_points."""
    cursor = db[COLLECTION_POINTS].find(
        {"is_deleted": False},
        {
            "ma_diem": 1, "ten_diem": 1, "parent_id": 1, "ma_tuyen": 1,
            "vi_do": 1, "kinh_do": 1, "point_type": 1,
        },
    )

    batch: List[Dict[str, Any]] = []
    synced = 0
    skipped_no_coord: List[str] = []

    async for p in cursor:
        ma_diem = p.get("ma_diem")
        lng, lat = p.get("kinh_do"), p.get("vi_do")
        if not ma_diem:
            continue
        if not _valid_coord(lng, lat):
            skipped_no_coord.append(ma_diem)
            continue

        pt = p.get("point_type")
        point_type_val = pt.get("value") if isinstance(pt, dict) else None

        batch.append({
            "source_id": ma_diem,
            "parent_id": p.get("parent_id"),
            "ma_tuyen": p.get("ma_tuyen"),
            "ten_diem": p.get("ten_diem"),
            "point_type": point_type_val,
            "lng": float(lng),
            "lat": float(lat),
        })

        if len(batch) >= settings.GIS_SYNC_BATCH_SIZE:
            synced += await gis_repository.upsert_points_batch(pool, batch)
            batch = []

    if batch:
        synced += await gis_repository.upsert_points_batch(pool, batch)

    return {
        "synced_points": synced,
        "skipped_no_coordinate": len(skipped_no_coord),
        "skipped_ma_diem_sample": skipped_no_coord[:20],
    }


async def sync_segments(db: AsyncIOMotorDatabase, pool: asyncpg.pool.Pool) -> Dict[str, Any]:
    """
    Đồng bộ toàn bộ đoạn cáp active từ Mongo sang geo_segments.
    Geometry AUTO = đường thẳng start_point -> end_point (lấy tọa độ từ chính
    collection Point). Nếu segment đã có geometry_source=USER trong PostGIS,
    repository sẽ tự giữ nguyên geometry đã chỉnh tay (xem upsert_segments_batch).
    """
    cables_cursor = db[COLLECTION_CABLES].find(
        {"is_deleted": False},
        {"_id": 1, "parent_id": 1, "ma_tuyen": 1, "start_point": 1, "end_point": 1},
    )
    cables = await cables_cursor.to_list(length=None)

    # Lấy toạ độ tất cả các điểm liên quan trong 1 query (tránh N+1).
    point_ids = set()
    for c in cables:
        if c.get("start_point"):
            point_ids.add(c["start_point"])
        if c.get("end_point"):
            point_ids.add(c["end_point"])

    points_cursor = db[COLLECTION_POINTS].find(
        {"ma_diem": {"$in": list(point_ids)}, "is_deleted": False},
        {"ma_diem": 1, "vi_do": 1, "kinh_do": 1},
    )
    coord_map: Dict[str, Dict[str, float]] = {}
    async for p in points_cursor:
        if _valid_coord(p.get("kinh_do"), p.get("vi_do")):
            coord_map[p["ma_diem"]] = {"lng": float(p["kinh_do"]), "lat": float(p["vi_do"])}

    batch: List[Dict[str, Any]] = []
    synced = 0
    skipped_missing_coord: List[str] = []

    for c in cables:
        cable_id = c["_id"]
        start_id, end_id = c.get("start_point"), c.get("end_point")
        if not start_id or not end_id:
            continue
        start_coord = coord_map.get(start_id)
        end_coord = coord_map.get(end_id)
        if not start_coord or not end_coord:
            skipped_missing_coord.append(cable_id)
            continue

        batch.append({
            "source_id": cable_id,
            "parent_id": c.get("parent_id"),
            "ma_tuyen": c.get("ma_tuyen"),
            "start_point_id": start_id,
            "end_point_id": end_id,
            "start_lng": start_coord["lng"], "start_lat": start_coord["lat"],
            "end_lng": end_coord["lng"], "end_lat": end_coord["lat"],
        })

        if len(batch) >= settings.GIS_SYNC_BATCH_SIZE:
            synced += await gis_repository.upsert_segments_batch(pool, batch)
            batch = []

    if batch:
        synced += await gis_repository.upsert_segments_batch(pool, batch)

    return {
        "synced_segments": synced,
        "skipped_missing_coordinate": len(skipped_missing_coord),
        "skipped_cable_id_sample": skipped_missing_coord[:20],
    }


async def run_full_sync(db: AsyncIOMotorDatabase, pool: asyncpg.pool.Pool) -> Dict[str, Any]:
    """Entry point: đồng bộ điểm trước, rồi đến đoạn cáp (đoạn cần tọa độ điểm)."""
    started_at = datetime.now(timezone.utc)
    points_result = await sync_points(db, pool)
    segments_result = await sync_segments(db, pool)
    finished_at = datetime.now(timezone.utc)

    return {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (finished_at - started_at).total_seconds(),
        "points": points_result,
        "segments": segments_result,
    }
