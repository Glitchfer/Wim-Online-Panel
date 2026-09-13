# Promo Edit — "Any Product", AND/OR Conditions, Redeem Limit

> **Status:** PLAN (not implemented) · **Date:** 2026-09-11
> **Goal:** extend the promo editor so bundling can express (1) an "any/mix product" purchase condition, (2) explicit AND vs OR between requirement rows, and (3) an optional per-promo redeem limit (or unlimited).

---

## 1. Current model (what exists today)

**DB (`wim_promo*` tables):**
- `wim_promo` — promo master (promo_ref, nama, jenis not null incl. `bundling`, status, priority, stackable, periode, min_transaction_amount, max_discount_amount, region_id). **No redeem-limit column.**
- `wim_promo_conditions` — `promo_id, condition_type, condition_value, condition_product_id`. New format uses `condition_type='required_sku'`, `condition_value=JSON {"sku":X,"qty":N}`. **No operator/AND-OR column.**
- `wim_promo_rewards` — `promo_id, reward_type (free_sku | discount_*), reward_sku_ref, reward_qty, reward_value`.

**Editor UI (`admin/promos.html`):**
- Requirements list (`#reqList`) = N rows, each a single `SKU` dropdown + `Qty`. `addReqRow()` (line 215), `readReqRows()` (line 230).
- **Row semantics today:** the UI hint says *"Beberapa baris = salah satu terpenuhi (atau)"* — multiple rows are treated as **OR** (any threshold met). There is no AND option and no per-row operator control.
- Reward (bundling) = `Bonus SKU` + `Qty` only.

**Engine (`frontend/serve.py`, ~line 3094):**
- Bundling: builds `thresholds` from `required_sku` rows, then `matched = next((th for th in thresholds if …))` → **any ONE** threshold met triggers (OR semantics, first match).
- Legacy total-mode exists internally as `thresholds=[{'sku': None, 'qty': N}]` (line 3114, `legacy_total_mode`) — i.e. "buy N total of ANY product" is *already representable at the engine level* via `sku: None`, but **the editor cannot express it** (dropdown only lists real SKUs).
- Bonus grant: `mult = _sku_qty(matched['sku']) // matched['qty']` → free qty = `reward.qty × mult`, no cap.

---

## 2. What to add (user requirements → mapping)

| # | User want | Current gap | Plan |
|---|---|---|---|
| A | Product-condition dropdown gains **"Any Product"** option | Editor only offers real SKUs; engine has hidden `sku:None` total-mode | Add `*ANY*`/`ANY MIX` option → store sku `null` in condition; engine already reads `sku:None` as total-qty mode |
| B | Choose **AND or OR** before each SKU requirement | Rows are hard-wired OR; no operator | Add `and_or` operator column + UI dropdown per row (first row has no operator or defaults OR) |
| C | **Unlimited redeems** checkbox; if unchecked, a **redeem-count** box | No redeem-limit storage or engine cap | Add `redeem_limit` on `wim_promo` (NULL/0 = unlimited); engine caps free-qty by remaining redeems |

---

## 3. Database changes (all additive, reversible)

```sql
-- A. Operator between requirement rows (AND | OR)
ALTER TABLE wim_promo_conditions ADD COLUMN and_or VARCHAR(8) DEFAULT 'or';
--   'or'  = this row is an alternative to the previous (ANY)
--   'and' = this row must ALSO be met (ALL)

-- B. "Any Product" requirement: condition_value already stores {"sku":null,"qty":N}
--    (no schema change; engine supports sku:None total-mode since legacy)

-- C. Redeem limits — BOTH per-order AND promo-lifetime (per decision 2026-09-11):
ALTER TABLE wim_promo
    ADD COLUMN redeem_limit_per_order INT,   -- NULL/0 = unlimited per order
    ADD COLUMN redeem_limit_lifetime  INT;   -- NULL/0 = unlimited lifetime

-- C2. Lifetime usage counter (new table)
CREATE TABLE wim_promo_usage (
    promo_id      INT NOT NULL REFERENCES wim_promo(id) ON DELETE CASCADE,
    used_count    INT NOT NULL DEFAULT 0,          -- total grants applied
    updated_at    TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (promo_id)
);
```

Grants: `wim_app` gets DML on the three affected objects (`wim_promo_conditions`, `wim_promo`, `wim_promo_usage` + its sequence) — add explicit `GRANT` lines in the migration.

**Column function notes (doc requirement):**
- `wim_promo_conditions.and_or` — logical join between this requirement and the previous one within the same promo. `and` = must be satisfied together (ALL), `or` = alternative (ANY). Mirrors the Goovi/Klikorder "Additional Conditions" concept.
- `wim_promo.redeem_limit_per_order` — how many times the promo's reward may be granted **in a single order**; `0/NULL` = unlimited per order.
- `wim_promo.redeem_limit_lifetime` — how many times the reward may be granted **across all orders ever**; `0/NULL` = unlimited lifetime.
- `wim_promo_usage.used_count` — running total of grants for the promo, incremented transactionally whenever a bonus is applied; backs the lifetime cap.

---

## 4. Backend changes (`frontend/serve.py`)

**Condition/reward mapping on read** (peg ~line 3007): when emitting a condition of type `required_sku`, include `andOr: c.and_or or 'or'` and, when `val.sku` is empty/null, emit `{type:'required_sku', value:{sku:null, qty:N}}` so the editor can pre-select **Any Product**.

**Engine — requirement evaluation** (currently line 3117 `matched = next(...)`) must become operator-aware:
- Group `required_sku` rows left-to-right: start with an accumulator of "met" flags; `and_or='and'` requires the joined row to be met for the promo to fire; `or` accepts alternatives (the current OR behavior).
- **Multiplier (decision 2026-09-11):** when an AND chain has multiple thresholds, the bonus multiplier is **min over all met AND thresholds** (conservative). Each alternative (`or`) row still grants on its own threshold.
- "Any Product" (`sku` null) row → treated like legacy total-mode: met when `sum(purchased qty) >= qty`.

**Redeem caps (decision 2026-09-11) — apply BOTH, then unlimited is just "both NULL":**
1. Per-order: after computing `mult`, if `redeem_limit_per_order > 0`, `mult = min(mult, redeem_limit_per_order)`.
2. Lifetime: guard the grant with a **transactional** read/update of `wim_promo_usage` — only grant if `used_count + mult <= redeem_limit_lifetime` (when set), then `UPDATE wim_promo_usage SET used_count = used_count + mult` in the same transaction as the order. `redeem_limit_lifetime` NULL/0 → no lifetime check. (Row inserted lazily on first use with `ON CONFLICT (promo_id) DO UPDATE`.)

**Bonus SKU (decision 2026-09-11):** the reward **must name an explicit Bonus SKU** — never auto-pick the max-qty purchased sku. If no Bonus SKU is set, the promo does not grant. (Removes the legacy `max(purchased,…)` fallback at line 3136.)

---

## 5. Editor UI changes (`admin/promos.html`)

1. **Requirement row** (`addReqRow`, line 215) gains an operator dropdown **before** the SKU select: `(-- | and | or)`. First row: operator hidden/disabled (no predecessor). Subsequent rows default to `or`.
2. **SKU dropdown** (`selectSkuOptions`, line 198) gains a leading option `* — Any Product — *` (`value=""`). When chosen → `readReqRows` emits `{sku:null, qty:…}`; the row label becomes "Any SKU / mix".
3. **Save** (`buildPromoPayload` / requirements map, ~line 373-377): include `andOr` per requirement (skip on first row) and allow empty `sku` → `null`.
4. **Open/edit** (mapping ~line 311-333): rebuild rows honoring `andOr` and `sku:null`.
5. **Redeem block** (in form, near reward): two checkbox+input pairs:
   - `☑ Per-order: unlimited` — when unchecked → `<input type=number id=fRedeemPerOrder min=0>` "Hoeveel redeems per pesanan".
   - `☑ Lifetime: unlimited` — when unchecked → `<input type=number id=fRedeemLifetime min=0>` "Hoeveel redeems totaal (alle pesanan)".
   Both default **checked (unlimited)**. If `fRedeemPerOrder` unchecked and input empty → validation error.
6. **List read** skip/cover: parseRule can stay; optionally append "×N redeems" or "unlimited" to the row.

---

## 6. Reset / migration / QA plan
- SQL migration file: `deploy/db/init/12-promo-conditions.sql` (`ALTER`s + `wim_promo_usage` + grants). Apply live, reversible via `ALTER TABLE … DROP COLUMN` / `DROP TABLE wim_promo_usage`.
- After implementation: 3 QA subagents (super_admin configuring promos, depo_admin validating an order, sales rep placing an order) to confirm (A) any-product promo fires, (B) AND vs OR produce different results on the same order, (C) **per-order** cap blocks a 3rd bonus when limit=2, (D) **lifetime** cap blocks an order once `used_count` exhausts it (and persists across orders), then fix→re-verify as usual.
- Add note to `docs/KLIKORDER-PROMO-COMPARISON-AND-IMPORT.md` mapping these editor capabilities to the promo columns the rekaps carry.

---

## 7. Resolved decisions (owner: rein, 2026-09-11)
1. **Redeem scope:** BOTH a **per-order cap** (`redeem_limit_per_order`, min=0 unlimited) AND a **promo-lifetime total** (`redeem_limit_lifetime` + `wim_promo_usage` counter). "Unlimited" = both columns NULL/0.
2. **AND multiplier:** `min` over all met AND thresholds (conservative); OR alternatives grant on their own threshold.
3. **Any-Product bonus SKU:** must be **explicitly named**; no auto-pick fallback.