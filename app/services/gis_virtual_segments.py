from typing import Any, Dict, List, Optional

import asyncpg
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import COLLECTION_POINTS, COLLECTION_CABLES
from app.repositories import gis_repository

POINT_TYPE_HA_NGAM = "Hạ ngầm"


def _valid_coord(lng: Any, lat: Any) -> bool:
    try:
        lng_f, lat_f = float(lng), float(lat)
    except (TypeError, ValueError):
        return False
    return -180.0 <= lng_f <= 180.0 and -90.0 <= lat_f <= 90.0


def build_points_index(points: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for p in points:
        ma_diem = p.get("ma_diem")
        if not ma_diem:
            continue
        pt = p.get("point_type")
        point_type_val = pt.get("value") if isinstance(pt, dict) else None
        sp = p.get("start_point")
        start_point_ma = sp.get("value") if isinstance(sp, dict) else None
        index[ma_diem] = {
            "ma_diem": ma_diem,
            "lng": p.get("kinh_do"),
            "lat": p.get("vi_do"),
            "point_type": point_type_val,
            "start_point": start_point_ma,
            "thu_tu": p.get("thu_tu") or 0,
        }
    return index


def build_ha_ngam_children_map(points_index: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    children: Dict[str, List[str]] = {}
    ha_ngam_points = [
        p for p in points_index.values()
        if p.get("point_type") == POINT_TYPE_HA_NGAM and p.get("start_point")
    ]
    ha_ngam_points.sort(key=lambda p: (p.get("thu_tu") or 0, p["ma_diem"]))
    for p in ha_ngam_points:
        children.setdefault(p["start_point"], []).append(p["ma_diem"])
    return children


def build_cable_chain(
    start_ma: str,
    end_ma: str,
    ha_ngam_children_map: Dict[str, List[str]],
) -> List[str]:
    chain = [start_ma]
    current = start_ma
    visited = {start_ma}
    while True:
        children = ha_ngam_children_map.get(current)
        if not children:
            break
        next_ma = children[0]
        if next_ma == end_ma or next_ma in visited:
            break
        chain.append(next_ma)
        visited.add(next_ma)
        current = next_ma
    if chain[-1] != end_ma:
        chain.append(end_ma)
    return chain


async def sync_virtual_segments_for_cable(
    pool: asyncpg.pool.Pool,
    cable_id: str,
    parent_id: Optional[str],
    ma_tuyen: Optional[str],
    start_ma: str,
    end_ma: str,
    points_index: Dict[str, Dict[str, Any]],
) -> int:
    ha_ngam_children_map = build_ha_ngam_children_map(points_index)
    chain = build_cable_chain(start_ma, end_ma, ha_ngam_children_map)

    chain_points: List[Dict[str, Any]] = []
    for ma in chain:
        info = points_index.get(ma)
        if info is None or not _valid_coord(info.get("lng"), info.get("lat")):
            continue
        chain_points.append({
            "ma_diem": ma,
            "lng": float(info["lng"]),
            "lat": float(info["lat"]),
        })

    new_ids = await gis_repository.recompute_virtual_segments_for_cable(
        pool, cable_id, parent_id, ma_tuyen, chain_points,
    )
    return len(new_ids)


async def sync_virtual_segments_for_route(
    pool: asyncpg.pool.Pool,
    parent_id: str,
    mongo_points: List[Dict[str, Any]],
    mongo_cables: List[Dict[str, Any]],
) -> Dict[str, Any]:
    points_index = build_points_index(mongo_points)

    total_virtual = 0
    processed_cables = 0
    for c in mongo_cables:
        start_ma = c.get("start_point")
        end_ma = c.get("end_point")
        if not start_ma or not end_ma:
            continue
        count = await sync_virtual_segments_for_cable(
            pool,
            cable_id=c["_id"],
            parent_id=c.get("parent_id") or parent_id,
            ma_tuyen=c.get("ma_tuyen"),
            start_ma=start_ma,
            end_ma=end_ma,
            points_index=points_index,
        )
        processed_cables += 1
        total_virtual += count

    return {
        "cables_processed": processed_cables,
        "virtual_segments_upserted": total_virtual,
    }


async def sync_virtual_segments_full(
    db: AsyncIOMotorDatabase,
    pool: asyncpg.pool.Pool,
) -> Dict[str, Any]:
    parent_ids = await db[COLLECTION_CABLES].distinct("parent_id", {"is_deleted": False})

    total_cables = 0
    total_virtual = 0
    routes_processed = 0

    for parent_id in parent_ids:
        if not parent_id:
            continue

        points_cursor = db[COLLECTION_POINTS].find(
            {"parent_id": parent_id, "is_deleted": False},
            {"ma_diem": 1, "vi_do": 1, "kinh_do": 1, "point_type": 1, "start_point": 1, "thu_tu": 1},
        )
        mongo_points = await points_cursor.to_list(length=None)

        cables_cursor = db[COLLECTION_CABLES].find(
            {"parent_id": parent_id, "is_deleted": False},
            {"_id": 1, "parent_id": 1, "ma_tuyen": 1, "start_point": 1, "end_point": 1},
        )
        mongo_cables = await cables_cursor.to_list(length=None)

        result = await sync_virtual_segments_for_route(pool, parent_id, mongo_points, mongo_cables)
        routes_processed += 1
        total_cables += result["cables_processed"]
        total_virtual += result["virtual_segments_upserted"]

    return {
        "routes_processed": routes_processed,
        "cables_processed": total_cables,
        "virtual_segments_upserted": total_virtual,
    }