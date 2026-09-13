# WIM Online — Change Log

> Tracks every modification to the WIM Online app for future reference.
> Format: date | area | change | reason | verification

---

## 2026-09-10 — Absensi & check-in photo capture: front-face (selfie) camera fix + switch to the phone's native camera app

**Changes: attendance (clock-in/out) and store-visit check-in photos now open the phone's built-in camera app instead of a custom in-page live preview + shutter. Absensi and the check-in selfie use the FRONT/selfie camera; the store-exterior photo keeps the rear camera. This fixes the reported bug where the absensi "selfie" opened the REAR camera on a phone and only used the front webcam on a laptop browser.**

**Root cause:** the old implementation used `navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })` — a custom in-page live preview with a "take photo" shutter button. `facingMode: 'environment'` explicitly requests the **rear** camera, so on a phone the attendance (meant to be a face selfie) opened the rear lens, while on a laptop (which has no rear camera) the browser fell back to the webcam — producing the "works only on laptop" behavior. The custom preview/shutter also requires an HTTPS or localhost origin and is unreliable on phones (which is why every flow already carried a fallback file-picker). Replaced with the native camera app via `<input type="file" accept="image/*" capture="...">`, which is far more compatible and always uses the correct lens.

| Area | File | Change | Verification |
|---|---|---|---|
| Attendance photo (clock-in/out) | `frontend/absensi.html` | Removed the `getUserMedia` live-preview + shutter (`startCamera`/`captureFromCamera`/`fallbackToFileInput`/`photoCaptureStream`, the `<video>`/`<canvas>` and the extra `nativeCameraInput`). Clicking Mulai Kerja/Selesai Kerja now opens the phone's **native FRONT (selfie) camera** via `<input type="file" accept="image/*" capture="user">`; result shows in the modal with Gunakan / Ambil Ulang / Batal | Fixes the rear-camera bug for the face selfies + better device compatibility |
| Check-in selfie | `frontend/visit-card.html` | `captureSelfie()` now opens the **native FRONT camera** (`capture="user"`) through a modal "Buka Kamera Depan" button. Removed the `getUserMedia` preview (`selfieStream`, `captureSelfieFromPreview`, the fallback toggle). Cancelling the camera resolves the pending check-in with `''` so the button no longer hangs disabled | Front-facing selfie with the native app; robust cancel path |
| Store "Foto Toko" (multi-photo) | `frontend/visit-card.html` | Taken with the **native REAR camera** (`capture="environment"`) via "Ambil Foto" → thumbnails (still multi-shot, captions, remove, Selesai). Removed `startLivePreview`/`captureFromLivePreview`/`fallbackToFile`/`camPreviewStream` and the preview `<video>`/`<canvas>` | Store exterior photos intentionally use the rear/primary lens |

*Desktop behavior:* `capture` is ignored by desktop browsers, where the hidden `<input type="file">` falls back to the normal file picker — so the same code works for both mobile (native camera app) and laptop (file picker). No backend/server, DB, or API change was needed (photos are still submitted as the same base64 data URL; `checkin_photo` and attendance photo fields unchanged).

**Verification:** Both files' inline JS pass `node --check` (no syntax errors); every `getElementById()` reference resolves to an `id` defined in the page markup; `capture` attributes verified (`user` for absensi + check-in selfie, `environment` for store photos); no stale references to the removed functions/elements remain.

| Docs | CHANGELOG |

---

## 2026-09-10 — Promo system rework: 2 canonical types, region-scoped, graphical admin builder

**Changes: promo reworked to exactly two types + region scoping + no-JSON graphical admin UI.**
| Area | Change | Verification |
|---|---|---|
| DB (`wim_promo`) | Added `region_id INT REFERENCES wim_regions(id)`. `jenis` consolidates to `bundling` + `diskon` (legacy `strata`/`bonus` still read for back-compat) | `ALTER TABLE` applied live; column confirmed; index `idx_promo_region` |
| Middleware `do_ORDER_CALC` | Reworked engine: **bundling** = buy N of a SKU (any of several `required_sku` thresholds) → bonus free SKU; **diskon** = multi-SKU combo (ALL `required_sku` rows must be in cart) → one flat IDR order-level discount (applied once, not per-unit). Legacy vocab normalization retained | Calc tests: 20×SQA→+2 bonus; 5 SQA +5 LVT→−Rp50,000; neither met→no promo; both→+2 & −50k |
| Middleware `do_PROMOS` (sales) | Region-scoped: rep's depot→region resolves promo list; promos for other regions excluded | Rep (region 1) sees only region-1 promos |
| Middleware `do_PROMOS_ADMIN_POST/PATCH` | Accept structured builder payload `{requirements:[{sku,qty}], reward:{type:'free_sku',sku,qty}|{type:'discount_amount',amount}, regionId}` + ASCII-safe nama | Create/edit round-trip verified |
| Admin `promos.html` | **Rewritten:** graphical builder (radio Bundling/Discount), region filter (`Semua Region` dropdown), dynamic SKU+Qty requirement rows, bonus-SKU qty OR discount-Rp reward picker, no JSON. Edit pre-fills from stored conditions/rewards | Deployed to CT113, served 200 |
| Docs | `DATABASE-MAPPING.md` (jenis + region_id), `PROMO-REWORK-PLAN.md` (new), CHANGELOG | Committed |

*Note: DB runs `SQL_ASCII`; promo names are ASCII-sanitized in middleware to avoid response-encoding failures (non-ASCII chars replaced with `?`).*

---

## 2026-09-10 — Pricing page: Indonesian localization fixes (from QA)

**Changes: cleaned the mixed Spanish/Indonesian strings the area-price QA flagged — the UI is now consistently Indonesian.**
| Area | Change | Reason | Verified |
|---|---|---|---|
| `pricing.html` | "Confirme & Simpan" → "Confirm & Simpan" (both main bar + modal); "Configuración" → "Configurasi"; "efectivo/efectif da" → "efektif da"; "Tanggal set (efectivo" → "(efektif"; fixed "Harga Area Ake (" typo → "Harga Area Aktif ("; "(— Area dipilih —)" → "(Area belum dipilih)" | QA: mixed Spanish/Indonesian labels in an Indonesian admin + a "Ake" typo | Browser-verified: no "Confirme/Configuración/efectivo/Ake" remain; "Confirm & Simpan/Configurasi/efektif/Harga Area Aktif" present; 5 area checkboxes + 10 product rows, no errors |
| Middleware | (no change — the regionIds `ANY(%s)::int[]` cast error flagged in this QA was already fixed in an earlier commit: `= ANY(%s)` without the cast; promo list + regionIds verified live returning 5 promos) | Regression confirmation | Verified |

---

## 2026-09-10 — Depo: add + edit capability, set radius/coords/address, remove misleading Map button

**Changes: the Depo admin page now lets an admin add a new depo and edit existing depo data (name, address, latitude/longitude coordinates, region, and the check-in radius / depo size). The misleading "→ Map" link was removed.**
| Area | Change | Reason | Verified |
|---|---|---|---|
| Middleware | `POST /api/depots` (create) + `PATCH /api/depots/:id` (edit name/address/kode/coords/radius/region/is_active); depot GET now returns `kodeDepo` + `regionId`; wired into POST + PATCH dispatch | Add + edit depo data | Create (id 5) returned ok; PATCH radius 60→70 + name/address edited; GET returns regionId/kodeDepo |
| Admin-server | `do_DEPOTS_POST` + `do_DEPOT_PATCH` proxies + dispatch in do_POST/do_PATCH; depot GET passes kodeDepo/regionId | Reach via admin server | CRUD via `/api/admin/depots` + `/api/admin/depots/:id` verified |
| `depots.html` | Added **"＋ Tambah Depo"** form + **✏️ Edit** button per row (prefill name, kode, address, region, lat/lng, radius). Radius field = check-in geofence radius for depot attendance. Removed the misleading **"→ Map"** link (depots already render as 🏭 icons on the route map) | User: "edit depo feature missing, admin should add depos, set radius/coords/address; Map button misleading" | Browser-verified: Add form toggles, Edit prefills (name/radius/region), no Map link, 4 depots listed |
| Docs | `DATABASE-MAPPING.md`, CHANGELOG | |

---

## 2026-09-10 — Pesanan page: click an order → invoice/order-confirmation detail modal (same as QR)

**Changes: in the admin Pesanan page each order row is now clickable and opens a modal showing the full order confirmation in the same "Kupon Pesanan" style the store gets when it scans the QR.**
| Area | Change | Reason | Verified |
|---|---|---|---|
| Admin-server | `do_ORDER_DETAIL` proxy: `GET /api/admin/orders/detail?uuid=` → forwards to the public order-confirmation endpoint (`/api/orders/public`) so admin sees the identical shape (header, items, subtotal, disc, grand, CONFIRMED·UNPAID) | Reuse the QR/invoice payload | Admin orders now return `uuid`; detail endpoint returns orderId/store/items/subtotal/grandTotal/CONFIRMED |
| `orders.html` | Rows are clickable; click opens a modal rendering an invoice-style **KUPON PESANAN** sheet: company, CONFIRMED·UNPAID badge, Toko/Akun, Sales, No. Pesanan, Tanggal, Item/Trx, Pembayaran, item table (produk/qty/harga/total incl. bonus rows), Subtotal/Diskonto/GRAND TOTAL, footer note; a Print/PDF button | Admin needs the same order detail the buyer sees | Browser-verified: click row → modal shows real order (TOKO KANTIN GRHA SANQUA, WIM-20260910-8D671F87, AMDK 220ml ×2 = Rp31.700, subtotal/grand, CONFIRMED·UNPAID) |
| Docs | CHANGELOG | |

---

## 2026-09-10 — Rencana Kunjungan rework: two-menu (Edit + View) with drag-drop editor + per-visit detail drill-down + check-in selfie fix

**Changes: "Rencana Kunjungan" nav is now a dropdown with Lihat List Kunjungan (view) and Edit List Kunjungan (edit). The edit page is a 3-step workflow (sales → week/day calendar → drag-drop numbered kunjungan list). The view page has a calendar + per-sales table (status, in/out route counts) + detail drill-down (foto checkin / foto tambahan / cek pesanan / stock toko). Check-in now captures a separate selfie.**
| Area | Change | Reason | Verified |
|---|---|---|---|
| DB (`05-rencana-kunjungan.sql`) | `wim_visits.checkin_photo` (selfie, separate from `photos` foto-tambahan); `wim_visit_plan.seq_no` (drag-drop order) | Separate selfie from merchandise photos; numbered kunjungan list | Columns applied live (110) |
| Middleware | `GET/POST /api/admin/plan/day` (numbered list + save with seq, store picker by region/search); `GET /api/admin/rencana/view` (per-sales summary + per-store detail: order count, norasan/notes, checkin photo, photos); checkin POST stores `checkin_photo` | Backend for edit + view | Verified endpoints (plan save round-trip with seq; rencana/view returns 4 sales w/ status+counts) |
| Admin nav (all pages) | "Rencana Hari" → hover **dropdown** with `👁️ Lihat List Kunjungan` (today-plan.html) + `✏️ Edit List Kunjungan` (plan-edit.html) | Two menus per user request | Deployed across 12 admin pages, JS valid |
| `plan-edit.html` (new) | 3-step edit: (1) sales list (region/depo/search, **no dates**), (2) **Week 1–4 × 6 days** calendar per sales, (3) drag-drop day editor — left column available stores (search + **area filter**), right column **numbered** kunjungan list (▲▼ reorder + ✕), save persists seq | Edit workflow | Browser-tested: sales → calendar (4 weeks/6 days) → drag-add 2 stores numbered 1,2 → save toast ✅ |
| `today-plan.html` (view) | **Calendar on top** → **sales table** (Sales/Region/Status Berjalan·Belum Masuk·Sudah Selesai/Nominal dalam Rute/Nominal Luar Rute/Detail) → **detail modal**: per-store (name, time visited, order/no-order w/ **alasan in red**, nota) + buttons **Foto Checkin** (selfie), **Foto Tambahan**, **Cek Pesanan** (order table; greyed if none), **Stock Toko** | View + drill-down | Browser-tested: calendar 30d, 4 sales, detail modal 8 stores, all 4 buttons open |
| Sales `visit-card.html` + `api.js` | Check-in now opens a **selfie (front-facing) camera**, auto-closes after capture, sent as `checkin_photo`; merchandise photos moved to a separate **🖼️ Foto Tambahan** button (environment camera) | Fix the selfie-vs-tambahan bug the user reported | Deployed to CT112 |
| Admin-server | Proxies for plan/day, rencana/view, stores/orders, stock (with place_uuid) | Reach via admin server | Verified Cek Pesanan + Stock modals open |
| Docs | `RENCANA-KUNJUNGAN-PLAN.md` (new), `DATABASE-MAPPING.md` (checkin_photo, seq_no), CHANGELOG | |

*Photo storage note: `wim_visits.checkin_photo` holds the selfie; `wim_visits.photos` (+ `wim_store_photos.photo_type`) keep the merchandise "foto tambahan".*

---

## 2026-09-10 — Promo QA fixes: duplicate data-corruption (cartesian dedup), requirement qty display, sales-catalog promo advertisement

**Changes: fix 3 bugs surfaced by the promo QA round.**
| Area | Change | Reason | Verified |
|---|---|---|---|
| Middleware `do_PROMOS_ADMIN_GET` | Dedup conditions/rewards (cartesian `LEFT JOIN conditions × rewards` produced doubled rows; duplicating a promo copied 2N rows); fixed `= ANY(%s)::int[]` cast error in the multi-area attach | Duplicate was corrupting condition/reward counts | Promo GET now returns clean counts (promo 22: 2 conds / 1 reward); no array-cast error; regions attach |
| Admin `promos.html` | Requirement list shows qty (`BUY 20× SQA-550-K24` for `required_sku`) | GUI collects qty but it was invisible ⇒ looked dropped | List renders qty |
| Sales `order.html` | Promo badge now matches `required_sku` + `purchase_sku` conditions AND bonus-reward SKUs (was only `jenis==='diskon'` + `purchase_sku`) | Reworked promos (bundling + required_sku) were never advertised in the catalog | `promo-badge` count = 2 on the catalog (SQA + LVT) |

---

## 2026-09-10 — Route map: sales travel route, current position, store visit/order coloring, attendance + depots

**Changes: the admin Route Map now reconstructs each salesperson's travel route (orange polyline through their logged app-opened positions), shows their current/last-known position, color-codes stores by visit+order status, marks attendance check-in/out, and shows depots.**
| Area | Change | Reason | Verified |
|---|---|---|---|
| Middleware | New `GET /api/admin/route-map?date=` returning stores (with visited/ordered/color), per-user travel lines (ordered position fixes), current positions, attendance check-in/out locations, depots | Power the travel visualization | API returns 15 stores (5 green/1 red/9 blue), 2 travel lines, 2 current pos, 1 attendance, 4 depots |
| `route-map.html` | Orange polyline per sales through logged positions; green current-position dot; store markers colored 🟢visited&ordered / 🔴visited-no-order / 🔵unvisited; amber 🕐 check-in/out icons; grey 🏭 depot icons; updated legend + sidebar badges | A rough sales tracker without constant GPS | Browser: map renders 22 markers (15 stores+2 current+1 attendance+4 depots), polyline layer present, no errors |
| Admin-server | Proxy `/api/admin/route-map` | Reach via admin server | |
| Docs | `ROUTE-MAP-TRACKING.md` (new), CHANGELOG | |

---

## 2026-09-10 — Admin: sales locations on route map (app-opened dots) + current positions on dashboard

**Changes: the admin home page shows each sales member's current location (map dots + last-online table), and the route map plots red dots where sales opened the app — both from `wim_sales_positions`.**
| Area | Change | Reason | Verified |
|---|---|---|---|
| Middleware | `GET /api/positions/all` (admin-only): latest position per sales user + recent trend of app-opened fixes | Admin approximation of sales whereabouts from the persisted position table | Returns latest per user (Andi, Budi) + trend |
| Admin-server | Proxy `GET /api/admin/positions/all` | Reach via the admin server | | 
| `dashboard.html` | New "📍 Lokasi Sales" card with a Leaflet map (one dot per sales at current position, initial-letter marker + popup) and a table of last-known position (name, coords, "just now"/N m ago) | Admin sees current sales position on the home page | Browser-verified: map renders 15 tiles, 2 markers, table lists Andi+Budi with last-online |
| `route-map.html` | Plots red dots where each sales opened the app (`wim_sales_positions` trend), alongside the route-plan markers; legend/count retained | Route map shows where sales have been | Browser-verified: 3 position dots + 8 plan markers render, no errors (fixed missing `esc`) |
| Docs | `GEOLOCATION-PLAN.md` updated, `DATABASE-MAPPING.md` (already has `wim_sales_positions`), CHANGELOG | |

---

## 2026-09-10 — Geolocation: sales position tracking, 10m kunjungan glow, check-in geofence

**Changes: the sales webapp captures+persists the rep's GPS position on every page load/refresh, the Kunjungan menu highlights stores within ~10m (green glow), and check-in validates the rep is within ~10m of the store.**
| Area | Change | Reason | Verified |
|---|---|---|---|
| DB | New `wim_sales_positions(user_id, user_name, latitude, longitude, accuracy_m, source, recorded_at)` + indexes; grants to `wim_app` | A time-series table of every reported sales position, joinable to visits/orders by user+time | Migration `04-sales-positions.sql` applied live (110) |
| Middleware | `POST /api/positions` persists a fix; `GET /api/positions/latest` returns caller's last; check-in geofence (Haversine ≤10m) blocks far check-ins; `haversine_m` helper | Position logging + store check-in validation | POST 200 + row persisted; check-in from ~157km blocked, at-store succeeds |
| `js/app.js` | New `WIM_Geo` util: capture/report/distanceM/inRange (10m) | Shared geolocation for sales pages | Served on CT112 |
| `visit-card.html` | On load/refresh capture+report position then re-render so in-range stores glow green (`.in-range`, "🟢 Dalam Jangkauan ≤10m" badge); check-in now sends rep's ACTUAL GPS position | Geofence + kunjungan visual cue | Deployed; JS syntax OK |
| `dashboard.html` | Reports position on landing (page change/refresh) | Position updated at every page change | Deployed |
| `css/app.css` | `.in-range` green glow style | Visual cue | |
| Docs | `GEOLOCATION-PLAN.md` (new), `DATABASE-MAPPING.md`, CHANGELOG | |

*Note: `navigator.geolocation.getCurrentPosition` is a mobile-webview API; on desktop browsers without it no fix is captured → no glow and no geofence block (graceful).*

---

## 2026-09-10 — Store page: server-side channel/status filters fix (pagination consistency)

**Changes: address the QA finding that page-scoped client-side filters produced misleading totals and missed matches across pages — channel/status filters are now server-side.**
| Area | Change | Reason | Verified |
|---|---|---|---|
| Middleware `do_ALL_STORES` | Added `chan` + `status` query params; COUNT and SELECT share one WHERE so totals + paging reflect the filter | QA: client-side filter + server paging disagreed (Horeka showed 1 row yet "29 total · page 1/2") | `chan=Horeka` → total 3, all 3 Horeka; no-filter → total 24 |
| Admin-server `do_STORES` | Forwards `chan`/`status` to middleware | Proxy parity | Verified via admin API |
| `stores.html` | `loadStores()` sends `chan`/`status`; drops the client-side post-filter; category datalist deduped; delete button labeled "✕ Hapus"; Status field hidden in add mode (new stores are active) | Consistent counts; cosmetic + create-clarity fixes | Node JS check ok; deployed |

---

## 2026-09-10 — Area-based pricing & multi-area promos

**Changes: product prices are now per-area (region), shops belong to a region, the sales app shows the shop's area price, admin sets prices graphically with an area checkbox + preview-then-confirm, and promos apply to multiple areas.**
| Area | Change | Reason | Verified |
|---|---|---|---|
| DB | `wim_stores.region_id` (INT FK→regions); new `wim_product_prices(product_uuid, region_id, price, effective_from)`; new `wim_promo_regions(promo_id, region_id)`; store regions backfilled from visited rep's depot region; legacy promo single region backfilled into `wim_promo_regions` | Enables per-area pricing and multi-area promos | Migration `03-area-pricing.sql` applied live (110) |
| Middleware `do_PRODUCTS` | `GET /api/products?store=<uuid>` resolves the shop's region and returns that area's price (`price`, plus `basePrice`/`isAreaPrice`/`regionId`); falls back to rep's region; base price when no area override | Sales rep sees the price for the shop's area | R1 store→13000, R2 store→180000 (isolated, no leak) |
| Middleware pricing APIs | `GET /api/admin/products/prices` (products + per-region map + regions); `POST /api/admin/products/prices` bulk set `{entries:[{sku,price,effective_from}], regionIds, allAreas}` UPSERT | Admin sets prices for many areas at once; returns changed/skipped summary | GET/POST round-trip + grants to `wim_app` |
| Admin `products.html` | Added `💰 Harga Area` nav link → new `pricing.html` | |
| Admin `pricing.html` (new) | Full area price editor: **area checkbox menu** (+ ⚡ Semua Area), set-date field, editable per-product price column, **👁️ Preview Perubahan** showing `SKU \| Nama \| Area \| Harga Lama \| Tanggal Set Lama \| Harga Baru`, and **✅ Confirme & Simpan** posts only after confirming | Graphical, no editing every row; preview-then-confirm | Served 200; API works |
| Admin `promos.html` + MB | Promo area single-select → **multi-area checkbox** + ⚡ Semua Area; `regionIds`/`allAreas` in POST/PATCH write `wim_promo_regions`; sales `do_PROMOS`/`do_ORDER_CALC` + admin GET resolve promos by their region set (empty set = all areas) | Manager can assign a promo to many areas quickly | DB backfilled; queries rewritten |
| Sales `order.html` | `loadProducts()` sends `?store=<storeUuid>` so the catalog shows the shop's area price | Shop-area pricing on the sales app | Cookie default region 1 → 13000 |
| Docs | `AREA-PRICING-PLAN.md` (new), `DATABASE-MAPPING.md`, CHANGELOG | |

*Note: DB runs `SQL_ASCII`; area price fields are numeric/date only (no non-ASCII). Grants for `wim_app` on the new tables applied live.*

---

## 2026-09-10 — Routes page: date query to view today's or a past day's route

**Changes: route-map.html now has a date picker on top to view the route plan for any day (today, yesterday, or a chosen date).**
| Area | Change | Reason | Verified |
|---|---|---|---|
| Admin `route-map.html` | Added a `📅 Kapan` date `<input type="date">` (defaults to today) + quick buttons `Hari Ini` / `Kelmarin` / `2 Hari Lalu` in the route sidebar filter bar. Selecting a date reloads the route map + store list for that date (`GET /api/admin/today-plan?date=YYYY-MM-DD`). Rep filter resets + repopulates per date. Page title shows the selected date in Indonesian | So admins can see today's route plan or review a past day's (e.g. yesterday) route | Browser-verified live: default shows today (Kamis, 10 Sept 2026, 8 rencana); switching to 2026-09-09 shows Rabu, 9 Sept (10 rencana) + rep list repopulated; Kelmarin button works |
| Backend | No change needed — middleware `do_VISIT_PLAN_GET` and admin proxy `do_TODAY_PLAN` already accept `?date=` and pass it through | Existing support | Verified via browser that `?date=` is sent and respected |

---

## 2026-09-10 — Improvements: promo edit/duplicate/filter, store pagination/delete, rep store fields, bonus jenis

| # | Change | Reason | Verified |
|---|--------|--------|----------|
| 80 | **Promo edit (conditions/rewards)** — `PATCH /api/admin/promos/:id` now replaces conditions/rewards (DELETE + reinsert) when provided, transactionally with header fields. Admin UI has an **Edit** button that pre-fills the form; Save PATCHes on edit. | QA backlog #1 | ✅ edited promo 4 conditions/rewards via PATCH → engine picked up new values; restored |
| 81 | **Promo duplicate + search/filter/sort** — admin page adds **⧉ Dup** (create " (copy)"), search box (nama/ref), jenis + status filters, sort by nama/status. | QA backlog #2 | ✅ buttons/filters present; duplicate POST works |
| 82 | **Promo JSON validation + templates** — savePvalidate blocks non-array JSON with the error message; quick-template links (Bundling 10+2, Strata 5%, Diskon Rp5000) fill the form. | QA backlog #3 | ✅ invalid JSON blocked with message; templates populate |
| 83 | **Store pagination + delete** — `/api/stores/all` supports `page`/`per_page` + returns `total`; `DELETE /api/stores/:uuid` soft-deletes (deleted_at/status=closed). Admin stores page: pagination footer + **✕ Hapus** button; channel/status filters; per-page selector. | QA backlog #4 | ✅ pagination (total 24, returns 5); delete soft-deletes; clean after |
| 84 | **Store category dropdown** — admin store form uses a datalist populated from existing categories + standard set (still allows typing new). | QA backlog #5 | ✅ datalist populated |
| 85 | **Rep `/api/stores` includes owner/channel/category** — `do_MY_STORES` SELECT + mapping now returns these for the rep dashboard/visit card. | QA backlog #6 | ✅ /api/stores returns owner_name/channel/category |
| 86 | **Promo `bonus` jenis handled by engine** — `do_ORDER_CALC` adds a `bonus` branch: grants free items when a purchase_sku condition is met (any threshold), reward `free_sku`/`legacy_free_qty`/`bonus_qty`. | QA backlog #7 | ✅ test bonus promo granted +1 free LVT exactly once |
| 87 | **Docs** — `IMPROVEMENT-PLAN.md` (plan + status), `QA-FINDINGS.md` backlog→resolved. | record | ✅ |

> **Verdict:** all 7 QA-backlog items implemented + live-verified. Promo full lifecycle (create/duplicate/edit/toggle/delete+search/filter/sort), store CRUD+pagination+delete, rep store fields, and bonus promo jenis all work. Ready for re-QA traversal.

---

## 2026-09-10 — QA fixes: promo engine vocabulary + double-fire + store phone (from role-traversal audit)

| # | Change | Reason | Verified |
|---|--------|--------|----------|
| 75 | **Promo engine now applies legacy/seed promos** — `do_ORDER_CALC` normalizes legacy condition/reward vocabulary (`min_qty`/`free_qty`/`percent_discount`/`flat_discount`/`min_amount`) into engine handling; legacy bundling grants bonus on most-purchased SKU. | QA: seeded promos never applied (vocab mismatch) | ✅ qty=12: bundling +2, strata 5%=6000, diskon flat Rp5000, grand 109000 |
| 76 | **Promo engine no longer double-fires** — conditions/rewards deduped per promo (keyed set) to remove cartesian-join multiplication. | QA: 10+2 granted 4 free; promosApplied twice | ✅ each promo + reward fires exactly once |
| 77 | **Store phone surfaced** — `GET /api/stores/all` response mapping now includes `phone` (was selected in SQL but dropped). | QA: phone lost on store write/read | ✅ /api/stores/all returns phone; admin stores shows it |
| 78 | **Promo admin UI render fixes** — removed doubled jenis; rewardText/parseRule handle both legacy and engine condition/reward types. | QA: jenis looked doubled, legacy rewards "—" | ✅ row shows jenis once + readable rewards |
| 79 | **Docs: `QA-FINDINGS.md`** — full audit writeup (findings, root causes, fixes, remaining enhancements). | record QA + improvements | ✅ |

> **Verdict after this round:** promo engine + store management correct and re-verified live;
> remaining items are enhancement backlog (promo edit/duplicate/search, store pagination/delete,
> guided promo JSON builder, category dropdown).

---

## 2026-09-10 — Admin: Promo management UI + Stores (customer) management + CRUD backend + bug fixes

| # | Change | Reason | Verified |
|---|--------|--------|----------|
| 69 | **Promo admin backend (middleware)** — `GET/POST/DELETE /api/admin/promos` + `PATCH /api/admin/promos/:id`. Create with header (nama/jenis/status/priority/stackable/periode/min/max) + conditions[] + rewards[]. Toggle status + delete (soft). Gated to super_admin/admin. | Self-service promo setup (matches "promo UI" gap) | ✅ CRUD POST/PATCH/DELETE/GET tested live via service key |
| 70 | **Promo admin page (`admin/promos.html`)** — list promos (ref/nama/jenis/periode/condition/reward/status), create form (JSON conditions+rewards), activate/deactivate toggle, delete. Design-matched to admin panel. | Promo self-service UI | ✅ browser: 4 promos list; create returns new id; toggle/delete work |
| 71 | **Stores (customer) admin backend** — `PATCH /api/stores/:uuid` (middleware, edit customer fields) + admin proxy GET/POST/PATCH `/api/admin/stores`. `/api/stores/all` now returns owner_name/channel/category/status/province. | Store management (highest gap) | ✅ browser: list 24 stores; create → new uuid; edit → persists |
| 72 | **Stores admin page (`admin/stores.html`)** — list (name/owner/phone/channel/category/city/status), search, create + edit forms. | Customer management UI | ✅ browser: list + create + edit verified |
| 73 | **Fixed latent UUID bug** — `do_ORDER_POST` and `do_STORE_POST` generated `secrets.token_hex(16)` (non-UUID) for `uuid` columns typed `UUID`. Changed to `str(uuid.uuid4())`. This was **breaking NOO store creation and order creation** (invalid-input errors). | found while testing store admin | ✅ store POST now returns valid UUID; order POST fixed |
| 74 | **Nav updated** on all admin pages to include Promo + Toko links | Navigation | ✅ |

> **Verified live:** promo CRUD (list/create/toggle/delete) and store CRUD (list/create/edit)
> work end-to-end through the admin panel with real data.

---

## 2026-09-10 — Sales app: payment method, out-of-route transaction type, visit Belum/Sudah tabs, promo/payment on order

| # | Change | Reason | Verified |
|---|--------|--------|----------|
| 64 | **Payment method (Cash/Kredit)** — order.html cart now has a **💳 Opsi Pembayaran** selector (Tunai/Kredit, default Cash). `src param` passed from visit-card; order POST writes `payment_method` (already in schema) + validates `in (cash,credit,cod)`. | Meeting-note: "opsi pembayaran (cash or credit)" was missing | ✅ order GET + public return paymentMethod; admin orders shows Bayar column (browser-verified) |
| 65 | **Out-of-route transaction type** — when store is `luar_rute`, order page shows a **Jenis Transaksi** dropdown (WA/Telepon/Admin Bantu/Lainnya); required before checkout; written to `off_route_reason` + `source='luar_rute'`. visit-card passes `&src=`. | Meeting-note: out-of-route orders need transaction type → report "status" | ✅ browser: field hidden for route, shown for luar-rute |
| 66 | **Visit card Belum/Sudah Dikunjungi tabs** — replaced single filter with two top tabs: **🕐 Belum Dikunjungi** (pending/active) and **✅ Sudah Dikunjungi** (visited/completed), plus a secondary in-route/luar-rute filter. | KlikOrder/GooVi visit-card parity | ✅ browser: Belum=5, Sudah=1 (completed) for test rep |
| 67 | **Promo + payment on order outputs** — `do_ORDER_GET` returns paymentMethod/offRouteType/source/bonusQty/promosApplied; `do_ORDER_PUBLIC` returns paymentMethod/offRouteType/source; invoice.html shows **Pembayaran**; admin orders page + CSV added **Bayar** + **Promo/Bonus** columns. | "promo tidak tampil di report" complaint + payment visibility | ✅ admin orders page shows COD + promo/bonus (browser) |
| 68 | **Fixed order INSERT column bug** — order POST previously wrote `sales_channel` into the `source` column (INSERT column/value mismatch). Now correctly maps source, sales_channel, payment_method, off_route_reason. | latent bug from initial order implementation | ✅ order rows now have proper source/payment |

> **Verified live:** sales rep `andi@wim.sales` — visit-card Belum/Sudah tabs work; payment selector renders + toggles; order GET/API return new fields; admin orders page shows new columns.

---

## 2026-09-10 — Report period/region/depo filters + sales dropdown; region data model

### Data model — regions
| # | Change | Reason | Verified |
|---|--------|--------|----------|
| 51 | **New `wim_regions` table** (id, uuid, name UNIQUE, kode_area, description, is_active) + **`wim_depots.region_id`** FK. Applied live via `deploy/db/init/02-regions.sql`. | Sales/data need an "area/major region" grouping (JABODETABEK, Jawa Tengah, Jawa Timur) | ✅ 5 regions seeded, 4 depots linked to JABODETABEK |
| 52 | **`wim_app` grants** added for `wim_regions`/`wim_depots` (GRANT SELECT etc. on all public tables/sequences) | New tables need app-role access | ✅ /api/filter-options works |

### Middleware (serve.py)
| # | Change | Reason | Verified |
|---|--------|--------|----------|
| 53 | **New `GET /api/filter-options`** — returns sales users (id, name, depot, region), depots (id, name, region), regions (id, name). For admin dropdowns. | Sales/depot/region dropdown sources | ✅ returns 8 users / 4 depots / 5 regions |
| 54 | **`GET /api/absensi`** — added period filters (`date_from`/`date_to`) + `user_id` + `depot_id` + `region_id`. Depot/region filter via the **user's assigned depot** (`wim_user_meta.depot_id → wim_depots → region`). Records include `userDepotName`, `regionName`. | Period + depo/region on attendance | ✅ period+region query returns 2 records |
| 55 | **`GET /api/visits`** — added same period + user + depot + region filters; returns userDepotName/regionName | ✅ period+region returns 9 visits |
| 56 | **`GET /api/visit_plan`** (today-plan) — added period + user + depot + region filters; plans include visitDate/userDepotName/regionName | ✅ |
| 57 | **`GET /api/orders`** — added period (date_from/date_to) + user + depot + region filters; orders include userDepotName/regionName; limit 200 | ✅ |

### Admin panel (admin-server.py)
| # | Change | Reason | Verified |
|---|--------|--------|----------|
| 58 | **`/api/admin/filter-options`** proxy → middleware | Dropdown data | ✅ |
| 59 | `do_VISITS/do_ORDERS/do_ATTENDANCE/do_TODAY_PLAN` now **forward period+user+depot+region** filters to middleware; scoped to depo_admin's depot by default; output includes depot/region | Full filter support | ✅ browser-verified |

### Admin pages (UI)
| # | Page | Change | Verified |
|---|------|--------|----------|
| 60 | **attendance.html** | Rebuilt: **period (Dari/Sampai)**, **Sales dropdown** (from DB, "Semua Sales"), **Region dropdown**, **Depo dropdown** (cascades by region), geo summary + CSV export (+ region/depo columns) | ✅ browser: 9 sales, 6 regions, 5 depots; region filter works |
| 61 | **visits.html** | Same filter bar + region column + CSV | ✅ 9 rows rendered |
| 62 | **orders.html** | Same filter bar + region column + CSV | ✅ 5 rows rendered |
| 63 | **today-plan.html** | Same filter bar + **period** (was today-only) + status/source + region + CSV | ✅ 17 rows rendered |

> **Verified live (browser, depo_admin `admin@wim.sales`/`sandi123`):** all 4 pages show Sales dropdown (9 = 8+All), Region dropdown (6 = 5+All), Depo dropdown cascaded by region; filtering by region JABODETABEK returns data, Jawa Timur returns 0 (correct); rows show their region/depo.

---

## 2026-09-10 — Order confirmation QR → online invoice (downloadable PDF)

| # | Change | Reason | Verified |
|---|--------|--------|----------|
| 47 | **`GET /api/orders/public?uuid=`** (middleware) — public, NO-auth order-confirmation endpoint. Returns order header + items + store/rep, with `paymentStatus:"UNPAID"` and `isConfirmation:true`. Normalises legacy (`unit_price`) vs new (`unitPrice`) item shapes. Validates uuid (400) and 404s missing orders. | Buyer-facing QR needs a public way to fetch order data without logging in | ✅ via proxy returns orderId/store/grandTotal/UNPAID; bad uuid→400, missing→404 |
| 48 | **`frontend/invoice.html`** — public "Kupon Pesanan" (order confirmation) page. Fetches `/api/orders/public`, renders store/rep/order-no/date/item lines (bonus lines marked Gratiis)/subtotal/discount/grand total, with a **CONFIRMED · UNPAID** status badge and a note that this is NOT a tax invoice. Sticky **"Download PDF / Print"** button uses the browser print-to-PDF. `@media print` stylesheet for clean export. | Buyers scan the QR → open browser → view + download an order confirmation (unpaid); future use as penagihan/invoice | ✅ renders real order data verified in browser |
| 49 | **Real QR code** on order success screen (`order.html`) — replaced the placeholder (raw UUID text) with a scannable QR encoding `{origin}/invoice.html?uuid=<orderUuid>`. Uses vendored `js/qrcode.min.js` (davidshimjs). Buyer scans → opens the invoice page → downloads PDF. | The QR previously showed raw text, not a scannable code; now it opens the order document | ✅ QR lib generates scannable code (browser-verified) |
| 50 | Added `frontend/js/qrcode.min.js` (vendored qrcodejs lib, 19.9KB) | QR rendering | ✅ served 200 |

> **Note:** QR encodes the current origin (e.g. `http://192.168.6.112` on LAN). Once a public
> domain (sales.sqa.web.id) is set up, the QR automatically uses it since it's built from
> `location.origin` at order time — so the buyer's phone can open the invoice from anywhere.

---

## 2026-09-10 — Report filters + CSV export; product edit

### Middleware (serve.py) — product edit support
| # | Change | Reason | Verified |
|---|--------|--------|----------|
| 38 | **`GET /api/products`** now returns `unit`, `qtyPerUnit`, `image` (read from `meta` JSONB) | Products page needs full fields + image; image stored without schema change | ✅ GET returns all fields incl. image |
| 39 | **New `PATCH /api/products/:uuid`** — update product details/pricing/image (admin only). Image stored in `meta.image` via `COALESCE(meta,'{}'::jsonb) || %s::jsonb`. Validates price/weight/qty as numeric. 404 if uuid not found. | Products page edit feature | ✅ PATCH price+name+image → 200, persisted via middleware |

### Admin server (admin-server.py) — product edit + fixes
| # | Change | Reason | Verified |
|---|--------|--------|----------|
| 40 | **Fixed `do_PRODUCTS` mapping** — middleware returns `uuid` (admin was reading nonexistent `id` → null). Added `description/weight/weightUnit/qtyPerUnit/image`. | Product edit needs the real id | ✅ products return uuid + all fields |
| 41 | **New `PATCH /api/admin/products/:uuid`** proxy → middleware; `do_PATCH` dispatcher + CORS PATCH allowed | Admin edit UI | ✅ PATCH through admin panel → 200 |

### Admin pages — filters + CSV + edit
| # | Page | Change | Verified |
|---|------|--------|----------|
| 42 | `today-plan.html` | Added **Sales** name + **Akun** (toko) text filters on plan rows + **⬇ CSV** export (BOM-prefixed UTF-8). Original status/source filters kept. | ✅ serves 200, filters render, CSV downloads |
| 43 | `visits.html` | Added **Sales** + **Akun** filters + CSV export | ✅ serves 200 |
| 44 | `orders.html` | Added **Sales** + **Akun** filters + CSV export (keeps total row) | ✅ serves 200 |
| 45 | `attendance.html` | Added **Sales** filter + CSV export (keeps geofence summary) | ✅ serves 200 |
| 46 | `products.html` | Added **Edit** button + inline form for each product: upload product image (preview, max ~1MB), edit name/brand/category/unit/qty-per-unit/price/weight/description → `PATCH /api/admin/products/:uuid`. Also fixed missing depots/today-plan nav links. | ✅ PATCH round-trips price/name/image (verified live, then restored) |

> **Verified live:** depo_admin login `admin@wim.sales`/`sandi123`; PATCH `/api/admin/products/:uuid` updates price+name+image persisted and read back; all pages serve HTTP 200.

---

## 2026-09-10 — Task C Completion: Depo + Today-Plan admin pages, depots bugfix

### Admin panel (LXC 113) — Task C remaining work finished
| # | Change | Reason | Verified |
|---|--------|--------|----------|
| 34 | **Fixed `/api/admin/depots` mapping bug** — `do_DEPOTS` read `dep.get('latitude')`/`('longitude')` but the middleware `/api/depots` returns `lat`/`lng`/`radiusM`, so coords were null. Now maps the correct keys and passes `radiusM` through. | Was a stopped-agent mistake; a depots page would have shown null coords | ✅ returns 4 depots with correct lat/lng/radiusM |
| 35 | **`depots.html` admin page added** — lists all depots (name, address, lat/lng, radius) from `/api/admin/depots`, design-matched to the panel (topnav, cards, badges). | Task C deliverable that was in the "remaining" queue | ✅ deploys, returns 200, data verified live |
| 36 | **`today-plan.html` admin page added** — today's full visit-plan detail (rep, store, address, source, status) with status/source filters + summary chips (total/pending/visited/in-route/luar-rute) from `/api/admin/today-plan`. | Task C deliverable — today-plan endpoint already returned detail rows; only the page was missing | ✅ deploys, returns 200, 13 plans verified live |
| 37 | **Topnav updated** on all 8 admin pages (dashboard/team/visits/orders/attendance/users/products/route-map) to link the 2 new pages. | Navigation | ✅ |

### Verified live (depo_admin `admin@wim.sales` / `sandi123`)
- `POST /api/admin/login` → token + role
- `GET /api/admin/depots` → 4 depots (correct lat/lng)
- `GET /api/admin/today-plan` → 13 plans (rep/store/source/status)

> **Note:** `CURRENT-STATE.md` must be reconciled — it still shows G3 Order Management as "NOT STARTED" and admin password as `wimadmin2026`, both stale. See CURRENT-STATE.md update.

---

## 2026-09-09 — Middleware + Containerized DB Deployment

### Database container (wim-db, LXC 110)
| # | Change | Reason | Verified |
|---|--------|--------|----------|
| 1 | **Dedicated PostgreSQL container** (LXC 110 `wim-db`, 192.168.6.110) on SanQua AI Proxmox — PostgreSQL 17.11, Debian 13 | Move DB to its own container, reduce coupling to the old monolith host | ✅ listening :5432, network auth works |
| 2 | **31-table `wim_sfa` schema applied** from `deploy/db/init/01-schema.sql` | Clean standalone schema (DATABASE-MAPPING.md) | ✅ all 31 tables + indexes created |
| 3 | **UTF-8 encoding** preferred; **app role `wim_app`** created with table-level grants (select/insert/update/delete on all public tables) | Least-privilege DB access for the middleware | ✅ |
| 4 | **Optimal PG tuning**: shared_buffers 384MB, work_mem 8MB, wal_level=replica, autovacuum on, timezone Asia/Jakarta | Fit for 2GB container | ✅ |

### Middleware (wim-mid, LXC 111)
| # | Change | Reason | Verified |
|---|--------|--------|----------|
| 5 | **Middleware container** (LXC 111 `wim-mid`, 192.168.6.111:8000) serving `serve.py` | Reduce direct DB connections, centralize logging, expose APIs for future apps | ✅ 26/26 API tests pass |
| 6 | **Bearer API-key auth** added (`_auth_external_key`) for future external apps | Let future apps read/write DB via API key, not DB creds | ✅ bearer test passes |
| 7 | **Schema drift fixed** in serve.py queries: `radius_m` (not radius_meters), `wim_orders.store_uuid` (not store_id only), `total`/`order_ref` (not grand_total/public_id), removed driver_uuid refs | Align middleware to canonical schema | ✅ 26/26 |
| 8 | **`visitId: 0` bug fixed** — visit INSERT now uses `RETURNING id` (was pymysql `lastrowid`/`LASTVAL()` which fail in psycopg2) | psycopg2 cursor has no lastrowid | ✅ check-in returns real visit id |
| 9 | **`wim_orders` columns added**: `store_uuid`, `verification_status`, `sales_channel` | Consistent UUID store refs + order verification lifecycle | ✅ recorded in 01-schema.sql + DATABASE-MAPPING.md |
| 10 | **`POST /api/products`** endpoint added (was missing) + **sync_queue insert/select fixed** to canonical schema | Missing endpoint + drifted columns | ✅ tested |
| 11 | **API key created** in `wim_api_keys` (`public-external-gateway`) | For future external apps | ✅ |

## 2026-09-09 — Task A/B: Sales webapp + Admin panel redeployed as containers

### Dummy data seeded (wim_sfa)
| # | Change | Verified |
|---|--------|----------|
| 1 | Seeded realistic Jakarta dataset via `/tmp/wim-dummy-seed.py` (run from middleware): 9 users, 4 depots, 21 stores, 41 store contacts (1:many), 9 products, 6 depot-products, 14 depot-stores, 33 visit plans, 4 promos (+cond/rewards), 27 stock checks, user_meta, admin_depot_access | ✅ flows through middleware APIs |

### Sales webapp container (LXC 112 `wim-sales`)
| # | Change | Verified |
|---|--------|----------|
| 2 | **Deployed sales app as its own LXC** (192.168.6.112) — nginx serves static frontend, `/api/*` proxies to middleware wim-mid:8000 | ✅ login via proxy 200, dashboard/stores/products/depots all return dummy data |
| 3 | **3-subagent QA loop** (sales rep, depot admin, super admin) run against live proxy. Found 7 real bugs + 1 RBAC dead-zone (verdicts: depot_admin=NO, super_admin=MAYBE) | ⚠️ issues → all fixed (see below) |

### Middleware bug fixes (from QA loop) — 9/9 verified PASS
| # | Fix | Verified |
|---|-----|----------|
| 4 | `GET /api/stores/all` removed bogus `type='store'` filter (no such column) | ✅ 200 |
| 5 | `GET /api/users/:id` fixed SQL missing-comma + non-existent meta cols (`kode_pos/kelurahan/kecamatan` are store cols), response uses `.get()` | ✅ 200 |
| 6 | `POST /api/orders/status` uses `order_ref AS public_id` (was nonexistent `public_id`) | ✅ 200 |
| 7 | `GET /api/orders/detail` joins store name (was KeyError `store_name`) | ✅ 200 |
| 8 | `wim_user_meta` deduped + added `UNIQUE(user_id)` (1:1) — fixes `ON CONFLICT (user_id)` + users-list dup JOIN | ✅ no dup ids |
| 9 | `POST /api/sync/queue` coerces string `entity_id` → int (DB column INTEGER) | ✅ no 500 |
| 10 | **RBAC**: role checks now use `ADMIN_ROLES = (super_admin, depo_admin, admin)` — `depo_admin` was completely locked out (only `admin`/`super_admin` were accepted) | ✅ depo_admin gets 200 |
| 11 | `/api/visits` + `/api/absensi` support **API-key admin scope** (return all users' data) vs cookie (own data) | ✅ admin panel sees cross-user data |

### Admin panel container (LXC 113 `wim-admin`)
| # | Change | Verified |
|---|--------|----------|
| 12 | **`admin-server.py` migrated** from pymysql/MySQL-fleetbase → **thin middleware client**: authenticates via `/api/auth/login`, queries `/api/*` with privileged Bearer API key (`ADMIN_API_KEY`), no direct DB | ✅ login super_admin, dashboard 9 staff/6 planned, team 9, orders 5, visits 8, depots 4, today-plan 6 |
| 13 | **Deployed admin app as its own LXC** (192.168.6.113:8001), systemd `wim-admin.service` | ✅ all `/api/admin/*` endpoints 200 |
| 14 | DEPLOYMENT.md updated: §3.4 admin migration status, §8.1 real LXC inventory (110–113) | ✅ |

### Admin-panel QA fixes (from 3-persona loop + enrichment)
| # | Fix | Verified |
|---|-----|----------|
| 15 | `/api/dashboard` gets an **API-key aggregate branch** — global KPIs (active staff, today's plan/visits/orders/attendance) instead of one fake apikey-user's zeros; cookie users keep their own scoped dashboard | ✅ api returns staff=9/visits=9/orders=5; rep andi sees own plan=9/visits=5 |
| 16 | `/api/orders` list joins **store name + rep name** (`store_name`, `user_name`), and scopes to `o.user_id` for cookie users vs all for API key | ✅ storeName/userName populate |
| 17 | `/api/visits` response now includes **`user_name` + `user_id`** (was selected but not mapped) | ✅ visits show rep name |
| 18 | **UUID input validation** on `/api/orders/detail` and `/api/stores/:uuid` — non-UUID returns 400 `uuid tidak valid`, not a 500 | ✅ `uuid=TEST` → 400 |
| 19 | admin-server maps visits `user_name`→`userName` and orders `userName`→`driverName` correctly | ✅ admin panel shows Andi Test on visits+orders |

### Remaining (Task C queue — ex-Fleetbase features)
- `GET /api/admin/users` endpoint not yet implemented in admin-server (user management = Task C).
- **Depot-level data scoping** for depo_admin (currently admin panel proxies via service key → sees all depots; needs `wim_user_meta.depot_id` filtering) = Task C.
- **Today-plan detail rows** (currently count-only `{plans:[],total:N}`) = Task C.
- Missing static pages (`admin.html`, `depots.html`, `today-plan.html`) = Task C.

### Sales-rep field-loop fixes (found by final sales-rep QA — 2 blockers)
| # | Fix | Verified |
|---|-----|----------|
| 20 | **Checkout 500 fixed** — `UPDATE wim_visits ... ORDER BY id DESC LIMIT 1` is a **MySQL-ism invalid in PostgreSQL** (`syntax error at or near "ORDER"`). Rewrote to PG subquery `WHERE id = (SELECT id ... ORDER BY id DESC LIMIT 1)`. This was a critical field-day blocker — a rep could check-in but never finish a visit. | ✅ checkout returns 200 `{status:ok, action:checkout}` |
| 21 | **Report orders count** — was always 0 (`driver_uuid` on wim_orders + None var). Replaced with correct `user_id` count. | ✅ report returns orders=3 |

> Note: `GET /api/visits` properly enforces the 180s minimum-visit-duration guard on checkout (returned 400 with countdown) — this is **correct server-side validation**, not a bug.

## 2026-09-09 — Task C: ex-Fleetbase features ported into admin app
Since Fleetbase is no longer part of this project, its management features (user mgmt, product/price, routes, maps, orders) are now native to the WIM Online admin panel, served from the middleware.

### Admin-server endpoints added (`/api/admin/*` — proxy → middleware)
| # | Endpoint | Feature | Verified |
|---|----------|---------|----------|
| 22 | `GET /api/admin/users` (+ `?role=sales`) | User management (list, role filter) | ✅ |
| 23 | `POST /api/admin/users` | Create user (super_admin only) | ✅ |
| 24 | `GET/POST /api/admin/products` | Product & price management | ✅ |
| 25 | `GET /api/admin/stores` | Store list w/ lat/lng (for maps) | ✅ |
| 26 | `GET /api/admin/stock` | Stock check history | ✅ |
| 27 | `POST /api/admin/orders/status` | Order management (status transitions) | ✅ 400-not-500 on bad order |
| 28 | `GET /api/visit_plan` (middleware) | Cross-rep route plans w/ user+store names (admin scope) / own plan (cookie) | ✅ |
| 29 | **Depot scoping** — `_scoped()` in admin-server: depo_admin resolves depot_id (by email → /api/users) and filters user/team queries by it; super_admin sees all | ✅ depo_admin sees 7 users (depot {None,1}), Budi(depot3)+depot4 Carla excluded |

### Admin pages added (design-matched to dashboard.html, subagent-built)
| # | Page | Wired to | Verified |
|---|------|----------|----------|
| 30 | `users.html` | GET/POST `/api/admin/users` | ✅ serves 200 |
| 31 | `products.html` | GET/POST `/api/admin/products` | ✅ serves 200 |
| 32 | `route-map.html` | GET `/api/admin/today-plan` + `/api/admin/stores`, Leaflet+OSM map, color-coded by status | ✅ serves 200 |
| 33 | Topnav updated across dashboard/team/visits/orders/attendance to link the 3 new pages | | ✅ |

> **Task A/B/C QA gate status:** Tasks A + B passed unanimous 3-persona approval after fixing 14 QA-caught bugs. Task C features implemented + deploy-verified; subagent QA loop runs next.

---

## 2026-09-08 — QA Loop Round 2 (UI/UX Expert Reviews Applied)

### Backend (`serve.py` / `server.py`)

| # | Change | Reason | Verified |
|---|--------|--------|----------|
| 1 | **Server-side minimum visit duration (180s)** — checkout rejected if `checkout_at - checkin_at < 180s` with message "Kunjungan minimal 3 menit. Tunggu X detik lagi" | Non-negotiable #3: never trust frontend. Frontend timer was bypassable via DevTools/refresh | ✅ Timer test |
| 2 | **`MIN_VISIT_SECONDS` env var** — configurable minimum (default 180) | Testability; env override for QA | ✅ |
| 3 | **`POST /api/stock`** — persist per-store stock checks to `wim_stock_check` table (user_id, place_uuid, sku, qty, checked_at) | Stock check was a non-persisted alert stub — reps skipped it, feeding the 51% WA-bypass problem | ✅ 2 tests |
| 4 | **`GET /api/stock?place_uuid=X`** — retrieve recent stock checks for a store | Frontend needs to show saved stock on revisit | ✅ |
| 5 | **`GET /api/stores/orders?place_uuid=X`** — last 3 orders for a store (via Fleetbase `orders.meta.place_uuid`/`store_uuid` match on driver) | Reps need order history context during a visit for an informed sales conversation | ✅ |
| 6 | New DB table `wim_stock_check` created | Stock persistence | ✅ |

### Frontend — `index.html`

| # | Change | Reason |
|---|--------|--------|
| 7 | **Role-based redirect** — admin → `admin.html`, sales → `dashboard.html` | IA review P0: admins were landing on sales dashboard with no admin path |

### Frontend — `visit-card.html`

| # | Change | Reason |
|---|--------|--------|
| 8 | **Timer starts at check-in, not modal open** | Mobile UX review P0: timer counting down before check-in wasted minimum-visit time |
| 9 | **Timer color progression** — green → yellow (#e67e22) at ≤60s → red (#dc3545) at ≤30s | Accessibility review P1: glanceable urgency |
| 10 | **Vibration on timer completion** (`navigator.vibrate(200)`) | Accessibility review P1: completion signal in noisy streets |
| 11 | **Loading state on check-in button** — "⏳ Memproses..." + disabled | Mobile UX review P0: prevent double-tap → 409 |
| 12 | **Confirm dialog on "Selesaikan Kunjungan"** | Mobile UX review P0: prevent accidental fat-finger checkout |
| 13 | **Toast notification system** (`showToast(type, title, msg)`) — replaces blocking `alert()` for errors/success/warnings | Accessibility review P0: `alert()` blocks JS thread, crashes on aggressive Android battery saver |
| 14 | **Stock check UI in store modal** — 5 quick SKU quantity inputs (PET 550, PET 220, CUP 120, GALON 19L, LEVONTE CUP), saved via `POST /api/stock` on checkout | Stock persistence + 1-tap-per-SKU UX |
| 15 | **Store order history in modal** — last 3 orders shown, via `GET /api/stores/orders` | Sales conversation context |
| 16 | **"Buat Pesanan" → "coming soon" toast** instead of redirecting to NOO form | IA review P0: was sending reps to wrong page (NOO is for new outlets, not orders) |
| 17 | **Debounce (300ms) on "Tambah Luar Rute" search** | Mobile UX review P0: every keystroke was firing an API call |

### Frontend — `css/app.css`

| # | Change | Reason |
|---|--------|--------|
| 18 | `@keyframes slideIn` — toast slide-up animation | Toast system |
| 19 | `@keyframes timerDone` — pulse animation on timer completion | Timer feedback |

### Database

| # | Change | Reason |
|---|--------|--------|
| 20 | `CREATE TABLE wim_stock_check` (id, user_id, place_uuid, sku, qty, checked_at) | Stock persistence |

---

## 2026-09-08 — NOO Channel→Kategori Cascade

| # | Change | Reason |
|---|--------|--------|
| 21 | **Channel→Kategori mapping** — GT, MT, Horeka, Institutional each have their own kategori options. GT shows Retail Kecil/Besar/Grosir/Agen/Semi Grosir/Kios; MT shows Minimarket/Convenience Store/Supermarket/Hypermarket/Department Store; Horeka shows Hotel/Restoran/Kafe/Katering/Tempat Hiburan; Institutional shows Kantor/Sekolah/Rumah Sakit/Pabrik/Instansi Pemerintah/Universitas. Default channel (GT) populates on page load. | User's request: "when they choose GT it should show GT specific options" |
| 22 | Product categories seeded in `entities.meta.category` (sanqua, levonte, batavia, aqua) | Strata promo needs category matching |

---

## 2026-09-08 — KlikOrder Shopping Cart (V1)

| # | Change | Reason |
|---|--------|--------|

## 2026-09-08 — QA Loop Round 1 (10 bugs fixed)

| # | Change | Severity |
|---|--------|----------|
| 21 | Deadlock fix — removed nested `SESSION_LOCK` acquisition in `get_session()` (non-reentrant `threading.Lock()`) | Critical — all session requests hung |
| 22 | MySQL connection pool (Queue maxsize=20) with ping-on-reuse | High — connection exhaustion |
| 23 | Single connection reuse in `get_session()` (no second `conn2`) | High |
| 24 | Single-write HTTP/1.0 responses with `Content-Length` in `_send_response_raw` | High — HTTP/1.1 hang |
| 25 | Collation fix — `COLLATE utf8mb4_unicode_ci` on `places` JOIN | Medium |
| 26 | Input validation — `isinstance(data, dict)` checks, 5MB body cap | High |
| 27 | Double-checkin guard → 409 "Kunjungan sudah check-in" | High |
| 28 | Checkout rowcount check → 400 "Belum ada check-in untuk toko ini" | High |
| 29 | Absensi empty clockIn → null normalization | Medium |
| 30 | Auth required on `/api/log` + `/api/logs` | Medium |
| 31 | Login rate limiting — 5 fails/5min → 429 | High |
| 32 | Session cache cleanup thread (5-min purge) | High |
| 33 | Hardcoded admin email removed from login form | Medium |
| 34 | `/api/absensi` clock_out rowcount check | Low |

---

## Test Status

| Test Suite | Result | Date |
|-----------|--------|------|
| full-qa-test.py (Round 1) | 31/31 pass | 2026-09-08 |
| full-qa-v2-test.py (Round 2) | 29/30 pass (1 expected: open-checkin 409) | 2026-09-08 |
| Rate limit test | 5×401 → 429 | 2026-09-08 |

## Deployment

- **Server:** LXC 106 (192.168.6.223:8080) — `nohup python3 -u /opt/wim-frontend/server.py`
- **Public:** sales.sqa.web.id → NPMplus → LXC 106
- **Local source:** `/Users/rein/projects/wim-fleetbase/frontend/`
- **Deploy method:** scp → jump host → `pct push 106`

## 2026-09-09 — Visit Card Overhaul + Data Audit

| # | Change | Reason |
|---|--------|--------|
| 23 | **visit-card.html complete rewrite** (639→840 lines) — check-in state restores on refresh via `/api/visits/active`, multi-photo modal with per-photo descriptions, stock input modal with SKU/last+order/input stock columns, store cards show grey + ✅ Selesai for completed visits, timer restores from server checkin_at, submitNoOrder fixed, Selesaikan Kunjungan as final trigger | User reported check-in reset on refresh, single photo only, broken stock input, missing selesai state |
| 24 | **serve.py new endpoints** — `GET /api/visits/active` returns open visit for current user; stock endpoint returns `previousOrderQty` per SKU from last order meta | Restore check-in state on page refresh, show last known stock + order qty |
| 25 | **Data audit** — Verified: all product prices from `entities.meta.price` match Buat Pesanan display; 12 visit records saved; 1 stock check exists; 1 attendance record; 6 orders (3 real WIM). Open visit #11 (since yesterday) auto-cleaned | Ensure all data persists to Fleetbase MySQL |
| 26 | **Deployment fix** — Discovered file was extracting as `serve.py` but server runs `server.py`; renamed + restarted | Old server.py wasn't overwritten by tar extraction |
