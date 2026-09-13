-- ============================================================
-- WIM Online — Administrative region dataset (wilayah)
-- Source: BPS / Kemendagri via api-wilayah-indonesia-2026
--   (jsDelivr CDN snapshot, BPS codes). Data files in deploy/wilayah/.
-- Population: scripts/import_wilayah.py (run once, offline-friendly).
-- Reversible: DROP TABLE wim_wilayah.
-- ============================================================
CREATE TABLE IF NOT EXISTS wim_wilayah (
    id          SERIAL PRIMARY KEY,
    kode        VARCHAR(13) UNIQUE NOT NULL,   -- BPS code (2/4/6/10 digits)
    nama        VARCHAR(120) NOT NULL,
    level       VARCHAR(5) NOT NULL,            -- 'prov' | 'kab' | 'kec' | 'kel'
    parent_kode VARCHAR(13),                    -- parent's BPS code (NULL for provinsi)
    kode_pos    VARCHAR(6)                      -- optional postal code (villages/kelurahan)
);
CREATE INDEX IF NOT EXISTS idx_wilayah_parent ON wim_wilayah(parent_kode);
CREATE INDEX IF NOT EXISTS idx_wilayah_level  ON wim_wilayah(level);
CREATE INDEX IF NOT EXISTS idx_wilayah_name   ON wim_wilayah(LOWER(nama));