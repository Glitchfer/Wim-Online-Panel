# Goovi Monthly Kunjungan Recap — DB Comparison & Gap Analysis

> **Date:** 2026-09-11 · **Source:** 3 monthly `Rekap_Kunjungan` exports (Jun/Agu/Juli 2026) + live `wim_sfa` schema.
> Recap granularity: **per sales-rep per day** (aggregated), 13 columns.

## 1. Goovi recap columns vs WIM database

Each Goovi row = one sales-rep + one date. Columns and their function → where WIM stores/derives them:

| # | Goovi column | Function | WIM source | Covered? |
|---|---|---|---|---|
| 1 | **Tanggal** | Visit date | `wim_visits.checkin_at` (DATE) | ✅ |
| 2 | **Nama Depo** | Depot the rep belongs to | `wim_user_meta.depot_id` → `wim_depots.name` | ✅ |
| 3 | **Nama Sales** | Salesperson (Goovi uses vehicle/rep name eg "AB 8501 EI") | `wim_users.name` (real person name) | ⚠️ WIM uses person name; Goovi used vehicle plate |
| 4 | **Jumlah Kunjungan** | # visits performed that day | `COUNT(wim_visits WHERE checkin_at)` | ✅ compute |
| 5 | **EC** | # visits that produced an order (effective call) | `COUNT(wim_orders)` joined by `visit_id` | ✅ compute |
| 6 | **Terkunjung** | # planned stores actually visited | `wim_visits` (status visited/completed) | ✅ compute |
| 7 | **Tidak Terkunjung** | # planned stores NOT visited | `wim_visit_plan` − `wim_visits` | ⚠️ compute (needs plan join) |
| 8 | **Luar Rute** | # off-route visits/orders | `wim_visits.source='luar_rute'` / `wim_orders.off_route_reason` | ✅ |
| 9 | **EC Rate (%)** | EC / Jumlah Kunjungan | derived | ✅ |
| 10 | **Jumlah Order** | total orders (line count or orders?) | `wim_orders` (or items) | ✅ |
| 11 | **Waktu Mulai** | first activity / clock-in time | `wim_visits` MIN(checkin) or `wim_attendance.clock_in` | ⚠️ per-day first visit OR attendance |
| 12 | **Waktu Selesai** | last activity / clock-out | `wim_visits` MAX(checkout) or `wim_attendance.clock_out` | ⚠️ |
| 13 | **Durasi** | Waktu Selesai − Waktu Mulai | derived **or** `wim_attendance.duration` | ✅ derived |

### Goovi summary sheet (rows 7-10)
Total CALL 62195 · Total EC 26134 · Total Luar Rute 10850 · EC Rate 42% — all derivable from the above aggregates.

## 2. Function mapping (Goovi/KlikOrder → WIM conceptual)

- **Jumlah Kunjungan / Terkunjung / EC** → the core SFA effectiveness metrics; WIM already computes
  `kunjungan`, `pesanan`, `noOrder`, `ecPct` in `do_ANALYTICS_RECAP`. Missing from WIM's recap tab:
  **Terkunjung vs Tidak Terkunjung** (planned-vs-actual), **timestamps (Waktu Mulai/Selesai/Durasi)**,
  and **Luar Rute count**.
- **Waktu Mulai/Selesai/Durasi** → Goovi captures a rep's work-day span. WIM has `wim_visits.checkin_at`/
  `checkout_at` per visit AND `wim_attendance` (clock_in/clock_out/duration). To replicate, either
  (a) derive day-span from MIN/MAX visit checkin/checkout, or (b) use `wim_attendance`. **Goovi's values
  (e.g. 09:15–15:28) match the attendance clock-in/clock-out pattern.**

## 3. What's MISSING from WIM (to match Goovi exactly)

1. **Terkunjung / Tidak Terkunjung (planned-vs-actual)** — WIM's recap doesn't split planned visits by
   visited vs missed. Requires joining `wim_visit_plan` (planned) against `wim_visits` (actual), and
   accounting for the new **template resolver** (planned = resolved template stores for that date).
2. **Durasi kerja per rep per hari (Waktu Mulai/Selesai)** — not explicitly aggregated in the recap.
   Most reliable source: `wim_attendance` (clock_in/clock_out); if absent, fall back to
   `MIN(checkin_at)..MAX(checkout_at)` of that sales' visits.
3. **Sales identified by vehicle plate** — Goovi uses the vehicle (e.g. "AB 8501 EI") as the rep label in
   recap. WIM uses the person's name; the **`wim_user_meta.vehicle_id`** field exists but there's no vehicle
   table (see Goovi/KlikOrder DB-gap doc). To show the same "Nama Sales" as Goovi, we'd either display the
   person's name (WIM) or the vehicle plate (requires `wim_vehicles`).
4. **"Tidak Terkunjung"** specifically needs the planned list for the date — the monthly-repeating template
   (now built) plus any ad-hoc `wim_visit_plan` rows.

## 4. Plan to make WIM complete

### Backend (`do_ANALYTICS_RECAP` extension) — additive, reversible
Extend the recap endpoint to also return, per (rep, date):
- `terkunjung` = COUNT visits with an actual visit row
- `tidak_terkunjung` = COUNT planned stores (via template resolver `resolve_template_for_date(user,date)`
  UNION `wim_visit_plan` rows for that date) MINUS those actually visited
- `luar_rute` = COUNT visits/orders with `source='luar_rute'` or `off_route_reason` set
- `waktu_mulai` / `waktu_selesai` / `durasi` = from `wim_attendance` (fallback MIN/MAX visit times)
- `jumlah_order` = COUNT orders

Group by `(user_id, DATE(checkin_at))` (per rep per day, like Goovi) instead of only by user.

### Frontend (Analitik → Rekap tab)
Add the missing columns to the recap table: Terkunjung, Tidak Terkunjung, Luar Rute, Waktu Mulai,
Waktu Selesai, Durasi, and show the summary totals (Total CALL/EC/EC%).
Allow CSV export to match Goovi's layout.

### Data model
- No new tables strictly required — all derivable from existing `wim_visits`, `wim_orders`, `wim_attendanc`,
  `wim_visit_plan`, and the template resolver.
- **Recommended (from prior gap doc):** create `wim_vehicles` + link `wim_users` to vehicles so "Nama Sales"
  can optionally show the vehicle plate like Goovi. This is the only schema addition and it's additive.

## 5. Priority
- **High:** extend recap with Terkunjung/Tidak Terkunjung, Luar Rute, Durasi, Jumlah Order per rep+day, and
  the plan-vs-actual view. This delivers the full Goovi recap.
- **Medium:** `wim_vehicles` table so rep↔vehicle mapping is possible (already a gap; unblocks "Nama Sales" = plate).
- **Low:** attendance-based Waktu Mulai/Selesai fallback to visits.

All changes additive & reversible; documented for future reference.