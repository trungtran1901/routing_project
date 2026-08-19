ALTER TABLE geo_segments
    ADD COLUMN IF NOT EXISTS virtual_parent_id TEXT;

ALTER TABLE geo_segments
    ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_geo_segments_virtual_parent_id
    ON geo_segments (virtual_parent_id);

CREATE INDEX IF NOT EXISTS idx_geo_segments_is_hidden
    ON geo_segments (is_hidden);