# WIM Online — Deployment Plan

> **Purpose:** Standalone deployment architecture for the WIM Online SFA platform
> (sales app + admin panel + middleware + PostgreSQL), using **containerized
> services** so each function can be scaled and hosted independently.
> **Deploy target:** Docker Compose or Proxmox LXC. Both supported.
> **Companion docs:** `DATABASE-MAPPING.md` (schema), `API-REFERENCE.md` (API contract).

---

## Table of Contents

1. [Deployment Philosophy](#1-deployment-philosophy)
2. [Architecture Overview](#2-architecture-overview)
3. [Services Breakdown](#3-services-breakdown)
4. [Required System Specs](#4-required-system-specs)
5. [Environment Variables](#5-environment-variables)
6. [Networking & Ports](#6-networking--ports)
7. [Docker Deployment](#7-docker-deployment)
8. [Proxmox LXC Deployment](#8-proxmox-lxc-deployment)
9. [Image Builds](#9-image-builds)
10. [Production vs Development Servers](#10-production-vs-development-servers)
11. [Scaling Path (Future)](#11-scaling-path-future)
12. [Backup & Restore](#12-backup--restore)
13. [Monitoring & Health Checks](#13-monitoring--health-checks)
14. [Testing Period (1-Month Sales Pilot)](#14-testing-period-1-month-sales-pilot)

---

## 1. Deployment Philosophy

Deploy the platform as **4 isolated containerized services**, each built from its own
image, connected by environment variables. This provides:

- **Independent scaling** — move the sales-app middleware/frontend to a beefier host later without touching the DB or admin.
- **Independent hosting** — each service can live on a different physical system (smallest footprint per host, or distribute across the homelab).
- **Clear env contract** — no hardcoded IPs/creds; everything flows through env vars.
- **Reproducibility** — same image runs in dev and prod, differing only by env file.
- **Isolation** — a crash/compromise in one service doesn't take down the whole platform.

```
┌────────────────────────────────────────────────────────────────┐
│                    WIM ONLINE PLATFORM                          │
│                                                                  │
│  ┌──────────────┐   ┌──────────────────┐   ┌────────────────┐  │
│  │  sales-app   │   │   wim-api        │   │   admin-panel  │  │
│  │  (nginx,     │──▶│   (serve.py      │◀──│   (admin-      │  │
│  │  static-only,│   │    middleware)   │   │    server.py)  │  │
│  │  :80)        │   │    :8000         │   │    :8001       │  │
│  └──────────────┘   └───────┬──────────┘   └────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│                    ┌──────────────────┐                         │
│                    │   wim-db         │                         │
│                    │   (PostgreSQL)   │                         │
│                    │    :5432         │                         │
│                    └──────────────────┘                         │
│                                                                  │
│  ──── Future sync ────────────────────────────────────────────  │
│        wim-api ──▶ sync layer ──▶ Fleetbase / order-app / Odoo  │
└────────────────────────────────────────────────────────────────┘
```

---

## 2. Architecture Overview

### 2.1 Service Roles

| # | Service | Container Name | Port (internal) | Runs | Depends On |
|---|---------|----------------|-----------------|------|------------|
| 1 | **Database** | `wim-db` | **5432** | PostgreSQL 17 | — |
| 2 | **API / Middleware** | `wim-api` | **8000** | `serve.py` (Python http.server) | wim-db |
| 3 | **Sales App** | `sales-app` | **80** | nginx serving static `frontend/` | wim-api |
| 4 | **Admin Panel** | `admin-panel` | **8001** | `admin-server.py` (Python http.server) | wim-db |

### 2.2 Request Flows

```
Sales rep browser
   │  HTTPS (NPMplus / reverse proxy)
   ▼
sales-app :80  ──(static html/js/css)──▶  browser renders page
   │  JS calls  /api/*   (same-origin via nginx proxy_pass)
   ▼
wim-api :8000  ──serve.py endpoints──▶  wim-db :5432  (psycopg2)

Admin browser
   │  HTTPS
   ▼
admin-panel :8001  ──admin-server.py──▶  wim-db :5432
```

**Key decision:** `serve.py` serves **both** the frontend static files AND the API in
the current monolith. In the container split, `sales-app` (nginx) takes over static
serving, and `wim-api` runs **only** the `/api/*` endpoints with `proxy_pass`
from nginx so the frontend still uses same-origin `/api/*` paths.

---

## 3. Services Breakdown

### 3.1 wim-db — PostgreSQL
- Image: `postgres:17-alpine` (or `postgres:17`)
- Volume: `/var/lib/postgresql/data` for persistent data
- Init: `init/` SQL scripts for schema + seed on first boot
- Health: `pg_isready`

### 3.2 wim-api — Middleware (serve.py)
- Image: `python:3.13-slim` + `psycopg2-binary`, `bcrypt`
- Entrypoint: `python serve.py`
- Serves: **only** API endpoints on :8000
- Health: `GET /api/auth/session` → 401 (alias alive check) or `/healthz`

### 3.3 sales-app — Static frontend host
- Image: `nginx:alpine`
- Copy: `frontend/*.html`, `frontend/js/`, `frontend/css/`, `frontend/assets/`
- nginx config:
  - `location /` → serve static files
  - `location /api/` → `proxy_pass http://wim-api:8000/api/`
- Health: `GET /` → 200 index.html

### 3.4 admin-panel — Admin app
- Image: `python:3.13-slim` + `psycopg2-binary`, `bcrypt`
- Entrypoint: `python admin-server.py`
- **✅ Migrated off MySQL/Fleetbase (2026-09-09).** `admin-server.py` is now a **thin client of the middleware** — it authenticates via `POST /api/auth/login` (shared `wim_users`) and queries the middleware's `/api/*` endpoints (users, visits, orders, attendance, depots, dashboard) using a privileged service **Bearer API key** (`ADMIN_API_KEY` env). No direct DB connection, no pymysql.
- Config env: `ADMIN_PORT`, `ADMIN_API_BASE` (middleware URL), `ADMIN_API_KEY`.
- RBAC: only admin-class roles (`super_admin`, `depo_admin`) can log in; server-side role checks.

---

## 4. Required System Specs

### 4.1 Minimum (single host, all 4 containers)

| Resource | Minimum | Comfortable |
|----------|---------|-------------|
| CPU | 1 vCPU | 2 vCPU |
| RAM | 1 GB | 2 GB |
| Disk | 5 GB | 10 GB (DB grows with photos/orders) |
| OS | Debian 12 / Ubuntu 22.04+ | same |

### 4.2 Dev Server (Rein's homelab LXC 106)

| Resource | Value |
|----------|-------|
| Host | Proxmox LXC 106 (192.168.6.101), 4 vCPU / 8 GB |
| PG | `wim_sfa` already running (PostgreSQL 17) |
| Public | sales.sqa.web.id → NPMplus → :8080 |

### 4.3 Production Server (after pilot)

| Resource | Value | Rationale |
|----------|-------|-----------|
| CPU | 2–4 vCPU | API concurrency + PG |
| RAM | 4–8 GB | PG cache + Python workers |
| Disk | 50 GB SSD | Photos (base64 in DB), order history, backups |
| Network | 1 Gbps | NPMplus TLS termination |

---

## 5. Environment Variables

The full env contract. Each service reads its own. Secrets injected at deploy time
(`.env` file, Docker secrets, or Proxmox env), **never committed to git.**

### 5.1 wim-db
| Variable | Default | Purpose |
|----------|---------|---------|
| `POSTGRES_DB` | `wim_sfa` | Database name |
| `POSTGRES_USER` | `postgres` | DB user |
| `POSTGRES_PASSWORD` | `wim_postgres_2026` | DB password |

### 5.2 wim-api
| Variable | Default | Purpose |
|----------|---------|---------|
| `PORT` | `8000` | Listener port (was 8080 in monolith) |
| `WIM_PG_HOST` | `wim-db` | DB host (container name in compose) |
| `WIM_PG_PORT` | `5432` | DB port |
| `WIM_PG_DB` | `wim_sfa` | DB name |
| `WIM_PG_USER` | `postgres` | DB user |
| `WIM_PG_PASS` | `wim_postgres_2026` | DB password |
| `MIN_VISIT_SECONDS` | `180` | Min visit duration |
| `ADMIN_EMAIL` | *(set in prod)* | Bootstrap super-admin |
| `ADMIN_PASSWORD` | *(set in prod)* | Bootstrap super-admin |

### 5.3 sales-app
| Variable | Default | Purpose |
|----------|---------|---------|
| `API_HOST` | `wim-api` | Upstream API container (used by nginx template) |
| `API_PORT` | `8000` | Upstream API port |

### 5.4 admin-panel
| Variable | Default | Purpose |
|----------|---------|---------|
| `ADMIN_PORT` | `8001` | Listener port |
| `WIM_PG_HOST` | `wim-db` | DB host |
| `WIM_PG_PORT` | `5432` | |
| `WIM_PG_DB` | `wim_sfa` | |
| `WIM_PG_USER` | `postgres` | |
| `WIM_PG_PASS` | `wim_postgres_2026` | |

### 5.5 Future integrations (not required for V1)
| Variable | Purpose |
|----------|---------|
| `FLEETBASE_API_URL` | (future) Delivery/driver sync endpoint |
| `FLEETBASE_API_KEY` | (future) Delivery/driver API key |
| `ODOO_API_URL` | Odoo order-app URL (future) |
| `ODOO_API_KEY` | Odoo consumer key |
| `WAREHOUSE_API_URL` | Warehouse system (future) |
| `WAREHOUSE_API_KEY` | Warehouse consumer key |

---

## 6. Networking & Ports

### 6.1 Public exposure (via NPMplus reverse proxy)

| Public Host | Internal Target |
|-------------|-----------------|
| `sales.sqa.web.id` | `sales-app:80` |
| `admin.sqa.web.id` | `admin-panel:8001` |
| `api.sqa.web.id` (optional) | `wim-api:8000` |

### 6.2 Internal (Docker network `wim-net`)
```
wim-db:5432        ← internal only
wim-api:8000       ← reached via sales-app proxy + optionally exposed
sales-app:80       ← public
admin-panel:8001   ← public
```

### 6.3 Security
- `wim-db` port **not exposed** to host; only reachable from `wim-api`/`admin-panel` inside the network.
- TLS terminated at NPMplus (public edge).
- API keys for external consumers use `wim_api_keys` (Bearer), scoped.

---

## 7. Docker Deployment

### 7.1 Directory layout
```
wim-online/
├── docker-compose.yml
├── .env                     # secrets (gitignored)
├── db/
│   └── init/
│       ├── 01-schema.sql    # CREATE TABLE wim_sfa schema
│       └── 02-seed.sql      # seed users/stores/products
├── api/
│   ├── Dockerfile
│   ├── serve.py
│   └── requirements.txt
├── sales-app/
│   ├── Dockerfile
│   ├── nginx.conf
│   └── www/                 # (frontend/*.html, js, css, assets)
└── admin/
    ├── Dockerfile
    ├── admin-server.py
    └── requirements.txt
```

### 7.2 docker-compose.yml
```yaml
version: "3.9"

services:
  wim-db:
    image: postgres:17-alpine
    container_name: wim-db
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-wim_sfa}
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-wim_postgres_2026}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/init:/docker-entrypoint-initdb.d:ro
    networks: [wim-net]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  wim-api:
    build: ./api
    container_name: wim-api
    restart: unless-stopped
    environment:
      PORT: 8000
      WIM_PG_HOST: wim-db
      WIM_PG_PORT: 5432
      WIM_PG_DB: ${POSTGRES_DB:-wim_sfa}
      WIM_PG_USER: ${POSTGRES_USER:-postgres}
      WIM_PG_PASS: ${POSTGRES_PASSWORD:-wim_postgres_2026}
      MIN_VISIT_SECONDS: 180
    depends_on:
      wim-db:
        condition: service_healthy
    networks: [wim-net]
    expose: ["8000"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=3)"]
      interval: 15s

  sales-app:
    build: ./sales-app
    container_name: sales-app
    restart: unless-stopped
    environment:
      API_HOST: wim-api
      API_PORT: 8000
    ports:
      - "8080:80"          # map public 8080 → nginx :80
    depends_on: [wim-api]
    networks: [wim-net]

  admin-panel:
    build: ./admin
    container_name: admin-panel
    restart: unless-stopped
    environment:
      ADMIN_PORT: 8001
      WIM_PG_HOST: wim-db
      WIM_PG_PORT: 5432
      WIM_PG_DB: ${POSTGRES_DB:-wim_sfa}
      WIM_PG_USER: ${POSTGRES_USER:-postgres}
      WIM_PG_PASS: ${POSTGRES_PASSWORD:-wim_postgres_2026}
    depends_on: [wim-db]
    ports:
      - "8081:8001"
    networks: [wim-net]

volumes:
  pgdata:

networks:
  wim-net:
    driver: bridge
```

### 7.3 Deploy commands
```bash
cd wim-online
docker compose up -d --build
docker compose ps
docker compose logs -f wim-api
```

---

## 8. Proxmox LXC Deployment

Exactly the same 4 services, but as **4 LXCs** on Proxmox. Env vars injected via
LXC config (`pct set <id> ...` env) or a systemd unit per service.

### 8.1 LXC inventory

| Service | VMID | Host | RAM | Notes |
|---------|------|------|-----|-------|
| wim-db | 110 | 192.168.6.110 | 2 GB | PostgreSQL 17.11, tuning applied, Asia/Jakarta |
| wim-api (middleware) | 111 | 192.168.6.111:8000 | 1 GB | serve.py, systemd `wim-mid.service`, dual auth (cookie + Bearer API key) |
| sales-app | 112 | 192.168.6.112:80 | 512 MB | nginx static, `/api/*` → 192.168.6.111:8000 |
| admin-panel | 113 | 192.168.6.113:8001 | 512 MB | admin-server.py (middleware-backed, systemd `wim-admin.service`) |

> All on Proxmox host 192.168.6.101 (`marketing-pc-ai`). VMIDs 107–109 are taken
> by orphaned/unrelated VMs; the active WIM set starts at 110. Note the node-name
> trap — `pct create` may report `VM <id> already exists on node 'proxsrv'` from
> stale cluster dirs; the real node is `marketing-pc-ai`.

### 8.2 Per-LXC setup (example — wim-api)
```bash
# Create privileged LXC from Debian 12 template
pct create 108 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
  --hostname wim-api --memory 1024 --cores 1 --storage local-lvm \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp

pct start 108
pct exec 108 -- apt update && pct exec 108 -- apt install -y python3 python3-pip
# Copy serve.py + install deps
pct push 108 ./api/serve.py /opt/wim-api/serve.py
# systemd unit reads /etc/wim/env
```

### 8.3 Option: Keep current monolith on LXC 106, then split
Rein already has the full stack on LXC 106 as a working monolith. The split into
separate LXCs/docker is an **evolution**, not a rebuild. Deploy order:
1. Stand up `wim-db` (or reuse PG on 106) ✅ already done
2. Stand up `wim-api` pointing at PG
3. Stand up `sales-app` pointing at wim-api
4. Stand up `admin-panel` pointing at PG
5. Update NPMplus to route to the new containers

---

## 9. Image Builds

### 9.1 api/Dockerfile
```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY serve.py .
EXPOSE 8000
CMD ["python", "serve.py"]
```
**requirements.txt:**
```
psycopg2-binary>=2.9
bcrypt>=4.0
```

### 9.2 sales-app/Dockerfile
```dockerfile
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY www/ /usr/share/nginx/html/
EXPOSE 80
```
**nginx.conf:**
```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://wim-api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### 9.3 admin/Dockerfile
```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY admin-server.py .
EXPOSE 8001
CMD ["python", "admin-server.py"]
```

### 9.4 Build notes
- Keep images slim (`-slim`/`-alpine`) — small attack surface, fast pulls.
- Tag with version/date: `wim-api:20260909`.
- Never bake secrets into images — always env at runtime.

---

## 10. Production vs Development Servers

Two parallel environments. The production server hosts the **1-month sales pilot**.

### 10.1 Dev Server (current)
| Attribute | Value |
|-----------|-------|
| Host | LXC 106 monolith (199. appreciated), then split to LXC 107–110 |
| Public | `sales.sqa.web.id` |
| Purpose | Build/test features, QA loops, 3-subagent verification |
| Data | Dev dataset (andi@wim.sales test account) |
| Secrets | `.env.dev` |

### 10.2 Production Server (for 1-month pilot)
| Attribute | Value |
|-----------|-------|
| Host | Separate Proxmox host or dedicated LXC set (prod 107–110) |
| Public | `wim.sqa.web.id` (prod) |
| Purpose | Live with **1 real sales member** for pilot |
| Data | Real WIM data (isolated `wim_sfa_prod`) |
| Secrets | `.env.prod` |
| DB | Backed up daily, off-host |

### 10.3 Keep them isolated
- Different databases (`wim_sfa` dev vs `wim_sfa_prod`).
- Different API consumers/keys.
- Different NPMplus hostnames.
- No code path shares secrets between them — only the repo does, via separate `.env.<env>`.

---

## 11. Scaling Path (Future)

The whole point of containerizing. When the sales-app frontend/API must scale:

| Scenario | Action |
|----------|--------|
| More sales reps / higher API load | Move `wim-api` to its own box (more CPU/RAM), keep DB where it is |
| Static asset spike | Spin up more `sales-app` replicas behind a load balancer / NPMplus |
| DB grows | Move `wim-db` to beefier storage, tune PG `shared_buffers` |
| Admin panel users grow | Keep admin on its own (cheap) box |

Because each service is a standalone image + env file, "moving the sales-app backend
and frontend to a stronger system" is literally: `docker compose pull` on the new host
with the same `.env` → run. No code changes.

---

## 12. Backup & Restore

### 12.1 Database (wim-db)
```bash
# In-container dump
docker exec wim-db pg_dump -U postgres wim_sfa > backup_$(date +%F).sql
# Restore
docker exec -i wim-db psql -U postgres wim_sfa < backup_20260909.sql
```

### 12.2 Proxmox
```bash
# Backup LXC (wgives linux container backups)
pct backup 107 /var/lib/vz/dump/  # wim-db
```
Use Proxmox's scheduled backup or a nightly cron on the host.

### 12.3 Pictures (base64 in DB)
Photos are stored as base64 inside the DB — **backing up PG backs up photos.** Keep
`wim_visits.photos`, `wim_attendance.*_photo`, `wim_stores.*` in the dump.

---

## 13. Monitoring & Health Checks

Each service exposes a health endpoint checked by NPMplus / uptime bot:

| Service | Endpoint | Expected |
|---------|----------|----------|
| wim-db | `pg_isready` | `accepting connections` |
| wim-api | `GET /healthz` | `{"status":"ok","db":"connected"}` |
| sales-app | `GET /` | `200 index.html` |
| admin-panel | `GET /api/admin/session` | 200 or 401 (auth gate) |

Add the 4 services to the existing Uptime Kuma / Beszel monitor (Rein runs at
:30038 / beszel).

---

## 14. Testing Period (1-Month Sales Pilot)

### 14.1 Goal
Validate the **core sales workflows** with **one real sales rep** on the production
server for 1 month.

### 14.2 In-scope for the pilot (core functions)
| Feature | Table/API | Priority |
|---------|-----------|----------|
| ✅ Auth (login) | `wim_users`, `/api/auth/*` | Core |
| ✅ Absensi clock-in/out + photo | `wim_attendance` | Core |
| ✅ Visit plan (route + luar rute) | `wim_visit_plan` | Core |
| ✅ Check-in/out + 3-min timer | `wim_visits` | Core |
| ✅ Photo capture (multi) | `wim_visits.photos` | Core |
| ✅ Order creation | `wim_orders` + items | Core |
| ✅ No-order reason | `wim_visits.notes` | Core |
| ✅ Stock check (one-tap) | `wim_stock_check` | Important |
| ⬜ Admin panel review | admin-panel | Important |

### 14.3 Out of scope (defer)
- Promo/bundling engine (post-pilot)
- Analytics dashboards (post-pilot)
- Odoo / Fleetbase sync (post-pilot — see FUTURE-INTEGRATION.md)
- PDF/Excel exports (post-pilot)

### 14.4 Pilot success criteria
- Sales rep completes **daily visits** with zero data loss.
- Clock-in/out and check-in/out persist reliably (reload → data stays — **no localStorage**).
- Orders created by the rep appear in the DB and admin panel.
- No 500 errors. Photos save and reload.

### 14.5 Pilot workflow
1. Deploy prod stack (docker or LXC 107–110) + `wim_sfa_prod`.
2. Seed prod: the pilot rep's account, their store list, route plan.
3. Give the rep the prod URL + credentials.
4. Weekly: I pull a report (`/api/report`) and confirm data integrity.
5. End of month: compare pilot data against expectations (visit counts, orders, stock).
6. Gate: if pilot passes, roll out to the full sales team.

---

## 15. Admin Panel Migration (prerequisite)

Before building the `admin-panel` container, migrate `admin/admin-server.py` from
`pymysql`/`fleetbase` to `psycopg2`/`wim_sfa`:
- Replace MySQL connection (`pymysql.connect(MYSQL_*)`) with PG (`psycopg2.connect(WIM_PG_*)`).
- Replace MySQL query syntax with PostgreSQL (same drift fixes as serve.py).
- Use `wim_sessions` / `wim_users` for auth (standalone PostgreSQL).
- Rename env vars from `WIM_MYSQL_*`/`FLEETBASE_API` to `WIM_PG_*`.
- This is tracked as the current active task; when serve.py's API work completes, apply the same to admin-server.py.