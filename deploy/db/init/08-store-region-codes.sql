-- ============================================================
-- WIM Online — Additive migration: store official region CODE columns
-- These persist the BPS/Kemendagri codes selected in the NOO cascading
-- dropdowns, so stores can be filtered by administrative region later
-- (e.g. plan-edit store picker).
-- ALL statements additive & reversible (no data destruction).
-- Apply: psql -f this file against wim_sfa.
-- ============================================================

ALTER TABLE wim_stores ADD COLUMN IF NOT EXISTS province_id  VARCHAR(16);
ALTER TABLE wim_stores ADD COLUMN IF NOT EXISTS city_id      VARCHAR(16);
ALTER TABLE wim_stores ADD COLUMN IF NOT EXISTS kecamatan_id VARCHAR(16);
ALTER TABLE wim_stores ADD COLUMN IF NOT EXISTS kelurahan_id VARCHAR(16);

CREATE INDEX IF NOT EXISTS idx_stores_kecamatan_id ON wim_stores(kecamatan_id);
CREATE INDEX IF NOT EXISTS idx_stores_kelurahan_id ON wim_stores(kelurahan_id);