# Scope — WIM Online V1 (Standalone)

## In scope for V1

### Sales Visit Management

| Feature | Implementation | Notes |
|---------|---------------|-------|
| **Sales check-in/check-out** | Geofence events via GPS + backend validation | Rep checks in at store location; 10m proximity check via frontend GPS + server-side distance calc |
| **Depot photo on arrival/departure** | Photo upload on check-in/check-out event | Base64 JPEG compressed to 800px; stored in PostgreSQL as JSON |
| **Visit card (route-based)** | Visit plan with ordered store list | Daily plan from `wim_visit_plan` table; stores ordered by priority |
| **In-route / out-route selection** | Visit plan source flag: `route` / `luar_rute` | Out-route = ad-hoc store added via search, flagged as `luar_rute` |
| **Route presets by day & week** | Visit plan import (4-week cycle, 5-day week) | Import route plans from CSV; `wim_visit_plan` stores entries per user + date |
| **NOO (New Outlet Opening)** | Store creation via `/api/stores` | Lat/lng, name, owner, channel, category, contact person, vehicle type, postal code, NIK, NPWP |
| **10m geofence check-in** | GPS distance check on check-in | Frontend captures coordinates; server validates proximity to store location |
| **OTP verification (optional)** | WhatsApp-based OTP to store owner's WA | External integration — webhook → WhatsApp gateway (future) |
| **Visit reason (no order)** | Visit status `no_order` with reason field | Reason stored in `wim_visits.notes` |
| **3-minute minimum before submit** | Frontend-enforced timer + server-side check | Configurable via `MIN_VISIT_SECONDS` env var |
| **Visit completion enforcement** | Explicit "Selesaikan Kunjungan" button; pending orders survive timeout/crash | Orders must NEVER be silently deleted on incomplete visit (GooVi deletes forgot-checkout visits — a core pain) |
| **Barcode scan from order creation** | Custom QR code on order creation | System generates order reference; QR encodes order ID |
| **Store stock tracking** | `wim_stock_check` table | Per-SKU stock remaining, recorded during visit — **simple one-tap UX required** (current GooVi UX too cramped → reps skip it, stock analysis unusable) |
| **Selfie photo (attendance)** | Photo upload on attendance clock-in | Front/back camera option, stored in PostgreSQL |
| **Additional visit photos (spanduk/flyer)** | Multi-photo upload on visit | Photos stored as JSON array in `wim_visits.photos` |
| **Route map for sales** | Leaflet.js map integration | Show store locations on a map with planned order and visit status |

### Order Management

| Feature | Implementation | Notes |
|---------|---------------|-------|
| **Product catalog** | Product table in PostgreSQL | Import Sanqua product list into `wim_products` table |
| **Brand-based store pages** | Product categories + brands | Filter products by brand (Sanqua, Levonte, Batavia, etc.) |
| **Cart with bundling programs** | Order line items with promo logic | Bundling = auto-add free product when quantity threshold met |
| **Promo visibility** | Product meta: `promo_price`, `promo_period` | Promo data visible to sales rep during order creation |
| **Checkout process** | Order creation (`status: pending`) | Customer = store contact; payload = order items with promo details |
| **Payment (COD)** | Order `payment_method = "cod"` | Default payment method |
| **Barcode generation** | Order `public_id` as QR code | QR encodes order reference for warehouse scanning |
| **Order history** | Order query (`GET /api/orders`) | Full order details including promo/free items |
| **Export to Excel** | API → CSV/XLSX export | Custom export script |
| **Out-of-route ordering** | Order with `off_route_reason` metadata | QR code generation for out-route orders requires reason |
| **Admin order creation** | Direct order creation via API or admin panel | Scan store barcode, same workflow as sales |
| **Packing list** | Route → Order aggregation | Invoice/vehicle-level packing list |
| **Delivery note / invoice PDF** | Custom PDF export per order | Mass PDF download (multiple orders) |

### Super Admin Features — Visit/Attendance

| Feature | Implementation |
|---------|---------------|
| Dashboard statistics | PostgreSQL aggregation queries |
| Visit monitoring (daily/monthly export) | `wim_visits` table + custom report |
| Visit recap per sales member | Visits grouped by user |
| Attendance & photo check-in | `wim_attendance` table with photo |
| Visit gallery | Visit photo browser |
| Activity recap | Visit + attendance event log |
| Store stock tracking | `wim_stock_check` table query |
| Out-of-route orders | Orders with `off_route` flag |
| Route visualization (map) | Leaflet.js with visit waypoints overlay |
| Sales portfolio analysis | User → Stores → Orders aggregation |
| Depot performance analysis | Group by depot → sales metrics |
| Store stock performance (order vs stock) | Order quantity vs stock quantity per store |
| Employee data management | `wim_users` + `wim_karyawan` tables |
| Vehicle data management | `wim_kendaraan` table |
| Route plan import & management | Route import (CSV) + schedule |
| User session tracking | `wim_auth.sessions` table |
| Depot brand access | Depot → brand permission model |

### Super Admin Features — Orders

| Feature | Implementation |
|---------|---------------|
| Order data export | Order API → CSV/XLSX |
| Mass PDF download (surat jalan) | Custom PDF generation per order |
| Admin order entry | Admin panel order creation |
| Promo settings | Custom Promo model |
| Catalog promo download | Product catalog with promo prices |
| **Packing list download** | Route → order aggregation |
| **Promo config self-service** | Custom Promo model (WIM sets programs in-app) |
| **Clean promo/bonus export** | Order lines tagged `is_bonus`, promo name + ref |

## Out of scope for V1

- Real-time GPS fleet tracking (beyond visit check-in)
- Route optimization / AI dispatch (OSRM handles navigation between fixed stops)
- Payroll / commission calculation from sales data
- Accounting / ERP integration
- Direct-to-consumer e-commerce
- Multi-language support (all in Bahasa Indonesia)
- Native mobile app development (mobile web only)
- 3rd-party logistics integration (courier, shipping)

## Future / later

- Commission/incentive auto-calculation from visit + order data
- ERP integration (Xero, Jurnal, or Sanqua's accounting system)
- Mobile app deep-linking / attendance via NFC
- Sales target assignment & tracking
- Real-time stock level sync with warehouse
- Automated WhatsApp order confirmation to store owners
- Photo/video evidence for proof-of-delivery
- **Future sync** — bidirectional sync of orders and stores via sync layer (see FUTURE-INTEGRATION.md)
- **Odoo sync** — export reports and order summaries to Odoo ERP
- **Warehouse sync** — inventory and stock level synchronization with warehouse systems

## Future Integration Architecture

```
WIM Online (standalone app)
    │
    ├── PostgreSQL (wim_sfa database) ─── all current data
    │
    ├── Future Sync Layer ─── orders / stores sync
    ├── Odoo API (future) ─── reports / accounting data
    └── Warehouse API (future) ─── inventory / stock levels
```

All V1 features are **self-contained** in PostgreSQL. External integrations are optional future additions — not dependencies.

## Data Stores

| Database | Schema | Purpose |
|----------|--------|---------|
| PostgreSQL | `wim_sfa` | All V1 data: users, stores, visits, attendance, visit plans, orders, products, promos, stock checks |
| PostgreSQL | `wim_auth` (in `wim_sfa`) | Authentication sessions, rate limiting |
| Browser | `localStorage` | Photo cache, offline fallback |