# WIM Online — Gap User Flows & Findings (GooVi + KlikOrder comparison)

> **Audit + flow spec date:** 2026-09-10
> **Purpose:** Consolidate all findings from comparing the legacy GooVi + KlikOrder admin
> panels against the current WIM Online implementation, and define the **user flows for the
> missing features** so they can be built.
> **Source docs:** APP-MAPPING.md, KLIKORDER-PLAN-DRAFT.md, KLIKORDER-FLOWS-DRAFT.md,
> FEATURE-GAP-AUDIT.md, and WIM team meeting notes (2026-09-10).
> **Legend:** ✅ present · 🟠 partial · 🔴 missing

---

## 1. How to read this document

Each section describes one **legacy user flow** in three parts:

1. **Legacy behaviour** — how GooVi/KlikOrder works today (from the mapping + meeting notes).
2. **WIM status** — what exists now (verified against code, not docs).
3. **Target flow (ASCII chart)** — the flow WIM should implement for parity, with the steps
   marked, so it can be handed straight to a coding subagent.

---

## 2. Consolidated findings (all gaps — summary)

| # | Area | Legacy (GooVi/KlikOrder) | WIM status |
|---|------|--------------------------|-----------|
| 1 | Payment method | Cash OR Credit at checkout | 🔴 No payment-method field |
| 2 | Visit card tabs | "Belum Dikunjungi" / "Sudah Dikunjungi" | 🟠 filter by route only; no 2-tab grouping |
| 3 | Order types | by sales (app), by customer (QR), by admin (QR from list), by deliver (next) | 🟡 app-only via rep |
| 4 | Out-of-route order type | transaction-type options → report "status" | 🟡 add-to-plan exists, no type picker |
| 5 | Promo types | "bonus" + "bundling", multi-apply, depot-setup list | 🟡 engine yes; admin/UI no; promo not in report |
| 6 | Master imports | products / promos / schedules (vendor-required today) | 🔴 no import |
| 7 | Product/schedule self-service | WIM has no create access | 🔴 no self-service |
| 8 | Depots CRUD | list/CREATE/ED/Delete/import + brand-per-depo | 🟠 list only |
| 9 | Employee (karyawan) CRUD | full | 🔴 |
| 10 | Users CRUD + import | full | 🟠 list + create only |
| 11 | Stores (customer) CRUD + import | full | 🔴 no admin store page |
| 12 | Vehicles / suppliers / categories | CRUD | 🔴 |
| 13 | Visit monitoring + export | detail/rekap/foto/usage + export | 🟠 visits page + client CSV |
| 14 | Stock check report + export | report | 🟠 endpoint only |
| 15 | Out-of-route order report | report | 🔴 |
| 16 | Shipped orders report | report | 🔴 |
| 17 | Surat tugas / delivery notes | list + export | 🔴 |
| 18 | Order vs stock analysis | report + recap | 🔴 |
| 19 | Confirmed-visits report | report | 🔴 |
| 20 | Route / performance visualization | sales-depo perf, unique-store, store-order | 🟡 route-map partial |
| 21 | Sessions reset | manage reset/failed-login | 🔴 |
| 22 | WhatsApp / OTP config | accounts CRUD | 🔴 |
| 23 | Depot configs / OTP-PIC | CRUD | 🔴 |
| 24 | Regions (admin wilayah) | create + assign depots | 🟡 table seeded, no admin UI |
| 25 | Admin order entry | create without check-in | 🔴 |
| 26 | Packing list | generate | 🔴 |
| 27 | Invoice / PDF export | bulk | 🔴 (only sales-side order-confirmation PDF) |
| 28 | Catalog download | download | 🔴 |
| 29 | Promo UI | create/manage | 🔴 (wim_promo + engine exist) |
| 30 | EC (Effective Call) hub | kunjungan detail/rekap/galeri/visual | 🔴 |
| 31 | Closing depo / closing gudang | depo/gudang close | 🔴 |
| 32 | Session reset / brand-per-depo / customer-reassign import | settings | 🔴 |
| 33 | Area/region pricing | (new request) | 🔴 planned |

---

## 2. User flows — meeting-notes-driven (the newly-discovered gaps)

### 2.1 Payment method: Cash / Credit

```
LEGACY:  [Checkout] → opsi pembayaran [Cash | Credit] → order saved with method
WIM now: 🔴 no field

TARGET (order checkout):
┌───────────────────────────────────────────────┐
│ 1. Rep taps "Buat Pesanan"                     │
│ 2. Cart review (+promo)                        │
│ 3. NEW: pilih pembayaran                       │
│        ├─ o Cash (Tunai)   ─────────┐          │
│        ├─ o Kredit (CR) ────────────┤          │
│        └─ (default: Cash)            │          │
│ 4. [Buat Pesanan]                              │
│ 5. POST /api/orders { ..., paymentMethod }     │
│ 6. wim_orders.payment_method = cash|credit     │
│ 7. Confirmation screen + QR shows payment type │
└───────────────────────────────────────────────┘
BACKEND:  add payment_method column; validate in (cash, credit).
FILES:    order-cart.js, order.html, serve.py (do_ORDER_POST), invoice.html.
```

### 2.2 Visit card — Belum / Sudah Dikunjungi tabs

```
LEGACY:  Visit Card has 2 menus/tabs:
         [Belum Dikunjungi]  [Sudah Dikunjungi]
         (and "Pilih Rencana Kunjungan", "Register Outlet")
WIM now: 🟡 single list with filter (Dalam/Luar Rute) + per-store status badge.

TARGET (mobile visit-card.html):
  [Belum Dikunjungi] [Sudah Dikunjungi]
             │                 └── list of stores visited today (status=visited/checked)
             └── list of today's store plans (status=pending / active)
                   each store card:
                     name, address, in/out-route badge, status badge
                     buttons: Check-in → (visit flow) / Tambah Luar Rute
  After a visit finishes, the store moves to "Sudah Dikunjungi" automatically.
BACKEND:  already provides store status via /api/stores + /api/visit_plan; add "status"
          grouping in frontend (source+status reveal which tab).
```

---

### 2.3 Order by customer (scan QR) / by admin (scan QR from customer list)

```
LEGACY:  3 order-entry modes:
         1. by sales (app)          ✅ WIM
         2. by customer (QR)        🔴
         3. by admin (QR from list) 🔴
WIM now: ▪ rep app order.

TARGET — Customer self-order by QR:
  [Store displays QR of its outlet]
        │ customer scans (phone)
        ▼
  [order-entry lite: choose products → checkout]
        │ POST /api/orders { order_channel: 'customer', scan_token }
        ▼
  [order confirm + QR (invoice)]
TARGET — Admin order:
  [Admin panel → Orders → Tambah order]
        │pick store (search / scan its barcode)
        ▼
  [same cart] order_channel:'admin'; no check-in required
BACKEND: extend do_ORDER_POST to accept channel + skip checkin_id for admin/customer
  (add order_channel + store_uuid), validate admin/customer authority.
```

---

### 2.4 Out-of-route order with transaction type

```
LEGACY:  luar-rute order: select outlet (precondition: barcode) → button "Barcode →
KlikOrder" → input qty → choose JENIS TRANSAKSI (options from system)
         the chosen type becomes the REPO's "status" on the transaction report.
WIM now: 🟠 can add luar-rute store; no transaction-type picker; no off_route reason.

TARGET:
  [Visit card → Tambah Toko Luar Rute]
        ▼ store added (luar_rute plan)
  [open store → Buat Pesanan]
        ▼ checkout: choose "Jenis Transaksi (Luar Rute)"
            ─ WA / Telepon / Admin-bantu / Lainnya (configurable)
        ▼ POST /api/orders { off_route_reason / off_route_type }
        ▼ visible in admin report as order "status"/src
BACKEND:  add off_route_type column (or use off_route_reason) + surface in /api/orders.
```

---

### 2.5 Promo — bonus + bundling, multi-apply, depot-setup, promo-in-report

```
LEGACY:  2 promo types: "bonus" & "bundling"; multi-apply; sales see active promos
         based on ASSIGNED DEPOT setup; promo info must show in reports.
WIM: 🟠 engine (bundling/strata/diskon/bonus) + stackable; but NO admin UI, NO depot-setup,
         and promo NOT shown in order exports/reports (matches legacy complaint).

TARGET (admin promo mgmt):
  [Admin → Promos]  [Tambah Promo]
     jenis: bonus | bundling  (strata/diskon optional)
     periode start/end · status · depot filter (depot yg menampilkannya)
     item SKUs + thresholds, bonus SKUs + qty
     [Simpan] → visible in rep catalog + applied at cart
  [Non-negociable] ALL order exports include for each line:
     is_bonus, promo_name, promo_ref, promo_type
BACKEND:  /api/admin/promos CRUD + do_ORDER export must include promo fields
  (already in wim_promo; wire UI + exports).
```

---

### 2.6 Master imports (products / schedules / promos) — self-service

```
LEGACY:  tim WIM saat ini TIDAK bisa menambah/import produk, promo, atau jadwal —
         harus submit form import ke vendor. KlikOrder admin dapat melakukan.
Goal:    WIM self-service.

TARGET:
  [Admin → Import]
     ├─ Import Products   (CSV: sku, name, brand, category, price, ...) → /api/admin/products/import
     ├─ Import Schedule   (CSV: sales, store, date/cycle, priority) → /api/admin/visit-plans/import
     └─ Import Promo      (CSV: jenis, sku/min, bonus, periode, depot) → /api/admin/promos/import
  Each: upload → parse + validate → preview errors → confirm → insert / log
BACKEND:  import endpoints + a simple importer helper.
```

---

### 2.7 Dashboard analytics / visualizations (EC, route maps, gallery)

```
LEGACY (Super Admin GooVi):  "ECON" hub:
   a. monitoring:  kunjungan detail, rekap kunjungan, presensi/absensi, galeri
   b. visualisasi: route map sales & driver; kunjungan (order); kunjungan non-order
   c. analisa strategis; gudang & stock (closing depo/closing gudang)
WIM now: 🟡 attendance/visits/today-plan pages + route-map.html (today's plan).

TARGET (admin dashboard):
  [Dashboard]  EC: # effective calls / visits / orders
  [Kunjungan Detail / Rekap]      [Galeri Foto]
  [Route Map Sales & Driver ⚑]   [Route Map Order / Non-order]
  [Analisa Strategis / Order-vs-Stock]
  [Closing Depo] [Closing Gudang]
BACKEND:  reuse visits/orders/attendance + add gallery (photos), route maps (order vs non),
  closing depo/gudang endpoints.
```

---

### 2.8 Settings / auth admin

```
LEGACY (GooVi settings):
  - user sessions: reset for failed-login/clear-cache
  - brand per depot (depot brand access)
  - customer of stall?  → import (reassign between sales)
WIM now: none of these.

TARGET:
  [Admin → Settings]
     ├─ Sessions / Akun (list, reset)
     ├─ Brand per Depo (table depot→brands, edit)
     └─ Customer Reassign (CSV import: old_sales → new_sales)
```

---

### 2.9 Admin depot / territory management (region)

```
LEGACY:   depos CRUD + import; admin wilayah (regions GET/POST + assign depots import).
WIM: 🟠 wim_regions + depots.region_id added (09-10); used as report filter; no admin UI.

TARGET:
  [Super Admin → Territory]
     ├─ Regions list / add / edit (name, kode)
     ├─ Depots list / add / edit / delete / import
     └─ Assign regions to depots (dropdown); assign depots to region
```

---

## 3. Correctness notes on what IS built

| Built feature | Verdict | Detail |
|---|---|---|
| Sales check-in / out + 180s min | ✅ | server-side guard; open-checkin restore |
| Order requires open check-in | ✅ | /api/orders validates open w
 visit for user+store |
| Promo engine (bundling/strata) | ✅ | server-side calculate; multi-apply via stackable |
| QR → order confirmation PDF | ✅ | invoice.html, downloadable |
| Admin dashboard / report filters | ✅ | period + user + depot + region (09-10) |
| Product edit (image/price/details) | ✅ | PATCH + meta image |
| Area/region pricing | 🔴 | planned (wim_area_product_prices) |
| Payment method | 🔴 | not built |
| Visit card Belum/Sudah tabs | 🟡 | does not exist as separate tabs |

---

## 4. Recommended build order (gated)

1. **Payment method (cash/credit)** — tiny, unblocks vehicle.
2. **Promo info in order / report exports** — closes the "promo tidak tampil di report" complaint.
3. **Visit card Belum/Sudah Dikunjungi tabs** — parity.
4. **Out-of-route transaction-type** + QR-based customer/admin order entry.
5. **Master imports (products/schedules/promos) + promo admin UI** — closes the "must submit vendor form" dependency.
6. **Stores (customer) admin + depot/region CRUD.**
7. **Server-side exports (CSV/XLSX)** on report pages.
8. **ECON / gallery / route-map analytics + closing depo/gudang.**

---

## 5. References

- `FEATURE-GAP-AUDIT.md` — quantified gap matrix (GooVi + KlikOrder → WIM) with counts
- `APP-MAPPING.md` — endpoint mapping (legacy → WIM target)
- `KLIKORDER-PLAN-DRAFT.md`, `KLIKORDER-FLOWS-DRAFT.md` — order lifecycle & promo specs
- Meeting notes 2026-09-10 (payment, visit tabs, order types, imports, ECON, settings)

---