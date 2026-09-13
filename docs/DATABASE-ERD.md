# WIM Online — Database Entity-Relationship Diagram (ERD) & Justification

> **Date:** 2026-09-11 · **Schema:** PostgreSQL `wim_sfa` (38 tables).
> This document explains every entity and relationship, and WHY each exists.

---

## 1. ERD (Mermaid)

Paste into any Mermaid renderer (GitHub, mermaid.live, Obsidian) to see the diagram.

```mermaid
erDiagram
    %% ── Core identity ──
    wim_users {
        int id PK
        uuid uuid
        varchar email UK
        varchar name
        varchar role "super_admin|head_of_sales|manager|depo_admin|delivery|sales"
        varchar status
    }
    wim_user_meta {
        int id PK
        int user_id FK
        int depot_id FK
        int supervisor_id FK
        varchar jenis_sales "TO|SPG|SPC|SMD|NA"
        varchar vehicle_id "→ wim_vehicles (planned)"
    }
    wim_depots {
        int id PK
        varchar kode_depo
        int region_id FK
    }
    wim_regions {
        int id PK
        varchar name
        varchar kode_area
    }

    %% ── People / activity ──
    wim_attendance { int id PK; int user_id FK; date date }
    wim_sessions { int id PK; int user_id FK; timestamp expires_at }
    wim_sales_positions { int id PK; int user_id FK; numeric latitude; numeric longitude }

    %% ── Master data ──
    wim_products { int id PK; uuid uuid; varchar sku; numeric price }
    wim_product_prices { int id PK; uuid product_uuid; int depot_id FK; numeric price }
    wim_depot_products { int id PK; int depot_id FK; int product_id FK; bool is_active }
    wim_stores {
        int id PK
        uuid uuid
        int region_id FK
        int depot_id FK
        int assigned_salesperson_id FK
        varchar channel
    }
    wim_store_contacts { int id PK; int store_id FK }
    wim_store_photos { int id PK; int store_id FK }
    wim_store_relations { int id PK; int store_id FK; int related_store_id FK }
    wim_depot_stores { int id PK; int depot_id FK; uuid store_uuid }

    %% ── Promotions ──
    wim_promo { int id PK; varchar jenis; int region_id FK }
    wim_promo_conditions { int id PK; int promo_id FK }
    wim_promo_rewards { int id PK; int promo_id FK }
    wim_promo_assignments { int id PK; int promo_id FK }
    wim_promo_regions { int promo_id FK; int region_id FK }

    %% ── Field execution ──
    wim_visit_plan_templates { int id PK; int user_id FK; int depot_id FK; int week_number; int day_of_week }
    wim_visit_plan_template_stores { int id PK; int template_id FK; uuid store_uuid }
    wim_visit_plan { int id PK; int user_id FK; uuid place_uuid; date visit_date; int seq_no }
    wim_visits {
        int id PK
        int user_id FK
        uuid place_uuid
        timestamp checkin_at
        timestamp checkout_at
    }
    wim_stock_check { int id PK; int user_id FK; int visit_id; uuid place_uuid }

    %% ── Commerce ──
    wim_orders { int id PK; uuid uuid; int user_id FK; int store_id FK; int visit_id }
    wim_order_items { int id PK; int order_id FK; int product_id }
    wim_order_status_log { int id PK; int order_id FK }
    wim_invoice { int id PK; uuid order_uuid; int order_id }
    wim_payment { int id PK; int invoice_id FK; int store_id }
    wim_stock_balance { int id PK; int product_id; int depot_id }

    %% ── System / infra ──
    wim_admin_depot_access { int id PK; int user_id FK; int depot_id FK }
    wim_api_keys { int id PK; varchar api_key }
    wim_app_config { int id PK; varchar config_key }
    wim_audit_log { int id PK; int user_id; varchar action }
    wim_sync_queue { int id PK; varchar entity_type }
    wim_sync_log { int id PK; int queue_id FK }
    wim_wilayah { int id PK; varchar kode; varchar parent_kode; varchar level }

    %% ── Relationships ──
    wim_users ||--o{ wim_user_meta : "1..1 meta"
    wim_users ||--o{ wim_sessions : "sessions"
    wim_users ||--o{ wim_attendance : "clock-in/out"
    wim_users ||--o{ wim_sales_positions : "GPS"
    wim_users ||--o{ wim_visits : "performs"
    wim_users ||--o{ wim_orders : "takes"
    wim_users ||--o{ wim_visit_plan_templates : "owns template"
    wim_users ||--o{ wim_visit_plan : "planned days"
    wim_users ||--o{ wim_stock_check : "records stock"
    wim_depots ||--o{ wim_user_meta : "belongs to"
    wim_depots ||--o{ wim_stores : "services"
    wim_depots ||--o{ wim_depot_products : "offers products"
    wim_depots ||--o{ wim_depot_stores : "serves stores"
    wim_depots ||--o{ wim_product_prices : "has prices"
    wim_depots ||--o{ wim_visit_plan_templates : "route templates"
    wim_depots ||--o{ wim_stock_balance : "stock on-hand"
    wim_regions ||--o{ wim_depots : "contains"
    wim_regions ||--o{ wim_stores : "categorizes"
    wim_regions ||--o{ wim_promo : "promo by area"
    wim_regions ||--o{ wim_promo_regions : "promo-region"
    wim_products ||--o{ wim_product_prices : "per-depot price"
    wim_products ||--o{ wim_depot_products : "depot offering"
    wim_products ||--o{ wim_order_items : "ordered lines"
    wim_products ||--o{ wim_stock_balance : "stock"
    wim_stores ||--o{ wim_store_contacts : "contacts"
    wim_stores ||--o{ wim_store_photos : "photos"
    wim_stores ||--o{ wim_store_relations : "related"
    wim_stores ||--o{ wim_orders : "receives orders"
    wim_stores ||--o{ wim_visits : "visited at"
    wim_visit_plan_templates ||--o{ wim_visit_plan_template_stores : "slot stores"
    wim_orders ||--o{ wim_order_items : "lines"
    wim_orders ||--o{ wim_order_status_log : "history"
    wim_orders ||--o{ wim_invoice : "billed"
    wim_invoice ||--o{ wim_payment : "paid via"
    wim_promo ||--o{ wim_promo_conditions : "conditions"
    wim_promo ||--o{ wim_promo_rewards : "rewards"
    wim_promo ||--o{ wim_promo_assignments : "targets"
    wim_sync_queue ||--o{ wim_sync_log : "attempts"
    wim_users ||--o{ wim_admin_depot_access : "scopes"
```

---

## 2. Entity Justifications

### 2.1 Core identity & accounts

**`wim_users`** — One row per human account (admin + field sales). Holds login identity
(`email`/`password_hash`), `role` (super_admin / head_of_sales / manager / depo_admin / delivery / sales), and `status`.
*Why:* every record (visits, orders, attendance) must tie back to a person.

**`wim_user_meta`** — 1:1 profile extension of a user (depot assignment, jenis_sales, NIK/NPWP,
vehicle_id, supervisor, join date). *Why:* keeps operational attributes off the login table;
a user has exactly one profile. `depot_id` links the person to their warehouse.

**`wim_depots`** — A depot/warehouse that services a set of stores and owns prices/routes.
`region_id` = its administrative area. *Why:* the unit of Master-Data scoping in this app
(prices are per depot; routes per depot).

**`wim_regions`** — Administrative region (area). *Why:* prices were historically per region
(now per depot, region remains a category); depots and stores carry a region for reporting.

**`wim_sessions`** — Auth session rows (cookie sessions). *Why:* stateless HTTP needs a server-side
session store for login continuity.

**`wim_admin_depot_access`** — Grants a depo_admin access to specific depots. *Why:* enforces
scoped admin permissions (which depots an admin may manage).

### 2.2 Field activity

**`wim_attendance`** — Daily clock-in/out of a sales rep (with photos, GPS, duration). *Why:*
absensi tracking + the recap's "Waktu Mulai/Selesai" (Goovi parity).

**`wim_sales_positions`** — Real-time/periodic GPS snapshots of reps. *Why:* the Rute/Maps page and
live position badges.

**`wim_visits`** — One row per store visit (check-in→checkout, photos, notes, geo, source
route/luar-rute, duration). *Why:* the core field action — everything else (orders, stock,
photos) hangs off a visit.

**`wim_visit_plan_templates` + `wim_visit_plan_template_stores`** — The **monthly-repeating route
template** (week×day slot → ordered store list). *Why:* lets admin set a rep's route once per
month (day1-wk1…day6-wk4) reused monthly (the plan-edit redesign).

**`wim_visit_plan`** — Date-based planned store visits for a specific day (execution snapshot,
resolved from template by `resolve_template_for_date()`). *Why:* the field app reads today's
planned stores; carries `seq_no` order + `source`.

**`wim_stock_check`** — Per-visit shelf-stock counts at a store. *Why:* tracks on-shelf inventory.

### 2.3 Master data (products & stores)

**`wim_products`** — Product catalog (SKU, name, base price, brand, unit, weight). *Why:* the item
master every price/order/stock row references.

**`wim_product_prices`** — **Per-depot product price** (1:1 product×depot, `UNIQUE(product_uuid,depot_id)`).
*Why:* pricing is per depot (user correction), giving one-to-one product↔depot price.

**`wim_depot_products`** — Which products a depot carries/offers (is_active). *Why:* a depot can
restrict its sellable catalog.

**`wim_stores`** — Customer/outlet master (name, geo, owner, NIK/NPWP, channel, category, address,
all 4 admin-region levels + their BPS codes). `depot_id` = servicing depot; `assigned_salesperson_id`
= owning rep. *Why:* the customer entity for selling; ties to depot (pricing) and rep (route).

**`wim_store_contacts`** — Named contacts for a store (owner/manager phones/roles). *Why:* a store
can have multiple people; keeps 1:many.

**`wim_store_photos`** — Store exterior/NOO photos (data URL). *Why:* evidence of store condition.

**`wim_store_relations`** — Related/affiliated stores. *Why:* parent-chain or linked-branch modeling.

**`wim_depot_stores`** — Explicit depot↔store assignment (many-to-many). *Why:* a depot may serve
stores beyond the rep's ones; complements `stores.depot_id`.

### 2.4 Promotions

**`wim_promo`** — Promotion header (name, type, status, period, stackable, region).
**`wim_promo_conditions`** — Eligibility rules (min transaction, product conditions).
**`wim_promo_rewards`** — Free-item/bonus rewards.
**`wim_promo_assignments`** — Which store/product types a promo targets.
**`wim_promo_regions`** — Join table: promos applicable to which regions.
*Why (all):* a flexible, composable promo engine (conditions+rewards+targets) split into small
1:many tables so each rule is a row, easy to manage and extend.

### 2.5 Commerce

**`wim_orders`** — A sales order (user, store, visit, items JSON, status, total, payment_method,
source route/luar). *Why:* the transaction; `visit_id` links the order to the check-in visit;
`items` JSONB denormalizes line data for fast reads (wim_order_items exists too).

**`wim_order_items`** — Normalized order line items (parallel to `orders.items` JSON). *Why:*
legacy/reporting structure; some analytics still read it.

**`wim_order_status_log`** — Status-change audit trail per order. *Why:* who/when changed status.

**`wim_invoice`** — Invoice header (INV-number, order_uuid, total, status unpaid/paid, due). *Why:*
billing / AR aging. **`wim_payment`** — Payments against an invoice (amount, method, paid_at).
*Why:* track partial/full settlement.

**`wim_stock_balance`** — Depot-level on-hand stock per product. *Why:* P4 stock feature — sells
and replenishment reference depot inventory, complements shelf `stock_check`.

### 2.6 System / infrastructure

**`wim_api_keys`** — External/integration API keys. **`wim_app_config`** — KV config.
**`wim_audit_log`** — Broad action audit trail. **`wim_sync_queue`** + **`wim_sync_log`** — Offline/
external sync (Fleetbase) work queue + per-attempt log. **`wim_wilayah`** — The BPS/Kemendagri
administrative-region lookup table (prov/kab/kec/kel codes, `parent_kode` hierarchy) powering the
cascading drop-downs.

*Why:* infra tables exist to support auth-key integrations, auditability, offline sync to Fleetbase,
and the typo-proof region dropdowns — each a distinct, single-purpose store.

---

## 3. Relationship Justifications

| Parent | → Child | Cardinality | Justification |
|---|---|---|---|
| `wim_users` | `wim_user_meta` | 1:1 | One profile per account; keeps login vs operational data separate. |
| `wim_users` | `wim_visits` | 1:N | A rep performs many visits over time. |
| `wim_users` | `wim_orders` | 1:N | A rep takes many orders. |
| `wim_users` | `wim_attendance` | 1:N | One rep has many daily clock rows (can't merge into user row — grows daily). |
| `wim_users` | `wim_visit_plan_templates` | 1:N | A rep owns 24 route slots. |
| `wim_users` | `wim_sessions` | 1:N | Multiple concurrent sessions per user. |
| `wim_depots` | `wim_user_meta` | 1:N | Many reps belong to one depot (a rep belongs to one depot). |
| `wim_depots` | `wim_stores` | 1:N | One depot services many stores → drives per-depot pricing. |
| `wim_depots` | `wim_product_prices` | 1:N | One depot has a price for each product (1:1 per product). |
| `wim_regions` | `wim_depots` | 1:N | A region groups many depots (historical area dimension). |
| `wim_regions` | `wim_stores` | 1:N | A region categorizes many stores. |
| `wim_products` | `wim_product_prices` | 1:N | One product has one price per depot (1:1 per depot). |
| `wim_products` | `wim_order_items` | 1:N | A product appears on many order lines. |
| `wim_stores` | `wim_orders` | 1:N | One store receives many orders. |
| `wim_stores` | `wim_store_contacts` | 1:N | One store → many named contacts. |
| `wim_visit_plan_templates` | `wim_visit_plan_template_stores` | 1:N | One slot → many ordered stores (route order = visit_order). |
| `wim_orders` | `wim_order_items` | 1:N | One order → many line items. |
| `wim_orders` | `wim_order_status_log` | 1:N | One order → many status changes. |
| `wim_orders` | `wim_invoice` | 1:0..1 | One order → at most one invoice (billing derived from order). |
| `wim_invoice` | `wim_payment` | 1:N | One invoice → many partial payments. |
| `wim_promo` | `wim_promo_conditions` | 1:N | One promo → many rules. |
| `wim_promo` | `wim_promo_rewards` | 1:N | One promo → many rewards. |
| `wim_sync_queue` | `wim_sync_log` | 1:N | One queued job → many attempt logs. |

### Notable design decisions
- **Stores↔Rep `assigned_salesperson_id (FK wim_users)`** — a store is owned by one rep; lets routes
  and per-store pricing resolve deterministically.
- **`wim_orders.items` JSONB alongside `wim_order_items`** — denormalized for speed + a normalized
  table for reporting; dual-source is acknowledged (read from `items`).
- **Route templates stored separately from dated `wim_visit_plan`** — template = reusable monthly
  "recipe"; plan = a concrete day's execution. Keeps them independent and reversible.
- **`vehicle_id` in `wim_user_meta` points to a not-yet-built `wim_vehicles` table** (known gap,
  Goovi parity — documented separately).

---

## 4. Diagram files
- This markdown (Mermaid source) is the canonical ERD.
- A rendered PNG/SVG can be produced from any Mermaid-compatible tool; not committed to avoid a
  toolchain dependency, but the source above is self-contained.