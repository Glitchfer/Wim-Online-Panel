# WIM Online — Promo System Rework Plan

> **Date:** 2026-09-10
> **Purpose:** Rework the promo engine + admin UI to support exactly **two promo types**
> (bundling bonus / multi-SKU discount), **region-scoped promos**, and a **graphical
> (no-JSON)** admin builder. Changes span database, middleware, admin webapp, sales webapp.
> **Legend:** DB = schema, MW = middleware `serve.py`, AS = admin-server, AD = admin page, SO = sales.

---

## 1. Promo types (the two supported)

1. **Bundling (buy N → bonus free SKU)**
   - Requirement: a *set of SKU+qty* thresholds (e.g. `SQA-PET-220 × 20` OR `× 30` → match any).
   - Reward: **free bonus SKU** (e.g. `SQA-PET-220` bonus at a given qty per bundle).
   - Example: buy 20 or 30 cartons of SANQUA PET 220 → get bonus SKU.

2. **Discount (multi-SKU mix → fixed IDR off)**
   - Requirement: a *multi-SKU combination* must ALL be present in cart
     (e.g. `SQA-PET-220 × 5` **and** `LEVONTE-CUP × 5`).
   - Reward: **fixed IDR discount** (Rp X off the order).
   - Example: buy 5 × SKU-A and 5 × SKU-B → Rp X discount.

Both types share: promo header (nama, ref, jenis, status, priority, stackable, periode) + a
**region assignment** (promos are by region).

---

## 2. Database changes

### 2.1 Add region to promo
```sql
ALTER TABLE wim_promo ADD COLUMN IF NOT EXISTS region_id INT REFERENCES wim_regions(id);
CREATE INDEX IF NOT EXISTS idx_promo_region ON wim_promo(region_id, status);
```
Migrate to the SQL file + apply live.

### 2.2 Requirement model (reuse `wim_promo_conditions`)
Store each requirement as a row:
```sql
INSERT INTO wim_promo_conditions (promo_id, condition_type, condition_value)
VALUES (:id, 'required_sku', '{"sku":"SQA-PET-220","qty":20}');
-- multiple rows = AND (all must be in cart) for discount; OR-match (any threshold) for bundling
```
- **bundling**: one `required_sku` per threshold; multiple `required_sku` rows = alternative thresholds.
- **discount**: multiple `required_sku` rows = ALL must be met (AND).

### 2.3 Reward model (reuse `wim_promo_rewards`)
```sql
-- bundling
INSERT INTO wim_promo_rewards (promo_id, reward_type, reward_sku_ref, reward_qty) VALUES (:id,'free_sku','SQA-PET-220',2);
-- discount
INSERT INTO wim_promo_rewards (promo_id, reward_type, reward_value) VALUES (:id,'discount_amount','{"amount":50000}');
```

---

## 3. Middleware changes (serve.py)

### 3.1 `do_PROMOS` (sales catalog) — region scoped
- Resolve the rep's region (`wim_user_meta.depot_id → wim_depots.region_id`).
- Return promos where `region_id IS NULL OR region_id = <rep region>`.
- Include `regionId` + `regionName` in payload.

### 3.2 `do_ORDER_CALC` — reworked evaluation for the two types
- **Load** promos for the rep's region (same join as catalog).
- **bundling**: for each promo, if ANY required-sku threshold is met (cart has ≥ qty of that sku),
  grant the free bonus SKU (reward `free_sku`), multiplied by how many times the threshold is met.
- **discount**: for each promo, if **ALL** required-sku rows are met, apply fixed `discount_amount`
  once to the order (flat).
- Keep legacy `min_qty`/`free_qty`/`percent_discount`/`flat_discount` normalization for old rows.

### 3.3 Admin promo CRUD (`do_PROMOS_ADMIN_*`)
- `region_id` accepted/returned in GET/POST/PATCH.
- POST/PATCH accept structured `requirements:[{sku,qty}]` + `rewardType` + `reward` (simpler than
  raw conditions/rewards JSON), but keep backward compat.

---

## 4. Admin webapp (`promos.html`)

### 4.1 Region filter
- A **Region dropdown** in the toolbar filters the promo list by region (from `/api/admin/filter-options`).
- Promo rows show their region.

### 4.2 Graphical builder (no JSON)
Replace the raw JSON textareas with a **visual builder**:
- **Promo type** radio/badge: `Bundling (bonus)` or `Discount (IDR)`.
- **Region** select (required).
- **Requirements** (dynamic rows):
  - For **bundling**: SKU dropdown + qty → "buy N of SKU" (can add multiple thresholds).
  - For **discount**: multiple SKU+qty rows → "buy Q of A AND Q of B".
- **Reward**:
  - Bundling → "bonus SKU" dropdown + qty ("get M of SKU free per bundle").
  - Discount → "Rp amount" numeric field.
- Save POSTs/PATCHes structured payload.

### 4.3 Search/filter/sort/toggle/delete/duplicate retained.

---

## 5. Sales webapp

- No heavy UI change: the catalog (`/api/products/promos`) and cart calc already surface promos;
  the region scoping in 3.1/3.2 makes promo appear/apply per-region automatically.
- The order cart bonus + promo summary stay as-is.

---

## 6. Verification plan

- Create one **bundling** promo (region) + one **discount** promo (region) via the new GUI/API.
- Cart calc: meet/not meet thresholds → correct bonus / discount, exactly once.
- Region filter: a rep in region A does NOT see a promo of region B.
- Admin list filters by region; builder saves structured requirements.
- Run 3-role QA traversal afterward.

## 7. Docs to update

- `CHANGELOG.md`, `DATABASE-MAPPING.md` (promo region), `IMPROVEMENT-PLAN.md` (mark done),
  this rework plan kept as reference.

---