# DB Gap Analysis — Goovi/KlikOrder Exports vs WIM Online Database

> **Date:** 2026-09-11 · **Source:** 4 exported Excel files (Goovi/KlikOrder) + live `wim_sfa` schema.
> Export sizes: Karyawan 540 rows · User 514 · Pelanggan 15,504 · Kendaraan 50.

## 1. What the exports contain (columns per sheet)

### Data_Karyawan.xlsx (employee)
| Column | | Column | |
|---|---|---|---|
| Kode | ✓ | Nama | |
| Nama Depo | | | |

### Data_User.xlsx (user accounts)
| Column | | Column | |
|---|---|---|---|
| Nama Depo | | Username | |
| Kode Karyawan | | Role | |
| Nama Karyawan | | Status | • Non Aktif |

| Column | | Column | |
|---|---|---|---|
| Jenis Sales | (SPG, etc.) | Tanggal Dibuat | |
| Waktu Dibuat | | Tanggal Diupdate | |
| Waktu Diupdate | | | |

### Data_Pelanggan.xlsx (customer/store) — 25 columns
| Column | | Column | |
|---|---|---|---|
| Kode | ↔ **store code** | Nama | |
| Longitude | | Latitude | |
| Nama Depo | | Nama Sales | (assigned salesperson) |
| Channel | (GT/Horeca/MT/...) | Kategori Pelanggan | (Hotel, Distributor, Retail Kecil...) |
| Nama Pemilik | | Kontak Person | |
| No HP | | Status Verif No HP | (belum_verif) |
| Alamat Lengkap | | Kode Pos | |
| NIK | | NPWP | |
| Nama NPWP | | Kecamatan | |
| Kelurahan | | Kota | |
| Provinsi | | Tanggal Dibuat | |
| Waktu Dibuat | | Tanggal Update | |
| Waktu Update | | | |

### Data_Kendaraan.xlsx (vehicle)
| Column | | Column | |
|---|---|---|---|
| Kode | ↔ **vehicle code** | PlatNo | (plate) |
| Jenis | (L300, Carry...) | Kubikasi | (cubic capacity) |
| BeratJenis | (weight) | Depo | (depot) |

---

## 2. Comparison vs WIM database (live schema)

### Customer (wim_stores) — vs Data_Pelanggan
| Goovi field | In WIM? | Notes |
|---|---|---|
| Kode | ⚠️ PARTIAL | `wim_stores.uuid` (UUID) exists, but **no human/business store code** like `PLG-244-...` |
| Nama / Alamat / Kode Pos | ✅ | `name, address, kode_pos` |
| Longitude / Latitude | ✅ | `latitude, longitude` |
| Nama Depo | ✅ | `region_id`/join via depot (indirect) |
| Nama Sales (assigned) | ✅ | `assigned_salesperson_id` |
| Channel | ✅ | `channel` |
| Kategori Pelanggan | ✅ | `category` |
| Nama Pemilik / Kontak Person | ✅ | `owner_name` + `wim_store_contacts` |
| No HP | ✅ | `phone` |
| Status Verif No HP | ❌ **MISSING** | no `phone_verified` / `status_verif_hp` column |
| NIK / NPWP / Nama NPWP | ✅ | `nik, npwp, npwp_name` |
| Kecamatan / Kelurahan / Kota / Provinsi | ✅ | `kecamatan, kelurahan, city, province` (+ `*_id` codes) |
| Tanggal/Waktu Dibuat & Update | ⚠️ | `created_at` exists; **no `updated_at` on wim_stores**; separate date vs time not stored |

### Employee/user (wim_users + wim_user_meta) — vs Data_Karyawan + Data_User
| Goovi field | In WIM? | Notes |
|---|---|---|
| Kode Karyawan | ⚠️ PARTIAL | `wim_user_meta` has `nik` but **no dedicated employee/business code** (`KRY-...`) |
| Nama Karyawan | ✅ | `wim_users.name` |
| Nama Depo | ✅ | `wim_user_meta.depot_id` / `depot_ids` |
| Username | ✅ | `wim_users.email` (used as login); **no separate username** |
| Role | ✅ | `wim_users.role` |
| Status (Aktif/Non Aktif) | ✅ | `wim_users.status` |
| Jenis Sales (SPG, etc.) | ✅ | `wim_user_meta.jenis_sales` |
| Tanggal/Waktu Dibuat/Update | ⚠️ | `created_at`/`updated_at` on users only |

### Vehicle (Data_Kendaraan) — vs DB
| Goovi field | In WIM? | Notes |
|---|---|---|
| **Tabla kendaraan completa** | ❌ **MISSING** | **No `wim_vehicles` table exists.** `wim_user_meta.vehicle_id` references a table that doesn't exist. |
| Kode | ❌ | no vehicle code |
| PlatNo | ❌ | no plate field |
| Jenis, Kubikasi, BeratJenis | ❌ | no vehicle type/volume/weight |
| Depo | ❌ | no vehicle↔depot link |

This connects directly to your **Fleetbase** plan (PHASE-2 doc: "vehicle dimensions & product dimensions → show vehicle capacity full/not-full"). The vehicle data model was planned but never built.

---

## 3. What's missing from the database (action items)

**Critical / gaps to fully match Goovi+KlikOrder:**

1. **No vehicle table.** Need `wim_vehicles` (kode, plat_no, jenis, kubikasi, berat_jenis, depot_id) — `wim_user_meta.vehicle_id` currently dangles. (Already flagged as deferred in PHASE-2 → Fleetbase.)
2. **No store-code / employee-code columns.** Goovi uses business codes (`PLG-244-9760...`, `KRY-D-WIM-...`). WIM uses internal UUIDs only. Add `store_code`, `employee_code` for human-readable identifiers.
3. **`phone_verified` / `status_verif_hp`** on stores — Goovi tracks "Status Verif No HP" (belum_verif / verified); WIM has no phone-verification field.
4. **`updated_at` on `wim_stores`** — Goovi records update timestamps; WIM stores has only `created_at`.

**Nice-to-have / audit parity:**
5. Separate `tanggal_dibuat`/`waktu_dibuat` vs single `created_at` — minor; WIM's single timestamp is functionally equivalent.
6. `kode_depo` already exists on `wim_depots` (depot code) — matches Goovi's depot codes; no work needed there.
7. `username` as a distinct field (Goovi has it) — WIM uses email; acceptable but could add an alias if needed.

## 4. Recommendation
- **Store & employee codes**: add nullable `store_code` / `employee_code` columns (additive) and backfill from the exports if you want Goovi parity.
- **Phone verification**: add `phone_verified VARCHAR` to `wim_stores`.
- **Vehicle model**: create `wim_vehicles` per the PHASE-2/Fleetbase plan (kode, plat_no, jenis, kubikasi, berat_jenis, depot_id) — this is the highest-value gap since `vehicle_id` already points to it.
- **Timestamps**: add `updated_at` to `wim_stores`.

No destructive changes; all additive and reversible.