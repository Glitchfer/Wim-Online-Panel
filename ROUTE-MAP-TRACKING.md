# WIM Online — Enhanced Route / Travel Map

> **Date:** 2026-09-10
> **Purpose:** Turn the admin Route Map into a full travel-visualization map using the
> `wim_sales_positions` geolocation data gathered from the sales webapp — showing the salesperson's
> **travel route, current position, store visit/order status, attendance check-in/out, and depots** —
> so admin gets a rough tracker even without continuous GPS.

## What the map shows

1. **Store markers** colored by visit + order status (from `wim_visit_plan` + `wim_orders`):
   - 🟢 **green** = visited **and** an order was placed
   - 🔴 **red** = visited but **no order**
   - 🔵 **blue** = not yet visited
2. **Sales travel line** — an orange polyline connecting, in time order, the coordinates the sales
   logged when they opened/refreshed the app (`wim_sales_positions`, sorted by `recorded_at` per user).
   This reconstructs the salesperson's route across the day without a constant GPS tracker.
3. **Current / last-known position** — a green dot at each salesperson's most recent fix, with a
   popup showing when they last opened the app.
4. **Attendance check-in/out** — amber clock icons at the coordinates where the sales did their
   attendance check-in/check-out (`wim_attendance.location_lat/lng` for the selected date).
5. **Depots** — grey 🏭 warehouse icons at each `wim_depots` location.
6. A **rep filter** lets the admin isolate one salesperson (travel line + their stores only).

## API

- `GET /api/admin/route-map?date=YYYY-MM-DD` (admin) → returns:
  - `stores[]` — each with `storeName, address, lat/lng, userName, visited, ordered, color`
  - `travelLines[]` — per user: `{userId, userName, points:[{latitude, longitude, recordedAt}]}` (ordered)
  - `currentPositions[]` — per user last-known `{userId, userName, latitude, longitude, recordedAt}`
  - `attendance[]` — check-in/out `{userId, userName, clockIn, clockOut, latitude, longitude}`
  - `depots[]` — `{id, name, latitude, longitude}`

## Rules

- A store with an order on the date is treated as **visited** (green), even if its plan status wasn't
  marked "visited" (the order proves the visit).
- Travel line requires ≥2 logged fixes per sales; the line is filtered with the rep filter.
- No change to the geolocation capture itself (uses `wim_sales_positions`), so the same `POST /api/positions`
  + `wim_sales_positions` data models apply.

## Files changed

- `frontend/serve.py` — `do_ROUTE_MAP` endpoint (stores with color, travel lines, current pos, attendance, depots).
- `admin/admin-server.py` — proxy `/api/admin/route-map`.
- `admin/route-map.html` — rich map: orange travel polylines, green current-position dots, color-coded
  store markers (green/red/blue), amber check-in/out icons, 🏭 depot icons, updated legend + sidebar.

## Verification

- Route-map API: 15 stores (5 green / 1 red / 9 blue), 2 travel lines (Andi 4 pts), 2 current positions,
  1 attendance, 4 depots.
- Browser: map renders 22 markers (15 stores + 2 current + 1 attendance + 4 depots), orange polyline
  layer present, no JS errors, sidebar lists stores with status badges.