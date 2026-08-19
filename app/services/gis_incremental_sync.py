from typing import Any, Dict, List

import asyncpg
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import COLLECTION_POINTS, COLLECTION_CABLES
from app.repositories import gis_repository
from app.services.gis_virtual_segments import sync_virtual_segments_for_route


def _valid_coord(lng: Any, lat: Any) -> bool:
    try:
        lng_f, lat_f = float(lng), float(lat)
    except (TypeError, ValueError):
        return False
    return -180.0 <= lng_f <= 180.0 and -90.0 <= lat_f <= 90.0


async def sync_route_scope(
    db: AsyncIOMotorDatabase,
    pool: asyncpg.pool.Pool,
    parent_id: str,
) -> Dict[str, Any]:
    points_cursor = db[COLLECTION_POINTS].find(
        {"parent_id": parent_id, "is_deleted": False},
        {
            "ma_diem": 1, "ten_diem": 1, "parent_id": 1, "ma_tuyen": 1,
            "vi_do": 1, "kinh_do": 1, "point_type": 1, "start_point": 1, "thu_tu": 1,
        },
    )
    mongo_points = await points_cursor.to_list(length=None)

    active_point_batch = []
    skipped_points: List[str] = []
    for p in mongo_points:
        ma_diem = p.get("ma_diem")
        lng, lat = p.get("kinh_do"), p.get("vi_do")
        if not ma_diem:
            continue
        if not _valid_coord(lng, lat):
            skipped_points.append(ma_diem)
            continue
        pt = p.get("point_type")
        point_type_val = pt.get("value") if isinstance(pt, dict) else None
        active_point_batch.append({
            "source_id": ma_diem,
            "parent_id": p.get("parent_id"),
            "ma_tuyen": p.get("ma_tuyen"),
            "ten_diem": p.get("ten_diem"),
            "point_type": point_type_val,
            "lng": float(lng),
            "lat": float(lat),
        })

    upserted_points = await gis_repository.upsert_points_batch(pool, active_point_batch)

    active_point_ids = {p["source_id"] for p in active_point_batch}
    existing_geo_points = await gis_repository.get_point_ids_by_parent_all(pool, parent_id)
    stale_point_ids = [
        r["source_id"] for r in existing_geo_points
        if not r["is_deleted"] and r["source_id"] not in active_point_ids
    ]
    soft_deleted_points = await gis_repository.soft_delete_points(pool, stale_point_ids)

    coord_map: Dict[str, Dict[str, float]] = {
        p["ma_diem"]: {"lng": float(p["kinh_do"]), "lat": float(p["vi_do"])}
        for p in mongo_points
        if p.get("ma_diem") and _valid_coord(p.get("kinh_do"), p.get("vi_do"))
    }

    cables_cursor = db[COLLECTION_CABLES].find(
        {"parent_id": parent_id, "is_deleted": False},
        {"_id": 1, "parent_id": 1, "ma_tuyen": 1, "start_point": 1, "end_point": 1},
    )
    mongo_cables = await cables_cursor.to_list(length=None)

    missing_point_ids = {
        pid for c in mongo_cables for pid in (c.get("start_point"), c.get("end_point"))
        if pid and pid not in coord_map
    }
    if missing_point_ids:
        extra_cursor = db[COLLECTION_POINTS].find(
            {"ma_diem": {"$in": list(missing_point_ids)}, "is_deleted": False},
            {"ma_diem": 1, "vi_do": 1, "kinh_do": 1},
        )
        async for p in extra_cursor:
            if _valid_coord(p.get("kinh_do"), p.get("vi_do")):
                coord_map[p["ma_diem"]] = {"lng": float(p["kinh_do"]), "lat": float(p["vi_do"])}

    active_segment_batch = []
    skipped_cables: List[str] = []
    for c in mongo_cables:
        cable_id = c["_id"]
        start_id, end_id = c.get("start_point"), c.get("end_point")
        start_coord = coord_map.get(start_id) if start_id else None
        end_coord = coord_map.get(end_id) if end_id else None
        if not start_id or not end_id or not start_coord or not end_coord:
            skipped_cables.append(cable_id)
            continue
        active_segment_batch.append({
            "source_id": cable_id,
            "parent_id": c.get("parent_id"),
            "ma_tuyen": c.get("ma_tuyen"),
            "start_point_id": start_id,
            "end_point_id": end_id,
            "start_lng": start_coord["lng"], "start_lat": start_coord["lat"],
            "end_lng": end_coord["lng"], "end_lat": end_coord["lat"],
        })

    upserted_segments = await gis_repository.upsert_segments_batch(pool, active_segment_batch)

    active_segment_ids = {s["source_id"] for s in active_segment_batch}
    existing_geo_segments = await gis_repository.get_segment_ids_by_parent_all(pool, parent_id)
    stale_segment_ids = [
        r["source_id"] for r in existing_geo_segments
        if not r["is_deleted"] and r["source_id"] not in active_segment_ids
    ]
    soft_deleted_segments = await gis_repository.soft_delete_segments(pool, stale_segment_ids)

    virtual_result = await sync_virtual_segments_for_route(pool, parent_id, mongo_points, mongo_cables)

    return {
        "parent_id": parent_id,
        "points": {
            "upserted": upserted_points,
            "soft_deleted": soft_deleted_points,
            "skipped_no_coordinate": len(skipped_points),
        },
        "segments": {
            "upserted": upserted_segments,
            "soft_deleted": soft_deleted_segments,
            "skipped_missing_coordinate": len(skipped_cables),
        },
        "virtual_segments": virtual_result,
    }