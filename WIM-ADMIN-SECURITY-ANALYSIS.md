# WIM Online Admin Panel — Security & Data Integrity Analysis

> **Date:** 2026-09-09
> **Audience:** Super admin / development team
> **Status:** Recommendations based on current production schema + serve.py audit

---

## 1. Row-Level Access Control (RLAC) Model

### Current State
The `wim_admin_roles` table already exists with a solid foundation:
- Roles: `super_admin`, `head_of_sales`, `regional_manager`, `depo_admin`
- Scoping columns: `depot_id` (int, nullable) and `region` (varchar, nullable)
- Permission flags: `can_manage_users`, `can_manage_promos`, `can_export`
- The `wim_depot_team` table links any user (`sales_staff`, `team_lead`, `depot_admin`) to a depot

**Key gaps:** No region table exists, auth checks in serve.py use the wim_admin_roles table, and admin.html renders all data unfiltered.

### Proposed RLAC Model

#### 4-Tier Role Hierarchy

```
Level 0:  super_admin        → ALL depots + regions, full system access
Level 1:  head_of_sales      → ALL depots + regions (read all data, write limited)
Level 2:  regional_manager   → assigned region (multiple depots)
Level 3:  depo_admin         → single depot (team-level data)
Level 4:  sales_staff        → own data only (dashboards already filter by user_id)
```

#### Data Scoping Implementation

| Role | Sees Sales Reps From | Sees Orders From | Sees Visits/Stock From | Can Manage |
|------|---------------------|------------------|----------------------|------------|
| super_admin | All depots + regions | All | All | Users, promos, exports |
| head_of_sales | All depots + regions | All (read-only) | All | Promos, exports |
| regional_manager | depots IN assigned_region | Same depots | Same depots | Promos for depots |
| depo_admin | Own depot only | Own depot only | Own depot only | Exports |
| sales_staff | Own user_id only | Own driver assigned | Own user_id only | Nothing |

#### Required Schema Changes

```sql
-- 1. Create a regions table (currently 'region' is just varchar on wim_admin_roles)
CREATE TABLE wim_regions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Add region_id FK to wim_depots
ALTER TABLE wim_depots ADD COLUMN region_id INT NULL REFERENCES wim_regions(id);

-- 3. Normalize wim_admin_roles to use region_id FK
ALTER TABLE wim_admin_roles ADD COLUMN region_id INT NULL REFERENCES wim_regions(id);
-- (Keep legacy 'region' varchar during migration, drop later)

-- 4. Add region_id to wim_depot_team for regional_manager scoping
```

#### Enforcement Strategy

**Backend (serve.py):** Add a middleware function `_get_user_scope(user_id)` that returns the user's role and scoping boundaries. Every admin endpoint MUST call this and apply WHERE clause filtering:

```python
def _get_user_scope(user_id):
    """Return (role, depot_ids, region_id, permissions) for row-level filtering."""
    cur = conn.cursor()
    cur.execute("""
        SELECT r.role, r.depot_id, r.region_id,
               r.can_manage_users, r.can_manage_promos, r.can_export,
               dt.depot_id as team_depot_id
        FROM wim_admin_roles r
        LEFT JOIN wim_depot_team dt ON dt.user_id = r.user_id
        WHERE r.user_id = %s
    """, (user_id,))
    ...
    if role == 'super_admin':
        return (role, None, None, ...)  # No WHERE filter
    elif role == 'depo_admin':
        return (role, [depot_id], None, ...)  # WHERE depot_id IN (depot_ids)
    elif role == 'regional_manager':
        return (role, None, region_id, ...)  # JOIN wim_depots ON region_id
```

**Frontend (admin.html redesign):** The admin panel must be rebuilt as a proper supervisory console, not a flat Fleetbase proxy. Endpoints to consolidate:

| Current (direct DB queries) | Replacement (WIM server-side with row scoping) |
|--------------------------|-----------------------------------------------|
| `/v1/places` (all stores) | `/api/admin/stores?scope=auto` |
| `/v1/contacts` (all) | `/api/admin/users?scope=auto` |
| `/v1/orders` (all) | `/api/admin/orders?scope=auto&date=today` |
| `/v1/entities` (all products) | `/api/admin/products` (already scoped by company) |

#### Redis/Session Cache for Scope
Cache the user's scope object (role + depot_ids + region_id) in the session on login to avoid a DB query on every request.

---

## 2. Auth Strategy: PostgreSQL vs Separate Auth

### Current State
The system currently uses **dual auth**:
1. **Login**: Authenticates against wim_users table (bcrypt)
2. **Sessions**: Stored in `wim_auth.sessions` (MySQL, separate database)
3. **wim_auth.users**: A separate table duplicate with SHA256 password hashes (insecure!)

**Critical security issue:** The `wim_auth.users` table stores passwords hashed with SHA256 (single round, no salt based on the hash length: `8689814c0ab6bb7f9b1104d61ab1de7eb2d6b5ec01b4dd23d46357ef1156df3a` = 64 hex chars = SHA256). This is trivially bruteforceable. This table appears unused for actual login (serve.py verifies against Fleetbase `users` table with bcrypt), but it's a liability.

### Recommendation: Keep Fleetbase as Auth Source, Drop wim_auth.users

**Auth Architecture:**

```
User Login
    ↓
serve.py POST /api/auth/login
    ↓
 1. Validate against Fleetbase `users` table (bcrypt) ← CONTINUE THIS
 2. Read role from wim_admin_roles (our custom table)
 3. Create session in wim_auth.sessions
 4. Return HttpOnly session cookie
```

**Why NOT a fully separate auth table:**
- Fleetbase already handles user lifecycle (create, suspend, type)
- Fleetbase manages password resets via its API
- Maintaining a duplicate password table is a security risk (SHA256 in current form)
- Syncing account state (disabled, deleted) becomes a timing attack surface

**What to do with wim_auth.users:**
1. **Drop the `password` column** — it's unused for login and stores weak hashes
2. **Keep the table** but only for `email → fleetbase_api_key` + `fleetbase_driver_id` mapping (a read-through cache)
3. Better: **Eliminate wim_auth.users entirely** and store the fleetbase_api_key mapping in a new, clean table:

```sql
CREATE TABLE wim_api_key_cache (
    fleetbase_user_id INT PRIMARY KEY,
    fleetbase_api_key VARCHAR(255) NOT NULL,
    fleetbase_driver_id VARCHAR(255),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

This cache is populated lazily on login (serve.py already stores API key in session on first login).

**Password Policy Enhancement:**
- Enforce minimum 8 chars via Fleetbase (done)
- Add rate limiting: ✅ Already done (5 attempts / 5 min per email+IP)
- Add geo-IP anomaly detection (optional, future)

---

## 3. Data Localization & Read Replicas

### Current State
- Single PostgreSQL instance on LXC 106 (localhost:5432)
- Single `wim_sfa` database with all wim_* tables
- No replicas, no backups visible
- All on-prem Proxmox LXC

### Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Single point of failure | **HIGH** | DB crash = complete system outage |
| No read replica | **MEDIUM** | Admin queries on production DB = concurrency impact |
| No backup strategy visible | **HIGH** | Data loss risk |
| Python http.server and PostgreSQL on same LXC | **MEDIUM** | Full resource contention |

### Recommendations

#### A. Structured Backups (Immediate — Week 1)

```bash
# Daily SQL dump (cron on LXC host, not inside container)
0 2 * * * lxc-attach 106 -- pg_dump \
  --single-transaction --routines --triggers --events \
  wim_sfa > /backups/wim-daily/$(date +\%Y-\%m-\%d).sql

# Keep 7 daily + 4 weekly + 3 monthly
# Off-site copy via rsync to Netbird-connected NAS
```

#### B. Read Replica (Phase 2 — after admin panel ships)

**Why a read replica helps the admin panel specifically:**
- Admin panel queries will be **heavier** than per-user sales queries (aggregations, JOINs across all depots, date ranges)
- Sales app queries are `WHERE user_id = X` (indexed, lightweight)
- Separate read replica prevents admin dashboard queries from slowing down sales check-ins

**Architecture:**

```
Sales App → psycopg2 → PostgreSQL (localhost:5432)
                                            ↑
Admin Panel ──→ psycopg2 → PostgreSQL (localhost:5432)
                            OR
Admin Panel → Fleetbase API (same as above, but queries are heavier)
```

**Verdict: Defer read replica until admin panel is built and profiled.** The risk profile today doesn't justify the operational overhead. Start with:

1. ✅ Proper daily backups (week 1)
2. ✅ MySQL slow query log + monitoring
3. ❌ Skip read replica for now — revisit when admin panel shows latency > 200ms on any endpoint
4. ❌ Skip sharding — single 3-depot WIM operation doesn't need it

But DO plan for a read replica eventually:
```sql
-- Future state: admin panel config
mysql_replica_host = os.environ.get('WIM_REPLICA_HOST', None)
if user['role'] in ('super_admin', 'head_of_sales', 'regional_manager'):
    DB_HOST = mysql_replica_host or MYSQL_HOST
```

---

## 4. API Surface for Admin Panel

### Current API (serve.py)
Per-user endpoints: `/api/dashboard`, `/api/stores`, `/api/visits`, `/api/absensi`, `/api/report`, `/api/stock`
Proxy: `/v1/*` → Fleetbase API

### Required New Admin Endpoints

All under `/api/admin/*` prefix, all require `wim_admin_roles` check (not just any auth):

| Endpoint | Method | Purpose | Scope Filter | Rate Limit |
|----------|--------|---------|-------------|------------|
| `/api/admin/stores` | GET | List stores (all or scoped) | depot_id/region | Standard |
| `/api/admin/stores/:uuid` | GET | Store detail + history | depot_id/region | Standard |
| `/api/admin/stores/:uuid/orders` | GET | Orders for a store | depot_id/region | Standard |
| `/api/admin/orders` | GET | List orders with filters | driver depo → depot_id | Standard |
| `/api/admin/orders/:uuid` | GET | Order detail | depot_id/region | Standard |
| `/api/admin/orders/:uuid/verify` | POST | Admin override verify | Only super_admin/head_of_sales | Strict |
| `/api/admin/orders/:uuid/cancel` | POST | Admin cancel order | Only super_admin/head_of_sales | Strict |
| `/api/admin/users` | GET | List sales team (scoped) | depot_id/region + `can_manage_users` | Standard |
| `/api/admin/users/:id/attendance` | GET | View sales rep attendance | depot_id/region | Standard |
| `/api/admin/users/:id/visits` | GET | View sales rep visits | depot_id/region | Standard |
| `/api/admin/users/create` | POST | Create user (via Fleetbase API proxy) | Only `can_manage_users` | Strict |
| `/api/admin/users/activate` | POST | Enable/disable user | Only `can_manage_users` | Strict |
| `/api/admin/visits` | GET | Visit dashboard (all/team) | depot_id/region | Standard |
| `/api/admin/visits/:id` | GET | Visit detail + photos | depot_id/region | Standard |
| `/api/admin/absensi` | GET | Attendance dashboard | depot_id/region | Standard |
| `/api/admin/absensi/export` | GET | CSV export attendance | `can_export` | Strict (1 req/5min) |
| `/api/admin/stores/export` | GET | CSV export visits | `can_export` | Strict (1 req/5min) |
| `/api/admin/dashboard` | GET | Supervisor dashboard (team KPI) | depot_id/region | Standard |
| `/api/admin/team` | GET | Team roster + status | depot_id/region | Standard |
| `/api/admin/promos` | GET | Promo CRUD | `can_manage_promos` + depot scope | Standard |
| `/api/admin/promos/create` | POST | Create promo | `can_manage_promos` + depot scope | Strict |
| `/api/admin/promos/toggle` | POST | Activate/deactivate promo | `can_manage_promos` + depot scope | Strict |
| `/api/admin/alerts` | GET | Anomaly detection dashboard | depot_id/region | Standard |
| `/api/admin/audit-log` | GET | Audit log viewer | Only super_admin | Standard |

### Scope Enforcement Pattern

All admin endpoints should use a shared authorization wrapper:

```python
def _require_admin_scope(user_id, required_permission=None):
    """
    Returns (role, scope_filter_dict) or None.
    scope_filter_dict is applied to every admin query automatically.
    
    Example scope_filter_dict for depo_admin:
        {'depot_ids': [1], 'region_id': None, 'sql_where': 'AND wv.user_id IN 
            (SELECT user_id FROM wim_depot_team WHERE depot_id=1)'}
    
    Example for regional_manager:
        {'depot_ids': [1,2,3], 'region_id': 1, 'sql_where': 'AND wv.user_id IN 
            (SELECT dt.user_id FROM wim_depot_team dt 
             JOIN wim_depots d ON dt.depot_id = d.id 
             WHERE d.region_id=1)'}
    """
    return (role, scope)
```

### API Rate Limiting

| Endpoint Group | Limit | Window |
|---------------|-------|--------|
| Admin dashboard | 30/min | Per user |
| Admin writes (create, verify, toggle) | 10/min | Per user |
| Admin exports | 1/5min | Per user |
| Admin audit log | 60/min | Per user |

---

## 5. Audit Logging Requirements

### Current State
- Flat file log (`wim-server.log`) with JSON entries
- Rotation at 5MB (`wim-server.log.1`)
- No structured audit trail, no retention, no query capability

### Complete Audit Event Catalog

#### Must-Log Events (Critical — Data Integrity)

| Event Category | Event | Data Captured | Retention |
|---------------|-------|---------------|-----------|
| **Auth** | Login success | user_id, email, role, IP, user_agent, timestamp | 1 year |
| **Auth** | Login failure | email, IP, attempt_count | 90 days |
| **Auth** | Logout | user_id, session_id, timestamp | 1 year |
| **Auth** | Session expiry | user_id, email, session_age | 90 days |
| **User Management** | User created | admin_id, new_user_email, role, depot, IP | Forever |
| **User Management** | User deactivated | admin_id, target_user_id, reason, IP | Forever |
| **User Management** | User role changed | admin_id, target_user_id, old_role, new_role, IP | Forever |
| **User Management** | User depot reassigned | admin_id, target_user_id, old_depot, new_depot, IP | Forever |
| **Order** | Order created | user_id, store, items_count, total, timestamp | 2 years |
| **Order** | Order verified | admin_id, order_id, method (QR/barcode/manual), IP | 2 years |
| **Order** | Order rejected | admin_id, order_id, reason, IP | 2 years |
| **Order** | Order cancelled | admin_id/user_id, order_id, reason, IP | 2 years |
| **Order** | Order amount override | admin_id, order_id, old_total, new_total, IP | 2 years |
| **Visit** | Visit check-in forced | admin_id, visit_id, reason, IP | 1 year |
| **Visit** | Visit deleted/modified | admin_id, visit_id, old_data, new_data, IP | 2 years |
| **Promo** | Promo created | admin_id, promo_name, type, value, depot, IP | 2 years |
| **Promo** | Promo activated/deactivated | admin_id, promo_id, new_status, IP | 2 years |
| **Promo** | Promo parameters changed | admin_id, promo_id, diff (before/after), IP | 2 years |
| **Export** | Data export | admin_id, export_type, filters, row_count, IP | 1 year |
| **Data** | Store created/modified | admin_id/user_id, store_uuid, changes, IP | 2 years |
| **Data** | Stock check viewed by admin | admin_id, store_uuid, items_count, IP | 90 days |
| **Admin** | Role/permission changed | admin_id, target_user_id, old, new, IP | Forever |
| **Admin** | Admin panel page access | admin_id, page, timestamp | 90 days |
| **System** | Backup started/completed | type, size, status | 30 days |
| **System** | Configuration changed | admin_id, config_key, old_value, new_value | Forever |

### Audit Log Implementation

```sql
CREATE TABLE wim_audit_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(64) NOT NULL,          -- e.g., 'order.verified', 'user.created'
    actor_id INT NOT NULL,                      -- FK to users.id (who did it)
    actor_role VARCHAR(50),                     -- Snapshot for historical context
    target_type VARCHAR(64),                    -- 'order', 'user', 'promo', 'store'
    target_id VARCHAR(64),                      -- UUID or ID of affected resource
    depot_id INT NULL,                          -- Depot context (null for HQ actions)
    metadata JSON,                              -- Flexible payload (before/after, reason, IP)
    ip_address VARCHAR(45),                     -- Client IP
    user_agent VARCHAR(500) NULL,               -- Browser/app identifier
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_event_type (event_type),
    INDEX idx_actor (actor_id),
    INDEX idx_target (target_type, target_id),
    INDEX idx_depot (depot_id),
    INDEX idx_created (created_at),
    INDEX idx_event_depot (event_type, depot_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### Audit Logging Service (serve.py)

```python
# In serve.py — structured audit logger
class AuditLogger:
    def log(self, event_type, actor_id, actor_role, target_type, target_id,
            depot_id=None, metadata=None, ip=None, user_agent=None):
        conn = get_mysql()
        if not conn: return
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO wim_audit_log 
                (event_type, actor_id, actor_role, target_type, target_id, depot_id, metadata, ip_address)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (event_type, actor_id, actor_role, target_type, str(target_id),
                  depot_id, json.dumps(metadata or {}), ip or '?'))
            conn.commit()
            cur.close()
        except Exception as e:
            write_log('ERROR', 'audit', f'Failed to write audit: {e}')
        finally:
            ret_mysql(conn)
```

### Audit UI Requirements

The admin panel must include an **Audit Log Viewer** (super_admin only):

- Search by event_type, actor, target, date range
- View metadata JSON as a diff (changed fields highlighted)
- Export audit log as CSV (strict rate limit)
- Real-time alerting for: login failures > 10 in 5min, admin role changes, export of > 1000 records
- Retention policy enforcement (archive/delete old records)

### Retention & Rotation

| Event Category | Hot Retention (DB) | Cold Storage | Destruction |
|---------------|-------------------|-------------|-------------|
| Auth events | 90 days | 1 year (JSON archive) | Delete after 1 year |
| Orders | 2 years | 5 years (parquet archive) | Delete after 5 years |
| User management | Forever | Forever | NEVER delete |
| Promo changes | 2 years | 5 years | Delete after 5 years |
| Admin access | 30 days | 90 days | Delete after 90 days |
| Exports | 1 year | 2 years | Delete after 2 years |

---

## Summary of Priority Actions

### Critical (Week 1)
1. ✅ Drop `wim_auth.users.password` column (SHA256 liability)
2. ✅ Implement `_get_user_scope()` middleware in serve.py
3. ✅ Set up daily MySQL backups with 7-day rotation
4. ✅ Rebuild admin.html as a server-rendered dashboard (not Fleetbase proxy)

### Important (Week 2-3)
5. ✅ Create `wim_regions` table and normalize `wim_admin_roles.region_id`
6. ✅ Implement admin API endpoints with row-level WHERE injection
7. ✅ Create `wim_audit_log` table and plug audit logging into all write operations
8. ✅ Add admin UI audit log viewer

### Future
9. ❌ Read replica — defer until admin panel profiling shows need
10. ❌ Geo-IP anomaly detection for auth
11. ❌ Parquet cold storage for audit logs older than 2 years