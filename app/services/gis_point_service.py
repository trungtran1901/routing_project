from datetime import datetime, timezone
from typing import Any, Dict, Optional

import asyncpg
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import COLLECTION_POINTS
from app.repositories import gis_repository
from app.models.point import PointGeoSyncRequest


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def update_point_location(
    db: AsyncIOMotorDatabase,
    point_id: str,
    lng: float,
    lat: float,
    modified_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    modified_fields = modified_fields or {}

    mongo_point = await db[COLLECTION_POINTS].find_one(
        {"ma_diem": point_id, "is_deleted": False}
    )
    if not mongo_point:
        raise ValueError(f"Không tìm thấy điểm '{point_id}' trong MongoDB (hoặc đã bị xóa).")

    now = _now()
    update_fields: Dict[str, Any] = {
        "vi_do": lat,
        "kinh_do": lng,
        "modified_by_date": now,
    }
    for k, v in modified_fields.items():
        if v is not None:
            update_fields[k] = v

    await db[COLLECTION_POINTS].update_one(
        {"ma_diem": point_id, "is_deleted": False},
        {"$set": update_fields},
    )

    updated_point = await db[COLLECTION_POINTS].find_one(
        {"ma_diem": point_id, "is_deleted": False}
    )

    return {
        "source_id": updated_point.get("ma_diem"),
        "ma_diem": updated_point.get("ma_diem"),
        "ten_diem": updated_point.get("ten_diem"),
        "lat": updated_point.get("vi_do"),
        "lng": updated_point.get("kinh_do"),
        "ma_tuyen": updated_point.get("ma_tuyen"),
        "parent_id": updated_point.get("parent_id"),
    }


async def sync_point_geometry_from_payload(
    pool: asyncpg.pool.Pool,
    payload: PointGeoSyncRequest,
) -> Dict[str, Any]:
    if payload.kinh_do is None or payload.vi_do is None:
        raise ValueError("Thiếu vi_do/kinh_do trong payload, không thể cập nhật toạ độ.")

    lng, lat = float(payload.kinh_do), float(payload.vi_do)

    if not (-180.0 <= lng <= 180.0):
        raise ValueError(f"Longitude không hợp lệ: {lng}")
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Latitude không hợp lệ: {lat}")

    point_id = payload.ma_diem

    existing_geo = await gis_repository.get_point(pool, point_id)
    point_type_val = payload.point_type.value if payload.point_type else None

    if existing_geo is None:
        await gis_repository.upsert_points_batch(pool, [{
            "source_id": point_id,
            "parent_id": payload.parent_id,
            "ma_tuyen": payload.ma_tuyen,
            "ten_diem": payload.ten_diem,
            "point_type": point_type_val,
            "lng": lng,
            "lat": lat,
        }])
    else:
        await gis_repository.update_point_geometry(pool, point_id, lng, lat)

    refreshed_segments = await gis_repository.sync_connected_segments_endpoint(pool, point_id)

    updated_geo = await gis_repository.get_point(pool, point_id)

    return {
        "point": updated_geo,
        "refreshed_segments": refreshed_segments,
    }