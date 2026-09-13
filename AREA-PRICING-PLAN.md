# WIM Online — Area-Based Pricing & Multi-Area Promos

> **Date:** 2026-09-10
> **Purpose:** Make product prices **per-area (region)** so a sales rep sees the price configured
> for the area the shop (store) is in — instead of one global price. Provide a graphical admin
> price-setter with an area checkbox menu and a **preview-then-confirm** save flow. Extend promos
> to support **multiple areas** (quick checkbox select).
>
> **Legend:** DB = schema/migration, MW = middleware `serve.py`, AS = admin-server, AD = admin
> HTML, SO = sales app.

---

## 1. Concepts

Each **region (area)** `wim_regions` groups a set of depots (`wim_depots.region_id`). Every
**store/shop** belongs to one region (`wim_stores.region_id`). A product's **price is set per
region**; when a sales rep opens the catalog for the shop they are visiting, the middleware
resolves that shop's region and returns the **region price** (falling back to the product's base
`price` if no region override exists).

- Currently promo and price share the same area separation (user will provide the final area
  breakdown later).
- A price row carries an **effective_from (set) date**, so the admin preview can show *price
  before*, *set date before*, and *price after*.

---

## 2. Database changes

### 2.1 `wim_stores.region_id`
```sql
ALTER TABLE wim_stores ADD COLUMN IF NOT EXISTS region_id INT REFERENCES wim_regions(id);
```
Backfill from visit plan (store visited by a rep whose depot is in a region):
```sql
UPDATE wim_stores s SET region_id = um_sub.r
FROM (
  SELECT vp.place_uuid, min(d.region_id) AS r
  FROM wim_visit_plan vp
  JOIN wim_user_meta um ON um.user_id=vp.user_id
  JOIN wim_depots d ON d.id=um.depot_id
  WHERE d.region_id IS NOT NULL GROUP BY vp.place_uuid
) um_sub WHERE um_sub.place_uuid=s.uuid AND s.region_id IS NULL;
```
(`wim_stores.region_id` NULL = region unknown → base price / all-areas price.)

### 2.2 `wim_product_prices` (per-product × per-region price history)
```sql
CREATE TABLE IF NOT EXISTS wim_product_prices (
    id SERIAL PRIMARY KEY,
    product_uuid UUID NOT NULL REFERENCES wim_products(uuid),
    region_id INT NOT NULL REFERENCES wim_regions(id),
    price DECIMAL(15,2) NOT NULL,
    effective_from DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(product_uuid, region_id)
);
```
Semantics:
- A row = the price of `product_uuid` in `region_id`, in effect from `effective_from` (the "set date").
- Base `wim_products.price` = default/all-areas price; a `wim_product_prices` row overrides it in that region.
- `effective_from` records when this price starts (used in the admin preview's "set date before/after").

---

## 3. Middleware changes (`serve.py`)

### 3.1 Sales catalog: price by shop's area
`GET /api/products?store=<store_uuid>`:
- Resolve `store_uuid → wim_stores.region_id`.
- For each product return `price` = region price (from `wim_product_prices` for that region) if
  present, else base `price`.
- Also resolve the **sales user's own region** as fallback when no `store` query is given, so the
  rep sees their area's prices on the browse page.

### 3.2 Admin price endpoints (new)
- `GET /api/admin/products/prices` → for each product, its base price + a map of
  `{region_id: {price, effective_from}}` (current effective price per region) + product sku/name.
- `GET /api/admin/pricing/options` → regions list (id, name) for checkbox UI. (Or reuse filter-options.)
- `POST /api/admin/products/prices` → **bulk apply**: body
  `{ entries:[{sku, price, effective_from}], regionIds:[1,2,3], allAreas:bool }`.
  For each (sku × region) UPSERT into `wim_product_prices`. If `allAreas` → apply to every region;
  if a price already equals the current effective region price, skip / report as *no-change*.
  Returns a summary: `{changed:[{sku,regionId,priceBefore,setDateBefore,priceAfter}], skipped}`.

> The **preview** is computed client-side from `GET /api/admin/products/prices` (price before,
> set-date before) before POSTing; the POST returns the authoritative `priceAfter` for confirmation.

### 3.3 Promos: multi-area
New join table `wim_promo_regions(promo_id, region_id)`:
```sql
CREATE TABLE IF NOT EXISTS wim_promo_regions (
    promo_id INT NOT NULL REFERENCES wim_promo(id),
    region_id INT NOT NULL REFERENCES wim_regions(id),
    PRIMARY KEY(promo_id, region_id)
);
```
- Admin POST/PATCH accept `regionIds:[...]` (or `allAreas`) → replace `wim_promo.region_id` semantics
  with the set of `wim_promo_regions`.
- `do_PROMOS` (sales), `do_ORDER_CALC`, `do_PROMOS_ADMIN_GET` resolve a promo's areas from
  `wim_promo_regions` (fallback: legacy single `region_id`).
- A promo with **no region rows / NULL** = applies to all regions (same as the "all areas" quick pick).

---

## 4. Admin webapp changes

### 4.1 `products.html` — price editor
Add a **"Prices by Area"** mode (button → new panel):
- **Area checkbox menu**: one checkbox per region + new "Quick pick: Semua Area" toggle.
- **Price input + Set date** (`effective_from`, defaults today).
- **Product target**: either edit inline per row (from product list) or a SKU + qty entry.
- **Preview screen** (blocking, before save): table `SKU | Name | Price Before | Set Date Before | Price After`.
  Shows only rows that actually change.
- **Confirm button** → POST bulk → toast + refresh.

### 4.2 `promos.html` — multi-area
Replace the single region `<select>` with a **checkbox area multi-select** + "Semua Area" quick toggle
(kept alongside the existing "Semua Region" list filter).

---

## 5. Sales webapp changes

- `order.html` `loadProducts()` already knows `ctx.storeUuid`; change the fetch to
  `/api/products?store=<storeUuid>` so the catalog shows the shop's area price.
- The product card renders `price` from the middleware (now area-aware) — no other change.
- `checkout`/`calc` alt uses the same area price object (region of the store).

---

## 6. Verification plan

- Backfill: stores linked to visits get `region_id`; verify counts.
- Set region-specific prices via admin bulk API + confirm saving a lower/higher price.
- Sales: `GET /api/products?store=<shop in region A>` returns region A price; a shop with no region
  returns base price.
- Promo: create promo applied to regions A+B, not C; rep in A sees it, rep in C does not; engine
  applies only in A/B.
- Run 3-role QA traversal afterward.

## 7. Docs to update

- `CHANGELOG.md`, `DATABASE-MAPPING.md` (wim_stores.region_id, wim_product_prices, wim_promo_regions),
  `IMPROVEMENT-PLAN.md` / `PROMO-REWORK-PLAN.md` (multi-area), this plan kept as reference.