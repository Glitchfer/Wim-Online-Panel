# Pricing per Depo (not per Area/Region) — Plan & Implementation

> **Date:** 2026-09-11 · **Status:** Plan → Implement
> User correction: prices are NOT per area/kecamatan/kabupaten — they are **per depo**.
> Requirement: one-to-one price per product per depo.

## 1. Current model (per region) — to change
- `wim_product_prices(product_uuid, region_id, price, effective_from)` — keyed by **region**.
- `do_PRODUCTS` (field app) resolves `pp.region_id=%s` using the **store's region** (or rep's region).
- `do_PRODUCTS_PRICES_GET/POST` (admin pricing.html) manage a **region×product** grid.

## 2. Target model (per depot) — one-to-one
- `wim_product_prices(product_uuid, depot_id, price, effective_from, region_id)` —
  **keyed by depot** (keep region_id as a mirror for migration/back-compat, drop later).
- Resolution: given a store → its **depot** (through `wim_stores.assigned_salesperson_id` →
  `wim_user_meta.depot_id`, or store's region→depot), select `pp.depot_id=%s`.

### One-to-one definition
A depot has exactly 0..1 price per product (UNIQUE(product_uuid, depot_id)). A depot's price
applies to all stores served by that depot — which is "per depo, not per area."

## 3. Why this maps cleanly
- Depo already carries `region_id` (`wim_depots.region_id`), so depot-level pricing still respects
  area as a dimension without being *the* pricing key.
- Each sales rep belongs to one depot (`wim_user_meta.depot_id`); the store being ordered belongs
  to a sales rep → so the order always resolves to a single depot price. No ambiguity.

## 4. Migration (additive & reversible)
```
ALTER TABLE wim_product_prices ADD COLUMN IF NOT EXISTS depot_id INT REFERENCES wim_depots(id);
-- backfill: for rows with a region, assign the FIRST depot in that region (best effort)
UPDATE wim_product_prices pp SET depot_id = (
   SELECT d.id FROM wim_depots d WHERE d.region_id = pp.region_id ORDER BY d.id LIMIT 1
) WHERE depot_id IS NULL AND region_id IS NOT NULL;
DROP INDEX IF EXISTS ... ; CREATE UNIQUE INDEX IF NOT EXISTS uq_product_depot ON wim_product_prices(product_uuid, depot_id) WHERE depot_id IS NOT NULL;
```

## 5. Backend changes (`serve.py`)
- `do_PRODUCTS` (field app): resolve the depot_id from the store's sales rep / store → use
  `pp.depot_id=%s` for the price; fall back to base `p.price`.
- `do_PRODUCTS_PRICES_GET`: return per-depot price map (products × depots) instead of regions.
- `do_PRODUCTS_PRICES_POST`: UPSERT by (sku × depotId).
- Admin proxy (`admin-server.py`): regenerate `pricing.html` calls to depo-based.

## 6. Frontend (`admin/pricing.html`)
- Replace the "Area / Kecamatan / Kabupaten" grid with a **Depo × Produk** grid:
  rows = products, columns = depots (or a depo selector + product rows). Set price per depo.
- Rename labels per depo.

## 7. Acceptance
- [ ] Admin can set a product price per depo (not per area).
- [ ] Field app shows the correct depo price for a store.
- [ ] A product can have a different price in different depots.
- [ ] Migration reversible; no data destroyed.
- [ ] 3-subagent QA.

## 8. Deploy
Commit, push; apply migration; deploy serve.py + admin-server.py + pricing.html; restart wim-mid + wim-admin.