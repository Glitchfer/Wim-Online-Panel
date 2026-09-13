# Roadmap — WIM Online

## Gate structure

Gates are sequential. Each gate has entry criteria (what must be true before starting), acceptance criteria (what proves it's done), and exit criteria (what must be true to call it complete).

---

### G0 — Foundation & Infrastructure Setup

**Entry:** Project charter signed off, LXC host identified, domain name secured

| Task | Dependencies | Est. effort |
|---|---|---|
| Create privileged LXC on Proxmox (nesting=1, 4C/6GB/24GB) | Host ready | 30 min |
| Install Docker CE on LXC (Debian repo) | LXC created | 15 min |
| Set up Python http.server project | Python ready | 15 min |
| Run `serve.py` with PostgreSQL connection | Project set up | 5 min |
| Configure NPMplus reverse proxy for WIM subdomain | App running | 20 min |
| Configure database connection in .env | PostgreSQL installed | 5 min |
| Verify console accessible via domain, API responds | Proxy configured | 5 min |

**Acceptance:** WIM Online loads at public domain, API responds at `:8080`, auth system works.
**Exit:** Infrastructure documented in ARCHITECTURE.md, credentials saved to vault.

---

### G1 — Core Data Setup (Stores, Products, Users)

**Entry:** Python http.server and PostgreSQL running and accessible

| Task | Dependencies | Est. effort |
|---|---|---|
| Create Company record for WIM | G0 done | 5 min |
| Create WIM super admin user | Company created | 5 min |
| Import store data (Places) from current WIM data | Data export from KlikOrder/Groovi | 2-4 hrs |
| Create circular Zone geofences (10m) per store | Places imported | 1-2 hrs |
| Create Contact records (store owners) per store | Places imported | 1 hr |
| Import product catalog as Entities | Product list from Sanqua | 1 hr |
| Set up promo/bundling metadata on relevant products | Products imported | 2 hrs |
| Create Depot grouping | Company created | 15 min |
| Create Driver records (sales reps) linked to Depots | Depots created | 30 min |
| Create Vehicle records | Depots created | 30 min |

**Acceptance:** All WIM stores, products, users, drivers, and vehicles exist in PostgreSQL `wim_sfa`. 10m geofences active per store. Admin can browse stores on the map.
**Exit:** Data import scripts saved in repository for repeatability.

---

### G2 — Route & Visit Workflow

**Entry:** G1 complete — stores, geofences, drivers, products in system

| Task | Dependencies | Est. effort |
|---|---|---|
| Create 4-week route schedule (20 route presets per depot) | G1 complete | 2-3 hrs |
| Assign routes to drivers | Routes created | 30 min |
| Verify geofence detection: POST /v1/drivers/{id}/track → GeofenceEntered | Geofences active | 1 hr |
| Build custom frontend (or configure Navigator) for sales rep check-in flow | API verified | 4-8 hrs |
| Implement selfie/photo attachment on tracking event | Check-in flow working | 2 hrs |
| Implement 3-minute minimum timer (frontend) | Check-in flow working | 1 hr |
| Implement no-order reason submission | Check-in flow working | 1 hr |
| Implement store stock tracking per SKU | Check-in flow working | 2 hrs |
| Implement visit gallery (photo + description) | Photo attachment working | 1 hr |

**Acceptance:** A sales rep can check in at a store (geofence triggers), take selfie, submit no-order with reason, or record store stock. Visit events logged with timestamps.
**Exit:** End-to-end visit flow documented and tested with a real phone.

---

### G3 — Order Management

**Entry:** G2 complete — visit workflow functional

| Task | Dependencies | Est. effort |
|---|---|---|
| Build product catalog browsing (brand filter, promo visibility) | G1 products, G2 visit flow | 3-4 hrs |
| Implement cart with bundling auto-add | Product catalog | 2-3 hrs |
| Create order submission (POST /v1/orders) | Cart functional | 1 hr |
| Generate QR code per order (order reference) | Order creation | 1 hr |
| Implement barcode scan verification (order > 0 must scan) | QR generation | 2 hrs |
| Implement out-of-route ordering with reason | Order creation | 1 hr |
| Implement COD payment field on order | Order creation | 30 min |
| Implement order history view per store/driver | Orders in DB | 1 hr |
| Implement admin order creation (scan store barcode) | Order API | 1 hr |

**Acceptance:** Sales rep can browse products, add to cart, bundling auto-applies, submit order, scan QR for verification. Admin can create orders. Out-of-route orders require reason.
**Exit:** Order integrity verified — every order > 0 has a matching check-in event + QR scan.

---

### G4 — Reporting & Admin Dashboard

**Entry:** G3 complete — orders flowing in

| Task | Dependencies | Est. effort |
|---|---|---|
| Build visit monitoring dashboard (daily/monthly export) | G2 visit data | 2-3 hrs |
| Build order export with promo/free-product data | G3 order data | 1 hr |
| Build route visualization (map with store markers, route lines) | G2 routes | 2 hrs |
| Build attendance/photo gallery view | G2 photos | 1 hr |
| Build sales portfolio analysis (active/inactive stores, ratios) | G1+G2 data | 2 hrs |
| Build depot performance recap | All data | 2 hrs |
| Build store stock performance (order vs stock analysis) | G2 stock data | 2 hrs |
| Build mass PDF download (surat jalan/invoices) | G3 orders | 2-3 hrs |
| Build packing list generation per route/vehicle | G3 orders | 1 hr |

**Acceptance:** Super admin can run all reports currently available in Groovi + KlikOrder panels. Export to Excel/PDF works.
**Exit:** Feature parity with current Groovi + KlikOrder reporting confirmed.

---

### G5 — Go-Live & Migration

**Entry:** G0-G4 complete, all features verified

| Task | Dependencies | Est. effort |
|---|---|---|
| Data migration: export all current KlikOrder+Groovi data | G1 import scripts | 4-8 hrs |
| UAT with 3-5 sales reps for 1 week | G4 done | 1 week |
| Parallel run: both systems active, compare outputs | UAT passes | 2 weeks |
| Sales rep training + documentation | Parallel run | 2-3 days |
| Cutover: disable KlikOrder + Groovi | Parallel run passes | 1 day |
| Production monitoring + bugfix | Cutover | 2 weeks |

**Acceptance:** All WIM sales reps use WIM Online exclusively. Order + visit data matches or exceeds previous accuracy. KlikOrder and Groovi decommissioned.
**Exit:** Post-mortem report written, lessons learned documented.