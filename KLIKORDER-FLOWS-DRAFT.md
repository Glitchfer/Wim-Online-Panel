# KlikOrder Replacement — Shopping Cart User Flows (DRAFT for Review)

> User flow definition for the KlikOrder replacement: in-app ordering, cart, promo,
> checkout, and order lifecycle. To be reviewed by 5 subagents before implementation planning.

## Context

WIM Online will replace KlikOrder's ordering capability. Legacy analysis (APP-MAPPING.md §KlikOrder):

- **Products:** Multi-brand catalog (SQA, KAP, WIN) with hierarchy: Jenis (type) → Kategori (category) → Brand → SKU
- **Brand restrictions:** Reps only see brands they're authorized to sell (`brands-auth`)
- **Promos:** Bundling (buy X get Y free), Strata (tiered qty discounts), Diskon (direct), Bonus (free product); promotion logic: `check-bundling`, `check-strata`, `checkAllPromoKeranjang-byPrioritas`, `calculate-global-combined-strata-discount`
- **Checkout:** OTP verification (WA to store owner), COD payment, order reference, barcode/QR generation
- **Bypass problem:** 51% of out-of-route orders placed via WA/Telepon instead of app
- **Charter complaints:** no promo data in history, no barcode verification, orders not cross-validated with visits

## Personas

| Persona | Needs |
|---------|-------|
| Sales Rep | Order during visit, promo-aware cart, quick entry (1-tap per SKU), order history per store |
| Depot Admin | Admin order entry (on behalf of store), packing list, invoice/PDF export |
| Super Admin | Promo configuration (self-service), order analytics, order status monitoring |

## Order Lifecycle (full state machine)

```
DRAFT → PENDING → VERIFIED → SUBMITTED → PROCESSING → PACKED → SHIPPED → DELIVERED
                        ↘ CANCELLED (with reason, before packing)
```

Key non-negotiable: **Order > 0 requires a verified check-in event** (meta.checkin_id on order)

## Sales Rep Order Flow (proposed)

```
1. Visit store → tap "🛒 Buat Pesanan" (in visit modal, after check-in)
2. Order screen opens with store context (from visit)
   - Store name, visit timer status shown
   - Product catalog with brand filter (only authorized brands)
   - Search + category filter (Jenis → Kategori)
3. Rep adds items to cart:
   - Product cards: name, SKU, price, stock hint
   - Promo badge if active promo on product
   - Tap +/- or qty input per product
   - Cart totals update live (line count, total qty, total Rp)
4. Promo engine runs automatically on cart change:
   - Bundling: shows "Beli 10, gratis 2" + auto-adds free items
   - Strata: tiered discount applied at thresholds
   - Combined discount calculation
   - Free items shown separately in cart ("Bonus" section)
5. Rep reviews cart:
   - Purchased items (priced line items)
   - Bonus/free items (promo_name, promo_ref, qty)
   - Total (after discounts)
6. Rep taps "Buat Pesanan" → OTP verification (optional, to store owner WA)
7. Order created → status PENDING → order reference generated
8. QR/barcode generated encoding order_uuid → rep scans to verify (verification loop)
9. Visit checkout completes with order attached (meta.checkin_id validated server-side)
10. Confirmation screen: order ID, items, total, QR code
```

## Admin Order Flow (proposed)

```
1. Admin selects store (search by name/code)
2. Same catalog + cart as sales rep
3. Admin can override prices, add ad-hoc items
4. No OTP required (admin verified)
5. Order created with meta.ordered_by_admin=true, meta.sales_channel='admin'
6. Packing list + invoice PDF generation available
```

## Promo Management Flow (Super Admin)

```
1. Create promo: nama, jenis (bundling/strata/diskon/bonus), status, periode, depo filter
2. Assign SKUs + thresholds (e.g., buy 10 qty of SKU-X → 2 free of SKU-Y)
3. Set strata tiers (qty ranges → % discount)
4. Activate/deactivate (status toggle)
5. Promo visibility in rep catalog (badge + promo price)
6. Promo data in ALL exports (is_bonus, promo_name, promo_ref) — non-negotiable #9/#12
```

## Data Model Requirements (PostgreSQL wim_sfa)

| Legacy (KlikOrder) | WIM Online Equivalent | Notes |
|--------------------|---------------------|------------------|
| SKU produk | Entity | `meta.brand`, `meta.category`, `meta.jenis`, `meta.price` |
| Brand | Company/Entity meta | brand access per depot |
| Promo | — | Custom `wim_promo` table |
| Pesanan (order) | Order + Payload | `meta.checkin_id`, `meta.sales_channel`, `meta.off_route_reason` |
| Order lines | Order Entity lines | `is_bonus`, `promo_name`, `promo_ref`, `promo_type` |
| OTP verification | — | Webhook → WhatsApp gateway (or toggle) |
| Barcode | Order `public_id` → QR | verification_status field |

## Anti-Bypass Design (from business process audit)

1. Out-of-route order requires `wim_visit_plan` row for place+user+date (403 otherwise)
2. Order payload requires `meta.checkin_id` (valid open checkin for driver+place)
3. `meta.sales_channel` = 'app' | 'wa' | 'telepon' | 'admin' — bypass orders tracked
4. No-order anomaly detector: reps >30% no-order rate flagged for admin
5. QR verification loop: rep scans QR before visit checkout finalizes