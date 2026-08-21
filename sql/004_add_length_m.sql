ALTER TABLE geo_segments
    ADD COLUMN IF NOT EXISTS length_m DOUBLE PRECISION;

CREATE OR REPLACE FUNCTION gis_set_segment_length()
RETURNS TRIGGER AS $$
BEGIN
    NEW.length_m = ST_Length(NEW.geometry::geography);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_geo_segments_length ON geo_segments;
CREATE TRIGGER trg_geo_segments_length
    BEFORE INSERT OR UPDATE OF geometry ON geo_segments
    FOR EACH ROW EXECUTE FUNCTION gis_set_segment_length();

UPDATE geo_segments
SET length_m = ST_Length(geometry::geography)
WHERE length_m IS NULL;

CREATE INDEX IF NOT EXISTS idx_geo_segments_parent_length
    ON geo_segments (parent_id) INCLUDE (length_m)
    WHERE virtual_parent_id IS NULL AND is_deleted = false;