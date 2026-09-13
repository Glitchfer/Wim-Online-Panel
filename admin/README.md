# WIM Online Admin Panel

## Architecture Overview

The admin panel is a **separate webapp** (not an extension of the sales app) for desktop-first management by Depo Admins and Super Admins. It shares the same MySQL database as `serve.py` but runs on its own port (8081).

### Why separate, not extending serve.py?

*This recommendation is validated by the Systems Architect analysis (see ADMIN-PANEL-ARCHITECTURE-ANALYSIS.md).*

| Consideration | Separate server | Extend serve.py |
|--------------|----------------|-----------------|
| Desktop-first CSS | ✅ Clean separation | ❌ Would clash with mobile-first sales CSS |
| Auth isolation | ✅ Separate in-memory TOKENS | ⚠️ Would share, could escalate |
| Admin bug crashes sales app | ✅ No risk | ❌ Same single-threaded process |
| Deployment independence | ✅ Restart admin alone | ❌ Restart restarts both |
| Port separation for NPMplus | ✅ 8081 admin / 8080 sales | ❌ Same port, path-based |
| Aggregation query load | ✅ Separate pool/memory | ❌ Blocks sales rep requests |
| Code maintainability | ✅ Clean module | ❌ 941-line monolith grows worse |

**Cost:** One more Python process to manage. Negligible vs. running 8 Docker containers on the same LXC.

### Role Hierarchy (V1 — 3 levels)

*The expert analysis concluded 5 levels add disproportionate complexity for V1. See §3 in ADMIN-PANEL-ARCHITECTURE-ANALYSIS.md for full reasoning.*

```
Super Admin (global)
  ├── sees ALL depots, ALL teams, ALL data
  ├── can manage users, promos, settings, exports
  └── Admin panel access retained
       │
       └── Depo Admin (depot-scoped)
             ├── sees their depot team's data only
             ├── cannot manage users/promos/settings
             ├── can export depot-scoped reports
             │
             └── Sales Staff (own data)
                   └── no admin panel access
```

**V2 additions** (when needed — see roadmap at bottom):
- **Regional Sales Manager** → `scope='multi_depot'` on the same `depo_admin` role
- **Head of Sales** → `scope='global'` + restricted settings (boolean on role)

### Database Tables

All in the PostgreSQL `wim_sfa` database on LXC 106, port 3306.

#### Core PostgreSQL tables (shared with sales app)

| Table | Role in Admin Panel |
|-------|---------------------|
| `users` | Auth source (bcrypt passwords) + user identity |
| `places` | Store names, addresses, GPS coordinates |
| `entities` | Product catalog (SKU, price, brand) |
| `orders` | Order records with items in meta |
| `payloads` | (legacy) FK reference |
| `contacts` | Store contact info (not yet used) |
| `drivers` | Sales rep driver records |
| `companies` | SanQua company context |

#### Custom wim_* tables (admin panel's primary data)

| Table | Rows | What it stores | Admin panel page |
|-------|------|----------------|-----------------|
| `wim_attendance` | 1 | Clock-in/out times, photos, GPS, geofence_status, depot_id | Attendance |
| `wim_depots` | 3 (+1 future) | Depot name, address, GPS + radius | Dashboard filters |
| `wim_depot_stores` | 5 | Depot→Store mapping for scoped queries | (backend) |
| `wim_depot_team` | 1 | Sales rep → depot assignments | Team |
| `wim_visits` | 10 | Store check-in/out, GPS, duration, photos, notes | Visits |
| `wim_visit_plan` | 10 | Daily store assignments per user | Dashboard |
| `wim_admin_roles` | 2 | Admin user roles + permissions | (auth) |
| `wim_admin_depot_access` | 4 | Which depots each admin can access | (RBAC) |
| `wim_audit_log` | 0 | Admin action audit trail | (system) |
| `wim_promo*` | 3+4+4 | Promo engine (header, conditions, rewards) | (future) |
| `wim_stock_check` | 1 | Per-store inventory counts | (future) |

### Technology Stack

| Layer | Current (V1 prototype) | Recommended for V2 | Reason |
|-------|----------------------|-------------------|--------|
| Backend | Python `http.server` | **FastAPI** (port 8090) | Current works for prototype; FastAPI adds async, Pydantic validation, auto-docs |
| Auth | wim_users (bcrypt) + in-memory session cache | Same — keep PostgreSQL as source of truth | Already proven in sales app |
| DB driver | PyMySQL | asyncmy (async) for FastAPI | Same DB, async connection |
| Frontend | Vanilla HTML/CSS/JS | Same pattern | No framework needed for table-heavy admin UI |
| Exports | CSV (planned) | openpyxl (XLSX) + FPDF | Mature Python libs |

### Design Decisions (with reasoning)

1. **Separate server on port 8081** — Not FastAPI yet in the prototype, but the codebase is modular enough to swap the backend framework later. The frontend stays identical regardless of backend.

2. **3-level V1 hierarchy** — The expert analysis (30+ pages) demonstrated that 5 levels add UNION-chain SQL queries, 5× nav variations, and zero V1 payoff. Super Admin = can see everything + manage settings. Depo Admin = sees their depot only. Sales Staff = existing app only. Regional Manager = Depo Admin with `multi_depot` scope in V2.

3. **Depot-scoped RBAC via `wim_admin_depot_access`** — Instead of a complex role hierarchy table, each admin has a flat list of depot IDs they can access. Super admin has all depots. Depo admin has 1-2. Queries filter by `WHERE d.id IN (admin_depot_ids)` — simple, correct, auditable.

4. **All data in one MySQL DB** — No read replicas needed for V1 (<10 concurrent admins, <5 tables, <100 rows per table). If the admin panel grows to serve 50+ concurrent admins with heavy aggregation, a read replica for the MySQL instance is a one-day infrastructure change.

5. **Auth stays on wim_users table** — No separate admin password store. `wim_admin_roles` just marks which users are admins. One account = both sales rep (in sales app) and admin (in admin panel). The security consultant confirmed this is the correct approach.

6. **No wim_auth.users SHA256 problem** — The security consultant found that a `wim_auth.users` table with SHA256 password hashes existed in some code path. This table is NOT used by `serve.py`'s login flow (which uses Fleetbase's bcrypt). The column should be dropped if it exists.

### Audit Logging

Every admin action logged to `wim_audit_log`:

```json
{"user_id": 6, "action": "login", "entity_type": "session", "ip_address": "192.168.x.x"}
{"user_id": 1, "action": "view_report", "entity_type": "attendance", "details": {"date": "2026-09-09", "filter": "depot_1"}}
```

Implemented in V2 when the FastAPI migration happens; V1 prototype uses basic Python logging.

### Data Access Flow

```
Admin Browser
    ↓
NPMplus (admin.sales.sqa.web.id → LXC 106:8081)
    ↓
admin-server.py
    ├── reads session token from Authorization header
    ├── resolves Fleetbase user + wim_admin_role
    ├── resolves depot scope from wim_admin_depot_access
    └── executes query with scoped WHERE clause
    
    SELECT ... FROM wim_visits v
    JOIN wim_depot_stores ds ON v.place_uuid = ds.place_uuid  -- or wim_depot_team via user
    WHERE ds.depot_id IN (1)  ← scoped by admin's depot access
```

Store→Depot linking is via `wim_depot_stores` (place_uuid → depot_id). Sales rep→Depot linking is via `wim_depot_team` (user_id → depot_id).

## Admin Panel Pages (V1 Prototype — 6 pages)

| Page | File | What it shows | Priority (UX consultant) |
|------|------|--------------|--------------------------|
| Login | `index.html` | Auth against Fleetbase users + admin role check | P1 |
| Dashboard | `dashboard.html` | 6 KPI cards: staff, attendance, visits, orders, geofence %, completion % + today's plan + visit table + team status | P1 |
| Team | `team.html` | Per-member status: clock-in/out, geofence badge, depot, visit count | P1 |
| Visits | `visits.html` | Visit log with date filter, sales, store, check-in/out, duration, route type | P1 |
| Orders | `orders.html` | Order history with date range, promo data, grand total row | P1 |
| Attendance | `attendance.html` | Attendance log + geofence compliance breakdown (depo vs outside) | P1 |

### Future screens (P2 — per UX consultant)

- Stock Alert dashboard
- NOO Pending Approval queue
- Promo Effectiveness report
- Visit Quality map (Leaflet)
- Regional KPI Scorecard (multi-depot comparison)
- Scheduled email digests

### API Endpoints (V1)

All are `GET` except login (POST). All require `Authorization: Bearer <token>`.

| Endpoint | Returns | RBAC |
|----------|---------|------|
| `POST /api/admin/login` | `{token, user}` | Any Fleetbase user with wim_admin_roles entry |
| `GET /api/admin/session` | `{user}` | Any admin |
| `GET /api/admin/dashboard` | KPI object (staff, attendance, visits, orders, geofence %, completion %) | Depo admin+ (depot-scoped) |
| `GET /api/admin/team` | `{members[], total}` with per-member status | Depo admin+ (depot-scoped) |
| `GET /api/admin/visits?date=` | `{visits[], total}` with duration, status, GPS | Depo admin+ (depot-scoped) |
| `GET /api/admin/orders?from=&to=` | `{orders[], total}` with promo data, grand total | Depo admin+ (depot-scoped) |
| `GET /api/admin/attendance?date=` | `{records[], total}` with geofence_status, depot_name | Depo admin+ (depot-scoped) |
| `GET /api/admin/depots` | `{depots[]}` with GPS | Any admin |
| `GET /api/admin/today-plan` | `{plans[], total}` per-user store assignments | Depo admin+ (depot-scoped) |

### Export Formats (MVP)

| Format | Priority | Implementation |
|--------|----------|---------------|
| CSV | P1 | Currently all visible data has CSV link (same-origin fetch + download) |
| XLSX | P2 | Multi-sheet workbook for RSM reviews |
| PDF | P2 | Executive report (HoS board materials) |
| Email digest | P3 | Scheduled cron delivery |

### UX Principles (per UX consultant analysis)

- Role-based routing (not toggling) — depot admin never sees "all depots" button
- Indonesia-first formatting: DD-MM-YYYY, Rp separators, 24h time
- Clickable drill-down on every KPI card
- Skeleton loading for table data (already implemented with loading states)
- No horizontal scroll at 1366px (already tested at this width)
- Desktop-first layout (nav bar on top, not side hamburger)

## Deployment

### Files (on LXC 106)

```
/opt/wim-admin/
├── admin-server.py      # Backend server (port 8081)
├── index.html           # Login page
├── dashboard.html       # Dashboard with KPI cards
├── team.html            # Team table
├── visits.html          # Visit log with date filter
├── orders.html          # Order history with date range
├── attendance.html      # Attendance + geofence report
├── README.md            # This file
└── logs/                # Server logs (auto-created)
```

### Starting / Stopping

```bash
# Start
nohup python3 -u /opt/admin/admin-server.py </dev/null >/tmp/admin-srv.log 2>&1 &

# Stop
pkill -f admin-server.py

# Check status
ss -tlnp | grep 8081
```

Deployment chain (same as sales app): `local → scp → jump 100.81.100.196 → 192.168.6.101 → pct push 106 → LXC 106`

### NPMplus Configuration (for public access)

To make the admin panel publicly accessible:

1. Add a new Proxy Host in NPMplus:
   - **Domain:** `admin.sales.sqa.web.id` (recommended subdomain)
   - **Scheme:** `http`
   - **Forward IP:** `192.168.6.223` (LXC LAN IP)
   - **Forward Port:** `8081`
   - **SSL:** Let's Encrypt (new cert)
   - **Websocket Support:** No

## Security Model (per security consultant analysis)

| Concern | Design |
|---------|--------|
| Auth source | Fleetbase `users` table (bcrypt). No separate admin password store. |
| Session storage | In-memory dict (V1). Acceptable for <10 concurrent admins. |
| RBAC | Server-enforced: every endpoint queries `wim_admin_depot_access` + `wim_depot_stores` to scope data. **No client-side filtering.** |
| Audit trail | `wim_audit_log` table records all admin actions (login, reports, exports, user management). |
| Secrets | MySQL password in env vars (same pattern as serve.py). Will move to `.env` file in V2. |
| Data isolation | Single DB, no read replicas for V1. Added when admin panel reaches 50+ concurrent users. |
| Fleetbase proxy | Admin panel reads Fleetbase native tables via direct MySQL. Read-only for V1; writes only through Fleetbase API proxy in V2. |

## Version History

### 2026-09-09 — V1 Prototype
- Created admin panel as separate webapp on port 8081
- 6 pages: login, dashboard, team, visits, orders, attendance
- RBAC (V1 3-level): super_admin, depo_admin, sales_staff (via wim_admin_roles + wim_admin_depot_access)
- All queries scoped by user's depot(s) via wim_depot_stores + wim_depot_team
- Shared auth with Fleetbase users table (bcrypt)
- Geofence compliance tracking on attendance page (in_depot / outside)
- Order history with promo data display
- Depot→Store linking table (wim_depot_stores) for scoped admin queries
- Audit log table (wim_audit_log) for action tracking

### Roadmap
- **V2:** Migrate to FastAPI on port 8090. Add Regional Sales Manager (multi_depot scope). Add CSV/XLSX exports. Add audit log integration.
- **V3:** Add Stock Alert dashboard + NOO approval queue + Promo Effectiveness report. Add scheduled email digests.
- **V4:** Shop accounts (online ordering without sales rep visit). Full multi-depot comparison dashboards.