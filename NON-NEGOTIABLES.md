# Non-Negotiables — WIM Online

## Hard rules (never violate without approval)

1. **No mock data in production.** Test data lives in a separate database or test mode. Production DB is real WIM data only.

2. **No hardcoded secrets.** API keys, DB passwords, Redis passwords — all in `.env` or Docker secrets. Never in code or config files committed to git.

3. **Server-side validation, never trust the frontend.** Order totals, geofence intersections, driver assignments — all validated server-side. Frontend is display + input only.

4. **Destructive actions require authorization.** No soft deletes bypassed by accident. Delete = status change to `cancelled`/`archived` unless explicitly approved.

5. **Production DB never reset by a worker.** No `migrate:fresh` or `DB::statement('drop table ...')` in any deployment script or scheduled job.

6. **No architecture changes without approval.** Changing database, framework, or core architecture requires explicit sign-off.

7. **Geofence verification is server-side.** The 10m check-in radius is enforced by Fleetbase's MySQL spatial queries (`ST_Contains`), not by the phone's GPS reading alone. The phone reports its position; the server decides if it's inside the zone.

8. **Every order > 0 requires a verified check-in event.** An order cannot exist without a corresponding `GeofenceEntered` event for that driver at that store on that day. This is the core data-integrity fix for the current GooVi→KlikOrder sync problem.

9. **Barcode/QR verification for orders > 0.** When a sales rep submits an order > 0, the system must generate a QR code (order reference), and the rep must scan it to confirm the order was actually placed. No auto-verification bypass.

10. **Export data must include promo/free-product information.** Unlike KlikOrder's current omission, all order exports include line-item-level promo details.

11. **Visit completion is explicit; orders survive failed visits.** A visit with a pending order that times out, crashes, or loses session must NOT lose the order data. The order lines survive; the visit can be resumed/completed. No silent deletion of orders.

12. **EC (Effective Call) computed from verified orders, not hand-typed counts.** The "effective call" measure for portfolio analytics uses the actual order records in the system, not a separate manually-entered "jumlah order" field. This is the core data-integrity fix for the GooVi→KlikOrder trust gap.

13. **Exports separate product lines from promo/bonus lines.** Line items show: purchased product, qty, unit price; bonus/free product, bonus qty, promo name, promo reference. No merged or code-only promo output.

## Authorization matrix

| Action | Super Admin | Depot Admin | Sales Rep (Driver) |
|---|---|---|---|
| Create/Edit store (Place) | ✓ | ✓ | ✓ (NOO only) |
| Create Order | ✓ | ✓ | ✓ |
| Delete Order | ✓ | ✗ | ✗ |
| Edit Route | ✓ | ✓ | ✗ |
| View all reports | ✓ | Own depot only | Own visits only |
| Manage users | ✓ | Own depot only | ✗ |
| Manage vehicles | ✓ | ✓ | ✗ |
| Export data | ✓ | Own depot only | Own data only |
| Promo management | ✓ | ✗ | ✗ |
| Bypass 3-min timer | ✗ | ✗ | ✗ |

## Data integrity rules

- A `no-order` visit must have a `reason` field populated
- An out-of-route order must have an `off_route_reason` populated
- A driver cannot check in at two different stores simultaneously (server-enforced — no overlapping `entered` events without intervening `exited`)