-- ============================================================================
-- Migration 002: thêm is_deleted vào geo_points / geo_segments.
--
-- Lý do: đồng bộ trước đây (001) chỉ UPSERT theo source_id, không có cách
-- nào biết 1 điểm/đoạn cáp đã bị soft-delete ở MongoDB để cũng ẩn nó khỏi
-- PostGIS. Thêm is_deleted để incremental sync (gis_incremental_sync.py)
-- có thể soft-delete tương ứng khi phát hiện bản ghi không còn active ở
-- MongoDB, thay vì để nó "sống mãi" trên map.
--
-- An toàn chạy nhiều lần (IF NOT EXISTS). Không đụng MongoDB.
-- ============================================================================

ALTER TABLE geo_points
    ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE geo_segments
    ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_geo_points_is_deleted
    ON geo_points (is_deleted);

CREATE INDEX IF NOT EXISTS idx_geo_segments_is_deleted
    ON geo_segments (is_deleted);
