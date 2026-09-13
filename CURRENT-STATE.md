# Current State — WIM Online

> Ledger of project progress. Updated after each feature addition.
> **Source of truth:** `CHANGELOG.md` tracks every change with verification. This file summarises the current state.

## Status: STACK DEPLOYED + QA-VERIFIED (Task A/B/C complete)

**Last updated:** 2026-09-10

### Gates

| Gate | Status | Started | Completed |
|---|---|---|---|
| G0 — Foundation & Infrastructure | ✅ COMPLETE | 2026-09-01 | 2026-09-07 |
| G1 — Core Data Setup | ✅ COMPLETE | 2026-09-07 | 2026-09-07 |
| G2 — Route & Visit Workflow | ✅ COMPLETE | 2026-09-07 | 2026-09-08 |
| G3 — Order Management | ✅ COMPLETE | 2026-09-09 | 2026-09-09 |
| G4 — Reporting & Admin | ✅ COMPLETE | 2026-09-08 | 2026-09-08 (admin panel + Task A/B/C: 2026-09-09/10) |
| G5 — Go-Live & Migration | 🔴 NOT STARTED | — | — |

> **G3 correction (2026-09-10):** Orders/checkout were implemented and QA-fixed on 2026-09-09
> (CHANGELOG #20–21), so G3 is **DONE**, not "NOT STARTED" as an earlier version of this
> doc claimed. G3 was mis-labelled after the builder agent paused mid-work.

### Deployment (current, verified live 2026-09-10)

| Service | CT | IP:Port | Runs | Status |
|---|---|---|---|---|
| PostgreSQL (`wim_sfa`, 31 tables) | 110 `wim-db` | 192.168.6.110:5432 | PG 17.11 | ✅ running 16h+ |
| Middleware (`serve.py`) | 111 `wim-mid` | 192.168.6.111:8000 | python http.server | ✅ running; login/session verified |
| Sales app (nginx static) | 112 `wim-sales` | 192.168.6.112:80 | nginx, `/api/*`→wim-mid | ✅ serves 200, proxy 401(auth) |
| Admin panel (`admin-server.py`) | 113 `wim-admin` | 192.168.6.113:8001 | python http.server → middleware | ✅ running; login verified |

- All on Proxmox host **192.168.6.101** (`marketing-pc-ai`). Host reachable via SSH key
  `~/.ssh/id_ed25519_hermes` from the Hermes gateway.
- **Admin panel is a thin client of the middleware** — it authenticates via
  `POST /api/auth/login` and queries `/api/*` with a privileged Bearer API key
  (`ADMIN_API_KEY`). No direct DB connection.

### Auth System

Sales reps and admins log in with **email + password**, verified server-side via session cookies.

| Component | Details |
|---|---|
| **Database** | `wim_users`, `wim_sessions` in PostgreSQL `wim_sfa` |
| **Auth endpoints** | `POST /api/auth/login`, `GET /api/auth/session`, `POST /api/auth/logout` |
| **Password hashing** | **bcrypt** (not SHA256) — `bcrypt.hashpw/checkpw` in `serve.py` |
| **Session lifetime** | 7 days |
| **API-key auth** | Middleware also accepts a Bearer API key (`wim_api_keys`) for external apps |
| **RBAC roles** | `super_admin`, `head_of_sales`, `regional_manager`, `depo_admin`, `sales` |
| **Admin login** | `reinharttanto@gmail.com` (super_admin, password known to Rein) |

### Test Accounts (dev, seeded)

| Email | Password | Role | Note |
|---|---|---|---|
| `andi@wim.sales` | `sandi123` | sales | Primary test rep (depot 1, route plans, orders) |
| `admin@wim.sales` | `sandi123` | depo_admin | Seed-created depo admin (all dummy users share `sandi123`) |

### Core Data (dummy dataset seeded)

| Item | Count | Notes |
|---|---|---|
| Users | 9 | 1 super_admin, 1 depo_admin, 7 sales reps |
| Depots | 4 | Jakarta Pusat/Barat/Timur + Gudang Pusat (50m radius) |
| Stores | 21 | Realistic Jakarta retail/MH/Horeka/Institutional mix |
| Store contacts | 41 | 1:many per store |
| Products | 9 | SANQUA, LEVONTE, BATAVIA |
| Visit plans | 33 | route + luar_rute sources |
| Promos | 4 | with conditions + rewards |
| Stock checks | 27 | per-store per-SKU |
| Orders | ~6 | various statuses |

### Sales Frontend Pages (served by wim-sales)

| Page | Features |
|---|---|
| `index.html` | Login (bcrypt, session cookie) |
| `dashboard.html` | KPIs, today's plan, store list, session redirect |
| `absensi.html` | Clock in/out with GPS + photo, depot geofence check |
| `visit-card.html` | In-Rute/Luar-Rute filter, 180s min-visit timer, check-in/out, multi-photo, stock, order, no-order reason |
| `noo.html` | New Outlet Opening, 14+ fields, GPS, channel→kategori cascade (GT/MT/Horeka/Institutional) |
| `order.html` | Shopping cart, product catalog, promo/strata, checkout → order |
| `report.html` | KPIs, period selector, JSON+CSV export |
| `route-map.html` | Leaflet/OSM store map (blue=route, green=visited, orange=luar rute) |

### Admin Panel Pages (served by wim-admin)

| Page | Data source (via middleware) |
|---|---|
| `dashboard.html` | Global KPIs (staff, plans, visits, orders, attendance) |
| `team.html` | Sales team list (+ per-rep attendance) |
| `visits.html` | Cross-rep visits w/ date filter |
| `orders.html` | Order list (store + rep names) |
| `attendance.html` | Cross-rep attendance |
| `users.html` | User management (list, role filter, create — super_admin only) |
| `products.html` | Product & price management |
| `depots.html` | **NEW (2026-09-10)** Depot list w/ lat/lng/radius |
| `today-plan.html` | **NEW (2026-09-10)** Today's full visit-plan detail w/ filters |
| `route-map.html` | Today's plan + stores on Leaflet map, color-coded by status |

### Auth Flow

```
Browser                         wim-sales(nginx)                wim-mid(:8000)          wim-db(:5432)
  │                                  │                              │                        │
  │ POST /api/auth/login             │  proxy_pass /api/*           │                        │
  │ {email, password}                ───────────────────────────────►  Verify bcrypt        │
  │ ◄── Set-Cookie: wim_session=xxx  │                            ◄── [user, role, id]      │
  │ GET /api/stores                  │                              │                        │
  │ Cookie: wim_session=xxx          ───────────────────────────────►  Validate session +   │
  │ ◄── [stores data]                │        (or Bearer API key)   │   query PG             │
                                     │                              ────────────────────►   │
                                     │                              ◄── [rows]               │
                                     │ ◄── [stores data]                                     │
```

### Git History (recent)

| Commit | Description |
|---|---|
| `HEAD` | Task C completion: depots.html + today-plan.html + /api/admin/depots bugfix (2026-09-10) |
| `cab35bf` | Task C: ex-Fleetbase admin endpoints + users/products/route-map pages (2026-09-09) |
| `90bbe6f` | Final sales-rep QA: PG subquery fix, report order count |
| `d4c7a87` | Admin-panel QA: dashboard KPIs, orders/visits join enrichment, UUID validation |
| `6a2e15a` | Task A/B: sales webapp + admin panel as containers, middleware-backed |
| `e7769a8` | WIM Online SFA platform — standalone PostgreSQL, containerized plan |

### MVP / Pilot Status

Deployment plan (`DEPLOYMENT.md`) defines a **1-month sales pilot** with one real sales
rep on the production server (`wim.sqa.web.id`, separate `wim_sfa_prod` DB) after core
functions are done. Core functions are now done + QA-verified; G5 (go-live + migration)
is not yet started.