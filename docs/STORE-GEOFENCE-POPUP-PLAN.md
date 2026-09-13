# Store Geofence Popup — "Luar Area" + Google Maps + Refresh Location + Admin Radius

> **Status:** PLAN → implemented → live-QA · **Date:** 2026-09-11
> **Feature:** In the sales app's **kunjungan list (Rencana Kunjungan Hari Ini → dashboard store list)**,
> clicking a store opens a popup that verifies the sales rep's GPS is within the store's geofence area.
> If **out of area**, the popup says so, offers a **Google Maps** link to the store's coordinates, and a
> **Refresh Location** button (in case the rep is actually at the store but the GPS fix is stale/inaccurate).
> Each store's radius is **admin-editable** (default **10 m**, like the sales-app default), so the depot
> admin can raise it for large stores that repeatedly trigger false alarms.

---

## 1. Why / reasoning

- Today, clicking a store on the dashboard kunjungan list **jumps straight to `visit-card.html`** with
  **no distance/geofence verification**. The rep can check in to a store they aren't physically at,
  which corrupts visit/geofence data.
- The engine already has the pieces to fix this convincingly:
  - `WIM_Geo` (`frontend/js/app.js`) captures GPS (`capture()`), computes distance (`distanceM()`),
    and already tags stores "in range" on `visit-card.html` via a hard-coded `storeRadiusM: 10`.
  - Stores already carry `latitude`/`longitude` in the `/api/stores` response.
  - Depots use a `radius_m` geofence (currently 50 m) for absensi.
- **Design decision — per-store geofence radius:** use a **10 m default**, with an optional per-store
  override stored in a new `wim_stores.geofence_radius_m` column — **editable by the admin in store data**.
  This is additive & reversible, and lets a depot admin raise a specific store's radius (e.g. a
  supermarket larger than 10 m) when it keeps flagging the rep "Luar Area" inside the store.
  Default (when NULL) = the app shared default (**10 m**).

### What each UI element does (user request mapping)
| Requested | Implementation |
|---|---|
| "popup says out of area" | Popup title + status badge = **Luar Area** (red) when `distance > radius`; **Dalam Area** (green) otherwise |
| "Google maps link to coordinates" | `https://www.google.com/maps?q=<lat>,<lng>` opens in new tab/browser maps |
| "refresh location (in case rep is at store but still far)" | Re-captures GPS, recomputes distance + re-renders the popup status; disables the button while capturing |

---

## 2. Database

```sql
-- Additive + reversible. Per-store geofence radius override (meters).
ALTER TABLE wim_stores ADD COLUMN IF NOT EXISTS geofence_radius_m INT;
-- NULL → use the app default (100 m).
GRANT SELECT, UPDATE ON wim_stores TO wim_app;  -- verify existing grant
```
- No new table. Backfill not needed (NULL = default).
- Document: `wim_stores.geofence_radius_m` = geofence radius (m) for this store's visit popup;
  NULL → app default (100 m). Related Goovi/Klikorder concept: the store's coverage zone.

## 3. Backend (`frontend/serve.py`)

- `do_MY_STORES` (the `/api/stores` response feeding the dashboard kunjungan list) returns
  `latitude`/`longitude`/`geofenceRadiusM`.
- `do_ALL_STORES`, `do_STORE_BY_UUID` (admin store read) return `geofence_radius_m`.
- `do_STORE_PATCH`, `do_STORE_POST` persist `geofence_radius_m` (empty → NULL/default).
- `admin/admin-server.py` passthrough adds `geofence_radius_m`.
- No new endpoint needed — the popup does everything client-side with the rep's `WIM_Geo` position.

## 4. Frontend (`frontend/dashboard.html` + `js/app.js`)

- **Store click** (`onclick` on `.store-item`) now calls `openStoreGeoPopup(s)` instead of
  `location.href='visit-card.html?...'`.
- New **modal** (reuse existing `.modal-overlay/.modal-content/.modal-title` CSS — already present in `app.css`):
  1. Store name + address.
  2. **Status badge** computed from `WIM_Geo.distanceM(repLat, repLng, store.lat, store.lng)` vs
     `store.geofence_radius_m || GEODEFAULT` (100 m). `null` distance (no GPS) → "Cek Lokasi".
  3. **Luar Area** state: red badge + alert text + two buttons:
     - `🗺️ Buka Google Maps` → `window.open('https://www.google.com/maps?q=lat,lng', '_blank')`
     - `📡 Refresh Lokasi` → `await WIM_Geo.capture()` then recompute + re-render; button disabled + spinner while capturing.
  4. **Dalam Area** state: green badge + `📍 Lanjut Kunjungan` button → navigate to `visit-card.html?store=uuid`.
  5. Always: a "Batal/Close" ✕.
- On modal open: capture GPS (if `WIM_Geo.lastPosition` exists use it, else `capture()`), compute distance, render.
- `js/app.js`: bump `WIM_Geo` default radius to **10 m** (`defaultRadiusM=10`) so the dashboard popup and
  the visit-card glow stay consistent; `WIM_Geo` remains the single GPS source.

### Frontend — admin radius edit (`admin/stores.html`)
- New **"Radius Geofence (meter)"** numeric field in the store edit form (default 10; blank = default).
- `openEdit` fills it from `geofence_radius_m`; `saveStore` sends it (`''` → null = default).
- Hint text explains: *"Kosongkan = default 10 m. Naikkan bila toko besar sering salah 'Luar Area'."*

## 5. Wire / deploy / QA

- Deploy `dashboard.html`, `js/app.js`, `frontend/serve.py` to LXC 112 field app (+ serve.py restart on 111).
- Migration `deploy/db/init/13-store-geofence.sql` applied live.
- **3 QA subagents:**
  1. Sales rep — real flow: open dashboard → click store → popup shows In/Dalam Area for a nearby store,
     Out/Luar Area for a far one; Lanjut navigates correctly.
  2. Sales rep — mock GPS: force a "far" coordinate → popup shows Luar Area + Google Maps link opens
     correct `maps?q=lat,lng`; Refresh Location re-captures and flips the badge when GPS changes.
  3. Sales rep / edge — store with `geofence_radius_m` set uses its radius, overrides default; store with
     NULL radius uses 100 m default; no JS errors; visit-card still reachable via popup.
- Fix → re-verify until verdicts pass, then commit + push + document in `docs/`.