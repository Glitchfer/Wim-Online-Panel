# WIM Online — QA Repair Log (from 20-reviewer + 3-QA findings)

> Consolidates actionable `BUG` findings from the expert reviewers and tracks the
> repair/iteration loop. Each row: finding → fix → verification.
> Legend: ✅ fixed · 🔧 in progress · ⏸ deferred

## A. Confirmed bugs — already fixed (committed/deployed pending restart)

| # | Finding (reviewer) | Fix | Status |
|---|---|---|---|
| A1 | Orders CSV column misalignment (11 fields/10 headers) | Dropped stray `offRouteType` in orders.html downloadCsv | ✅ code |
| A2 | Analytics gallery CSV header/data mismatch | Added missing `Foto` column | ✅ code |
| A3 | Attendance duration parse (`.` vs `:`) | `split(/[:.]/)` in absensi.html | ✅ code |
| A4 | Packing/order-stock SKU fragmentation | `GROUP BY sku`, `MAX(name)` | ✅ committed |

## B. New actionable bugs from batch-2 reviewers (this session)

| # | Finding (reviewer) | Fix plan | Status |
|---|---|---|---|
| B1 | `POST /api/orders/verify` → 500 `column "public_id" does not exist` | Fixed → `order_ref`; added `verified_at` column | ✅ code |
| B2 | Order list `itemCount:0` vs detail 5 items | Added `itemCount` (non-bonus qty) to list | ✅ code |
| B3 | `GET /api/visits` no-date → SQL error leak | Default `date` to today for cookie users | ✅ code |
| B4 | `POST /api/orders/calculate` trusts client price → grandTotal=0 | **Deferred** (needs server reprice refactor; flagged, higher risk) | ⏸ |
| B5 | Dashboard `completionPct`/`geofenceCompliancePct` = 0 despite visits | `storesVisited` from real visits; admin uses it | ✅ code |
| B6 | Promo `periode_start` ignored (future promo applied) | Enforce `periode_start <= today` in calc feed | ✅ code |
| B7 | Promo `stackable:false` not honored | Stacking guard in calc loop | ✅ code |

### B8 (batch-3, RBAC/locale/UI) — new repairs
| # | Finding (reviewer) | Fix | Status |
|---|---|---|---|
| B8a | Store lat/lng wiped on Edit (proxy returns `lat`/`lng`, form read `latitude`/`longitude`) | Proxy emits both keys; openEdit tolerates both | ✅ code |
| B8b | Localization leftovers: "Simpan Cambios", "Add Produk", "Activate/Deactivate", "Kordinasi", "Kelmarin" | → "Simpan Perubahan", "Tambah Produk", "Aktifkan/Nonaktifkan", "Koordinasi", "Kemarin" | ✅ code |
| B8c | RBAC: depo_admin sees all-company data (users NIK/NPWP, positions GPS, stores, visits) — F1–F5 | **Deferred** (full server-side RBAC rework, per release critic; high-risk, post-pilot) | ⏸ |
| B8d | Cookies no `Secure` flag + HTTP transport | **Deferred** (needs HTTPS/TLS deployment) | ⏸ |
| B8e | Stores list intermittently blank (loader not auto-run) | **Deferred** (frontend init; flagged) | ⏸ |
| B8f | `verified_at`/`public_id`/`grand_total` column mismatches flagged by data-model reviewer | `public_id`→`order_ref` fixed (B1); others noted | ✅/⏸ |

### B9 — P4 stock feature verification found (FAIL → repaired)
| # | Finding (verifier) | Fix | Status |
|---|---|---|---|
| B9a | `POST /api/admin/stock-balance` always HTTP 500 (`tuple indices ... kind str`) — plain cursor + `fetchone()['id']` | Use RealDictCursor | ✅ **verified live**: POST → 201 |
| B9b | `GET` stock-balance didn't return `note` → UI "Catatan" always `-` | Added `sb.note` to SELECT | ✅ **verified live**: note returned |
| B9c | `product_name` NULL when posting by sku (sku not resolved to product_id) | Resolve `product_id` from `wim_products` by sku in POST | ✅ **verified live**: new row id7 → product_name "SANQUA 550ML Bottle" |

> P4 now: render/filter/empty-state/validation-400 all PASS (verifier), plus POST→201, note, product_name verify live after fix deploy + wim-mid restart.

### B10 — Feature-verification results summary (feat QA, 4 subagents)
- **Invoice & Receivables (P2): PASS 5/5** — render, aging buckets, create-invoice (grand_total server-side = order.total), dedup-409, deterministic invoice_no all verified live.
- **Store enrichment (P5): PASS** — form fields present, edit prefill, PATCH persists (credit_limit + salesperson), propagates to middleware.
- **Bug fixes (A1/A2/B3/B4-report): PASS live** — orders CSV = 10 cols aligned; gallery CSV header=5=cell; `/api/visits` no-date = 200; `/api/report` returns nonzero.
- **Stock on-hand (P4): FAIL initially** → defects B9a/B9b/B9c now fixed in code (awaiting restart).

## C. Infrastructure / deferred (already documented in plan; not rebuilt this session)
- No offline queue / no PWA (sw.js 200-login) — deferred per release critic (reuse wim_sync_queue later).
- No barcode/QR scan, no map "my location", no payment collection in field — deferred.
- Photos as base64 in DB — deferred (size-cap later).
- GPS depends on HTTPS / non-standard `navigator.geolocation` — needs HTTPS; deferred (deploy concern).
- No server-side XLSX/PDF / bulk export — deferred.
- Admin nav on field app points to internal `192.168.6.113:8001` — deployment/URL config.
- `wim_order_items` stale stub vs `items` JSONB dual-source — flagged; not re-normalized this session.

## D. Verified-working (from QA batch-1) — no action
- Analytics recap/performance/packing/order-stock/gallery/store-orders all **PASS** vs independent SQL.
- Promo lifecycle (create/active/catalog/cart/order) works; per-area activation works; inactive/expired excluded.