"""
GIS/Map-oriented SID service.

Hai việc:
1. build_sid_map_data(): tương tự app/services/routing_service.get_sid_diagram_data,
   nhưng thay vì trả nodes/edges "logic" (label lắp ráp từ text, không có
   geometry), trả nodes có lat/lng thật và edges có geometry LineString thật
   (lấy từ PostGIS geo_segments nếu đã sync; nếu chưa sync thì fallback vẽ
   đường thẳng tạm từ toạ độ 2 điểm, giống cơ chế AUTO ở gis_sync_service).
   Edge được gộp theo cable_id (1 đoạn cáp = 1 polyline) thay vì theo từng
   sợi, để không vẽ trùng nhiều polyline chồng lên nhau trên cùng 1 đoạn.

2. get_segment_sid_list(): lấy danh sách SID đang đi qua 1 đoạn cáp (segment/
   cable) cụ thể - dùng cho GET /map/segments/{segment_id} (chi tiết đoạn).

KHÔNG sửa MongoDB, KHÔNG động vào routing_service hiện có.
"""

from typing import Any, Dict, List

from motor.motor_asyncio import AsyncIOMotorDatabase
import asyncpg

from app.core.database import (
    COLLECTION_POINTS,
    COLLECTION_CABLES,
    COLLECTION_CABLE_DETAIL,
    COLLECTION_SID_CABLE,
)
from app.repositories import gis_repository

COLLECTION_TUYEN = "instance_data_hatang_quanlytuyen_newversion"


# ---------------------------------------------------------------------------
# 1. Segment detail -> danh sách SID đi qua đoạn cáp đó
# ---------------------------------------------------------------------------

async def get_segment_sid_list(db: AsyncIOMotorDatabase, cable_id: str) -> List[Dict[str, Any]]:
    """Trả danh sách SID (kèm sợi/cable_number tương ứng) đang active trên 1 đoạn cáp."""
    fibers_cursor = db[COLLECTION_CABLE_DETAIL].find(
        {"parent_id": cable_id, "is_deleted": False},
        {"_id": 1, "cable_number": 1},
    )
    fibers = await fibers_cursor.to_list(length=None)
    if not fibers:
        return []

    fiber_ids = [f["_id"] for f in fibers]
    fiber_number_map = {f["_id"]: f.get("cable_number") for f in fibers}

    sids_cursor = db[COLLECTION_SID_CABLE].find(
        {"parent_id": {"$in": fiber_ids}, "is_deleted": False},
        {"_id": 1, "parent_id": 1, "SID": 1, "ten_khach_hang": 1, "ma_tuyen": 1},
    )
    sids = await sids_cursor.to_list(length=None)

    result = []
    for s in sids:
        sid_obj = s.get("SID")
        sid_value = sid_obj.get("value") if isinstance(sid_obj, dict) else None
        result.append({
            "sid_cable_id": s["_id"],
            "sid": sid_value,
            "ten_khach_hang": s.get("ten_khach_hang"),
            "fiber_id": s.get("parent_id"),
            "cable_number": fiber_number_map.get(s.get("parent_id")),
            "ma_tuyen": s.get("ma_tuyen"),
        })
    return result


# ---------------------------------------------------------------------------
# 2. Map theo SID: nodes (điểm) + edges (đoạn cáp thực, gộp theo cable_id)
# ---------------------------------------------------------------------------

async def build_sid_map_data(
    db: AsyncIOMotorDatabase,
    pool: asyncpg.pool.Pool,
    sid_value: str,
) -> Dict[str, Any]:
    # Bước 1: tìm toàn bộ sid_cable có SID.value = sid_value
    sid_docs_cursor = db[COLLECTION_SID_CABLE].find(
        {"SID.value": sid_value, "is_deleted": False},
        {"_id": 1, "parent_id": 1, "SID": 1, "ten_khach_hang": 1},
    )
    sid_docs = await sid_docs_cursor.to_list(length=None)

    if not sid_docs:
        return {"sid": sid_value, "nodes": [], "edges": [], "message": "Không tìm thấy SID."}

    fiber_ids = list({s["parent_id"] for s in sid_docs})

    # Bước 2: cable_detail (sợi)
    fibers_cursor = db[COLLECTION_CABLE_DETAIL].find(
        {"_id": {"$in": fiber_ids}, "is_deleted": False},
        {"_id": 1, "parent_id": 1, "cable_number": 1},
    )
    fibers = await fibers_cursor.to_list(length=None)
    fiber_map = {f["_id"]: f for f in fibers}

    cable_ids = list({f["parent_id"] for f in fibers})

    # Bước 3: cable (đoạn)
    cables_cursor = db[COLLECTION_CABLES].find(
        {"_id": {"$in": cable_ids}, "is_deleted": False},
        {"_id": 1, "parent_id": 1, "ma_tuyen": 1, "start_point": 1, "end_point": 1, "code": 1},
    )
    cables = await cables_cursor.to_list(length=None)
    cable_map = {c["_id"]: c for c in cables}

    tuyen_ids = list({c["parent_id"] for c in cables})

    # Bước 4: tuyến
    tuyen_cursor = db[COLLECTION_TUYEN].find(
        {"_id": {"$in": tuyen_ids}},
        {"_id": 1, "ma_tuyen": 1, "ten_tuyen": 1},
    )
    tuyen_docs = await tuyen_cursor.to_list(length=None)
    tuyen_map = {t["_id"]: t for t in tuyen_docs}

    # Bước 5: điểm liên quan (start/end của các cable)
    point_ids = set()
    for c in cables:
        if c.get("start_point"):
            point_ids.add(c["start_point"])
        if c.get("end_point"):
            point_ids.add(c["end_point"])

    points_cursor = db[COLLECTION_POINTS].find(
        {"ma_diem": {"$in": list(point_ids)}, "is_deleted": False},
        {"ma_diem": 1, "ten_diem": 1, "parent_id": 1, "point_type": 1, "vi_do": 1, "kinh_do": 1},
    )
    points = await points_cursor.to_list(length=None)

    # Toạ độ ưu tiên lấy từ PostGIS (đã sync); fallback về Mongo nếu chưa sync.
    geo_points_rows = await gis_repository.get_points_by_ids(pool, list(point_ids))
    geo_point_map = {r["source_id"]: r for r in geo_points_rows}

    nodes = []
    node_lookup: Dict[str, Dict[str, Any]] = {}
    for p in points:
        ma_diem = p["ma_diem"]
        geo = geo_point_map.get(ma_diem)
        lat = geo["lat"] if geo else p.get("vi_do")
        lng = geo["lng"] if geo else p.get("kinh_do")
        if lat is None or lng is None:
            continue  # không có toạ độ ở cả 2 nguồn -> bỏ qua node này

        pt = p.get("point_type")
        point_type_val = pt.get("value") if isinstance(pt, dict) else None
        tuyen_info = tuyen_map.get(p.get("parent_id"), {})

        node = {
            "id": ma_diem,
            "label": p.get("ten_diem", ""),
            "lat": lat,
            "lng": lng,
            "point_type": point_type_val or "",
            "ma_tuyen": tuyen_info.get("ma_tuyen", ""),
            "ten_tuyen": tuyen_info.get("ten_tuyen", ""),
        }
        nodes.append(node)
        node_lookup[ma_diem] = node

    # Bước 6: gộp SID theo cable_id (1 cable = 1 polyline, có thể nhiều sợi/SID)
    sid_by_cable: Dict[str, List[Dict[str, Any]]] = {}
    for sid_doc in sid_docs:
        fiber = fiber_map.get(sid_doc["parent_id"])
        if not fiber:
            continue
        cable_id = fiber["parent_id"]
        sid_obj = sid_doc.get("SID")
        sid_by_cable.setdefault(cable_id, []).append({
            "sid_cable_id": sid_doc["_id"],
            "sid": sid_obj.get("value") if isinstance(sid_obj, dict) else None,
            "ten_khach_hang": sid_doc.get("ten_khach_hang"),
            "fiber_id": fiber["_id"],
            "cable_number": fiber.get("cable_number"),
        })

    # Geometry thật từ PostGIS cho toàn bộ cable liên quan (1 query, tránh N+1)
    geo_segments_rows = await gis_repository.get_segments_by_ids(pool, list(sid_by_cable.keys()))
    geo_segment_map = {r["source_id"]: r for r in geo_segments_rows}

    edges = []
    for cable_id, sid_list in sid_by_cable.items():
        cable = cable_map.get(cable_id)
        if not cable:
            continue

        geo_seg = geo_segment_map.get(cable_id)
        if geo_seg:
            geometry = geo_seg["geometry"]
            geometry_source = geo_seg["geometry_source"]
        else:
            # Chưa sync sang PostGIS -> fallback vẽ đường thẳng tạm từ toạ độ
            # 2 điểm đã lấy ở trên (không sửa MongoDB, chỉ tạo geometry tạm
            # trong response, giống quy tắc AUTO ở gis_sync_service).
            start_node = node_lookup.get(cable.get("start_point"))
            end_node = node_lookup.get(cable.get("end_point"))
            if start_node and end_node:
                geometry = {
                    "type": "LineString",
                    "coordinates": [
                        [start_node["lng"], start_node["lat"]],
                        [end_node["lng"], end_node["lat"]],
                    ],
                }
            else:
                geometry = None
            geometry_source = "AUTO"

        tuyen_info = tuyen_map.get(cable.get("parent_id"), {})
        edges.append({
            "id": cable_id,
            "code": cable.get("code", ""),
            "from": cable.get("start_point", ""),
            "to": cable.get("end_point", ""),
            "ma_tuyen": tuyen_info.get("ma_tuyen", ""),
            "ten_tuyen": tuyen_info.get("ten_tuyen", ""),
            "geometry": geometry,
            "geometry_source": geometry_source,
            "list_sid": sid_list,
        })

    return {"sid": sid_value, "nodes": nodes, "edges": edges}
