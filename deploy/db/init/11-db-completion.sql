-- ============================================================
-- WIM Online — DB completion + Goovi/Klikorder parity (additive)
-- Creates missing tables/columns, backfills from existing data.
-- ============================================================

-- 1) Vehicles (was missing; wim_user_meta.vehicle_id dangles)
CREATE TABLE IF NOT EXISTS wim_vehicles (
    id SERIAL PRIMARY KEY,
    kode VARCHAR(64) UNIQUE,
    plat_no VARCHAR(32),
    jenis VARCHAR(64),
    kubikasi NUMERIC(12,2) DEFAULT 0,
    berat_jenis NUMERIC(12,2) DEFAULT 0,
    depot_id INT REFERENCES wim_depots(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vehicles_depot ON wim_vehicles(depot_id);

-- 2) Store code / phone-verification / updated_at (Goovi parity)
ALTER TABLE wim_stores ADD COLUMN IF NOT EXISTS store_code VARCHAR(64);
ALTER TABLE wim_stores ADD COLUMN IF NOT EXISTS phone_verified VARCHAR(24);
ALTER TABLE wim_stores ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;

-- 3) Employee code on user profile
ALTER TABLE wim_user_meta ADD COLUMN IF NOT EXISTS employee_code VARCHAR(64);

-- 4) Unique on store_code (allows multiple NULLs)
CREATE UNIQUE INDEX IF NOT EXISTS uq_stores_store_code ON wim_stores(store_code);

-- 5) Employee code unique where present
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_meta_employee_code ON wim_user_meta(employee_code) WHERE employee_code IS NOT NULL;