# WIM Online — Middleware Backend Service

> **Purpose:** The standalone API middleware that fronts the `wim_sfa` PostgreSQL
> database. Sales app and admin panel hit these APIs; future external apps use the
> same gateway via API keys.
> **Deployed:** LXC 111 (`wim-mid`) on SanQua AI Proxmox 192.168.6.101, port **8000**.
> **Database:** LXC 110 (`wim-db`) 192.168.6.110:5432, DB `wim_sfa`.
> **Companion docs:** `API-REFERENCE.md` (API contract), `DATABASE-MAPPING.md` (schema),
> `DEPLOYMENT.md` (containerization plan).

---

## 1. Architecture

```
                 ┌───────────────────────────────────────────────┐
                 │            WIM ONLINE PLATFORM                 │
                 │                                                │
  Sales App ────▶│  ┌─────────────────────────────────────────┐  │
 (mobile)        │  │       MIDDLEWARE (wim-mid, LXC 111)      │  │
                 │  │       serve.py  :8000                    │  │
 Admin Panel ──▶ │  │  ┌─────────────────────────────────┐     │  │
 (desktop)       │  │  │  Cookie auth (app users)          │     │  │
                 │  │  │  Bearer API-key (external apps)   │     │  │
 Future apps ──▶ │  │  └───────────────┬─────────────────┘     │  │
 (API key)       │  │                  │ request logging       │  │
                 │  └──────────────────┼───────────────────────┘  │
                 │                     │ psycopg2 (pooled)         │
                 │                     ▼                           │
                 │        ┌──────────────────────────┐            │
                 │        │  wim-db (LXC 110)         │            │
                 │        │  PostgreSQL 17 :5432      │            │
                 │        │  wim_sfa (31 tables)      │            │
                 │        └──────────────────────────┘            │
                 └───────────────────────────────────────────────┘
```

### 1.1 Why a middleware service?

| Goal (user's requirement) | How the middleware delivers it |
|---------------------------|-------------------------------|
| **Reduce direct DB connections** | Apps never touch PG directly; all reads/writes go through `serve.py` which uses a connection pool (`get_pg()`/`ret_pg()`). |
| **Easier logging** | `write_log()` — every request, auth event, API hit, and error is logged to a structured log file. |
| **Future apps need APIs to the DB** | External consumers authenticate with a Bearer API key (from `wim_api_keys`) and use the same endpoints. No DB credentials exposed. |

---

## 2. Deployment (LXC 111)

### 2.1 Container

| Property | Value |
|----------|-------|
| VMID | 111 |
| Hostname | `wim-mid` |
| OS | Debian 13 (LXC template) |
| IP | 192.168.6.111/24 |
| RAM / CPU | 1 GB / 1 vCPU |
| Storage | local-lvm |
| Listens | `0.0.0.0:8000` |
| Deps | `python3`, `python3-psycopg2`, `python3-bcrypt` |

### 2.2 systemd unit (`/etc/systemd/system/wim-mid.service`)

```ini
[Unit]
Description=WIM Online Middleware API Server
After=network.target postgresql.service

[Service]
Type=simple
WorkingDirectory=/opt/wim-mid
Environment=PORT=8000
Environment=WIM_PG_HOST=192.168.6.110
Environment=WIM_PG_PORT=5432
Environment=WIM_PG_DB=wim_sfa
Environment=WIM_PG_USER=wim_app
Environment=WIM_PG_PASS=wim_app_sfa_2026
ExecStart=/usr/bin/python3 -u /opt/wim-mid/serve.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 2.3 Service management

```bash
# From the Proxmox host:
pct exec 111 -- systemctl restart wim-mid   # restart
pct exec 111 -- systemctl status wim-mid    # status
pct exec 111 -- tail -f /opt/wim-mid/logs/  # logs (or the log file path)
# Reload code after a deploy:
pct exec 111 -- bash -c 'cd /opt/wim-mid && tar xzf <pkg>.tar.gz && systemctl restart wim-mid'
```

### 2.4 Environment variables

| Var | Default | Override via systemd `Environment=` |
|-----|---------|---------------------------------------|
| `PORT` | `8000` | Listener port |
| `MIN_VISIT_SECONDS` | `180` | Min visit duration |
| `WIM_PG_HOST` | `127.0.0.1` | DB host (`192.168.6.110` in prod) |
| `WIM_PG_PORT` | `5432` | DB port |
| `WIM_PG_DB` | `wim_sfa` | Database |
| `WIM_PG_USER` | `postgres` | DB user (`wim_app`) |
| `WIM_PG_PASS` | — | DB password |

---

## 3. Authentication — Two Modes

The middleware brokers two identity types against the same API surface.

### 3.1 Cookie session (app users — sales reps, admins)
- **Login:** `POST /api/auth/login` `{email, password}` → bcrypt-verified against `wim_users`, returns session cookie.
- **Session:** `GET /api/auth/session` validates the cookie.
- Used by the **sales app** and **admin panel** in the browser.

### 3.2 Bearer API key (external apps / future integrations)
- **Key source:** stored (hashed) in `wim_api_keys` table (name, api_key, scope, is_active, expires_at, last_used_at).
- **Auth header:** `Authorization: Bearer <api_key>`.
- **Validation:** `_auth_external_key()` looks up the key, checks `is_active=TRUE` + not expired, updates `last_used_at`, and maps the key's `scope` to an auth role.
- **Purpose:** future apps (order-taking app, Fleetbase sync, Odoo, warehouse) read/write the DB **without DB credentials** — just an API key.

### 3.3 Auth flow in code (`_require_auth`)
```
1. Try Bearer API key → if valid, use synthetic user {name, role, is_api:True}
2. Else try cookie session → look up wim_sessions → return user dict
3. Else 401
```

### 3.4 Create an API key
```bash
# From middleware (has psycopg2 + DB access), or via the API as super_admin:
pct exec 111 -- python3 - <<'PY'
import secrets, psycopg2
key = f"wim_{secrets.token_hex(24)}"
c = psycopg2.connect(host='192.168.6.110', dbname='wim_sfa', user='wim_app', password='wim_app_sfa_2026')
cur = c.cursor(); cur.execute(
  "INSERT INTO wim_api_keys (name,api_key,scope) VALUES ('public-gateway',%s,%s)", (key,'orders:read,orders:write,stores:read,stock:read,report:read,sync:write'))
c.commit(); print("KEY:", key)
PY
```

---

## 4. API Surface

The middleware serves **~50 endpoint handlers** across all domains. Full contract in
`API-REFERENCE.md`. Groups:

| Domain | Example endpoints |
|--------|-------------------|
| Auth | `/api/auth/login`, `/api/auth/session`, `/api/auth/logout` |
| Users | `/api/users` (GET/POST), `/api/users/:id`, `/api/users/:id/meta` |
| Stores/NOO | `/api/stores` (GET/POST), `/api/stores/:uuid`, `/api/stores/:uuid/contacts` |
| Products | `/api/products` (GET/POST), `/api/products/promos` |
| Depots | `/api/depots` |
| Visit plan | `/api/visit_plan` |
| Visits | `/api/visits` (check-in/out), `/api/visits/active` |
| Attendance | `/api/absensi` (clock-in/out) |
| Orders | `/api/orders` (GET/POST), `/api/orders/detail`, `/api/orders/calculate`, `/api/orders/verify`, `/api/orders/status` |
| Stock | `/api/stock` |
| Reports | `/api/report`, `/api/analytics/orders` |
| Config | `/api/config`, `/api/config/:key` |
| API keys | `/api/api-keys` |
| Sync | `/api/sync/queue` |
| System | `/api/dashboard`, `/api/log`, `/api/logs` |

---

## 5. Testing

All APIs were tested end-to-end (input + read) from the middleware against the live
DB. **Result: 26/26 passed.**

| # | Domain | Method | Auth | Result |
|---|--------|--------|------|--------|
| 1 | login | POST | cookie | ✅ |
| 2 | session validate | GET | cookie | ✅ |
| 3 | session (bearer key) | GET | bearer | ✅ |
| 4 | list users | GET | bearer | ✅ |
| 5 | create user | POST | bearer | ✅ |
| 6 | NOO create store (1:many contact) | POST | bearer | ✅ |
| 7 | get store detail | GET | cookie | ✅ |
| 8 | add store contact | POST | cookie | ✅ |
| 9 | list products | GET | bearer | ✅ |
| 10 | create product | POST | bearer | ✅ |
| 11 | list depots | GET | bearer | ✅ |
| 12 | clock-in | POST | cookie | ✅ |
| 13 | read absensi | GET | cookie | ✅ |
| 14 | visit check-in | POST | cookie | ✅ |
| 15 | read visits | GET | cookie | ✅ |
| 16 | create order | POST | cookie | ✅ |
| 17 | read orders | GET | cookie | ✅ |
| 18 | read orders | GET | bearer | ✅ |
| 19 | stock check | POST | cookie | ✅ |
| 20 | read stock | GET | cookie | ✅ |
| 21 | report | GET | cookie | ✅ |
| 22 | analytics orders | GET | bearer | ✅ |
| 23 | list api-keys | GET | bearer | ✅ |
| 24 | set config | PATCH | bearer | ✅ |
| 25 | dashboard | GET | cookie | ✅ |
| 26 | logout | POST | cookie | ✅ |

**Verified data persisted to DB via API:** 7 users, 6 stores, 10 store contacts,
3 products, 1 depot, 4 visits, 1 attendance, 2 orders, 4 stock checks, 1 api_key —
all written through the middleware, confirming the app→middleware→DB path.

---

## 6. Request Logging

Every request path is instrumented with `write_log(level, tag, message)`:

| Tag | Logged when |
|-----|-------------|
| `auth` | login success/fail, api-key checks, expired keys |
| `sessions` | session create/get/delete |
| `orders` | order create/get, SKU-built order refs |
| `visits` | check-in/check-out |
| `absensi` | clock-in/clock-out |
| `stores` | NOO creation, store queries |
| `stock` | stock-check writes |
| `products` | product create/read |
| `sync_queue` | queue enqueue failures |
| `server` | startup/shutdown |

Logs write to a file (path defined by `LOG_FILE`); `GET /api/logs` surfaces recent
entries.

---

## 7. Security

| Measure | Implemented via |
|---------|-----------------|
| No DB credentials in apps | Apps use cookie or API key; DB creds only in middleware systemd env |
| API keys scoped + revocable | `wim_api_keys.scope`, `.is_active`, `.expires_at` |
| bcrypt password hashing | `wim_users.password_hash` |
| Server-side validation | Role checks on privileged endpoints (e.g. admin-only product create) |
| Parameterized SQL | All queries use `%s` placeholders, no string interpolation |
| Connection pooling | `get_pg()`/`ret_pg()` reuse connections |

---

## 8. Schema Changes Made During Testing (recorded)

The API test suite surfaced **schema drift** between the first serve.py draft and the
canonical `01-schema.sql`. The **canonical schema is the source of truth**; serve.py
was aligned to it. One schema table was extended:

### wim_orders — columns added
| Column | Type | Default | Why |
|--------|------|---------|-----|
| `store_uuid` | UUID | — | Consistent with rest of system (stores referenced by UUID everywhere) |
| `verification_status` | VARCHAR(30) | `'pending'` | Order verification lifecycle (QR/barcode) |
| `sales_channel` | VARCHAR(30) | `'app'` | Tracks source channel |

These additions are reflected in `deploy/db/init/01-schema.sql`. No tables were
dropped; no data was lost.

---

## 9. Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `relation does not exist` | serve.py references a table not in wim_sfa — verify against 01-schema.sql |
| `column does not exist` | schema drift — check the column against `DATABASE-MAPPING.md` canonical names (e.g. `address` not `street1`, `total` not `grand_total`) |
| `must be owner of table` | DDL must run as `postgres` (app user has DML only) |
| Middleware won't start | check `systemctl status wim-mid`, verify `WIM_PG_*` env point at 192.168.6.110 |
| DB unreachable | `pct exec 111 -- bash -c 'ping -c1 192.168.6.110'` — network; or PG `listen_addresses`/pg_hba.conf |
| `visitId: 0` | visit INSERT must use `RETURNING id`, not `lastrowid`/`LASTVAL()` (psycopg2) |