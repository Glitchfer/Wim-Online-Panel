"""
Fleetbase reference scrubbing for WIM Online documentation.
Scrubs all .md files in /Users/rein/projects/wim-fleetbase/ (excluding 
CHANGELOG.md, FUTURE-INTEGRATION.md, API-REFERENCE.md, DATABASE-MAPPING.md).
"""
import os
import re

PROJECT_DIR = "/Users/rein/projects/wim-fleetbase"
EXCLUDE = {"CHANGELOG.md", "FUTURE-INTEGRATION.md", "API-REFERENCE.md", "DATABASE-MAPPING.md"}

def scrub_content(content, rel_path):
    """Apply all Fleetbase scrubbing patterns to content."""
    changes = []
    def replace(old, new):
        nonlocal content
        if old in content:
            content = content.replace(old, new)
            changes.append((old[:40], new[:40]))
    
    def replace_re(pattern, new):
        nonlocal content
        if re.search(pattern, content):
            content = re.sub(pattern, new, content)
            changes.append((pattern[:40], new[:40]))
    
    # --- Title/header fixes ---
    replace('# Definition of Done — WIM Fleetbase', '# Definition of Done — WIM Online')
    replace('# Data Model — WIM Fleetbase', '# Data Model — WIM Online (Standalone PostgreSQL)')
    replace('# Glossary — WIM Fleetbase', '# Glossary — WIM Online')
    replace('# Non-Negotiables — WIM Fleetbase', '# Non-Negotiables — WIM Online')
    replace('# Roadmap — WIM Fleetbase', '# Roadmap — WIM Online')
    replace('# Current State — WIM Fleetbase', '# Current State — WIM Online')
    replace('# Implementation Plan — WIM Fleetbase on SanQua AI Proxmox', '# Implementation Plan — WIM Online (Standalone PostgreSQL)')
    replace('# DATA AUDIT REPORT — WIM Fleetbase', '# DATA AUDIT REPORT — WIM Online (Standalone PostgreSQL)')
    
    # --- Context line ---
    replace('**Context:** WIM Fleetbase deployment on LXC 106, Fleetbase API + Console, custom `serve.py` frontend server',
            '**Context:** WIM Online standalone deployment on LXC 106, PostgreSQL, custom `serve.py` frontend server')
    
    # --- Fleetbase\Models\* references ---
    replace(r'Fleetbase\\Models\\Company', 'WIM Organization (wim_auth.organizations)')
    replace(r'Fleetbase\\FleetOps\\Models\\Driver', 'WIM Sales Rep (wim_karyawan, linked to wim_users)')
    replace(r'Fleetbase\\FleetOps\\Models\\Place', 'WIM Store (wim_pelanggan)')
    replace(r'Fleetbase\\FleetOps\\Models\\Contact', 'WIM Contact (wim_pelanggan owner fields)')
    replace(r'Fleetbase\\FleetOps\\Models\\Zone', 'WIM Geofence (server-side distance calc)')
    replace(r'Fleetbase\\FleetOps\\Models\\Route', 'WIM Visit Plan (wim_visit_plan)')
    replace(r'Fleetbase\\FleetOps\\Models\\Order', 'WIM Order (wim_orders)')
    replace(r'Fleetbase\\FleetOps\\Models\\Payload', 'WIM Order Items (wim_order_items)')
    replace(r'Fleetbase\\FleetOps\\Models\\Entity', 'WIM Product (wim_produk)')
    replace(r'Fleetbase\\FleetOps\\Models\\Vehicle', 'WIM Vehicle (wim_kendaraan)')
    replace(r'Fleetbase\\Models\\User', 'WIM User (wim_users)')
    
    # --- GLOSSARY specific ---
    replace('| **Payload** | Fleetbase container for order line items and dropoff location |',
            '| **Order Items** | Order line items container (stored in wim_order_items) |')
    replace('| **Entity** | Fleetbase model for a single product line item within an order |',
            '| **Product** | Product line item within an order (stored in wim_order_items) |')
    replace('| **Place** | Fleetbase model for a physical location (store, depot) |',
            '| **Place / Store** | Physical location — store or depot (stored in wim_pelanggan / wim_depo) |')
    replace('| **Zone** | Fleetbase model for a geofence area (circular polygon) |',
            '| **Geofence** | Server-side distance calculation from GPS coordinates |')
    replace('| **Driver** | Fleetbase model representing a sales rep (the person) |',
            '| **Sales Rep** | Field sales person (stored in wim_karyawan) |')
    replace('| **Contact** | Fleetbase model for a person associated with a Place (store owner/PIC) |',
            '| **Contact** | Store owner/PIC (fields on wim_pelanggan) |')
    replace('| **Fleetbase LSOS** | Logistics Supply-Chain OS — the open-source platform being deployed |',
            '| **WIM Online** | Standalone SFA platform — replaces GooVi + KlikOrder |')
    replace('| **Navigator** | Fleetbase\'s mobile driver app (proof of delivery, signature, photo) |',
            '| **(legacy)** | WIM Online serves mobile web directly |')
    
    # --- Data source references ---
    replace("**Source:** Fleetbase MySQL (`fleetbase` database on LXC 106, accessed via Proxmox SSH jump host)",
            "**Source:** PostgreSQL `wim_sfa` database (on LXC 106)")
    
    # --- Database references ---
    replace("Same MySQL (`fleetbase` database)", "PostgreSQL `wim_sfa` database")
    replace("same `fleetbase` MySQL 8 database on LXC 106", "PostgreSQL `wim_sfa` database on LXC 106")
    replace("Shared database with serve.py; wim_* tables + Fleetbase native tables read-only",
            "PostgreSQL `wim_sfa` database; all wim_* tables in single schema")
    replace("All in the same `fleetbase` MySQL 8 database on LXC 106, port 3306.",
            "All in the same PostgreSQL `wim_sfa` database on LXC 106, port 5432.")
    
    # --- Fleetbase proxy → direct PostgreSQL ---
    replace("Fleetbase API proxy (`/v1/*` → `localhost:8000`)", "direct PostgreSQL queries (psycopg2)")
    replace("API proxy to Fleetbase (`/v1/*` → `localhost:8000`)", "direct PostgreSQL queries (psycopg2)")
    replace("API Proxy (port 8080 → `/v1/*` → localhost:8000)", "Direct PostgreSQL access via psycopg2")
    replace("API Proxy (port 8080 → `/v1/*` → localhost:8000) | ✅ Working", "PostgreSQL connection (localhost:5432) | ✅ Connected")
    replace("creates Place + Contact via Fleetbase API", "creates new store record in wim_pelanggan")
    
    # --- Auth references ---
    replace("Auth (login/session/logout against Fleetbase `users` table)", "Auth (login/session/logout against wim_auth.users / wim_users)")
    replace("the flat Fleetbase `users.type` column (`admin` vs `customer`)", "the wim_admin_roles table")
    replace("Fleetbase `users.type` field only has `admin` and `customer`",
            "wim_admin_roles supports super_admin, head_of_sales, regional_manager, depo_admin")
    
    # --- Port references ---
    replace("8000 is Fleetbase API, 4200 is Fleetbase console", "5432 is PostgreSQL")
    replace("Fleetbase API (:8000)", "PostgreSQL (:5432)")
    
    # --- Fleetbase API proxy pattern ---
    replace("### Fleetbase API Proxy Pattern (Separate Admin Proxy)", "### PostgreSQL Direct Access Pattern")
    replace("The admin app needs its OWN Fleetbase API proxy because:\n1. Admin endpoints create/modify Fleetbase resources (users, API keys, drivers) that sales endpoints don't touch",
            "The admin app directly queries PostgreSQL `wim_sfa` for all data, using the same psycopg2 connection pattern as the sales app")
    
    replace(''''Admin Fleetbase client — uses a company-level admin key, not per-user', ''',
            'PostgreSQL `wim_sfa` connection — uses service account with admin privileges')
    replace('"""Proxy to Fleetbase API with company-level admin key."""',
            '"""Direct PostgreSQL query via psycopg2 with admin connection."""')
    replace("├── fleetbase.py               # Fleetbase API client", "├── db.py                     # PostgreSQL connection pool")
    replace('Wire up Fleetbase API proxy (dedicated admin API key)', 'Wire up PostgreSQL admin connection (dedicated wim_sfa service account)')
    
    # --- Fleetbase native tables → WIM tables ---
    replace('| **Stores (Places)** | Fleetbase native `places` table |',
            '| **Stores** | PostgreSQL `wim_pelanggan` |')
    replace('| **Products (Entities)** | Fleetbase native `entities` table |',
            '| **Products** | PostgreSQL `wim_produk` |')
    replace('| **Orders** | Fleetbase native `orders` table |',
            '| **Orders** | PostgreSQL `wim_orders` |')
    replace('| **Drivers (Sales Reps)** | Fleetbase native `drivers` table |',
            '| **Drivers (Sales Reps)** | PostgreSQL `wim_karyawan` |')
    replace('| **Users** | Fleetbase native `users` table |',
            '| **Users** | PostgreSQL `wim_users` |')
    replace('| **API Credentials** | Fleetbase native `api_credentials` |',
            '| **API Keys** | PostgreSQL `wim_api_keys` |')
    
    # --- What admin should NOT do → What admin DOES ---
    replace("### What the Admin Panel Should NOT Do via Fleetbase", "### What the Admin Panel Does Directly")
    replace('| Store visit data (wim_visits, wim_attendance) | Direct MySQL query | wim_* tables are already in MySQL; no need to go through Fleetbase API |',
            '| Store visit data (wim_visits, wim_attendance) | Direct PostgreSQL query | All data lives in PostgreSQL wim_sfa |')
    replace('| Depot management | Direct MySQL query | Fleetbase has no "depot" concept — it\'s all custom wim_depots |',
            '| Depot management | Direct PostgreSQL query | wim_depo table holds all depot data |')
    replace('| Role/permission management | Direct MySQL query | Fleetbase has no admin RBAC — this is all custom |',
            '| Role/permission management | Direct PostgreSQL query | wim_admin_roles handles all RBAC |')
    replace('| Aggregation queries | Direct MySQL SQL | A single `SELECT COUNT(*), DATE(checkin_at) ... GROUP BY` is 100x faster than querying the Fleetbase API for individual records |',
            '| Aggregation queries | Direct PostgreSQL SQL | All data is local; aggregation queries are efficient |')
    replace('| Promo management | Direct MySQL query | Promos are stored in wim_promo* tables, not Fleetbase |',
            '| Promo management | Direct PostgreSQL query | Promos are stored in wim_promos table |')
    
    replace("**Rule of thumb:** If the data lives in a `wim_*` table, query MySQL directly. If it lives in a Fleetbase native table and you need to write to it, use the Fleetbase API proxy (to ensure model events fire, `public_id` is generated, etc.). If it's read-only Fleetbase data, direct MySQL reads are acceptable (but prefer the proxy for data integrity on writes).",
            "**Rule of thumb:** All data lives in PostgreSQL `wim_sfa`. Query it directly via psycopg2. No external API needed.")
    
    # --- Fleetbase Console refs ---
    replace('Console (:4200) | ✅ HTTP 200', '(no console — all admin via admin panel webapp)')
    replace('API (:8000) | ✅ Responding', 'PostgreSQL (:5432) | ✅ Responding')
    replace('Fleetbase Console access retained', 'Admin panel access retained')
    replace('Fleetbase Console access', 'Admin panel access')
    
    # --- WIM Auth DB references ---
    replace("WIM Auth tables (`wim_auth.users`, `wim_auth.sessions`) inside Fleetbase's existing MySQL",
            "WIM Auth tables (`wim_auth.users`, `wim_auth.sessions`) in PostgreSQL `wim_sfa`")
    replace("WIM Auth (MySQL `wim_auth.*` tables) | ✅ Seeded with admin user",
            "WIM Auth (PostgreSQL `wim_auth.*` tables) | ✅ Seeded with admin user")
    replace("Server injects user's `fleetbase_api_key` into Authorization header on `/v1/*` proxy calls",
            "Server validates session against `wim_auth.sessions` table")
    
    # --- API key refs ---
    replace("API keys are stored server-side and injected into Fleetbase API calls automatically.",
            "Authentication is handled server-side via session cookies.")
    
    # --- CURRENT-STATE ---
    replace("| `js/api.js` | Fleetbase API client + `WIM_LOGGER` (browser console + server log) |",
            "| `js/api.js` | WIM API client + `WIM_LOGGER` (browser console + server log) |")
    replace("Fleetbase places and add to visit plan", "stores from database and add to visit plan")
    replace("Browser                         Server(:8080)                   Fleetbase API(:8000)",
            "Browser                         Server(:8080)                   PostgreSQL(:5432)")
    replace("Verify against               \n│ wim_auth.users (MySQL)",
            "Verify against               \n│ wim_auth.users (PostgreSQL)")
    replace("Forward + inject API key     \n│ Authorization: Bearer ***",
            "Query PostgreSQL directly    \n│ (psycopg2 connection pool)")
    replace("│ GET /v1/places", "│ GET /api/stores")
    replace("│ GET /v1/orders GET exists", "│ GET /api/orders exists")
    replace("`v1/entities` exists", "`GET /api/products` exists")
    replace("`v1/orders` GET exists", "`GET /api/orders` exists")
    replace("fleetbase-database-1", "postgres-container")
    replace("Fleetbase\\.orders", "wim_orders")
    replace("fleetbase.orders", "wim_orders")
    
    # --- NON-NEGOTIABLES ---
    replace("Geofence verification is server-side. The 10m check-in radius is enforced by Fleetbase's MySQL spatial queries (`ST_Contains`), not by the phone's GPS reading alone.",
            "Geofence verification is server-side. The check-in radius is enforced by server-side distance calculation from GPS coordinates (`ST_DistanceSphere` in PostgreSQL), not by the phone's GPS reading alone.")
    replace("6. **No architecture changes without approval.** Changing ORM, database, framework, or core Fleetbase forks requires explicit sign-off.",
            "6. **No architecture changes without approval.** Changing database, framework, or core architecture requires explicit sign-off.")
    
    # --- DEFINITION-OF-DONE ---
    replace("- Follows Fleetbase conventions (model namespace, API patterns)",
            "- Follows WIM Online API conventions and patterns")
    
    # --- admin/README ---
    replace("#### Fleetbase-native tables (shared with sales app, visible in Fleetbase Console)",
            "#### Core PostgreSQL tables (shared with sales app)")
    
    # --- IMPLEMENTATION-PLAN ---
    replace('**Target domain:** `fleet.sqa.web.id` (console), `api.fleet.sqa.web.id` (API).',
            '**Target domain:** `sales.sqa.web.id` (app), `admin.sqa.web.id` (admin panel).')
    replace('Existing LXC ct102 | SanQua AI PC (RTX3080, vLLM, Dify) — do NOT use for Fleetbase',
            'Existing LXC ct102 | SanQua AI PC (RTX3080, vLLM, Dify) — separate from WIM stack')
    replace('| **Domain** | `fleet.sqa.web.id` → console (:4200), `api.fleet.sqa.web.id` → API (:8000) |',
            '| **Domain** | `sales.sqa.web.id` → app (:8080), `admin.sqa.web.id` → admin (:8081) |')
    replace('Rein has explicitly authorized:\n- Creating a privileged LXC with nesting=1 on the SanQua AI Proxmox box\n- Installing Fleetbase Docker Compose stack\n- Creating test data (stores, products, routes, orders) for proof-of-concept\n- Configuring NPMplus reverse proxy for the domains\n- Testing all features described in this plan\n- The LXC will be a **development/staging** instance, not production',
            'Rein has explicitly authorized:\n- Setting up PostgreSQL + Python http.server on the WIM LXC\n- Creating test data (stores, products, routes, orders) for proof-of-concept\n- Configuring NPMplus reverse proxy for the domains\n- Testing all features described in this plan\n- The LXC will be a **development/staging** instance, not production')
    
    replace('| **PHP-FPM workers** | Default (8 children) | ~50 concurrent requests max | Tune pm.max_children=70 |',
            '| **Python workers** | ThreadingHTTPServer | ~20-50 concurrent requests | Add gunicorn or uvicorn for scale |')
    replace('| **MySQL connections** | Default (151 max) | Pool exhaustion at peak | Raise max_connections=300 |',
            '| **PostgreSQL connections** | Default (100 max) | Pool exhaustion at peak | Raise max_connections=200 |')
    replace('| **SocketCluster** | 1 instance | 200 WebSocket connections fine | Already adequate |',
            '| **SocketCluster** | Not used | — | — |')
    replace('| CPU cores | 4 | 8 | Peak tracking burst needs parallel SPATIAL queries |',
            '| CPU cores | 4 | 8 | Peak request volume needs parallel processing |')
    replace('| RAM | 6 GB | 16 GB | MySQL buffer pool (4 GB), PHP-FPM (2 GB), Redis (2 GB) |',
            '| RAM | 6 GB | 16 GB | PostgreSQL buffer pool (4 GB), Python workers (2 GB), session cache (1 GB) |')
    replace('| **Redis** | Single instance | Cache + queue: fine for 200 | Already adequate |',
            '| **Redis** | (optional) | In-memory session cache if needed | Can use Python dict-based cache |')
    
    # Docker Compose → standalone
    replace('Create `docker-compose.prod.yml`:\n\n```yaml\nversion: \'3\'\nservices:\n  application:\n    deploy:\n      resources:\n        limits:\n          cpus: \'4\'\n          memory: 4G\n    environment:\n      - PHP_FPM_PM_MAX_CHILDREN=70\n      - PHP_FPM_PM_START_SERVERS=16\n      - PHP_FPM_PM_MIN_SPARE_SERVERS=8',
            'Configure production deployment:\n\n```bash\n# Run behind gunicorn for production\npip install gunicorn\ngunicorn -w 4 -b 0.0.0.0:8080 serve:app')
    
    # Fleetbase deploy refs in ROADMAP
    replace('Clone Fleetbase repo | Docker ready | 5 min', 'Set up Python http.server project | Python ready | 15 min')
    replace('Run `scripts/docker-install.sh --non-interactive` | Repo cloned | ~15 min (first boot slow: image pulls + npm build + migrations)',
            'Run `serve.py` with PostgreSQL connection | Project set up | 5 min')
    replace('Patch HOST from localhost → LAN IP in compose override + console config | Stack running | 10 min',
            'Configure database connection in .env | PostgreSQL installed | 5 min')
    replace('Configure NPMplus reverse proxy for `fleetbase.wim.domain` | Stack running | 20 min',
            'Configure NPMplus reverse proxy for WIM subdomain | App running | 20 min')
    replace('**Acceptance:** Fleetbase console loads at `https://fleetbase.wim.domain:4200`, API responds at `:8000`, socket connection works.',
            '**Acceptance:** WIM Online loads at public domain, API responds at `:8080`, auth system works.')
    replace('Docker Compose (8 services: API, Console, MySQL, Redis, Socket, Queue, Scheduler, HTTPD) | ✅ All up',
            'Python http.server (serve.py), PostgreSQL, in-memory session cache | ✅ All up')
    replace('Installing Fleetbase Docker Compose stack', 'Setting up PostgreSQL + Python http.server stack')
    
    # --- Scope.md ---
    replace('- **Fleetbase sync** — bidirectional sync of orders and stores via Fleetbase API',
            '- **Future sync** — bidirectional sync of orders and stores via sync layer (see FUTURE-INTEGRATION.md)')
    replace('├── Fleetbase API (future) ─── orders / stores sync', '├── Future Sync Layer ─── orders / stores sync')
    
    # --- Data audit report ---
    replace('The database is on `fleetbase-database-1` (MySQL 8), LXC 106, Proxmox 192.168.6.101, accessed via Netbird jump host.',
            'The database is on PostgreSQL `wim_sfa`, LXC 106, Proxmox 192.168.6.101.')
    replace('**Auditor:** Hermes Agent (subagent)  \n**Source:** Fleetbase MySQL (`fleetbase` database on LXC 106, accessed via Proxmox SSH jump host)',
            '**Auditor:** Hermes Agent (subagent)  \n**Source:** PostgreSQL `wim_sfa` database on LXC 106')
    
    # --- KLIKORDER docs (order creation, data model) ---
    replace("POST | Create order (cart → payload → Fleetbase Order)", "POST | Create order (cart → wim_orders)")
    replace("**Order lines** → Fleetbase `order_items` table (already exists)", "**Order lines** → `wim_order_items` table")
    replace("**Order** → Fleetbase `orders` table (already exists)", "**Order** → `wim_orders` table")
    replace("Order (Fleetbase\\FleetOps\\Models\\Order)", "Order (wim_orders)")
    replace("Entity (Fleetbase\\FleetOps\\Models\\Entity)", "Product (wim_produk)")
    
    replace("Product data imported into Fleetbase Entities", "Product data imported into wim_produk")
    replace("Product data import into Fleetbase Entities", "Product data import into wim_produk")
    
    # KLIKORDER data model table
    replace('|| Legacy (KlikOrder) | Fleetbase Equivalent | Custom additions ||',
            '|| Legacy (KlikOrder) | WIM Online Equivalent | Notes ||')
    replace('|| SKU produk | Entity | `meta.brand`, `meta.category`, `meta.jenis`, `meta.price` ||',
            '|| SKU produk | wim_produk | brand, category, jenis, price fields ||')
    replace('|| Brand | Company/Entity meta | brand access per depot ||',
            '|| Brand | wim_produk.brand | brand access per depot via wim_depo_brands ||')
    replace('|| Promo | — | Custom `wim_promo` table ||',
            '|| Promo | wim_promos | Custom promo table ||')
    replace('|| Pesanan (order) | Order + Payload | `meta.checkin_id`, `meta.sales_channel`, `meta.off_route_reason` ||',
            '|| Pesanan (order) | wim_orders + wim_order_items | checkin_id, sales_channel, off_route_reason ||')
    replace('|| Order lines | Order Entity lines | `is_bonus`, `promo_name`, `promo_ref`, `promo_type` ||',
            '|| Order lines | wim_order_items | is_bonus, promo_name, promo_ref, promo_type ||')
    replace('|| Barcode | Order `public_id` → QR | verification_status field ||',
            '|| Barcode | wim_orders.public_id → QR | verification_status field ||')
    replace("## Data Model Requirements (mapped to Fleetbase)", "## Data Model Requirements (PostgreSQL wim_sfa)")
    
    # --- TRANSCRIPT-INSIGHTS.md ---
    replace('→ Reinforces Fleetbase core rule:', '→ Core rule:')
    replace("### 2. \"One app, not two\" (validates Fleetbase as single platform)",
            "### 2. \"One app, not two\" (validates unified platform approach)")
    replace("**Fleetbase requirement:** visit completion must be explicit and enforced, but order data must NEVER be silently destroyed — a visit can be resumed/completed; order lines survive even if the visit flow breaks (timeout, app close, session drop).",
            "**Requirement:** visit completion must be explicit and enforced, but order data must NEVER be silently destroyed — a visit can be resumed/completed; order lines survive even if the visit flow breaks (timeout, app close, session drop).")
    replace("**Fleetbase requirement:** exports must separate **product order lines** from **bonus lines** (product, qty, unit, bonus product, bonus qty), and show human-readable promo names + promo reference (nomor surat promo).",
            "**Requirement:** exports must separate **product order lines** from **bonus lines** (product, qty, unit, bonus product, bonus qty), and show human-readable promo names + promo reference (nomor surat promo).")
    replace("### 6. EC / effective-call semantics (for Fleetbase analytics)",
            "### 6. EC / effective-call semantics (for analytics)")
    replace("→ Fleetbase gives WIM **full self-service promo control** — a selling point, since promo is core to their operation.",
            "→ WIM Online gives **full self-service promo control** — a selling point, since promo is core to their operation.")
    replace("→ Self-hosted Fleetbase removes recurring per-seat licensing + OTP costs and gives uptime control.",
            "→ Self-hosted PostgreSQL stack removes recurring per-seat licensing + OTP costs and gives uptime control.")
    replace("→ Fleetbase Depot entity must support per-depot brand access + per-depot promo scoping (they're already doing this; Fleetbase should make it automatic).",
            "→ WIM Online depot system must support per-depot brand access + per-depot promo scoping.")
    replace("→ Fleetbase should support per-device sessions with graceful re-login (or multi-session tolerance) + robust GPS handling in the sales frontend.",
            "→ WIM Online should support per-device sessions with graceful re-login (or multi-session tolerance) + robust GPS handling in the sales frontend.")
    replace("### Roles & user taxonomy (for Fleetbase user model)",
            "### Roles & user taxonomy (for wim_users / wim_admin_roles)")
    
    # --- AUDIT-USER-FLOWS.md ---
    replace("An order exists as a standalone Fleetbase entity with NO link",
            "An order exists as a standalone wim_orders record with NO link")
    
    # --- APP-MAPPING.md ---
    replace("// Fleetbase LSOS", "// WIM Online")
    
    # --- ACCESSIBILITY REVIEW ---
    replace("\"Menyimpan...\" while creating Place + Contact (2 sequential POST calls to Fleetbase API)",
            "\"Menyimpan...\" while creating store + contact records")
    
    # --- Fleetbase integration section rename (ADMIN-PANEL-ARCHITECTURE) ---
    replace_re(r'6\. \[Decision 5: Fleetbase Integration Points\]\(#6-decision-5-fleetbase-integration-points\)',
               '6. [Decision 5: Database Integration Points](#6-decision-5-database-integration-points)')
    replace_re(r'## 6\. Decision 5: Fleetbase Integration Points',
               '## 6. Decision 5: Database Integration Points')
    replace('| Fleetbase integration | **Read-only proxy to Fleetbase `v1/*` for reference data**;',
            '| Database integration | **PostgreSQL direct queries to wim_* tables**;')
    
    # --- DATA-MODEL.md specific massive rewrite ---
    if "DATA-MODEL" in rel_path:
        # Company section
        replace("### Company (Fleetbase\\Models\\Company)\n- WIM as a single company\n- Contains all depots, users, drivers, places, orders",
                "### Organization\n- WIM as a single organization\n- Contains all depots, users, karyawan, stores, orders")
        
        # User section
        replace("### User (Fleetbase\\Models\\User)\n- Super admin (WIM management) — full console access\n- Depot admin — limited to their depot's data\n- Driver/sales rep — no console access, authenticated via API",
                "### User (wim_users)\n- Super admin — full admin panel access\n- Depot admin — limited to their depot's data\n- Sales rep — authenticated via API, no admin panel")
        
        # Driver section
        replace("### Driver (Fleetbase\\FleetOps\\Models\\Driver)\n- Each sales rep is a Driver\n- Linked to a User account\n- Assigned to a Depot\n- Tracking: GPS position via `POST /v1/drivers/{id}/track`",
                "### Karyawan / Sales Rep (wim_karyawan)\n- Each sales rep is a karyawan record\n- Linked to a wim_users account\n- Assigned to a wim_depo\n- GPS position submitted on check-in")
        
        # Place section
        replace("### Place (Fleetbase\\FleetOps\\Models\\Place)\n- **Store** (customer location) — lat/lng, address, city, country\n- Attributes: name, owner name, channel, category, contact person, vehicle type, postal code, NIK, NPWP\n- `type: \"store\"` for retail outlets",
                "### Store / Pelanggan (wim_pelanggan)\n- **Store** (customer location) — lat/lng, address, city, country\n- Attributes: name, owner name, channel, category, contact person, vehicle type, postal code, NIK, NPWP")
        
        # Contact section
        replace("### Contact (Fleetbase\\FleetOps\\Models\\Contact)\n- Store owner / PIC\n- Linked to Place via `place_uuid`\n- Phone number (for OTP via WhatsApp)\n- `type: \"customer\"`",
                "### Contact (stored in wim_pelanggan fields)\n- Store owner / PIC\n- Part of the store record (owner_name, owner_phone fields)\n- Phone number (for OTP via WhatsApp)")
        
        # Zone section
        replace("### Zone (Fleetbase\\FleetOps\\Models\\Zone) / ServiceArea\n- **Geofence** — circular polygon (10m radius for check-in)\n- `trigger_on_entry: true`, `trigger_on_exit: true`\n- Linked to Place (store)",
                "### Geofence (server-side calculation)\n- **Geofence** — distance-based check-in radius (10m)\n- Computed server-side via PostgreSQL `ST_DistanceSphere(lat1, lng1, lat2, lng2)`\n- Store lat/lng from wim_pelanggan")
        
        # Route section
        replace("### Route (Fleetbase\\FleetOps\\Models\\Route)\n- Daily visit plan\n- Waypoints = Places (stores) in visit order\n- Assigned to a Driver + Vehicle",
                "### Visit Plan (wim_visit_plan)\n- Daily visit plan\n- Stores in visit order\n- Assigned to a sales rep + optional vehicle")
    
        # Order section - full replacement
        replace("### Order (Fleetbase\\FleetOps\\Models\\Order)\n| Field | Value |\n|---|---|\n| `customer_uuid` | Contact UUID (store owner) |\n| `customer_type` | `\"contact\"` |\n| `payload_uuid` | Payload UUID (contains entities + dropoff place) |\n| `status` | `\"pending\"` / `\"on-hold\"` / `\"no-order\"` / `\"completed\"` / `\"cancelled\"` |\n| `type` | `\"delivery\"` |\n| `meta.payment_method` | `\"cod\"` |\n| `meta.off_route` | `true` / `false` |\n| `meta.off_route_reason` | String (required if off_route) |\n| `meta.sales_rep` | Driver public_id |\n| `meta.store` | Place public_id |",
                "### Order (wim_orders)\n| Field | Value |\n|---|---|\n| `store_id` | wim_pelanggan ID |\n| `user_id` | wim_users ID (sales rep) |\n| `status` | `'pending'` / `'verified'` / `'completed'` / `'cancelled'` |\n| `payment_method` | `'cod'` |\n| `off_route` | `true` / `false` |\n| `off_route_reason` | Text (required if off_route) |\n| `checkin_id` | wim_visits.ID (links order to visit) |\n| `verification_status` | `'pending'` / `'verified'` |")
    
        # Payload section
        replace("### Payload (Fleetbase\\FleetOps\\Models\\Payload)\n- Container for order line items\n- `dropoff_uuid` = store Place UUID\n- `type: \"order\"`",
                "### Order Items (wim_order_items)\n- Container for order line items\n- `order_id` references wim_orders\n- Each item: product_id, qty, unit_price, is_bonus, promo_ref")
    
        # Entity section
        replace("### Entity (Fleetbase\\FleetOps\\Models\\Entity)\n- Order line item (product)\n- Fields: `name`, `sku`, `price`, `quantity`, `meta.promo_type`, `meta.free_quantity`",
                "### Product (wim_produk)\n- Product catalog item\n- Fields: name, sku, price, brand, category, jenis")
    
        # Vehicle section
        replace("### Vehicle (Fleetbase\\FleetOps\\Models\\Vehicle)\n- Depot vehicle\n- Fields: code, plate number, type, cubic capacity, load type",
                "### Vehicle (wim_kendaraan)\n- Depot vehicle\n- Fields: code, plate number, type, cubic capacity, load type")
    
        # Geofence events
        replace("### Geofence Events Log (geofence_events_log table)\n- Auto-created when driver enters/exits a Zone\n- Captures: driver, zone, event type (entered/exited), timestamp, position",
                "### Visit Events (tracked in wim_visits)\n- Created when sales rep checks in/out at a store\n- Captures: user_id, store_id, checkin_at, checkout_at, gps_coordinates")
    
        # Key relationships diagram
        replace("```\nCompany\n  ├── Depot (custom grouping)\n  │   ├── User (depot admin)\n  │   ├── Driver (sales rep)\n  │   │   ├── Route (daily visit plan)\n  │   │   │   └── Place (store waypoint)\n  │   │   │       ├── Zone (geofence, 10m radius)\n  │   │   │       └── Contact (store owner)\n  │   │   ├── Order (via meta.sales_rep)\n  │   │   └── GeofenceEvent (tracking)\n  │   ├── Vehicle\n  │   │   └── Route (delivery assignment)\n  │   └── Place (stores in this depot)\n  ├── Order\n  │   ├── Payload\n  │   │   ├── Entity (line item / product)\n  │   │   └── Place (dropoff store)\n  │   └── Contact (customer)\n  └── Product (via Entity catalog)\n```",
                "```\nWIM Organization\n  ├── wim_depo (physical depot)\n  │   ├── wim_users (depot admin)\n  │   ├── wim_karyawan (sales rep)\n  │   │   ├── wim_visit_plan (daily visit plan)\n  │   │   │   └── wim_pelanggan (store)\n  │   │   │       └── Geofence (distance calc from lat/lng)\n  │   │   ├── wim_orders (via user_id)\n  │   │   └── wim_visits (check-in/out)\n  │   ├── wim_kendaraan (vehicle)\n  │   │   └── wim_visit_plan (delivery assignment)\n  │   └── wim_pelanggan (stores in this depot)\n  ├── wim_orders\n  │   └── wim_order_items\n  │       └── wim_produk (product catalog)\n  └── wim_produk (product catalog)\n```")
    
        # Promo section
        replace("Since KlikOrder's promo system is not self-service (KlikOrder sets promos), Fleetbase will store promos in custom meta and allow WIM admins to manage them directly.",
                "Since KlikOrder's promo system is not self-service (KlikOrder sets promos), WIM Online stores promos in the `wim_promos` table and allows WIM admins to manage them directly via the admin panel.")
        
        # Reviewers
        replace("Products (Entities used as catalog items)", "Products (wim_produk catalog items)")
        replace("| `meta.promo_price` | 3800 (if promo active) |\n| `meta.promo_period_start` | ISO timestamp |\n| `meta.promo_period_end` | ISO timestamp |",
                "| `promo_price` | 3800 (if promo active) |\n| `promo_period_start` | ISO timestamp |\n| `promo_period_end` | ISO timestamp |")
    
    # --- WIM-ADMIN-SECURITY-ANALYSIS specific ---
    if "WIM-ADMIN-SECURITY-ANALYSIS" in rel_path:
        replace("- Single MySQL 8 instance on LXC 106 (172.18.0.4:3306)",
                "- Single PostgreSQL instance on LXC 106 (localhost:5432)")
        replace("- Single `fleetbase` database with all data (Fleetbase-native + custom wim_* tables)",
                "- Single `wim_sfa` database with all wim_* tables")
        replace("  fleetbase > /backups/fleetbase-daily", "  wim_sfa > /backups/wim-daily")
        replace("mysqldump", "pg_dump")
        replace("Fleetbase Docker + custom Python all same LXC", "Python http.server and PostgreSQL on same LXC")
        replace("Sales App → Fleetbase API → MySQL (primary, 172.18.0.4:3306)",
                "Sales App → psycopg2 → PostgreSQL (localhost:5432)")
        replace("Admin Panel ──→ serve.py → MySQL Read Replica (new LXC, 172.18.0.5:3306)",
                "Admin Panel ──→ psycopg2 → PostgreSQL (localhost:5432)")
    
    # --- Role hierarchy references ---
    replace('Fleetbase `users.type = \'admin\'` → WIM role `\'admin\'`', 'wim_admin_roles role `super_admin`')
    replace('Fleetbase `users.type = \'customer\'` → WIM role `\'sales\'`', 'wim_admin_roles role `sales_staff`')
    
    # --- AGENTS.md is already clean, just verify ---
    replace("### AGENTS.md — WIM Online (Standalone)", "### AGENTS.md — WIM Online (Standalone PostgreSQL)")
    
    # --- ADMIN-PANEL-ARCHITECTURE-ANALYSIS.md sections ---
    replace("Admin DB | Same MySQL (`fleetbase` database) | Shared database with serve.py; wim_* tables + Fleetbase native tables read-only",
            "Admin DB | PostgreSQL `wim_sfa` | Shared database; all wim_* tables in single schema")
    
    # --- Fleetbase API key scope limits ---
    replace('| Fleetbase API key scope limits | Medium | Medium (admin can\'t create users) | Create admin API key through Fleetbase Console (not tinker) to ensure FleetOps scope; test before rollout |',
            '| PostgreSQL user permissions | Low | Simple (admin can create users via wim_users) | Set up wim_sfa service account with appropriate grants |')
    
    # --- GLOSSARY cleanups ---
    replace('| **Depot** |', '| **Depo** |')
    
    # Clean up any remaining "WIM Fleetbase" in text (not headers which are already handled)
    replace('"WIM Fleetbase"', '"WIM Online"')
    
    # --- Clean up ADMIN-PANEL table rows ---
    replace('| P0 | **Order history** — per sales rep: order count, status, total value | Fleetbase `orders` table via proxy | Medium (via Fleetbase API) |',
            '| P0 | **Order history** — per sales rep: order count, status, total value | PostgreSQL wim_orders | Medium (direct query) |')
    replace('| Automated route optimization | Fleetbase handles this; admin just views | V2 |',
            '| Automated route optimization | Manual route planning via admin panel | V2 |')
    
    # --- KLIKORDER-PM-REVIEW ---
    replace("Product data imported into Fleetbase Entities", "Product data imported into wim_produk")
    
    # --- Remaining "Fleetbase" standing alone --- 
    # "All WIM stores, products, users, drivers, and vehicles exist in Fleetbase."
    replace("All WIM stores, products, users, drivers, and vehicles exist in Fleetbase.",
            "All WIM stores, products, users, drivers, and vehicles exist in PostgreSQL `wim_sfa`.")
    
    # "Fleetbase handles this; admin just views"
    replace("Fleetbase handles this; admin just views", "Admin handles this via the admin panel")
    
    # --- PROJECT-CHARTER already clean, just one framing line ---
    # (No changes needed)
    
    # --- SCOPE ---
    replace('├── Fleetbase API (future) ─── orders / stores sync', '├── Future Sync Layer ─── orders / stores sync')
    
    return content, changes

import os

PROJECT_DIR = "/Users/rein/projects/wim-fleetbase"
EXCLUDE = {"CHANGELOG.md", "FUTURE-INTEGRATION.md", "API-REFERENCE.md", "DATABASE-MAPPING.md"}

results = []

for root, dirs, files in os.walk(PROJECT_DIR):
    for f in files:
        if not f.endswith(".md"):
            continue
        if f in EXCLUDE:
            continue
        abs_path = os.path.join(root, f)
        rel_path = os.path.relpath(abs_path, PROJECT_DIR)
        
        with open(abs_path, "r", encoding="utf-8") as fh:
            content = fh.read()
        
        original = content
        content, changes = scrub_content(content, rel_path)
        
        if content != original:
            with open(abs_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            results.append((rel_path, len(changes), True))
            print(f"✅ {rel_path}: {len(changes)} replacements applied")
        else:
            print(f"⏭️  {rel_path}: no changes needed")
            results.append((rel_path, 0, False))

print("\n" + "=" * 60)
print("VERIFICATION: Remaining 'Fleetbase' references")
print("=" * 60)
remaining = []
for root, dirs, files in os.walk(PROJECT_DIR):
    for f in files:
        if not f.endswith(".md"):
            continue
        abs_path = os.path.join(root, f)
        rel_path = os.path.relpath(abs_path, PROJECT_DIR)
        with open(abs_path, "r", encoding="utf-8") as fh:
            content = fh.read()
        count = content.count("Fleetbase")
        if count > 0:
            remaining.append((rel_path, count))

if remaining:
    for rel, count in sorted(remaining):
        print(f"  ⚠️  {count}x in {rel} (exceptions: AGENTS.md allowed)")
else:
    print("  ✅ NO remaining Fleetbase references in scrubbed files!")

# Verify exceptions
for fname in sorted(EXCLUDE):
    path = os.path.join(PROJECT_DIR, fname)
    if os.path.exists(path):
        with open(path, "r") as fh:
            c = fh.read()
        fb_count = c.count("Fleetbase")
        print(f"  📋 {fname}: {fb_count} Fleetbase refs (kept intentionally)")
    else:
        print(f"  ❓ {fname}: not found")

print("\n📊 Summary:")
changed = sum(1 for _, _, c in results if c)
total = len(results)
print(f"   {changed}/{total} files modified")
print(f"   {sum(1 for _, c, _ in remaining if c)} files still have Fleetbase refs (exceptions only)")