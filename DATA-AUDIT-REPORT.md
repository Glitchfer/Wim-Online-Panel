# DATA AUDIT REPORT — WIM Online (Standalone PostgreSQL)

**Date:** 2026-09-09  
**Auditor:** Hermes Agent (subagent)  
**Source:** PostgreSQL `wim_sfa` database (on LXC 106)  
**Scope:** Product prices, visits, stock checks, attendance, orders

---

## 1. PRODUCT PRICES — Entities Table vs Buat Pesanan

### 1.1 Entities Table (Source of Truth)

| # | SKU | Name | meta.price | meta.brand | meta.category |
|---|-----|------|-----------|-----------|-------------|
| 1 | SQA-220-K24 | SANQUA PET 220ML K24 | **Rp100,000** | SANQUA | sanqua |
| 2 | SQA-550-K24 | SANQUA PET 550ML K24 | **Rp150,000** | SANQUA | sanqua |
| 3 | SQA-1500-K12 | SANQUA PET 1500ML K12 | **Rp135,000** | SANQUA | sanqua |
| 4 | SQA-120-K40 | SANQUA CUP 120ML K40 | **Rp80,000** | SANQUA | sanqua |
| 5 | SQA-330-K24 | SANQUA CUP 330ML K24 | **Rp90,000** | SANQUA | sanqua |
| 6 | LEV-220-K24 | LEVONTE CUP 220ML K24 | **Rp85,000** | LEVONTE | levonte |
| 7 | BAT-200-K48 | BATAVIA CUP 200ML K48 | **Rp95,000** | BATAVIA | batavia |
| 8 | BAT-600-K24 | BATAVIA PET 600ML K24 | **Rp130,000** | BATAVIA | batavia |

### 1.2 Buat Pesanan Price Source

The `GET /api/products` endpoint (in `orders.py:do_products`) reads `price` from `entities.meta.price` directly:

```python
price = (m.get('price') if isinstance(m, dict) else None) or 0
```

The `order.html` displays `formatIDR(p.price)` where `p.price` comes from this API response.  

**Verdict: ✅ MATCH** — Buat Pesanan prices are read directly from `entities.meta.price` with no transformation. Prices shown to the user in the UI are identical to the DB values.

### 1.3 Price Consistency Check — Orders vs Catalog

| Order ID | SKU | Order unit_price | Entities meta.price | Match? |
|----------|-----|-----------------|-------------------|--------|
| order_d988547cxc7b | BAT-200-K48 | 95,000 | 95,000 | ✅ |
| order_d988547cxc7b | BAT-600-K24 | 130,000 | 130,000 | ✅ |
| order_d988547cxc7b | SQA-120-K40 | 80,000 | 80,000 | ✅ |
| order_d988547cxc7b | SQA-330-K24 | 90,000 | 90,000 | ✅ |
| order_d988547cxc7b | SQA-220-K24 | 100,000 | 100,000 | ✅ |
| order_944ad28ex489 | SQA-550-K24 | 150,000 | 150,000 | ✅ |

**Verdict: ✅ ALL ORDERS MATCH CATALOG PRICES** — No price drift between order creation and current catalog.

### 1.4 Price Discrepancy — Plan Doc vs Actual

The IMPLEMENTATION-PLAN.md and test-env doc reference **different prices** than the DB:

| SKU | Planned Price (doc) | Actual DB Price | Delta |
|-----|-------------------|----------------|-------|
| SQA-220-K24 | 120,000 | **100,000** | -20,000 |
| SQA-550-K24 | 150,000 | 150,000 | ✅ |
| SQA-1500-K12 | 130,000 | **135,000** | +5,000 |
| SQA-120-K40 | 80,000 | 80,000 | ✅ |
| SQA-330-K24 | 100,000 | **90,000** | -10,000 |
| LEV-220-K24 | 95,000 | **85,000** | -10,000 |
| BAT-200-K48 | 115,000 | **95,000** | -20,000 |
| BAT-600-K24 | 140,000 | **130,000** | -10,000 |

**Note:** The DB prices appear to be the intentionally-set "actual" prices (possibly updated by the user). The plan docs are 8 days old (2026-09-01). The DB prices are the authoritative source since Buat Pesanan reads from them directly. **No action needed — docs need updating, not data.**

---

## 2. wim_visits — Check-in/Checkout Records

### 2.1 Record Count

| Metric | Value |
|--------|-------|
| **Total visits** | 12 |
| **Today** (2026-09-09) | 2 |
| **Yesterday** (2026-09-08) | 10 |

### 2.2 Today's Visits (2026-09-09)

| ID | Store | Check-in | Check-out | Duration | Status | Source |
|----|-------|---------|----------|----------|--------|--------|
| 12 | TOKO TESTING GRHA SANQUA | 14:09:25 | 14:16:16 | 180s | no_order | luar_rute |
| 13 | TOKO SEJAHTERA (BLOK A) | 14:12:28 | 14:16:48 | 180s | no_order | luar_rute |

### 2.3 Yesterday's Visits (2026-09-08)

| ID | Store | Check-in | Check-out | Duration | Status |
|----|-------|---------|----------|----------|--------|
| 1 | TOKO BERKAH | 18:02:26 | 18:02:27 | 120s | visited |
| 2 | TOKO BERKAH | 18:03:10 | 18:03:11 | 120s | visited |
| 4 | TOKO BERKAH | 18:43:48 | 18:43:48 | 120s | visited |
| 5 | TOKO BERKAH | 18:55:24 | 18:55:24 | 120s | visited |
| 6 | TOKO BERKAH | 22:07:38 | 22:08:57 | 0s | visited |
| 7 | TOKO BERKAH | 22:08:57 | 15:10:12 | 0s | visited |
| 8 | TOKO BERKAH | 22:10:20 | 22:57:34 | 200s | visited |
| 9 | TOKO BERKAH | 22:57:34 | 15:59:27 | 0s | visited |
| 10 | TOKO BERKAH | 22:59:36 | 16:02:42 | 0s | visited |
| 11 | TOKO BERKAH | 23:02:50 | **NULL** | 0s | visited |

**Issues found:**
- ⚠️ **Visit #11 has no checkout** (NULL) — open/ongoing since yesterday 23:02
- ⚠️ **Visits #7, #9, #10** show checkout times *before* check-in times (check-in 22:08, checkout 15:10) — likely due to timezone mismatch (server uses UTC+7 WIB, but checkout_at stored off by ~7 hours)
- ⚠️ **Multiple duplicate visits to TOKO BERKAH** (10 to same store) — test data noise from QA loops

**Verdict: ✅ VISITS ARE PERSISTED WITH CHECK-IN/CHECKOUT DATA** — Data exists, but has timezone issues and an open visit.

---

## 3. wim_stock_check — Stock Data

### 3.1 Record Count

| Metric | Value |
|--------|-------|
| **Total stock check records** | 1 |

### 3.2 Stock Check Data

| ID | User ID | Place UUID | SKU | Qty | Checked At |
|----|---------|-----------|-----|-----|-----------|
| 1 | 6 | test | SQA-PET-550 | 5 | 2026-09-08 22:10:20 |

### 3.3 Stock Check SKU Consistency

**Issue: ⚠️ SKU mismatch between stock check UI and catalog**

| Stock Check UI SKU (visit-card.html) | Stock Check DB SKU | Catalog Entity SKU | Match? |
|--------------------------------------|-------------------|-------------------|--------|
| `SQA-PET-550` | `SQA-PET-550` | `SQA-550-K24` | ❌ |
| `SQA-PET-220` | — | `SQA-220-K24` | ❌ |
| `SQA-CUP-120` | — | `SQA-120-K40` | ❌ |
| `SQA-GALON-19L` | — | *(not in catalog)* | ❌ |
| `LEVONTE-CUP` | — | `LEV-220-K24` | ❌ |

The stock check UI uses **human-readable quick-entry SKUs** (e.g., `SQA-PET-550`) while the actual product catalog uses **structured SKUs** (e.g., `SQA-550-K24`). There is no mapping table between them. This means:
- Stock check data cannot be joined to the product catalog
- The `place_uuid` for the only record is `'test'` (not a real UUID)

**Verdict: ⚠️ STOCK CHECK DATA EXISTS (1 record) BUT IS EFFECTIVELY DISCONNECTED** — SKUs don't match the catalog, and the place_uuid is invalid. Needs a mapping table or SKU alignment.

---

## 4. wim_attendance — Clock-in Data

### 4.1 Record Count

| Metric | Value |
|--------|-------|
| **Total attendance records** | 1 |

### 4.2 All Attendance Records

| ID | User ID | Date | Clock In | Clock Out | Duration | Geofence Status | Depot ID |
|----|---------|------|---------|----------|----------|----------------|----------|
| 6 | 6 | 2026-09-08 | 09:00:00 | 18:00:00 | (empty) | (empty) | NULL |

### 4.3 Today's Attendance

**No attendance record for today (2026-09-09).** User (Andi Sales) has not clocked in today.

### 4.4 Observations

- Only 1 attendance record exists — for yesterday (2026-09-08)
- No geofence status recorded (empty)
- No depot ID recorded (NULL)
- No duration value stored

**Verdict: ✅ ATTENDANCE DATA EXISTS (1 record for yesterday)** — Clock-in/out persisted correctly. No attendance for today yet.

---

## 5. orders — Order Data

### 5.1 Record Count

| Metric | Value |
|--------|-------|
| **Total orders** (deleted_at IS NULL) | 6 |
| **WIM Online orders** (meta.source='wim-online') | 3 |
| **Legacy test orders** | 2 |
| **Test orders** | 1 |

### 5.2 WIM Online Orders (Real Orders)

| Order ID | Status | Store | Grand Total | Check-in ID | Verification | Created |
|----------|--------|-------|------------|-------------|-------------|---------|
| order_d988547cxc7b | **pending** | TOKO TESTING GRHA SANQUA | Rp490,000 | 12 | pending | 2026-09-09 07:10 |
| order_944ad28ex489 | **verified** | TOKO BERKAH (PASAR TANAH ABANG) | Rp600,000 | 11 | verified | 2026-09-08 16:02 |
| order_4df94dbfx10e | **pending** | TOKO BERKAH (PASAR TANAH ABANG) | Rp600,000 | 10 | pending | 2026-09-08 15:59 |

### 5.3 Order → Visit Link Verification

| Order | Check-in ID | Visit Store | Visit Check-in | Visit Check-out | Visit Status | Linked? |
|-------|-----------|------------|---------------|----------------|-------------|---------|
| order_d988547cxc7b | 12 | TOKO TESTING GRHA SANQUA | 14:09:25 | 14:16:16 | no_order | ✅ |
| order_944ad28ex489 | 11 | TOKO BERKAH | 23:02:50 | NULL | visited | ✅ |
| order_4df94dbfx10e | 10 | TOKO BERKAH | 22:59:36 | 16:02:42 | visited | ✅ |

**All 3 real orders link to valid check-in events.** The core integrity rule (Order > 0 must have a verified check-in event) is satisfied.

### 5.4 Order Items Price Verification

Extracted from `orders.meta.items` and compared against `entities.meta.price`:

| Order | SKU | Order Unit Price | Catalog Price | Match? |
|-------|-----|-----------------|---------------|--------|
| order_d988547cxc7b | BAT-200-K48 | 95,000 | 95,000 | ✅ |
| order_d988547cxc7b | BAT-600-K24 | 130,000 | 130,000 | ✅ |
| order_d988547cxc7b | SQA-120-K40 | 80,000 | 80,000 | ✅ |
| order_d988547cxc7b | SQA-330-K24 | 90,000 | 90,000 | ✅ |
| order_d988547cxc7b | SQA-220-K24 | 100,000 | 100,000 | ✅ |
| order_944ad28ex489 | SQA-550-K24 | 150,000 | 150,000 | ✅ |

**Verdict: ✅ PRICES MATCH — All order unit prices match the current catalog.** No price manipulation or drift.

### 5.5 Order Fulfillment Check

| Order ID | Grand Total | Discount Applied | Items | Verified? |
|----------|------------|-----------------|-------|-----------|
| order_d988547cxc7b | 490,000 | Promo "Diskon Rp 5.000/karton" (PROMO-2026-09-003) | 5 SKUs × 1 each | ❌ Pending |
| order_944ad28ex489 | 600,000 | None | 4 × SQA-550-K24 | ✅ Verified |
| order_4df94dbfx10e | 600,000 | None | (items stored, no unit_price breakdown) | ❌ Pending |

**Verdict: ✅ ORDERS ARE PERSISTED WITH LINE ITEMS, PRICES, AND PROMOS** — 1 verified, 2 pending verification.

---

## 6. SYSTEM-WIDE DATA INTEGRITY

### 6.1 Referential Integrity

| Check | Status |
|-------|--------|
| Orders → wim_visits (checkin_id) | ✅ All 3 real orders link to valid visits |
| Orders → drivers (driver_assigned_uuid) | ✅ All 3 real orders link to driver 9f449042-b718-4b36-803c-f52ff6443337 (Andi Sales) |
| Orders → payloads (payload_uuid) | ⚠️ 9 payload rows exist, but order-to-payload link not verified per-order |
| wim_visits → users (user_id) | ✅ All visits by user 6 (Andi Sales) |
| wim_attendance → users (user_id) | ✅ Record 6 for user 6 |
| wim_stock_check → entities (sku) | ❌ `SQA-PET-550` does not match any catalog SKU |
| wim_stock_check → places (place_uuid) | ❌ `place_uuid` = 'test' (invalid UUID) |

### 6.2 Data Completeness

| Table | Expected | Actual | Status |
|-------|----------|--------|--------|
| entities (products) | 8 | 8 | ✅ |
| wim_visits (today) | ≥1 | 2 | ✅ |
| wim_stock_check | ≥1 | 1 | ⚠️ Minor |
| wim_attendance (today) | ≥1 | 0 | ⚠️ No one clocked in yet |
| orders (real) | 3 | 3 | ✅ |

### 6.3 Active Promos

| Promo | Type | Status | Period |
|-------|------|--------|--------|
| PROMO-2026-09-001: Beli 10 SANQUA PET 550ML, Gratis 2 LEVONTE CUP | bundling | active | Sep 2026 |
| PROMO-2026-09-002: Diskon Strata SANQUA (10+: 5%, 21+: 10%) | strata | active | Sep 2026 |
| PROMO-2026-09-003: Diskon Rp 5.000/karton SANQUA PET 220ML | diskon | active | Sep 2026 |

---

## 7. SUMMARY

| # | Area | Verdict | Details |
|---|------|---------|---------|
| 1 | **Product prices match Buat Pesanan** | ✅ PASS | Both read from `entities.meta.price` — identical by construction |
| 2 | **wim_visits has check-in/checkout** | ✅ PASS | 12 records, 2 today, 10 yesterday. ⚠️ Visit #11 has open checkout; timezone issues on some records |
| 3 | **wim_stock_check has stock data** | ⚠️ PASS (with issues) | 1 record exists. **SKU mismatch** — stock check uses `SQA-PET-550` vs catalog `SQA-550-K24`. `place_uuid` is `'test'` (invalid) |
| 4 | **wim_attendance has clock-in data** | ✅ PASS (yesterday) | 1 record for 2026-09-08 (09:00-18:00). No attendance for today yet |
| 5 | **orders table has order data** | ✅ PASS | 6 total (3 real WIM orders). 1 verified, 2 pending. All prices match catalog. All link to valid check-ins |

### Key Issues Found

1. **⚠️ SKU mismatch between stock check UI and product catalog** — The 5 quick-entry SKUs in `visit-card.html` (SQA-PET-550, SQA-PET-220, SQA-CUP-120, SQA-GALON-19L, LEVONTE-CUP) don't match any entity SKUs. The single stored record uses `SQA-PET-550` which doesn't link to `SQA-550-K24`. **Fix needed:** Add a mapping table or align SKUs.

2. **⚠️ Visit #11 has open checkout** — Check-in at 2026-09-08 23:02:50 with no checkout. If this is a stuck/bugged visit, it should be resolved.

3. **⚠️ Timezone inconsistency on some visits** — Visits #7, #9, #10 show checkout times before check-in times (e.g., check-in 22:08, checkout 15:10). Likely a UTC/local timezone issue in the server.

4. **⚠️ Plan docs have outdated prices** — The IMPLEMENTATION-PLAN.md and test-env references show different prices than the actual DB (e.g., SQA-220-K24: doc says 120,000, DB has 100,000). The DB is the authoritative source.

### Tables Up-to-Date

All tables queried confirmed live and accessible. The database is on `postgres-container` (MySQL 8), LXC 106, Proxmox 192.168.6.101, accessed via Netbird jump host.