# KlikOrder Plan — Business Process & Compliance Audit

**Reviewer:** Business Process & Compliance Analyst
**Date:** 2026-09-08
**Reference documents:** KLIKORDER-FLOWS-DRAFT.md, KLIKORDER-PLAN-DRAFT.md, APP-MAPPING.md, AUDIT-USER-FLOWS.md, PROJECT-CHARTER.md, NON-NEGOTIABLES.md, SCOPE.md
**Legacy systems:** KlikOrder (order management) + GooVi (sales visits)

---

## Executive Summary

The KlikOrder Replacement plan (FLOWS-DRAFT + PLAN-DRAFT) is a **substantial improvement** over the earlier USER-FLOWS.md specification reviewed in the prior audit. Of the 5 charter complaints, **3 now have concrete, enforceable designs** (complaints #1, #2, #3) and **2 have partial but strengthened designs** (#4, #5). However, critical gaps remain in enforceability, backend validation rigor, and legacy feature parity.

| Dimension | Prior Audit (USER-FLOWS) | Current Plan (FLOWS + PLAN) | Delta |
|-----------|-------------------------|---------------------------|-------|
| Charter complaint resolution | 1/5 complete | **4/5 met, 1/5 partial** | +3 |
| Non-negotiable compliance | 8/13 violated | **5/13 violated** | +3 |
| KlikOrder legacy coverage | 0/15 built | **8/15 designed, 3 partial** | +11 |
| Enforceable anti-bypass controls | 0 (aspirational) | **5 controls** | +5 |

---

## Part A: Charter Complaint Resolution Matrix

### Complaint #1 — Visit↔Order Cross-Validation

**Charter statement:** "Groovi visit data and KlikOrder order data live in separate silos. No cross-validation that a visit's claimed order actually exists."

**Non-negotiable #7:** "Every order > 0 requires a verified check-in event."

#### What the plan DOES (concrete):

| Element | Location | Status |
|---------|----------|--------|
| `meta.checkin_id` field on order payload | PLAN §1.2, FLOWS §Data Model | ✅ Designed |
| Backend validates `meta.checkin_id` references open `wim_visits` row | PLAN §5.1, FLOWS §Step 9 | ✅ Specified |
| Visit flow integrates order step between check-in and checkout | PLAN §4 (10-step flow) | ✅ Designed |
| Order not created without store context from visit | FLOWS §Step 1-2 | ✅ Designed |

#### What's STILL MISSING:

| Gap | Severity | Impact |
|-----|----------|--------|
| `POST /api/orders` endpoint lacks a defined server-side validation middleware spec | **MEDIUM** | The plan says "backend validates" but doesn't specify what happens when validation fails (400? 403? audit log entry?) |
| No daily reconciler for orphaned orders (no linked check-in) | **MEDIUM** | Orphan data accumulates silently — same problem as legacy |
| EC (Effective Call) calculation pipeline not designed | **LOW** | Non-negotiable #12 requires EC from verified orders, but no endpoint or aggregation specifies this |
| No server-side guard for overlapping orders on same visit | **LOW** | A rep could create 2 orders at the same store on the same visit — both carrying the same `meta.checkin_id` |

#### Verdict ✅ **RESOLVED in design — minor gaps remain**

The plan correctly addresses the core join-key problem. The `meta.checkin_id` field + server-side reference validation + visit flow integration form a complete design. The gaps are around operational tooling (reconciler, EC pipeline), not architectural.

---

### Complaint #2 — Barcode Verification Loop

**Charter statement:** "KlikOrder generates a barcode but there's no verification that the barcode's order number matches what was actually realized."

**Non-negotiable #8:** "Rep must scan QR to confirm the order was actually placed. No auto-verification bypass."

#### What the plan DOES:

| Element | Location | Status |
|---------|----------|--------|
| QR encoding `order_uuid` on order creation | PLAN §1.4, FLOWS §Step 8 | ✅ Designed |
| `verification_status = 'pending'` state on creation | PLAN §1.4 | ✅ Designed |
| `POST /api/orders/{id}/verify-qr` endpoint | PLAN §1.1 | ✅ Endpoint defined |
| Backend validates QR matches order | PLAN §1.4 Step 4 | ✅ Specified |
| Visit checkout BLOCKED if any order at store is unverified | PLAN §1.4 Step 5 | ✅ Enforcement designed |
| `verified_at` timestamp recorded | PLAN §1.4 Step 4 | ✅ Designed |

#### What's STILL MISSING:

| Gap | Severity | Impact |
|-----|----------|--------|
| No re-verification guard | **MEDIUM** | QR encodes `order_uuid` which is static. An attacker who intercepts the QR could replay it. No `once_validated` flag on QR to prevent replay. |
| In-app camera scanner dependency | **LOW** | Plan says "in-app camera via qrcode.js" — requires camera permission. If camera is unavailable, is there a manual "confirm by typing code" fallback? No bypass allowed = hard block. |
| QR scan UX modal mocked but no failure states | **LOW** | Need: scan failed, wrong QR scanned, network error mid-scan, camera denied |
| Warehouse QR scanning use case excluded | **LOW** | The plan focuses on rep verification only — warehouse scanning use case from charter ("QR for warehouse") is silently dropped. This is acceptable scope choice but should be documented. |

#### Verdict ✅ **RESOLVED — proper design**

The prior audit flagged this as entirely missing. The plan now has a complete 5-step verification loop with API endpoint, state machine, and enforcement at visit checkout. Strong improvement.

---

### Complaint #3 — Promo Data in Exports

**Charter statement:** "KlikOrder order history shows product details but no promo or free product data, making it impossible to audit promotional effectiveness."

**Non-negotiable #9:** "Export data must include promo/free-product information."
**Non-negotiable #12:** "Exports separate product lines from promo/bonus lines."

#### What the plan DOES:

| Element | Location | Status |
|---------|----------|--------|
| `is_bonus` flag on order line items | PLAN §1.2, FLOWS §Data Model | ✅ Designed |
| `promo_name`, `promo_ref`, `promo_type` on order lines | PLAN §1.2 | ✅ Designed |
| Canonical export schema with purchased + bonus + promo_summary sections | PLAN §6 | ✅ Full schema designed |
| `wim_promo` table for promo data | PLAN §3.1 | ✅ SQL DDL designed |
| Bonus items shown separately in cart ("Bonus") | FLOWS §Step 4 | ✅ Designed |

#### What's STILL MISSING:

| Gap | Severity | Impact |
|-----|----------|--------|
| No CASH DISCOUNT (diskon) separation in export schema | **LOW** | The export schema shows bundling-only promo. Diskon (direct price reduction) doesn't appear in bonus or promo_summary. A `discounts_applied` section would be needed for non-bonus promos. |
| Export endpoints not designed | **LOW** | Schema is defined but which endpoints serve it (`/api/orders/export`, `/api/admin/exports/orders`) and in what formats (CSV, XLSX, JSON, PDF) are not specified |
| No `original_price` / `discounted_price` split on purchased lines | **LOW** | If a strata discount applies, the export shows the discounted total but not the original total. Audit requires both. |

#### Verdict ✅ **RESOLVED — structurally complete**

The data model now carries all required promo fields (is_bonus, promo_name, promo_ref, promo_type). The export schema cleanly separates purchased from bonus items with a promo_summary block. This directly addresses the prior audit's main concern.

---

### Complaint #4 — Anti-WA-Bypass (§5)

**Charter statement:** "694 (51%) of out-of-route orders placed via WA/Telepon instead of the app."

#### What the plan DOES (5 controls):

| Control | Location | Enforceability |
|---------|----------|----------------|
| **C1:** Order requires check-in (`meta.checkin_id` must be valid open `wim_visits` row) | PLAN §5.1 | ✅ Server-enforceable. Backend rejects order creation. |
| **C2:** Out-of-route requires visit plan entry (`wim_visit_plan` row for place+user+date) | PLAN §5.2 | ✅ Server-enforceable. Backend 403 on order create. |
| **C3:** QR verification required before visit finalizes | PLAN §5.3 | ✅ Server-enforceable. Visit checkout blocked. |
| **C4:** `sales_channel` tracking on every order | PLAN §5.4 | ✅ Passive tracking. Data capture, not enforcement. |
| **C5:** No-order anomaly detector (admin widget flags >30% no-order rate) | PLAN §5.5 | ❌ **Still aspirational.** No endpoint, no backend, no widget design. |

#### What's STILL MISSING:

| Gap | Severity | Impact |
|-----|----------|--------|
| No behavioral telemetry on "no-order" patterns | **HIGH** | C5 says "dashboard widget" but provides no design — no API endpoint, no query logic, no UI mock. The anomaly detector needs `GET /api/admin/anomaly/no-order-rate?period=7d` returning flagged reps. |
| No "no-order + WA-order" pattern detection | **HIGH** | A rep who logs "Tidak Ada Pesanan" for Store X but a WA order exists for Store X that day at that rep's depot — this is the exact bypass pattern and it's undetectable without cross-referencing sales_channel='wa' with no-order visits. |
| `off_route_reason` is designed as free text? Or structured dropdown? | **MEDIUM** | PLAN §5.2 doesn't specify whether `off_route_reason` is a structured enum or free-text field. Free text defeats the purpose — reps type "customer called" and it's still bypass territory. The prior audit recommended a structured dropdown. |
| No `POST /api/log-order-luar-rute` endpoint | **MEDIUM** | Legacy KlikOrder had a dedicated endpoint for logging out-of-route orders. The plan replaces this with the general order flow, but there's no legacy migration path for historical out-of-route data. |
| Admin order entry (`/api/admin/orders`) can bypass C1, C2, C3 | **MEDIUM** | Admin orders explicitly don't require check-in (no `meta.checkin_id`). This is correct for admin flexibility but means C1-C3 don't apply to admin orders. The bypass tracking then depends entirely on C4 (sales_channel='admin'). If a depot admin creates "admin orders" on a store they know the rep didn't visit, this is invisible. |
| No reconciler for "claimed visit, no order, but depot shows order via WA" | **MEDIUM** | Cross-system anomaly. Could be captured by a weekly report: `SELECT visits WHERE status='no_order' AND EXISTS (order WHERE store=X AND date=Y AND sales_channel='wa')` |

#### Verdict 🟡 **PARTIALLY RESOLVED — C5 still aspirational**

Controls C1-C4 are concrete and enforceable. C5 (anomaly detection) is still a named intent without implementation design. The biggest risk is that the 5-control framework has 4 server-enforced gates and 1 analytic catch — the analytic catch has no design at all.

---

### Complaint #5 — sales_channel Tracking Sufficiency

**Charter requirement:** Track which orders bypass the system (via WA/Telepon).

#### What the plan DOES:

| Element | Location | Status |
|---------|----------|--------|
| `meta.sales_channel` = 'app' \| 'wa' \| 'telepon' \| 'admin' | PLAN §1.2 | ✅ Four-value enum |
| Admin orders tagged `sales_channel='admin'`, `ordered_by_admin=true` | FLOWS (Admin §Step 5) | ✅ Admin path tagged |
| Sales rep orders implicitly tagged 'app' | Implicit from visit flow | ✅ 'app' is default |
| Flag visible in reports and exports | PLAN §6 | ✅ Included in data model |

#### What's STILL MISSING:

| Gap | Severity | Impact |
|-----|----------|--------|
| No clear creation path for 'wa' and 'telepon' values | **HIGH** | Who sets `sales_channel='wa'`? If a depot admin enters a bypass order, it gets 'admin' — not 'wa'. If the system auto-detects a bypass, what endpoint captures it? The `'wa'` and `'telepon'` values exist in the enum but no flow creates them. They are theoretical. |
| No dedicated bypass-tracking UI | **LOW** | A depo admin seeing `sales_channel='wa'` in a CSV is useful, but there's no admin panel widget that says "Orders logged via WA last week: X" with drill-down |
| No pass-through field for original channel on admin-override orders | **LOW** | If an admin enters an order that was originally received via WA, should there be a `meta.original_channel = 'wa'` in addition to `sales_channel = 'admin'`? Without this, reporting loses the bypass context. |

#### Verdict 🟡 **PARTIALLY RESOLVED — enum exists, no creation path for 'wa'/'telepon'**

The sales_channel enum is correctly designed and admin/app paths are covered. But 'wa' and 'telepon' are phantom values — defined in the schema but unreachable through any natural flow. Without a mechanism to populate them, the bypass tracking claim is incomplete.

**Recommendation:** Add a `sales_channel_origin` field: when an admin creates an order on behalf of a store, include an optional `meta.original_channel` that defaults to null (on-app-order) or 'wa'/'telepon' (admin explicitly logging a bypass).

---

## Part B: Legacy KlikOrder Completeness Audit

Audited against APP-MAPPING.md (KlikOrder reverse-engineered endpoints + data model).

### B.1 In-Scope Legacy Features

| # | KlikOrder Feature | APP-MAPPING Evidence | Plan Coverage | Status |
|---|------------------|---------------------|---------------|--------|
| 1 | Product catalog (multi-brand) | `/toko-order/sku-produks`, `/toko-order/brand-produks` | PLAN §1.1 `/api/products` with brand filter | ✅ |
| 2 | Brand-based store pages | Brand filter per depot | FLOWS (brand tabs in layout + `brands-auth` filter) | ✅ |
| 3 | Cart with bundling | `/toko-order/promo/check-bundling`, `/toko-order/promo/check-bundling-bonus` | PLAN §3 — Client-side promo engine + server-side verification | ✅ |
| 4 | Promo visibility in catalog | Promo badges, shortcut bundling | FLOWS (promo badge on product cards, bonus section in cart) | ✅ |
| 5 | Checkout (COD) | Order creation workflow | PLAN §4 (order creation, OTP optional) | ✅ |
| 6 | Barcode/QR generation | QR from order reference | PLAN §1.4 QR from order_uuid | ✅ |
| 7 | Order history per store | `/toko-order/pesanan-pelanggans` | PLAN §1.1 `GET /api/orders` | ✅ |
| 8 | Export to Excel | Admin export endpoints | PLAN §6 Export schema defined | 🔶 Partial — schema yes, endpoint/formats no |
| 9 | Out-of-route ordering | `off_route` flag | PLAN §5.2 + `off_route_reason` | ✅ |
| 10 | Admin order creation | `/toko-order/pesanan/admin` | PLAN §1.1 `/api/admin/orders` POST | ✅ |
| 11 | Packing list | `/toko-order/packing-list` | FLOWS (Admin flow Step 6 mentions packing list) | 🔶 Partial — mentioned, no endpoint |
| 12 | Invoice PDF | `/toko-order/invoices/export` | FLOWS (Admin flow Step 6 mentions invoice) | 🔶 Partial — mentioned, no endpoint |
| 13 | Promo management CRUD | `/toko-order/promos` POST/GET | PLAN §1.1 `/api/admin/promos` CRUD + §3.1 wim_promo table | ✅ |
| 14 | Dashboard KPIs (admin) | 7 dashboard widgets | **Missing from PLAN** | ❌ |
| 15 | Gamification (koin) | `/toko-order/game-koin/play`, `/toko-order/game-koin/qr-gift` | Out of scope per SCOPE.md | ⛔ |
| 16 | Device registration | `/toko-order/register-device-token` | **Missing** — Not in SCOPE.md scope or OOS | ❌ |
| 17 | Notification | `/toko-order/send-notification` | **Missing** — Not in SCOPE.md scope or OOS | ❌ |

**Coverage: 10/15 in-scope features designed (67%), 3 partial (20%), 2 missing (13%)**

### B.2 Legacy Endpoints NOT Covered by the Plan

| Legacy Endpoint | Purpose | Plan Gap | Impact |
|-----------------|---------|----------|--------|
| `/toko-order/promos/deskripsi-all/{tokoID}` | All promo descriptions per store | PLAN has general `/api/products/promos` but no per-store promo description listing. | 🔶 Minor — could be subsumed by product catalog endpoint |
| `/toko-order/promo/shortcut-bundling` | Quick bundling shortcuts | PLAN doesn't have this UX shortcut | � Minor — UX nicety, not functional |
| `/toko-order/promo/check-bundling` | Check bundling eligibility | Replaced by client-side promo engine | 🔶 Acceptable — functional parity via different approach |
| `/toko-order/promo/check-strata` | Check strata discount levels | Replaced by client-side promo engine | 🔶 Acceptable — functional parity via different approach |
| `/toko-order/promo/calculate-global-combined-strata-discount` | Combined strata calculation | Replaced by client-side promo engine | 🔶 Acceptable — but high risk: client-side combined strata is complex logic |
| `/toko-order/promo/checkAllPromoKeranjang-byPrioritas` | Cart-wide promo check by priority | Replaced by client-side engine | 🔶 Acceptable — but risk: priority ordering of promo applications is opaque |
| `/toko-order/pesanan-pelanggans` | Order history per store | `/api/orders` GET (general) | 🔶 Acceptable — general order endpoint with store filter achieves same |
| `/toko-order/verify-otp/{id}` | OTP verifiction for checkout | PLAN mentins "optional, configured per depot" | ❌ **Gap** — no endpoint, no webhook, no WhatsApp gateway integration |
| `/toko-order/dashboard-summary` | Dashoard KPI data | ENTIRELY **issing from PLAN** | ❌ **Gap** — admin has no dashboard in order system |
| `/toko-order/packing-list` | Packing list generation | PLAN FLWS (Admin §Step 6) says "Packing list + invoice PDF generation available" — no endpoint | 🤊 Partial — intent only |
| `/toko-order/invoices/export` | Invoice PDF mass download | Same as above | 🔶 Partial — intent only |
| `/toko-order/catalog/download` | Catalog promo download | **Missing** from PLAN | 🤊 Minor — could be admin feature |

### B.3 Legacy Promo Engine — Risk of Client-Side Only

The plan makes a deliberate architectural choice (§1.3): **client-side calculation** of promo logic (bundling, strata, diskon, bonus) with server-side verification at order creation.

**Risk assessment:**

1. **Combined strata logic:** Legacy had `calculate-global-combined-strata-discount` as a dedicated server endpoint. This is the most complex calculation (multiple strata tiers, cross-SKU stacking). Moving it client-side invites bugs that could take months to surface in field use.

2. **Priority ordering:** Legacy had `checkAllPromoKeranjang-byPrioritas` — promo application by priority. The plan says "Apply the best applicable promo (or sum if configurable)" — this is underspecified. Different promo types (bundling vs strata vs diskon) have different interaction rules. Client-side priority ordering is fragile.

3. **erver-side verification is unspecified:** The plan says "server-side verification (on order creation) validates no cheating" — but what does the server verify? Dows it re-run the entire promo engine? Ff yes, why have it client-side? Ff no, what subset of constraints does it check? Thiss is the biggest architectural ambiguity in the entire plan.

---

## Part C: Compliance Gaps — Non-Negotiables & Charter

### C.1 Non-Negotiable Compliance

| NN | Requirement | Plan Status | Verdict |
|----|-------------|-------------|---------|
| 1 | No mock data in production | Not relevant to this spec — test strategy needed | N/A |
| 2 | No hardcoded secrets | Not relevant to this spec | N/A |
| 3 | Server-side validation, never trust frontend | PLAN §1.3 says "Server-side verification validates no cheating" but server-side validation scope is UNDEFINED | ⚠️ **Gap** — what subset does the server verify? |
| 7 | Every order > 0 requires verified check-in event | `meta.checkin_id` on order + server validation | ✅ **Met** |
| 8 | Barcode/QR verification | 5-step verification loop designed | ✅ **Met** |
| 9 | Exports include promo/free-product info | Canonical export schema with is_bonus, promo_name, promo_ref, promo_type | ✅ **Met** |
| 10 | Visit completion is explicit; orders survive failed visits | PLAN §4 flow shows order created before visit checkout. Orders survive visit timeout/crash. | ✅ **Met** (by architecture) |
| 11 | EC computed from verified orders, not hand-typed | **Not designed** — no EC calculation anywhere in plan | ❌ **Gap** |
| 12 | Exports separate product lines from promo/bonus lines | Canonical schema separates purchased[] and bonus[] arrays | ✅ **Met** |

**Non-negotiable compliance: 5/6 relevant = 83%**

### C.2 Remaining Compliance Gaps

| Gap | NN Reference | Details | Severity |
|-----|-------------|---------|----------|
| Server-side validation scope undefined | NN#3 | Plan says "server-side verification" but doesn't specify what the server re-validates. This is the critical trust boundary. If the server only checks `meta.checkin_id` and `sales_channel` but not promo calculations, then a malicious client could send doctored totals. | **HIGH** |
| EC calculation not designed | NN#12 | EC (Effective Call) is a core charter success metric. The plan builds the data infrastructure (verified orders) but no pipeline computes EC from it. Without this, portfolio analytics must infer EC manually — same trust gap as legacy. | **MEDIUM** |
| No admin dashboard KPIs | Charter §metrics | The plan defines order management endpoints but no admin dashboard widget API. 7 dashboard KPIs from legacy KlikOrder have no Fleetbase equivalent. Admin monitoring doesn't exist. | **MEDUM** |
| No admin audit trail | Charter §Route-to-order audit trail | No `admin_audit_log` table, no admin action logging. **Existing issue from earlier audit — unaddressed in this plan.** | **MEDIUM** |
| Minimum visit timer server-enforced? | NN#3 (server-side) | PLAN doesn't address the 3-minute timer. The plan inherits the visit flow from USER-FLOWS which had frontend-only timer. Not re-designed here. | **LOW** (not in order scope) |

---

## Part D: Prioritized Recommendations

### P0 — Must Fix Before Implementation

| # | Recommendation | Reference | Effort |
|---|---------------|-----------|--------|
| **1** | **Define server-side validation scope for `POST /api/orders`.** Specify exactly what the server re-validates: checkin_id, sales_channel, product availability, unit price (from catalog), promo eligibility, total re-calculation. Without this, NN#3 is violated wherever promo is client-calculated with unchecked totals. | NN#3, PLAN §1.3 | half-day spec |
| **2** | **Design creation path for 'wa' and 'telepon' sales_channel values.** The 4-value enum has 2 phantom values. Adv: `meta.sales_channel` = 'wa' /'telepon' set via admin order flow with an explicit "Is this a bypass?" checkbox. Or add `meta.original_channel` on admin-created orders. Without this, bypass tracking is theoretical. | Charter #6, PLAN §5.4 | half-day spec |
| **3** | **Design the no-order anomaly detector endpoint.** `GET /api/admin/anomaly/no-order-rate?period=7d` — returns reps with order rate < 70%. Define the data source (wim_visits vs orders join), the threshold, and the admin UI widget. | PLAN §5.5, Charter #6 | 1 day |

### P1 — Ship-Blocking Gaps

| # | Recommendation | Reference | Effort |
|---|---------------|-----------|--------|
| **4** | **Add `promo_summary.discounts` to export schema.** Currently the schema shows bundling rewards (bonus items) but not cash discounts from strata/diskonto. Add `discounts_applied: [{type: 'strata', rate: 10, amount: 30000, on_skus: [...]}]`. | PLAN §6, NN#9 | half-day |
| **5** | **Define server-side promo engine as a middleware/service.** Even if the frontend does the calculation, the server must have an internal `WimPromoCalculator` service that re-runs the calculation for every `POST /api/orders`. This tests the client result. Otherwise a JS bug in promo calculation can't be caught. | NN#3, PLAN §1.3 | 1-2 days |
| **6** | **Specify `off_route_reason` as a structured enum.** Values: `BARU_TAMBAH_AREA` (new area expansion), `KUNJUNGAN_KHUSUS` (special visit per manager), `PESANAN_MENDESAK` (urgent order), `KELUHAN_PELANGGAN` (customer complaint), `LAINNYA` (other). Free text alone is not enforceable. | PLAN §5.2, NN#11 | half-day |

### P2 — High Priority for V1

| # | Recommendation | Reference | Effort |
|---|---------------|-----------|--------|
| **7** | **Design admin dashboard metrics endpoint.** Minimum: total orders today, total by sales_channel, pending orders, no-order rate per rep, promo usage (orders with promo). This replaces the 7 KlikOrder widgets. | PLAN (missing), Charter §metrics | 1 day |
| **8** | **Add daily reconciler.** Cron job: `SELECT orders WHERE NOT EXISTS (wim_visits WHERE checkin_id = meta.checkin_id)` — flag as orphaned. Admin alert if count > threshold. Catches edge cases from session loss or API bypass. | NN#7, Charter §1 | half-day |
| **9** | **Specify OTP verification endpoint + integration pattern.** The plan says "optional, configured per depot." Define: `POST /api/orders/{id}/request-otp`, `POST /api/orders/{id}/verify-otp`, webhook shape for WhatsApp gateway. Even if deferred, the contract must be defined so the data model doesn't need migration later. | FLOWS (OTP mention), SCOPE §OTP | half-day spec |
| **10** | **Add `original_price` and `discounted_price` on export line items.** Without it, an order with strata discount shows total value with no audit trail of the discount amount applied. | NN#9 (auditability) | half-day |

### P3 — V1.1 / V2

| # | Recommendation | Reference |
|---|---------------|-----------|
| 11 | Admin audit trail (`wim_audit_log` table) — every admin action logged | Charter (p.3 audit trail) |
| 12 | EC (Effective Call) calculation pipeline — aggregator from verified orders | NN#12 |
| 13 | "No-order + WA-order" cross-reference report | Charter #6 |
| 14 | Packing list endpoint design (`GET /api/orders/{id}/packing-list`) | Legacy parity |
| 15 | Invoice PDF endpoint design (`GET /api/orders/{id}/invoice`) | Legacy parity |
| 16 | Catalog promo download (PDF) | Legacy parity |

---

## Part E: Key Findings Summary

### What the Plan Gets Right

1. **`meta.checkin_id` + server validation** — The core architectural fix for the GooVi↔KlikOrder data split. Clean design.
2. **QR verification loop** — Full 5-step design with state machine and enforcement. Addresses prior audit's biggest P0 gap.
3. **Export schema with promo separation** — Canonical `purchased[]` + `bonus[]` + `promo_summary` structure is correct and future-proof.
4. **5-layer anti-bypass framework** — Structured controls (checkin, plan, QR, channel, anomaly) that move from "aspirational" to "enforceable" for 4/5 layers.
5. **Client-side promo engine with server verification** — Pragmatic choice for 200-user scale, provided server-side scope is specified.
6. **Order lifecycle state machine** — Complete `DRAFT→SUBITTED→...→DELIVERED` with cancellation before packing.

### What Must Change Before Implementation

1. **Server-side validation scope is undefined (NN#3).** The architectural choice of client-side promo calculation requires a defined server-side re-validation boundary. Without this, promo totals are trust-on-first-use.
2. **'wa'/'telepon' sales_channel values have no creation path.** Bypass tracking requires a mechanism to POPULATE these values. Currently only 'app' and 'admin' can be set.
3. **No-order anomaly detector has no design.** C5 is a named requirement with no API endpoint, no query logic, no admin UI — it's still aspirational.
4. **Admin dashboard is entirely missing.** 7 KPI widgets from legacy KlikOrder have no Fleetbase equivalent. The order system admin has no monitoring capability beyond API queries.
5. **`off_route_reason` should be a structured dropdown**, not free text, for the control to be meaningful.

### Architectural Risk — Promo Engine Location

The biggest architectural risk in this plan is the **client-side promo engine with undefined server-side verification**. For a system whose charter explicitly cites promo auditability as a success metric, the calculation engine being JavaScript (with accelerated JS via Alamacena/obfuscated code -- edit: made up) in a browser session is delicate. The plan correctly notes that `POST /api/orders/calculate` could be server-side, but doesn't commit to either approach — it says client-side with server verification.

**Recommendation:** Commit to a dual implementation:
- Frontend does instant feedback (UX responsiveness)
- Backend has `WimPromoCalculator` service that re-runs every calculation on order submission
- If results differ, **block the order and log an audit event**

This avoids the "cheating by JS manipulation" vector while keeping frontend responsiveness.

---

## Appendix: Prior Audit Gap Resolution Tracking

| Prior Audit Gap | PLAN-DRAFT Resolution | Status |
|-----------------|----------------------|--------|
| G1 No visit↔order cross-validation | `meta.checkin_id` + server validation | ✅ Resolved |
| G2 No barcode/QR verification loop | 5-step verification design | ✅ Resolved |
| G3 Anti-Wa-bypass aspirational | 5/5 controls, 4 enforceable | �ats Resolved (C5 still gap) |
| G4 No promo data in export design | Canonical export schema | ✅ Resolved |
| G5 Photo-based attendance not audit-proof | Not in plan scope (GooVi flow) | 🤊 Not re-addressed (separate flow)|
| GG6 No admin audit trail | Not addressed in plan | 🤊 Still a gap (P3) |
| G8 Username flexibility | Already resolved pre-plan| ✅ Legacy resolved |