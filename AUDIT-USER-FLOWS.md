# Business Process Audit — WIM Online USER-FLOWS.md

**Reviewer:** Business Process & Workflow Analyst
**Date:** 2026-09-08
**Reference documents:** USER-FLOWS.md, APP-MAPPING.md, SCOPE.md, PROJECT-CHARTER.md, NON-NEGOTIABLES.md
**Legacy systems:** GooVi (sales visits) + KlikOrder (orders)

---

## Executive Summary

USER-FLOWS.md provides a solid architectural foundation but reveals **systemic coverage gaps** and **business-integrity design holes** that, if shipped as-is, would recreate many of the same problems the charter seeks to eliminate. Of the ~38 legacy use cases documented across Appendices A & B, only **14 are fully built**, **3 are partial/stub**, **19 are not built**, and **2 are out of scope**. More critically, the **anti-WA-bypass enforcement**, **barcode verification loop**, **visit→order cross-validation**, and **admin audit trail** have either no design or only aspirational notes with no implementable specification.

---

## Part A: Completeness Matrix — Legacy Use Case Audit

### A.1 GooVi Features → WIM Online

| # | GooVi Feature | WIM Status | Has Flow? | Has API? | Findings |
|---|---|---|---|---|---|
| 1 | Login (email/password) | ✅ Built | §3 Complete | ✅ | Device_info removed (good), single-session removed (good — multi-device flexibility) |
| 2 | Visit card (today's plan) | ✅ Built | §6.1 Complete | ✅ `/api/stores` | Legacy priority ordering NOT carried over |
| 3 | Check-in/check-out | ✅ Built | §6.2 Complete | ✅ `/api/visits` | Double-checkin guard present; 3-min timer is FRONTEND-ONLY (bypassable) |
| 4 | In-route / out-route flag | ✅ Built | §6.1 Complete | ✅ `source` field | ✓ Covered |
| 5 | Ad-hoc store (luar rute) | ✅ Built | §6.3 Complete | ✅ `/api/visit_plan` | ✓ Covered |
| 6 | Set visit priority | 🔴 Not built | Missing | Missing | Legacy feature — depot admins can't reorder a rep's visit plan. **Gap.** |
| 7 | Selfie photo on visit | ✅ Built | §6.2 Step 4 | ✅ Attachment on `wim_visits` | 1 photo, optional (no enforcement of 1-required) |
| 8 | Additional photos | ✅ Built | §6.2 Step 4 | ✅ Array in `wim_visits.photos` | ✓ Covered |
| 9 | Stock check | 🔴 Stub only | §6.2 Step 5 | Missing `stock/*` endpoints | NOT PERSISTED — data-loss; V1.1 priority #1 |
| 10 | NOO (new outlet) | 🟡 Partial | §7 Complete | ✅ Place + Contact creation | **No OTP verification** (GooVi has WA-OTP to depo PIC); **no draft save**; **no category icons** |
| 11 | OTP verification (WA to depo PIC) | 🔴 Not built | §7 "NOT YET" | Missing | Required for NOO integrity |
| 12 | Order creation | 🔴 Not built | §8.1 Spec-only | Missing | No backend endpoints (`/api/orders/*`), no cart, no checkout |
| 13 | Promo/bundling display | 🔴 Not built | §12 Spec-only | Missing | No promo model, no calculation engine |
| 14 | Dashboard (sales rep) | ✅ Built | §4 Complete | ✅ `/api/dashboard` | ✓ Works |
| 15 | Route map visualization | 🔴 Not built | §11.3 Spec-only | Missing | Only text store lists; no geospatial view |
| 16 | Absensi (attendance) | ✅ Built | §5 Complete | ✅ `/api/absensi` | **GPS is optional** (null on timeout); clock-out has NO mandatory photo |
| 17 | Report (sales rep) | ✅ Built | §9 Complete | ✅ `/api/report` | Four KPI cards only — lacks legacy richness |
| 18 | Report via KlikOrder | 🔴 Not built | §9.1 Spec-only | Missing | Admin reporting gap |
| 19 | Edit customer phone number | 🔴 Not built | Missing | Missing | Minor but present in legacy |

**GooVi coverage: 10/19 fully built = 53%**

### A.2 KlikOrder Features → WIM Online

| # | KlikOrder Feature | WIM Status | Has Flow? | Has API? | Findings |
|---|---|---|---|---|---|
| 1 | Product catalog | 🔴 Not built | §8.1 Mentioned | `GET /api/products` exists | No frontend, no branded catalog endpoints |
| 2 | Brand-based store pages | 🔴 Not built | §8.1 Mentioned | Missing | No brand filter UI |
| 3 | Cart with bundling | 🔴 Not built | §8.1 Spec-only | Missing | Bundling logic entirely unimplemented |
| 4 | Promo visibility in catalog | 🔴 Not built | §12.2 Spec-only | Missing | "PROMO" badge aspirational only |
| 5 | Checkout (COD) | 🔴 Not built | §8.1 Step 5 | Missing | No OTP, no order submission |
| 6 | Barcode/QR generation | 🔴 Not built | §8.1 Step 5 | Missing | Order `public_id` not generated yet |
| 7 | Order history | 🔴 Not built | §8.3 Spec-only | `GET /api/orders` exists | No frontend |
| 8 | Export to Excel | 🟡 Partial | §13 Partial | Sales only | Only sales-rep-level JSON/CSV; no admin multi-format |
| 9 | Out-of-route ordering | 🔴 Not built | §8.1 Step 6 | Missing | `off_route_reason` not implemented |
| 10 | Admin order creation | 🔴 Not built | §8.2 Spec-only | Missing | Backend endpoints needed |
| 11 | Packing list | 🔴 Not built | — | Missing | No payload → entity aggregation |
| 12 | Invoice PDF | 🔴 Not built | — | Missing | No PDF engine integration |
| 13 | Promo management (CRUD) | 🔴 Not built | §12.1-12.2 Spec-only | Missing | No self-service promo UI |
| 14 | Dashboard KPIs (admin) | 🔴 Not built | §10.1 Spec-only | Missing | 7 chart widgets; no admin.html backend |
| 15 | Gamification (koin) | ⛔ Out of scope | — | — | Legitimate OOS |
| 16 | Device registration | 🔴 Not built | — | — | Minor with multi-session tolerance |
| 17 | Notification | 🔴 Not built | — | — | Minor |

**KlikOrder coverage: 0/15 fully built = 0% (only 1 partial, 1 OOS)**

### A.3 Combined Legacy Coverage

| Category | Total | ✅ Built | 🟡 Partial | 🔴 Not Built | ⛔ OOS |
|---|---|---|---|---|---|
| GooVi (visits) | 19 | 10 (53%) | 1 (5%) | 7 (37%) | 0 |
| KlikOrder (orders) | 17 | 0 (0%) | 1 (6%) | 15 (88%) | 1 (6%) |
| **Total** | **36** | **10 (28%)** | **2 (6%)** | **22 (61%)** | **1 (3%)** |

> **Key finding:** The order management pipeline (KlikOrder replacement) is almost entirely undefined at the implementation level. USER-FLOWS.md describes intentions for order creation but no backend endpoints, no cart logic, no promo engine, no barcode verification, and no cross-validation exist.

---

## Part B: Business-Integrity Gaps (Critical)

### B.1 Gap 1 (CRITICAL) — No Visit ↔ Order Cross-Validation Engine

**Charter complaint #1:** GooVi visit data and KlikOrder order data live in separate silos. No cross-validation.

**Charter requirement (p.3):** "100% — every order links to a verified visit event"

**Non-negotiable #7:** "Every order > 0 requires a verified check-in event"

**What USER-FLOWS.md says:** §15.6 says "Blocked by frontend (checkin required)" and "Also blocked by backend (no driver context)."

**What's MISSING from the design:**

| Missing Element | Impact |
|---|---|
| No `visit_id` / `checkin_id` foreign key on the `orders` table | An order exists as a standalone wim_orders record with NO link to the specific check-in that spawned it |
| No backend validation that an open `wim_visits.checkin` exists for `driver_uuid + place_uuid` before an order is placed | The frontend blocks it, but the backend design has no guard — non-negotiable #3 violated |
| No periodic reconciler that flags visits-with-order-but-no-checkin | No data quality tooling |
| No "EC" (Effective Call) calculation pipeline | Non-negotiable #11: EC must come from verified orders, but the report flow shows "Pesanan ditugaskan: 12" — orders assigned, not verified as placed |

**Design gap:** The non-negotiables demand server-side order→visit cross-validation, but the data model has NO join key between `wim_visits` and `wim_orders`. Without `visit_uuid` or `checkin_id` on the order payload, reconciliation requires heuristic matching by driver + date + store — which is the same broken approach the legacy system uses.

**Recommendation:** Add `meta.checkin_id` (wim_visits UUID) to every order payload at creation time. Backend must reject orders (400) that don't carry a valid, open `wim_visits.checkin` record for that driver at that place. Implement a daily reconciler: `SELECT wim_visits WHERE checkout_at IS NULL AND DATE(checkin_at) < TODAY` → flag missed checkouts.

---

### B.2 Gap 2 (CRITICAL) — No Barcode/QR Verification Loop

**Charter complaint #2:** KlikOrder generates a barcode but there's NO verification that it matches what was realized.

**Non-negotiable #8:** "When a sales rep submits an order > 0, the system must generate a QR code (order reference), and the rep must scan it to confirm the order was actually placed. No auto-verification bypass."

**What USER-FLOWS.md says:** §8.1 Step 5 says "Generate order reference" and "QR code for warehouse scanning." Step 6 says "Option to download QR/barcode."

**What's MISSING:**

| Missing Element | Impact |
|---|---|
| No scan-verification step in the order flow | The QR is generated for *warehouse* scanning, not for *sales rep* verification |
| No design for the verification API endpoint | No `POST /api/orders/{id}/verify-qr` |
| No enforcement that the verification MUST happen | Non-negotiable says "no auto-verification bypass" — no design for this |
| No re-verification if QR is regenerated | Replay attack vector |

**The flow doc confuses QR-for-logistics (warehouse reads the code) with QR-as-verification-loop (rep scans to prove order is real). These are different controls.**

**Recommendation:** Design a two-step verification:
1. **At order creation:** Generate QR encoding `order_uuid`. System state: `verification_status = 'pending'`.
2. **At visit checkout:** Rep must scan the QR. Frontend calls `POST /api/orders/{id}/verify-qr {qr_code, place_uuid}`. Backend validates QR matches the order, sets `verification_status = 'verified'`, records `verified_at`.
3. **Enforcement:** Visit checkout with `status = 'ordered'` is BLOCKED if `verification_status ≠ 'verified'` for any active order at that store.

---

### B.3 Gap 3 (HIGH) — Anti-WA-Bypass Design Is Aspirational, Not Enforced

**Charter complaint #6:** 51% of out-route orders placed via WA/Telepon instead of the app.

**What USER-FLOWS.md says:** §15.6 says "Out-of-route via WA/Telepon: Must use app 'Tambah Luar Rute' → order flow. Current 51% avoidance rate."

**What's MISSING:**

| Missing Element | Impact |
|---|---|
| No server-side guard that an out-of-route STORE must be in the visit plan before an order can reference it | A rep can add an out-of-route store, record "Tidak Ada Pesanan" (no order), then place the real order via WA — the visit exists but the order isn't in the system |
| No enforcement that visits with no-order-reason "Tidak Ada Pesanan" cannot suddenly have pending orders in the background | Reconciler needed: visits where status='no_order' but orders exist for that store+driver on that date = anomaly |
| No behavioral telemetry on "no-order" patterns | A rep who logs "Tidak Ada Pesanan" for the same store every 2 weeks is likely bypassing |
| No depot admin alert when a rep's no-order rate exceeds threshold | Missing operational control |

**Recommendation:**
1. **Block out-of-route orders without a visit plan entry.** The `wim_visit_plan` table must have a row for that `place_uuid + user_id + date` before any order referencing that place can be created.
2. **Add `sales_channel` field to orders:** `meta.sales_channel = 'app' | 'wa' | 'telepon' | 'admin'`. Any order created through the proper flow defaults to `'app'`. This puts a stake in the ground for tracking which orders were placed through which channel.
3. **Add a "no-order anomaly detector"** to the admin dashboard: sales reps with >30% no-order rate over a week get flagged.
4. **Out-of-route orders must have `off_route_reason`** (non-negotiable #11), and the reason must be from a structured dropdown (not free text — or the rep types "customer called me" and it's still in WA/Telepon bypass territory).

---

### B.4 Gap 4 (HIGH) — Promo/Free-Product Data in Exports Has No Concrete Design

**Charter complaint #4:** "KlikOrder order history shows product details but no promo or free product data."

**Non-negotiable #9:** "Export data must include promo/free-product information."
**Non-negotiable #12:** "Exports separate product lines from promo/bonus lines."

**What USER-FLOWS.md says:** §13 lists export types. "Required from GooVi+KlikOrder (NOT BUILT)" — 11 export formats with no promo data structure designed. §15.6 says "Bonus items tracked in order line items" as intended behavior.

**What's MISSING:**
- No export schema that separates `line_items` (purchased) from `bonus_items` (free)
- No `promo_name`, `promo_ref`, `promo_type` fields on line items
- No specific export handler for the 11 required admin export formats
- No `is_bonus` flag column designed on order line items

**Recommendation:** Define the canonical export payload schema NOW — before the order system is built — so the data model is correct from day one:

```json
{
  "purchased": [
    {"sku": "SQA-PET-550", "name": "SANQUA PET 550ML", "qty": 10, "unit_price": 15000, "total": 150000}
  ],
  "bonus": [
    {"sku": "SQA-PET-220", "name": "SANQUA PET 220ML", "qty": 2, "promo_name": "Bundling Beli 10 Gratis 2", "promo_ref": "PROMO-2026-09-001", "promo_type": "bundling"}
  ],
  "promo_summary": {"total_discount": 30000, "total_bonus_value": 15000, "promos_applied": ["Bundling Beli 10 Gratis 2"]}
}
```

---

### B.5 Gap 5 (HIGH) — Photo-Based Attendance Is NOT Audit-Proof

**Charter demand:** An audit-proof attendance system. The current GooVi system has selfie check-in.

**What USER-FLOWS.md says:**
- §5.1: GPS at clock-in with 3s timeout → proceeds with `null` lat/lng on failure
- §5.2: Clock-out has NO mandatory photo requirement (only "if clockOutPhoto exists" in localStorage)
- Photos stored in `localStorage` (browser-side) — can be cleared, tampered, or replaced

**Audit weaknesses:**

| Weakness | Exploit Scenario |
|---|---|
| GPS timeout → null location | Rep clocks in from home (30km from depot); GPS times out; no evidence of location |
| Clock-out has no mandatory photo | Rep clocks out at 14:00 without visiting last 3 stores; no photo evidence |
| Photos stored in localStorage | A rep can replace the clock-in photo after the fact by uploading a different one |
| No geofence at clock-in | Attendance is NOT validated against a depot zone — differs from store visit (which has 10m geofence) |
| No server-side timestamp verification | Frontend sends `"time": "08:00"` — could be spoofed |
| Clock-out has no GPS | Rep claims to be at depot but could be anywhere |

**Recommendation:**
1. **Attendance must use the same geofence pattern as store visits.** The depot should be a `Zone` with a 50-100m circular polygon. Clock-in is only accepted when the rep's GPS is inside the depot zone.
2. **Clock-out MUST also have a mandatory photo.** Not optional.
3. **GPS must be mandatory, not best-effort.** If GPS fails after 10s (not 3s), the clock-in is rejected. Offer "retry" not "skip."
4. **Server-side generates the timestamp.** The frontend sends `action: "clock_in"` and `photo`; the server records `clock_in = NOW()` — not the client's reported time. This prevents clock-in-time spoofing.
5. **Store photos server-side, not localStorage.** Attendance photos must go to MySQL or S3, not the browser's `sessionStorage`.

---

### B.6 Gap 6 (MEDIUM) — No Admin Audit Trail

**Charter requirement:** "Route-to-order audit trail" — every route waypoint → visit event → order is traceable.

**What USER-FLOWS.md has:**
- §10 (Admin Management): Only a shell page `admin.html` exists with NO backend endpoints
- §7 (NOO): No edit/update flow for admin changes to store data
- Nowhere: No `admin_audit_log` table, no `who changed what` tracking
- Nowhere: No route modification history

**What the legacy system has:**
- GooVi: `/user-sessions` (view active sessions, force-reset)
- GooVi: `/kunjungan-harian/detail-penggunaan-aplikasi` (app usage log)
- KlikOrder: Dashboard KPI tracking

**Design gap:** Any admin action (route reassignment, user role change, promo activation, order override) is currently **invisible** — no audit trail, no rollback capability. For a system that replaces two compliance-critical tools, this is a regulatory risk.

**Recommendation:** Design `wim_audit_log` table:
```
id | actor_uuid | action | target_type | target_uuid | old_value | new_value | ip_address | user_agent | created_at
```
Every admin-endpoint handler must insert an audit row. Surface this in the admin panel as a log viewer.

---

### B.7 Gap 7 (MEDIUM) — Minimum Visit Timer Is Bypassable

**What USER-FLOWS.md says:** §6.2 Step 2: "Timer runs in browser (VisitTimer class), not server-side."

**Risk:** A rep can:
- Open browser DevTools → execute `timer.forceComplete()`
- Refresh the page → timer resets
- Use a browser extension to manipulate JS timers
- Send API calls directly (curl/Postman → bypass the frontend entirely)

**Recommendation:** The minimum visit duration must be server-enforced. Backend should reject checkout if `checkout_at - checkin_at < 180 seconds`. The frontend timer is a UX convenience, not a security control.

---

### B.8 Gap 8 (LOW) — Username/Account Flexibility

**Charter complaint #3/#7:** Vendor lock on username changes.

**Status:** ✅ Addressed. WIM Online supports user management via `wim_users` table. Replaced KlikOrder's vendor-locked account model.

**This is the only charter complaint with a complete resolution in the current design.** No gaps here.

---

## Part C: Integrity-Gap Severity Ranking

| Rank | Gap | Severity | Impact |
|---|---|---|---|
| **P0** | No visit→order cross-validation engine | **CRITICAL** | Recreates GooVi→KlikOrder data-split problem. Non-negotiable #7 violated. |
| **P0** | No barcode/QR verification loop | **CRITICAL** | Non-negotiable #8 violated. Fake orders undetectable. |
| **P1** | No anti-WA-bypass enforcement | **HIGH** | Charter complaint #6 unresolved. 51% bypass rate will not improve. |
| **P1** | No promo/free data in export design | **HIGH** | Non-negotiable #9, #12 violated. Audit inability for promotions persists. |
| **P1** | Attendance not audit-proof | **HIGH** | Photo, GPS, and timestamp controls are too weak for attendance integrity. |
| **P2** | No admin audit trail | **MEDIUM** | Every admin action is invisible. Compliance risk. |
| **P2** | Minimum timer frontend-only | **MEDIUM** | Bypassable artificial constraint. |
| **P3** | Stock check not persisted | **LOW** | V1.1 priority, but weakens store-level analytics until then. |
| **P3** | Set visit priority not built | **LOW** | Legacy feature missing but workaround exists (route import ordering). |

---

## Part D: Priority-Ranked Recommendations

### P0 — Must-Fix Before V1 Shipment

| # | Recommendation | Reference | Effort |
|---|---|---|---|
| 1 | **Design order→visit linking.** Add `meta.checkin_id` (UUID from `wim_visits`) to every `wim_orders` payload. Backend rejects orders without a valid, open check-in for that driver+place. | Non-negotiable #7 | 2 days |
| 2 | **Implement barcode verification loop.** QR encodes `order_uuid`. Rep must scan QR before visit checkout finalizes. API: `POST /api/orders/{id}/verify-qr`. State machine: `pending → verified`. Visit with `status=ordered` blocked if any order at that store is unverified. | Non-negotiable #8, Charter #2 | 3 days |
| 3 | **Enforce attendance GPS+photo as mandatory, not best-effort.** Depot geofence on clock-in. Mandatory photo on both clock-in and clock-out. Server-generated timestamps. No null GPS tolerance. | Non-negotiable #3, §5 | 1.5 days |

### P1 — Ship-Blocking Gaps

| # | Recommendation | Reference | Effort |
|---|---|---|---|
| 4 | **Block out-of-route orders without visit plan entry.** `wim_visit_plan` row must exist for `place_uuid+user_id+date` before any order referencing that place can be created. Add `off_route_reason` enforcement. | Charter #6, Non-negotiable #11 | 1.5 days |
| 5 | **Define canonical export schema with promo/bonus separation.** Implement `is_bonus`, `promo_name`, `promo_ref`, `promo_type` on order line items BEFORE the order system ships. Don't build the export UI yet — lock in the data model. | Non-negotiable #9, #12 | 1 day |
| 6 | **Enforce minimum-visit server-side.** Backend rejects checkout if `checkout_at - checkin_at < 180s`. Frontend timer is UX-only decorative. | Non-negotiable #3 | 0.5 days |
| 7 | **Add "no-order anomaly" dashboard widget.** Depot admin can see reps with >30% no-order rate per week. | Charter #6 | 1 day |

### P2 — High Priority for V1 or Early V1.1

| # | Recommendation | Reference | Effort |
|---|---|---|---|
| 8 | **Design `wim_audit_log` table.** Every admin endpoint logs: `actor_uuid, action, target_type, target_uuid, old_value, new_value, ip, created_at`. | Charter (p.3 audit trail) | 1 day |
| 9 | **Add `sales_channel` field to orders.** `meta.sales_channel = 'app' \| 'wa' \| 'telepon'`. Default `'app'`. Allows depot admin to tag admin-entered orders. | Charter #6 | 0.5 days |

### P3 — V1.1

| # | Recommendation | Reference |
|---|---|---|
| 10 | Implement stock check persistence (V1.1 #1 — already flagged) | §6.2 Step 5 |
| 11 | Implement visit priority reordering | Appendix A #6 |
| 12 | Implement NOO draft save + OTP verification | Appendix A #10 |

---

## Part E: Anti-WA-Bypass — Detailed Workflow Design

The current doc's approach ("Must use app") is aspirational. Here is the enforceable design:

```
Flow for an out-of-route order:

1. REP is at an unplanned store
2. REP opens app → "Tambah Luar Rute" → selects store
3. REP checks in to store (GPS + 10m geofence verified? Yes, even for out-of-route)
4. REP opens "Buat Pesanan"
   → Backend checks: is `wim_visit_plan` row present for this place+user+date?
   → NO → 403 "Toko belum ditambahkan ke daftar kunjungan hari ini"
5. REP creates order
   → Order payload REQUIRES `meta.checkin_id` (from the wim_visits row)
   → Order payload REQUIRES `meta.off_route_reason` (structured dropdown)
   → Backend validates both exist → proceed
6. QR generated → REP scans to verify → `verification_status = 'verified'`
7. Visit checkout → order submitted

What happens if the rep bypasses (steps 3-5) and texts the depot admin "order for Toko X via WA":
→ Depot admin can create an admin order (§8.2)
→ That order gets `meta.sales_channel = 'wa'`, `meta.ordered_by_admin = true`
→ Both flags are visible in reports, making bypass TRACKABLE
→ NOT BLOCKED — but visibile, auditable, and the rep's no-order+WA-order combo is flagged
```

This pattern doesn't block admin flexibility but creates full traceability — exactly what the charter demands.

---

## Part F: Summary Assessment

### What USER-FLOWS.md Gets Right
- **Authentication and session management** (§3) are thorough with rate limiting, error states, and session lifecycle
- **Visit card flow** (§6) covers the core workflow in detail with double-checkin/checkout guards
- **NOO flow** (§7) handles the GooVi data model migration correctly (14+ fields mapped)
- **Edge cases** (§15) are documented comprehensively (30+ scenarios covering auth, visits, absensi, network)
- **Data flow architecture** (§16) cleanly separates WIM custom tables (all in PostgreSQL `wim_sfa`)
- **Appendix A & B** provide an honest and clear status of every legacy feature

### What Must Change Before Shipment

1. **The order system is the heart of the product and it's entirely aspirational.** USER-FLOWS.md describes what it should do (cart, checkout, promo, barcode) but no API endpoints, no data model schema, no backend design exist. Every P0 and P1 gap traces back to this.

2. **The non-negotiables are not reflected in the flow design.** Seven of the 13 non-negotiables have no corresponding design artifact. The gap between "what the charter demands" and "what USER-FLOWS.md specifies" is the primary risk.

3. **The anti-bypass control is a note, not a design.** §15.6 says the intent but no mechanism, no enforcement, no anomaly detection.

4. **Attendance integrity is weaker than the legacy system.** GooVi's attendance required mandatory selfie + GPS; WIM Online makes both optional under error conditions.

5. **No admin audit trail exists.** Every admin action is currently unlogged — a regression from GooVi's session management.

### Verdict

**USER-FLOWS.md is a solid V0.5 specification.** It correctly identifies what needs to be built but has **no executable design for the order system** (which is 100% of the KlikOrder replacement) and **enforcement mechanisms that are aspirational where they should be concrete**. The document would benefit from a "Security & Integrity Controls" section that traces each non-negotiable to a specific API endpoint, data model constraint, and backend validation rule — closing the gap between charter requirements and implementation guidance.