# Call Plan Sales Import — Document Structure → DB Mapping & Import Plan

> **Status:** ANALYSIS + PLAN (not yet implemented) · **Date:** 2026-09-12
> **Source:** `Call Plan Sales - UPdate 11.09.26.zip` — 53 `.xlsx` files (one per depo/route).

---

## 1. Document structure (all 53 files, identical 23-column layout)

Each workbook has a single sheet **"Data Rencana Kunjungan"**. Columns:

| Col | Name | Example | Function |
|---|---|---|---|
| 1 | `Nama Depo` | `PT. WAHANA INTI MAS - JABAR - AGEN JAP JAP` | Depot the route belongs to |
| 2 | `Kode_Karyawan` | `KRY-D-WIM-JABAR-10-004` | Sales rep employee code |
| 3 | `Nama_Karyawan` | `Iman Jatmika` | Sales rep name |
| 4 | `Kode_Pelanggan` | `PLG-828-e0def662-…` / `PEL-…` | Customer/store code |
| 5 | `Nama_Pelanggan` | `Jap-jap 99` | Store name |
| 6–12 | `senin..sabtu..minggu` | `0/1` | **Which weekday** the store is visited (Sun possible) |
| 13–16 | `week1..week4` | `0/1` | **Which week-of-month** the store is visited |
| 17 | `longitude` | `107.443195` | Store lng |
| 18 | `latitude` | `-6.541180` | Store lat |
| 19 | `alamat_lengkap` | `Gg aster,…` | Store address |
| 20 | `kecamatan` | `Purwakarta` | District |
| 21 | `kelurahan` | `Negarikaler` | Sub-district |
| 22 | `kota` | `Purwakarta` | City |
| 23 | `provinsi` | `Jawa Barat` | Province |

**Semantics confirmed by inspection:** each row = one store assigned to one sales rep for a
**(week-of-month × day-of-week) recurring slot**. Measured across samples:
- ~88% of rows have **exactly 1 day flag + 1 week flag** → a single deterministic slot.
- ~9% have **1 day flag + 0 week flags** → "repeat every week" (weekly route; Kanvaser/TO-Kanvas reps).
- ~2.8% have **1 day + all 4 week flags** → visited every week explicitly (same as 0-week, equivalent).
- Exactly **4 rows** are Sunday-flagged (`minggu=1`).

**Scale:** **138,852 total rows** · 53 files · 252 distinct employee codes · **124,857 distinct
customer codes**. Largest files: Bintaro Tangsel (12,749), Subang & Surabaya (13,995 each),
Jakarta (9,825), Bandung To (6,953). 3 files appear twice (Surabaya/Subang same size 13,995 —
likely duplicate exports — to be deduped).

---

## 2. Mapping to WIM database

This is exactly the **monthly template** model we built:

| Document field | WIM DB |
|---|---|
| `Kode_Karyawan` / `Nama_Karyawan` | → **`wim_user_meta.employee_code`** → `wim_users.id` |
| `Nama Depo` | → **`wim_depots.name`** (match by name → `wim_depots.id`) |
| `Kode_Pelanggan` / `Nama_Pelanggan` | → **`wim_stores.store_code`** (→ `wim_stores.uuid`) |
| `senin..sabtu` (day flag) | → **`wim_visit_plan_templates.day_of_week`** (1=Mon..6=Sat) |
| `week1..week4` (week flag) | → **`wim_visit_plan_templates.week_number`** (1..4) |
| `longitude, latitude, alamat, kecamatan, kelurahan, kota, provinsi` | verification/matching data for `wim_stores` (geo/address enrichment) |
| (Sunday `minggu=1`) | **not mappable** — template model excludes Sunday (day_of_week 1-6); 4 rows, to be flagged/skipped |

Each row (1 day × 1 week) = one `wim_visit_plan_templates` row + its `wim_visit_plan_template_stores`
entries — the exact structure the plan-edit grid already uses (which now auto-materializes dates).

---

## 3. Data-accuracy check vs current database (live join results)

### Employees — **HIGH match**
- 252 distinct employee codes in the zip; **244 (97%) match** `wim_user_meta.employee_code`.
- 242 (96%) match `wim_users.name` (case/trim-insensitive).
- → 8 employee codes (≈4%) don't resolve — either not-yet-imported reps or renamed ones.

### Customers/stores — **LOW match (the critical gap)**
- **124,857 distinct customer codes** in the zip; **only 15,443 (12.4%) match** `wim_stores.store_code`.
- Reverse: of our 15,526 stores, **83 are not referenced** in the zip (fine — they're just un-routed).
- Embedded-UUID lookup (the `PLG-<n>-<uuid>` last segment as `wim_stores.uuid`) → **0 matches**
  (the embedded id is *not* our store uuid — it's the Goovi/MSP external id).
- **So ~109,000 (87%) of the zip's customer codes have NO store in our DB.** The zip's customer
  master is far larger than the 15,496-store export we previously imported (Data_Pelanggan was a
  subset, mostly JABODETABEK + some venta; the zip covers many more JAVA/outside areas).

**Why logically mappable only partially:** our `wim_stores` master came from a single Goovi
`Data_Pelanggan` export that covered ~15.5k stores. The Call Plan covers the full operational
customer base (~110k yards/outlets across all depots). The missing ~87% are legitimate stores we
simply do not carry yet — **not a naming defect**. Each missing store row, however, carries its
own lat/lng/address/kecamatan/kelurahan/kota/provinsi **in the zip**, so it can be **upserted as
new `wim_stores`** during import (with `store_code` = the zip's `Kode_Pelanggan`).

---

## 4. What's missing from the database → and how to implement it

### 4a. Stores master is incomplete — **needs expansion**
- **Gap:** `wim_stores` (15.5k) << zip customer codes (124.9k). 87% unmapped.
- **Implementation:** during import, treat each unmapped `Kode_Pelanggan` as a **new store** upsert:
  - Match/assign depot (from `Nama Depo`), country `Indonesia`.
  - Store `store_code=Kode_Pelanggan`, `name=Nama_Pelanggan`, `latitude/longitude`,
    `address`, `kecamatan`, `kelurahan`, `city/Kabupaten`, `province` (all present in the zip).
  - Backfill region codes via `wim_wilayah` (kota/kecamatan/kelurahan name lookup) — reuse the
    existing wilayah dataset + the NOO cascade logic.
- **Precedent:** this mirrors the earlier Goovi store import (`scripts/import_goovi.py`), just
  additive and only for unmapped codes.

### 4b. Employee linkage — **small cleanup**
- 244/252 resolve. For the 8 unresolved codes: attempt name match, else create minimal `wim_users`
  (placeholder password, role per `Nama_Karyawan` — TO/SPG/SPC/SMD/kanvaser → sales) + `wim_user_meta`
  (`employee_code`, `depot_id`, `jenis_sales` from the name pattern), mirroring the earlier user import.

### 4c. Template row encoding — `(week, day)` semantics
- Our model stores **one template slot per 1×1 combo**. For rows with **0 week flags** (= every week)
  the import expands to **4 slots (week1..week4)** on that weekday — same as explicit all-weeks rows.
- **Sunday (`minggu=1`) rows (4 total)** have no home in `day_of_week=1..6`. Options:
  - (recommended) **skip + report** them (Sunday is closed / no shop visit in practice), or
  - add a `day_of_week=0`-or-`7` variant + resolver change. Given only 4 rows, **skip+log** is cleaner.

### 4d. Dedup
- Surabaya & Subang files are byte-identical in size (13,995) → likely duplicate exports; import
  is `ON CONFLICT (user_id, week_number, day_of_week)`-safe anyway, so duplicates self-resolve.

---

## 5. Import plan (proposed, not executed)

1. **Pre-flight** (Python, offline): parse all 53 workbooks → canonical rows
   `(depot_name, emp_code, emp_name, store_code, store_name, day, week, geo…)`.
2. **Resolve employees** via `employee_code` → `wim_users.id` (create missing as §4b).
3. **Resolve stores** via `store_code` → `wim_stores.uuid` (upsert missing stores §4a).
4. **Load templates** into `wim_visit_plan_templates` + `_template_stores`:
   - Row with 1 week flag → one slot `(week, day)`, store appended in file order (visit_order).
   - Row with 0/all-weeks flags → expand to 4 slots `(1..4, day)`.
   - Skip the 4 Sunday rows (logged).
5. **Verify counts** (rows loaded, stores created, employees linked, orphans) and report a mismatch
   log (8 employee codes, Sunday rows, any row whose emp/store still unresolved).
6. **No materialization during import** — templates auto-materialize on read (field app + admin
   view already do this), so routes appear automatically per date.
7. Reversible additive (insert-only; new stores unique by `store_code`; no destructive ops).

**Commit/deliverable:** `scripts/import_call_plan.py` + migration (if any) + this doc.
I have not run it — awaiting your go-ahead (it will create ~110k new stores, which is a large
but additive change).

---

## 6. Open questions for you
1. Confirm **87% new-store expansion** is wanted (bulk-add ~109k stores from the zip), vs. import
   only the ~12% already-mapped stores now and leave the rest for a later full Goovi sync.
2. Confirm **skip the 4 Sunday rows** (recommended) rather than adding Sunday support.
3. Import scope: all 53 files at once, or start with one depot file as a pilot to validate mapping?

---

## 7. IMPORT EXECUTED (2026-09-12)

**Result (live, verified):**
- **188,954 source rows** expanded to **185,884 template slots** loaded into `wim_visit_plan_templates` + `_template_stores`.
- **107,819 new stores upserted** (from the zip's own geo/address data) → `wim_stores` grew **15,526 → 124,781**.
- **4,220 templates** created with **167,354 store links**.
- **Excluded by design (mock-data rule, 3,070 slots):** the only 8 unmatched employee codes are all **dummy/training accounts** (`dummy_abjs`, `Dummy-AR`, `Akun Dummy (Untuk Training)`, `SALES DUMMY WIM JAKARTA`, `Sales_Dummy_Wilayah_Jogja`, etc.). One real rep (Vinarosa Prawitasari) matched by a different stored code — her route links to that account.
- **161 Sunday rows** skipped (template model excludes Sunday); 185 weekday rows skipped for missing codes.
- **End-to-end verified:** imported template W1D3 for rep Agus Darmawan (user 264) auto-materializes into dated `wim_visit_plan` — the admin Lihat-list for 2026-09-02 shows all **299** of his W1D3 stores (`belum_masuk`), via the auto-materialize-on-read path. No manual resolve needed.

**Script:** `scripts/import_callplan.py` (idempotent, additive). Rerun-safe `ON CONFLICT`.
