# Plan-Edit Template Grid — Date Context + Auto-Materialization (FINAL)

> **Status:** PLAN → implement → test · **Date:** 2026-09-12
> Diagnosis completed by 3 subagents (deleg_ca664fb7). Both problems confirmed.

---

## Confirmed findings

### Problem 1 — No date context on the Step-2 grid
- Cells render only `Hari3-Minggu2 …` (day-of-week × week-of-month, monthly repeating, Sun excluded). **No calendar date** and **no month selector** exists anywhere on Step-2 (the only date phrase is static "berulang setiap bulan").
- Backend mapping (deterministic, verified): `week = LEAST(CEIL(day_of_month/7),4)`; `dow = ISODOW` (1=Mon..6=Sat, Sun skipped). To know which date a cell is, you need a **reference month** + this formula.
- **Week-4 caveat:** days 22+ fold into W4; some weekdays can occur twice (e.g. Sep 2026 W4-D2 = 22 **and** 29). Display the first occurrence; mark the overhang.

### Problem 2 — Templates are never materialized into dated visits (root cause of "set it but can't find it")
- `POST /api/admin/plan/template/resolve` (→ `materialize_template_for_date`) **exists and works** (round-trip verified: 3 stores → appear in `/api/admin/rencana/view` with `source='template'`), but has **ZERO callers** (no frontend, no cron).
- Field app `do_MY_STORES` and admin `do_RENCANA_VIEW` read **only `wim_visit_plan`**. Templates write to `wim_visit_plan_templates` + `_template_stores` and stop.
- DB proof: **8 templates / 14 store assignments exist, but 0 `source='template'` rows in `wim_visit_plan`** for any date. Hence salespeople/admins never see the planned visits.

---

## Implementation

### A. Frontend — `admin/plan-edit.html`
1. **Reference-month selector on Step-2** (card header area): `‹ Sep 2026 ›` month paging + a text showing the active month. Defaults to the current month when the grid opens. State: `refYM` added to the state block.
2. **Per-cell date labels** in `renderTplGrid()`: for each `(week, day)` compute the concrete date(s) in `refYM` using the same formula as the backend (client-side pure JS: `week=LEAST(CEIL(dm/7),4)`, `dow=ISODOW`, skip Sun; first occurrence for W4 overlap with a `±` marker). Render a second line under `HariD-MingguW`, e.g. `Sen 07 Sep` (Indonesian short weekday + DD MMM).
3. Optionally append the date to `selectSlot`'s breadcrumb/header.

### B. Backend — auto-materialization (the sync fix)
Hook **on-read materialize** into:
- `do_MY_STORES` (field app "today's plan") — before reading `wim_visit_plan`, call `materialize_template_for_date(user_id, date)`.
- `do_RENCANA_VIEW` (admin Lihat-list, any date + the per-user filter) — same, for the requested date and optionally the filtered user.
- (Optional) `do_PLAN_DAY_GET` — same.
- This is **idempotent** (`INSERT … ON CONFLICT DO NOTHING`). No DB schema change (SQL functions already exist). Reconcile-on-edit: when a slot is re-saved, delete that date's `source='template'` rows then re-materialize, so edits propagate.

## Document
- `docs/PLAN-EDIT-TEMPLATE-CONTEXT-PLAN.md` (this file) = mapping explanation + materialization path + admin reference.
- Update `docs/PLAN-EDIT-TEMPLATE-REDESIGN.md` to note the grid now carries dates and visits auto-materialize.

## Test (after implement)
- 3 subagents per user flow: (1) admin saves a slot in the grid and confirms the per-cell date label matches the mapping + sees it in Lihat-list; (2) field app sees today's planned stores auto-materialized from a template; (3) editing a slot reconciles (stale rows removed, new ones appear).