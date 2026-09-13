# WIM Online — Geolocation / Sales Position Tracking

> **Date:** 2026-09-10
> **Purpose:** Sales rep geolocation is captured + persisted every time they open/refresh the app,
> the Kunjungan menu highlights stores within ~10 m, and check-in validates the rep is within
> ~10 m of the store. This powers later reporting (route tracing, EC/effective-call, attendance
> by location).

## Behavior

1. **Capture + persist position** — the sales webapp gets the GPS position on every page load and
   refresh (`WIM_Geo.track()`), POSTs it to `POST /api/positions` which inserts into
   `wim_sales_positions(user_id, user_name, latitude, longitude, accuracy_m, recorded_at)`. This
   gives a time-series of each salesperson's location that can be joined to visits/orders later.
2. **Kunjungan menu glow** — on the visit-card (Kunjungan) page, after capturing a fix the store
   list is re-rendered: stores within `10 m` of the reported position glow green (`.in-range`
   class + "🟢 Dalam Jangkauan ≤10m" badge). Position is refreshed every page change/refresh.
3. **Check-in geofence** — `do_VISITS_POST` (checkin) now validates the rep's reported location
   against the store's coordinates (Haversine); if > 10 m it returns a clear error and blocks the
   check-in. If either the store coords or the rep's location is unavailable, check-in proceeds
   (no false block).

## API

- `POST /api/positions` `{latitude, longitude, accuracy?}` — persist a position fix (auth required).
- `GET /api/positions/latest` — the caller's most recent recorded position.
- `GET /api/positions/all` (admin) — latest position per sales user + recent trend of app-opened fixes; powers the dashboard + route-map views.

## Admin viewing (sales whereabouts)

- **Dashboard home (`dashboard.html`)** — "📍 Lokasi Sales" card: a Leaflet map with one dot per sales at their current (latest) position, plus a table of last-known position per rep (name, coords, "just now"/N m ago).
- **Route map (`route-map.html`)** — plots red dots where each sales opened the app / refreshed (from `wim_sales_positions` trend), alongside the route-plan markers, so the admin can see where sales have been during the day.

## Files changed

- `deploy/db/init/04-sales-positions.sql` (new) + `01-schema.sql` — `wim_sales_positions`.
- `frontend/serve.py` — `haversine_m`, `do_POSITION_POST`, `do_POSITION_GET`, check-in geofence.
- `frontend/js/app.js` — `WIM_Geo` shared util (capture/report/distance/inRange).
- `frontend/visit-card.html` — track position on load; glow in-range stores; use rep's location on check-in.
- `frontend/dashboard.html` — track position on landing (page change/refresh).
- `frontend/css/app.css` — `.in-range` glow styles.

## Verification

- `POST /api/positions` → 200, row persisted with time + user id/name + coords.
- Check-in from ~157 km away → blocked (`Lokasi terlalu jauh ... max 10m`); at the store → succeeds.