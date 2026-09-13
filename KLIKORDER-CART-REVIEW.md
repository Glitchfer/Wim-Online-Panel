# KlikOrder Cart UX Review — B2B Order System Expert Analysis

> **Reviewer:** Senior E-Commerce / Order-Management UX Expert (B2B CPG Distribution)
> **Reviewed:** KLIKORDER-FLOWS-DRAFT.md, KLIKORDER-PLAN-DRAFT.md, APP-MAPPING.md (§KlikOrder)
> **Date:** 2026-09-08

---

## (A) Verdict Per Section

### 1. Sales Rep Order Flow (§Flows: 34–61)
**Verdict: 🔶 STRUCTURALLY SOUND, 3 CRITICAL MISSING PIECES**

The flow is correct at a high level: check-in → browse → cart → promo → OTP → QR → visit close. The anti-bypass integration (checkin_id enforcement, QR verification loop) is a strong design. However:

- **Order entry is buried.** The rep must: open store modal → check-in → take photos → stock check → THEN "Buat Pesanan". That's 4 taps before reaching the primary action a rep is at the store to do. In a hot, noisy shop, this kills adoption.
- **No offline fallback.** 200 users at Indonesian depot scale means variable connectivity. A field rep in a basement store (Tanah Abang, mall basement) will lose signal. No offline cart persistence is mentioned.
- **No "quick reorder" flow.** 51% bypass rate suggests reps already have a mental model of "the last order" — they reorder from history via WA instead of the app. No path for "reorder same items as last visit."

### 2. Admin Order Flow (§Flows: 64–72)
**Verdict: ✅ SOLID FOUNDATION, 2 CLARIFICATIONS NEEDED**

Price override and ad-hoc items are correctly called out as admin-only. No OTP is correct for admin trust level. However:

- **No "copy from rep order" path.** Admins frequently re-key orders that came in via WA/Telepon. The plan has `sales_channel='wa'` but no UI to let an admin convert a WA order record into a real order without re-entering every SKU.
- **Price override audit trail.** A price override without an `override_reason` or `override_approved_by` field will be abused by admins under depot pressure.

### 3. Cart UI & Layout (§Plan: 63–93)
**Verdict: 🔴 MOBILE-FIRST FAILURES — NEEDS REDESIGN**

The proposed layout (Plan §2.1) is a **desktop-first** design shoehorned into mobile. Problems:

- **Product cards are too wide for one-hand use.** The "+" and "−" buttons at right edge force a thumb stretch. On a 6.1" phone held in one hand, the right 20% of screen is a hard reach zone. QTY stepper should be left-justified per card or use a swipe-to-add pattern.
- **Bottom summary bar steals critical screen height.** ~25% of viewport taken by a persistent summary that only matters at decision time. On mobile, this should be a collapsible or a floating FAB with a counter badge, expanding to full summary on tap.
- **No quick-add scan mode.** Legacy KlikOrder has barcode scanning (APP-MAPPING §KlikOrder Sales API). The plan mentions QR at checkout but not barcode scanning for product entry — a huge miss for field reps who can scan shelf barcodes to add items instantly.
- **Brand tabs as horizontal scroll tabs** ("[Semua] [SANQUA] [LEVONTE] [BAT]") don't work at 3+ brands (KAP, WIN etc. exist). Horizontal tab bars with 5+ items require swipe-hunting. Use a dropdown or a vertical filter panel instead.

### 4. Cart as Bottom Sheet vs Full Page (crucial decision)
**Verdict: ❓ BOTTOM SHEET IS CORRECT, BUT IMPLEMENTATION NEEDS SPEC**

The plan doesn't explicitly decide this. For mobile field use:

- **Bottom sheet (detent-based)** is the right pattern. The rep scans products → sees a floating badge count → pulls up the sheet to review. Keeps catalog visible beneath. Full-page cart would lose browsing context.
- **Must spec:** 3 detent levels: collapsed (badge only), mid (summary + promo line), expanded (full line items + bonus). iOS `UISheetPresentationController`-style or CSS `snap-scroll` equivalent.
- **Edge case:** Depot admin on desktop — bottom sheet is wrong here. The admin view should be a side panel or a split-pane layout. The plan doesn't distinguish responsive behavior.

### 5. Promo Engine & Display (§Flow: 47–54, §Plan: 132–168)
**Verdict: 🔶 FUNCTIONALLY COMPLETE, UNDERSPECIFIED FOR EDGE CASES**

The four promo types (bundling, strata, diskon, bonus) and the engine flow are correctly mapped from legacy. The client-side calc + server-side verification split is appropriate at 200-user scale. Gaps:

- **Promo conflict resolution is ambiguous.** The plan says "Apply the best applicable promo (or sum if configurable)." This is dangerously vague. What happens when strata + diskon both apply to the same SKU? KlikOrder legacy uses `checkAllPromoKeranjang-byPrioritas` (a priority-ordered check). The plan must define priority order and whether overlapping promos stack or exclude.
- **Promo badge is mentioned but visual hierarchy unspecified.** A "🏷 PROMO" badge on every promoted product teaches the rep nothing — which promo? How much savings? Show: "Diskon 10%" or "Beli 10 gratis 2 LEVONTE" on the card directly.
- **No promo "countdown" or "limited time" context.** B2B promos have end dates (periode_end). The rep should see "Promo berakhir 3 hari lagi" on cards — urgency drives conversion.
- **Strata tier display is invisible until thresholds met.** A rep adding 8 units of an item that has a strata discount at qty 10 sees zero visual feedback until item 10 is added. Must show "Tambahkan 2 lagi untuk diskon strata 10%" as a live hint.

### 6. Checkout Flow — OTP & QR Verification (§Flow: 56–59, §Plan §1.4)
**Verdict: 🔶 CORRECT DIRECTION, UX FRICTION POINTS**

- **OTP as "optional" is a weak design.** The plan says "OTP verification (optional, configured per depot)". Optional means it will be turned off everywhere to save 5 seconds, defeating its purpose. The charter complaints specifically mention no verification existing. Make OTP mandatory for orders above a configurable threshold (e.g., > Rp 500K) and optional below.
- **QR verification loop has a UX trap.** The rep creates order → sees QR → must scan it with the same phone. On a single device this means: view QR → back out → open scanner → scan → return. That's 4 steps. Consider: (a) use the self-facing camera, or (b) let the rep scan a printed QR (on the store wall) so the store owner also sees verification, or (c) skip self-scan when the order is created via the app from within the store geofence (GPS proximity replaces QR). The current design will be bypassed in practice.
- **No "pay later" or COD confirmation.** Legacy KlikOrder uses COD. The plan has no payment step — fine for pure COD, but the confirmation screen must show "Pembayaran: Tunai (COD)" or the store owner will ask at delivery.

---

## (B) Prioritized UX Improvements

### P0 — MUST FIX (blocks adoption, enables bypass)

| # | Area | Improvement | Concrete Spec Change |
|---|------|-----------|---------------------|
| 1 | Flow | **Add barcode scan for product entry** | In the product catalog header, a camera icon. Tap → viewfinder scans shelf barcode → `POST /api/products/lookup-barcode` → if found, add 1 qty directly to cart. Falls back to search. |
| 2 | Cart | **Swap bottom summary for floating FAB + collapsible sheet** | Replace permanent bottom bar (§Plan 2.1 layout) with: circular FAB showing count badge ("3") → tap opens bottom sheet with 3 snap detents. Desktop: side panel. |
| 3 | Promo | **Define priority-ordered promo conflict resolution** | **Specify:** `bonus` > `bundling` > `diskon` > `strata` precedence. If two apply to same SKU, higher priority wins. Summable: only `strata` can stack with `diskon`. Add this to §Plan §1.3 point 5. |
| 4 | Checkout | **Make OTP mandatory above a configurable threshold** | Add `otp_threshold` to depo_config. Default Rp 500K. Orders below threshold skip OTP. Non-negotiable: orders with `sales_channel='app'` from a verified check-in geofence AND under threshold skip OTP. |
| 5 | Cart | **Left-justify qty controls on product cards** | Move `- + 5` from right edge to left column on mobile. Or use: tap card = +1, long-press = −1, tap qty number for manual input. No thumb stretch. |

### P1 — SHOULD FIX (significant quality & efficiency gains)

| # | Area | Improvement | Concrete Spec Change |
|---|------|-----------|---------------------|
| 6 | Flow | **Add "Re-order from last visit" shortcut** | Below the search bar, a button: "🔄 Pesanan Terakhir" → loads last order's line items into cart (qty pre-filled). Reduces 51% bypass by removing friction. |
| 7 | Catalog | **Replace horizontal brand tabs with dropdown/modal filter** | On mobile: a pill button "[SANQUA ▾]" that opens a vertical brand checklist. On desktop: sidebar filter. Only one brand visible at a time. |
| 8 | Promo | **Show strata tier progress on product cards** | If SKU has strata: show progress bar + text "Diskon strata 10% pada qty 10. Saat ini: 8" inline below the price. Update live as qty changes. |
| 9 | Promo | **Show promo name + savings, not just "PROMO" badge** | Replace "🏷 PROMO" with either "⬇ 10%" or "🎁 Beli 10 Gratis 2". Show original price + discounted price on card (strikethrough). |
| 10 | Checkout | **Simplify QR verification for same-device flow** | Option A: present QR on screen, then auto-open scanner after 3s countdown ("Arahkan kamera ke QR"). Option B: verify via GPS proximity — if rep is within store geofence at order creation, auto-verify. Fall back to QR only when GPS is off. |

### P2 — NICE TO FIX (polish, edge cases, future-proofing)

| # | Area | Improvement | Concrete Spec Change |
|---|------|-----------|---------------------|
| 11 | Admin | **Add "duplicate from WA/Telepon order" button** | Admin order page: search an order by ID → tap "Duplikat Pesanan" → pre-fills cart with same line items. Admin adjusts qty → saves as new admin order. |
| 12 | Admin | **Price override reason field (mandatory)** | Require `override_reason` select (Stok Lama, Promo Khusus, Negosiasi, etc.) when unit_price differs from catalog. Log to `meta.override_reason` and `meta.override_by`. |
| 13 | Cart | **Empty cart should show last-order suggestion** | Instead of "Keranjang masih kosong", show: "Belum ada item. 📋 Pesanan terakhir dari 3 hari lalu: [3 item, Rp 450K] — 🔄 Pesan Lagi?" |
| 14 | Promo | **Expiring promo countdown badge** | If `periode_end - today ≤ 7 days`, add "⏳ Berakhir 3 hari" under the promo badge. |
| 15 | Offline | **Local cart persistence in IndexedDB/LocalStorage** | Cart state survives tab close, browser crash, network loss. On reconnect: re-validate promos (may have expired) → warn rep if promo prices changed. |

---

## (C) Gaps & Contradictions Found

### Contradictions

1. **Client-side vs server-side promo calc (§Plan §1.3 point 7 vs §Plan §5)**
   - Plan §1.3 says "Client-side calculation (JS)" with server-side verification on order creation.
   - But the legacy KlikOrder uses **server-side** promo endpoints (`POST /api/toko-order/promo/check-bundling`, `check-strata`, `checkAllPromoKeranjang-byPrioritas` in APP-MAPPING).
   - **Risk:** If the JS client-side engine diverges from the PHP server-side engine, orders will fail at submission with "promo mismatch". The rep will see a different total in the cart vs what the server accepts.
   - **Fix:** Either run the same calculation on both sides (reference implementation in JS, mirrored in PHP), or move promo calc to a single server-side `/api/orders/calculate` endpoint and only display results client-side. The 200-user scale doesn't justify the complexity of dual engines.

2. **QR verification in Plan §5 vs Flow §Flows §9**
   - Plan §5.3 says QR verification is required and blocks visit checkout if unverified.
   - Flow §58 says OTP is "optional" and QR is the verification loop.
   - **Conflict:** If OTP is optional but QR is mandatory, what happens when a depot disables OTP? The flow says step 6 (OTP) is skipped, step 8 (QR) still runs. That means QR verification is the **only** authentication gate. A QR generated and scanned on the same device is zero-factor auth (possession-only). This is weaker than the current KlikOrder OTP-to-owner-WA flow.
   - **Fix:** Do not rely on same-device QR as a meaningful verification. Either: (a) require the store owner's phone to scan the QR (printed or displayed on rep's phone), or (b) use QR as a delivery-verification token (scanned by the driver at drop-off, like current surat jalan), not as an order-creation gate.

3. **Visit timer in cart header (§Plan §2.1)**
   - The layout shows "Timer: 1:45" in the cart header for visit context.
   - But the existing visit flow (§4 integration) says the timer starts at check-in and runs **before** the order page opens. If the rep is deep in the catalog searching for a SKU, visible timer causes anxiety and rushed orders.
   - **Fix:** Move the timer to the visit modal only. In the order page, display "Kunjungan ke Toko Berkah" without the countdown. The timer is in the background visit context, not in the shopping UI.

### Gaps

4. **No "order template" or "frequent items" concept** — B2B CPG reps often sell the same 5-10 SKU combinations daily. No fast-path for this.

5. **No split-delivery support** — Some B2B orders ship partially (backordered items). The data model has no backorder flag, no `qty_shipped < qty_ordered` tracking.

6. **No "hold order" state** — Rep starts building an order, store owner says "tunggu bentar", rep needs to save-as-draft and come back. The plan has no DRAFT → RETURN path. Cart is ephemeral (sessionStorage). If the rep closes the browser or switches stores, the partial order is lost.

7. **No price discrepancy warning** — If the catalog price differs from the last invoice's price (common in CPG due to promotions), the rep has no way to know. Should show "Harga terakhir: Rp 14.000" vs current "Rp 15.000" on the product card.

8. **Depot-specific pricing missing** — APP-MAPPING shows depots exist (JABAR, JATIM, JATENG). The plan has `depo_uuid` on promos but no per-depot price lists for the same SKU. Different depots may sell the same SKU at different base prices. The plan needs a `price_list` concept.

9. **No "bundle SKU" or "case/pack" unit handling** — The order uses "karton" (carton) as the unit. But some products sell by piece (cup, bottle) and some by case. The qty increment and unit price need per-SKU `uom` (unit of measure) and `qty_per_case`. A rep shouldn't be able to order 1.5 cartons.

10. **No error recovery for failed order creation** — What happens when `POST /api/orders` fails mid-transaction (server timeout, network drop)? The plan has no retry logic, no "resume partial order" state. The rep loses the entire cart.

---

## Summary Recommendation

**Do not build the cart as drawn in §Plan 2.1.** The layout is desktop-first and will fail in field mobile use. Specific changes required before development starts:

1. Redesign the product card for **left-thumb reach** (stepper on left, not right)
2. Replace the permanent bottom bar with a **floating FAB + detent-based bottom sheet**
3. **Add barcode scanning** as primary product entry (not QR-at-checkout-only)
4. Move promo calc to **server-side endpoint** (avoid dual-engine divergence)
5. Add **"reorder last visit"** shortcut to address the 51% bypass root cause
6. Make OTP **threshold-based**, not boolean optional
7. **Fix the self-scan QR paradox** — a QR generated and scanned on the same device is not verification

The architecture is otherwise sound — the PostgreSQL data model, checkin_id enforcement, sales_channel tracking, and export schema are well-specified. The gaps above are additive, not foundational rebuilds.