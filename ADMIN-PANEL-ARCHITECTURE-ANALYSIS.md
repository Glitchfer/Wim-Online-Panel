# WIM Online Admin Panel — Systems Architecture Analysis

**Author:** Hermes Agent (Systems Architect Consultant)
**Date:** 2026-09-09
**Context:** WIM Online standalone deployment on LXC 106, PostgreSQL, custom `serve.py` frontend server

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Decision 1: Separate Webapp vs Extend serve.py](#2-decision-1-separate-webapp-vs-extend-servepy)
3. [Decision 2: 3-Level vs 5-Level Role Hierarchy](#3-decision-2-3-level-vs-5-level-role-hierarchy)
4. [Decision 3: Backend Tech Stack](#4-decision-3-backend-tech-stack)
5. [Decision 4: RBAC Table Design & Data Access Control](#5-decision-4-rbac-table-design--data-access-control)
6. [Decision 5: Database Integration Points](#6-decision-5-database-integration-points)
7. [Recommended Architecture Blueprint](#7-recommended-architecture-blueprint)
8. [Migration Path](#8-migration-path)

---

## 1. Executive Summary

**Recommendation: Build a separate admin webapp on a modern Python framework (FastAPI), but share the same MySQL database as `serve.py`, same auth (session cookie), and same LXC host. Do NOT extend `serve.py` or build a 5-level hierarchy in V1.**

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| Separate app vs extend serve.py | **Separate app** (FastAPI on port 8090) | `serve.py` is a fragile `http.server` monolith; admin has fundamentally different workload (read-heavy analytics, heavy aggregation queries, no geofence/tracking) |
| 3-level vs 5-level hierarchy | **3-level for V1** (Super Admin → Depo Admin → Sales) | 5-level adds custom admin-wilayah mappings, per-user RBAC joins, and complex data scoping with zero clear benefit in V1. Head of Sales = Super Admin, Regional Manager = Depo Admin for V1 |
| Backend tech stack | **FastAPI** (Python) for the admin API, **pure HTML/CSS/JS** frontend (same pattern as current frontend) | Matches existing Python ecosystem, avoids introducing PHP/Laravel, reuses existing MySQL connection pool patterns, stays lightweight |
| RBAC model | **Flat RBAC with `wim_admin_roles` table** + scope column (depot_scoped, region_scoped, global) | Avoids complex permission matrix; admin scopes are hierarchical (can see their own data + all children's data) |
| Database integration | **PostgreSQL direct queries to wim_* tables**; wim_* tables are the admin panel's primary data source | Fleetbase is the store/product/order backbone; admin analytics come from wim_* data warehouse queries |

---

## 2. Decision 1: Separate Webapp vs Extend serve.py

### Current State of serve.py

`serve.py` is a 941-line `http.server`-based monolith handling:
- Auth (login/session/logout against wim_auth.users / wim_users)
- direct PostgreSQL queries (psycopg2)
- Absensi CRUD (`wim_attendance`)
- Visit plan + visits (`wim_visit_plan`, `wim_visits`)
- Stock check (`wim_stock_check`)
- Per-user dashboard + report endpoints
- Server-side logging
- Connection pool management (MySQL)

It's a **single-threaded** `ThreadingHTTPServer` with a 20-connection MySQL pool — adequate for ~20-50 concurrent sales reps, but **not designed for admin analytics workloads**.

### Option A: Extend serve.py

**Approach:** Add more `/api/admin/*` routes to the existing `do_GET`/`do_POST` routing block, adding aggregation queries.

**Pros:**
- Zero additional infrastructure — same port, same process, same auth
- Reuses existing MySQL connection pool, `get_mysql()`/`ret_mysql()` pattern
- Reuses existing session auth (`_require_auth()`)
- Simplest possible deployment — one Python process to manage
- Frontend already has admin.html — just needs real data instead of the current shell

**Cons:**
- **Fragile base:** `http.server.SimpleHTTPRequestHandler` already has a complex routing pattern (dozens of URL matches in `do_GET`/`do_POST` dispatch chains). Adding 10-15 admin endpoints makes this unwieldy
- **Single-process bottleneck:** Admin queries (aggregation across depots, date-range rollups, cross-salesperson comparisons) are **heavy** — they could block the request handler thread pool during full-table scans, degrading sales rep response times
- **No structured framework:** No dependency injection, no middleware for role checking, no query parameter validation — everything is hand-parsed with `parse_qs(urlparse(self.path).query)`
- **Role checking is ad-hoc:** Currently `admin.html` just calls `Session.checkOrRedirect()` with a role check of `wim_user_role === 'admin'` in JS — no server-side enforcement
- **Security surface:** Mixing sales-rep endpoints (geofence, tracking, photo uploads) with admin endpoints (aggregate exports, user management, promo management) in one process creates unnecessary risk
- **Code maintainability:** Adding admin endpoint patterns to an already 941-line file with no test coverage is tech debt

### Option B: Separate Admin Webapp (Recommended)

**Approach:** FastAPI on port 8090 with its own MySQL connection pool, sharing the same database. Behind the same NPMplus reverse proxy on `/admin/*` or a subdomain.

**Pros:**
- **Clean separation of concerns:** Sales endpoints on port 8080, admin endpoints on port 8090 — different load profiles, different scaling needs
- **Right tool for aggregation:** FastAPI has proper async SQL drivers (asyncmy/aiomysql), Pydantic request models, dependency injection for auth/role checks
- **No cross-contamination:** A buggy admin aggregation query can't crash the sales app
- **Independent scaling:** Admin panel can be resource-limited differently (more CPU for aggregation, less memory)
- **Proper role middleware:** FastAPI dependencies let you build a `require_role("super_admin")` decorator that checks the session and returns 403 cleanly
- **Auto-generated OpenAPI docs:** `/docs` endpoint for free API documentation
- **Future-proof:** When the admin panel grows (promo management, bulk imports, analytics dashboards), FastAPI handles it gracefully. serve.py doesn't need rewrites
- **Frontend stays the same pattern:** Static HTML/CSS/JS served by the admin server, same auth cookie — minimal frontend changes

**Cons:**
- **One more process to manage:** Startup, monitoring, restart — though the LXC already runs 8 Docker containers, one more Python process is negligible
- **Port management:** Need to avoid conflicts (8080 is serve.py, 8090 is admin, 5432 is PostgreSQL). NPMplus reverse proxy handles this transparently
- **Auth duplication:** Session validation code must be duplicated or shared — but it's ~30 lines of Python, trivial to copy
- **Slightly higher learning curve:** Team needs to understand FastAPI patterns vs `do_GET` dispatch

| Criterion | Extend serve.py | Separate admin app |
|-----------|----------------|-------------------|
| Lines of code added | ~300-400 in monolithic file | ~200 in clean module |
| Risk to sales app uptime | HIGH (admin query blocks sales) | NONE (separate process) |
| Role enforcement | Ad-hoc if/else | Framework-native deps |
| Aggregation performance | Thread-blocked | Async I/O |
| Maintainability | Poor | Good |
| Time to implement | 3-4 hours | 4-6 hours |
| Deployment complexity | Zero (same process) | Slightly more (new service) |

**Verdict:** Separate admin app on FastAPI. The cost is one more systemd service to manage; the benefit is **production-grade isolation, maintainability, and async aggregation performance.**

---

## 3. Decision 2: 3-Level vs 5-Level Role Hierarchy

### The Proposed Hierarchy

```
Super Admin / Head of Sales — all data, all settings
    └── Regional Sales Manager — data for assigned depots/teams
         └── Depo Admin — data for their depot's sales team
              └── Sales Staff — own data only (existing mobile app users)
```

### What Exists Today

| Level | System Representation | Notes |
|-------|----------------------|-------|
| Super Admin | wim_admin_roles role `super_admin` | Full access to all admin pages + Fleetbase Console |
| Sales Staff | wim_admin_roles role `sales_staff` | Per-user data only, no admin pages |
| Depot Admin | Currently does NOT exist as a separate role | The admin.html page shows all data (no depot scoping) |

### The Case for 3 Levels (V1 Recommendation)

**V1 hierarchy:**
1. **Super Admin** — Full access (data, settings, promos, user management, exports, Fleetbase Console)
2. **Depot Admin** — Depot-scoped access (can see/manage their depot's sales reps, visit data, orders, reports)
3. **Sales Staff** — Own data only (cannot access admin panel at all)

The middle layers (Regional Sales Manager, Head of Sales) are **not needed in V1** because:

**Why Head of Sales = Super Admin in V1:**
- The Head of Sales role in GooVi (`Admin_Wilayah`) is an operational supervisor — they need to see ALL depots, ALL sales reps, and ALL reports. That's functionally identical to Super Admin
- Adding a separate "Head of Sales" role that is "almost super admin but without settings access" means building a granular permission matrix that V1 doesn't need. If the Head of Sales shouldn't change system settings, that's a UI restriction, not a role
- **Recommendation:** Head of Sales = Super Admin account. If they need restricted settings access, add a `settings_access` boolean on the role, not a whole new role tier

**Why Regional Sales Manager = Depo Admin in V1:**
- A Regional Manager oversees multiple depots. A Depo Admin oversees one depot
- The data access pattern is identical: "see everything in my depots" — just at a different cardinality
- The wim_admin_roles supports super_admin, head_of_sales, regional_manager, depo_admin. Introducing a `regional_manager` type means either:
  - Adding a new type to the Fleetbase users table (crosses into Fleetbase core territory — NOT recommended)
  - Building a completely separate `wim_auth.user_roles` table (which is what we do for Depot Admin too)

**The complexity cost of 5 levels:**

| Factor | 3 Levels | 5 Levels |
|--------|----------|----------|
| Role tables | 1 (`wim_admin_roles`) + no hierarchy table | 1 role table + 1 hierarchy/scope table |
| Access queries | `WHERE user_id IN (depot_user_ids)` | `WHERE user_id IN (depot_user_ids UNION region_user_ids UNION all_ids)` |
| Admin panel nav logic | 2-3 nav items vary by role | 5+ nav items vary by role |
| API decorators | `require_role(['super_admin','depot_admin'])` | `require_role_and_scope(...)` 
| SQL complexity | Simple | UNION chains with scope resolution |
| User management | Create/edit/delete sales + depots | Create/edit/delete at 3 management levels |
| Testing | Straightforward | Multiplied by scope permutations |

**The argument FOR 5 levels (and why it doesn't hold in V1):**
- "But GooVi has Admin Wilayah!" — Yes, but in GooVi, Admin Wilayah = can see everything. GooVi's real role distinction is between KP (Kepala) who can manage users and staff who can only see reports. That's 2 tiers, not 5
- "We need different reporting dashboards for each level" — A dashboard is a UI concern, not a role concern. All three V1 levels see the same admin panel; data is just filtered at the query level by `depot_id`
- "Regional Manager needs different data than Depot Admin" — They need MORE depots' data, not DIFFERENT data. That's a scope parameter, not a role parameter

**Recommendation:**
- **V1: 3 Levels** — Super Admin, Depot Admin, Sales Staff
- **V2: Add a `scope` column** to the admin roles table (range: `single_depot`, `multi_depot`, `global`). Regional Manager = Depot Admin with `scope='multi_depot'`
- **V3: Add granular permissions** if needed (can_manage_users, can_manage_promos, can_export)
- Head of Sales uses Super Admin in V1; if settings restriction is needed, `scope='global'` with a boolean `settings_access=False`

---

## 4. Decision 3: Backend Tech Stack

### Recommended Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Admin API server** | FastAPI (Python 3.13) | Same Python ecosystem as serve.py, async I/O for aggregation, Pydantic models for validation, auto-docs |
| **DB driver** | `asyncmy` + `pymysql` (fallback sync) | asyncmy for async queries, pymysql for compatibility with existing patterns |
| **Auth** | Same session cookie (`wim_session`) | Reuse existing `wim_auth.sessions` table; FastAPI dependency reads cookie → checks session → returns user |
| **Admin DB** | PostgreSQL `wim_sfa` database | PostgreSQL `wim_sfa` database; all wim_* tables in single schema |
| **Admin frontend** | Static HTML/CSS/JS (same pattern as current frontend) | Matches existing codebase, no build step, served by FastAPI's `StaticFiles` |
| **Session cache** | In-memory dict + MySQL (same as serve.py) | For V1, keep it simple. V2 can add Redis |
| **Background tasks** | FastAPI `BackgroundTasks` or simple thread | For heavy export generation (CSV/PDF) |
| **Export library** | `openpyxl` (Excel) + `reportlab`/`FPDF` (PDF) | Mature Python libs, no external service needed |

### Why NOT these alternatives:

| Rejected Option | Reason |
|----------------|--------|
| **Laravel plugin inside Fleetbase** | Requires forking Fleetbase core, PHP knowledge, Composer, Eloquent. Overkill for a standalone admin panel |
| **Flask** | Flask lacks async, Pydantic integration, and auto-docs. FastAPI is strictly better for this use case |
| **Node.js/Express** | Different ecosystem than existing Python stack; no shared DB auth code |
| **Next.js** | Full JS framework with build step, SSR, bundling — unneeded for an admin panel that's mostly tables and forms |
| **Django** | Too heavy for an analytics-focused panel. Django ORM is powerful but adds migration complexity |
| **React/Vue SPA** | Overkill for admin panel. Static HTML with fetch() calls keeps things simple and maintainable. The current frontend pattern works fine |

### serve.py stays unchanged

serve.py continues serving sales-rep endpoints on port 8080. The admin panel on port 8090 is a **separate, independent process** with its own codebase.

---

## 5. Decision 4: RBAC Table Design & Data Access Control

### Table Design

```sql
-- ========================================
-- Admin roles for the WIM admin panel
-- Separate from Fleetbase's native roles
-- ========================================

-- Users who can access the admin panel
CREATE TABLE wim_admin_users (
    user_id INT PRIMARY KEY,                -- FK to fleetbase.users.id
    role ENUM('super_admin', 'depot_admin') NOT NULL DEFAULT 'depot_admin',
    scope ENUM('single_depot', 'multi_depot', 'global') NOT NULL DEFAULT 'single_depot',
    settings_access BOOLEAN NOT NULL DEFAULT FALSE,  -- can change system settings
    user_management BOOLEAN NOT NULL DEFAULT FALSE,  -- can create/edit/delete users
    promo_management BOOLEAN NOT NULL DEFAULT FALSE, -- can create/edit promos
    export_access BOOLEAN NOT NULL DEFAULT TRUE,     -- can export data
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Admin-depot assignments (which depots an admin can see)
CREATE TABLE wim_admin_depot_access (
    user_id INT NOT NULL,                   -- FK to users.id
    depot_id INT NOT NULL,                  -- FK to wim_depots.id
    PRIMARY KEY (user_id, depot_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (depot_id) REFERENCES wim_depots(id) ON DELETE CASCADE
);
```

### V1 Default Configurations

| Role | scope | settings_access | user_management | promo_management | export_access | Depot access |
|------|-------|-----------------|-----------------|-----------------|---------------|--------------|
| **Super Admin** | `global` | TRUE | TRUE | TRUE | TRUE | All depots (unused, scope=global) |
| **Depot Admin** | `single_depot` | FALSE | FALSE | FALSE | TRUE | Assigned depot(s) |
| **Regional Manager** (V2) | `multi_depot` | FALSE | FALSE | FALSE | TRUE | Selected depots |
| **Head of Sales** (V2) | `global` | FALSE | TRUE | TRUE | TRUE | All depots |

### Data Access Enforcement Pattern

In FastAPI, a middleware/dependency checks the session, then resolves the admin's access scope:

```python
# Pseudocode — FastAPI dependency
async def get_admin_user(request: Request):
    session_id = request.cookies.get("wim_session")
    if not session_id: raise HTTPException(401)
    
    # Reuse same session validation logic as serve.py
    user = await validate_session(session_id)
    if not user: raise HTTPException(401)
    
    # Check if this user is an admin
    admin = await db.fetch_one(
        "SELECT * FROM wim_admin_users WHERE user_id = :uid",
        {"uid": user["id"]}
    )
    if not admin: raise HTTPException(403, "Not an admin")
    
    # If scope is single/multi_depot, resolve which depots
    if admin["scope"] in ("single_depot", "multi_depot"):
        depot_ids = await db.fetch_all(
            "SELECT depot_id FROM wim_admin_depot_access WHERE user_id = :uid",
            {"uid": user["id"]}
        )
        admin["depot_ids"] = [r["depot_id"] for r in depot_ids]
    else:
        admin["depot_ids"] = None  # global = no filter
    
    return admin

# Then in endpoint:
@app.get("/api/admin/reports/visits")
async def visit_report(admin: dict = Depends(get_admin_user)):
    if admin["scope"] == "global":
        query = "SELECT * FROM wim_visits WHERE ..."
    else:
        # Only sales reps in this admin's depots
        query = """
            SELECT v.* FROM wim_visits v
            JOIN wim_visit_plan vp ON v.place_uuid = vp.place_uuid
            JOIN wim_depots d ON ...  -- depot linkage via user/driver
            WHERE d.id IN :depot_ids
        """
```

### How SCALE works (the critical query pattern)

Depot-scoped data access is the hardest problem. The key is linking `wim_visits` records back to depots:

**Route:** Sales Rep → Driver → Depot (via driver's depot assignment, or via the `wim_visit_plan` → store's depot)

```sql
-- If sales reps are linked to depots:
SELECT v.* FROM wim_visits v
JOIN drivers d ON d.user_uuid = (SELECT uuid FROM users WHERE id = v.user_id)
WHERE d.depot_id IN (:admin_depot_ids)

-- If stores are linked to depots (simpler):
-- Store's depot is known from `wim_depot_stores` mapping:
SELECT v.* FROM wim_visits v
JOIN wim_depot_stores ds ON ds.place_uuid = v.place_uuid
WHERE ds.depot_id IN (:admin_depot_ids)
```

**For V1, recommend a `wim_depot_stores` table** (linking places to depots) and a `depot_id` column on `drivers` — this makes depot-scoped admin queries a simple JOIN, not a multi-hop graph traversal:

```sql
CREATE TABLE wim_depot_stores (
    depot_id INT NOT NULL,
    place_uuid CHAR(36) NOT NULL,
    PRIMARY KEY (depot_id, place_uuid),
    FOREIGN KEY (depot_id) REFERENCES wim_depots(id),
    FOREIGN KEY (place_uuid) REFERENCES places(uuid)
);

-- Add depot_id to drivers (Fleetbase native table — use tinker or raw ALTER)
ALTER TABLE drivers ADD COLUMN depot_id INT NULL;
-- Or use a custom wim_driver_depot table
CREATE TABLE wim_driver_depot (
    driver_id INT NOT NULL,
    depot_id INT NOT NULL,
    PRIMARY KEY (driver_id, depot_id)
);
```

### API route guard strategy for V1

| Admin Area | Super Admin | Depot Admin | Sales Staff |
|-----------|-------------|-------------|-------------|
| `/api/admin/dashboard` | ✅ Global totals | ✅ Depot-scoped | ❌ 403 |
| `/api/admin/reports/visits` | ✅ All visits | ✅ Their depot visits only | ❌ |
| `/api/admin/reports/attendance` | ✅ All attendance | ✅ Depot attendance only | ❌ |
| `/api/admin/reports/orders` | ✅ All orders | ✅ Depot orders only | ❌ |
| `/api/admin/reports/stock` | ✅ All stock checks | ✅ Depot stock only | ❌ |
| `/api/admin/reports/promo` | ✅ All promo performance | ✅ Depot promo only | ❌ |
| `/api/admin/reports/routes` | ✅ All route completion | ✅ Depot routes only | ❌ |
| `/api/admin/export` | ✅ Global export | ✅ Depot-scoped export | ❌ |
| `/api/admin/users` | ✅ CRUD all users | ➡ Read only (depot reps) | ❌ |
| `/api/admin/settings` | ✅ Full | ❌ | ❌ |
| `/api/admin/promos` | ✅ Manage promos | ➡ Read promos (V2) | ❌ |

---

## 6. Decision 5: Database Integration Points

### What the Admin Panel Reads FROM Fleetbase (not wim_*)

| Data | Source | Why It Matters |
|------|--------|---------------|
| **Stores** | PostgreSQL `wim_pelanggan` | Store names, addresses, coordinates, type, phone. Admin needs to browse/manage stores |
| **Products** | PostgreSQL `wim_produk` | Product catalog with SKU, price, brand. Admin needs to manage products and prices |
| **Orders** | PostgreSQL `wim_orders` | Order status, customer, driver assignment. Admin needs to see order history and status |
| **Drivers (Sales Reps)** | PostgreSQL `wim_karyawan` | Driver names, status, vehicle assignment. Admin manages sales reps |
| **Users** | PostgreSQL `wim_users` | User accounts for sales reps. Admin creates/manages user accounts |
| **API Keys** | PostgreSQL `wim_api_keys` | Needed to generate API keys for new users |

These are all **read-heavy** lookups — the admin panel reads them, displays them, and in some cases creates/edits them via the Fleetbase API proxy (`/v1/*`).

### What the Admin Panel Reads FROM wim_* Tables

| Data | Source | Why It Matters |
|------|--------|---------------|
| **Attendance logs** | `wim_attendance` | Clock-in/out times, photos, geofence status. THE primary admin KPI |
| **Visit logs** | `wim_visits` | Check-in/out times, GPS, photos, notes, status. Visit completion tracking |
| **Visit plans** | `wim_visit_plan` | Daily store assignments, in/out-route tracking. Route completion stats |
| **Depots** | `wim_depots` | Depot locations, geofence radius, manager |
| **Stock checks** | `wim_stock_check` | Per-store inventory counts per SKU. Stock analysis |
| **Promo data** | `wim_promo*` | Promo programs (planned but not yet built). Promo performance analysis |
| **Admin roles** | `wim_admin_users` (new) | Admin role assignments. Super Admin manages this |
| **Admin depot access** | `wim_admin_depot_access` (new) | Depot scoping for depot admins |

### Integration Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    LXC 106 (same host)                    │
│                                                          │
│   serve.py (:8080)             Admin App (:8090)          │
│   ┌──────────────────┐        ┌──────────────────┐       │
│   │ Sales endpoints  │        │ Admin endpoints  │       │
│   │ ─ /api/auth/*    │        │ ─ /api/admin/*   │       │
│   │ ─ /api/absensi   │        │ ─ /api/export/*  │       │
│   │ ─ /api/visits    │        │                  │       │
│   │ ─ /v1/* proxy    │        │ ─ /v1/* proxy    │       │
│   └──────┬───────────┘        └──────┬───────────┘       │
│          │                          │                    │
│          │       ┌──────────────────┐│                    │
│          └───────┤  MySQL :3306     ├┘                    │
│                  │  fleetbase DB    │                      │
│                  │  ┌───────────┐   │                      │
│                  │  │ Fleetbase  │   │                      │
│                  │  │ native    │   │                      │
│                  │  │ tables    │   │                      │
│                  │  ├───────────┤   │                      │
│                  │  │ wim_*     │   │                      │
│                  │  │ custom    │   │                      │
│                  │  │ tables    │   │                      │
│                  │  └───────────┘   │                      │
│                  └──────────────────┘                      │
│                                                          │
│   PostgreSQL (:5432)                                    │
│   ┌───────────────────────────────┐                       │
│   │ Laravel API (read/write)      │                       │
│   │ ─ /v1/orders, /v1/places     │                       │
│   └───────────────────────────────┘                       │
└─────────────────────────────────────────────────────────┘
```

### PostgreSQL Direct Access Pattern

The admin app directly queries PostgreSQL `wim_sfa` for all data, using the same psycopg2 connection pattern as the sales app
2. The admin API key is a COMPANY-level key, not a per-user key — it has `FleetOps` scope
3. Admin proxy should use a **dedicated, long-lived admin API key** (stored in env var) rather than per-user keys

```python
# Admin Fleetbase client — uses a company-level admin key, not per-user
ADMIN_API_KEY = os.environ.get("FLEETBASE_ADMIN_KEY")
FLEETBASE_API = os.environ.get("FLEETBASE_API", "http://localhost:8000")

async def fleetbase_proxy(path: str, method: str = "GET", body: dict = None):
    """Direct PostgreSQL query via psycopg2 with admin connection."""
    headers = {
        "Authorization": f"Bearer {ADMIN_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    url = f"{FLEETBASE_API}{path}"
    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, json=body, headers=headers) as resp:
            return await resp.json(), resp.status
```

This is used when the admin panel does:
- `POST /v1/orders` (admin creates order)
- `POST /api_credentials` (admin generates API key for new sales rep)
- `GET /v1/places` (admin browses stores)
- `PUT /v1/entities/{id}` (admin edits product price)

### What the Admin Panel Does Directly

| Operation | Better Approach | Reason |
|-----------|----------------|--------|
| Store visit data (wim_visits, wim_attendance) | Direct PostgreSQL query | All data lives in PostgreSQL wim_sfa |
| Depot management | Direct PostgreSQL query | wim_depo table holds all depot data |
| Role/permission management | Direct PostgreSQL query | wim_admin_roles handles all RBAC |
| Aggregation queries | Direct PostgreSQL SQL | All data is local; aggregation queries are efficient |
| Promo management | Direct PostgreSQL query | Promos are stored in wim_promos table |

**Rule of thumb:** All data lives in PostgreSQL `wim_sfa`. Query it directly via psycopg2. No external API needed.

---

## 7. Recommended Architecture Blueprint

### V1 Admin Panel — The Minimum Viable Admin

```
frontend/
├── admin/                         # New admin webapp directory
│   ├── server.py                  # FastAPI app (port 8090)
│   ├── auth.py                    # Session validation (same logic as serve.py)
│   ├── db.py                      # MySQL async connection pool
│   ├── db.py                     # PostgreSQL connection pool
│   ├── models.py                  # Pydantic models for request/response
│   ├── dependencies.py            # FastAPI dependencies (get_admin_user)
│   ├── routers/
│   │   ├── dashboard.py           # Admin dashboard stats
│   │   ├── reports.py             # Visit, attendance, order, stock reports
│   │   ├── users.py               # User management (CRUD sales reps)
│   │   ├── depots.py              # Depot management
│   │   ├── stores.py              # Store management
│   │   ├── products.py            # Product/price management
│   │   ├── orders.py              # Order management
│   │   ├── promos.py              # Promo management
│   │   └── export.py              # CSV/Excel/PDF exports
│   ├── templates/                 # (Optional) Jinja2 templates if needed
│   └── static/                    # Admin frontend HTML/CSS/JS (same pattern)
│       ├── index.html             # Login (or redirect to serve.py login)
│       ├── admin-dashboard.html   # Admin overview
│       ├── admin-reports.html     # Reports with date pickers
│       ├── admin-users.html       # User management
│       ├── admin-depots.html      # Depot management
│       ├── admin-stores.html      # Store management
│       ├── admin-products.html    # Product management
│       ├── admin-orders.html      # Order management
│       ├── admin-promos.html      # Promo management
│       ├── css/
│       │   └── admin.css          # Admin-specific styles (data tables, etc.)
│       └── js/
│           ├── admin-config.js    # Admin API base URL
│           ├── admin-api.js       # Admin API client
│           └── admin-app.js       # Shared admin utilities
```

### V1 Admin Panel Data to Show (Priority Ordered)

| Priority | Report/View | Data Sources | SQL Complexity |
|----------|-------------|-------------|----------------|
| **P0** | **Visit completion stats** — per sales rep: planned vs visited, in-route vs luar-rute, duration | `wim_visit_plan` + `wim_visits` | Medium (LEFT JOIN + GROUP BY) |
| **P0** | **Attendance logs** — per sales rep: clock-in/out times, duration, geofence status | `wim_attendance` | Low (simple SELECT) |
| **P0** | **Order history** — per sales rep: order count, status, total value | Fleetbase `orders` table via proxy | Medium (via Fleetbase API) |
| **P1** | **Stock check results** — per store: SKU, quantity, timestamp | `wim_stock_check` | Low |
| **P1** | **Promo performance** — promo usage, free product distribution | `wim_promo*` (once built) | Medium |
| **P1** | **Route completion** — % of planned stores visited, avg visit duration | `wim_visit_plan` + `wim_visits` | Medium |
| **P2** | **Photo gallery** — visit photos by sales rep, date, store | `wim_visits.photos` | Low (JSON extract) |
| **P2** | **GPS trail** — clock-in locations, visit check-in locations on map | `wim_attendance` + `wim_visits` | Low |
| **P2** | **Export to CSV/Excel/PDF** — all reports downloadable | All of the above | File generation logic |

### V1 Excluded Features (Out of Scope)

| Feature | Reason | Target |
|---------|--------|--------|
| Real-time map of all sales reps | Requires WebSocket + GPS streaming; overkill for V1 | V2 |
| Automated route optimization | Manual route planning via admin panel | V2 |
| WhatsApp/OTP integration | External system; admin only configures it | V2 |
| Payroll/reimbursement integration | Beyond field sales scope | V3 |
| Automated report scheduling (cron email) | Not needed for initial admin panel | V2 |

---

## 8. Migration Path

### Phase 1: Foundation (Days 1-2)

1. Create `wim_admin_users` table + `wim_admin_depot_access` table (SQL)
2. Create the FastAPI project skeleton on port 8090
3. Wire up session auth (copy 30 lines from serve.py — cookie parsing, MySQL session check)
4. Wire up PostgreSQL admin connection (dedicated wim_sfa service account)
5. Build the admin frontend scaffold (HTML pages, CSS)
6. Deploy behind NPMplus reverse proxy

### Phase 2: Core Reports (Days 3-5)

1. Visit completion dashboard (Super Admin sees all; Depot Admin sees their depot)
2. Attendance log viewer with date range filter
3. Order history with status filter
4. Depot admin scope enforcement in queries

### Phase 3: Admin Management (Days 5-7)

1. Store management (CRUD — uses Fleetbase API proxy for Place creation)
2. Product management (edit prices, SKUs — uses Fleetbase API proxy)
3. User management (create/edit Fleetbase users + API keys + driver records)
4. Depot management (add/edit depot locations, radius)

### Phase 4: Advanced Features (Days 7-10)

1. Export to CSV, Excel (openpyxl), PDF (FPDF)
2. Promo management UI
3. Stock check analysis view
4. Route completion heat map

### Seed Admin Users

```sql
-- Create the first admins for the admin panel
-- These users must already exist in Fleetbase's users table

-- Rein = Super Admin (global scope, settings access)
INSERT INTO wim_admin_users (user_id, role, scope, settings_access, user_management, promo_management)
SELECT id, 'super_admin', 'global', TRUE, TRUE, TRUE FROM users WHERE email = 'reinharttanto@gmail.com';

-- Depo Bintaro admin (single_depot scope)
INSERT INTO wim_admin_users (user_id, role, scope, settings_access, user_management, promo_management, export_access)
SELECT id, 'depot_admin', 'single_depot', FALSE, FALSE, FALSE, TRUE FROM users WHERE email = 'bintaro-admin@wim.fleet';

INSERT INTO wim_admin_depot_access (user_id, depot_id)
SELECT (SELECT id FROM users WHERE email = 'bintaro-admin@wim.fleet'), id FROM wim_depots WHERE name = 'Depo Bintaro';
```

---

## Appendix: Key Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Admin aggregation queries overload MySQL | Medium | High (slows sales app too) | Use READ replicas or connection tagging; set `wait_timeout` on admin connections; add query timeouts |
| Session cookie mismatch between serve.py and admin app | Low | High (auth fails) | Share session cookie domain; both apps read from same `wim_auth.sessions` table; same cookie name `wim_session` |
| Depot-scoped queries miss data due to missing depot → store linkage | Medium | High (wrong reports) | Backfill `wim_depot_stores` during Phase 0; query traces to verify each admin sees correct data |
| PostgreSQL user permissions | Low | Simple (admin can create users via wim_users) | Set up wim_sfa service account with appropriate grants |
| Admins don't know which role they have | Low | Medium (confusion) | Show role badge prominently in admin header; role dropdown for Super Admin to "view as" depot admin |