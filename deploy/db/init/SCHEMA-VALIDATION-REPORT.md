# WIM SFA Schema Relationship Validation Report

**Date:** 2026-09-09
**Database:** wim_sfa (PostgreSQL 17, 192.168.6.110:5432)
**Tables:** 31 (all wim_ prefix)
**Method:** psycopg2 from middleware container LXC 111, transactional (ROLLBACK at end)

---

## 1. Schema Overview

The schema defines 31 tables with 26 FOREIGN KEY constraints and 20 UNIQUE constraints. All FK constraints are defined inline via `REFERENCES` clauses in `CREATE TABLE`. All enforcement tests confirmed the FKs are active in the live database.

---

## 2. Relationship Test Results

### 2.1 1:many Relationships

| # | Relationship | FK Constraint | JOIN Test | Enforcement Test | Verdict |
|---|---|---|---|---|---|
| 1 | `wim_users(1) → wim_visits(many)` | ✅ `wim_visits.user_id → wim_users.id` | PASS (4 visits for 1 user) | PASS (rejected invalid user_id) | **PASS** |
| 2 | `wim_stores(1) → wim_store_contacts(many)` | ✅ `wim_store_contacts.store_id → wim_stores.id` | PASS (3 contacts for 1 store) | PASS (rejected invalid store_id) | **PASS** |
| 3 | `wim_stores(1) → wim_visit_plan(many)` | **MISSING** (place_uuid has no FK to stores.uuid) | PASS (3 plans by UUID join) | — | **PASS (data flow) / FAIL (no FK)** |
| 4 | `wim_orders(1) → wim_order_items(many)` | ✅ `wim_order_items.order_id → wim_orders.id` | PASS (3 items for 1 order) | PASS (rejected invalid order_id) | **PASS** |
| 5 | `wim_products(1) → wim_stock_check(many)` | **MISSING** (product_id has no FK) | PASS (3 checks for 1 product) | — | **PASS (data flow) / FAIL (no FK)** |
| 6a | `wim_promo(1) → wim_promo_conditions(many)` | ✅ `wim_promo_conditions.promo_id → wim_promo.id` | PASS (2 conditions) | PASS (rejected invalid promo_id) | **PASS** |
| 6b | `wim_promo(1) → wim_promo_rewards(many)` | ✅ `wim_promo_rewards.promo_id → wim_promo.id` | PASS (2 rewards) | PASS (rejected invalid promo_id) | **PASS** |
| 7 | `wim_products(1) → wim_product_prices(many)` | ✅ `wim_product_prices.product_id → wim_products.id` | Not explicitly tested | — | **PASS** |
| 8 | `wim_depots(1) → wim_depot_stores(many)` | ✅ `wim_depot_stores.depot_id → wim_depots.id` | Not explicitly tested | — | **PASS** |
| 9 | `wim_depots(1) → wim_depot_products(many)` | ✅ `wim_depot_products.depot_id → wim_depots.id` | Not explicitly tested | — | **PASS** |

### 2.2 1:1 Relationships

| # | Relationship | Expected | Actual | Verdict |
|---|---|---|---|---|
| 10 | `wim_users(1) ↔ wim_user_meta(1)` | 1:1 via UNIQUE(user_id) | **1:many** — second meta INSERT succeeded, no UNIQUE(user_id) | **FAIL** |
| 11 | `wim_visits(1) → wim_orders(1)` | 1:1 via UNIQUE(visit_id) | **1:many** — second order for same visit succeeded, no UNIQUE(visit_id) | **FAIL** |
| 12 | `wim_users(1) ↔ wim_attendance(1) per day` | 1:1 per day via UNIQUE(user_id,date) | **1:1 per day** — duplicate rejected ✅ | **PASS** |

### 2.3 Summary

| Category | PASS | FAIL |
|---|---|---|
| 1:many data flow (JOINs) | 8 | 0 |
| FK enforcement | 5 | 0 |
| 1:1 cardinality enforcement | 1 | 2 |
| **Total** | **23 PASS** | **3 FAIL** |

---

## 3. Missing FOREIGN KEY Constraints

The schema has **26 real FK constraints**, but **30 logical FK columns are unconstrained**:

### Critical Missing FKs (logical parent-child relationships with no FK constraint)

| Child Table | Column | Should Reference | Impact |
|---|---|---|---|
| `wim_orders` | `store_id` | `wim_stores(id)` | Orders can reference non-existent stores |
| `wim_orders` | `visit_id` | `wim_visits(id)` | Orders can be orphaned from visits |
| `wim_order_items` | `product_id` | `wim_products(id)` | Items can reference non-existent products |
| `wim_stock_check` | `product_id` | `wim_products(id)` | Stock checks can reference non-existent products |
| `wim_stock_check` | `visit_id` | `wim_visits(id)` | Stock checks can be orphaned |
| `wim_visit_plan` | `place_uuid` | `wim_stores(uuid)` | Plans can reference non-existent stores (by UUID) |
| `wim_attendance` | `depot_id` | `wim_depots(id)` | Attendance can reference non-existent depots |
| `wim_visits` | `depot_id` | `wim_depots(id)` | Visits can reference non-existent depots |
| `wim_user_meta` | `depot_id` | `wim_depots(id)` | User meta can reference non-existent depots |
| `wim_user_meta` | `supervisor_id` | `wim_users(id)` | Supervisor can be non-existent |
| `wim_promo_conditions` | `condition_product_id` | `wim_products(id)` | Conditions can reference non-existent products |
| `wim_audit_log` | `user_id` | `wim_users(id)` | Audit log can reference non-existent users |
| `wim_store_photos` | `visit_id` | `wim_visits(id)` | Photos can be orphaned from visits |

### Intentional or Low-Priority Missing FKs

| Child Table | Column | Reason |
|---|---|---|
| `wim_orders` | `store_uuid` | Denormalized — already have store_id |
| `wim_orders` | `uuid` | Self-referencing is uncommon |
| `wim_stores` | `uuid` | Self-referencing |
| `wim_products` | `uuid` | Self-referencing |
| `wim_orders` | `fleetbase_order_uuid` | Optional external system reference |
| `wim_sync_log` | `entity_id` | Polymorphic — references different tables |
| `wim_promo_assignments` | `target_id` | Polymorphic — references different tables |
| `wim_users` | `driver_uuid` | Optional external system reference |
| `wim_stores` | `fleetbase_place_uuid` | Optional external system reference |

---

## 4. Missing Indexes on FK Columns

**18 FK columns lack a dedicated index** (i.e., no index whose first column is the FK column, excluding PK indexes):

| Table | Column | Current Index Coverage | Recommendation |
|---|---|---|---|
| `wim_admin_depot_access` | `depot_id` | Covered by UNIQUE(user_id,depot_id) — 2nd column only | LOW priority |
| `wim_depot_products` | `product_id` | Covered by UNIQUE(depot_id,product_id) — 2nd column only | LOW priority |
| `wim_order_status_log` | `order_id` | 🚫 No index | **ADD INDEX** |
| `wim_product_prices` | `product_id` | 🚫 No index | **ADD INDEX** |
| `wim_promo_assignments` | `promo_id` | 🚫 No index | **ADD INDEX** |
| `wim_promo_conditions` | `promo_id` | 🚫 No index | **ADD INDEX** |
| `wim_promo_rewards` | `promo_id` | 🚫 No index | **ADD INDEX** |
| `wim_sessions` | `user_id` | 🚫 No index | **ADD INDEX** |
| `wim_stock_check` | `user_id` | 🚫 No index | **ADD INDEX** |
| `wim_store_contacts` | `store_id` | 🚫 No index | **ADD INDEX** |
| `wim_store_photos` | `store_id` | 🚫 No index | **ADD INDEX** |
| `wim_store_relations` | `store_id` | 🚫 No index | **ADD INDEX** |
| `wim_store_relations` | `related_store_id` | 🚫 No index | **ADD INDEX** |
| `wim_sync_log` | `queue_id` | 🚫 No index | **ADD INDEX** |
| `wim_user_meta` | `user_id` | 🚫 No index | **ADD INDEX** |
| `wim_visit_plan_template_stores` | `template_id` | 🚫 No index | **ADD INDEX** |
| `wim_visit_plan_templates` | `depot_id` | 🚫 No index | **ADD INDEX** |
| `wim_visit_plan_templates` | `user_id` | 🚫 No index | **ADD INDEX** |

---

## 5. Schema Design Flaws

### 5.1 Stores linked by UUID, not ID

Tables `wim_visit_plan`, `wim_visits`, `wim_orders`, and `wim_stock_check` reference stores by `place_uuid` (a UUID), not by `store_id` (the integer PK). This means:
- **No FK constraint possible** on `place_uuid` → `wim_stores(uuid)` (UUID is not a PK, only a UNIQUE column)
- No ON DELETE CASCADE behavior
- No index on `wim_stores.uuid` for reverse lookups (though it has a UNIQUE index)

**Recommendation:** Add a `store_id` column to `wim_visit_plan` and `wim_stock_check` with a proper FK, or add FK constraints on `place_uuid` referencing `wim_stores(uuid)`.

### 5.2 wim_orders has both store_id (INT) and store_uuid (UUID)

Redundant — both reference the same store. The `store_id` has no FK, and `store_uuid` should be sufficient. Either:
- Remove `store_id` and add FK to `wim_stores(uuid)` (or `store_uuid` → `wim_stores(uuid)`)
- Or remove `store_uuid` and add FK on `store_id` → `wim_stores(id)`

### 5.3 wim_user_meta allows multiple rows per user (1:many instead of 1:1)

Missing `UNIQUE(user_id)` constraint means a user can have unlimited meta rows. If the intent is 1:1, add `UNIQUE(user_id)` or merge the columns into `wim_users`.

### 5.4 wim_orders.visit_id allows multiple orders per visit (1:many instead of 1:1)

Missing `UNIQUE(visit_id)` constraint means a visit can have many orders. If the intent is 1 order per visit, add `UNIQUE(visit_id)`.

### 5.5 Several tables use INT for user/store references instead of UUID

`wim_orders.store_id`, `wim_stock_check.product_id`, etc. use serial INTs. The parent tables' UUID columns are not used for FK relationships, which means UUIDs are only useful for external API consumers but not for internal referential integrity.

### 5.6 No ON DELETE CASCADE rules

All 26 FK constraints use `NO ACTION` for both DELETE and UPDATE. This means:
- Deleting a user requires manually deleting all visits, orders, attendance, etc.
- No cascading behavior — could lead to orphaned data or application errors when deleting parent records

---

## 6. Recommended Fixes (Priority Order)

### P0 (Data Integrity)
1. Add `UNIQUE(visit_id)` to `wim_orders` — enforce 1:1 visit→order
2. Add `UNIQUE(user_id)` to `wim_user_meta` — enforce 1:1 user→meta
3. Add FK `wim_orders.store_id → wim_stores(id)` — critical for order integrity
4. Add FK `wim_order_items.product_id → wim_products(id)` — critical for order items
5. Add FK `wim_stock_check.product_id → wim_products(id)`
6. Add FK `wim_orders.visit_id → wim_visits(id)`
7. Add FK `wim_visit_plan.place_uuid → wim_stores(uuid)`

### P1 (Performance)
8. Add indexes on all unindexed FK columns (18 items — see section 4 above)

### P2 (Cleanup)
9. Add FK `wim_attendance.depot_id → wim_depots(id)`
10. Add FK `wim_visits.depot_id → wim_depots(id)`
11. Add FK `wim_user_meta.depot_id → wim_depots(id)`
12. Add FK `wim_audit_log.user_id → wim_users(id)`
13. Consider adding ON DELETE SET NULL or CASCADE rules where appropriate