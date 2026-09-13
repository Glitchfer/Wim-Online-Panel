# NOO Baru — GPS Map Pin Feature (Plan & Implementation)

> **Date:** 2026-09-11 · **Status:** Plan → Implement
> Pages: `frontend/noo.html` (field app). Marker preset at `-6.2088, 106.8456`.

## 1. What the user asked
On the NOO (New Outlet Order) page, after the user presses **"📍 Ambil dari GPS"** and a
location is captured, a **small map should pop up under the Lat/Long inputs** with a **pin**
at the GPS location entered.

## 2. Current behavior
`ambilGPS()` uses `navigator.geolocation.getCurrentPosition()`, writes
`#lat` / `#lng` (readonly inputs), and updates `#gpsStatus` (text). There is no map.

## 3. Design / plan
- Reuse **Leaflet 1.9.4** (already the project's map library — used by admin route-map) loaded
  from unpkg CDN: `<link>` for `leaflet.css`, `<script>` for `leaflet.js` in the head.
- Add a **container div** right **under the lat/lng input grid** (`<div id="gpsMap">`) that is
  hidden (`display:none`) until a location is available.
- After `ambilGPS()` gets a fix, it:
  1. stores the coords,
  2. **initializes (or updates)** a Leaflet map centered at those coords,
  3. shows a **marker (pin)** at `[lat, lng]` with a popup `Lat, Lng`,
  4. reveals the map container ("pops up") below the inputs.
- Handle re-presses: if the map already exists, move the marker + recenter instead of
  re-initializing (avoids flicker).
- Graceful failure: if GPS errors, keep the map hidden and show the existing error text.
- A tile layer (OSM/standard) renders the background around the pin.

### Layout (visual)
```
📍 Ambil dari GPS
[ Latitude : -6.2088 ] [ Longitude : 106.8456 ]
Lokasi: -6.2088, 106.8456          <- gpsStatus (existing)
┌────────────────────────────┐
│        small MAP            │  <- #gpsMap, pops up here, pin at coords
│       (pin ◎)               │
└────────────────────────────┘
```

## 4. Files changed
- `frontend/noo.html` — add Leaflet CSS/JS, `#gpsMap` container, `initGpsMap()` logic wired
  into `ambilGPS()`.

## 5. Acceptance criteria
- [ ] After pressing "Ambil dari GPS", a map appears under the lat/lng inputs.
- [ ] A pin/marker sits at the captured coordinates.
- [ ] Re-pressing does not duplicate the map; marker recenters.
- [ ] On GPS error, no map shows; error text still shown.
- [ ] Works offline? No (tiles need network) — same as existing route-map behavior.
- [ ] 3 QA subagents verify on the live page.

## 6. Deploy
- Commit + push; copy `noo.html` → LXC 112 (`/var/www/wim-sales/noo.html`). No backend change.