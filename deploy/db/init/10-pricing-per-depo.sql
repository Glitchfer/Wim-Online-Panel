-- ============================================================
-- WIM Online — Pricing per Depo (not per Area/Region)
-- Additive & reversible. Makes product price a 1:1 per depot:
--   wim_product_prices.product_uuid × depot_id (UNIQUE)
-- Also links each store to its depot (store → depot → price).
-- Apply: psql against wim_sfa.
-- ============================================================

-- 1) Link each store to its servicing depot (one-to-one).
ALTER TABLE wim_stores ADD COLUMN IF NOT EXISTS depot_id INT REFERENCES wim_depots(id);
-- Backfill store.depot_id from the store's assigned sales rep's depot, else region's first depot.
UPDATE wim_stores s SET depot_id = (
    SELECT um.depot_id FROM wim_user_meta um WHERE um.user_id = s.assigned_salesperson_id LIMIT 1
) WHERE s.depot_id IS NULL AND s.assigned_salesperson_id IS NOT NULL;
UPDATE wim_stores s SET depot_id = (
    SELECT d.id FROM wim_depots d WHERE d.region_id = s.region_id ORDER BY d.id LIMIT 1
) WHERE s.depot_id IS NULL AND s.region_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_stores_depot ON wim_stores(depot_id);

-- 2) Price now keyed by depot. Add depot_id + mirror region_id.
ALTER TABLE wim_product_prices ADD COLUMN IF NOT EXISTS depot_id INT REFERENCES wim_depots(id);
-- Backfill depot from region (first depot in that region).
UPDATE wim_product_prices pp SET depot_id = (
    SELECT d.id FROM wim_depots d WHERE d.region_id = pp.region_id ORDER BY d.id LIMIT 1
) WHERE pp.depot_id IS NULL AND pp.region_id IS NOT NULL;

-- 3) One-to-one: a product has at most one price per depot.
-- Drop the old region-level unique (pricing is now per-depot; region_id stays as a mirror).
ALTER TABLE wim_product_prices DROP CONSTRAINT IF EXISTS wim_product_prices_product_uuid_region_id_key;
DROP INDEX IF EXISTS uq_product_depot;
CREATE UNIQUE INDEX uq_product_depot ON wim_product_prices(product_uuid, depot_id) WHERE depot_id IS NOT NULL;