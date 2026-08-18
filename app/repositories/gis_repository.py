"""
Data-access layer cho PostGIS (geo_points / geo_segments).

Convention: giống app/services/*.py hiện tại - dùng raw query (ở đây là SQL
qua asyncpg thay vì Mongo filter), trả về dict/list dict, không lộ driver-
specific object ra ngoài router.

Kể từ migration 002, mọi query ĐỌC đều lọc `is_deleted = false` (điểm/đoạn
đã bị soft-delete sẽ không xuất hiện trên map nữa, dù vẫn còn bản ghi trong
bảng để giữ lịch sử / tránh phải xoá cứng).
"""

import json
from typing import Any, Dict, List, Optional

import asyncpg


# ---------------------------------------------------------------------------
# Points
# ---------------------------------------------------------------------------

async def upsert_points_batch(pool: asyncpg.pool.Pool, points: List[Dict[str, Any]]) -> int:
    """
    Upsert hàng loạt điểm vào geo_points.
    Mỗi phần tử: {source_id, parent_id, ma_tuyen, ten_diem, point_type, lng, lat}
    Idempotent: dùng ON CONFLICT (source_id) DO UPDATE.
    Luôn set is_deleted = false (kể cả khi trước đó điểm này đã bị soft-delete
    và nay xuất hiện lại active trong MongoDB).
    """
    if not points:
        return 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                """
                INSERT INTO geo_points
                    (source_id, parent_id, ma_tuyen, ten_diem, point_type, geometry, is_deleted)
                VALUES
                    ($1, $2, $3, $4, $5, ST_SetSRID(ST_MakePoint($6, $7), 4326), false)
                ON CONFLICT (source_id) DO UPDATE SET
                    parent_id  = EXCLUDED.parent_id,
                    ma_tuyen   = EXCLUDED.ma_tuyen,
                    ten_diem   = EXCLUDED.ten_diem,
                    point_type = EXCLUDED.point_type,
                    geometry   = EXCLUDED.geometry,
                    is_deleted = false
                """,
                [
                    (
                        p["source_id"], p.get("parent_id"), p.get("ma_tuyen"),
                        p.get("ten_diem"), p.get("point_type"),
                        p["lng"], p["lat"],
                    )
                    for p in points
                ],
            )
    return len(points)


async def soft_delete_points(pool: asyncpg.pool.Pool, source_ids: List[str]) -> int:
    """Đánh dấu is_deleted=true cho các điểm không còn active ở MongoDB."""
    if not source_ids:
        return 0
    result = await pool.execute(
        "UPDATE geo_points SET is_deleted = true WHERE source_id = ANY($1::text[]) AND is_deleted = false",
        source_ids,
    )
    try:
        return int(result.split(" ")[-1])
    except (ValueError, IndexError):
        return len(source_ids)


async def get_point(pool: asyncpg.pool.Pool, source_id: str) -> Optional[Dict[str, Any]]:
    row = await pool.fetchrow(
        """
        SELECT source_id, parent_id, ma_tuyen, ten_diem, point_type,
               ST_Y(geometry) AS lat, ST_X(geometry) AS lng
        FROM geo_points
        WHERE source_id = $1 AND is_deleted = false
        """,
        source_id,
    )
    return dict(row) if row else None


async def get_points_by_ids(pool: asyncpg.pool.Pool, source_ids: List[str]) -> List[Dict[str, Any]]:
    if not source_ids:
        return []
    rows = await pool.fetch(
        """
        SELECT source_id, parent_id, ma_tuyen, ten_diem, point_type,
               ST_Y(geometry) AS lat, ST_X(geometry) AS lng
        FROM geo_points
        WHERE source_id = ANY($1::text[]) AND is_deleted = false
        """,
        source_ids,
    )
    return [dict(r) for r in rows]


async def get_points_bbox(
    pool: asyncpg.pool.Pool,
    min_lng: float, min_lat: float, max_lng: float, max_lat: float,
    limit: int,
) -> List[Dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT source_id, parent_id, ma_tuyen, ten_diem, point_type,
               ST_Y(geometry) AS lat, ST_X(geometry) AS lng
        FROM geo_points
        WHERE is_deleted = false
          AND geometry && ST_MakeEnvelope($1, $2, $3, $4, 4326)
        LIMIT $5
        """,
        min_lng, min_lat, max_lng, max_lat, limit,
    )
    return [dict(r) for r in rows]


async def get_points_bbox_clustered(
    pool: asyncpg.pool.Pool,
    min_lng: float, min_lat: float, max_lng: float, max_lat: float,
    grid_cols: int, grid_rows: int,
    limit: int,
) -> List[Dict[str, Any]]:
    """
    Gom cụm điểm trong viewport theo lưới NxN chia đều trên chính viewport đó
    (giống cơ chế marker clustering của Google Maps) — dùng `width_bucket()`
    có sẵn của PostgreSQL để bỏ vào 1 trong grid_cols*grid_rows ô lưới.

    Vì lưới chia theo VIEWPORT (không phải toạ độ tuyệt đối/geohash cố định),
    số ô luôn <= grid_cols*grid_rows bất kể viewport rộng hay hẹp, hay có bao
    nhiêu điểm bên trong — response luôn bị chặn kích thước, giải quyết đúng
    vấn đề "zoom nhỏ tải toàn bộ điểm". Khi zoom lớn (viewport hẹp), số điểm
    thực tế trong khung thường đã nhỏ hơn số ô lưới -> tự nhiên mỗi ô có
    đúng 1 điểm -> trả về điểm thật (không bị gom), giống Google Maps.

    Mỗi ô lưới trả về:
    - cnt = 1  -> trả điểm thật (source_id, ten_diem... như bbox thường)
    - cnt > 1  -> trả 1 pseudo-node "cluster": tâm (trung bình toạ độ), count,
                  và bbox bao các điểm trong cụm (để frontend fitBounds khi
                  người dùng click vào cụm để "zoom vào xem chi tiết").
    """
    rows = await pool.fetch(
        """
        WITH pts AS (
            SELECT source_id, parent_id, ma_tuyen, ten_diem, point_type,
                   ST_X(geometry) AS lng, ST_Y(geometry) AS lat
            FROM geo_points
            WHERE is_deleted = false
              AND geometry && ST_MakeEnvelope($1, $2, $3, $4, 4326)
        ),
        grid AS (
            SELECT *,
                   width_bucket(lng, $1, $3, $5) AS gx,
                   width_bucket(lat, $2, $4, $6) AS gy
            FROM pts
        )
        SELECT
            gx, gy,
            count(*)                       AS cnt,
            avg(lng)                       AS center_lng,
            avg(lat)                       AS center_lat,
            min(lng)                       AS min_lng,
            max(lng)                       AS max_lng,
            min(lat)                       AS min_lat,
            max(lat)                       AS max_lat,
            (array_agg(source_id))[1]      AS sample_source_id,
            (array_agg(parent_id))[1]      AS sample_parent_id,
            (array_agg(ma_tuyen))[1]       AS sample_ma_tuyen,
            (array_agg(ten_diem))[1]       AS sample_ten_diem,
            (array_agg(point_type))[1]     AS sample_point_type
        FROM grid
        GROUP BY gx, gy
        LIMIT $7
        """,
        min_lng, min_lat, max_lng, max_lat, grid_cols, grid_rows, limit,
    )
    return [dict(r) for r in rows]


async def get_points_by_parent(pool: asyncpg.pool.Pool, parent_id: str) -> List[Dict[str, Any]]:
    """Toàn bộ điểm active thuộc 1 tuyến (parent_id = tuyến._id), dùng cho GET /map/routes."""
    rows = await pool.fetch(
        """
        SELECT source_id, parent_id, ma_tuyen, ten_diem, point_type,
               ST_Y(geometry) AS lat, ST_X(geometry) AS lng
        FROM geo_points
        WHERE parent_id = $1 AND is_deleted = false
        """,
        parent_id,
    )
    return [dict(r) for r in rows]


async def get_point_ids_by_parent_all(pool: asyncpg.pool.Pool, parent_id: str) -> List[Dict[str, Any]]:
    """
    Toàn bộ điểm thuộc 1 tuyến trong PostGIS (KHÔNG lọc is_deleted) - dùng để
    incremental sync so sánh với danh sách active hiện tại ở MongoDB, từ đó
    biết điểm nào cần soft-delete.
    """
    rows = await pool.fetch(
        "SELECT source_id, is_deleted FROM geo_points WHERE parent_id = $1",
        parent_id,
    )
    return [dict(r) for r in rows]


async def nearby_points(
    pool: asyncpg.pool.Pool, lat: float, lng: float, radius_m: float, limit: int,
) -> List[Dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT source_id, parent_id, ma_tuyen, ten_diem, point_type,
               ST_Y(geometry) AS lat, ST_X(geometry) AS lng,
               ST_Distance(geometry::geography, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography) AS distance_m
        FROM geo_points
        WHERE is_deleted = false
          AND ST_DWithin(
            geometry::geography,
            ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography,
            $3
        )
        ORDER BY distance_m ASC
        LIMIT $4
        """,
        lng, lat, radius_m, limit,
    )
    return [dict(r) for r in rows]


async def update_point_geometry(
    pool: asyncpg.pool.Pool, source_id: str, lng: float, lat: float,
) -> Optional[Dict[str, Any]]:
    """Cập nhật geometry (vị trí) của 1 điểm đã tồn tại trong geo_points."""
    row = await pool.fetchrow(
        """
        UPDATE geo_points
        SET geometry = ST_SetSRID(ST_MakePoint($2, $3), 4326)
        WHERE source_id = $1
        RETURNING source_id, parent_id, ma_tuyen, ten_diem, point_type,
                  ST_Y(geometry) AS lat, ST_X(geometry) AS lng
        """,
        source_id, lng, lat,
    )
    return dict(row) if row else None


async def sync_connected_segments_endpoint(pool: asyncpg.pool.Pool, point_id: str) -> List[Dict[str, Any]]:
    """
    Sau khi 1 điểm bị dời vị trí, MỌI đoạn cáp nối tới điểm này (bất kể
    geometry_source là AUTO hay USER) cần dịch chuyển theo, nếu không map sẽ
    hiển thị sai lệch (đoạn "đứt" khỏi điểm mà nó vốn phải nối tới).

    Cách làm: chỉ thay đúng 1 ĐỈNH (vertex) đầu hoặc cuối của LineString -
    đúng vertex trùng với điểm vừa di chuyển - bằng ST_SetPoint(), thay vì vẽ
    lại toàn bộ đường bằng ST_MakeLine(). Nhờ vậy:
    - Đoạn AUTO (chỉ 2 điểm, đường thẳng) → kết quả giống hệt cách cũ (vẽ
      lại đường thẳng nối 2 điểm).
    - Đoạn USER (nhiều điểm, do người dùng tự vẽ tay trên map) → CHỈ đầu mút
      trùng với điểm bị di chuyển được cập nhật, các điểm uốn ở giữa (hình
      dạng người dùng đã tự vẽ) được GIỮ NGUYÊN — trước đây các đoạn USER bị
      bỏ qua hoàn toàn (đóng băng vĩnh viễn, không bao giờ di chuyển theo
      điểm), đây chính là lỗi đã báo cáo và được sửa ở đây.

    KHÔNG tăng geometry_version (đây là hệ thống tự khớp lại theo điểm, khác
    với việc người dùng chủ động sửa geometry qua PUT /map/segments/{id}/geometry).

    Trả về danh sách {source_id, geometry_source} các đoạn đã được cập nhật.
    """
    rows = await pool.fetch(
        """
        UPDATE geo_segments s
        SET geometry = CASE
                WHEN s.start_point_id = $1 THEN ST_SetPoint(s.geometry, 0, p.geometry)
                WHEN s.end_point_id   = $1 THEN ST_SetPoint(s.geometry, ST_NumPoints(s.geometry) - 1, p.geometry)
                ELSE s.geometry
            END
        FROM geo_points p
        WHERE p.source_id = $1
          AND s.is_deleted = false
          AND (s.start_point_id = $1 OR s.end_point_id = $1)
        RETURNING s.source_id, s.geometry_source
        """,
        point_id,
    )
    return [{"source_id": r["source_id"], "geometry_source": r["geometry_source"]} for r in rows]


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------

async def upsert_segments_batch(pool: asyncpg.pool.Pool, segments: List[Dict[str, Any]]) -> int:
    """
    Upsert hàng loạt đoạn cáp vào geo_segments.
    Mỗi phần tử: {source_id, parent_id, ma_tuyen, start_point_id, end_point_id,
                  start_lng, start_lat, end_lng, end_lat}
    Sync luôn set geometry_source = AUTO và geometry_version = 1 CHỈ KHI segment
    chưa tồn tại. Nếu đã tồn tại và geometry_source = USER (người dùng đã tự
    vẽ), KHÔNG được ghi đè geometry — chỉ cập nhật các field routing.
    Luôn set is_deleted = false.
    """
    if not segments:
        return 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                """
                INSERT INTO geo_segments
                    (source_id, parent_id, ma_tuyen, start_point_id, end_point_id,
                     geometry, geometry_source, geometry_version, is_deleted)
                VALUES
                    ($1, $2, $3, $4, $5,
                     ST_SetSRID(ST_MakeLine(ST_MakePoint($6, $7), ST_MakePoint($8, $9)), 4326),
                     'AUTO', 1, false)
                ON CONFLICT (source_id) DO UPDATE SET
                    parent_id      = EXCLUDED.parent_id,
                    ma_tuyen       = EXCLUDED.ma_tuyen,
                    start_point_id = EXCLUDED.start_point_id,
                    end_point_id   = EXCLUDED.end_point_id,
                    is_deleted     = false,
                    -- Chỉ tự cập nhật lại geometry AUTO nếu segment hiện tại
                    -- cũng đang là AUTO (chưa từng bị người dùng chỉnh trên map).
                    geometry = CASE
                        WHEN geo_segments.geometry_source = 'AUTO'
                        THEN EXCLUDED.geometry
                        ELSE geo_segments.geometry
                    END
                """,
                [
                    (
                        s["source_id"], s.get("parent_id"), s.get("ma_tuyen"),
                        s["start_point_id"], s["end_point_id"],
                        s["start_lng"], s["start_lat"], s["end_lng"], s["end_lat"],
                    )
                    for s in segments
                ],
            )
    return len(segments)


async def soft_delete_segments(pool: asyncpg.pool.Pool, source_ids: List[str]) -> int:
    """Đánh dấu is_deleted=true cho các đoạn cáp không còn active ở MongoDB."""
    if not source_ids:
        return 0
    result = await pool.execute(
        "UPDATE geo_segments SET is_deleted = true WHERE source_id = ANY($1::text[]) AND is_deleted = false",
        source_ids,
    )
    try:
        return int(result.split(" ")[-1])
    except (ValueError, IndexError):
        return len(source_ids)


def _row_to_segment_dict(row) -> Dict[str, Any]:
    d = dict(row)
    d["geometry"] = json.loads(d.pop("geometry_geojson"))
    return d


async def get_segment(pool: asyncpg.pool.Pool, source_id: str) -> Optional[Dict[str, Any]]:
    row = await pool.fetchrow(
        """
        SELECT source_id, parent_id, ma_tuyen, start_point_id, end_point_id,
               geometry_source, geometry_version,
               ST_AsGeoJSON(geometry) AS geometry_geojson
        FROM geo_segments
        WHERE source_id = $1 AND is_deleted = false
        """,
        source_id,
    )
    return _row_to_segment_dict(row) if row else None


async def get_segments_by_ids(pool: asyncpg.pool.Pool, source_ids: List[str]) -> List[Dict[str, Any]]:
    if not source_ids:
        return []
    rows = await pool.fetch(
        """
        SELECT source_id, parent_id, ma_tuyen, start_point_id, end_point_id,
               geometry_source, geometry_version,
               ST_AsGeoJSON(geometry) AS geometry_geojson
        FROM geo_segments
        WHERE source_id = ANY($1::text[]) AND is_deleted = false
        """,
        source_ids,
    )
    return [_row_to_segment_dict(r) for r in rows]


async def get_segments_bbox(
    pool: asyncpg.pool.Pool,
    min_lng: float, min_lat: float, max_lng: float, max_lat: float,
    limit: int,
    simplify_tolerance: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    `simplify_tolerance` (độ, cùng đơn vị SRID 4326) nếu > 0 sẽ áp dụng
    ST_SimplifyPreserveTopology để giảm số vertex của LineString trước khi
    trả về — hữu ích khi zoom nhỏ, đoạn cáp do người dùng tự vẽ tay (USER)
    có nhiều điểm uốn, giảm dung lượng response mà hình dạng tổng thể không
    đổi đáng kể ở độ phân giải hiển thị đó. Đoạn AUTO (2 điểm) không bị ảnh
    hưởng gì (không thể đơn giản hoá thêm được nữa).
    """
    geom_expr = "geometry"
    if simplify_tolerance and simplify_tolerance > 0:
        geom_expr = f"ST_SimplifyPreserveTopology(geometry, {float(simplify_tolerance)})"

    rows = await pool.fetch(
        f"""
        SELECT source_id, parent_id, ma_tuyen, start_point_id, end_point_id,
               geometry_source, geometry_version,
               ST_AsGeoJSON({geom_expr}) AS geometry_geojson
        FROM geo_segments
        WHERE is_deleted = false
          AND geometry && ST_MakeEnvelope($1, $2, $3, $4, 4326)
        LIMIT $5
        """,
        min_lng, min_lat, max_lng, max_lat, limit,
    )
    return [_row_to_segment_dict(r) for r in rows]


async def get_segments_by_parent(pool: asyncpg.pool.Pool, parent_id: str) -> List[Dict[str, Any]]:
    """Toàn bộ segment active thuộc 1 tuyến (parent_id = tuyến._id), dùng cho GET /map/routes."""
    rows = await pool.fetch(
        """
        SELECT source_id, parent_id, ma_tuyen, start_point_id, end_point_id,
               geometry_source, geometry_version,
               ST_AsGeoJSON(geometry) AS geometry_geojson
        FROM geo_segments
        WHERE parent_id = $1 AND is_deleted = false
        """,
        parent_id,
    )
    return [_row_to_segment_dict(r) for r in rows]


async def get_segment_ids_by_parent_all(pool: asyncpg.pool.Pool, parent_id: str) -> List[Dict[str, Any]]:
    """Toàn bộ đoạn cáp thuộc 1 tuyến trong PostGIS (KHÔNG lọc is_deleted) -
    dùng để incremental sync so sánh với danh sách active hiện tại ở MongoDB."""
    rows = await pool.fetch(
        "SELECT source_id, is_deleted FROM geo_segments WHERE parent_id = $1",
        parent_id,
    )
    return [dict(r) for r in rows]


async def nearby_segments(
    pool: asyncpg.pool.Pool, lat: float, lng: float, radius_m: float, limit: int,
) -> List[Dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT source_id, start_point_id, end_point_id, ma_tuyen,
               ST_Distance(geometry::geography, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography) AS distance_m
        FROM geo_segments
        WHERE is_deleted = false
          AND ST_DWithin(
            geometry::geography,
            ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography,
            $3
        )
        ORDER BY distance_m ASC
        LIMIT $4
        """,
        lng, lat, radius_m, limit,
    )
    return [dict(r) for r in rows]


async def update_segment_geometry(
    pool: asyncpg.pool.Pool,
    source_id: str,
    coordinates: List[List[float]],
    geometry_source: str,
    expected_version: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Cập nhật geometry của 1 segment, tăng geometry_version.
    Trả về None nếu segment không tồn tại (hoặc đã bị soft-delete), hoặc nếu
    expected_version không khớp (optimistic locking) — trong trường hợp đó
    raise ValueError riêng để router phân biệt 404 vs 409.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                "SELECT source_id, geometry_version FROM geo_segments "
                "WHERE source_id = $1 AND is_deleted = false FOR UPDATE",
                source_id,
            )
            if existing is None:
                return None

            if expected_version is not None and existing["geometry_version"] != expected_version:
                raise ValueError(
                    f"Version không khớp: hiện tại={existing['geometry_version']}, "
                    f"client gửi expected_version={expected_version}."
                )

            row = await conn.fetchrow(
                """
                UPDATE geo_segments
                SET geometry = ST_SetSRID(ST_GeomFromGeoJSON($2), 4326),
                    geometry_source = $3,
                    geometry_version = geometry_version + 1
                WHERE source_id = $1
                RETURNING source_id, parent_id, ma_tuyen, start_point_id, end_point_id,
                          geometry_source, geometry_version,
                          ST_AsGeoJSON(geometry) AS geometry_geojson
                """,
                source_id,
                json.dumps({"type": "LineString", "coordinates": coordinates}),
                geometry_source,
            )
    return _row_to_segment_dict(row) if row else None