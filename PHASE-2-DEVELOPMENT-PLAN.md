# WIM Online — Phase 2 Development Plan (Post-Review)

> **Date:** 2026-09-10
> **Audience:** super_admin / head of development · **Status:** APPROVED-PLANNING (design, not yet built)
> **Source:** Consolidated findings of 20 expert reviewers + 3 analytics-QA agents across the
> live app (both batches), the 5 plan critics, and direct product decisions from the user on
> **delivery** and **payment semantics**.
> **Guiding rule:** every item is additive & reversible; nothing erases existing flows. Build
> order prioritized by value/risk.

---

## 0. Payment & delivery model — DESIGN DECISIONS (from user)

These two clarifications change how delivery + payment are modeled. Read them first — they
drive P1–P3 below.

### 0.1 What "cash" and "kredit" mean at checkout (NOT the payment form)
At checkout the merchant chooses **when** payment is collected, **not** how it is physically paid:

| Checkout option | Meaning | Settlement |
|---|---|---|
| **Cash** | Pay **on delivery** (COD-style) — payment collected when goods arrive | Collected at/before delivery → order becomes `paid` |
| **Kredit** | **Pay later / menunggu pelunasan** — goods delivered on credit; customer settles within credit terms | After delivery → order becomes **`menunggu_pelunasan`** (awaiting settlement) → tracks as an open receivable → `paid` on settlement |

- So `payment_method` on the order is really a **settlement-type / payment term**, not a
  tender type. We keep the column name for back-compat but the **semantics** are: it selects
  the receivable lifecycle, not the instrument.
- A real cash-vs-card "tender" split is NOT modelled now (no need).

### 0.2 Delivery status (current vs future Fleetbase)
- **Now (no Fleetbase):** printing the **Surat Jalan + Invoice** by the depo admin is the
  **proof of dispatch/fulfillment** — it moves the order from `picked/packed` to **`delivered`**
  (the depot has handed it to the route and invoiced it).
- **Future (Fleetbase integration):** delivery gets its **own status/object** with in-transit
  tracking (packed → shipped → in_transit → delivered) driven by Fleetbase; the WIM side
  mirrors it. This is staged behind the Fleetbase sync milestone.

---

## 1. Phase-2 scope overview

| Area | Items | Priority |
|---|---|---|
| A. Order lifecycle + delivery | Order statuses, Surat Jalan print = delivered, invoice, future Fleetbase status | 🔴 P1 |
| B. Payment & receivables (AR) | Settlement-type lifecycle, `menunggu_pelunasan`, AR aging close, credit-limit enforcement | 🔴 P1 |
| C. Security / RBAC / HTTPS | Server-side role+depot/region scope, HTTPS+TLS, cookie hardening, PII masking | 🔴 P1 |
| D. Field resilience | Offline queue + idempotency, retry/timeouts, photo compression | 🔴 P1 |
| E. Performance & storage | Photo→object storage, thumbnails, pagination, gzip, index tuning | 🟠 P2 |
| F. Reporting & UX | Server XLSX/PDF, AOV/repeat/leaderboard/trend, period presets, per-store drilldown, localization, onboarding | 🟠 P2 |
| G. Data-model completeness | SKU barcode + store QR, customer address/phone on order, order_items canonicalization, dedup constraints | 🟡 P3 |
| H. Docs & processes | Migration scripts, QA gates per milestone | 🟡 P3 |

---

## 2. A — Order lifecycle + Delivery

### A1. Order status state machine (extend current)
Today orders sit `pending` forever. Define explicit lifecycle using the existing
`wim_order_status_log` (append-only, idempotent per transition):

```
pending → packed → shipped(by depot print) → delivered
                                   ↘ menunggu_pelunasan (if kredit) → paid
                                   ↘ delivered+cash → paid (COD collection)
          ↘ cancelled (with reason, before packing)
```
- **Now:** `packed` and `delivered` are set by the **depo admin print action** (A2), not by a
  driver. There is no real `shipped/in_transit` driver step yet.
- Guard: only forward transitions allowed; replay of the same status returns OK (idempotent),
  per the earlier security critic.

### A2. Surat Jalan + Invoice print → auto-mark delivered
- Depo admin opens an order (or a day's batch), presses **🖨️ Print Surat Jalan** and
  **🖨️ Print Invoice**.
- **When both are printed, the order status becomes `delivered`** (server-side, audited, once).
  Print is server-generated PDF (not `window.print()`), numberable:
  - `surat_jalan_no` = `SJ-<date>-<batch/order>` (deterministic, dedup).
  - `invoice_no` already exists from Phase-1 (`INV-<date>-<order_id>`).
- Tables: `wim_delivery_note` + `wim_delivery_note_orders` (surat jalan header + order set);
  `wim_orders.delivery_note_id`, `wim_orders.delivered_at`, `wim_orders.invoice_no` (or link
  to `wim_invoice`).
- Reversible: new tables/columns only; `do_ORDER_STATUS_POST` extended with guarded transitions.

### A3. Vehicle / driver (deferred, Fleetbase)
- Do **not** build `wim_vehicle`/`wim_driver` UI now. When Fleetbase sync lands, delivery gets
  its own status object and WIM mirrors `packed/shipped/in_transit/delivered`.
- Staged plan: add `wim_delivery` status columns now (nullable), populate driver/vehicle only
  after Fleetbase integration.

---

## 3. B — Payment & Receivables (AR) closure

### B1. Settlement lifecycle per order
- **Cash (COD):** after `delivered`, order is `payment_pending` (collect on arrival) →
  admin/driver records collection → `paid`.
- **Kredit:** after `delivered`, order → **`menunggu_pelunasan`** (awaiting settlement) →
  records as **open receivable** with a due date → recorded settlement → `paid`.
- Implementation: extend `wim_orders` with `payment_status` (`pending_unpaid` | `cod_pending` |
  `menunggu_pelunasan` | `paid`), `due_date`, `paid_at`, `collected_by`. Keep the existing
  `payment_method` column for data back-compat; add a derived settlement-type label.

### B2. Payment recording UI (`payments.html` / collect button)
- On an order in `delivered`/`menunggu_pelunasan`, admin records a payment: amount, method
  (cash/transfer), date, collector → writes `wim_payment` (created Phase-1) linked by
  `invoice_id` + `store_id`; updates `wim_invoice.status` and `wim_orders.payment_status`.
- Partial payments allowed (multi-`wim_payment` rows); invoice `status` reflects balance
  (`unpaid`/`partial`/`paid`).

### B3. AR aging + per-customer balance (close the loop)
- AR aging (d30/d60/d90) already built in Phase-1 invoices; **extend** so it includes
  `menunggu_pelunasan` orders even before an invoice exists.
- Add a **per-store receivable screen** showing open `menunggu_pelunasan` + overdue + balance.
- **Credit-limit enforcement:** when a store's open balance + new order total would exceed
  `wim_stores.credit_limit` (Phase-1 column), block the order or require `super_admin`
  override (configurable).

### B4. Checkout wording (match user intent)
- Change the checkout toggle from "Cash/Kredit" to clearer labels:
  `Bajar Tenga (COD)` and `Kredit (Bajar Kiu / menunggu pelunasan)` — so reps understand it's
  **when** they get paid, not the tender.

---

## 4. C — Security, RBAC, HTTPS

### C1. Server-side RBAC (central, enforced at every endpoint)
- Add `_require_admin_scope(user, roles, scope_kind)` used by **every** `/api/admin/*` +
  `/api/analytics/*` read: super_admin (all), regional_manager (region), depo_admin (depot).
- Inject `WHERE` scope into queries (visits, orders, attendance, stores, positions/all,
  today-plan, route-map, depots, analytics, filter-options).
- Fix `regional_manager` + `head_of_sales` missing from `ADMIN_ROLES` so they can log in and
  be scoped.
- **Default-deny** in the router: any unrecognized admin path → 403, not passthrough.
- Role-permission matrix documented; menu hiding is only cosmetic on top of real 403s.

### C2. PII masking
- Never return `NIK`/`NPWP` raw in list/export. Mask (`***.***.xxx-xxx`) except a dedicated
  detail endpoint gated to super_admin + audit log.
- Restrict `positions/all` (live GPS) to need-to-know roles; depot admin sees last-position
  of its own reps only (no full movement history).

### C3. HTTPS / TLS + cookie hardening (infra)
- Terminate TLS (NPMplus/HAProxy) in front of sales + admin; Force HTTPS + HSTS.
- Cookies: add `Secure`; consider `__Host-` prefix. Move admin token out of `localStorage`
  (or mitigate with CSP + stale-token timeout). Shorter admin session + idle timeout.
- Add Content-Security-Policy header on admin pages to blunt stored-XSS.

---

## 5. D — Field resilience (offline)

### D1. Outbox / offline queue
- Reuse existing `wim_sync_queue` (NOT a new table). Client persists pending check-in, order,
  stock, absensi to IndexedDB/localStorage with a **client_request_id** (UUID per logical
  action, stable across retries).
- On reconnect: replay; server upserts on `client_request_id` (`ON CONFLICT DO NOTHING` +
  return existing) → **idempotent, no double orders/check-ins**.
- Add `offline_uuid` UNIQUE to `wim_orders`, `wim_visits`, `wim_attendance` for the conflict key.

### D2. UX affordance
- Persistent sync badge (pending count) in the field app header; banner "Disimpan lokal — akan
  kirim saat online"; a queue list; auto-retry 2× with backoff; explicit AbortController
  timeouts on all fetches.

### D3. Photo handling on weak networks
- Compress/resize client-side before upload (already done in absensi; extend to visit photos).
- Make photos not block checkout on flaky networks (queue them; mark visit pending-photo).

---

## 6. E — Performance & storage

### E1. Photos out of Postgres
- Store photo blobs on disk/object storage; DB keeps path + small thumbnail (≤320px, q60).
- List/gallery returns **metadata-only** by default; full image fetched on demand.
- Cap upload size (e.g. 800px, jpg q75–80, strip EXIF).

### E2. Pagination + compression
- Mandatory `?page&pageSize` on stores, visits, orders, gallery (honored, not ignored).
- Enable gzip on middleware + admin (nginx `gzip on`), ETag/Last-Modified, cache headers on
  stable data.

### E3. Indexes + query tuning
- Add indexes: `wim_visits(user_id, checkin_at)`, `wim_visits(checkin_at)`, `wim_visits(place_uuid)`,
  `wim_orders(user_id, created_at)`, `wim_stores(region_id)`.
- Replace `DATE(col)=x` range patterns with `col >= x AND col < x+1` so indexes are used
  (also fixes `/api/admin/dashboard` ~904ms).

---

## 7. F — Reporting & UX

### F1. Server-side XLSX/PDF export + tax invoice
- Shared export module (CSV today, then XLSX/PDF) reusing the same rows; **golden-file** tests
  so the shared module never regresses the already-fixed CSV bug.
- Real **tax invoice** (number, fiscal header, tax) replacing the "not a tax invoice" coupon;
  bulk invoice print; delivery note PDF (ties to A2).

### F2. Director-level analytics (extend `analytics/orders` → new)
- AOV (global/per-rep/per-depot), repeat-order-rate, top/bottom stores, sales leaderboard
  (omzet/orders/kunjungan/EC), order trend time-series (day/week).
- Persistent date/period presets: Hari Ini / Kemarin / Sapta Ini / Bulan Ini / 30 Hari on every
  report + dashboard; fix dashboard that's hard-locked to today.

### F3. UX polish
- Fix stores-list blank-on-load (ensure `loadStores()` runs on init reliably).
- Localization sweep (remaining `Activate`, `PHONE`, `CLOCK IN`, depot "Management").
- First-run tour (2–3 steps), friendly empty states, confirm on destructive actions
  (reset absen), touch targets ≥44px, remove `user-scalable=no`, searchable password toggle +
  "Lupa Password".

---

## 8. G — Data-model completeness

- **Barcode** column on `wim_products` (Phase-1 added, no hook) → add SKU barcode scan in
  order entry + **store QR** check-in scan + scanning audit log.
- **Store QR / customer QR** for fast check-in.
- **Order carries delivery context:** store delivery address, customer phone, requested
  delivery date (Phase-1 column) surfaced on order.
- **Canonical order_items:** reconcile `wim_order_items` (stale stub) vs `wim_orders.items`
  JSONB — pick **one source** (recommend normalizing to `wim_order_items`) so totals never
  diverge; stop dual-write.
- **Dedup constraints:** unique email on users, unique `kode_depo`, dedupe "Carla Rep"
  duplicates; fix `/api/stores/all` `type` column bug + reported SQL column mismatches.

---

## 9. H — Docs & QA gates per milestone

| Milestone | Contents | Gate (must pass before next) |
|---|---|---|
| **PB1** | C (RBAC+HTTPS+PII) — highest risk, do first | Full role×endpoint matrix, zero regressions for super_admin/depo_admin; HTTPS reachable; PII masked |
| **PB2** | A (order lifecycle + Surat Jalan/invoice print = delivered) + B (settlement types, `menunggu_pelunasan`, AR close, credit limit) | Full pending→packed→delivered walkthrough; cash=kod→paid, kredit→menunggu_pelunasan→paid; idempotent status log |
| **PB3** | D (offline queue + idempotency + photo-on-weak) | Queue flush offline→online creates exactly 1 order (no dupe); badge UX |
| **PB4** | E (photo storage, pagination, gzip) | Gallery metadata-only; page 2 offsets correct; payload sizes drop |
| **PB5** | F (server export, director reports, period presets, UX) | Golden CSV/PDF per report; AOV/repeat/leaderboard correct vs SQL; presets work |
| **PB6** | G (barcode/QR, order context, order_items reconcile, dedup) | Scan check-in/order works; totals match across all pages |

Each milestone: 3 expert verification subagents per feature (per user's standing QA rule);
iterative repair loop on bad feedback.

---

## 10. Delivery / payment status matrix (summary)

| State | Meaning | Set by |
|---|---|---|
| `pending` | Order placed | Rep checkout |
| `packed` | Loaded/picked at depot | Depo admin (or auto when Surat Jalan drafted) |
| `delivered` | Surat Jalan **+ Invoice printed** (now) / Fleetbase delivered (future) | Depo admin print / Fleetbase sync |
| `cod_pending` | Delivered cash/COD, awaiting collection | Auto on delivered+cash |
| `menunggu_pelunasan` | Delivered on kredit, awaiting settlement | Auto on delivered+kredit |
| `paid` | Settled | Payment recorded |

> Future Fleetbase: a real `delivery` object carries `packed → shipped → in_transit →
> delivered` and WIM mirrors it; driver/vehicle data lives there, not duplicated in WIM now.