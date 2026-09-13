# WIM Admin — Proposed Navigation Bar Organization

> **Date:** 2026-09-11 · **Status:** Proposal (NOT implemented)
> Goal: clear, consistent, non-overlapping navbar. Dropdown menus used so top-level
> stays shallow. Every page/function assigned once to a category below its true function.

## 1. Design principle
Organize by **business lifecycle**, not by technical feature:
**Katalog → Pelanggan → Penjualan → Operasional → Kunjungan → Analitik → Sistem.**

The current bar mixes three different axes (what the page *is*, who *uses* it, and
whether it's a report vs. an action). The fix: group by *what the deprecated admin is
doing in that moment* — and separate **reference/master data** from **transactions**,
**execution/field ops** from **reporting**.

---

## 2. Recommended navbar (7 top-level buttons)

```
📊 Dashboard
🛒 Penjualan ▾        📦 Pesanan · 🧾 Invois & Piutang · 🚚 Packing List
🏷️ Katalog ▾          📦 Produk & Harga · 💰 Harga per Area · 🎁 Promo
🏬 Pelanggan ▾        🏬 Toko
🏢 Operasional ▾      🏢 Depo · 📦 Stok On-Hand · 🗺️ Rute & Maps
🗓️ Kunjungan ▾       👁️ Lihat Rencana · ✏️ Edit Rencana · 🛍️ Log Kunjungan · ⏰ Absensi · 👥 Tim
📈 Analitik ▾         📊 Rekap Harian · 📈 Performa Sales · 🧾 Laporan · 📦 Order vs Stok · 🛍️ Order per Toko · 🖼️ Galeri Foto
```

Optionally a **8th** `⚙️ Sistem ▾` (Pengguna) that is **super_admin-only**.

---

## 3. Page/function map (current → proposed)

| Page / Function | What it is | Current location | Proposed | Reason |
|---|---|---|---|---|
| `dashboard.html` | KPI home | top-level | **Dashboard** | unchanged |
| `orders.html` (Pesanan, Edit Order) | Transaction: manage orders | top-level Pesanan | **Penjualan** | core sales transaction |
| `invoices.html` (Invois & Piutang, AR aging) | Transaction: billing/receivables | top-level Invois | **Penjualan** | order-money lifecycle |
| `packing.html` (Dispatch Per Hari / Luar Rute / Muatan SKU) | Fulfillment: plan dispatch + packing | Pesanan ▾ | **Penjualan** (or **Operasional**) | it is the raise→deliver handoff; see note |
| `products.html` (Produk & Harga) | Master: catalog | Produk & Promo ▾ | **Katalog** | reference data |
| `pricing.html` (Harga by Area) | Master: region pricing | top-level | **Katalog** | belongs with product pricing, NOT standalone |
| `promos.html` (Promo) | Master: promo config | Produk & Promo ▾ | **Katalog** | reference data |
| `stores.html` (Toko) | Master: customer stores | top-level Toko | **Pelanggan** | customer master |
| `depots.html` (Depo) | Master: warehouse/depot | top-level Depo | **Operasional** | operational unit |
| `stock.html` (Stok On-Hand) | Inventory | top-level Stok | **Operasional** | inventory ops |
| `route-map.html` (Rute & Maps) | Field ops: live positions/routes | top-level Rute/Maps | **Operasional** or **Kunjungan** | field execution |
| `today-plan.html` (Lihat List Kunjungan) | Field: view planned visits (read-only) | Rencana Kunjungan ▾ | **Kunjungan** | keep paired with edit |
| `plan-edit.html` (Edit List Kunjungan) | Field: assign/reorder store route | Rencana Kunjungan ▾ | **Kunjungan** | keep paired with view |
| `visits.html` (Kunjungan log) | Field: historical visit log | Analitik ▾ (currently) | **Kunjungan** | it's the *log of a field action*, not a report |
| `attendance.html` (Absensi) | Field: attendance/clock in-out | top-level Absensi | **Kunjungan** | field-activity record |
| `team.html` (Tim) | Master/Ppl: sales roster | Analitik ▾ (currently) | **Kunjungan** (or **Sistem**) | team is a roster, not analytics |
| `users.html` (User Management) | System admin | top-level Users | **Sistem ▾** (super-only) | privilege config |
| `analytics.html` tabs: Rekap Harian | Report | Analitik ▾ | **Analitik** | report |
| `analytics.html` tab: Performa Sales-Depo | Report | Analitik ▾ | **Analitik** | report |
| `analytics.html` tab: Order per Toko | Report | Analitik ▾ | **Analitik** | report |
| `analytics.html` tab: Order vs Stok | Report | Analitik ▾ | **Analitik** | report |
| `analytics.html` tab: Galeri Foto | Media/log | Analitik ▾ | **Analitik** | visit photos recap |
| `laporan.html` hub (Cetak SJ, Cetak Invoice Batch) | Report/export | Laporan ▾ | **Analitik** | export & batch print |
| `index.html` (login) | — | — | (not in nav) | auth screen |

---

## 4. Key judgment calls (and why)

1. **`packing.html` → Penjualan (recommended)**, not Operasional.
   - Why: packing is the *dispatch of the orders a sales rep took today* — the driver's
     route is derived from the sales rep's route for that day (your stated model). It sits
     at the Pesanan→delivery handoff, so it belongs beside Pesanan/Invois where the admin
     works orders into delivery. Alternative (also valid): a **Distribusi ▾** group with
     Stok + Depo + Rute + Packing if you think of it primarily as outbound logistics.
   - Recommendation: keep it under **Penjualan** for now (fewer clicks from orders → pack).

2. **`visits.html` & `attendance.html` → Kunjungan**, *not* Analitik.
   - Though they render tabular data (feels like "reporting"), they are the **log of field
     execution** (a store was visited, sales clocked in). Keeping them with Rencana (plan →
     execute → log) makes the **Kunjungan** group tell the full field story: *plan the
     route, execute it, log visits & attendance.* Analitik should be *aggregate KPI* views
     only.

3. **`team.html` → Kunjungan** (not Analitik, not separate).
   - Team = the roster of salespeople whose routes/kunjungan/absensi this admin manages.
     Grouping it with Kunjungan keeps the *people + their activity* together.

4. **`pricing.html` → Katalog** alongside Produk & Promo.
   - Price by area is product pricing data; it was stranded as a top-level menu item.
     Fold under **Katalog** (reference), not left floating.

5. **`users.html` → `⚙️ Sistem`**, super_admin-only.
   - Account/privilege management is not a daily task; hiding it under a small admin
     dropdown declutters and (optionally) enforces role separation.

6. **Analitik collapses to read-only KPI reports.** The 5 report tabs + Laporan hub all
   live under one **Analitik ▾**. This removes the current confusion where some reports
   were in Analitik and others (packing) drifted to Laporan/Pesanan.

7. **Rute & Maps → Operasional** (or Kunjungan). It shows live sales positions + delivery
   routes. If it's used mainly to *supervise the field*, it fits **Kunjungan**; if used to
   *route vehicles/depots*, it fits **Operasional**. Recommend **Operasional** now since it
   pairs with Depo/Stok for depot-level ops; can move to Kunjungan if field supervision is
   the primary use.

---

## 5. Alternative (flatter, 6 buttons)
For a smaller device/simpler feel, merge **Katalog + Pelanggan** into one:
```
📊 Dashboard
🛒 Penjualan ▾        Pesanan · Invois · Packing
📦 Master ▾           Produk & Harga · Harga per Area · Promo · Toko · Depo · Stok
🗓️ Kunjungan ▾       Rencana (lihat/edit) · Log Kunjungan · Absensi · Tim · Rute
📈 Analitik ▾         Rekap · Performa · Order-Toko · Order-Stok · Galeri · Laporan
⚙️ Sistem ▾           Pengguna
```
Trade-off: fewer top-level items but **Master** becomes a grab-bag mixing product catalog,
customers, depots and stock — less semantically clean. The 7-button version is preferred.

---

## 6. What this does NOT change
- All existing pages/files kept; this is purely a **nav regrouping** (edit `partials/header.html`).
- Field app (sales) nav is separate and unaffected.
- Each page's `data-page` + shared header/footer include remain the mechanism.
- No DB/query changes. Pure IA refactor.

## 7. Next step (only on your go-ahead)
Rewrite `admin/partials/header.html` to the recommended groups, deploy to LXC 113,
and run 3 QA subagents to verify every target page is reachable + active-state correct.