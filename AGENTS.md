# AGENTS.md — WIM Online (Standalone)

> Auto-injected by Hermes Agent when `workdir` is set to this project.
> Read this before any task. Abide by all rules.

## Non-negotiables (condensed)

1. **No mock data in production** — test data in separate DB or test mode only
2. **No hardcoded secrets** — everything in `.env` or Docker secrets
3. **Server-side validation** — never trust frontend for auth, totals, or geofence checks
4. **Destructive actions require authorization** — soft delete via status changes
5. **Production DB never reset by a worker** — no `migrate:fresh` in any script
6. **Architecture changes require approval** — no swapping ORM/DB/framework
7. **Order > 0 must have a verified check-in event** — core data integrity rule
8. **Order > 0 requires QR/barcode scan verification**
9. **Exports must include promo/free-product data**

## Scope rule

If a task lands in **"Out of scope for V1"** (see SCOPE.md), **STOP and escalate**. Do not implement it.

## Architecture reference

- **Deployment:** Python http.server on Proxmox LXC
- **Stack:** Python http.server (port 8080), PostgreSQL 15+, in-memory session cache
- **Network:** Static LAN IP, reverse proxy via NPMplus
- **Geofence:** Server-side distance calculation from GPS coordinates
- **Database:** PostgreSQL `wim_sfa` database — all data self-contained

### Database Schema (wim_sfa)

Core tables:
- `wim_auth.sessions` — authentication sessions
- `wim_users` — user accounts (bcrypt passwords, roles)
- `wim_karyawan` — employee records (linked to users)
- `wim_depo` — depot/branch data
- `wim_pelanggan` — customer stores (14+ fields: name, location, owner, channel, etc.)
- `wim_produk` — product catalog (multi-brand)
- `wim_visit_plan` — daily visit plans (user_id, store_id, date, priority, source)
- `wim_visits` — visit check-in/check-out records
- `wim_attendance` — attendance clock-in/out with photos
- `wim_orders` — order headers (status, total, payment method)
- `wim_order_items` — order line items (with is_bonus flag for promo tracking)
- `wim_stock_check` — per-store stock records
- `wim_promos` — promo definitions (bundling, strata, discount, bonus)
- `wim_kendaraan` — vehicle records
- `wim_channels` — sales channels (GT, MT, Horeka, Institutional)
- `wim_store_categories` — customer store categories per channel

### No Fleetbase Dependencies

This system is **fully standalone**. It does NOT depend on Fleetbase for any V1 feature:
- No Fleetbase API proxy (`/v1/*` endpoints removed)
- No Fleetbase MySQL database
- No Fleetbase Laravel API
- No Fleetbase SocketCluster
- No Fleetbase user/company models

All data lives in PostgreSQL `wim_sfa`. External integrations (Fleetbase, Odoo, Warehouse) are optional future sync layers defined in `FUTURE-INTEGRATION.md` — they are NOT V1 requirements.

## Definition of Done

A feature is Done when:
1. Acceptance criteria pass
2. Tests pass (no regression)
3. Data integrity verified (order links to visit event)
4. No dead code, no hardcoded values, Bahasa-friendly error messages
5. Documentation updated
6. Review completed

## Escalation conditions (stop and ask)

- Ambiguous requirement not covered in SCOPE.md or PROJECT-CHARTER.md
- Need to access WIM production data that isn't available in a dev mirror
- Integration with external system not documented in the scope
- Task that implies reintroducing Fleetbase dependency for V1

## Evidence required per task

- New files created: list them
- API calls made: include request/response
- Data created: include DB query or export showing the data
- Tests run: include pass/fail output

## Subagent QA loop (mandatory for every feature)

After implementing a feature, spawn 3 subagents to test it as a human would:

1. **Subagent A** — Sales rep persona (check-in, visit card, NOO, order, photo, stock, out-of-route)
2. **Subagent B** — Depot admin persona (route plan, admin order, report, export, user management)
3. **Subagent C** — Super admin persona (dashboard, settings, promo, analytics, full reporting)

Each subagent gets:
- The feature's context + AGENTS.md rules
- The GooVi/KlikOrder mapping docs (APP-MAPPING.md) for comparison
- A task to walk through the flow as a real user and submit structured feedback

**Gate rule:** A feature is NOT done until all 3 subagents agree it's suitable. If any says "No" or "Maybe", fix the issues and re-run the subagent loop. Unanimous approval required.