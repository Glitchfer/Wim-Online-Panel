# Klikorder Promo / Order Detail — DB Comparison & Data Import Record

> **Date:** 2026-09-11 · **Source:** 3 monthly `Klikorder + Promo` exports (Jun/Jul/Agu 2026) + live `wim_sfa`.

## 1. What the Klikorder exports contain
Sheets per file (Jul file is the richest): **Rekap Pesanan**, **Detail Pesanan**, **Detail Pesanan Promo (T1)**, **PV**, **Detail Pesanan Promo (T2)**, **Rekap Promo**, **Detail Promo**.

Key columns (promo/order detail):
`Tanggal · Jam · Kode Pesanan · Kode Pelanggan · Nama Pelanggan · Kode Sales · Nama Sales · Depo · Order Source · Jenis Pembayaran · Produk · Qty · Qty Bonus · Produk Bonus · Nama Promo · Harga · Subtotal Sebelum Diskon · Subtotal Setelah Diskon · Longitude · Latitude · Alamat Lengkap · Kelurahan · Kecamatan · Kabupaten/Kota · No HP · No HP dari GooVi`

Plus promo-specific: `Diskon per Unit · Diskon per Paket · Diskon Total · Jumlah Paket · Produk Bonus · Qty Bonus`.

---

## 2. Function mapping → WIM database

| Klikorder field | Function | WIM source | Covered? |
|---|---|---|---|
| Tanggal / Jam | Order timestamp | `wim_orders.created_at` | ✅ |
| Kode Pesanan | Order ref | `wim_orders.order_ref` | ✅ |
| Kode / Nama Pelanggan | Customer | `wim_stores.store_code`* + `name` | ✅ (store_code added) |
| Kode / Nama Sales | Sales rep | `wim_users` + `wim_user_meta.employee_code`* | ✅ (employee_code added) |
| Depo | Depot | `wim_depots` | ✅ |
| Order Source | in/out route etc. | `wim_orders.source` / `off_route_reason` | ✅ |
| Jenis Pembayaran | payment (CASH/CREDIT) | `wim_orders.payment_method` | ✅ |
| Produk / Qty / Harga / Subtotal | line item | `wim_orders.items` JSON + `wim_order_items` | ✅ |
| Qty Bonus / Produk Bonus / Nama Promo | promo award | `wim_orders.promos_applied` + `wim_promo*` | ✅ |
| Diskon per Unit/Paket/Total | discount | `wim_orders.promos_applied`/`discount` | ⚠️ discount totals not stored as a column (derivable from items/promos) |
| Subtotal Sebelum/Sesudah Diskon | totals | `wim_orders.total`(after) only | ⚠️ no separate "before" store; historical orders only keep final |
| Long/Lat, Alamat, Kel/Kec/Kab | store address/geo | `wim_stores.*` | ✅ |
| No HP (GooVi vs Klikorder) | phone | `wim_stores.phone` + `phone_verified`* | ✅ (phone_verified added) |

*— added in this DB-completion migration (`11-db-completion.sql`).

---

## 3. What was MISSING → now added
1. **`wim_vehicles` table** (vehicle master: kode, plat_no, jenis, kubikasi, berat_jenis, depot) — was referenced by `wim_user_meta.vehicle_id` but absent.
2. **`wim_stores.store_code`** — Goovi/Klikorder use business codes (`PLG-…`, `ORD-…`); WIM had only UUIDs.
3. **`wim_stores.phone_verified`** — "Status Verif No HP" (belum_verif/verified).
4. **`wim_user_meta.employee_code`** — Goovi employee codes (`KRY-…`) for users.
5. **`wim_stores.updated_at`** — update audit (Goovi tracks update times).

Still only partially covered (acceptable, derivable): separate **Subtotal Sebelum Diskon** and **Diskon Total** columns on orders — WIM keeps final `total` and the promo breakdown in `promos_applied` JSON; historical "before" is only recoverable if replayed.

---

## 4. Data imported (reference/testing data, mock/trial excluded)

All 4 reference exports imported idempotently via `scripts/import_goovi.py`:

| Entity | Source export | Rows imported | Mock excluded |
|---|---|---|---|
| **Vehicles** | Data_Kendaraan | 50 | 0 |
| **Depots** | Data_User / Data_Karyawan (Nama Depo) | 58 new + 4 existing = 62 | 0 |
| **Users** | Data_User (active sales + others) | 505 new + existing | ~9 mock rows (names/trial) |
| **Customers/Stores** | Data_Pelanggan | 15,496 new + existing = 15,526 | 8 mock/trial rows |

Notes:
- Import is **idempotent** (`ON CONFLICT … DO UPDATE`) — re-running won't duplicate.
- Imported users carry a **placeholder, non-usable password hash** — they exist for dataset completeness; only the original test accounts (Andi, Reinhart, etc.) have real credentials. This is intentional to avoid creating login accounts from source data.
- Province codes backfilled for 13,133/15,526 stores; city codes 446 — Goovi "city" names (e.g. "Jakarta Selatan", "Tangerang") don't always exactly match BPS full names, so city-level cascading may be partial. Kecamatan/kelurahan codes filled where the source had exact names.
- **Mock/trial excluded:** rows whose code/name matched `mock|trial|dummy|qa-e2e|percobaan|contoh|test|prueba|uji` were skipped (8 store rows, 9 user rows; none in vehicles/depots).

## 5. Promo transaction data (Detail Pesanan Promo, Rekap Promo)
Not bulk-imported — these are **derivable order-level analytics** (aggregates over `wim_orders`). The structure is fully supported by WIM's `wim_orders.promos_applied` + `wim_promo*` engine. If you want the historical promo *transactions* staged, I can import `Detail Pesanan Promo` rows into `wim_orders`/`wim_order_items` as historical orders — say the word.

## 6. Re-run / rollback
- Re-run any stage: `python3 scripts/import_goovi.py <vehicles|depots|users|customers>` (idempotent).
- Rollback DB-completion: `DROP TABLE wim_vehicles; ALTER TABLE wim_stores DROP COLUMN store_code, phone_verified, updated_at; ALTER TABLE wim_user_meta DROP COLUMN employee_code;` (additive migration, safe to drop).