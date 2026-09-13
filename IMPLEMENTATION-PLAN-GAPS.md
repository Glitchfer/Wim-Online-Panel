# WIM Online — Implementation Plan: Closing the Legacy Feature Gaps

> **Plan date:** 2026-09-10
> **Scope:** Implement the missing features (from FEATURE-GAP-AUDIT.md + USER-FLOWS-GAPS.md)
> across the **sales app** (frontend/ + middleware serve.py) and the **admin panel**
> (admin/*.html + admin-server.py).
> **Grounded against code:** every "current state" claim below was verified against the repo,
> not assumed. Column/table existence checked in `deploy/db/init/01-schema.sql` and live DB.
> **Legend:** S = Schema, MW = Middleware (serve.py), AS = Admin server (admin-server.py),
> AD = Admin page (admin/*.html), SO = Sales order front (order.html/order-cart.js), VC = visit-card.html

---

## Phase 0 — Baseline facts (verified)

| Fact | Value | Where |
|---|---|---|
| `wim_orders.payment_method` | EXISTS (default 'cod') | schema — but **not written** by `do_ORDER_POST` |
| `wim_orders.off_route_reason` | EXISTS | **not written** by order flow |
| `wim_orders.sales_channel` | EXISTS (default 'app') | written = `salesChannel` from client |
| Promo tables | `wim_promo` + conditions + rewards + assignments | **exist**, engine reads them; no admin UI |
| Order status lifecycle | `pending→verified→processed→shipped→delivered` + `cancelled` | admin PATCH exists |
| Admin pages | dashboard, team, visits, orders, attendance, users, products, depots, today-plan, route-map, index | no stores/promos/settings/import pages |
| /api/admin/filter-options | built (2026-09-10) | dropdowns work |

---

## Phase 1 — Payment Method (Cash / Credit)  · HIGH priority · tiny

**Goal:** rep picks payment method at checkout; stored + visible on confirmation/QR.

- **SO (order-cart.js):** add `paymentMethod: 'cash'` to cart; expose on checkout.
- **SO (order.html):** add a payment selector [Cash (Tunai) | Kredit (CR)] at checkout (default Cash).
- **MW (serve.py `do_ORDER_POST`):** read `data.paymentMethod`; write it into the INSERT
  (`payment_method` column). Validate `in ('cash','credit','cod')`.
- **MW (`do_ORDER_GET` / `do_ORDER_PUBLIC`):** include `payment_method` in returned payload.
- **SO (invoice.html):** show "Pembayaran: Tunai/Kredit" on the confirmation (QR page).
- **Admin (orders.html):** show payment method column.
- **Test:** create order with cash + credit; confirm stored + on public invoice.

---

## Phase 2 — Promo info in order/report exports  · HIGH · closes "promo tidak tampil di report"

**Goal:** surfacing `promo_name`, `promo_ref`, `is_bonus`, `promo_type` on every order line and
report export — non-negotiable #9/#12.

- **MW (`do_ORDER_GET`):** already returns `items` JSON (with `is_bonus`/`promoName`). Add a
  derived `promoSummary` (total_discount, bonus_value, promos_applied) to each order.
- **MW (`do_ORDER_PUBLIC`):** same `promoSummary`.
- **AD (orders.html):** add a **Promo** column (list promo names) + include promo columns in CSV.
- **SO (invoice.html):** already shows bonus lines (+Gratiis); add a **promo/gratis summary block**
  (total bonus value, promos applied) for the buyer.
- **MW (`do_REPORT`):** include promo/bonus breakdown per order in the sales report.
- **Test:** create order with a bundling promo → verify promo info appears in /api/orders,
  public invoice, admin orders page, and report CSV.

---

## Phase 3 — Visit card: Belum / Sudah Dikunjungi tabs (mobile UDR)

**Goal:** parity with KlikOrder/GooVi visit-card 2-tab grouping.

- **SO (visit-card.html):** add two top tabs.
  - **Belum Dikunjungi** = today's plans with status `pending` / not-yet-visited.
  - **Sudah Dikunjungi** = store status `visited`/`checked` (completed today).
  - Keep existing in-route/luar-rute filter within each tab.
- **MW (`GET /api/stores`):** ensure returns a status field per store today (already returns
  route plan with `status`); if missing, add `status` (pending/visited) to the store list.
- **Test:** after completing a visit, store moves from Belum → Sudah automatically on refresh.

---

## Phase 4 — Out-of-route order transaction type  · MD

**Goal:** when ordering a luar-rute store, sales choose a transaction type that becomes the
"status" on the reporting.

- **SO (visit-card / order.html):** when store is `luar_rute`, show a **Jenis Transaksi (Luar Rute)**
  dropdown at checkout: e.g. `WA`, `Telepon`, `Admin Bantu`, `Lainnya` (configurable).
- **MW (`do_ORDER_POST`):** write the chosen value to `off_route_reason` (already column) along
  with `source='luar_rute'`. Validate the value.
- **MW (`do_ORDER_GET` / `do_ORDER_PUBLIC`):** expose `offRouteType`/`off_route_reason`.
- **AD (orders.html):** show the out-of-route type as its own column/report filter.
- **Test:** create a luar-rute order with type `WA` → report shows `off_route_type=WA`.

---

## Phase 5 — Order by customer / admin (QR entry)  · [S + factory]

**Goal:** support the 3 order modes (sales / customer-QR / admin-QR-from-list).

- **MW (`do_ORDER_POST`):** accept `order_channel` in (`app`, `customer`, `admin`, `delivery`).
  - For **admin**: allow `store_uuid` with NO open check-in (skip the checkin verification).
  - For **customer** (QR): validate a public `scan_token`/store_uuid; create order; `sales_channel='customer'`.
- **AD (admin orders):** add **"+ Tambah Order (Admin)"** → pick store (search) → cart → create
  with `order_channel=admin` (no check-in required).
- **SO (customer QR):** a lite public order page for the QR — pick products, choose the 
  + method, checkout without login (via a signed scan token). (Reuses order-cart.js.)
- **Test:** admin order without checkin succeeds; store-scanned QR order succeeds.

> **Note:** Customer self-order (no-login) carries auth/abuse considerations — we'll gate by
> store QR barcode + a lightweight token. Keep it simple in V2; admin mode first.

---

## Phase 6 — Master imports (products / schedules / promos) + self-service  · [S + admin]

**Goal:** close the "submit form to vendor" dependency — WIM can import/update master data itself.

- **MW — import endpoints (admin-key, role-gated):**
  - `POST /api/admin/products/import` (CSV: sku,name,brand,category,price,unit,qty_per_unit,...)
  - `POST /api/admin/visit-plans/import` (CSV: sales_email,store_uuid/name,date,cycle,priority)
  - `POST /api/admin/promos/import` (CSV: jenis,sku/min_qty,bonus_sku/qty,periode,depot,status)
- **Every import:** parse CSV → validate per-row → return preview (valid/errors) → confirm →
  insert with a log. Report failures back to the admin.
- **AD (import.html):** upload + preview + confirm UI (a shared admin page).

---

## Phase 7 — Promo admin UI (create/manage)  · [S + admin]

**Goal:** self-service promo creation backing existing promo engine.

- **AD (promos.html, NEW):**
  - List promos (nama, jenis, status, periode).
  - Create/Edit: nama, jenis (bonus|bundling|strata|diskon), status, priority, stackable
    (multi-apply), periode; condition lines (SKU/min_qty/pct), reward lines (bonus SKU+qty/
    discount), and **depot assignments** (`wim_promo_assignments`) so promos appear per-depot.
  - Activate/deactivate toggle.
- **AD (admin-server.py):** add `/api/admin/promos` CRUD proxy → middleware `do_PROMOS_*`.
- **MW:** add `GET/POST/PATCH/DELETE /api/admin/promos[ /:id ]` for CRUD over wim_promo +
  conditions/rewards/assignments (transactions).
- **SO (order.html / cart):** promo visibility already exists (badge + auto-calc). Keep.
- **Test:** create a depo-scoped bundling promo → shows in that depo's reps' catalog.

---

## Phase 8 — Stores (customer) admin + depot/region CRUD  [S + admin]

**Goal:** full master-data handle.

- **AD (stores.html, NEW):** list stores (filter by depot/region/channel), create, edit
  (NOO fields), deactivate (soft delete). Built on `/api/admin/stores` GET + `POST /api/admin/stores`
  (wire MW `do_STORE_POST`) + `PATCH /api/admin/stores/:uuid`.
- **AD (depots.html)** — extend existing read page to **Create/Edit/Delete/Import**; add region
  dropdown (depots already have region_id).
- **AD (regions.html — NEW):** list/add/edit regions + assign depots to region (reuse
  `/api/admin/regions` which is aspirone in mapping; add MW CRUD).
- **Import store master** (`POST /api/admin/stores/import`).

---

## Phase 9 — Server-side export (CSV/XLSX) on reports [MW + AD]

**Goal:** richer exports (currently client-side CSV from rendered rows).

- **MW:** `/api/admin/visits/export`, `/api/admin/orders/export` (CSV, respects filters),
  `/api/admin/attendance/export`, `/api/admin/stock/export`.
- **AD:** replace/augment the client CSV button with a server export link (`?export=csv`) so
  large datasets stream server-side.
- **Keep client CSV** as a lightweight fallback.

---

## Phase 10 — ECON analytics + gallery + closing depo/gudang  [MW + AD]

**Goal:** ECON hub + visualisation parity.

- **AD (dashboard.html):** add **EC (Effective Call)** card: numerator visits-with-order,
  denominator visits-today → %.
- **AD (visits.html)** — add **Rekap Kunjungan** and **Galeri Foto** (photos from visits).
- **AD (route-map.html):** add toggle order vs non-order rendering (stored source/status).
- **AD (NEW closing.html):** **Closing Depo** and **Closing Gudang** flows.
- **MW:** EC aggregate endpoint (`/api/admin/ec`), photo gallery,closing endpoints.

---

## 11. Settings / session management [MW + AD]

- **AD (settings.html — NEW):**
  - **Sessions/Akun** (list active, reset failed-login).
  - **Brand per Depo** (depot→brand access table, edit).
  - **Customer Reassign** (CSV import: old sales → new sales).
- **MW:** `/api/admin/sessions` (list/reset), `/api/admin/depots/brands`, `/api/admin/stores/reassign`.

---

## Suggested build order (dependencies first)

| Phase | Feature | Depends on | Effort |
|---|---|---|---|
| 1 | Payment method | — | S (tiny) |
| 2 | Promo in report/export | — | S-M |
| 3 | Visit tabs | — | S-M |
| 4 | Out-of-route type | 1 | S |
| 5 | Order by admin/customer QR | 1,4 | M |
| 6 | Master imports (product/schedule/promo) | — | M-L |
| 7 | Promo admin UI | 6 (partly) | M |
| 8 | Store / depot / region admin | — | M |
| 9 | Server-side exports | 2 | M |
| 10 | ECON + gallery + closing | — | L |
| 11 | Settings / session | — | M |

---

## Cross-cutting rules (follow for every feature)

1. **Server-side validation only** — never trust frontend for totals/geofence/prices (AGENTS.md #3).
2. **Order > 0 requires verified check-in** unless channel is admin/customer (which store that).
3. **Exports include promo data** (promo_name, is_bonus, promo_ref) — non-racable #9/#12.
4. **Bahasa-friendly** error messages (AGENTS.md #5).
5. **Region/depot filters** applied server-side (already built in Phase-2 patterns).
6. **After each feature** run the 3-subagent QA loop (sales / depo admin / super admin).

---

## Related docs

- `FEATURE-GAP-AUDIT.md` — quantified matrix + meeting-note addendum
- `USER-FLOWS-GAPS.md` — user-flow charts for the missing flows (reference for each phase)

---