# Application Mapping — GooVi + KlikOrder → WIM Online

> Mapped via reverse-engineering the Nuxt SPA bundles and live API probing (2026-09-07).
> This document maps legacy endpoints to their WIM Online `/api/*` equivalents.

## GooVi — Sales Visit App

**Original API Base:** `https://api-cloud.goovi.satriamitra.website/api`
**WIM Online Equivalent:** All endpoints under `/api/*` on the WIM server

### Authentication

| Original GooVi Endpoint | WIM Online Endpoint | Notes |
|------------------------|-------------------|-------|
| `POST /api/login` | `POST /api/auth/login` | Returns cookie + user data; no `device_info` required |
| `DELETE /api/user-sessions/reset/session/{id}` | `POST /api/auth/logout` | Session-based (cookie), not token-based |
| `POST /api/logout` | `POST /api/auth/logout` | Destroys session + clears cookie |

### Sales Panel — Visit Card

| GooVi Endpoint | WIM Online Endpoint | Description |
|----------------|-------------------|-------------|
| `GET /api/rencana-kunjungan/kunjungan-hari-ini/pilihan` | `GET /api/stores` | Today's visit plan |
| `POST /api/rencana-kunjungan-driver/kanvas/on-the-fly` | `POST /api/visit_plan` | Add ad-hoc store |
| `POST /api/rencana-kunjungan/kunjungan-hari-ini/set-prioritas` | `PUT /api/visit_plan/priority` | Set visit priority |
| `GET /api/konfirm-kunjungan?visitID=X` | `GET /api/visits/{id}` | Visit confirmation data |
| `POST /api/kunjungan-harian` | `POST /api/visits` | Submit daily visit |
| `POST /api/log-order-luar-rute` | Included in `POST /api/visits` | Out-of-route logged via visit flow |

### Sales Panel — NOO (New Outlet Opening)

| GooVi Endpoint | WIM Online Endpoint | Description |
|----------------|-------------------|-------------|
| `POST /api/pelanggans/` | `POST /api/stores` | Create/update store |
| `POST /api/pelanggans/noo/draft` | `POST /api/stores/draft` | Save NOO as draft |
| `POST /api/pelanggans/noo/` | `POST /api/stores` | Submit complete NOO |
| `DELETE /api/pelanggans/{id}` | `DELETE /api/stores/{id}` | Delete store |
| `GET /api/channels` | `GET /api/channels` | Channel dropdowns |
| `GET /api/kategori-pelanggan` | `GET /api/store-categories` | Customer categories |
| `GET /api/otp-whatsapp/check-kadepo` | `GET /api/otp/check` | OTP check |
| `POST /api/otp-whatsapp/request-kadepo` | `POST /api/otp/request` | Request OTP |
| `POST /api/otp-whatsapp/verify-kadepo` | `POST /api/otp/verify` | Verify OTP |

### Sales Panel — Products & References

| GooVi Endpoint | WIM Online Endpoint |
|----------------|-------------------|
| `GET /api/produk` | `GET /api/products` |
| `GET /api/produk/brands-auth` | `GET /api/products/brands` |
| `GET /api/channels` | `GET /api/channels` |
| `GET /api/kategori-pelanggan` | `GET /api/store-categories` |

### Sales Panel — Stock & History

| GooVi Endpoint | WIM Online Endpoint |
|----------------|-------------------|
| `GET /api/kunjungan-cek-stok-brand/order-terakhir-pelanggan` | `GET /api/stores/{id}/last-order` |
| `POST /api/pesanan-detail/surat-tugas/history` | `GET /api/orders/history` |

### Super Admin — Depot (Depo)

| GooVi Endpoint | WIM Online Endpoint |
|----------------|-------------------|
| `GET /depos` | `GET /api/admin/depots` |
| `POST /depos` | `POST /api/admin/depots` |
| `PUT /depos/{id}` | `PUT /api/admin/depots/{id}` |
| `DELETE /depos/{id}` | `DELETE /api/admin/depots/{id}` |
| `POST /import-depo` | `POST /api/admin/depots/import` |

### Super Admin — Employee (Karyawan)

| GooVi Endpoint | WIM Online Endpoint |
|----------------|-------------------|
| `GET /karyawans` | `GET /api/admin/employees` |
| `POST /karyawans` | `POST /api/admin/employees` |
| `PUT /karyawans/{id}` | `PUT /api/admin/employees/{id}` |
| `DELETE /karyawans/{id}` | `DELETE /api/admin/employees/{id}` |
| `GET /karyawan-jenis-sales` | `GET /api/admin/sales-types` |
| `POST /import-karyawan` | `POST /api/admin/employees/import` |

### Super Admin — User

| GooVi Endpoint | WIM Online Endpoint |
|----------------|-------------------|
| `GET /users-filtered` | `GET /api/admin/users` |
| `POST /users` | `POST /api/admin/users` |
| `PUT /users/{id}` | `PUT /api/admin/users/{id}` |
| `DELETE /users/{id}` | `DELETE /api/admin/users/{id}` |
| `PATCH /users/{id}` | `PATCH /api/admin/users/{id}` |
| `POST /users/import-update` | `POST /api/admin/users/import` |

### Super Admin — Customer/Store (Pelanggan)

| GooVi Endpoint | WIM Online Endpoint |
|----------------|-------------------|
| `GET /pelanggans-filtered` | `GET /api/admin/stores` |
| `PUT /pelanggans/{id}` | `PUT /api/admin/stores/{id}` |
| `DELETE /pelanggans/{id}` | `DELETE /api/admin/stores/{id}` |
| `POST /import-pelanggan` | `POST /api/admin/stores/import` |
| `POST /import-update-pelanggan` | `POST /api/admin/stores/import-update` |

### Super Admin — Product (Produk)

| GooVi Endpoint | WIM Online Endpoint |
|----------------|-------------------|
| `GET /produk` | `GET /api/admin/products` |
| `PUT /produk/{id}` | `PUT /api/admin/products/{id}` |
| `GET /produk/brands` | `GET /api/admin/products/brands` |
| `POST /produk/sync` | `POST /api/admin/products/sync` |
| `GET /channels` | `GET /api/channels` |

### Super Admin — Visit Plan (Rencana Kunjungan)

| GooVi Endpoint | WIM Online Endpoint |
|----------------|-------------------|
| `GET /rencana-kunjungan` | `GET /api/admin/visit-plans` |
| `DELETE /rencana-kunjungan/{id}` | `DELETE /api/admin/visit-plans/{id}` |
| `POST /import-rencana-kunjungan` | `POST /api/admin/visit-plans/import` |

### Super Admin — Other Master Data

| GooVi Endpoint | WIM Online Endpoint |
|----------------|-------------------|
| `GET /kendaraans` | `GET /api/admin/vehicles` |
| `POST /kendaraans` | `POST /api/admin/vehicles` |
| `PUT /kendaraans/{id}` | `PUT /api/admin/vehicles/{id}` |
| `DELETE /kendaraans/{id}` | `DELETE /api/admin/vehicles/{id}` |
| `GET /suppliers` | `GET /api/admin/suppliers` |
| `GET /kategori-pelanggan` | `GET /api/admin/store-categories` |
| `POST /kategori-pelanggan/import` | `POST /api/admin/store-categories/import` |

### Super Admin — Visit Monitoring & Reporting

| GooVi Endpoint | WIM Online Endpoint |
|----------------|-------------------|
| `GET /kunjungan-harian/all` | `GET /api/admin/visits` |
| `GET /kunjungan-harian/export` | `GET /api/admin/visits/export` |
| `GET /kunjungan-harian/report-foto` | `GET /api/admin/visits/photos` |
| `GET /kunjungan-harian/export-foto` | `GET /api/admin/visits/photos/export` |
| `GET /kunjungan-harian/detail-penggunaan-aplikasi` | `GET /api/admin/activity-log` |
| `GET /kunjungan-harian/export-detail-penggunaan-aplikasi` | `GET /api/admin/activity-log/export` |
| `GET /kunjungan-harian/report-harian` | `GET /api/admin/daily-recap` |
| `GET /kunjungan-harian/export-rekap` | `GET /api/admin/daily-recap/export` |
| `GET /absensi` | `GET /api/admin/attendance` |
| `GET /absensi/export` | `GET /api/admin/attendance/export` |
| `GET /kunjungan-cek-stok-brand/report/all` | `GET /api/admin/stock-checks` |
| `GET /kunjungan-cek-stok-brand/export` | `GET /api/admin/stock-checks/export` |
| `DELETE /kunjungan-cek-stok-brand/{id}` | `DELETE /api/admin/stock-checks/{id}` |
| `GET /report-order-luar-rute` | `GET /api/admin/out-of-route-orders` |

### Super Admin — Order & Invoice Reporting

| GooVi Endpoint | WIM Online Endpoint |
|----------------|-------------------|
| `GET /pesanan-detail-terkirim` | `GET /api/admin/shipped-orders` |
| `GET /pesanan-detail-terkirim/export` | `GET /api/admin/shipped-orders/export` |
| `GET /pesanan/surat-tugas` | `GET /api/admin/task-documents` |
| `GET /pesanan/surat-tugas/export` | `GET /api/admin/task-documents/export` |
| `GET /pesanan-detail/surat-tugas/history` | `GET /api/admin/order-history` |
| `GET /report/analisa-order-vs-stok` | `GET /api/admin/order-vs-stock` |
| `GET /report/analisa-order-vs-stok/export` | `GET /api/admin/order-vs-stock/export` |
| `GET /report/analisa-order-vs-stok/rekap` | `GET /api/admin/order-vs-stock/recap` |
| `GET /report/analisa-order-vs-stok/rekap/export` | `GET /api/admin/order-vs-stock/recap/export` |
| `GET /kunjungan-harian/allConfirm` | `GET /api/admin/confirmed-visits` |

### Super Admin — Route Map Visualization

| GooVi Endpoint | WIM Online Endpoint |
|----------------|-------------------|
| `GET /report-visualisasi/performa-sales-depo` | `GET /api/admin/sales-performance` |
| `GET /report-visualisasi/performa-sales-depo-harian` | `GET /api/admin/sales-performance/daily` |
| `GET /rencana-kunjungan/pelanggan-unik` | `GET /api/admin/unique-stores` |
| `GET /kunjungan-harian/report-order-pelanggan` | `GET /api/admin/store-orders` |

### Super Admin — Settings

| GooVi Endpoint | WIM Online Endpoint |
|----------------|-------------------|
| `GET /user-sessions` | `GET /api/admin/sessions` |
| `DELETE /user-sessions/reset/{session_id}` | `DELETE /api/admin/sessions/{id}` |
| `POST /user-sessions/import-reset-session` | `POST /api/admin/sessions/reset-bulk` |
| `PUT /depo/brands-bulk` | `PUT /api/admin/depots/brands-bulk` |
| `GET /depo/{id}/brand` | `GET /api/admin/depots/{id}/brands` |
| `GET /surat-jalan-driver/by-kode` | `GET /api/admin/delivery-notes/by-code` |
| `DELETE /surat-jalan-driver/{id}` | `DELETE /api/admin/delivery-notes/{id}` |
| `GET /depo-configurations` | `GET /api/admin/depot-configs` |
| `POST /depo-configurations` | `POST /api/admin/depot-configs` |
| `GET /depo-otp-pic` | `GET /api/admin/otp-pic` |
| `POST /depo-otp-pic` | `POST /api/admin/otp-pic` |
| `GET /whatsapp-accounts` | `GET /api/admin/whatsapp-accounts` |
| `POST /whatsapp-accounts` | `POST /api/admin/whatsapp-accounts` |
| `PUT /whatsapp-accounts/{id}` | `PUT /api/admin/whatsapp-accounts/{id}` |
| `DELETE /whatsapp-accounts/{id}` | `DELETE /api/admin/whatsapp-accounts/{id}` |

### Admin Wilayah

| GooVi Endpoint | WIM Online Endpoint |
|----------------|-------------------|
| `GET /admin-wilayah/{id}` | `GET /api/admin/regions/{id}` |
| `POST /admin-wilayah` | `POST /api/admin/regions` |
| `POST /admin-wilayah/depos/assign/import` | `POST /api/admin/regions/depots/assign` |

---

## KlikOrder Super Admin Panel

### Admin API Endpoints (Confirmed)

| KlikOrder Endpoint | WIM Online Endpoint |
|--------------------|-------------------|
| `GET /toko-order/promos` | `GET /api/admin/promos` |
| `POST /toko-order/promos` | `POST /api/admin/promos` |
| `GET /toko-order/pesanan-pelanggans` | `GET /api/admin/order-history` |
| `GET /toko-order/produk-baru` | `GET /api/admin/products/new` |
| `GET /toko-order/sku-produks` | `GET /api/admin/products/skus` |

### Admin API Endpoints (Inferred)

| KlikOrder Endpoint | WIM Online Endpoint |
|--------------------|-------------------|
| `GET /toko-order/users` | `GET /api/admin/users` |
| `GET /toko-order/karyawan` | `GET /api/admin/employees` |
| `GET /toko-order/pelanggan` | `GET /api/admin/stores` |
| `POST /toko-order/pesanan/admin` | `POST /api/admin/orders` |
| `GET /toko-order/dashboard-summary` | `GET /api/admin/dashboard` |
| `GET /toko-order/packing-list` | `GET /api/admin/packing-lists` |
| `POST /toko-order/invoices/export` | `POST /api/admin/invoices/export` |
| `GET /toko-order/catalog/download` | `GET /api/admin/catalog/download` |

### Sales Panel — Store & Products

| KlikOrder Endpoint | WIM Online Endpoint |
|--------------------|-------------------|
| `GET /api/toko-order/dashboard/{tokoID}` | `GET /api/stores/{id}/dashboard` |
| `GET /api/toko-order/brand-produks` | `GET /api/products/brands` |
| `GET /api/toko-order/sku-produks` | `GET /api/products/skus` |
| `GET /api/toko-order/sku-produks/search` | `GET /api/products/search` |
| `GET /api/toko-order/sku-produks/filter-availability` | `GET /api/products?available=true` |
| `GET /api/toko-order/jenis-produks` | `GET /api/products/types` |
| `GET /api/toko-order/kategori-produks` | `GET /api/products/categories` |
| `GET /api/toko-order/produk-baru` | `GET /api/products/new` |

### Sales Panel — Promos & Bundling

| KlikOrder Endpoint | WIM Online Endpoint |
|--------------------|-------------------|
| `GET /api/toko-order/promos/deskripsi-all/{tokoID}` | `GET /api/promos/store/{id}` |
| `GET /api/toko-order/promo/shortcut-bundling` | `GET /api/promos/bundling-shortcuts` |
| `GET /api/toko-order/products/discounted-preview` | `GET /api/promos/discounted-products` |
| `POST /api/toko-order/promo/check-bundling` | `POST /api/promos/check-bundling` |
| `POST /api/toko-order/promo/check-bundling-bonus` | `POST /api/promos/check-bundling-bonus` |
| `POST /api/toko-order/promo/check-strata` | `POST /api/promos/check-strata` |
| `POST /api/toko-order/promo/calculate-global-combined-strata-discount` | `POST /api/promos/calculate-combined` |
| `POST /api/toko-order/promo/checkAllPromoKeranjang-byPrioritas` | `POST /api/promos/check-cart` |

### Sales Panel — Orders

| KlikOrder Endpoint | WIM Online Endpoint |
|--------------------|-------------------|
| `GET /api/toko-order/pesanan-pelanggans` | `GET /api/stores/{id}/orders` |
| `POST /api/toko-order/verify-otp/{id}` | `POST /api/otp/verify/{id}` |
| `GET /api/slideshow-dashboard` | `GET /api/dashboard/slideshow` |

### Sales Panel — Other

| KlikOrder Endpoint | WIM Online Endpoint |
|--------------------|-------------------|
| `POST /api/cek-rencana-kunjungan` | `GET /api/visit-plan/check` |
| `POST /api/selesai-kegiatan` | `POST /api/visits/end-day` |
| `POST /api/toko-order/register-device-token` | `POST /api/devices/register` |
| `POST /api/toko-order/send-notification` | `POST /api/notifications/send` |

---

## Existing API Endpoint Map (WIM Online)

| Endpoint | Method | Purpose | Auth | Status |
|----------|--------|---------|------|--------|
| `/api/auth/login` | POST | Email/password login | No | ✅ Built |
| `/api/auth/session` | GET | Validate session cookie | Cookie | ✅ Built |
| `/api/auth/logout` | POST | Destroy session | Cookie | ✅ Built |
| `/api/dashboard` | GET | Per-user dashboard data | Cookie | ✅ Built |
| `/api/absensi` | GET/POST | Attendance CRUD | Cookie | ✅ Built |
| `/api/stores` | GET | Today's visit plan stores | Cookie | ✅ Built |
| `/api/stores/all` | GET | Search all stores | Cookie | ✅ Built |
| `/api/visit_plan` | POST | Add luar rute store | Cookie | ✅ Built |
| `/api/visits` | GET/POST | Visits CRUD | Cookie | ✅ Built |
| `/api/report` | GET | Per-user report | Cookie | ✅ Built |
| `/api/log` | POST | Client-side logging | Cookie | ✅ Built |
| `/api/logs` | GET | Read server logs | Cookie | ✅ Built |
| `/api/stores/{id}/last-order` | GET | Last order per store | Cookie | ✅ Built |
| `/api/stores/orders` | GET | Store order history | Cookie | ✅ Built |
| `/api/stock` | POST | Stock check | Cookie | ✅ Built |
| `/api/admin/*` | — | Admin endpoints | Cookie+Role | 🔴 Not built |
| `/api/orders/*` | — | Order CRUD endpoints | Cookie | 🔴 Not built |
| `/api/promos/*` | — | Promo management | Cookie+Role | 🔴 Not built |

---

## GooVi Data Model → PostgreSQL

### Depo
`kode`, `nama` → `wim_depo` table

### Karyawan (Employee)
`nama`, `id_depo` → `wim_karyawan` table

### Pelanggan (Customer/Store) — full schema
`id`, `kode`, `nama`, `longitude`, `latitude`, `id_depo`, `nama_pemilik`, `kontak_person`, `alamat_lengkap`, `kecamatan`, `kelurahan`, `kota`, `provinsi`, `jenis_kendaraan`, `no_hp`, `kode_pos`, `nik`, `npwp`, `nama_npwp`, `status_pelanggan`, `status_otp_kadepo`, `id_kategori_pelanggan` → `wim_pelanggan` table

### Absensi (Attendance)
`id_karyawan`, `waktu`, `jenis` (checkin/checkout), `latitude`, `longitude`, `foto_absensi` → `wim_attendance` table

### Kategori Pelanggan
`kode`, `kategori`, `channel_id` → `wim_store_categories` table

### Jenis Sales
TO (Trade Outlet), SPC, SPG, Motoris, SMD, Kanvaser → `wim_sales_types` table

---

## Key Data Model Differences

### GooVi data shape:
- **RencanaKunjungan** (Visit Plan): `{id, id_karyawan, id_pelanggan, minggu_rencana (week of month), hari, status_tugas, prioritas_kunjungan, is_dalam_rute (boolean), pelanggan (nested)}`
- **Pelanggan** (Customer/Store): `{id, kode, nama, longitude, latitude, id_depo, nama_pemilik, kontak_person, alamat_lengkap, kecamatan, kelurahan, kota, provinsi, jenis_kendaraan, no_hp, kode_pos, nik, npwp, nama_npwp, status_pelanggan, status_otp_kadepo, id_kategori_pelanggan}`
- **KunjunganHarian** (Daily Visit): Submitted via POST with check-in/check-out timestamps, visit outcome
- **Channel/Kategori**: Hierarchical — channel (GT/MT/Inst) → kategori (Retail Kecil, Grosir, etc.)

### KlikOrder data shape:
- **Brand**: `{kode_brand, nama_brand}` — SQA (SANQUA) primary
- **SKU**: Multi-brand product catalog
- **Promo/Bundling**: Multiple promotional systems (bundling, strata discounts, combined global discounts)
- **Product hierarchy**: Jenis (type) → Kategori (category) → Brand → SKU
- **Pesanan** (Order): Has order lines, promo tracking, OTP verification

---

## WIM Online Gaps vs Legacy Apps

| Current Feature | Legacy Support | WIM Online Status | Mitigation Plan |
|----------------|---------------|-------------------|-----------------|
| Bundling promos (mix X get Y free) | Native | 🔴 Not built | Custom Promo model + frontend logic |
| Strata discounts | Native | 🔴 Not built | Custom Promo model or frontend-calculated |
| OTP verification (WA, depo PIC) | Native | 🔴 Not built | Webhook → WhatsApp gateway integration |
| Selfie/photo on visit | Native | ✅ Built | Photo upload on attendance |
| 3-min minimum timer | Native | ✅ Built | Frontend + server-side timer |
| Route plan import (4-week cycle) | Native | 🔴 Not built | Import script building 20 route presets |
| Barcode/QR scanning | Native (KlikOrder) | 🔴 Not built | Custom integration |
| Koin game (gamification) | Native | 🚫 Out of scope | Not planned |
| Promo catalog downloads | Native | 🔴 Not built | Custom promo model |

---

## Future Integration Endpoints

See `FUTURE-INTEGRATION.md` for the complete specification of:

- **Future sync endpoints** — bidirectionally sync orders and stores via sync layer
- **Odoo sync endpoints** — push reports and accounting data
- **Warehouse sync endpoints** — sync inventory and stock levels

These are NOT required for V1. They are optional future integrations that will be added after the standalone system stabilizes.