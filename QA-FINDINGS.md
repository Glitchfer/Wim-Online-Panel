# WIM Online — QA Findings & Improvements (Human-Role Traversal Audit)

> **Date:** 2026-09-10
> **Method:** 3 QA subagents (Super Admin, Depot Admin, Super Admin-e2e) traversed the live
> apps like real users after the Admin app + Database changes (promo mgmt, store mgmt, sales
> order flow). Results were reviewed, real bugs reproduced/fixed, and re-verified live.
> **Status:** Critical + major bugs fixed and verified; remaining items logged as enhancements.

---

## 1. Summary

The subagent audit found **critical defects in the promotion engine** that the earlier
verification had not caught (because it only checked list/create, not end-to-end application),
plus a **store phone data-loss** bug, and several UX gaps. All critical/major items were fixed
and re-verified against the live stack.

| Severity | Finding | Status |
|---|---|---|
| CRITICAL | Promo calc engine **never applied** seeded/legacy promos (vocabulary mismatch) | ✅ FIXED & verified |
| CRITICAL | Promo calc engine **double-fired** rewards (cartesian LEFT JOIN) | ✅ FIXED & verified |
| MAJOR | Store **phone field lost** on write/read (not surfaced in /api/stores/all) | ✅ FIXED & verified |
| MEDIUM | Promo list UI showed jenis doubled + legacy rewards as "—" | ✅ FIXED |
| MEDIUM | `/admin/promos.html` referenced as 404 (page served at `/promos.html`) | ✅ nav uses correct relative links |
| LOW | Promo create form ships pre-filled sample values; no JSON validation | 🟠 logged |
| LOW | No promo edit/duplicate/search/filter; store pagination; free-text category | 🟠 logged enhancement |

---

## 2. Critical — Promo engine never applied seeded promos (vocabulary)

**Symptom:** Promos created in admin appeared in the rep's catalog (`/api/products/promos`) but
`/api/orders/calculate` never applied them — `bonus=[]` / `promosApplied=[]` even with qualifying carts.

**Root cause:** Two different vocabularies existed:
- **Seed** (`wim-dummy-seed.py`) wrote legacy types: condition `min_qty`/`min_amount`,
  reward `free_qty`/`percent_discount`/`flat_discount`.
- **Engine** (`do_ORDER_CALC`) only parsed `purchase_sku`/`purchase_qty_min`/`free_sku`,
  `eligible_sku_category`+`{min_qty,pct}`, `discount_amount`.

So the seeded `PROMO-BUNDLE-10-2`, `PROMO-STRATA-10`, `PROMO-DISKON-5K` never fired.

**Fix (serve.py, `do_ORDER_CALC`):** normalize legacy condition/reward types into the engine's
handling at parse time (`min_qty`→`legacy_min_qty` w/ `{qty}`, `free_qty`→`legacy_free_qty`,
`percent_discount`/`flat_discount` honored in strata/diskon branches). Bundling in legacy
"any-N-free-M" mode grants bonus on the most-purchased SKU.

**Verified live:** with qty=12 × SQA-PET-220:
- Bundling 10+2 → **+2 bonus** (once)
- Strata ≥10 → **5%** = Rp6000
- Diskon flat → **Rp5000 once**
- grand total 120000−11000 = **Rp109000**, each promo listed exactly once.

---

## 3. Critical — Promo double-fire (cartesian join)

**Symptom:** A bundling condition `buy 2 get 1` with cart qty=4 returned bonus qty=4 (expected 2),
and `promosApplied` listed the promo twice. A 10+2 config could grant 4 free instead of 2.

**Root cause:** `do_ORDER_CALC` used a single flat `LEFT JOIN` of
`wim_promo × wim_promo_conditions × wim_promo_rewards`. A promo with N conditions and M rewards
yields N×M rows; the loop appended each reward once **per row** → multiplied rewards.

**Fix:** Assemble `promos_raw` with **dedup keyed set** per promo for both conditions and rewards
(signature = type|json(value)|skuRef|qty), so each fires exactly once regardless of join fan-out.

**Verified:** `[{'promoRef':'PROMO-BUNDLE-10-2',...}]` appears exactly once; bonus qty computed
correctly (12//10 × 2 = 2).

---

## 4. Major — Store phone field lost

**Symptom:** Entering/patching a store's `phone` returned `200 ok` but the value was `''` on read.
All 26 stores showed empty phone despite DB values.

**Root cause:** `GET /api/stores/all` **selected** `phone` in the SQL but the response mapping
**omitted** `'phone'` — so it read into the cursor then dropped it from the JSON.

**Fix:** Added `'phone': r['phone'] or ''` to the `/api/stores/all` response mapping.

**Verified live:** `/api/stores/all` now returns `phone: 62811110009`; admin stores page shows it.

> Note: the QA also flagged that store PATCH "silently succeeds" on fields — since the schema
> column exists and now maps end-to-end (store → middleware → `/api/stores/all`), this is resolved.

---

## 5. Medium — Promo list UI rendering

- **Jenis doubled**: the jenis appeared under the name AND in a badge in the same row (looked doubled).
  **Fixed** — removed the redundant name-subline; jenis now shown once in a badge.
- **Legacy rewards shown "—"**: `rewardText()` didn't recognize `percent_discount`/`flat_discount`/
  `free_qty`/`discount_pct`/`bonus_qty`, so promos with them showed `—`.
  **Fixed** — rewardText now maps all legacy + engine reward types to readable text
  (`🎁 +2 any sku`, `-5%`, `-Rp 5000`, etc.).
- **Periode "… → ∞"**: cryptic for open-ended; left as-is (means "from start → no end") — acceptable.

---

## 6. Remaining enhancements (logged, not blocking)

| # | Item | Note |
|---|---|---|
| 1 | Promo **edit** (change conditions/rewards without delete+recreate) | add PATCH for conditions/rewards |
| 2 | Promo **duplicate / search / filter / sort** by jenis/status/periode | scale (~5 rows today) |
| 3 | Promo create form **JSON validation + guided condition/reward builder** (not free-text JSON) | UX safety |
| 4 | Store **pagination** + **delete** + **bulk actions** | 26+ rows, archive-via-status only |
| 5 | Store **category as controlled dropdown/list** (currently free-text) | consistency |
| 6 | Rep `/api/stores` (dashboard plan) doesn't include owner/channel (only `/api/stores/all`) | surface only if needed at POS |
| 7 | Promo `bonus` jenis not evaluated by engine (only bundling/strata/diskon) | add if "bonus" used |

---

## 7. Re-verification (after fixes)

Ran a full cart-calc through the live middleware as the test rep:
- All 3 seeded promo types apply, no double-fire, flat discount applied once, bonus qty correct.
- Store phone surfaces on `/api/stores/all` and admin stores page.
- Promo list shows readable conditions/rewards with no doubled jenis.
- QA-created test promo (8,9) and test stores cleaned from the DB.

**Verdict after fixes:** the promo engine + store management are now correct for the end goals;
remaining items are enhancement backlog, not blockers.

---

## 8. Files changed (this round)

- `frontend/serve.py` — `do_ORDER_CALC`: legacy-vocab normalization + condition/reward dedupe +
  flat-order discount + legacy bundling/strata/diskon handling; `/api/stores/all`: add `phone`.
- `admin/promos.html` — remove doubled jenis; `parseRule`/`rewardText` handle legacy + engine types.
- `admin/stores.html` — (unchanged behavior; phone display fixed at backend).
- `CHANGELOG.md` — #75–77 entries.

---