# WIM Online — Feature Gap Audit: GooVi + KlikOrder Admin vs WIM Online

> **Audit date:** 2026-09-10
> **Method:** Cross-checked the legacy admin feature map (APP-MAPPING.md, KLIKORDER-PLAN-DRAFT.md,
> KLIKORDER-FLOWS-DRAFT.md) against the **actual current WIM Online code** (admin-server.py routes,
> middleware serve.py endpoints, admin/*.html pages) — not the docs.
> **Legend:** ✅ Present & working · 🟠 Present but incomplete · 🔴 Missing

---

## 1. Headline finding

The mapping docs list WIM `/api/admin/*` endpoints as the target for every GooVi/KlikOrder admin
feature. But most of those WIM endpoints **do not exist yet as CRUD**. What exists today is a solid
**read/report/admin-lite** surface, plus sales-side order creation + QR. The **management/configuration
and reporting/export depth** of the legacy panels is largely **not yet built**.

**In short: the core sales-to-order flow is done; the legacy admin panel is ~40% covered.** The user's
instinct ("there are missing features") is correct.

---

## 2. Verified WIM Online admin surface (current)

| Admin endpoint | Implemented? | WIM page |
|---|---|---|
| login / logout / session | ✅ | index.html |
| filter-options (sales/depot/region) | ✅ | (shared) |
| dashboard | ✅ | dashboard.html |
| team | ✅ | team.html |
| visits (period/region/depo) | ✅ | visits.html |
| orders (period/region/depo) | ✅ | orders.html |
| attendance (period/region/depo) | ✅ | attendance.html |
| depots (list) | ✅ | depots.html |
| today-plan (period/region/depo) | ✅ | today-plan.html |
| products (list) | ✅ | products.html |
| products (create) | ✅ | products.html |
| products/:uuid (PATCH edit, image) | ✅ | products.html |
| stores (list) | 🟠 | — (no stores page) |
| stock (list) | 🟠 | — |
| orders/status (PATCH) | ✅ | orders.html (via status btn) |
| users (POST create) | ✅ | users.html |

**Admin PAGES present:** dashboard, team, visits, orders, attendance, users, products, depots,
today-plan, route-map, index. **No** stores page, no promos page, no reports/export pages.

---

## 3. Feature-by-feature gap matrix (legacy admin → WIM)

### 3a. GooVi Super Admin features

| # | Legacy feature (GooVi endpoint) | WIM equivalent | Status | Notes |
|---|---|---|---|---|
| G1 | **Depot CRUD** (`/depos` GET/POST/PUT/DELETE, `import-depo`) | `/api/admin/depots` | 🟠 | WIM: **list only**. No create/edit/delete/import, no **Bulk depo→harga brand** (`depos/brands-bulk`). |
| G2 | **Employee (Karyawan) CRUD** (`/karyawans` + import + sales-types) | — | 🔴 | No karyawan endpoint/page. Only `users`. |
| G3 | **User CRUD + import** (`/users-filtered`, POST/PUT/DELETE/PATCH/import) | `/api/admin/users` GET/POST | 🟠 | List + create only. No edit/delete/import. |
| G4 | **Customer/Store CRUD + import** (`/pelanggans-filtered`, PUT/DELETE/import) | — | 🔴 | No store management in admin. |
| G5 | **Product CRUD/sync** (`/produk`, PUT, sync, brands) | `/api/admin/products` GET/POST/PATCH | 🟠 | Add + edit exist. No `sync`/import/brand mgmt. |
| G6 | **Visit Plan CRUD + import** (`/rencana-kunjungan`, DELETE, import) | `/api/admin/today-plan` (read) | 🔴 | View today's plan only. No CRUD/import of route plans. |
| G7 | **Other master data** vehicles (`/kendaraans` CRUD), suppliers, store-categories | — | 🔴 | None. |
| G8 | **Visit monitoring + export** (`kunjungan-harian` all/export/foto/app-usage/daily-recap) | `/api/admin/visits` | 🟠 | Report exists (visits.html). No photo/usage/daily-recap reports or server export. |
| G9 | **Attendance + export** (`/absensi`) | `/api/admin/attendance` | ✅ | Full + CSV download (client-side). |
| G10 | **Stock-check report + export** (`kunjungan-cek-stok-brand`) | `/api/admin/stock` | 🟠 | List endpoint only; no report page/export. |
| G11 | **Out-of-route order report** | — | 🔴 | Not present. |
| G12 | **Shipped orders report** (`pesanan-detail-terkirim`) | — | 🔴 | Not present. |
| G13 | **Surat tugas / delivery notes** (list + export) | — | 🔴 | Not present. |
| G14 | **Analisa order vs stock** (`report/analisa-order-vs-stok` + recap) | — | 🔴 | Not present. |
| G15 | **Confirmed visits** (`kunjungan-harian/allConfirm`) | — | 🔴 | Not present. |
| G16 | **Route-map / performance visualisation** (performa-sales-depo, unique-stores, store-orders) | `/api/admin/...` + route-map.html | 🟠 | route-map.html exists (Leaflet today's plan). Performance/unique-store/store-order analytics missing. |
| G17 | **Sessions management** (`/user-sessions` reset/import) | — | 🔴 | Not present. |
| G18 | **WAB/WhatsApp accounts** (`/whatsapp-accounts` CRUD) | — | 🔴 | Not present. |
| G19 | **Depot configs, OTP-PIC** (`/depo-configurations`, `/depo-otp-pic`) | — | 🔴 | Not present. |
| G20 | **Admin wilayah (regions)** (GET/POST + assign import) | `/api/admin/regions` | 🟠 (not wired) | `wim_regions` table + depots.region_id exist (just added 09-10). No admin CRUD page yet. |

### 3b. KlikOrder admin features

| # | Legacy (KlikOrder) | WIM equivalent | Status | Notes |
|---|---|---|---|---|
| K1 | **Promo CRUD** (`/toko-order/promos`) | — | 🔴 | `wim_promo` tables exist + promo engine in order calc, but **no admin promo UI**. |
| K2 | **Order history / management** (`pesanan-pelanggans`) | `/api/admin/orders` | ✅ | orders.html + status PATCH. |
| K3 | **New products / SKUs** (`produk-baru`, `sku-produks`) | `/api/admin/products` + products.html | 🟠 | Create list/view; catalog. "New products" badge not shown. |
| K4 | **Admin order entry** (`pesanan/admin`, no checkin) | — | 🔴 | Not present (all orders require a rep check-in). |
| K5 | **Packing list** (`packing-list`) | — | 🔴 | Not present. |
| K6 | **Invoice export / PDF** (invoices/export) | — | 🔴 | Only the sales-side order-confirmation QR→PDF. No admin bulk invoice export. |
| K7 | **Catalog download** (catalog/download) | — | 🔴 | Not present. |
| K8 | **Order-vs-store dashboard** (`toko-order/dashboard/{tokoID}`) | `/api/stores/orders` | 🟠 | Store order history exists for reps; no admin store dashboard. |

---

## 4. User-flow charts (how the legacy features should work, and WIM current state)

### 4a. Admin — Depot & Master Data CRUD (G1/G2/G3/G4/G7/G20)

```
[Super Admin] → Dashboard → Master Data
   ├─ Depots      list/TCreate/DEdit/DDelete/Import   → WIM: 🟠 list only
   ├─ Employees   list/TCreate/DEdit/Del/Import        → WIM: 🔴
   ├─ Users       list/TCreate/DEdit/Del/PATCH/PImport → WIM: 🟠 create only
   ├─ Stores      list/TCreate/DEdit/Del/PImport        → WIM: 🔴
   ├─ Vehicles    CRUD        → WIM: 🔴
   ├─ Categories  CRUD/import → WIM: 🔴
   └─ Regions     TCreate/assignDepots → WIM: 🟠 (table only, no UI)
```
**Flow:** login → click module → see list (paginated/filtered) → create/edit → save → toast → list refresh.
**WIM current:** only Users list+create and Depots list. **Missing:** the whole editable-master-data surface.

### 4.2 Sales rep — Order flow (SALES, present in WIM)

```
1. Check-in at store (open visit)
2. Tap 🛒 Buat Pesanan → order.html
3. Browse products (brand filter, search)
4. Add to cart (qty +/-), promos auto-calc
5. Review cart + promo/bonus lines
6. Buat Pesanan → order created (requires open checkin)
7. → success screen: order ID + QR (invoice.html)
8. Verify QR (optional) → return to visit → Selesaikan
✅ Present & correct. (see §5 for promo depth)
```

### 4.3. Admin — Promo management (K1)

```
Super Admin → Promos → [Tambah Promo]
   jenis: bundling | strata | diskon | bonus
   periode: start/end  depot filter
   sku thresholds → bonus/discount rules
   activate/deactivate (status)
   → visible in rep catalog + exports
WIM: 🔴 No promo admin UI. (wim_promo + order engine exist, just no UI.)
```

### 4.4. Admin — Order entry + operations (K4/K5/K6)

```
Depot Admin: Orders → [Tambah Pesanan Manual]
   pick store (search) → reuse cart catalog
   price override / ad-hoc items (dataset: metapreneur)
   no OTP needed → create order (sales_channel='admin')
   → packing list / invoice PDF (bulk)
WIM: 🔴 admin order entry absent; 🔴 packing list; 🟠 invoice only as order-confirmation PDF.
```

### 4.5. Admin — Reporting & analytics (G8/G10–G16)

```
Reports menu:
  Visits (daily/period) + export         → WIM 🟠 (page + client CSV)
  Attendance + export                    → WIM ✅ (page + CSV)
  Stock-checks report + export           → WIM 🟠 (list only)
  Out-of-route orders                    → WIM 🔴
  Shipped orders                         → WIM 🔴
  Surat tugas (task/delivery) + export   → WIM 🔴
  Order vs stock analysis                → WIM 🔴
  Confirmed visits                       → WIM 🔴
  Sales/Depot performance (map/charts)   → WIM 🟠 (route-map partial)
```

---

## 5. Correctness review of WIM-built features (present-but-verify)

| Feature | Correct? | Findings |
|---|---|---|
| Sales visit check-in/out | ✅ | 180s min-visit enforced server-side; open check-in restore. |
| Order requires open check-in | ✅ | `POST /api/orders` validates `checkin_id` open for user+store. |
| Promo engine (bundling/strata/diskon) | ✅ logic, 🟠 UX | Server-side `/api/orders/calculate` correct. Catalog promo badge shown. |
| QR → order confirmation/PDF | ✅ | QR encodes invoice.html;  previously raw-text. |
| Order status transitions | 🟠 | Only super-set PATCH status; no full lifecycle/delo logic, no ship/pack timestamps. |
| Admin depot/region filters | ✅ | Added 09-10 (period, user, depo, region). |
| Product edit (image/details/price) | ✅ | PATCH + image in meta; area pricing is a **future plan** (not yet built). |
| Area/region pricing | 🔴 | Planned (wim_area_product_prices) — not yet implemented. |

---

## 6. Priority backlog (recommended order)

1. **Admin store (customer) management** — import, list, edit, add — highest (feeds everything).
2. **Promo management UI** — self-service promos (backed by existing wim_promo/engine).
3. **Admin order entry** (no-checkin) + order lifecycle/status + packing list.
4. **Depot CRUD + territory/region management UI** (regions already seeded).
5. **Export server-side** (CSV/XLSX) for visits/orders/stock on reports.
6. **Reporting analytics**: out-of-route, shipped, order-vs-stock, sales-depot performance, confirmed visits.
7. Optionali: vehicles, suppliers, user import/PATCHion, WhatsApp/OTP config.

---

## 7. Meeting notes addendum — flows WIM is still missing (2026-09-10)

> Source: WIM team meeting notes (workflow descriptions). Cross-checked against actual code.

### 7a. Visit Card — Belum/Sudah Dikunjungi tabs
- **Legacy:** Visit card has 2 tabs — **"Belum Dikunjungi"** and **"Sudah Dikunjungi"** (completed visits), plus a "register outlet (NOO)" flow with: logco/geo, Sinkronisasi, checkin → NOO → foto → alasan tidak order (mandatory) → kirim kunjungan.
- **WIM status:** 🟠 Visit card has in-route/luar-rute filters + a "Sedang Dikunjungi"/"Selesai" per-store badge, and NO O order-reason + stock + "Sinkronisasi lokasi". But **no explicit 2-tab Belum/Sudah-dikunjungi grouping**, and **NOO is a separate page** (noo.html) not inlined into the visit card flow as the notes describe.
- **Gap:** group visits into Belum/Sudah Dikunjungi; optionally allow NOO registration from the visit card with sync→checkin→NOO.

### 7b. Payment method (Cash / Credit)
- **Legacy:** Opsi pembayaran **cash OR credit** at checkout.
- **WIM:** ❌ **Not present.** No payment-method field in order POST or cart. Only `paymentStatus:UNPAID` on the confirmation. **Missing:** add `payment_method` (cash/credit) to cart + order + invoice.

### 7c. Order type (sales/QR/customer) + out-of-route order-with-type
- **Legacy:** order types: **by sales (app)**, **by customer (QR)**, **by admin (QR from customer list)**, by deliver (next phase). Out-of-route order: select outlet (precondition: barcode), press "Barcode → KlikOrder", then input order with a **transaction type** (options shown in system; becomes "status" on report).
- **WIM:** 🟠 Orders are **app-only via rep**. **No customer/admin QR order entry**, no admin order-by-QR. Out-of-route exists but **no transaction-type option** → no `off_route_reason` picker or status label. 
- **Gap:** order type enum, QR-based customer/admin order entry, transaction-type for out-of-route.

### 7d. Promo — its type + multi-apply + "bonus"/"bundling"
- **Legacy:** 2 promo types **"bonus" and "bundling"**; multi-apply allowed; sales see list of active promos based on **assigned depot setup**; promo data must appear on reports/visualizations.
- **WIM:** 🟠 Engine handles bundling/strata/diskon/bonus with `stackable` flag (multi-apply possible) and depot filter exists in schema. But: **no promo admin/import UI**, and **promo info is NOT shown in the order report line-items** (matches the "report has no promo info" complaint — WIM has same gap). 
- **Gap:** promo depot-setup drill + promo info in exports/reports (non-negotiable #9/#12).

### 7e. Catalog / schedule / promo master imports (self-service)
- **Legacy:** Tim WIM currently **cannot ADD/import products, promos, or schedule** — must submit import form to vendor. KlikOrder admin does this.
- **WIM:** 🔴 **Import not available** for products, visit schedules, or promos. This is a stated WIM self-service goal.
- **Gap:** product/schedule/promo **import** endpoints + UI.

### 7f. Backend admin — monitoring/visualization/reports (Super Admin GooVi)
- **GooS:** EC (Effective Call) hub with:
  a. monitoring (kunjungan detail, rekap kunjungan, presensi/absensi, galeri)
  b. visualization (route maps sales & driver; kunjungan order; kunjungan non-order)
  c. strategic analysis; gudang & stock (closing depo/closing gudang)
- **WIM:** 🟠 has attendance/visits/today-plan pages + route-map.html. **Missing: EC metriccard, kunjungan rekap, gallery foto, non-order route map, closing depo/gudang.**

### 7g. Data/settings admin
- **Legacy (GooVi):** data all (karyawan, user/creds, kendaraan, rencana kunjungan), **session reset (failed login/clear cache)**, brand-per-depo access, customer reassign between sales (**import**).
- **WIM:** 🔴 none of these settings exist. **Gap:** manage sessions, brand-per-depo config, import customer reassign.

### 7h. Closing depo / closing gudang
- **Legacy:** warehouse unused... depo-close and gudang-close flows.
- **WIM:** 🔴 Not present. (Out of immediate V1 priority, but logged.)

### 7i. Dahim — "Selesai Kunjungan" gateway
- **Notes:** after checkout, visiting an order-in-store is... `selesai kunjungan` required before next customer; heavy flow if order without order must complete. If previous order not complete/removed, sales must return/locations.
- **WIM:** ✅ checkout guard exists (must complete open visit). 
- **Gap (UI):** no explicit "you have an un-submitted order — return or delete" tieback to the idea of whether an order exists; needs an order-pending flow (delete/return).

---

### Priority reshuffle (meeting-note insights)
1. **Payment method (cash/credit)** — small, high-value.
2. **Belum/Sudah Dikunjungi tabs** (visit card) — UX parity.
3. **Promo info in order/report exports** + depot-setup promo visibility.
4. **Out-of-transaction order type + QR-based order entry.**
5. **Import builders:** products/schedule/promo (self-service, addresses the vendor reliance complaint).
6. **ECON metric + kunjungan/galeri/non-order visualization + closing depo/gudang.**

---