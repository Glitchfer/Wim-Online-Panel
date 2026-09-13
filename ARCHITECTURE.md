# Architecture — WIM Online (Standalone PostgreSQL)

## High-level deployment

```
┌─────────────────────────────────────────────────────┐
│                Proxmox VE (Host)                     │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  LXC — WIM Server (privileged, Python + PostgreSQL)      │   │
│  │                                                │   │
│  │  ┌─────────────┐  ┌──────────────────────┐    │   │
│  │  │ Python       │  │ WIM Admin Panel       │    │   │
│  │  │ API (Laravel)│  │ (Ember.js SPA)        │    │   │
│  │  │ :8000        │  │ :4200                 │    │   │
│  │  └──────┬───────┘  └──────────────────────┘    │   │
│  │         │                                       │   │
│  │  ┌──────┴───────┐  ┌──────────────────────┐    │   │
│  │  │ SocketCluster │  │ Redis (queue/cache)  │    │   │
│  │  │ :38000        │  │ :6379                │    │   │
│  │  └──────────────┘  └──────────────────────┘    │   │
│  │                                                │   │
│  │  ┌─────────────┐  ┌──────────────────────┐    │   │
│  │  │ MySQL 8      │  │ Scheduler (go-crond)  │    │   │
│  │  │ :3306        │  │ (cosmetic unhealthy)  │    │   │
│  │  └─────────────┘  └──────────────────────┘    │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  LXC — NPMplus Reverse Proxy (existing)       │   │
│  │  fleetbase.wim.domain → :8000, :4200          │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

## Infrastructure decisions

### LXC must be privileged

**Critical:** Docker-in-unprivileged-LXC may fail with certain container images very high UIDs. Unprivileged LXC cannot map them → `lchown` errors. Create as privileged with `--features nesting=1,keyctl=1`.

### Recommended LXC spec

| Resource | Value |
|---|---|
| CPU cores | 4 |
| RAM | 6 GB |
| Swap | 1 GB |
| Rootfs | 24 GB (local-lvm) |
| OS | Debian 13 |
| Network | Static LAN IP via vmbr0 bridge |

### Stack components

| Component | Technology | Port | Purpose |
|---|---|---|---|
| API | Laravel (PHP 8.x) | :8000 | REST API, auth, geofence engine |
| Console | Ember.js SPA | :4200 | Web dashboard for super admins |
| Database | MySQL 8 | :3306 | Primary data store |
| Cache/Queue | Redis | :6379 | Job queue, cache, session |
| WebSocket | SocketCluster (Node) | :38000 | Real-time events (geofence alerts) |
| Scheduler | go-crond | — | Scheduled tasks (cosmetic unhealthy — ignore) |

### Network topology

- LXC has a static LAN IP (e.g., `192.168.x.x`)
- NPMplus reverse proxy routes `fleetbase.wim.domain` → LXC :8000 (API) and :4200 (console)
- Sales reps' phones connect via mobile data → internet → NPMplus → LXC
- Super admins access console via browser → NPMplus → LXC

## Data flow — visit → order lifecycle

```
1. Sales rep assigned Route (waypoints = stores)
2. Rep arrives at store (GPS enters 10m geofence Zone)
3. POST /v1/drivers/{id}/track → GeofenceIntersectionService fires GeofenceEntered
4. Rep takes selfie (attachment on tracking event)
5. Rep selects products from catalog → builds Order (entities)
6. Order created with status "on-hold" or "pending"
7. QR code generated (order reference)
8. If order > 0: rep must scan QR as verification
9. If order = 0: rep submits "no-order" with reason
10. Rep records store stock (per-SKU) → custom entity/meta
11. Rep submits visit → Kirim Kunjungan (min 3 min enforced frontend)
12. End of day: admin aggregates orders → builds Route for delivery
13. Warehouse generates packing list from Route → Payload → Entities
```

## Security model

- **Single-tenant** (WIM only; no multi-tenant isolation needed for V1)
- API access: Session cookie (wim_session) — one per user
- Admin console: Fleetbase user auth (email + password)
- Sales reps: authenticated via API token (no direct console access)
- No mock data in production
- Destructive actions (delete order, delete route) require super admin auth