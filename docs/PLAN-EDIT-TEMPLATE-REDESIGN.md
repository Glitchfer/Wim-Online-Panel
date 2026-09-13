# Plan-Edit Redesign — Monthly Repeating Route Template (Plan & Implementation)

> **Date:** 2026-09-11 · **Status:** Implement (design consulted)
> Based on 3-subagent design consultation (data model, UI/UX, route map) — consolidated here.

## 1. Goal
Replace the calendar-date plan editor with a **monthly-repeating template**:
`day1..day6 × week1..week4` (4 weeks × 6 days Mon-Sat = 24 slots), repeated every month.
Each slot holds an **ordered** list of stores (the route). Admin can filter available stores by
**provinsi→kota→kecamatan→kelurahan** (bundle nearby) and see a **live numbered route map** that
syncs with the reorderable list.

## 2. Data model (from consult)
Existing (already in live DB, in `01-schema.sql`):
- `wim_visit_plan_templates(id, depot_id, user_id, nama_template, week_number, day_of_week, is_active, created_at)`
- `wim_visit_plan_template_stores(id, template_id, store_uuid, visit_order, created_at)`

**Migrations needed (additive):**
1. `UNIQUE(user_id, week_number, day_of_week)` on templates (dedup slot; add partial index/constraint).
2. `UNIQUE(template_id, store_uuid)` on template_stores.
3. Stored functions:
   - `resolve_template_for_date(p_user_id, p_date) RETURNS TABLE(store_uuid, visit_order)` —
     computes week-of-month + ISODOW, returns the slot's stores.
   - `materialize_template_for_date(p_user_id, p_date)` — copies a slot's stores into
     `wim_visit_plan` (date-based execution table) `ON CONFLICT DO NOTHING`.
4. **Keep** `wim_visit_plan` for daily field execution (status, seq_no, real dates). Template =
   monthly "recipe", resolved on demand.

### Week-of-month rule (documented)
`week_of_month = LEAST(CEIL(DAY/7), 4)`; `day_of_week = ISODOW` (1=Mon..6=Sat; skip Sunday=7).
Repeated identically every month.

## 3. Backend endpoints (additive, admin role)
- `GET  /api/admin/plan/templates?user_id=` → list of 24 slots with store counts.
- `GET  /api/admin/plan/template?user_id=&week=&day=` → one slot's ordered stores (+ available stores filtered).
- `POST /api/admin/plan/template` → save a slot's ordered store list (replace, seq=position).
- `POST /api/admin/plan/template/resolve` → {user_id, date} → materialize into wim_visit_plan today (for field app).
- Extend store picker to return `latitude, longitude, address, kecamatan_id, kelurahan_id` for map + address filter.

## 4. Frontend — `admin/plan-edit.html`
### Step 2: 4×6 template grid (not calendar)
- Rows=Week1..4, columns=Day1..6. Cells labelled `Day3-Wk2` etc. Each cell shows planned store count + first-store previews.
- Click selects "active slot" (highlight). No calendar dates; repeats monthly.

### Step 3: address-cascading store picker
- 4 cascading selects (Provinsi/Kota/Kecamatan/Kelurahan) using `/api/wilayah`.
- Filter the available store list **client-side** by `kecamatan_id`/`kelurahan_id` (stores loaded once; instant, low clicks).
- Same active-slot flow: click cell → filter → pick store → into slot's ordered list.

### Step 3: live route map
- Leaflet 1.9.4 (already used in route-map) loaded in head.
- Numbered DivIcon markers 1..N by list order, red polyline through ordered geo stores,
  tooltip (hover) + popup (click) with store name/address/region.
- `scheduleRender()` (150ms throttle) called after every mutation (moveKunj/addToPlan/removeFromPlan/drop).
- Stores with null lat/lng: kept in list (marked "tak berpeta"), excluded from map/polyline; numbering follows full list (n=idx+1).
- Lazy init + `invalidateSize()` when step 3 opens.

## 5. Store fields required (from plan-day endpoint)
`s.latitude, s.longitude, s.address, s.kecamatan_id, s.kelurahan_id, s.kecamatan, s.kelurahan`
so both the map and address filters work.

## 6. Acceptance
- [ ] Step 2 shows Day1-Wk1..Day6-Wk4 grid (no calendar).
- [ ] Click cell = active slot; count + preview update.
- [ ] Store picker has 4 cascading region filters; filters narrow list.
- [ ] Add/move/remove updates slot ordered list + cell badge.
- [ ] Live Leaflet map shows numbered pins + red polyline, updates on reorder.
- [ ] Save persists to template tables.
- [ ] Resolver maps a real date to a template slot for the field app.
- [ ] 3 QA subagents verify end-to-end.

## 7. Deploy & rollback
Commit, push; apply migration; deploy `admin/plan-edit.html` + `frontend/serve.py` + `admin/admin-server.py`
proxies to LXC 113/111. Rollback = DROP new functions/constraints (additive; wim_visit_plan untouched).