# Project Charter — WIM Online (Standalone)

## Product, in one sentence

Build a **standalone sales force automation (SFA) platform** on PostgreSQL to replace **KlikOrder** (order management) and **GooVi** (sales visit management) as the single unified operations platform for PT Wahana Inti Mas (Sanqua Group distribution arm). The system is self-contained — external integrations (Fleetbase, Odoo, Warehouse) are optional future sync layers, not dependencies.

## Who it's for

- **Primary:** WIM management / super admins — monitoring, reporting, analytics
- **Daily operators:** ~90+ sales reps (confirmed by live data: 90 sales involved in out-of-route orders alone) — visit check-ins, order taking, store stock tracking
- **Depot admin:** route planning, employee & vehicle management, admin order entry
- **Secondary:** WIM leadership — portfolio analytics, performance dashboards

## What problem does it solve

**Current state (the complaint):** KlikOrder and GooVi are **not synchronized**. Sales data in GooVi is untrustworthy because sales reps can misinput in one system and the data doesn't cross-validate. Key problems:

1. **Data not synced** — GooVi visit data and KlikOrder order data live in separate silos. No cross-validation that a visit's claimed order actually exists in KlikOrder.
2. **No barcode verification** — when a sales rep inputs an order > 0, KlikOrder generates a barcode but there's **no verification** that the barcode's order number matches what was actually realized. Sales can enter a fake order.
3. **Username locked** — KlikOrder doesn't let admins change usernames, forcing a hard guarantee that staff turnover doesn't compromise account access. This is a pain point for managing staff changes.
4. **No promo data in history** — KlikOrder order history shows product details but **no promo or free product data**, making it impossible to audit promotional effectiveness.
5. **Manual coordination** — route planning, stock tracking, orders, and attendance are across two separate tools with no automation bridge.
6. **Out-of-route orders bypassing the system** — live data reveals 1,365 out-of-route orders tracked, with **694 (51%) placed via WA/Telepon** instead of the app. This means reps are actively avoiding the order flow for off-route stores, defeating KlikOrder's tracking.
7. **Username/staff name cannot be changed freely** — technically the API supports PATCH, but the vendor blocks username changes for **billing reasons** (7-day minimum charge per user — changing the name resets the billing cycle). This is a vendor policy lock, not a technical limitation.

## Success metrics

| Metric | Target |
|--------|--------|
| Single source of truth for orders + visits | 100% — every order links to a verified visit event |
| Barcode/order verification | Every order > 0 has a verified check |
| Unified reporting | All visit + order data in one exportable dashboard |
| Route-to-order audit trail | Every route waypoint → visit event → order is traceable |
| Admin overhead reduction | Eliminate dual-system data entry |

## Owner

Reinhart Tanto (Rein) — project oversight, PostgreSQL architecture, data migration, integration.

## Non-goals (explicitly NOT in scope)

- Building a custom mobile app from scratch (mobile web + PWA instead)
- Replacing Sanqua Group's ERP or accounting system
- Real-time GPS fleet tracking beyond visit check-in geofencing
- Route optimization / AI dispatch (OSRM navigation between fixed ordered stops is sufficient)
- E-commerce / direct-to-consumer ordering
- Payment gateway integration (COD is the norm)

## Architecture

```
┌────────────────────────────────────────────────────┐
│              WIM Online (Python http.server)        │
│  Port 8080                                         │
│  ┌─────────────┐  ┌──────────────────────────┐     │
│  │ Static Files│  │ API Handlers              │     │
│  │ /index.html │  │ /api/auth/*               │     │
│  │ /dashboard  │  │ /api/dashboard            │     │
│  │ /visit-card │  │ /api/visits, /api/stores  │     │
│  │ /js/*.js    │  │ /api/absensi, /api/report │     │
│  │ /css/*.css  │  │ /api/visit_plan           │     │
│  └─────────────┘  │ /api/orders, /api/stock   │     │
│                    │ /api/admin/*              │     │
│                    │ /api/promos               │     │
│                    └────────────┬──────────────┘     │
└─────────────────────────────────┼────────────────────┘
                                  │
                                  ▼
                  ┌──────────────────────────────┐
                  │     PostgreSQL (wim_sfa)      │
                  │  ┌────────────────────────┐  │
                  │  │ wim_auth (sessions)     │  │
                  │  │ wim_users               │  │
                  │  │ wim_karyawan            │  │
                  │  │ wim_depo                │  │
                  │  │ wim_pelanggan (stores)  │  │
                  │  │ wim_produk (products)   │  │
                  │  │ wim_visit_plan          │  │
                  │  │ wim_visits              │  │
                  │  │ wim_attendance          │  │
                  │  │ wim_orders              │  │
                  │  │ wim_order_items         │  │
                  │  │ wim_stock_check         │  │
                  │  │ wim_promos              │  │
                  │  │ wim_kendaraan           │  │
                  │  └────────────────────────┘  │
                  └──────────────────────────────┘
```

## Future Sync Layer (NOT in V1 — documented for architecture roadmap)

After V1 stabilizes, a sync layer will be added to connect WIM Online with external systems:

```
WIM Online (PostgreSQL wim_sfa)
    │
    ├── Fleetbase API Sync (future) ──── Orders and stores bidirectionally synced
    │                            POST /v1/orders → Fleetbase (future)
    │                            POST /v1/places → Fleetbase (future)
    │                            GET /v1/orders → import to wim_orders
    │
    ├── Odoo API Sync ────────── Reports, sales data, accounting summaries
    │                            POST /api/odoo/reports
    │                            GET /api/odoo/products
    │
    └── Warehouse API Sync ───── Inventory levels, stock movements
                                 POST /api/warehouse/stock
                                 GET /api/warehouse/inventory
```

See `FUTURE-INTEGRATION.md` for endpoint stubs and format examples.

## Cost / risk motivation

The current GooVi + KlikOrder setup carries recurring costs and operational risks that a standalone system eliminates:

| Item | Current cost | WIM Online |
|------|-------------|------------|
| OTP verification | ~Rp500 per OTP | Zero (self-hosted WhatsApp gateway or toggle) |
| Admin accounts | ~Rp50k/seat/month per user | Zero (self-hosted) |
| Driver module | Additional per-account fee | Included (no per-seat cost) |
| Server SLA | None — no compensation when down | Full uptime control (own infrastructure) |
| Single-session lockout | Support intervention needed | Multi-device tolerance |
| Storage limit (photos) | Limited — auto-deletes after ~3 months | Self-managed storage |
| Two apps licensing | GooVi + KlikOrder separate | Single unified platform |
| Vendor lock-in | API changes, billing policy, feature gates | Full control, open-source stack |