# WIM Online — Database Mapping Document

> **Purpose:** Complete schema reference for the WIM Online SFA (Sales Force Automation) platform.
> **Database:** PostgreSQL `wim_sfa` (standalone, no Fleetbase dependency)
> **Status:** Design document — implement tables in this exact order.
> **Future integration:** Sync adapters will push relevant data to Fleetbase (delivery/driver tracking) and an order-taking app that posts to Odoo (sales/accounting). WIM Online is the canonical source; integrations are optional layers.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Table Index](#2-table-index)
3. [Table Definitions](#3-table-definitions)
4. [Entity Relationship Diagram](#4-entity-relationship-diagram)
5. [Column Patterns](#5-column-patterns)
6. [Auth & Security](#6-auth--security)
7. [SFA Core (Sales Visit)](#7-sfa-core-sales-visit)
8. [Order Management](#8-order-management)
9. [Inventory & Stock](#9-inventory--stock)
10. [Promo Engine](#10-promo-engine)
11. [HR & Attendance](#11-hr--attendance)
12. [Depot & Territory](#12-depot--territory)
13. [Admin & RBAC](#13-admin--rbac)
14. [NOO (New Outlet Opening)](#14-noo-new-outlet-opening)
15. [Reporting & Analytics](#15-reporting--analytics)
16. [Sync & Integration Queue](#16-sync--integration-queue)
17. [Audit & Logging](#17-audit--logging)
18. [App Configuration](#18-app-configuration)
19. [Implementation Order](#19-implementation-order)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    WIM Online SFA Platform                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐    ┌──────────────────────┐           │
│  │  Sales App        │    │  Admin Panel          │           │
│  │  (mobile-first)   │    │  (desktop)            │           │
│  │  port 8080        │    │  port 8081            │           │
│  └────────┬─────────┘    └──────────┬─────────────┘           │
│           │                          │                         │
│           └──────────┬──────────────┘                         │
│                      │ HTTP JSON API                          │
│                      ▼                                         │
│           ┌──────────────────────┐                             │
│           │   serve.py           │   ← Python http.server      │
│           │   middleware layer   │      (backend API)          │
│           └──────────┬───────────┘                             │
│                      │ psycopg2                                │
│                      ▼                                         │
│           ┌──────────────────────┐                             │
│           │   PostgreSQL          │                             │
│           │   wim_sfa DB         │   ← SINGLE SOURCE OF TRUTH  │
│           └──────────────────────┘                             │
│                                                              │
│  ───────── Future Sync Layer ────────────────────────────    │
│           ┌────────────────────────────────────────┐          │
│           │  wim_sync_queue → Fleetbase API        │          │
│           │                  → Odoo API             │          │
│           │                  → Warehouse API        │          │
│           └────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

### 1.1 Key Design Decisions

| Decision | Rule |
|----------|------|
| **Single DB** | PostgreSQL `wim_sfa` is the canonical source. No dual-write. |
| **No Fleetbase dependency** | All tables self-contained. Future sync via `wim_sync_queue`. |
| **UUIDs for public IDs** | `gen_random_uuid()` for all entities exposed externally. Integer PKs internal only. |
| **JSONB for flexible data** | Order items, promo conditions/rewards, audit details, sync payloads. |
| **Soft delete** | `deleted_at` timestamp on all major entities. |
| **Timestamps** | `created_at` + `updated_at` on all tables. `NOW()` defaults. |
| **Bahasa Indonesia** | Column names in English, but all user-facing content in Bahasa. |

---

## 2. Table Index

> **Status note (2026-09-10):** All **31** tables below exist in `deploy/db/init/01-schema.sql`
> (verified: `grep -c "^CREATE TABLE"` = 31, and 31 tables confirmed in the live `wim_sfa` DB).
> Earlier versions of this file listed a phantom `wim_visit_photos` (32nd) table — visit photos
> are stored **inline** in `wim_visits.photos` (JSON array), so no separate table exists.

Total planned tables: **31**

| # | Table | Category | Purpose | Status |
|---|-------|----------|---------|--------|
| 1 | `wim_users` | Auth | User accounts (all personas) | ✅ Migrated |
| 2 | `wim_sessions` | Auth | Login sessions | ✅ Migrated |
| 3 | `wim_api_keys` | Auth | Consumer/integration keys (Bearer) | 🔴 New |
| 4 | `wim_user_meta` | Auth | Extended profile (jenis_sales, depot, vehicle) | 🔴 New |
| 5 | `wim_stores` | Core | Retail outlets | ✅ Migrated |
| 6 | `wim_store_contacts` | Core | Store owner/PIC phone/WA | 🔴 New |
| 7 | `wim_store_photos` | Core | Store photos (spanduk, banner) | 🔴 New |
| 8 | `wim_store_relations` | Core | Store-to-store chains/groups | 🔴 New |
| 9 | `wim_products` | Core | Product catalog | ✅ Migrated |
| 10 | `wim_product_prices` | Core | Price history per product | 🔴 New |
| 11 | `wim_depots` | Territory | Distribution centers + geofence | ✅ Migrated |
| 12 | `wim_depot_stores` | Territory | Depot-to-store assignments | ✅ Schema created |
| 13 | `wim_depot_products` | Territory | Depot product availability | 🔴 New |
| 14 | `wim_visit_plan` | SFA | Daily route assignments | ✅ Migrated |
| 15 | `wim_visit_plan_templates` | SFA | Reusable route cycles | 🔴 New |
| 16 | `wim_visit_plan_template_stores` | SFA | Stores per route template | 🔴 New |
| 17 | `wim_visits` | SFA | Store check-in/out records | ✅ Migrated |
| 18 | ~~`wim_visit_photos`~~ | ~~SFA~~ | ~~Per-visit photos + descriptions~~ | **REMOVED** — photos stored inline in `wim_visits.photos` |
| 19 | `wim_attendance` | HR | Daily clock-in/out | ✅ Migrated |
| 20 | `wim_orders` | Orders | Order headers | ✅ Schema created |
| 21 | `wim_order_items` | Orders | Order line items | 🔴 New |
| 22 | `wim_order_status_log` | Orders | Order status history | 🔴 New |
| 23 | `wim_stock_check` | Inventory | In-store stock recording | ✅ Migrated |
| 24 | `wim_promo` | Promo | Promo definitions | ✅ Schema created |
| 25 | `wim_promo_conditions` | Promo | Promo triggers | ✅ Schema created |
| 26 | `wim_promo_rewards` | Promo | Promo rewards | ✅ Schema created |
| 27 | `wim_promo_assignments` | Promo | Depot/store/channel promos | 🔴 New |
| 28 | `wim_admin_depot_access` | Admin | Depot-scoped RBAC | ✅ Migrated idea |
| 29 | `wim_audit_log` | System | CRUD audit trail | ✅ Schema created |
| 30 | `wim_sync_queue` | Integration | Async sync to Fleetbase/Odoo/order-app | ✅ Schema created |
| 31 | `wim_sync_log` | Integration | Append-only sync trace | 🔴 New |
| 32 | `wim_app_config` | System | Key-value application configuration | 🔴 New |

### 2.1 Legend

| Status | Meaning |
|--------|---------|
| ✅ Migrated | Data already in PostgreSQL from Fleetbase migration |
| ✅ Schema created | `CREATE TABLE` exists in migration, may be empty |
| 🔴 New | Not yet created — needs implementation |

---

## 3. Table Definitions

### 3.1 Auth & Security

#### `wim_users`
The single user table for all personas: Sales Rep, Depot Admin, Super Admin.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | Internal ID |
| `uuid` | `UUID` | `UNIQUE NOT NULL DEFAULT gen_random_uuid()` | Public-facing ID |
| `email` | `VARCHAR(255)` | `UNIQUE NOT NULL` | Login email |
| `name` | `VARCHAR(255)` | `NOT NULL` | Display name |
| `password_hash` | `TEXT` | `NOT NULL` | bcrypt hash |
| `role` | `VARCHAR(50)` | `DEFAULT 'sales'` | `sales`, `depo_admin`, `super_admin` |
| `phone` | `VARCHAR(30)` | | WhatsApp number |
| `status` | `VARCHAR(20)` | `DEFAULT 'active'` | `active`, `inactive`, `suspended` |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |
| `updated_at` | `TIMESTAMP` | `DEFAULT NOW()` | |
| `deleted_at` | `TIMESTAMP` | | Soft delete |

**Indexes:**
- `email` UNIQUE
- `uuid` UNIQUE
- `role`

#### `wim_user_meta` _(🔴 New)_
Extended profile data per user.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `user_id` | `INT` | `FK → wim_users(id)` **UNIQUE (1:1)** | One profile per user (enforced) |
| `jenis_sales` | `VARCHAR(30)` | | `TO`, `Motoris`, `SPC`, `SPG`, `Kanvaser`, `SMD` |
| `depot_id` | `INT` | `FK → wim_depots(id)` | Primary depot |
| `depot_ids` | `INT[]` | | All depots user belongs to (array for multi-depot reps) |
| `photo_url` | `TEXT` | | Profile photo |
| `vehicle_id` | `VARCHAR(50)` | | Assigned vehicle code |
| `nik` | `VARCHAR(30)` | | National ID |
| `npwp` | `VARCHAR(30)` | | Tax ID |
| `alamat` | `TEXT` | | Home address |
| `tanggal_bergabung` | `DATE` | | Join date |
| `supervisor_id` | `INT` | `FK → wim_users(id)` | Reports to |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |
| `updated_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

#### `wim_sessions`
Server-side auth sessions (HttpOnly cookie).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `VARCHAR(64)` | `PK` | Random token (hex 32 bytes) |
| `user_id` | `INT` | `FK → wim_users(id)` | |
| `expires_at` | `TIMESTAMP` | `NOT NULL` | 7 days from creation |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

#### `wim_api_keys` _(🔴 New)_
Consumer/integration API keys (for external systems pulling/inputting data via Bearer token).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `name` | `VARCHAR(100)` | `NOT NULL` | Key label (e.g. `odoo-order-app`) |
| `api_key` | `TEXT` | `NOT NULL UNIQUE` | Hashed consumer key |
| `scope` | `TEXT` | | Comma list: `orders:read`, `orders:write`, `stores:read`, `stock:read`, `sync:write`, `report:read` |
| `is_active` | `BOOLEAN` | `DEFAULT TRUE` | Revoke = set false |
| `expires_at` | `TIMESTAMP` | | Optional expiry |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |
| `last_used_at` | `TIMESTAMP` | | |

---

### 3.2 SFA Core (Sales Visit)

#### `wim_stores`
Retail outlets visited by sales reps.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `uuid` | `UUID` | `UNIQUE NOT NULL DEFAULT gen_random_uuid()` | Public ID |
| `name` | `VARCHAR(255)` | `NOT NULL` | Store name |
| `address` | `TEXT` | | Full address |
| `city` | `VARCHAR(100)` | | |
| `province` | `VARCHAR(100)` | | |
| `latitude` | `DECIMAL(10,7)` | | GPS latitude |
| `longitude` | `DECIMAL(10,7)` | | GPS longitude |
| `owner_name` | `VARCHAR(255)` | | Store owner |
| `phone` | `VARCHAR(30)` | | Phone / WA |
| `channel` | `VARCHAR(50)` | | `GT`, `MT`, `Horeka`, `Institutional` |
| `category` | `VARCHAR(100)` | | `Retail Kecil`, `Minimarket`, `Restoran`, etc. |
| `nik` | `VARCHAR(30)` | | Owner NIK (NOO field) |
| `npwp` | `VARCHAR(30)` | | Owner NPWP |
| `npwp_name` | `VARCHAR(255)` | | Name on NPWP |
| `kendaraan` | `VARCHAR(50)` | | Vehicle type for delivery |
| `kode_pos` | `VARCHAR(10)` | | |
| `kelurahan` | `VARCHAR(100)` | | |
| `kecamatan` | `VARCHAR(100)` | | |
| `status` | `VARCHAR(20)` | `DEFAULT 'active'` | `active`, `inactive`, `closed` |
| `meta` | `JSONB` | | Flexible: extra fields, store group, chain name |
| `fleetbase_place_uuid` | `UUID` | | Future: maps to Fleetbase Place |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |
| `deleted_at` | `TIMESTAMP` | | |

**Indexes:**
- `uuid` UNIQUE
- `city, channel, category` (for filtering)
- `latitude, longitude` (for geofence queries)

#### `wim_store_contacts` _(🔴 New)_
Additional contacts per store (for multi-PIC stores).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `store_id` | `INT` | `FK → wim_stores(id)` | |
| `name` | `VARCHAR(255)` | `NOT NULL` | Contact person name |
| `phone` | `VARCHAR(30)` | `NOT NULL` | Phone / WA |
| `role` | `VARCHAR(50)` | | `owner`, `manager`, `staff`, `gudang` |
| `is_primary` | `BOOLEAN` | `DEFAULT FALSE` | Primary contact for OTP |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

#### `wim_store_photos` _(🔴 New)_
Per-visit store photos with metadata.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `visit_id` | `INT` | `FK → wim_visits(id)` | |
| `store_id` | `INT` | `FK → wim_stores(id)` | |
| `photo_data` | `TEXT` | `NOT NULL` | base64 JPEG (compressed 800px) |
| `description` | `TEXT` | | Per-photo keterangan |
| `photo_type` | `VARCHAR(30)` | | `spanduk`, `banner`, `display`, `interior`, `exterior` |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

#### `wim_store_relations` _(🔴 New)_
Group/chain relationships between stores (same owner, same chain).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `store_id` | `INT` | `FK → wim_stores(id)` | |
| `related_store_id` | `INT` | `FK → wim_stores(id)` | |
| `relation_type` | `VARCHAR(50)` | | `chain`, `same_owner`, `nearby` |
| `notes` | `TEXT` | | |

---

### 3.3 Products & Pricing

#### `wim_products`
Product catalog.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `uuid` | `UUID` | `UNIQUE NOT NULL DEFAULT gen_random_uuid()` | |
| `sku` | `VARCHAR(50)` | `UNIQUE NOT NULL` | Product SKU (e.g. `SQA-550-K24`) |
| `name` | `VARCHAR(255)` | `NOT NULL` | Product name |
| `price` | `DECIMAL(15,2)` | `DEFAULT 0` | Current selling price |
| `brand` | `VARCHAR(100)` | | `Sanqua`, `Levonte`, `Batavia`, `Aqua` |
| `category` | `VARCHAR(100)` | | Product category |
| `unit` | `VARCHAR(30)` | `DEFAULT 'karton'` | `karton`, `botol`, `pack`, `pcs` |
| `qty_per_unit` | `INT` | `DEFAULT 1` | Bottles per carton |
| `weight` | `DECIMAL(10,2)` | `DEFAULT 0` | |
| `weight_unit` | `VARCHAR(10)` | `DEFAULT 'pcs'` | |
| `description` | `TEXT` | | |
| `is_active` | `BOOLEAN` | `DEFAULT TRUE` | |
| `meta` | `JSONB` | | Flexible extra fields |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |
| `deleted_at` | `TIMESTAMP` | | |

**Indexes:**
- `sku` UNIQUE
- `uuid` UNIQUE
- `brand`
- `category`

#### `wim_product_prices` _(🔴 New)_
Price change history (tracks all price changes for auditing).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `product_id` | `INT` | `FK → wim_products(id)` | |
| `price` | `DECIMAL(15,2)` | `NOT NULL` | |
| `effective_date` | `DATE` | `NOT NULL` | When this price takes effect |
| `set_by` | `INT` | `FK → wim_users(id)` | Who set it |
| `notes` | `TEXT` | | Reason for change |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

---

### 3.4 Depot & Territory

#### `wim_depots`
Distribution centers / depots.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `name` | `VARCHAR(255)` | `NOT NULL` | Depot name |
| `address` | `TEXT` | | Physical address |
| `latitude` | `DECIMAL(10,7)` | | GPS for geofence center |
| `longitude` | `DECIMAL(10,7)` | | |
| `radius_m` | `INT` | `DEFAULT 50` | Geofence radius in meters |
| `kode_depo` | `VARCHAR(20)` | | Depot code |
| `is_active` | `BOOLEAN` | `DEFAULT TRUE` | |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

#### `wim_depot_stores`
Which stores belong to which depot.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `depot_id` | `INT` | `FK → wim_depots(id)` | |
| `store_uuid` | `UUID` | `NOT NULL` | References `wim_stores.uuid` |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

**Index:** `depot_id, store_uuid` UNIQUE

#### `wim_depot_products` _(🔴 New)_
Which products each depot is authorized to sell. Allows depot-specific brand/category filtering.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `depot_id` | `INT` | `FK → wim_depots(id)` | |
| `product_id` | `INT` | `FK → wim_products(id)` | |
| `is_active` | `BOOLEAN` | `DEFAULT TRUE` | |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

**Index:** `depot_id, product_id` UNIQUE

---

### 3.5 Visit Plan & Route Management

#### `wim_visit_plan`
Daily store assignments for each sales rep.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `user_id` | `INT` | `FK → wim_users(id)` | Sales rep |
| `place_uuid` | `UUID` | `NOT NULL` | Store UUID |
| `visit_date` | `DATE` | `NOT NULL` | Scheduled date |
| `source` | `VARCHAR(20)` | `DEFAULT 'route'` | `route`, `luar_rute` |
| `visit_order` | `INT` | `DEFAULT 0` | Sort order for route (1, 2, 3...) |
| `seq_no` | `INT` | `DEFAULT 0` | Numbered position in a day's kunjungan list (drag-drop editor) |
| `status` | `VARCHAR(20)` | `DEFAULT 'pending'` | `pending`, `visited`, `skipped` |
| `notes` | `TEXT` | | Pre-visit notes |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

**Indexes:**
- `user_id, visit_date` (daily plan lookup)
- `place_uuid, visit_date` (prevent duplicate assignments)
- `user_id, visit_date, source` (filter by route/luar_rute)

#### `wim_visit_plan_templates` _(🔴 New)_
Reusable 4-week cycle route templates. Each depot has up to 20 templates (4 weeks × 5 days).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `depot_id` | `INT` | `FK → wim_depots(id)` | |
| `user_id` | `INT` | `FK → wim_users(id)` | Sales rep |
| `nama_template` | `VARCHAR(100)` | | e.g. "Minggu 1 Senin" |
| `week_number` | `INT` | | 1–4 |
| `day_of_week` | `INT` | | 1 (Mon) – 5 (Fri) |
| `is_active` | `BOOLEAN` | `DEFAULT TRUE` | |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

#### `wim_visit_plan_template_stores` _(🔴 New)_
Stores in each template.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `template_id` | `INT` | `FK → wim_visit_plan_templates(id)` | |
| `store_uuid` | `UUID` | `NOT NULL` | |
| `visit_order` | `INT` | `DEFAULT 0` | |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

---

### 3.6 Visits (Check-in/Check-out)

#### `wim_visits`
The core visit record. Every store visit = one row.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `user_id` | `INT` | `FK → wim_users(id)` | Sales rep |
| `place_uuid` | `UUID` | `NOT NULL` | Store UUID |
| `place_name` | `VARCHAR(255)` | | Denormalized store name (for history) |
| `checkin_at` | `TIMESTAMP` | | When check-in happened |
| `checkout_at` | `TIMESTAMP` | | When check-out happened |
| `duration_seconds` | `INT` | | Duration in seconds |
| `status` | `VARCHAR(30)` | `DEFAULT 'checkin'` | `checkin`, `visited`, `no_order` |
| `photos` | `TEXT` | `DEFAULT '[]'` | JSON array of {url, desc} — "foto tambahan" (merchandise) |
| `checkin_photo` | `TEXT` | | The check-in SELFIE (base64 data URL), separate from `photos` |
| `notes` | `TEXT` | | Visit notes / no-order reason (alasan tidak order) |
| `location_lat` | `DECIMAL(10,7)` | | GPS at check-in |
| `location_lng` | `DECIMAL(10,7)` | | |
| `source` | `VARCHAR(20)` | | `route`, `luar_rute` |
| `geofence_status` | `VARCHAR(20)` | | `in_depot`, `outside` |
| `depot_id` | `INT` | `FK → wim_depots(id)` | Nearest depot |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

**Indexes:**
- `user_id, checkin_at` (daily visit history)
- `place_uuid, checkout_at IS NULL` (active visit lookup)
- `user_id, checkout_at IS NULL` (active visit per user)

---

### 3.7 HR & Attendance

#### `wim_attendance`
Daily clock-in/clock-out records.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `user_id` | `INT` | `FK → wim_users(id)` | |
| `date` | `DATE` | `NOT NULL` | |
| `clock_in` | `VARCHAR(10)` | | HH:MM format |
| `clock_out` | `VARCHAR(10)` | | HH:MM format |
| `clock_in_photo` | `TEXT` | | Base64 JPEG (selfie) |
| `clock_out_photo` | `TEXT` | | Base64 JPEG (selfie) |
| `duration` | `VARCHAR(20)` | | e.g. "9j 30m" |
| `location_lat` | `DECIMAL(10,7)` | GPS at clock-in |
| `location_lng` | `DECIMAL(10,7)` | | |
| `geofence_status` | `VARCHAR(20)` | | `in_depot`, `outside` |
| `depot_id` | `INT` | `FK → wim_depots(id)` | |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

**Index:** `user_id, date` UNIQUE

---

### 3.8 Order Management

#### `wim_orders`
Order records. Replaces Fleetbase orders as the canonical source.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `uuid` | `UUID` | `UNIQUE NOT NULL DEFAULT gen_random_uuid()` | Public order ID |
| `user_id` | `INT` | `FK → wim_users(id)` | Sales rep who created |
| `store_id` | `INT` | `FK → wim_stores(id)` | Destination store |
| `store_uuid` | `UUID` | | Store UUID (consistent with rest of system) |
| `visit_id` | `INT` | `FK → wim_visits(id)` | Linked visit |
| `order_ref` | `VARCHAR(30)` | | Human-readable order number (e.g. `WIM-20260909-001`) |
| `status` | `VARCHAR(30)` | `DEFAULT 'pending'` | `pending`, `verified`, `on_hold`, `processed`, `delivered`, `cancelled`, `no_order` |
| `total` | `DECIMAL(15,2)` | `DEFAULT 0` | Grand total |
| `payment_method` | `VARCHAR(30)` | `DEFAULT 'cod'` | `cod` |
| `notes` | `TEXT` | | Order notes |
| `source` | `VARCHAR(20)` | `DEFAULT 'route'` | `route`, `luar_rute` |
| `off_route_reason` | `TEXT` | | Required if `source='luar_rute'` |
| `promos_applied` | `JSONB` | `DEFAULT '[]'::jsonb` | Array of {promo_id, promo_ref, discount_amount} |
| `verification_status` | `VARCHAR(30)` | `DEFAULT 'pending'` | Order verification lifecycle (QR/barcode) |
| `sales_channel` | `VARCHAR(30)` | `DEFAULT 'app'` | Source channel |
| `verified_at` | `TIMESTAMP` | | When QR/barcode scanned |
| `synced_to_fleetbase` | `BOOLEAN` | `DEFAULT FALSE` | Future: sync flag |
| `fleetbase_order_uuid` | `UUID` | | Future: maps to Fleetbase Order |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |
| `updated_at` | `TIMESTAMP` | `DEFAULT NOW()` | |
| `deleted_at` | `TIMESTAMP` | | |

**Indexes:**
- `uuid` UNIQUE
- `user_id, created_at` (rep's order history)
- `store_id, created_at` (store's order history)
- `visit_id` UNIQUE (one order per visit)
- `status`

#### `wim_order_items`
Line items for each order.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `order_id` | `INT` | `FK → wim_orders(id)` | |
| `product_id` | `INT` | `FK → wim_products(id)` | |
| `product_name` | `VARCHAR(255)` | | Denormalized |
| `product_sku` | `VARCHAR(50)` | | Denormalized |
| `quantity` | `INT` | `NOT NULL` | |
| `unit_price` | `DECIMAL(15,2)` | `NOT NULL` | Price at time of order |
| `total_price` | `DECIMAL(15,2)` | `NOT NULL` | quantity × unit_price |
| `is_bonus` | `BOOLEAN` | `DEFAULT FALSE` | Free item from promo |
| `promo_ref` | `VARCHAR(50)` | | Which promo gave this bonus |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

**Index:** `order_id`

#### `wim_order_status_log` _(🔴 New)_
Audit trail for order status changes.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `order_id` | `INT` | `FK → wim_orders(id)` | |
| `from_status` | `VARCHAR(30)` | | |
| `to_status` | `VARCHAR(30)` | `NOT NULL` | |
| `changed_by` | `INT` | `FK → wim_users(id)` | |
| `notes` | `TEXT` | | |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

---

### 3.9 Inventory & Stock

#### `wim_stock_check`
Per-visit stock recording at store.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `user_id` | `INT` | `FK → wim_users(id)` | |
| `visit_id` | `INT` | `FK → wim_visits(id)` | |
| `place_uuid` | `UUID` | `NOT NULL` | Store UUID |
| `product_id` | `INT` | `FK → wim_products(id)` | |
| `sku` | `VARCHAR(50)` | `NOT NULL` | |
| `qty` | `INT` | `DEFAULT 0` | Stock counted |
| `previous_stock` | `INT` | `DEFAULT 0` | Last known stock from previous visit |
| `last_order_qty` | `INT` | `DEFAULT 0` | Qty from last order to this store |
| `checked_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

**Indexes:**
- `visit_id` (stock checks in one visit)
- `place_uuid, sku` DESC `checked_at` (last stock per store per SKU)

---

### 3.10 Promo Engine

#### `wim_promo`
Promo program definitions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `promo_ref` | `VARCHAR(50)` | `UNIQUE NOT NULL` | Human-readable reference |
| `nama` | `VARCHAR(255)` | `NOT NULL` | Promo name |
| `jenis` | `VARCHAR(30)` | `NOT NULL` | `bundling` (buy-N → bonus SKU), `diskon` (multi-SKU mix → fixed IDR). Legacy: `strata`, `bonus` |
| `status` | `VARCHAR(20)` | `DEFAULT 'active'` | `active`, `inactive`, `archived` |
| `priority` | `INT` | `DEFAULT 0` | Higher = applied first |
| `stackable` | `BOOLEAN` | `DEFAULT FALSE` | Can combine with other promos |
| `region_id` | `INT` | `FK → wim_regions(id)` | Promo is scoped to this region; NULL = all regions |
| `periode_start` | `DATE` | | |
| `periode_end` | `DATE` | | |
| `min_transaction_amount` | `DECIMAL(15,2)` | | Minimum order total to qualify |
| `max_discount_amount` | `DECIMAL(15,2)` | | Cap on discount |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |
| `deleted_at` | `TIMESTAMP` | | |

#### `wim_promo_conditions`
When a promo triggers.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `promo_id` | `INT` | `FK → wim_promo(id)` | |
| `condition_type` | `VARCHAR(50)` | `NOT NULL` | `min_qty`, `min_total`, `product_match`, `category_match`, `brand_match` |
| `condition_value` | `VARCHAR(255)` | | Value depends on type |
| `condition_product_id` | `INT` | `FK → wim_products(id)` | For product_match |

#### `wim_promo_rewards`
What the promo gives.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `promo_id` | `INT` | `FK → wim_promo(id)` | |
| `reward_type` | `VARCHAR(50)` | `NOT NULL` | `free_product`, `discount_percent`, `discount_amount` |
| `reward_value` | `VARCHAR(255)` | | |
| `reward_sku_ref` | `VARCHAR(50)` | | SKU of free product |
| `reward_qty` | `INT` | `DEFAULT 0` | Quantity on free product |

#### `wim_promo_assignments` _(🔴 New)_
Which depots/stores/channels get which promos.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `promo_id` | `INT` | `FK → wim_promo(id)` | |
| `target_type` | `VARCHAR(30)` | | `depot`, `store`, `channel`, `global` |
| `target_id` | `INT` | | Depot ID or Store ID |
| `target_value` | `VARCHAR(50)` | | For channel: `GT`, `MT`, etc. |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

#### `wim_promo_regions` _(🔴 New 2026-09-10)_
Which areas (regions) a promo applies to — enables multi-area promos.
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `promo_id` | `INT` | `PK, FK → wim_promo(id)` | |
| `region_id` | `INT` | `PK, FK → wim_regions(id)` | Area the promo applies to |

A promo with **no rows** in this table = applies to **all areas** (or legacy single `wim_promo.region_id`).

#### `wim_product_prices` _(🔴 New 2026-09-10)_
Per-area product pricing. Base `wim_products.price` is default; a row here overrides it in that region.
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `product_uuid` | `UUID` | `FK → wim_products(uuid)` | |
| `region_id` | `INT` | `FK → wim_regions(id)` | Area this price applies to |
| `price` | `DECIMAL(15,2)` | `NOT NULL` | Area price (Rp) |
| `effective_from` | `DATE` | `DEFAULT CURRENT_DATE` | "Set date" — when this price takes effect |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

**UNIQUE** `(product_uuid, region_id)`.

`wim_stores.region_id` (`INT FK → wim_regions(id)`) was **added** (2026-09-10) so each shop belongs to a pricing/propaganda area; used by the sales app to show the shop's area price.

#### `wim_sales_positions` _(🔴 New 2026-09-10)_
Every reported sales/user geolocation, persisted each time the app hits the position API (page load/refresh / page change). Joins to visits/orders/absensi by `user_id` + `recorded_at`.
| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `user_id` | `INT` | `FK → wim_users(id)` | Salesperson |
| `user_name` | `VARCHAR(255)` | | Denormalized name for quick joins |
| `latitude` | `DECIMAL(10,7)` | `NOT NULL` | |
| `longitude` | `DECIMAL(10,7)` | `NOT NULL` | |
| `accuracy_m` | `DECIMAL(10,2)` | | GPS accuracy (if reported) |
| `source` | `VARCHAR(20)` | `DEFAULT 'app'` | `app`, ... |
| `recorded_at` | `TIMESTAMP` | `DEFAULT NOW()` | When the fix was recorded |

**Indexes:** `(user_id)`, `(recorded_at)`.

---

### 3.11 Admin & RBAC

#### `wim_admin_depot_access`
Scoped access for depot admins. A depot admin assigned here can only see their depot's data.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `user_id` | `INT` | `FK → wim_users(id)` | |
| `depot_id` | `INT` | `FK → wim_depots(id)` | |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

**Index:** `user_id, depot_id` UNIQUE

---

### 3.12 NOO (New Outlet Opening)

NOO data is stored in `wim_stores` (the store record created) + `wim_store_contacts` (the owner contact).

**NOO Form Fields → Database Mapping:**

| Form Field | Table | Column |
|-----------|-------|--------|
| Nama Toko | `wim_stores` | `name` |
| Nama Pemilik | `wim_stores` | `owner_name` |
| No. HP | `wim_stores` | `phone` |
| Kontak Person | `wim_store_contacts` | `name` |
| Alamat | `wim_stores` | `address` |
| Provinsi | `wim_stores` | `province` |
| Kota | `wim_stores` | `city` |
| Kecamatan | `wim_stores` | `kecamatan` |
| Kelurahan | `wim_stores` | `kelurahan` |
| Kode Pos | `wim_stores` | `kode_pos` |
| Channel | `wim_stores` | `channel` |
| Kategori | `wim_stores` | `category` |
| Jenis Kendaraan | `wim_stores` | `kendaraan` |
| GPS | `wim_stores` | `latitude`, `longitude` |
| NIK | `wim_stores` | `nik` |
| NPWP | `wim_stores` | `npwp` |
| Nama NPWP | `wim_stores` | `npwp_name` |
| Foto Toko | `wim_store_photos` | `photo_data` |

---

### 3.13 Reporting & Analytics

Reporting queries are computed from existing tables. No separate reporting tables needed — the `wim_report` endpoint queries across:

| Report | Source Tables |
|--------|--------------|
| **Daily activity** (visits, orders, attendance) | `wim_visits`, `wim_orders`, `wim_attendance` |
| **Sales rep performance** (visit count, order count, total value) | `wim_visits`, `wim_orders`, `wim_order_items` |
| **Store visit frequency** | `wim_visits` GROUP BY `place_uuid` |
| **Depot performance** | `wim_visits` + `wim_orders` JOIN `wim_depot_stores` |
| **Stock analysis** (recorded stock vs ordered) | `wim_stock_check` + `wim_order_items` |
| **Promo effectiveness** (orders with promos) | `wim_orders.promos_applied` |

---

### 3.14 Sync & Integration

#### `wim_sync_queue`
Async job queue for pushing data to external systems.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `entity_type` | `VARCHAR(50)` | `NOT NULL` | `order`, `store`, `visit`, `attendance` |
| `entity_id` | `INT` | `NOT NULL` | ID in wim_* table |
| `action` | `VARCHAR(20)` | `NOT NULL` | `create`, `update`, `delete` |
| `target` | `VARCHAR(50)` | `NOT NULL` | `fleetbase`, `odoo`, `warehouse` |
| `status` | `VARCHAR(20)` | `DEFAULT 'pending'` | `pending`, `processing`, `done`, `failed` |
| `payload` | `JSONB` | | The data to send |
| `error` | `TEXT` | | Last error message |
| `retry_count` | `INT` | `DEFAULT 0` | |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |
| `synced_at` | `TIMESTAMP` | | When successfully synced |

**Index:** `status, target, created_at` (for worker queue)

#### `wim_sync_log` _(🔴 New)_
Append-only log of every external sync operation (for tracing/reconciliation).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `queue_id` | `INT` | `FK → wim_sync_queue(id)` | Originating job |
| `entity_type` | `VARCHAR(50)` | | |
| `entity_id` | `INT` | | |
| `target` | `VARCHAR(50)` | `NOT NULL` | `fleetbase`, `odoo`, `order_app` |
| `action` | `VARCHAR(20)` | | `create`, `update`, `push`, `pull` |
| `status` | `VARCHAR(20)` | | `started`, `done`, `failed` |
| `external_ref` | `VARCHAR(100)` | | Idempotency key from external system |
| `request_payload` | `JSONB` | | What was sent |
| `response_payload` | `JSONB` | | What came back |
| `error` | `TEXT` | | |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

---

### 3.15 Audit & Logging

#### `wim_audit_log`
All significant CRUD operations for compliance.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `user_id` | `INT` | `FK → wim_users(id)` | Who did it |
| `action` | `VARCHAR(100)` | | e.g. `order.create`, `user.login`, `visit.checkout` |
| `entity_type` | `VARCHAR(50)` | | `order`, `user`, `visit`, `store` |
| `entity_id` | `INT` | | ID in the affected table |
| `details` | `JSONB` | | Before/after values, metadata |
| `ip_address` | `VARCHAR(45)` | | |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

### 3.16 App Configuration

#### `wim_app_config` _(🔴 New)_
Key-value configuration store for application settings.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `SERIAL` | `PK` | |
| `config_key` | `VARCHAR(100)` | `UNIQUE NOT NULL` | Setting key |
| `config_value` | `JSONB` | `NOT NULL` | Any JSON value |
| `description` | `TEXT` | | |
| `updated_by` | `INT` | `FK → wim_users(id)` | |
| `created_at` | `TIMESTAMP` | `DEFAULT NOW()` | |
| `updated_at` | `TIMESTAMP` | `DEFAULT NOW()` | |

**Seed values:**
- `min_visit_seconds` → `180` (3 minutes)
- `geofence_radius_m` → `50`
- `app_name` → `"WIM Online"`
- `max_photo_size_mb` → `2`
- `sales_session_timeout_hours` → `12`
- `admin_session_timeout_hours` → `8`

---

## 4. Entity Relationship Diagram

```
wim_users
  ├── wim_user_meta (1:1 extended profile)
  ├── wim_sessions (1:N auth sessions)
  ├── wim_attendance (1:N daily clock-in/out)
  ├── wim_visit_plan (1:N daily route assignments)
  ├── wim_visits (1:N store check-ins)
  │   ├── wim_visit_photos (1:N photos per visit)
  │   ├── wim_stock_check (1:N stock records)
  │   └── wim_orders (1:1 order per visit)
  │       ├── wim_order_items (1:N line items)
  │       └── wim_order_status_log (1:N status changes)
  ├── wim_admin_depot_access (M:N depot access)
  └── wim_audit_log (1:N user actions)

wim_stores
  ├── wim_store_contacts (1:N phone/WA contacts)
  ├── wim_store_photos (1:N photos)
  ├── wim_store_relations (M:N store-to-store)
  ├── wim_depot_stores (M:N depot assignments)
  ├── wim_visit_plan (1:N visit schedule)
  ├── wim_visits (1:N visit history)
  ├── wim_stock_check (1:N stock records)
  └── wim_orders (1:N order history)

wim_products
  ├── wim_product_prices (1:N price history)
  ├── wim_depot_products (M:N depot availability)
  ├── wim_order_items (1:N order lines)
  ├── wim_stock_check (1:N stock records)
  ├── wim_promo_conditions (1:N promo triggers)
  └── wim_promo_rewards (1:N promo rewards)

wim_depots
  ├── wim_depot_stores (1:N store assignments)
  ├── wim_depot_products (1:N product availability)
  ├── wim_admin_depot_access (1:N admin RBAC)
  ├── wim_visit_plan_templates (1:N route templates)
  └── wim_user_meta (1:N user home depot)

wim_promo
  ├── wim_promo_conditions (1:N triggered by)
  ├── wim_promo_rewards (1:N gives)
  ├── wim_promo_assignments (1:N applies to)
  └── wim_orders.promos_applied (M:N orders)

wim_sync_queue → (future) Fleetbase API, Odoo API, Warehouse API
```

---

## 5. Column Patterns

All tables follow these conventions:

| Pattern | Rule |
|---------|------|
| **Primary key** | `id SERIAL PRIMARY KEY` |
| **Public ID** | `uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL` (on main entities) |
| **Foreign key** | `column_name INT REFERENCES table(id)` |
| **Timestamps** | `created_at TIMESTAMP DEFAULT NOW()` |
| **Update tracking** | `updated_at TIMESTAMP DEFAULT NOW()` (on mutable tables) |
| **Soft delete** | `deleted_at TIMESTAMP` (on major entities) |
| **JSON data** | `column_name JSONB DEFAULT '[]'::jsonb` or `'{}'::jsonb` |
| **Boolean** | `column_name BOOLEAN DEFAULT FALSE` |
| **Money** | `DECIMAL(15,2)` |
| **GPS** | `DECIMAL(10,7)` |

---

## 6. Future Sync API Endpoints

When the sync layer is built, the following API endpoints will be added to serve.py:

| Endpoint | Purpose | Reads From |
|----------|---------|------------|
| `GET /api/sync/fleetbase/orders?since=ISO` | Pending orders for Fleetbase | `wim_orders WHERE synced_to_fleetbase=FALSE` |
| `POST /api/sync/fleetbase/orders/:id/confirm` | Mark order synced | Updates `synced_to_fleetbase` |
| `GET /api/sync/odoo/report?period=m` | Monthly sales data for Odoo | `wim_orders` + `wim_order_items` |
| `GET /api/sync/warehouse/stock?date=today` | Today's stock data for warehouse | `wim_stock_check` |
| `POST /api/sync/queue` | Enqueue a sync job | Inserts into `wim_sync_queue` |
| `GET /api/sync/queue?status=pending` | Worker picks up jobs | `wim_sync_queue` |

---

## 7. Implementation Order

Recommended table creation order (dependencies first):

```
Phase 1 (Core — already migrated)
  1. wim_users
  2. wim_depots
  3. wim_stores
  4. wim_products
  5. wim_sessions
  6. wim_attendace
  7. wim_visits
  8. wim_visit_plan
  9. wim_stock_check
  10. wim_depot_stores

Phase 2 (Orders — schema ready, needs tables)
  11. wim_order_items
  12. wim_orders (depends on users, stores, visits, products, order_items)
  13. wim_order_status_log

Phase 3 (Promo — schema ready)
  14. wim_promo
  15. wim_promo_conditions
  16. wim_promo_rewards
  17. wim_promo_assignments

Phase 4 (Extended features)
  18. wim_user_meta
  19. wim_store_contacts
  20. wim_store_photos
  21. wim_store_relations
  22. wim_product_prices
  23. wim_depot_products
  24. wim_visit_plan_templates + stores
  25. wim_admin_depot_access
  26. wim_audit_log
  27. wim_sync_queue
  28. wim_app_config
```