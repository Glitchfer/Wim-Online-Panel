-- Area-based pricing migration (2026-09-10)
-- 1) wim_stores.region_id  (the area/shop zone a store belongs to)
ALTER TABLE wim_stores ADD COLUMN IF NOT EXISTS region_id INT REFERENCES wim_regions(id);
CREATE INDEX IF NOT EXISTS idx_stores_region ON wim_stores(region_id);

-- 2) wim_product_prices — per-product per-region price
-- NOTE: a legacy unreferenced wim_product_prices existed with a different (unused) schema;
-- drop it so our schema is authoritative.
DROP TABLE IF EXISTS wim_product_prices;
CREATE TABLE IF NOT EXISTS wim_product_prices (
    id SERIAL PRIMARY KEY,
    product_uuid UUID NOT NULL REFERENCES wim_products(uuid),
    region_id INT NOT NULL REFERENCES wim_regions(id),
    price DECIMAL(15,2) NOT NULL,
    effective_from DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(product_uuid, region_id)
);
CREATE INDEX IF NOT EXISTS idx_product_prices_region ON wim_product_prices(region_id);
CREATE INDEX IF NOT EXISTS idx_product_prices_product ON wim_product_prices(product_uuid);

-- 3) wim_promo_regions — promo applies to many areas
CREATE TABLE IF NOT EXISTS wim_promo_regions (
    promo_id INT NOT NULL REFERENCES wim_promo(id),
    region_id INT NOT NULL REFERENCES wim_regions(id),
    PRIMARY KEY(promo_id, region_id)
);

-- 4) Backfill store region from each store's visited-rep depot's region
UPDATE wim_stores s
SET region_id = um_sub.r
FROM (
    SELECT vp.place_uuid AS uuid, min(d.region_id) AS r
    FROM wim_visit_plan vp
    JOIN wim_user_meta um ON um.user_id = vp.user_id
    JOIN wim_depots d ON d.id = um.depot_id
    WHERE d.region_id IS NOT NULL
    GROUP BY vp.place_uuid
) um_sub
WHERE um_sub.uuid = s.uuid AND s.region_id IS NULL AND s.deleted_at IS NULL;

-- 5) Backfill promo regions from legacy single region_id
INSERT INTO wim_promo_regions (promo_id, region_id)
SELECT id, region_id FROM wim_promo
WHERE region_id IS NOT NULL
ON CONFLICT (promo_id, region_id) DO NOTHING;