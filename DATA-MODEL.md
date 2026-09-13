# Data Model — WIM Online (Standalone PostgreSQL)

## Core Entities

### Organization
- WIM as a single organization
- Contains all depots, users, karyawan, stores, orders

### Depot (custom or via Company segmentation)
- Physical distribution center (e.g., Depo Tapos, Depo Bintaro)
- Linked to users, drivers, vehicles, routes
- **Depots may be split by program type** (TO vs SPC same city = separate depots) so promo programs don't clash
- **Per-depot brand access** — a depot's sales reps only see brands/products the depot is authorized for

### User (wim_users)
- Super admin — full admin panel access
- Depot admin — limited to their depot's data
- Sales rep — authenticated via API, no admin panel

### Roles (GooVi/KlikOrder taxonomy)
- **Role types:** Sales, Driver, Helper, Kepala Depo, Kepala Gudang, Admin Depo, Admin Wilayah
- **Jenis sales** (sub-type filter): SPG, TO (Trade Outlet), Motoris, SMD, SPC, Kanvaser
- All personnel have wim_users accounts; order-writing permissions limited to roles that place orders

### Karyawan / Sales Rep (wim_karyawan)
- Each sales rep is a karyawan record
- Linked to a wim_users account
- Assigned to a wim_depo
- GPS position submitted on check-in

### Store / Pelanggan (wim_pelanggan)
- **Store** (customer location) — lat/lng, address, city, country
- Attributes: name, owner name, channel, category, contact person, vehicle type, postal code, NIK, NPWP

### Contact (stored in wim_pelanggan fields)
- Store owner / PIC
- Part of the store record (owner_name, owner_phone fields)
- Phone number (for OTP via WhatsApp)

### Geofence (server-side calculation)
- **Geofence** — distance-based check-in radius (10m)
- Computed server-side via PostgreSQL `ST_DistanceSphere(lat1, lng1, lat2, lng2)`
- Store lat/lng from wim_pelanggan

### Visit Plan (wim_visit_plan)
- Daily visit plan
- Stores in visit order
- Assigned to a sales rep + optional vehicle
- 4-week cycle, 5 days/week — 20 route presets per depot

### Order (wim_orders)
| Field | Value |
|---|---|
| `customer_uuid` | Contact UUID (store owner) |
| `customer_type` | `"contact"` |
| `payload_uuid` | Payload UUID (contains entities + dropoff place) |
| `status` | `"pending"` / `"on-hold"` / `"no-order"` / `"completed"` / `"cancelled"` |
| `type` | `"delivery"` |
| `meta.payment_method` | `"cod"` |
| `meta.off_route` | `true` / `false` |
| `meta.off_route_reason` | String (required if off_route) |
| `meta.sales_rep` | Driver public_id |
| `meta.store` | Place public_id |

### Order Items (wim_order_items)
- Container for order line items
- `order_id` references wim_orders
- Each item: product_id, qty, unit_price, is_bonus, promo_ref

### Product (wim_produk)
- Order line item (product)
- Fields: `name`, `sku`, `price`, `quantity`, `meta.promo_type`, `meta.free_quantity`

### Vehicle (wim_kendaraan)
- Depot vehicle
- Fields: code, plate number, type, cubic capacity, load type

### Visit Events (tracked in wim_visits)
- Created when sales rep checks in/out at a store
- Captures: user_id, store_id, checkin_at, checkout_at, gps_coordinates

## Key Relationships

```
WIM Organization
  ├── wim_depo (physical depot)
  │   ├── wim_users (depot admin)
  │   ├── wim_karyawan (sales rep)
  │   │   ├── wim_visit_plan (daily visit plan)
  │   │   │   └── wim_pelanggan (store)
  │   │   │       └── Geofence (distance calc from lat/lng)
  │   │   ├── wim_orders (via user_id)
  │   │   └── wim_visits (check-in/out)
  │   ├── wim_kendaraan (vehicle)
  │   │   └── wim_visit_plan (delivery assignment)
  │   └── wim_pelanggan (stores in this depot)
  ├── wim_orders
  │   └── wim_order_items
  │       └── wim_produk (product catalog)
  └── wim_produk (product catalog)
```

## Product catalog

Products (wim_produk catalog items) will be imported from Sanqua's current product list:

| Attribute | Example |
|---|---|
| `name` | Aqua 600ml |
| `sku` | AQ-600 |
| `price` | 4000 |
| `meta.brand` | Sanqua |
| `meta.category` | Galon / Botol / Kardus |
| `promo_price` | 3800 (if promo active) |
| `promo_period_start` | ISO timestamp |
| `promo_period_end` | ISO timestamp |

## Promo / bundling model

Bundling programs (e.g., "mix 30 carton get free 1 220ml") — stored as metadata on relevant entities:

```json
{
  "bundling": {
    "type": "mix_free",
    "trigger_quantity": 30,
    "free_sku": "AQ-220",
    "free_quantity": 1,
    "description": "Mix 30 carton get free 1 220ml"
  }
}
```

Since KlikOrder's promo system is not self-service (KlikOrder sets promos), WIM Online stores promos in the `wim_promos` table and allows WIM admins to manage them directly via the admin panel.