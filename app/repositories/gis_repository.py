import json
from typing import Any, Dict, List, Optional

import asyncpg


async def upsert_points_batch(pool: asyncpg.pool.Pool, points: List[Dict[str, Any]]) -> int:
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


async def upsert_segments_batch(pool: asyncpg.pool.Pool, segments: List[Dict[str, Any]]) -> int:
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


async def recompute_virtual_segments_for_cable(
    pool: asyncpg.pool.Pool,
    cable_id: str,
    parent_id: Optional[str],
    ma_tuyen: Optional[str],
    chain_points: List[Dict[str, Any]],
) -> List[str]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            if len(chain_points) <= 2:
                await conn.execute(
                    "DELETE FROM geo_segments WHERE virtual_parent_id = $1",
                    cable_id,
                )
                await conn.execute(
                    "UPDATE geo_segments SET is_hidden = false WHERE source_id = $1",
                    cable_id,
                )
                return []

            new_source_ids: List[str] = []
            for i in range(len(chain_points) - 1):
                a = chain_points[i]
                b = chain_points[i + 1]
                sub_id = f"{cable_id}::v{i}"
                new_source_ids.append(sub_id)
                await conn.execute(
                    """
                    INSERT INTO geo_segments
                        (source_id, parent_id, ma_tuyen, start_point_id, end_point_id,
                         geometry, geometry_source, geometry_version, is_deleted,
                         virtual_parent_id, is_hidden)
                    VALUES
                        ($1, $2, $3, $4, $5,
                         ST_SetSRID(ST_MakeLine(ST_MakePoint($6, $7), ST_MakePoint($8, $9)), 4326),
                         'AUTO', 1, false, $10, false)
                    ON CONFLICT (source_id) DO UPDATE SET
                        parent_id = EXCLUDED.parent_id,
                        ma_tuyen = EXCLUDED.ma_tuyen,
                        start_point_id = EXCLUDED.start_point_id,
                        end_point_id = EXCLUDED.end_point_id,
                        is_deleted = false,
                        virtual_parent_id = EXCLUDED.virtual_parent_id,
                        is_hidden = false,
                        geometry = CASE
                            WHEN geo_segments.geometry_source = 'AUTO'
                            THEN EXCLUDED.geometry
                            ELSE geo_segments.geometry
                        END
                    """,
                    sub_id, parent_id, ma_tuyen, a["ma_diem"], b["ma_diem"],
                    a["lng"], a["lat"], b["lng"], b["lat"], cable_id,
                )

            await conn.execute(
                "DELETE FROM geo_segments WHERE virtual_parent_id = $1 AND NOT (source_id = ANY($2::text[]))",
                cable_id, new_source_ids,
            )
            await conn.execute(
                "UPDATE geo_segments SET is_hidden = true WHERE source_id = $1",
                cable_id,
            )
            return new_source_ids


async def soft_delete_segments(pool: asyncpg.pool.Pool, source_ids: List[str]) -> int:
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


async def soft_delete_virtual_segments_by_parent(pool: asyncpg.pool.Pool, parent_ids: List[str]) -> int:
    if not parent_ids:
        return 0
    result = await pool.execute(
        "UPDATE geo_segments SET is_deleted = true WHERE virtual_parent_id = ANY($1::text[]) AND is_deleted = false",
        parent_ids,
    )
    try:
        return int(result.split(" ")[-1])
    except (ValueError, IndexError):
        return len(parent_ids)


async def get_virtual_segment_parents_by_route(pool: asyncpg.pool.Pool, parent_id: str) -> List[Dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT DISTINCT virtual_parent_id
        FROM geo_segments
        WHERE parent_id = $1
          AND virtual_parent_id IS NOT NULL
          AND is_deleted = false
        """,
        parent_id,
    )
    return [dict(r) for r in rows]


def _row_to_segment_dict(row) -> Dict[str, Any]:
    d = dict(row)
    d["geometry"] = json.loads(d.pop("geometry_geojson"))
    return d


async def get_segment(pool: asyncpg.pool.Pool, source_id: str) -> Optional[Dict[str, Any]]:
    row = await pool.fetchrow(
        """
        SELECT source_id, parent_id, ma_tuyen, start_point_id, end_point_id,
               geometry_source, geometry_version, virtual_parent_id, is_hidden,
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
               geometry_source, geometry_version, virtual_parent_id, is_hidden,
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
    geom_expr = "geometry"
    if simplify_tolerance and simplify_tolerance > 0:
        geom_expr = f"ST_SimplifyPreserveTopology(geometry, {float(simplify_tolerance)})"

    rows = await pool.fetch(
        f"""
        SELECT source_id, parent_id, ma_tuyen, start_point_id, end_point_id,
               geometry_source, geometry_version, virtual_parent_id, is_hidden,
               ST_AsGeoJSON({geom_expr}) AS geometry_geojson
        FROM geo_segments
        WHERE is_deleted = false
          AND is_hidden = false
          AND geometry && ST_MakeEnvelope($1, $2, $3, $4, 4326)
        LIMIT $5
        """,
        min_lng, min_lat, max_lng, max_lat, limit,
    )
    return [_row_to_segment_dict(r) for r in rows]


async def get_segments_by_parent(pool: asyncpg.pool.Pool, parent_id: str) -> List[Dict[str, Any]]:
    rows = await pool.fetch(
        """
        SELECT source_id, parent_id, ma_tuyen, start_point_id, end_point_id,
               geometry_source, geometry_version, virtual_parent_id, is_hidden,
               ST_AsGeoJSON(geometry) AS geometry_geojson
        FROM geo_segments
        WHERE parent_id = $1 AND is_deleted = false AND is_hidden = false
        """,
        parent_id,
    )
    return [_row_to_segment_dict(r) for r in rows]


async def get_segment_ids_by_parent_all(pool: asyncpg.pool.Pool, parent_id: str) -> List[Dict[str, Any]]:
    rows = await pool.fetch(
        "SELECT source_id, is_deleted FROM geo_segments WHERE parent_id = $1 AND virtual_parent_id IS NULL",
        parent_id,
    )
    return [dict(r) for r in rows]


async def get_all_segment_ids_non_virtual(pool: asyncpg.pool.Pool) -> List[Dict[str, Any]]:
    rows = await pool.fetch(
        "SELECT source_id, is_deleted FROM geo_segments WHERE virtual_parent_id IS NULL",
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
          AND is_hidden = false
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
                          geometry_source, geometry_version, virtual_parent_id, is_hidden,
                          ST_AsGeoJSON(geometry) AS geometry_geojson
                """,
                source_id,
                json.dumps({"type": "LineString", "coordinates": coordinates}),
                geometry_source,
            )
    return _row_to_segment_dict(row) if row else None