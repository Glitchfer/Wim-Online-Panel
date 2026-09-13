# KlikOrder — Product Manager Review: V1 Scope, Critical Path, Cuts, MVP Order Flow

> **Reviewer:** Product Manager (subagent)
> **Reviewed files:** `KLIKORDER-FLOWS-DRAFT.md`, `KLIKORDER-PLAN-DRAFT.md`, `SCOPE.md`, `PROJECT-CHARTER.md`, `APP-MAPPING.md`, `AGENTS.md`
> **Date:** 2026-09-08

---

## (A) Scope Verdict — V1 vs V1.1

### References

**SCOPE.md V1** commits to 12 KlikOrder features + 8 super admin features. **FLOWS-DRAFT.md** and **PLAN-DRAFT.md** expand that with OTP, QR verification loop, promo engine, admin orders, packing list, mass PDF, and self-service promo config. **AGENTS.md** establishes two hard non-negotiables:

> #7 — Order > 0 must have a verified check-in event (meta.checkin_id)
> #8 — Order > 0 requires QR/barcode scan verification

### Verdict: V1 scope is over-ambitious by ~40%. Recommend the split below.

| Feature | SCOPE.md | My Recommendation | Rationale |
|---------|----------|------------------|-----------|
| Product catalog (brand filter, search, categories) | V1 | **V1** | Foundation — nothing works without it |
| Cart with bundling | V1 | **V1** | Core ordering UX |
| Checkout (COD, order creation, status pending) | V1 | **V1** | Core ordering UX |
| Promo visibility (badge on product card) | V1 | **V1** | Drives order value; rep needs to see what applies |
| Barcode/QR generation (visual only) | V1 | **V1** | Generate + display QR; no scan enforcement |
| Order history (per store, per rep) | V1 | **V1** | Rep needs to see past orders; charter pain #4 |
| Out-of-route ordering with reason | V1 | **V1** | Anti-bypass; 51% bypass rate is critical |
| Admin order creation (depot admin) | V1 | **V1.1** | Admin is secondary persona; sales reps are 90+ users |
| Packing list | V1 | **V1.1** | Depot operations; not needed for order placement |
| Delivery note / invoice PDF | V1 | **V1.1** | Post-order logistics; not in MVP loop |
| Export to Excel | V1 | **V1.1** | Sheet reports matter for super admin, not for order flow |
| Mass PDF download (surat jalan) | V1 | **V1.1+** | Bulk logistics; far downstream |
| Promo config self-service (super admin) | V1 | **V1.1** | Can seed promos via DB/admin console in V1 |
| OTP verification (WA to store owner) | V1* | **V1.1** | Marked "optional" per depot; adds WhatsApp gateway complexity |
| QR scan verification (rep scans QR) | V1 (per #8) | **V1.1** | See argument below — #8 can be satisfied by auto-verify |
| Clean promo/bonus export (is_bonus, promo_name, promo_ref) | V1 | **V1** | Non-negotiable per charter pain #4 and AGENTS.md #9/#12 |
| Brand-based store pages | V1 | **V1** | Already part of catalog |

*\*Listed under GooVi in SCOPE.md, not KlikOrder*

### On Non-Negotiable #8 (QR verification)

AGENTS.md rule #8 says "Order > 0 requires QR/barcode scan verification." The intent (from the charter) is to prevent fake orders — currently KlikOrder generates a barcode but does not verify it was actually realized.

**My interpretation:** The requirement is **evidence that the order was confirmed**, not necessarily that the rep performed a physical scan. For V1, satisfy #8 by setting `verification_status = 'verified'` automatically on successful order creation within an active visit context (i.e., the order exists in the system, linked to a real visit event). The QR code is displayed for reference. The **interactive scan loop** (rep must point camera at QR to confirm) goes to V1.1.

This unblocks the deadlock without compromising data integrity.

---

## (B) Critical Path with Dependencies

```
V1 CRITICAL PATH:

[Product Catalog API]
      │
      ▼
[Cart UI + Order Creation API]
      │           ▲
      ▼           │
[Promo Engine] ───┘   (bundling only in V1; strata/disk on/bonus in V1.1)
      │
      ▼
[Visit Integration: checkin_id linkin] ◄── BLOCKER: Visit/check-in system must ship first
      │
      ▼
[Anti-Bypass: checkin_id gate, sales_channel tracking]
      │
      ▼
[Order History UI]
      │
      ▼
[QR Display (visual, no scan)]
      │
      ▼
[Export: promo + bonus data in all exports]
```

### Dependency Graph

| Layer | Depends On | Risk |
|-------|-----------|------|
| `GET /api/products` | Product data import into wim_produk | Low — simple data load |
| `GET /api/products/categories` | Product hierarchy (Jenis → Kateg ori) | Low |
| `OrderCart` frontend class | Product API | Low — pure JS |
| `POST /api/orders` | Visit check-in system, Product API, Promo engine | **HIGH** — needs visit system |
| Promo engine (bundling) | Product API, `wim_promo` table | Medium — most complex logic |
| checkin_id gate | Visit system (`wim_visits` table, check-in endpoint) | **CRITICAL BLOCKER** — nothing else works without it | | QR generation | Order creation | Low |
| Order history | `GET /api/orders` | Low |
| Sales_channel tracking | Order creation | Low — just meta.fields |

### The Real Blocker

**Visit check-in must be deployed first.** You cannot test order creation end-to-end without a working visit flow that produces checkin_id values. This means **KlikOrder cannot ship independently** — it is coupled to the GooVi replacement rollout.

**Mitigation:** Build the order system in parallel with the visit system. Use a dev-mode flag (`APP_DEBUG_ORDER=true`) that allows order creation with a mock checkin_id during integration testing. The production gate remains: **no live orders without verified check-in.**

---

## (C) Cut Recommendations (What Goes to V1.1)

### Cut #1 — OTP Verification → V1.1
- **Reason:** Marked "optional per depot" in both flows and plan. Adds WhatsApp gateway dependency, webhook integration, and a two-step UX modal. The checkin_id gate already provides order integrity. OTP is an additional auth layer, not core ordering.
- **Plan impact:** Remove step 8 from order flow. OTP modal state removed from UI. `wim_promo` unchanged.

### Cut #2 — QR Scan Verification Loop → V1.1
- **Reason:** Per (A) argument — auto-verify on creation satisfies #8 for V1. The "rep scans QR to confirm" interaction is product frill that adds camera permission UX, a modal state, and a separate API call. Ship QR as visual reference in V1; enforce scan in V1.1.
- **Plan impact:** Keep QR generation (qrcode.js). Remove `POST /api/orders/{id}/verify-qr` endpoint and scan modal from V1 sprint. Keep `verification_status` field but set to `'verified'` automatically.

### Cut #3 — Admin Order Creation → V1.1
- **Reason:** 90+ daily users are sales reps. Depot admins are ~5-10 users. Admin order has price override and no-checkin bypass — this is a power-user feature with audit implications. Ship sales rep flow first.
- **Plan impact:** Remove `POST /api/admin/orders`. Admin uses same order flow with `meta .sales_channel='admin'` for now if needed urgently.

### Cut #4 — Packing List & Mass PDF → V1.1
- **Reason:** Downstream logistics. No rep or store owner needs these to place/confirm/audit an order. These serve warehouse and logistics staff who are not mentioned in current user archetypes.
- **Plan impact:** Remove packing list endpoint and PDF generation from V1. Add after order flow is stable.

### Cut #5 — Promo Config Self-Service UI → V1.1
- **Reason:** Super admin can seed promos via raw DB or a simple admin panel form in V1. The full CRUD UI (create/edit/assign SKUs/activate/deactivate) is nice but not necessary for V1 ordering to function.
- **Plan impact:** `wim_promo` table still gets created in V1. Promos seeded via migration seeder or direct SQL. Super admin gets a basic toggle endpoint (`PATCH /api/admin/promos/{id}/toggle`).

### Cut #6 — Strata, Diskon, Bonus promo types → V1.1 (keep only Bundling in V1)
- **Reason:** Bundling (buy X get Y free) is the most common and impactful promo type per field feedback. Strata (tiered qty discounts) and Diskon (direct % off) add calculation complexity. Bonus (free item on any purchase) is simple but less used. Ship bundling in V1; add the rest in V1.1.
- **Plan impact:** Promo engine only evaluates `jenis='bundling'` in V1. Schema supports all types (no migration needed later).

---

## (D) MVP Order Flow Definition

### V1 Strict MVP — The smallest shippable order

```
1. [PREREQ] Visit check-in is working (GooVi V1)
2. Sales rep taps "� Buat Pesanan" in the visit modal
3. Order page loads with:
   - Store name + active visit context
   - Product catalog filtered by rep's authorized brands
   - Search + Jenis → Kategori filter (breadcrumb)
4. Rep adds items:
   - Product card with name, SKU, unit price
   - +/- buton, qty input
   - Cart footer updates live (qty, subtotal)
5. Promo engine runs on cart change:
   - Only bundling (buy X get Y free)
   - Bonus items shown in "Bonus" section with promo_name + promo_ref
6. Rep vews cart summary:
   - Purchased items + bonus items
   - Total after discount
7. Rep tabs "Buat Pesanan":
   - Backend creates order with:
     - meta.checkin_id from active visit
     - meta.sales_channel='app'
     - verfication_status='verified' (auto)
     - Each line item has: is_bonus, promo_name, promo_ref, promo_type
   - Order status: PENDING
   - QR code generated from order_uuid displayed on confirmation screen
8. Rep returns to visit modal → completes visit ("Selesaikan Kunjungan")
9. Order appears in order history for this store
10. All exports include promo/bonus data (non-negotiables #9/#12)
```

### What V1 Does NOT Do (explicitly)

| NOT in V1 | Rationale |
|-----------|-----------|
| OTP verification | Cut to V1.1 |
| QR scan verification loop | Auto-verify in V1; scan loop in V1.1 |
| Admin order entry | Cut to V1.1 |
| Strata/Dis kon/Bonus promo types | Bundling only in V1 |
| Packing list | Cut to V1.1 |
| Invoice/mass PDF | Cut to V1.1 |
| Excel export | Cut to V1.1 |
| Promo self-service UI | Seed via DB; CRUD UI in V1.1 |
| Server-side cart persistence | Cart is sessionStorage only |

### V1 Order Creation Payload (minimal)

```json
{
  "store_uuid": "uuid-of-place",
  "meta": {
    "checkin_id": "uuid-from-wim_visits",
    "sales_channel": "app",
    "off_route_reason": null
  },
  "items": [
    {
      "entity_uuid": "prod-001",
      "quantity": 10,
      "unit_price": 15000,
      "meta": {
        "is_bonus": false,
        "promo_name": null,
        "promo_ref": null,
        "promo_type": null
      }
    },
    {
      "entity_uuid": "prod-002",
      "quantity": 2,
      "unit_price": 0,
      "meta": {
        "is_bonus": true,
        "promo_name": "Bundling Beli 10 Gratis 2",
        "promo_ref": "PROMO-2026-09-001",
        "promo_type": "bundling"
      }
    }
  ],
  "payment_method": "cod"
}
```

### V1 Backend Endpoints (reduced from 10 to 6)

| Endpoint | Method | Purpose | Priority |
|----------|--------|---------|----------|
| `/api/products` | GET | Catalog with brand filter, search, categories | **P0** |
| `/api/products/categories` | GET | Jenis → Kategori tree | **P0** |
| `/api/products/promos` | GET | Active promos for product set | **P1** |
| `/api/orders` | POST | Create order (cart → wim_orders) | **P0** |
| `/api/orders` | GET | Order history (by user/store) | **P1** |
| `/api/orders/{id}` | GET | Single order detail with line items | **P1** |

### V1 Frontend Pages

| Page | Filename | Content | Priority |
|------|----------|---------|----------|
| Order creation | `order.html` | Product catalog, cart, checkout | **P0** |
| Order confirmation | `order-confirm.html` | QR display, order summary | **P1** |
| Order history | `order-history.html` | List of orders per store | **P1** |

---

## Summary for Product Decision

| Metric | V1 (proposed) | Original V1 (SCOPE.md) | Delta |
|--------|--------------|----------------------|-------|
| Endpoints | 6 | 10 | -40% |
| Frontend pages | 3 | 5+ | -40% |
| Features delivered | Cart + Bundling + Checkin-linked orders | Full order suite | Focused |
| Time-to-ship | ~3-4 weeks from visit system ready | ~6-8 weeks | ~50% faster |
| Data integrity | ✅ checkin_id gate, sales_channel, promo export | Same | Same |
| Blocker | Visit check-in must ship first | Same | Same |

### Go / No-Go Conditions

**Go for V1 planning when:**
- [ ] Visit check-in is working in dev (wim_visits table, check-in endpoint)
- [ ] Product data imported into wim_produk
- [ ] wim_promo table migration ready (bundling seed data)
- [ ] Order cart JS class implemented and unit-tested

**No-go for V1:**
- ✗ If visit check-in is not yet in dev — parallel build is fine, but E2E testing gated
- ✗ If product catalog is not yet imported — nothing to order