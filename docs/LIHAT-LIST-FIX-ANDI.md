# Lihat List Kunjungan — fix: always opened Andi Test

> **Status:** FIXED · **Date:** 2026-09-12

## Bug
On the admin **Lihat List Kunjungan** page (`today-plan.html`), clicking the row of any
sales rep (their visit detail) always opened **Andi Test** instead of the selected rep.

## Root cause
The middleware endpoint `do_RENCANA_VIEW` (`/api/admin/rencana/view`) **ignored the
`user_id` query parameter** — it always queried every rep's plan for the date. Because the
response is ordered alphabetically by name, **Andi Test** was always first. The frontend
`openDetail(uid)` then did `const s = (d.sales||[])[0]`, i.e. it always picked sales[0] =
Andi Test for *any* row clicked.

## Fix
1. **Backend** (`frontend/serve.py`): `do_RENCANA_VIEW` now reads `user_id` and applies
   `AND vp.user_id=%s` to the plan query. Placeholder ordering is exact:
   `[6 subquery dates] + [plan date] + [optional user_id]` (the 6 DATE()= subqueries
   precede the WHERE clause in the SQL text). Verified live: `user_id=3`→only **Budi Rep**,
   `user_id=16`→only **Arman**, `user_id=2`→only **Andi Test**, no filter→all 4.
2. **Frontend** (`admin/today-plan.html`): `openDetail(uid)` now finds the clicked user by
   id in the response (`sales.find(x => x.userId === uid) || sales[0]`) as a defensive
   fallback, instead of blindly taking `sales[0]`.

No DB change. Commits: `f9531a5`.

## QA
3 subagents verified the fix on the live panel (deleg: see session) — diagnosis, checklist
and PASS/FAIL results appended below as they report.