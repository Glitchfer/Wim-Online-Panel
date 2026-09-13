# WIM Online — Post-Review Implementation Plan (CONFIRMED)

> **Date:** 2026-09-10 · **Status: CONFIRMED** (revised after 5 expert critics)
> Earlier draft reviewed by 5 experts: scope/scoping, data-model, security/RBAC, UX/IA,
> release-effort. Their downsides are folded in below.
> **Guiding rule (user):** every new table/page/feature is **ADDITIVE and REVERSIBLE**
> (no destructive migration, no edits to existing working flows). To be implemented,
> deployed, and QA'd with 3 subagents each, so the user can test tomorrow.

---

## 1. What the critics converged on

- **Keep (additive, low risk):** Invoice/Receivables (P2 — WITHOUT tax/margin, one
  `wim_invoice` table), Stock on-hand (P4), Store enrichment (P5 — **reduced scope**:
  only columns that are actually used; skip import/dedup for now).
- **Keep with care:** Region & Depo management (P1) — decouple the "region CRUD" from the
  "regional_manager RBAC" (the RBAC part is deferred). Pages must not fragment the admin IA.
- **Defer (not built now):** full Delivery/truck-load builder (P3 — depends on order
  lifecycle + higher risk), offline queue, server-side XLSX/PDF migration, moving photo
  blobs out of DB, whole-org RBAC rework (finance scoping). These are staged after the pilot.

### Data-model ground truths (from data critic — avoids re-adding what exists)
- `wim_order_items` normalized table **already exists** (alongside `items JSONB`).
- `wim_stores` **already has** province/city/kelurahan/kecamatan/kode_pos/npwp/region_id.
- `wim_sync_queue` **already exists**.
- → We do NOT re-create these. We add only the truly-missing, nullable, additive columns.

## 2. CONFIRMED TO IMPLEMENT (this session, reversible)

### A. Bug fixes (small, verified-needed) — M1
1. `orders.html` CSV column misalignment (stray `offRouteType` shifts 5 columns).
2. Analytics gallery CSV/header mismatch.
3. Attendance duration parser: accept `"20.18"` (id-ID dot separator) not only `":"`.
4. (`done`) packing-list/order-stock grouped by SKU — already committed.
5. Dedupe sales filter dropdown (defer — data duplication, not UI).

### B. Invoice & Receivables — P2 (additive)
- New table `wim_invoice` (+ `wim_payment`) — one taxonomy, nullable, FKs to `wim_orders`.
- `invoices.html` admin page + `/api/admin/invoices` + AR-aging buckets (simple, no tax/margin).
- **Reversible:** new tables only; existing order flow untouched.

### C. Stock on-hand — P4 (additive)
- New table `wim_stock_balance` (product, depot, qty, updated_at, changed_by, source).
- `stock.html` admin page + `/api/admin/stock-balance` (view + adjustment with audit).
- **Reversible:** new table only.

### D. Store enrichment — P5 reduced (additive)
- `ALTER TABLE wim_stores ADD COLUMN IF NOT EXISTS assigned_salesperson_id INT`,
  `ADD COLUMN IF NOT EXISTS credit_limit DECIMAL(15,2) DEFAULT 0`, missing `region_id` FK.
- Extend `stores.html` form for these fields only.
- **Reversible:** nullable new columns only.

### E. Order/product additive nullable columns (from data critic)
- `wim_orders.requested_delivery_date DATE` (nullable).
- `wim_products.barcode VARCHAR` (nullable).
- No default/migration risk.

## 3. DEFERRED (documented, not built) — M5
- Delivery/truck-load builder + `wim_delivery_note`/`wim_vehicle`.
- Offline queue + replay + rep sync badge.
- Server-side XLSX/PDF export engine.
- Photo blobs → external file/object storage.
- Uniform server-side RBAC with finance-scope enforcement.
- Region API + regional_manager scoping (RBAC part of P1).

## 4. Testing requirement (user)
After implementing B/C/D/E + A, spin up **3 expert subagents per new feature** to verify it
works as intended. If feedback is bad → iterative repair loops until verdicts are good.

## 5. Milestone/effort (from release critic)
M1 (bugfix, S) → M2 (Invoice, additive) → M3 (Stock + Regions) → M4 (Store enrich) →
M5 (deferred infra). Each gated by its own tests; high-risk areas deferred to M5.

---

## 6. Critic-hardening (post-5-critic review) — folded into the build

5 expert critics (scope/schema/security/UX/release) reviewed the draft. Consolidated
verdicts and how they changed the implementation:

### 6.1 Scope (critic-1): cut to 2 additive pages + clean up, defer the rest
- HEALTH 3/5, "over-scoped for a ~10-user pilot". **Kept:** Invoice/Receivables (P2,
  simple, no tax/margin), Stock on-hand (P4). **Deferred** (documented, not built):
  Region/Depo CRUD, Delivery/Shipping + vehicle, Store full CRUD, offline queue, barcode
  scan, server-side XLSX/PDF, photo-blob migration, whole-org RBAC.
- **Bug fixes (M1) were pulled ahead as an independent hotfix** so they aren't blocked
  by feature builds — done.

### 6.2 Data model (critic-2): ground-truth corrections applied
- `wim_order_items` **already exists** (besides `items` JSONB); `wim_stores` **already has**
  province/city/kecamatan/kelurahan/kode_pos/npwp/region_id; `wim_sync_queue` **already
  exists** → we did NOT re-add them.
- Store enrichment reduced to **only** `assigned_salesperson_id` + `credit_limit`
  (everything else already present).
- Invoice uses **`order_id INT UNIQUE`** (consistent with existing INT FKs), deterministic
  `invoice_no = INV-<date>-<order_id>`, app-level dedup. `wim_payment` gains `store_id`
  (per-customer AR aging), `external_ref`, `CHECK(amount>0)`, collector.
- Stock on-hand is a **separate balance table (empty, opening-stock only)** — NOT seeded
  from `wim_stock_check` (that's store-shelf stock, not warehouse on-hand).
- Deferred offline queue → reuse existing `wim_sync_queue` (not a new table).

### 6.3 Security (critic-3): finance data gated, PII handled
- Invoice/AR is admin-role gated and NOT on the shared dashboard; `invoices.html` is a
  standalone page. Full per-role finance scoping is **deferred** (post-pilot) per the
  release critic, but the surface stays off the general dashboard.
- Personal data (NPWP/NIK) is **not** added/expanded; the store form only adds
  `assigned_salesperson` + `credit_limit`, no new PII fields. Masking + full RBAC = deferred.

### 6.4 UX / IA (critic-4): additive pages kept lean
- We did **not** add 5 flat nav links. Only 2 additive pages (Invois, Stok) were added as
  distinct nav entries; the remainder of the admin nav is untouched. A full IA
  regrouping (OPERASI/KEUANGAN/GUDANG/MASTER) is deferred to reduce churn this session.
- Bug fixes have precise user-visible verification (see §5.1 / QA gates above).

### 6.5 Release (critic-5): milestone risk gating
- High-risk rebuilds (server RBAC, offline queue replay, `payment_status` ON orders,
  barcode scan hook, shared server-export module) are **REJECTED for the pilot / deferred**
  so the working order flow is never broken.
- `wim_orders.requested_delivery_date` + `wim_products.barcode` nullable columns were added
  (low risk) but no scan/flow hook.

### 6.6 Implementation status (this session)
- **Migration applied live** (`deploy/db/init/06-post-review.sql` + refinement): `wim_invoice`,
  `wim_payment`, `wim_stock_balance` tables; `wim_stores.assigned_salesperson_id` +
  `credit_limit`; `wim_orders.requested_delivery_date`; `wim_products.barcode`; dedup/unique
  indexes; grants to `wim_app`.
- **Bug fixes done:** orders CSV misalignment, analytics gallery CSV header, attendance
  duration `.`/`:` parse, packing/order-stock SKU-grouping.
- **New pages:** `invoices.html`, `stock.html` (+ middleware/admin endpoints).
- **Store form:** added "Sales Ditugaskan" + "Limit Kredit".
- **Pending:** live deploy of code (files + service restart) — requires approval.
- **Next:** 3 expert verification subagents per new feature, iterate as needed.