# User Roles & Sales Status — Auto-Classification, Manager Role, Delivery Badge, Form Dropdowns

> **Status:** PLAN → implement → migrate → verify · **Date:** 2026-09-12

## Goal
1. **Auto-classify roles by name** in existing users:
   - Name contains **`kepala depo` | `kepala gudang` | `gudang`** → role **`depo_admin`** (Admin Depo).
   - Name contains **`PIC` | `coordinator`** → role **`manager`**.
   - **`regional_manager`** accounts → role **`manager`** (no more `regional_manager`).
2. **`delivery` role** gets a **blue background + white text** badge (was unstyled).
3. **Add-user form**: role becomes a full **dropdown** (incl. `manager`, `delivery`) and **Sales status** (`TO | SPG | SPC | SMD | NA`) becomes a **dropdown** (was missing/empty).
4. Update DB documentation.

## Data model notes
- `wim_users.role` is a free string (no CHECK constraint) — safe to set `manager`/`depo_admin`.
- `wim_user_meta.jenis_sales` currently holds values incl. `TO, SPG, SPC, SMD, SA, manager, sales, Kanvaser Non SJ` (imported from Goovi). We standardize the **input UI** to `TO | SPG | SPC | SMD | NA`; existing stored values are left untouched.
- New role `manager` must be added to the admin `ROLE_LEVEL` map (admin-server.py) so manager accounts can still log in to the panel (level 3, same as former regional_manager …, actually = depo_admin-tier access).

## Changes

### DB (migration `14-user-role-normalize.sql`, applied live, reversible)
```sql
-- 1) kepala depo / kepala gudang / gudang in name -> depo_admin
UPDATE wim_users SET role='depo_admin'
WHERE deleted_at IS NULL AND role != 'super_admin'
  AND (LOWER(name) LIKE '%kepala depo%' OR LOWER(name) LIKE '%kepala gudang%' OR LOWER(name) LIKE '%gudang%');
-- 2) PIC / coordinator in name -> manager
UPDATE wim_users SET role='manager'
WHERE deleted_at IS NULL AND role != 'super_admin'
  AND (LOWER(name) LIKE '%pic%' OR LOWER(name) LIKE '%coordinator%');
-- 3) regional_manager -> manager
UPDATE wim_users SET role='manager' WHERE deleted_at IS NULL AND role='regional_manager';
```
Order: gudang→depo_admin first, then pic/manager, then regional→manager (no name overlaps gudang+pic today; a conflict would resolve oddly but none exists — noted).

### Code
- `admin/admin-server.py`: `ROLE_LEVEL` add `'manager': 3` (same level as former regional_manager / depo_admin-tier). Keep `'regional_manager': 3` for safety during rollback.
- `admin/users.html`:
  - Role badge: add `.role-manager`, `.role-delivery` CSS. `delivery` = **blue bg + white text** (`#0984e3`); `manager` = distinct violet (`#7c3aed`).
  - `roleBadge()` label map: add `manager: 'Manager'`, `delivery: 'Delivery'`.
  - Add-user form: role `<select>` gains `Manager`, `Delivery`; `Regional Manager` removed (replaced by Manager).
  - **New** "Sales Status" `<select id="newJenis">` with `TO | SPG | SPC | SMD | NA` (+ empty default).
  - `submitUser()` includes `jenis_sales` in the POST body.
  - `toggleForm()` reset clears the new field.
  - Filter role dropdown gains `manager`, `delivery`; remove `regional_manager`.

### Docs
- `docs/DATABASE-ERD.md` + `docs/KLIKORDER-PROMO-COMPARISON-AND-IMPORT.md`: update role vocabulary (roles now `super_admin | head_of_sales | manager | depo_admin | delivery | sales`), note `jenis_sales` enum values.

## 4. User management page refinements (round 2)
- **Depo shows NAME not ID**: `wim_users` list now LEFT JOINs `wim_depots` (middleware) and the admin passes `depot_name` through; the "Depo" table column and detail popup render the depot **name** (falls back to ID if unused).
- **Add-user form has a Depo dropdown** (`/api/admin/depots`), wired into POST (`depot_id`) + reset.
- **Click-to-edit popup**: clicking a user row opens a detail popup (name/email/role/sales-status/depo/status). An **"✏️ Edit User"** button swaps to an edit form (Nama, Email, Role dropdown, Sales Status dropdown, Depo dropdown, No. HP, Status) with **💾 Simpan** → `PATCH /api/admin/users/:id` (new admin-server route proxying middleware `/api/users/:id`), then reloads.
- Verified live end-to-end: edit changed name/role(sales→depo_admin)/jenis(TO→SPC)/depot(1→3→"Depo WIM Jakarta Barat")/phone and persisted (GET confirmed).

## 5. User management — filters, edit toggle, all-data edit + user flows

### List filters (toolbar)
Admin can filter the user list by **Role**, **Sales Type** (TO/SPG/SPC/SMD/NA), **Depo** (name), and **Status** (Aktif/Nonaktif). Implemented as backend query params on the middleware (`role`, `jenis_sales`, `depot_id`, `status`) + admin passthrough; combined filters work (AND).

### Edit menu — active/inactive toggle + all data editable
The edit form (opened from a row → "✏️ Edit User") now has a **Status Akun** checkbox toggle (Aktif/Nonaktif) that maps to `wim_users.status`, replacing the old select. Every user-associated field on the profile is editable: Nama, Email, Role, Sales Type, Depo, No. HP, NIK, NPWP, Nama NPWP, Kendaraan, Kode Pos, Kecamatan, Kelurahan, Status. All persist via `PATCH /api/admin/users/:id` (name/phone/status on `wim_users`; the rest on `wim_user_meta`).

### User flow — Making a new user
1. Admin opens **User Management** → clicks **＋ Tambah User**.
2. Fills **Nama**, **Email**, **Password**, picks **Role**, **Sales Type** (TO/SPG/SPC/SMD/NA), and optionally a **Depo** (by name).
3. Clicks **💾 Simpan** → `POST /api/admin/users` creates the account (`wim_users` + `wim_user_meta`); list reloads; new user appears with role badge + depot name.
4. New user defaults to **active** status.

### User flow — Editing an existing user
1. Admin opens **User Management**, optionally narrows with filters (Role/Sales Type/Depo/Status).
2. Clicks any **user row** → **detail popup** shows name/email/role badge/sales-type/depo/status.
3. Clicks **✏️ Edit User** → edit form pre-filled with all current profile data.
4. Changes any fields; toggles **Status Akun** to Aktif/Nonaktif if needed.
5. Clicks **💾 Simpan** → `PATCH /api/admin/users/:id` updates `wim_users` + `wim_user_meta`; popup closes with success toast; list reloads reflecting the change.

## Rollback
`UPDATE wim_users SET role='sales' WHERE role='depo_admin' AND id IN (<original sales ids>)` … (or restore from pre-migration snapshot). Code ROLE_LEVEL entry / CSS / form fields revert via git.

## Verify
- Count roles before/after; confirm depo_admin count rose (~32), one manager (QA Region Mgr); delivery untouched (49).
- Browser admin panel: badges colored; add form shows role + sales-status dropdowns; POST round-trips `jenis_sales`.