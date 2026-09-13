-- WIM Online — user_meta columns for full-profile editing (additive & reversible)
-- Adds columns the user-edit menu needs (parity with store profile fields).
ALTER TABLE wim_user_meta ADD COLUMN IF NOT EXISTS npwp_name VARCHAR(255);
ALTER TABLE wim_user_meta ADD COLUMN IF NOT EXISTS kendaraan VARCHAR(255);
ALTER TABLE wim_user_meta ADD COLUMN IF NOT EXISTS kode_pos VARCHAR(16);
ALTER TABLE wim_user_meta ADD COLUMN IF NOT EXISTS kecamatan VARCHAR(120);
ALTER TABLE wim_user_meta ADD COLUMN IF NOT EXISTS kelurahan VARCHAR(120);
GRANT SELECT, INSERT, UPDATE, DELETE ON wim_user_meta TO wim_app;