# KlikOrder Replacement — Implementation Plan (DRAFT)

> Specification for building the shopping cart/order management system in WIM Online.
> After 5 subagents review this, it becomes the build spec for the development phase.

## 1. Order System Architecture

### 1.1 New Backend Endpoints

| Endpoint | Method | Purpose | Auth |
|----------|--------|---------|------|
| `/api/products` | GET | Product catalog (with brand filter, search, categories) | Cookie |
| `/api/products/categories` | GET | Product category tree (Jenis → Kategori) | Cookie |
| `/api/products/promos` | GET | Active promos for a store (with discount calculations) | Cookie |
| `/api/orders` | GET | Order history for current user or store | Cookie |
| `/api/orders` | POST | Create order (cart → wim_orders) | Cookie |
| `/api/orders/{id}/verify-qr` | POST | QR/barcode verification step | Cookie |
| `/api/orders/{id}` | GET | Single order detail with line items | Cookie |
| `/api/admin/orders` | POST | Admin order entry (no checkin required) | Cookie+Admin |
| `/api/admin/promos` | CRUD | Promo management (super admin) | Cookie+Admin |
| `/api/admin/products` | GET/POST | Product management | Cookie+Admin |

### 1.2 Data Storage Strategy

**Order lines** → `wim_order_items` table
- Each line has: entity_uuid (product), quantity, unit_price, meta
- **Custom meta per line:** `{is_bonus: bool, promo_name: string, promo_ref: string, promo_type: string}`

**Order** → `wim_orders` table
- **Custom meta:** `{checkin_id: uuid, sales_channel: "app"|"wa"|"telepon"|"admin", off_route_reason: string, store_uuid: uuid, store_name: string}`

**Promos** → Custom `wim_promo` table
- `id, nama, jenis(bundling|strata|diskon|bonus), status(active|inactive), periode_start, periode_end, depo_uuid, items(JSON: [{sku, min_qty, discount_pct}]), bonus(JSON: [{sku, qty}]), created_at, updated_at`

**Cart** → In-memory (browser sessionStorage or IndexedDB)
- Cart is ephemeral — no server-side "cart" endpoint. Order is created atomically.

### 1.3 Promo Calculation Engine

The promo engine is the most complex logic in the system. Implementation approach:

1. **On cart change** (frontend): Send cart contents to `/api/orders/calculate` (or client-side JS)
2. **Engine evaluates:** For each active promo, check cart against SKU conditions
3. **Bundling**: If cart has ≥ N qty of SKU-X → add M free of SKU-Y
4. **Strata**: If total ≥ Q1 → discount D1%; if ≥ Q2 → D2%
5. **Combined**: Apply the best applicable promo (or sum if configurable)
6. **Result**: Cart with purchased + bonus items, total after discounts

**Implementation decision:** Client-side calculation (JS) is simpler and instant for the 200-user scale. Server-side verification (on order creation) validates no cheating. This avoids a heavy calculation server and keeps field responsiveness.

### 1.4 QR/Barcode Verification

1. Order created → system generates QR encoding `order_uuid`
2. State: `verification_status = 'pending'`
3. Rep scans QR via in-app camera → `POST /api/orders/{id}/verify-qr {qr_code, place_uuid}`
4. Backend validates QR matches order → `verification_status = 'verified'`, records `verified_at`
5. Visit checkout blocked if any active order at store has `status ≠ 'verified'`

**QR generation:** Frontend (qrcode.js library). QR encodes: `wim:{order_uuid}`

## 2. Frontend: New `order.html` Page

### 2.1 Layout

```
┌──────────────────────────────────┐
│ ← Buat Pesanan                  │
│ TOKO BERKAH (PASAR TANAH ABANG) │
│ Timer: 1:45 (visit context)      │
├──────────────────────────────────┤
│ [Semua] [SANQUA] [LEVONTE] [BAT]│  ← Brand tabs
│ [🔍 Cari produk...]              │  ← Search (debounce 300ms)
├──────────────────────────────────┤
│ ┌ PET 550ML ──────────────────┐ │
│ │ SANQUA PET 550ML K24   - + 5│ │  ← Product card in grid
│ │ Rp 15.000        🏷 PROMO   │ │
│ └─────────────────────────────┘ │
│ ┌ PET 220ML ──────────────────┐ │
│ │ SANQUA PET 220ML K24   - + 2│ │
│ │ Rp 10.000                   │ │
│ └─────────────────────────────┘ │
│ ┌ CUP 120ML ───────────────────┐│
│ │ SANQUA CUP 120ML K40   - + 3││
│ │ Rp 8.000                     ││
│ └──────────────────────────────┘│
├──────────────────────────────────┤
│ 📋 Ringkasan Pesanan             │
│ 3 item • 10 karton • Rp 130.000  │
│ 🎁 Bonus: 2 LEVONTE CUP (Gratis) │
│                                  │
│ [🛒 Buat Pesanan]               │
└──────────────────────────────────┘
```

### 2.2 States

| State | UI |
|-------|----|
| Loading products | Skeleton cards (5 gray boxes) |
| No products in category | "Tidak ada produk untuk brand ini" |
| Empty cart | "Keranjang masih kosong" |
| Promo applied | Badge on product + bonus section in summary |
| Checkout success | "✅ Pesanan berhasil!" → QR code display |
| Checkout loading | Spinner on button + "Memproses..." |
| OTP verification modal | (if enabled) "Masukkan kode OTP dari WA" |
| QR scan modal | Camera viewfinder + scan guide |

### 2.3 Cart Logic (JavaScript)

```javascript
class OrderCart {
  constructor() {
    this.items = []; // {entity_uuid, sku, name, qty, unit_price, is_bonus, promo_name}
    this.bonusItems = []; // {sku, name, qty, promo_name, promo_ref}
  }
  
  addProduct(entity_uuid, qty = 1) { /* add/update item */ }
  removeProduct(entity_uuid) { /* remove item */ }
  updateQty(entity_uuid, qty) { /* set qty, 0 = remove */ }
  
  get subtotal() { return this.items.reduce((s, i) => s + i.qty * i.unit_price, 0); }
  get totalQty() { return this.items.reduce((s, i) => s + (i.is_bonus ? 0 : i.qty), 0); }
  get itemCount() { return this.items.filter(i => !i.is_bonus).length; }
  
  runPromoEngine(promos) { /* evaluate all active promos against cart */ }
  toPayload() { /* convert to order creation payload */ }
}
```

## 3. Promo Engine Implementation

### 3.1 Data Model (`wim_promo`)

```sql
CREATE TABLE wim_promo (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nama VARCHAR(255) NOT NULL,
  jenis ENUM('bundling', 'strata', 'diskon', 'bonus') NOT NULL,
  status ENUM('active', 'inactive') DEFAULT 'active',
  periode_start DATE,
  periode_end DATE,
  depo_uuid VARCHAR(64),
  items JSON NOT NULL, /* [{sku, min_qty, discount_pct}] */
  bonus JSON, /* [{sku, qty}] */
  created_at DATETIME DEFAULT NOW(),
  updated_at DATETIME DEFAULT NOW() ON UPDATE NOW()
);
```

### 3.2 Calculation Logic

```
bundling(item): 
  IF cart has ≥ item.min_qty of item.sku
  THEN add bonus items from promo.bonus

strata(item):
  IF cart total_qty ≥ item.min_qty
  THEN discount = item.discount_pct% of all matching SKU prices

diskon(item):
  IF cart has any of item.sku
  THEN unit_price for that SKU = unit_price × (1 - item.discount_pct/100)

bonus(item):
  IF cart has item.sku (any qty)  
  THEN add bonus items from promo.bonus
```

## 4. Integration with Visit Flow

The order flow integrates into the existing visit (§6.2) as a new step between check-in and checkout:

```
Visit flow with order:

1. Open store modal
2. Check-in → timer starts
3. (existing) Take photos
4. (existing) Stock check
5. NEW: Tap "🛒 Buat Pesanan" → opens order.html
6. Browse products → add to cart → promos auto-calculated
7. Review cart → tap "Buat Pesanan"
8. OTP verification (optional, configured per depot)
9. Order created → QR code shown → rep scans to verify
10. Return to visit modal → tap "Selesaikan Kunjungan"
11. Checkout saves visit + order link (meta.checkin_id)
```

## 5. Anti-Bypass Controls

1. **Order requires check-in:** `meta.checkin_id` must reference an open wim_visits row for that user+place
2. **Out-of-route requires plan entry:** `wim_visit_plan` row must exist for place+user+date
3. **QR verification required:** Order status shows `verification_status=pending` until QR scanned
4. **sales_channel tracking:** Every order has meta.sales_channel = 'app' | 'wa' | 'telepon' | 'admin'
5. **No-order anomaly detection:** Admin dashboard widget flags reps with >30% no-order rate

## 6. Export Schema (Non-negotiable #9/#12)

Required in all order exports:

```json
{
  "order": {"id", "date", "store", "rep", "total", "status"},
  "purchased": [
    {"sku": "SQA-PET-550", "name": "SANQUA PET 550ML", "qty": 10, "unit_price": 15000, "total": 150000}
  ],
  "bonus": [
    {"sku": "LEV-220-K24", "name": "LEVONTE CUP 220ML", "qty": 2, 
     "promo_name": "Bundling Beli 10 Gratis 2", "promo_ref": "PROMO-2026-09-001", "promo_type": "bundling"}
  ],
  "promo_summary": {"total_discount": 30000, "total_bonus_value": 30000, 
                    "promos_applied": ["Bundling Beli 10 Gratis 2"]}
}
```