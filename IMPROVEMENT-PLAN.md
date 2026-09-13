# WIM Online — Improvement Plan: Resolution of QA Backlog

> **Date:** 2026-09-10
> **Purpose:** Plan + implement fixes for all remaining issues found in the QA role-traversal
> audit (`QA-FINDINGS.md §6` enhancement backlog). Each item below is defined with the fix
> approach, the files to touch, and a verification step.
> **Legend:** MW = middleware `serve.py`, AS = admin-server, AD = admin page, SO = sales frontend.

---

## Priorities & items

| # | Item (from QA-FINDINGS §6) | Fix approach | Files |
|---|---|---|---|
| 1 | **Promo edit** (change conditions/rewards without delete+recreate) | Middleware PATCH replaces conditions/rewards (delete + reinsert) when `conditions`/`rewards` present; admin UI edit form reuses create form pre-filled | MW `do_PROMOS_ADMIN_PATCH`, AD `promos.html` |
| 2 | **Promo duplicate + search/filter/sort** | Frontend: duplicate action (POST same payload w/ new name); filter selects + sort by jenis/status; search box | AD `promos.html` |
| 3 | **Promo create JSON validation + guided builder** | Frontend: validate conditions/rewards JSON with clear error; optionally prefill from a small builder (keep JSON for power users) | AD `promos.html` |
| 4 | **Store pagination + delete + bulk actions** | Middleware `/api/stores/all` pagination (limit/offset); admin store DELETE (soft `status` or new endpoint); page shows pagination controls | MW, AS, AD `stores.html` |
| 5 | **Store category controlled dropdown** | Admin uses a category list (from existing data + standard set) instead of free-text; keep ability to type new | AD `stores.html` |
| 6 | **Rep `/api/stores` include owner/channel** | Add owner_name/channel/category to `do_MY_STORES` SELECT + mapping | MW `do_MY_STORES` |
| 7 | **Promo `bonus` jenis not evaluated** | Add `bonus` handling in `do_ORDER_CALC` (simplest: treat like bundling w/ store-defined trigger, or explicit bonus-only free item config) | MW `do_ORDER_CALC` |

---

## Item 1 — Promo edit (conditions/rewards)

**Backend (`do_PROMOS_ADMIN_PATCH`):** when the PATCH body includes `conditions` (list) or
`rewards` (list), replace the promo's existing rows:
1. `DELETE FROM wim_promo_conditions WHERE promo_id=%s`
2. `DELETE FROM wim_promo_rewards WHERE promo_id=%s`
3. Re-insert the provided conditions/rewards (same shape as POST).
4. Also update header fields (nama/jenis/status/priority/stackable/periode) as today.

**Admin (`promos.html`):** add an **Edit** button per row that opens the create form pre-filled
with the promo's current header + parsed conditions/rewards JSON; Save PATCHes `/api/admin/promos/:id`
with the full payload.

---

## Item 2 — Promo duplicate + search/filter/sort

**Admin (`promos.html`):**
- **Duplicate**: button per row → POST `/api/admin/promos` with the same conditions/rewards and
  `nama` suffixed ` (copy)`, then reload.
- **Search**: text input filters rows by `nama`/`promoRef` (client-side, live).
- **Filter by jenis**: dropdown (All/bundling/strata/diskon/bonus).
- **Sort**: by priority / status / name (clickable headers or a select).

---

## Item 3 — Promo create JSON validation + guided builder

**Admin (`promos.html`):** before submit, parse the two JSON textareas; produce a readable error
(`Kondisi JSON tidak valid: {err}`) with the offending line; block submit on malformed JSON.
Add small helper buttons to insert common condition/reward templates (Bundling 10+2, Strata 5%,
Diskon Rp5000) so a non-technical manager can start without writing raw JSON.

---

## Item 4 — Store pagination + delete

**Backend:** extend `GET /api/stores/all` with `?page=` & `?per_page=`; return `total` and slice.
Add `DELETE /api/stores/:uuid` (admin) → soft-delete (sets `deleted_at` / status `closed`).

**Admin (`stores.html`):** show pagination controls (Prev/Next + page count); add a **Hapus**
button per row (confirm) calling DELETE.

---

## Item 5 — Store category dropdown

**Admin (`stores.html`):** replace free-text category input with a `<select>` populated from the
distinct categories present (via `/api/stores/all`) plus a datalist so new values can be typed.

---

## Item 6 — Rep plan stores include owner/channel

**Middleware (`do_MY_STORES`):** add `owner_name`, `channel`, `category` to the SELECT and mapping,
so the rep dashboard/visit card can show channel if desired.

---

## Item 7 — Promo `bonus` jenis (engine)

**Middleware (`do_ORDER_CALC`):** handle `jen == 'bonus'` as a free-item grant: when conditions
(e.g. `purchase_sku` present) are met, add reward `free_sku`/`bonus_qty` items to the bonus list
(no price change). Treat `bonus` same as bundling's free-item path but without qty-tier threshold
(any qty ≥ 1).

---

## Re-verification / QA

After all fixes: re-run the **3-role subagent traversal** (Super Admin, Depot Admin, e2e) on the
live stack, walk each newly-added interaction, and confirm no regressions. Record results.

## Docs

- `CHANGELOG.md` — log each fix.
- `QA-FINDINGS.md` — move resolved items out of backlog.

---