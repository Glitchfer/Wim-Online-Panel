# WIM Online — REST API Reference

> **Purpose:** Complete API contract for the WIM Online platform. Every table in
> `wim_sfa` (PostgreSQL) is exposed through a consistent REST surface so all data
> can be pulled, filtered, and written programmatically.
> **Transport:** JSON over HTTP(S). Same-origin cookie session for app users; Bearer
> token for external consumers/integrations.
> **Conventions:** camelCase in JSON, snake_case in DB. Timestamps ISO-8601.
> **Companion doc:** `DATABASE-MAPPING.md` (PostgreSQL schema this API wraps).

> **Implementation status (2026-09-10):** This document is the **design contract** and
> includes aspirational/planned endpoints. The **currently implemented** surface (in
> `frontend/serve.py`, verified) is: `/api/auth/login|logout|session`,
> `/api/absensi`, `/api/analytics/orders`, `/api/api-keys`, `/api/config`,
> `/api/dashboard`, `/api/depots`, `/api/log`, `/api/logs`, `/api/orders`
> (+ `/orders/calculate|detail|status|verify`), `/api/products` (+ `/products/promos`),
> `/api/report`, `/api/stock`, `/api/stores` (+ `/stores/all|orders`), `/api/sync/queue`,
> `/api/users`, `/api/visit_plan`, `/api/visits` (+ `/visits/active`).
> Endpoints **not yet implemented** (documented as design targets): `/api/export/*`,
> `/api/analytics/visits|stock|salespeople|depots|products|promo`, `/api/contacts`,
> `/api/photos`, `/api/store/relations`, `/api/admin/*` (handled by `admin-server.py`
> as a proxy, not `serve.py`), and all `/api/sync/fleetbase/*` + `/api/sync/odoo/*`
> (future integration). See `CHANGELOG.md` for verified-state tracking.

---

## Table of Contents

1. [Conventions](#1-conventions)
2. [Authentication](#2-authentication)
3. [Domain Table](#3-domain-table)
4. [Auth & Users API](#4-auth--users-api)
5. [Stores & NOO API](#5-stores--noo-api)
6. [Products & Pricing API](#6-products--pricing-api)
7. [Depot & Territory API](#7-depot--territory-api)
8. [Visit Plan API](#8-visit-plan-api)
9. [Visits API](#9-visits-api)
10. [Attendance API](#10-attendance-api)
11. [Orders API](#11-orders-api)
12. [Stock API](#12-stock-api)
13. [Promo API](#13-promo-api)
14. [Reporting & Analytics API](#14-reporting--analytics-api)
15. [Admin & RBAC API](#15-admin--rbac-api)
16. [Sync & Integration API](#16-sync--integration-api)
17. [Audit & Config API](#17-audit--config-api)
18. [Response & Error Standards](#18-response--error-standards)
19. [Future Integration (Fleetbase + Order-app → Odoo)](#19-future-integration-fleetbase--order-app--odoo)

---

## 1. Conventions

| Rule | Standard |
|------|----------|
| **Base URL** | `/api/*` (same-origin), `/external/*` (Bearer-token integrations) |
| **Auth** | Cookie `wim_session` (app). Bearer `Authorization: Bearer <key>` (integrations) |
| **Content-Type** | `application/json` for bodies and responses |
| **Pagination** | `?page=N&per_page=N&cursor=<uuid>` (page indexed from 1, default 1/50) |
| **Filtering** | `?field=value&field__op=value` (e.g. `?date__gte=2026-09-01`) |
| **Sorting** | `?sort=field&dir=asc\|desc` |
| **Field selection** | `?fields=id,name,price` (projection) |
| **Timestamps** | ISO-8601 with offset, UTC storage |
| **Money** | Integer minor units preferred in payloads; float allowed internally |
| **Geo** | `lat`/`lng` as decimals, `radius` meters |

### Common Query Operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `__eq` | equals | `?status__eq=pending` |
| `__ne` | not equals | `?status__ne=cancelled` |
| `__in` | in list | `?status__in=pending,shipped` |
| `__gte` / `__lte` | range | `?total__gte=50000` |
| `__like` | substring | `?name__like=TOKO` |
| `__null` | is null | `?father_id__null=true` |

---

## 2. Authentication

### 2.1 Login (app)
`POST /api/auth/login`
```json
{ "email": "andi@wim.sales", "password": "sandi123" }
```
**200:** sets `Set-Cookie: wim_session=<token>` + body:
```json
{ "token": "<session>", "user": { "id": 6, "uuid": "...", "name": "Andi Sales", "email": "andi@wim.sales", "role": "sales" } }
```
**401** wrong credentials, **429** rate limited, **400** bad body.

### 2.2 Session validate
`GET /api/auth/session` → `200 {user: {...}}` or `401`.

### 2.3 Logout
`POST /api/auth/logout` → clears cookie, `200 {success: true}`.

### 2.4 External consumer (integration)
`POST /external/auth` with `{api_key}` → `{token, scope}` (JWT, TTL configurable).
Scopes from `wim_api_keys`: `orders:read/write`, `stores:read`, `stock:read`, `sync:write`, `report:read`.

---

## 3. Domain Table

| Domain | Core Tables | Primary Ownership |
|--------|-------------|-------------------|
| Auth & Users | `wim_users`, `wim_user_meta`, `wim_sessions`, `wim_api_keys` | Identity/access |
| Stores & NOO | `wim_stores`, `wim_store_contacts`, `wim_store_photos`, `wim_store_relations` | Customer outlets |
| Products | `wim_products`, `wim_product_prices` | Catalog |
| Depot | `wim_depots`, `wim_depot_stores`, `wim_depot_products` | Territory |
| Visit Plan | `wim_visit_plan`, `wim_visit_plan_templates`, `wim_visit_plan_template_stores` | Scheduling |
| Visits | `wim_visits`, `wim_visit_photos` | Field activity |
| Attendance | `wim_attendance` | Time tracking |
| Orders | `wim_orders`, `wim_order_items`, `wim_order_status_log` | Sales |
| Stock | `wim_stock_check` | In-store inventory |
| Promo | `wim_promo`, `wim_promo_conditions`, `wim_promo_rewards`, `wim_promo_assignments` | Promotions |
| Reports | computed (no tables) | Analytics |
| Admin/RBAC | `wim_admin_depot_access` | Scoping |
| Sync | `wim_sync_queue`, `wim_sync_log` | Integration |
| Audit/Config | `wim_audit_log`, `wim_app_config` | System |

---

## 4. Auth & Users API

### Users
| Method | Path | Purpose | Access |
|--------|------|---------|--------|
| GET | `/api/users` | List users (filter by role/depot) | admin |
| GET | `/api/users/:id` | Get one user + meta | admin, self |
| POST | `/api/users` | Create user (bcrypt hash) | super_admin |
| PATCH | `/api/users/:id` | Update profile/role/depot | super_admin, self |
| DELETE | `/api/users/:id` | Soft-delete (status=inactive) | super_admin |

**GET /api/users?role=sales&depot_id=1**
```json
{ "data": [ { "id": 6, "uuid": "...", "name": "Andi Sales", "email": "andi@wim.sales", "role": "sales", "jenis_sales": "SPG", "depot_id": 1, "status": "active" } ], "total": 1, "page": 1 }
```

**POST /api/users**
```json
{ "email": "juan@wim.sales", "name": "Juan Rep", "password": "temp123", "role": "sales", "jenis_sales": "TO", "depot_id": 1 }
```

### User Meta
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/users/:id/meta` | Extended profile |
| PATCH | `/api/users/:id/meta` | Update jenis_sales, vehicle, NIK, NPWP |

### API Keys
| Method | Path | Purpose | Access |
|--------|------|---------|--------|
| GET | `/api/api-keys` | List consumer keys | super_admin |
| POST | `/api/api-keys` | Issue key + scope | super_admin |
| DELETE | `/api/api-keys/:id` | Revoke | super_admin |

---

## 5. Stores & NOO API

### Stores
| Method | Path | Purpose | Access |
|--------|------|---------|--------|
| GET | `/api/stores` | Today's visit plan stores (rep-scoped) | sales |
| GET | `/api/stores/all` | Search all stores `?q=&channel=&category=` | sales, admin |
| GET | `/api/stores/:uuid` | One store full detail | sales, admin |
| POST | `/api/stores` | **Create store / NOO** | sales |
| PATCH | `/api/stores/:uuid` | Update store | admin |
| DELETE | `/api/stores/:uuid` | Soft-delete (status=closed) | admin |

**POST /api/stores (NOO creation)** — atomic: creates store + owner contact + optional photo.
```json
{
  "name": "TOKO NOO BARU", "owner_name": "Budi Santoso", "phone": "6281234567890",
  "address": "Jl. Test No. 1", "city": "Jakarta", "province": "DKI Jakarta",
  "kecamatan": "Tanah Abang", "kelurahan": "Bendungan", "kode_pos": "10210",
  "latitude": -6.2088, "longitude": 106.8456,
  "channel": "GT", "category": "Retail Kecil", "kendaraan": "Motor",
  "nik": "3273010101900001", "npwp": "99.999.999.9-999.999", "npwp_name": "Budi Santoso",
  "contacts": [ { "name": "Budi", "phone": "6281234567890", "role": "owner", "is_primary": true } ],
  "photo": "data:image/jpeg;base64,...",
  "source": "luar_rute"
}
```
**201:** `{ "uuid": "...", "id": 42, "place_uuid": "..." }`

### Contacts
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/stores/:uuid/contacts` | List store contacts |
| POST | `/api/stores/:uuid/contacts` | Add contact |
| PATCH | `/api/contacts/:id` | Update contact |
| DELETE | `/api/contacts/:id` | Remove |

### Photos
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/stores/:uuid/photos` | List store photos |
| POST | `/api/stores/:uuid/photos` | Add photo `{photo_data, description, photo_type}` |
| DELETE | `/api/photos/:id` | Remove photo |

### Relations
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/stores/:uuid/relations` | Chains / same-owner groups |
| POST | `/api/stores/:uuid/relations` | Link related store |

---

## 6. Products & Pricing API

| Method | Path | Purpose | Access |
|--------|------|---------|--------|
| GET | `/api/products` | Catalog (filter brand/category/q) | sales, admin |
| GET | `/api/products/:sku` | One product | sales, admin |
| POST | `/api/products` | Create product | admin |
| PATCH | `/api/products/:sku` | Update product/price | admin |
| DELETE | `/api/products/:sku` | Soft-delete | admin |
| GET | `/api/products/:sku/prices` | Price history | admin |
| POST | `/api/products/:sku/prices` | Record price change | admin |

**GET /api/products?brand=Sanqua&category=Botol**
```json
{ "data": [ { "uuid": "...", "sku": "SQA-550-K24", "name": "SANQUA PET 550ML", "price": 5000, "brand": "Sanqua", "category": "Botol", "unit": "karton" } ], "total": 8 }
```

---

## 7. Depot & Territory API

| Method | Path | Purpose | Access |
|--------|------|---------|--------|
| GET | `/api/depots` | List depots + geofence | sales, admin |
| GET | `/api/depots/:id` | One depot | sales, admin |
| POST | `/api/depots` | Create depot | super_admin |
| PATCH | `/api/depots/:id` | Update geo/radius | super_admin |
| GET | `/api/depots/:id/stores` | Stores in a depot | admin |
| POST | `/api/depots/:id/stores` | Assign store to depot | admin |
| DELETE | `/api/depots/:id/stores/:store_uuid` | Unassign store | admin |
| GET | `/api/depots/:id/products` | Products available at depot | admin |
| POST | `/api/depots/:id/products` | Add depot product access | admin |
| DELETE | `/api/depots/:id/products/:product_id` | Remove access | admin |

---

## 8. Visit Plan API

| Method | Path | Purpose | Access |
|--------|------|---------|--------|
| GET | `/api/visit_plan` | Today's plan (rep) / by date `?date=`. Admin: `?user_id=&depot_id=` | sales, admin |
| POST | `/api/visit_plan` | Add store to plan `{place_uuid, date, source}` | sales |
| PATCH | `/api/visit_plan/:id` | Update order/source/status | admin |
| DELETE | `/api/visit_plan/:id` | Remove from plan | admin, self |
| GET | `/api/visit_plan/templates` | Route templates | admin |
| POST | `/api/visit_plan/templates` | Create template | admin |
| POST | `/api/visit_plan/templates/:id/apply` | Apply template to a date | admin |

**POST /api/visit_plan**
```json
{ "place_uuid": "550e8400-...", "visit_date": "2026-09-09", "source": "luar_rute" }
```
**201:** `{ "id": 18, "plan_id": 18 }`

---

## 9. Visits API

| Method | Path | Purpose | Access |
|--------|------|---------|--------|
| GET | `/api/visits` | Visits by date/user | sales, admin |
| GET | `/api/visits/active` | Active (open) visit | sales |
| GET | `/api/visits/:id` | One visit + photos | sales, admin |
| POST | `/api/visits` | Check-in / check-out | sales |
| GET | `/api/visits/:id/photos` | Visit photos with description | sales, admin |
| POST | `/api/visits/:id/photos` | Attach photo to visit | sales |

**POST /api/visits (check-in)**
```json
{ "action": "checkin", "place_uuid": "...", "place_name": "TOKO BERKAH", "lat": -6.2088, "lng": 106.8456, "source": "route" }
```
**200:** `{ "visit": { "id": 15, "checkin_at": "2026-09-09T08:30:00+07:00", "status": "checkin" } }`

**POST /api/visits (check-out)**
```json
{ "action": "checkout", "place_uuid": "...", "photos": [{"url":"data:...","desc":"Spanduk"}], "notes": "Stok masih penuh", "durationSeconds": 240, "status": "visited" }
```

---

## 10. Attendance API

| Method | Path | Purpose | Access |
|--------|------|---------|--------|
| GET | `/api/absensi` | Attendance `?date=&user_id=` | sales, admin |
| POST | `/api/absensi` | Clock in / out | sales |
| PATCH | `/api/absensi/:id` | Correct record (admin) | admin |

**POST /api/absensi (clock-in)**
```json
{ "action": "clock_in", "date": "2026-09-09", "time": "08:00", "photo": "data:...", "lat": -6.2572, "lng": 106.7649 }
```
**POST /api/absensi (clock-out)**
```json
{ "action": "clock_out", "date": "2026-09-09", "time": "17:00", "photo": "data:...", "duration": "9j 0m" }
```

---

## 11. Orders API

| Method | Path | Purpose | Access |
|--------|------|---------|--------|
| GET | `/api/orders` | Order list (filter status/store/date) | sales, admin |
| GET | `/api/orders/detail?id=` | One order + items + promo | sales, admin |
| POST | `/api/orders` | **Create order** | sales |
| POST | `/api/orders/calculate` | Cart totals + promo preview | sales |
| POST | `/api/orders/verify` | Verify order (QR/barcode) | admin, warehouse |
| PATCH | `/api/orders/:id` | Update status/notes | admin |
| POST | `/api/orders/:id/status` | Status change + log | admin, warehouse |

**POST /api/orders**
```json
{
  "store_uuid": "...", "visit_id": 15, "source": "route",
  "items": [ { "sku": "SQA-550-K24", "qty": 10, "unit_price": 5000 } ],
  "promos_applied": [], "payment_method": "cod", "notes": ""
}
```
**201:**
```json
{ "id": 31, "uuid": "...", "order_ref": "WIM-20260909-031", "total": 50000, "status": "pending" }
```

**POST /api/orders/calculate** (promo engine preview)
```json
{ "store_uuid": "...", "items": [ {"sku":"SQA-550-K24","qty":30} ] }
```
```json
{ "subtotal": 150000, "discount": 5000, "free_items": [{"sku":"SQA-220-K24","qty":1,"promo_ref":"BND-SQA-30"}], "total": 145000 }
```

---

## 12. Stock API

| Method | Path | Purpose | Access |
|--------|------|---------|--------|
| GET | `/api/stock` | Stock checks `?place_uuid=&sku=&from=&to=` | sales, admin |
| POST | `/api/stock` | Record stock check | sales |
| GET | `/api/stock/last` | Last stock per SKU per store | sales, admin |

**POST /api/stock**
```json
{ "place_uuid": "...", "visit_id": 15, "sku": "SQA-550-K24", "qty": 12, "previous_stock": 8, "last_order_qty": 10 }
```

---

## 13. Promo API

| Method | Path | Purpose | Access |
|--------|------|---------|--------|
| GET | `/api/promos` | Active promos (for cart engine) | sales |
| GET | `/api/promos/all` | All promos (admin management) | admin |
| GET | `/api/promos/:id` | One promo + conditions/rewards | admin |
| POST | `/api/promos` | Create promo | admin |
| PATCH | `/api/promos/:id` | Update promo/status | admin |
| DELETE | `/api/promos/:id` | Soft-delete (status=archived) | admin |
| POST | `/api/promos/:id/conditions` | Add condition | admin |
| POST | `/api/promos/:id/rewards` | Add reward | admin |
| POST | `/api/promos/:id/assign` | Assign to depot/store/channel | admin |

**POST /api/promos**
```json
{
  "promo_ref": "BND-SQA-30", "nama": "Mix 30 karton SANQUA", "jenis": "bundling",
  "stackable": false, "priority": 10, "periode_start": "2026-09-01", "periode_end": "2026-09-30",
  "min_transaction_amount": 0, "max_discount_amount": null,
  "conditions": [ {"condition_type": "min_qty", "condition_value": "30", "condition_product_id": 1} ],
  "rewards": [ {"reward_type": "free_product", "reward_value": "1", "reward_sku_ref": "SQA-220-K24", "reward_qty": 1} ]
}
```

---

## 14. Reporting & Analytics API

| Method | Path | Purpose | Access |
|--------|------|---------|--------|
| GET | `/api/report` | Rep's report `?period=daily\|weekly\|monthly` | sales, admin |
| GET | `/api/analytics/visits` | Visit aggregated `?depot=&user=&from=&to=` | admin |
| GET | `/api/analytics/orders` | Order aggregates (omset, count, AOV) | admin |
| GET | `/api/analytics/stock` | Stock vs order analysis | admin |
| GET | `/api/analytics/salespeople` | Rep performance ranking | admin |
| GET | `/api/analytics/depots` | Depot performance | admin |
| GET | `/api/analytics/products` | Top products | admin |
| GET | `/api/analytics/promo` | Promo effectiveness | admin |
| GET | `/api/export/orders.csv` | CSV export (respects filters) | admin |
| GET | `/api/export/orders.xlsx` | Excel export | admin |
| GET | `/api/export/visits.csv` | Visit export | admin |

**GET /api/analytics/orders?from=2026-09-01&to=2026-09-09**
```json
{ "summary": { "total_omset": 4316118114, "total_orders": 28959, "avg_order_value": 149043, "unique_stores": 21298 },
  "by_depot": [], "by_salesperson": [], "by_day": [] }
```

---

## 15. Admin & RBAC API

| Method | Path | Purpose | Access |
|--------|------|---------|--------|
| GET | `/api/admin/dashboard` | Admin home stats | admin |
| GET | `/api/admin/team` | Sales reps + perf | depo_admin+ |
| POST | `/api/admin/depot-access` | Grant depot to admin | super_admin |
| DELETE | `/api/admin/depot-access/:id` | Revoke | super_admin |
| GET | `/api/admin/audit` | Audit log (filter) | super_admin |
| PATCH | `/api/admin/config` | App config keys | super_admin |

---

## 16. Sync & Integration API

### Queue (internal worker)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/sync/queue?status=pending` | Worker picks up jobs |
| POST | `/api/sync/queue` | Enqueue job `{entity_type, entity_id, action, target}` |
| PATCH | `/api/sync/queue/:id` | Update status/error |
| POST | `/api/sync/queue/:id/retry` | Retry a failed job |

### External pull points
All data is pullable via the standard endpoints above authenticated as an external
consumer (Bearer key). No special sync endpoints needed for internal reads — the API
itself is the pull surface.

---

## 17. Audit & Config API

| Method | Path | Purpose | Access |
|--------|------|---------|--------|
| GET | `/api/audit` | Query audit log `?user=&action=&entity=&from=&to=` | super_admin |
| GET | `/api/config` | Read public config | auth |
| GET | `/api/config/all` | Read all config | super_admin |
| PATCH | `/api/config/:key` | Set config value | super_admin |

**PATCH /api/config/min_visit_seconds**
```json
{ "value": 180, "description": "Min visit duration in seconds" }
```

---

## 18. Response & Error Standards

### Success envelope (list)
```json
{ "data": [...], "total": n, "page": 1, "per_page": 50, "next_cursor": "..." }
```

### Success envelope (single)
```json
{ "data": { ... } }
```

### Error envelope
```json
{ "success": false, "error": { "code": "...", "message": "...", "details": {}, "request_id": "..." } }
```

| HTTP | Code | Meaning |
|------|------|---------|
| 200 | `OK` | Success |
| 201 | `CREATED` | Resource created |
| 400 | `INVALID_PAYLOAD` | Bad request/validation |
| 401 | `UNAUTHENTICATED` | Missing/invalid credentials |
| 403 | `FORBIDDEN` | No permission/scope |
| 404 | `NOT_FOUND` | Resource missing |
| 409 | `CONFLICT` | Duplicate / state conflict |
| 422 | `UNPROCESSABLE` | Valid JSON, wrong values |
| 429 | `RATE_LIMITED` | Too many requests |
| 500 | `SERVER_ERROR` | Unhandled failure |

---

## 19. Future Integration (Fleetbase + Order-app → Odoo)

WIM Online is **fully standalone**. Fleetbase and the Odoo order-taking app are
**optional future integrations** reached only through the sync layer — never a
runtime dependency.

```
        ┌─────────────────────────────────────────────┐
        │              WIM Online (wim_sfa)             │
        │   PK / canonical source of all SFA data       │
        └───────────────┬─────────────────────────────┘
                        │ wim_sync_queue (worker)
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
┌───────────────┐ ┌───────────────┐ ┌────────────────┐
│ Fleetbase      │ │ Order-taking  │ │ (future)       │
│ (delivery/     │ │ app → Odoo    │ │ other ERP/WMS  │
│  driver/maps)  │ │ (sales/accnt) │ │                │
└───────────────┘ └───────────────┘ └────────────────┘
```

### 19.1 Sync queue table behavior
Every cross-system write enqueues a row in `wim_sync_queue`:
`{entity_type, entity_id, action, target: 'fleetbase'|'odoo', payload, status}`.

### 19.2 Fleetbase (delivery & driver tracking — future)
Used for order delivery, driver GPS, route mapping. Bi-directional:
- **Push:** new orders → Fleetbase, new stores → Fleetbase places
- **Pull:** delivery status updates → WIM order status

| Endpoint | Direction |
|----------|-----------|
| `POST /api/sync/fleetbase/orders/push` | WIM → Fleetbase |
| `POST /api/sync/fleetbase/orders/pull` | Fleetbase → WIM |
| `POST /api/sync/fleetbase/stores/push` | WIM → Fleetbase |
| `POST /api/sync/fleetbase/stores/pull` | Fleetbase → WIM |
| `GET /api/sync/fleetbase/status` | Sync health |

### 19.3 Order-taking app → Odoo (future)
An external order-taking application collects orders and posts them to Odoo ERP.
WIM Online exchanges data with both:
- **Pull into WIM:** orders captured by the order-app → stored as `wim_orders`
- **Push to Odoo:** WIM orders + completed sales → Odoo invoices/reporting

| Endpoint | Direction |
|----------|-----------|
| `POST /api/sync/odoo/orders/inbound` | Order-app → WIM (create orders) |
| `POST /api/sync/odoo/orders/push` | WIM → Odoo (invoice) |
| `POST /api/sync/odoo/reports/push` | WIM → Odoo (reporting) |
| `GET /api/sync/odoo/products` | Odoo → WIM (catalog refresh) |

**Odoo inbound order payload (order-app → WIM):**
```json
{
  "store_uuid": "",             // matched/created store
  "customer_phone": "6281234567890",
  "source": "odoo_order_app",
  "items": [ {"sku": "SQA-550-K24", "qty": 20} ],
  "total": 100000, "payment_method": "cod",
  "external_ref": "ODOO-SO-45001"          // idempotency key
}
```

### 19.4 Idempotency & reliability
- Every sync job has a deterministic `external_ref`/`wim_order_id` used as the idempotency key — re-pushing the same payload never duplicates.
- Failures go to `wim_sync_queue.status='failed'` with `error` + `retry_count`, reprocessed by a cron worker.
- Credentials per integration in environment: `FLEETBASE_*`, `ODOO_*` (never in DB, never in git).

---

## 20. Endpoint Status (current build)

| Group | Implemented | Missing (designed) |
|-------|-------------|--------------------|
| Auth/Users | login, session, logout | users CRUD, api-keys, user-meta |
| Stores | today's plan, search, store orders | **POST /api/stores (NOO)**, contacts, photos, relations |
| Products | list | **POST/PATCH/DELETE**, prices history |
| Depots | list | CRUD, depot stores/products |
| Visit plan | GET today, add, PATCH proxy | templates |
| Visits | get, check-in/out, active | photos, detail |
| Attendance | get, clock in/out | PATCH (admin correct) |
| Orders | get, create, calc, verify, detail | **status log**, PATCH |
| Stock | get, post | last |
| Promos | get active | full admin CRUD |
| Reports | rep report | analytics set, exports |
| Sync | queue enqueue | worker endpoints, external auth |

> **Legend:** ✅ live in `serve.py`; ⬜ designed in this doc, implement next; 🔶 partially implemented.