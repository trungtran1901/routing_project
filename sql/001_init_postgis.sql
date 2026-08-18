-- ============================================================================
-- GIS layer schema (PostgreSQL + PostGIS)
-- Đây là schema ĐỘC LẬP với MongoDB. MongoDB vẫn là source of truth cho
-- business/topology data. PostGIS chỉ lưu geometry + các field tối thiểu
-- cần cho spatial query, liên kết ngược tới MongoDB qua "source_id".
--
-- An toàn chạy nhiều lần: dùng IF NOT EXISTS / CREATE OR REPLACE.
-- Không đụng tới MongoDB, không migrate dữ liệu production Mongo.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- ----------------------------------------------------------------------------
-- geo_points: chiếu (projection) của các điểm (MongoDB: instance_data_hatang_
-- quanlytuyen_newversion_detail) sang PostGIS.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS geo_points (
    id            BIGSERIAL PRIMARY KEY,
    source_id     TEXT NOT NULL UNIQUE,      -- = point.ma_diem (Mongo)
    parent_id     TEXT,                       -- = point.parent_id (tuyến _id)
    ma_tuyen      TEXT,
    ten_diem      TEXT,
    point_type    TEXT,
    geometry      geometry(Point, 4326) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_geo_points_geometry
    ON geo_points USING GIST (geometry);

CREATE INDEX IF NOT EXISTS idx_geo_points_parent_id
    ON geo_points (parent_id);

CREATE INDEX IF NOT EXISTS idx_geo_points_ma_tuyen
    ON geo_points (ma_tuyen);

-- ----------------------------------------------------------------------------
-- geo_segments: chiếu của đoạn cáp (MongoDB: instance_data_hatang_quan_ly_cable)
-- sang PostGIS. Mỗi segment nối start_point_id -> end_point_id (= ma_diem).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS geo_segments (
    id                BIGSERIAL PRIMARY KEY,
    source_id         TEXT NOT NULL UNIQUE,   -- = cable._id (Mongo)
    parent_id         TEXT,                    -- = cable.parent_id (tuyến _id)
    ma_tuyen          TEXT,
    start_point_id    TEXT NOT NULL,           -- = cable.start_point (ma_diem)
    end_point_id      TEXT NOT NULL,           -- = cable.end_point (ma_diem)
    geometry          geometry(LineString, 4326) NOT NULL,
    geometry_source    TEXT NOT NULL DEFAULT 'AUTO'
                        CHECK (geometry_source IN ('AUTO', 'USER', 'IMPORTED', 'GOOGLE')),
    geometry_version   INTEGER NOT NULL DEFAULT 1,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_geo_segments_geometry
    ON geo_segments USING GIST (geometry);

CREATE INDEX IF NOT EXISTS idx_geo_segments_start_point
    ON geo_segments (start_point_id);

CREATE INDEX IF NOT EXISTS idx_geo_segments_end_point
    ON geo_segments (end_point_id);

CREATE INDEX IF NOT EXISTS idx_geo_segments_parent_id
    ON geo_segments (parent_id);

CREATE INDEX IF NOT EXISTS idx_geo_segments_ma_tuyen
    ON geo_segments (ma_tuyen);

-- ----------------------------------------------------------------------------
-- geo_routes: KHÔNG tạo ở phase này. Route hiện tại (tuyến) không có geometry
-- riêng biệt độc lập với các segment của nó — sơ đồ tuyến hiện được suy ra
-- từ tập hợp geo_segments theo ma_tuyen/parent_id. Nếu sau này cần một
-- geometry tổng hợp (ví dụ MultiLineString bounding của cả tuyến để zoom-to-
-- fit nhanh hơn), có thể thêm bảng geo_routes lúc đó mà không phá vỡ gì ở đây.
-- ----------------------------------------------------------------------------

-- Trigger tiện ích: tự cập nhật updated_at khi UPDATE.
CREATE OR REPLACE FUNCTION gis_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_geo_points_updated_at ON geo_points;
CREATE TRIGGER trg_geo_points_updated_at
    BEFORE UPDATE ON geo_points
    FOR EACH ROW EXECUTE FUNCTION gis_set_updated_at();

DROP TRIGGER IF EXISTS trg_geo_segments_updated_at ON geo_segments;
CREATE TRIGGER trg_geo_segments_updated_at
    BEFORE UPDATE ON geo_segments
    FOR EACH ROW EXECUTE FUNCTION gis_set_updated_at();
