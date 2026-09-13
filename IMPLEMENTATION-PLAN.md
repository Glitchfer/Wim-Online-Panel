# Implementation Plan — WIM Online (Standalone PostgreSQL)

> **Note:** This implementation plan was created during the Fleetbase deployment phase.
> WIM Online is now **fully standalone on PostgreSQL**. Fleetbase references in this file
> describe the original deployment plan and are retained for historical context.
> The current architecture uses **Python http.server + PostgreSQL `wim_sfa`** with no Fleetbase dependency.
> For the current data model see `DATABASE-MAPPING.md`. For future integration plans see `FUTURE-INTEGRATION.md`.


> Author: Seraphine (Hermes Agent)
> Authorization: Rein has approved deploying and testing on the SanQua AI Proxmox box (192.168.6.101, ct102, RTX3080 10GB).
> Target domain: `fleet.sqa.web.id` (console), `api.fleet.sqa.web.id` (API).
> Domains currently unconfigured — DNS will be pointed after install.

---

## Environment

| Resource | Value |
|---|---|
| **Host** | SanQua AI Proxmox VE (192.168.6.101) |
| **Gateway** | 192.168.6.1 |
| **Existing LXC ct102** | SanQua AI PC (RTX3080, vLLM, Dify) — separate from WIM stack |
| **New LXC** | Create fresh (ct121 or next available) — privileged, nesting=1 |
| **LXC spec** | 4 cores, 6 GB RAM, 1 GB swap, 24 GB rootfs, Debian 13 |
| **Domain** | `sales.sqa.web.id` → app (:8080), `admin.sqa.web.id` → admin (:8081) |
| **Target LAN IP** | 192.168.6.x (DHCP or static within WIM subnet) |

### Permission

Rein has explicitly authorized:
- Setting up PostgreSQL + Python http.server on the WIM LXC
- Creating test data (stores, products, routes, orders) for proof-of-concept
- Configuring NPMplus reverse proxy for the domains
- Testing all features described in this plan
- The LXC will be a **development/staging** instance, not production

**Not authorized:** Touching the existing ct102 (SanQua AI PC with vLLM/Dify), modifying production WIM data.

---

## Scaling for 200+ Concurrent Users

The current dev LXC (4 cores, 6 GB, 24 GB) is adequate for testing but not for 200+ simultaneous sales reps. Below is the production scaling plan.

### User Profile & Traffic Model

| Metric | Value | Basis |
|---|---|---|
| Total users | ~200 sales reps + 20 admins | WIM meeting notes |
| Peak concurrent | ~180 (all check-in 8:00-8:30 AM) | Morning depot rush |
| Avg API calls/user/day | ~50 calls (tracking, orders, catalog) | GooVi/KlikOrder telemetry |
| Total daily API calls | ~11,000 (peak ~500/min) | 200 x 55 |
| Photo uploads/day | ~600 (3 photos x 200 visits) | Selfie + 2 kunjungan photos |
| Order creations/day | ~200 | 1 order/store visit average |
| Geofence checks/day | ~1,000 | 5 stores x 200 reps |

### Bottleneck Analysis

| Component | Dev Config (G0) | Limit at 200 users | Fix |
|---|---|---|---|
| **Python workers** | ThreadingHTTPServer | ~20-50 concurrent requests | Add gunicorn or uvicorn for scale |
| **PostgreSQL connections** | Default (100 max) | Pool exhaustion at peak | Raise max_connections=200 |
| **Queue workers** | 1 (scheduler) | Geofence backlog during peak | Scale to 3-5 workers |
| **SocketCluster** | Not used | — | — |
| **Redis** | (optional) | In-memory session cache if needed | Can use Python dict-based cache |
| **Disk I/O** | 24 GB rootfs | Photos fill disk in 2 weeks | Add Docker volume on NAS |
| **Network** | 1 GbE | ~3 Mbps peak = negligible | Already adequate |
| **LXC resources** | 4C / 6 GB | CPU ~40%, RAM ~3.5 GB at peak | Scale to 8C / 16 GB |

### Production LXC Spec

```bash
pct create <ID> local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst \
  --hostname fleetbase-prod --arch amd64 --cores 8 --memory 16384 --swap 2048 \
  --rootfs local-lvm:80 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.6.224/24,gw=192.168.6.1,type=veth \
  --features nesting=1,keyctl=1 --ostype debian --timezone Asia/Jakarta \
  --nameserver "1.1.1.1 8.8.8.8" --onboot 1
```

| Resource | Dev (G0) | Production (200 users) | Rationale |
|---|---|---|---|
| CPU cores | 4 | 8 | Peak request volume needs parallel processing |
| RAM | 6 GB | 16 GB | PostgreSQL buffer pool (4 GB), Python workers (2 GB), session cache (1 GB) |
| Root disk | 24 GB | 80 GB | Logs, Docker images, 6 months of data |
| Photo volume | Container ephemeral | NFS mount at /opt/storage/photos/ | 600 photos/day x 200 KB = 120 MB/day |
| Backup | None | Daily DB dump + weekly LXC snapshot | 12-month data retention |

### Docker Compose Tuning for Production

Configure production deployment:

```bash
# Run behind gunicorn for production
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8080 serve:app
      - PHP_FPM_PM_MAX_SPARE_SERVERS=24

  mysql:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
    environment:
      - MYSQL_MAX_CONNECTIONS=300
      - INNODB_BUFFER_POOL_SIZE=2G

  redis:
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 1G

  queue-worker:
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '1'
          memory: 512M
```

### MySQL Tuning

```ini
[mysqld]
max_connections = 300
innodb_buffer_pool_size = 2G
innodb_log_file_size = 512M
innodb_flush_log_at_trx_commit = 2
tmp_table_size = 256M
max_heap_table_size = 256M
thread_cache_size = 32
sort_buffer_size = 4M
join_buffer_size = 2M
```

### Photo Storage Architecture

- Photos stored on NAS (NFS mount) to avoid filling LXC disk
- Photo file paths stored in DB; served via nginx
- Estimated: 600 photos/day x 200 KB avg = 120 MB/day, ~3.6 GB/month
- For 500+ users in future: add MinIO (S3-compatible) Docker service

### Queue Worker Design

Geofence detection runs synchronously on `POST /v1/drivers/{id}/track`. At 8:00 AM peak (~180 concurrent check-ins), increase workers:

```bash
docker compose up -d queue-worker --scale queue-worker=5
```

(Legacy) Laravel Horizon config — not applicable to current Python stack:
```php
'defaults' => [
    'supervisor-1' => [
        'connection' => 'redis',
        'queue' => ['default', 'geofence', 'orders', 'exports'],
        'balance' => 'auto',
        'maxProcesses' => 10,
        'tries' => 3,
    ],
],
```

### Monitoring

| What | Tool | Alert threshold |
|---|---|---|
| PHP-FPM pool exhaustion | pm.status endpoint | max_children reached -> scale |
| MySQL connections | SHOW PROCESSLIST | > 250 -> kill idle or scale |
| Queue backlog | Laravel Horizon | Pending > 100 -> increase workers |
| Disk usage | df -h | > 80% -> archive or add storage |
| API response time | nginx upstream_response_time | p95 > 2s -> investigate |

### Production Readiness Checklist

- [ ] LXC auto-starts on Proxmox boot (onboot=1)
- [ ] Docker containers restart on failure (unless-stopped)
- [ ] Photo volume on NAS with NFS mount
- [ ] Daily MySQL dump to backup volume
- [ ] Weekly Proxmox LXC snapshot
- [ ] NPMplus with SSL (Let's Encrypt auto-renew)
- [ ] Rate limiting on tracking endpoint (30 req/s)
- [ ] PHP-FPM status monitoring endpoint
- [ ] Redis persistence enabled (RDB snapshots every 5 min)
- [ ] Docker Compose prod override applied

---

## Phase 0 — Infrastructure Setup (G0)

### Step 0.1: Create privileged LXC

Connect to the Proxmox host and create the container:

```bash
# SSH into Proxmox host
ssh root@192.168.6.101

# Find next available CT ID
pvesh get /cluster/nextid

# Create LXC (privileged, nesting, Docker-ready)
pct create <ID> local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst \
  --hostname fleetbase --arch amd64 --cores 4 --memory 6144 --swap 1024 \
  --rootfs local-lvm:24 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.6.223/24,gw=192.168.6.1,type=veth \
  --features nesting=1,keyctl=1 --ostype debian --timezone Asia/Jakarta \
  --nameserver "1.1.1.1 8.8.8.8" --onboot 0
```

### Step 0.2: Install Docker CE

```bash
pct enter <ID>
apt update && apt install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt update && apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

### Step 0.3: Deploy Python http.server

```bash
cd /opt
git clone https://github.com/fleetbase/fleetbase.git
cd fleetbase
bash scripts/docker-install.sh --non-interactive
```

**First boot:** ~15 minutes. Image pulls → npm build of Ember console (2138 packages) → migrations run twice (main DB + sandbox) → seeding.

### Step 0.4: Patch host config for LAN access

```bash
# Change HOST from localhost to LAN IP
sed -i 's/HOST=localhost/HOST=192.168.6.223/g' docker-compose.override.yml
sed -i 's/"host": "localhost"/"host": "192.168.6.223"/g' console/fleetbase.config.json

# Restart
docker compose up -d application socket console
```

### Step 0.5: Configure NPMplus reverse proxy

On the existing NPMplus instance:
- **Domain:** `fleet.sqa.web.id` → Forward to `192.168.6.223:4200` (console)
- **Domain:** `api.fleet.sqa.web.id` → Forward to `192.168.6.223:8000` (API)
- Enable SSL via Let's Encrypt

### Step 0.6: Verify

```bash
# Check console is up
curl -sL http://192.168.6.223:4200 | head -5

# Check API is up  
curl -sL http://192.168.6.223:8000 | head -5

# Create admin user
docker exec -it fleetbase-api-1 php artisan fleetbase:create-user \
  --email admin@wim.fleet --name "Admin WIM" --password "changeme" \
  --company "PT Wahana Inti Mas"
```

**G0 exit:** Python http.server accessible at http://192.168.6.223:8080, PostgreSQL at localhost:5432. Admin user created.

---

## Phase 1 — Core Data Setup (G1)

All data is created via `php artisan tinker` inside the container — no API key needed.

### Step 1.1: Create initial PHP setup script

Write `/tmp/setup-g1.php` and `docker cp` it into the Fleetbase API container:

```php
<?php
use Fleetbase\Models\Company;
use Fleetbase\Models\User;
use Fleetbase\Models\ApiCredential;
use Fleetbase\FleetOps\Models\Place;
use Fleetbase\FleetOps\Models\Contact;
use Fleetbase\FleetOps\Models\Driver;
use Fleetbase\FleetOps\Models\Vehicle;
use Fleetbase\FleetOps\Models\Zone;
use Fleetbase\FleetOps\Models\Route;

$company = Company::first();
$companyUuid = $company->uuid;

// --- Create test depots ---
// Depots modeled as custom categories/segments via Place type="depot"
$depots = [
    ['name' => 'Depo Bintaro', 'lat' => -6.2571, 'lng' => 106.7645, 'city' => 'Jakarta Selatan'],
    ['name' => 'Depo Tapos', 'lat' => -6.3431, 'lng' => 106.8856, 'city' => 'Depok'],
    ['name' => 'Depo Bandung TO', 'lat' => -6.9175, 'lng' => 107.6191, 'city' => 'Bandung'],
    ['name' => 'Depo Bandung SPC', 'lat' => -6.9175, 'lng' => 107.6191, 'city' => 'Bandung'],
];
foreach ($depots as $d) {
    Place::create([
        'company_uuid' => $companyUuid, 'name' => $d['name'], 'type' => 'depot',
        'location' => ['latitude' => $d['lat'], 'longitude' => $d['lng']],
        'country' => 'ID', 'city' => $d['city'],
    ]);
}

// --- Create test stores (Places) ---
$stores = [
    ['name' => 'Toko Berkah', 'owner' => 'Budi', 'lat' => -6.2088, 'lng' => 106.8456, 'kota' => 'Jakarta Pusat', 'channel' => 'GT', 'kategori' => 'Retail Kecil', 'hp' => '6281234567890'],
    ['name' => 'Toko Jaya', 'owner' => 'Siti', 'lat' => -6.2404, 'lng' => 106.7976, 'kota' => 'Jakarta Selatan', 'channel' => 'GT', 'kategori' => 'Grosir'],
    ['name' => 'Toko Makmur', 'owner' => 'Agus', 'lat' => -6.2625, 'lng' => 106.7890, 'kota' => 'Jakarta Selatan', 'channel' => 'GT', 'kategori' => 'Retail Kecil'],
    ['name' => 'Toko Sejahtera', 'owner' => 'Dewi', 'lat' => -6.2345, 'lng' => 106.7934, 'kota' => 'Jakarta Selatan'],
    ['name' => 'Toko Baru', 'owner' => 'Eko', 'lat' => -6.2512, 'lng' => 106.8021, 'kota' => 'Jakarta Selatan'],
];
$placeIds = [];
foreach ($stores as $s) {
    $p = Place::create([
        'company_uuid' => $companyUuid, 'name' => $s['name'], 'type' => 'store',
        'location' => ['latitude' => $s['lat'], 'longitude' => $s['lng']],
        'country' => 'ID', 'city' => $s['kota'], 'street1' => $s['nama'] ?? '',
    ]);
    // Also create a Contact for each store
    Contact::create([
        'company_uuid' => $companyUuid, 'place_uuid' => $p->uuid,
        'name' => $s['owner'], 'type' => 'customer',
        'phone' => $s['hp'] ?? '',
    ]);
    $placeIds[$s['name']] = $p;
}

// --- Create 10m geofence Zones for each store ---
function circlePolygon($lat, $lng, $radiusMeters, $points=32) {
    $coords = [];
    $r = $radiusMeters / 111320.0;
    for ($i=0; $i<$points; $i++) {
        $a = ($i/$points) * 2*M_PI;
        $dlat = $r * cos($a);
        $dlng = $r * sin($a) / cos($lat * M_PI/180);
        $coords[] = [$lng+$dlng, $lat+$dlat];
    }
    $coords[] = $coords[0];
    return json_encode(['type'=>'Polygon','coordinates'=>[$coords]]);
}
foreach ($stores as $s) {
    $store = $placeIds[$s['name']];
    Zone::create([
        'company_uuid' => $companyUuid, 'name' => 'Geofence '.$s['name'],
        'border' => circlePolygon($s['lat'], $s['lng'], 10),
        'status' => 'active', 'trigger_on_entry' => 1, 'trigger_on_exit' => 1,
    ]);
}

// --- Create Driver (sales rep) ---
$driver = Driver::create([
    'company_uuid' => $companyUuid,
    'name' => 'Andi Sales', 'email' => 'andi@wim.fleet',
    'phone' => '628111111111',
    'status' => 'active',
]);

// --- Create Vehicle ---
$vehicle = Vehicle::create([
    'company_uuid' => $companyUuid,
    'name' => 'Motor Andi', 'plate_number' => 'B 1234 ABC',
    'type' => 'motorcycle',
]);

echo "G1 setup complete.\n";
echo "Company UUID: $companyUuid\n";
echo "Driver UUID: {$driver->uuid}\n";
echo "Stores created: " . count($stores) . "\n";
echo "Zones created: " . count($stores) . "\n";
```

Run it:
```bash
docker cp /tmp/setup-g1.php fleetbase-api-1:/tmp/
docker exec fleetbase-api-1 php artisan tinker /tmp/setup-g1.php
```

### Step 1.2: Create Company API Credential

```bash
docker exec fleetbase-api-1 php artisan tinker /tmp/create-api-key.php
```

Where `create-api-key.php`:
```php
$cred = ApiCredential::create([
    'user_uuid' => User::first()->uuid,
    'company_uuid' => Company::first()->uuid,
    'name' => 'WIM API Key', 'test_mode' => true,
    'api' => ['fleetbase', 'fleet-ops'],
]);
echo "API key: " . $cred->fresh()->key . "\n";
```

Save this key — it's the Bearer token for all Fleetbase API calls.

### Step 1.3: Product import (Entity catalog)

Products in Fleetbase are **Entities** linked to a company. Create a script that imports the Sanqua product catalog:

```php
$products = [
    ['name' => 'SANQUA PET 220ML K24', 'sku' => 'SQA-220-K24', 'price' => 120000, 'meta' => ['brand' => 'SANQUA', 'category' => 'PET', 'uom' => 'karton', 'uom_qty' => 24]],
    ['name' => 'SANQUA PET 550ML K24', 'sku' => 'SQA-550-K24', 'price' => 150000, 'meta' => ['brand' => 'SANQUA', 'category' => 'PET', 'uom' => 'karton', 'uom_qty' => 24]],
    ['name' => 'SANQUA PET 1500ML K12', 'sku' => 'SQA-1500-K12', 'price' => 130000, 'meta' => ['brand' => 'SANQUA', 'category' => 'PET', 'uom' => 'karton', 'uom_qty' => 12]],
    ['name' => 'SANQUA CUP 120ML K40', 'sku' => 'SQA-120-K40', 'price' => 80000, 'meta' => ['brand' => 'SANQUA', 'category' => 'CUP', 'uom' => 'karton', 'uom_qty' => 40]],
    ['name' => 'SANQUA CUP 330ML K24', 'sku' => 'SQA-330-K24', 'price' => 100000, 'meta' => ['brand' => 'SANQUA', 'category' => 'CUP', 'uom' => 'karton', 'uom_qty' => 24]],
    ['name' => 'LEVONTE CUP 220ML K24', 'sku' => 'LEV-220-K24', 'price' => 95000, 'meta' => ['brand' => 'LEVONTE', 'category' => 'CUP']],
];
```

**G1 exit:** At least 5 test stores with 10m geofences, 1 driver, 1 vehicle, 6 products, Company API key saved.

---

## Phase 2 — Visit Workflow (G2)

### Step 2.1: Geofence detection test

Verify the geofence engine detects driver entry:

```bash
# Simulate driver position at store location
curl -X POST "http://192.168.6.223:8000/v1/drivers/{driver_uuid}/track" \
  -H "Authorization: Bearer {api_key}" \
  -H "Content-Type: application/json" \
  -d '{"latitude":-6.2088,"longitude":106.8456}'

# Check geofence events
curl -X GET "http://192.168.6.223:8000/v1/geofences/events" \
  -H "Authorization: Bearer {api_key}"
```

Expected: `GeofenceEntered` event fired for Toko Berkah when driver tracks at its coords.

### Step 2.2: Custom sales frontend

Fleetbase Navigator is a delivery app — **not** designed for the sales-rep flow (plan selection, in/out route, NOO, 3-min timer, promos, barcode). A custom web-based sales panel is needed.

#### Frontend features to build (HTML/CSS/JS SPA, served via the Fleetbase box or standalone):

| Feature | Implementation approach |
|---|---|
| **Login** | POST to Fleetbase auth (or use Driver API token) |
| **Visit card (today's plan)** | GET stores with Route → display list with in/out-route tags |
| **In/out-route selection** | UI toggle; out-route triggers ad-hoc Place creation + off_route_reason |
| **NOO form** | Form with all fields (name, owner, channel, category, contact, lat/lng from GPS, NIK, NPWP) |
| **10m geofence enforcement** | Browser Geolocation API → POST /v1/positions; server checks Zone intersection |
| **OTP request** | POST to WhatsApp gateway webhook (external) |
| **Selfie + visit photos** | Camera API capture → POST as attachment to visit event |
| **3-min minimum timer** | Client-side countdown; disable "Kirim Kunjungan" until elapsed |
| **No-order reason** | If jumlah_order=0, require reason field |
| **Barcode scan** | Use `navigator.mediaDevices` + jsQR library to scan QR |
| **Store stock entry** | Simple per-SKU quantity input (one-tap, big touch targets) |
| **Product catalog + cart** | Browse products by brand → add to cart → bundling auto-add |
| **Promo display** | Show active promos per store with bundling/strata info |
| **Checkout** | Submit Order with Payload + Entities → QR generated → scan to confirm |

### Step 2.3: Custom frontend architecture

```text
frontend/                     # Static HTML/CSS/JS, served via Fleetbase LXC nginx
├── index.html                # Login page
├── dashboard.html            # Visit dashboard (today's plan, route map)
├── visit-card.html           # Visit card flow (check-in → store → order)
├── noo.html                  # New Outlet Opening form
├── report.html               # Visit history
├── js/
│   ├── api.js                # Fleetbase API client (Bearer auth)
│   ├── geolocation.js        # GPS tracking + geofence check
│   ├── camera.js             # Photo capture (selfie, display)
│   ├── qr-scanner.js         # Barcode/QR scanning via jsQR
│   ├── cart.js               # Product catalog, cart, bundling logic
│   ├── timer.js              # 3-minute minimum visit timer
│   └── map.js                # Route map (Leaflet + OSRM)
├── css/
│   └── app.css               # Mobile-first responsive (WIM brand colors)
└── assets/
    └── icons/                # Brand icons
```

The frontend is served via a static nginx container added to the Fleetbase Docker Compose, or via the existing httpd proxy.

### Step 2.4: Visit flow implementation

The core visit flow — all API calls against Fleetbase:

```
1. Rep opens visit-card.html
2. GET /v1/routes?driver={driver_id}&date=today  →  today's route with waypoints
3. Rep selects store → 
   POST /v1/positions  ({lat, lng})  →  GeofenceIntersectionService detects entry
4. GeofenceEntered event fires (logged to geofence_events_log)
5. Rep takes selfie → POST to /v1/drivers/{id}/track with photo attachment
6. Rep enters NOO data → POST /v1/places + POST /v1/contacts
7. Optional OTP → external WhatsApp gateway webhook
8. Rep checks store stock → POST /v1/places/{id}/meta (custom: stock per SKU)
9. If order > 0:
   a. Browse products → POST /v1/orders with payload + entities
   b. Order creates QR (public_id)
   c. Rep scans QR to confirm → PATCH /v1/orders/{id} {status: "verified"}
10. If order = 0:
    POST /v1/orders {status: "no-order", meta: {reason: "..."}}
11. After 3 minutes → "Kirim Kunjungan" enabled → PATCH visit status
```

### Step 2.5: Photo & attachment handling

```javascript
// Camera capture
async function capturePhoto(facingMode) {
    const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: facingMode } // 'user' = selfie, 'environment' = store
    });
    // ... capture to canvas, get blob
    const formData = new FormData();
    formData.append('photo', blob, 'visit.jpg');
    formData.append('description', document.getElementById('photoDesc').value);
    
    await fetch(`/v1/drivers/${driverId}/track`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
    });
}
```

**G2 exit:** Custom frontend deployed. A test visit can be completed end-to-end: check-in → NOO → order/barcode/scan → stock entry → photos → submit.

---

## Phase 3 — Order Management (G3)

### Step 3.1: Product catalog

The Fleetbase Entity model is used as the product catalog. Products are queried by brand/category:

```javascript
// GET /v1/entities?company={company_uuid}&meta.brand=SANQUA
async function getProducts(brand) {
    const resp = await fetch(`/v1/entities?meta.brand=${brand}&limit=50`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    return resp.json();
}
```

### Step 3.2: Cart with bundling

Bundling logic sits in the frontend (Fleetbase has no native bundling):

```javascript
// Example bundling rule stored in product meta:
const bundlingRules = [
    {
        triggerSku: 'SQA-220-K24',
        triggerQty: 30,
        freeSku: 'SQA-220-K24',
        freeQty: 1,
        description: 'Mix 30 karton SANQUA PET 220ml gratis 1 karton'
    },
    {
        triggerSku: 'SQA-220-K24',
        triggerQty: 15,
        freeSku: 'SQA-220-K24',
        freeQty: 1,
        description: 'Beli 15 karton 220ml gratis 1 karton'
    }
];

function calculateBundling(cartItems) {
    let bonuses = [];
    bundlingRules.forEach(rule => {
        const item = cartItems.find(i => i.sku === rule.triggerSku);
        if (item && item.qty >= rule.triggerQty) {
            const bundleCount = Math.floor(item.qty / rule.triggerQty);
            bonuses.push({
                sku: rule.freeSku,
                qty: rule.freeQty * bundleCount,
                is_bonus: true,
                promo_name: rule.description
            });
        }
    });
    return bonuses;
}
```

### Step 3.3: Order creation with verified check-in

```javascript
async function submitOrder(storePlaceId, items, driverId) {
    // 1. Verify geofence event exists today for this driver+store
    const geofenceCheck = await fetch(
        `/v1/geofences/events?driver=${driverId}&place=${storePlaceId}&event=entered&date=today`
    );
    const events = await geofenceCheck.json();
    if (events.data.length === 0) {
        throw new Error('Rep must check in at store before ordering');
    }
    
    // 2. Create order
    const order = await fetch(`/v1/orders`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
            customer_uuid: contactUuid,
            customer_type: 'contact',
            payload: { 
                dropoff_uuid: storePlaceId,
                entities: items.map(i => ({
                    name: i.name, sku: i.sku, price: i.price, quantity: i.qty,
                    meta: { is_bonus: i.is_bonus || false, promo_name: i.promo_name || null }
                }))
            },
            status: 'pending',
            type: 'delivery',
            meta: { payment_method: 'cod', sales_rep: driverId, store: storePlaceId }
        })
    });
    
    // 3. Generate QR from order.public_id
    const qrData = order.data.public_id;
    
    // 4. Rep scans QR to confirm
    const scanned = await scanQRCode();
    if (scanned === qrData) {
        await fetch(`/v1/orders/${order.data.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'verified' })
        });
    }
    return order;
}
```

### Step 3.4: Out-of-route order

When a rep visits a store not on today's planned route:

```javascript
// 1. Add store to route (on-the-fly)
const routeUpdate = await fetch(`/v1/routes/${routeId}`, {
    method: 'PATCH',
    body: JSON.stringify({ 
        waypoints: [...existingWaypoints, storePlaceId],
        meta: { off_route: true }
    })
});

// 2. Create order with off_route_reason
await fetch(`/v1/orders`, {
    method: 'POST',
    body: JSON.stringify({
        // ... order data ...
        meta: { 
            off_route: true, 
            off_route_reason: document.getElementById('offRouteReason').value,
            payment_method: 'cod'
        }
    })
});
```

### Step 3.5: Admin order entry

```javascript
// Admin scans store barcode → same order flow
async function adminOrder(barcode) {
    const store = await fetch(`/v1/places?barcode=${barcode}`);
    // ... same order flow as sales, but store selected by barcode lookup
}
```

### Step 3.6: Order export with promo/bonus separation

```php
// Fleetbase API: GET /v1/orders?export=csv
// Enhance export to include bonus lines separately
$orders = Order::with('payload.entities')->get();
$csv = "Product SKU,Product Name,Qty,Unit Price,Total,Bonus SKU,Bonus Qty,Promo Name\n";
foreach ($orders as $order) {
    foreach ($order->payload->entities as $entity) {
        $bonusInfo = '';
        if ($entity->meta['is_bonus'] ?? false) {
            $bonusInfo = "BONUS,{$entity->quantity},{$entity->meta['promo_name']}";
        }
        $csv .= "{$entity->sku},{$entity->name},{$entity->quantity},{$entity->price}," . 
                ($entity->quantity * $entity->price) . ",{$bonusInfo}\n";
    }
}
```

**G3 exit:** Can browse products → add to cart → bundling auto-applies → create order → QR scan → verify. Out-of-route orders work. Admin can create orders. Exports show promo/bonus data.

---

## Phase 4 — Reporting & Admin Dashboard (G4)

### Step 4.1: Fleetbase-native reporting

Fleetbase Console has built-in dashboards for:
- **Routes** — map-based route visualization with waypoints
- **Drivers** — driver activity, tracking history
- **Orders** — order listing, status, filtering
- **Entities** — product catalog management

These cover the base Groovi reporting.

### Step 4.2: Custom reports

For WIM-specific reports (not in Fleetbase Console natively):

| Report | Implementation |
|---|---|
| **Kunjungan Detail (daily/monthly export)** | Custom report: JOIN geofence_events_log + orders → CSV |
| **Rekapitulasi Kunjungan** | GROUP BY driver, day → visit count, order count, EC |
| **Presensi Absensi** | Photo attachments grouped by driver + date |
| **Galeri Foto Kunjungan** | Attachment browser by visit/date |
| **Aktivitas Aplikasi** | Geofence events log |
| **Ketersediaan Stock di Toko** | Place meta stock data per store |
| **Order Luar Rute** | Orders with meta.off_route=true |
| **Portfolio Sales** | Driver → Places → Orders aggregation |
| **Rekap Kinerja Depo** | Group by depot → sales metrics |
| **Analisa Order vs Stock** | Order qty vs place.meta.stock per store |

All custom reports implemented as:
1. Fleetbase API queries (JSON)
2. Export to CSV/XLSX via custom PHP script or Python export tool
3. Optionally visualized via a simple dashboard page

### Step 4.3: Mass PDF download (surat jalan)

```bash
# Install wkhtmltopdf or use Fleetbase's built-in PDF generation
docker exec fleetbase-api-1 composer require barryvdh/laravel-dompdf
```

Create an artisan command:
```bash
php artisan wim:export-packing-list --route={route_id} --format=pdf
```

**G4 exit:** Visit monitoring dashboard with export. Portfolio analytics. Stock analysis. Mass PDF download works.

---

## Phase 5 — Go-Live & Migration (G5)

### Step 5.1: Data migration scripts

Three migration scripts to export from GooVi/KlikOrder and import to Fleetbase:

```bash
# 1. Export stores from GooVi (read-only, using admin API)
curl -X GET "https://api-cloud.goovi.satriamitra.website/api/pelanggans-filtered?page=1&per_page=1000" \
  -H "Authorization: Bearer {admin_token}" \
  -o /tmp/wim-stores.json

# 2. Transform and import to Fleetbase (as Places + Contacts)
python3 /opt/wim-migration/import-stores.py /tmp/wim-stores.json

# 3. Export products from KlikOrder
curl -X GET "https://api-cloud.klikorder.satriamitra.website/api/toko-order/sku-produks?page=1&per_page=1000" \
  -H "Authorization: Bearer {klikorder_token}" \
  -o /tmp/wim-products.json

# 4. Import to Fleetbase (as Entities)
python3 /opt/wim-migration/import-products.py /tmp/wim-products.json

# 5. Export route plans
curl -X POST "https://api-cloud.goovi.satriamitra.website/api/rencana-kunjungan" \
  -H "Authorization: Bearer {admin_token}" \
  -H "Content-Type: application/json" \
  -d '{"page":1,"per_page":5000}' \
  -o /tmp/wim-routes.json

# 6. Import route plans to Fleetbase
python3 /opt/wim-migration/import-routes.py /tmp/wim-routes.json
```

### Step 5.2: Parallel run

- Both systems active for 2 weeks
- Compare Fleetbase reports with GooVi+KlikOrder reports daily
- Fix discrepancies found
- Train sales reps (3-day workshop)

### Step 5.3: Cutover

1. Final data sync from GooVi/KlikOrder
2. DNS update: `goomartapp.satriamitra.website` → `fleet.sqa.web.id`
3. Disable GooVi/KlikOrder API access
4. Monitor Fleetbase daily for 2 weeks

**G5 exit:** All WIM sales reps use Fleetbase exclusively. Vendor apps decommissioned.

---

## Fleetbase Gap Mitigations — Feature-by-Feature

| GooVi/KlikOrder Feature | Fleetbase Implementation | Custom Code? | ETA |
|---|---|---|---|
| Sales check-in check-out with depot photo | POST /v1/drivers/{id}/track + photo attachment | Frontend camera UI | G2 |
| Visit card with route plan | Route + waypoints (Places) + GET filtered by date | Route import script | G1 |
| In-route / out-route flag | Route waypoints; out-route = `meta.off_route:true` on Route | Frontend toggle | G2 |
| Route presets (4-week × 5-day) | Import script: 20 Routes per depot from CSV | Python import script | G1 |
| NOO registration (all 14 fields) | POST /v1/places + POST /v1/contacts | Frontend form | G2 |
| 10m geofence check-in | Zone circular polygon + POST /v1/drivers/{id}/track | Zone creation in G1 | G1 |
| OTP verification via WA | External webhook → WhatsApp Gateway | Integration | G2 |
| No-order reason | Order `status:"no-order"` + `meta.reason` | Frontend logic | G2 |
| 3-minute minimum timer | Frontend countdown (`setTimeout`) | Frontend only | G2 |
| Barcode scan verification | jsQR scan order.public_id → PATCH verify | Frontend only | G3 |
| Store stock tracking | Place `meta.stock_per_sku` (JSON blob) | Frontend input | G2 |
| Selfie + extra photos | Attachment on driver track / visit event | Camera + upload | G2 |
| Product catalog by brand | Entity catalog + `meta.brand` filter | None (native) | G1 |
| Bundling promos | Frontend calculation + `meta.is_bonus` on Entities | Frontend logic | G3 |
| Strata/volume discounts | Frontend calculation (not stored in Fleetbase) | Frontend logic | G3 |
| Cart + checkout | POST /v1/orders with Payload + Entities | Frontend cart UI | G3 |
| QR code generation | Order `public_id` → QR via qrcode.js | Frontend only | G3 |
| Out-of-route order with reason | `meta.off_route_reason` | Frontend + API | G3 |
| COD payment | `meta.payment_method:"cod"` | None (native) | G3 |
| Visit / order history | GET /v1/orders + GET /v1/geofences/events | None (native) | G3 |
| Report exports (Excel) | Custom PHP artisan commands → CSV/XLSX | Custom script | G4 |
| Route map visualization | Fleetbase Console built-in map | None (native) | G4 |
| Portfolio / performance analytics | Fleetbase Console dashboards | Minor config | G4 |
| Admin order entry | Same POST /v1/orders flow, store selected by barcode | Frontend admin page | G4 |
| Promo settings (self-service) | Custom `meta.promo` on applicable Entities + frontend | Frontend only | G4 |
| Mass PDF surat jalan | Custom artisan command → dompdf | Custom script | G4 |
| Packing list download | Route → Payload → Entity aggregation report | Custom script | G4 |
| Gamification (coin game) | **OUT OF SCOPE** | — | — |
| Real-time GPS tracking | **OUT OF SCOPE** (check-in only) | — | — |

---

## Testing Plan

All tests run on the SanQua AI Proxmox staging instance:

### Testing Methodology: Subagent QA Loop

Every feature or user flow goes through this iterative cycle:

```
┌─────────────────────────────────────────────────────────────┐
│  1. Build/implement feature                                  │
│     ↓                                                       │
│  2. Spawn 3+ subagents, each tasked to:                     │
│     ├─ Subagent A: Walk through the flow as a SALES REP      │
│     │   (check-in, visit, order, NOO, photo, stock, etc.)   │
│     ├─ Subagent B: Walk through as a DEPOT ADMIN             │
│     │   (route plan, admin order, report, export)            │
│     └─ Subagent C: Walk through as a SUPER ADMIN             │
│         (dashboard, settings, user management, promo)        │
│     ↓                                                       │
│  3. Each subagent submits structured feedback:              │
│     ├─ What worked?                                         │
│     ├─ What felt wrong / missing vs GooVi/KlikOrder?        │
│     ├─ Bugs or edge cases found?                            │
│     └─ Is it suitable for production use? (Yes/No/Maybe)    │
│     ↓                                                       │
│  4. If ALL subagents agree "Yes" → feature is done          │
│     If ANY subagent says "No" or "Maybe" →                  │
│     ├─ Fix issues found                                     │
│     └─ Repeat from step 2 (new subagent cycle)              │
└─────────────────────────────────────────────────────────────┘
```

**Rules for subagent QA:**
- Each subagent is a fresh Hermes Agent session with no prior context
- Subagents are given the feature's AGENTS.md context + the specific flow to test
- They must use the app as a human would — click, navigate, enter data, make mistakes
- They must compare against the GooVi/KlikOrder flow they know from the mapping docs
- A feature is only "Done" when the 3-subagent loop closes with unanimous approval
- Subagent feedback is saved to the project's test log for traceability

**What gets tested (by feature/flow):**

### G0 verification
- [ ] Console accessible at `fleet.sqa.web.id`
- [ ] API responds at `api.fleet.sqa.web.id`
- [ ] Admin can log in
- [ ] `docker compose ps` shows all services healthy (scheduler expected "unhealthy")

### G1 data verification
- [ ] Company created
- [ ] 5+ test stores exist as Places with lat/lng
- [ ] 10m Zones exist per store, active
- [ ] Contacts exist per store
- [ ] Driver created and active
- [ ] Vehicle created
- [ ] 6+ products exist as Entities
- [ ] API key works (Bearer token)

### G2 visit flow test
- [ ] Driver can POST track → geofence fires `entered` event
- [ ] Visit plan shows today's stores
- [ ] NOO form creates Place + Contact successfully
- [ ] Selfie/photo uploads as attachment
- [ ] 3-minute timer disables submit until elapsed
- [ ] No-order with reason submits successfully
- [ ] Stock entry saves per-store per-SKU

### G3 order test
- [ ] Product catalog loads by brand
- [ ] Cart supports quantity entry
- [ ] Bundling auto-adds free product
- [ ] Order creates with Payload + Entities
- [ ] QR code generates from order ID
- [ ] QR scan verifies order (PATCH status)
- [ ] Out-of-route order with reason
- [ ] Order history returns promo/bonus data
- [ ] Admin creates order via barcode scan

### G4 report test
- [ ] Visit monitoring exports CSV
- [ ] Photo gallery loads
- [ ] Portfolio/EC stats match expectations
- [ ] Mass PDF download works
- [ ] Packing list generation works

---

## Timeline Estimate

| Phase | Est. Duration | Dependencies |
|---|---|---|
| G0 — LXC + Fleetbase install | 1-2 hours | Proxmox access, domain DNS |
| G1 — Data setup | 3-4 hours | G0 done, product list from WIM |
| G2 — Visit workflow | 2-3 days | G1 done (frontend build + testing) |
| G3 — Order management | 2-3 days | G2 done (frontend + bundling logic) |
| G4 — Reporting | 2-3 days | G3 done (report scripts + admin pages) |
| G5 — Migration + cutover | 1-2 weeks | All phases done |

**Total to G4 completion:** ~7-10 working days.
**Full go-live (G5):** 2-4 weeks including parallel run.