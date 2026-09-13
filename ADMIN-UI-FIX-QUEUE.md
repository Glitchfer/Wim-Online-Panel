# WIM Admin — UI/Fix Batch Queue (from user review)

> **Date:** 2026-09-10 · **Status:** QUEUED — documented before execution
> Source: direct admin-panel review by user (13 issues). Each fix is planned, then executed,
> then reviewed by 3 subagents per fix. This doc is the master queue + reference.

---

## Master decisions first

1. **Shared header/footer (issue #10):** create ONE master header (+ footer) file that all admin
   pages load, so the navbar is consistent everywhere and editing it once updates all pages.
   Because admin pages are plain HTML served by HTTP (no templating), we use **JS-injected**
   shared partials: `admin/partials/header.html` rendered via a tiny `js/include.js` that each
   page loads and that fills `#appHeader`/`#appFooter`. This gives 1 source of truth for the
   navbar (fixes #1, #5, #10, #11) and a clean reference-style nav.
2. **Navbar restructure (#1, #5, #6, #11):** reference-style grouped menu:
   - **📊 Dashboard**
   - **📈 Analitik** (contains Tim, Kunjungan as sub-tabs — #6; menu appears on ALL pages)
   - **📦 Pesanan** (contains "Order per Toko" + "Edit Order" — #6)
   - **🗂️ Laporan** (NEW menu — holds **Packing List** moved out of Analitik — #3, #7)
   - **📄 Invois**, **📦 Stok**, **⏰ Absensi**
   - **🏷️ Produk & Promo** (single menu w/ dropdown — #11)
   - **🏢 Depo**, **🏬 Toko**, **🗺️ Rute/Maps**, **🗓️ Rencana Kunjungan** (#8 rename)
3. This is one master header applied to every page; page-specific body stays in each .html.

---

## Task queue (each → 3-subagent review)

| # | Fix | Problem | Solution | Priority |
|---|---|---|---|---|
| 1 | Navbar neat (not hand-rolled) | Nav inconsistent/ugly across pages | Use reference-style grouped topnav in master header (grouped menus, dropdowns, cleaner CSS); reused everywhere via shared include | ✅ done (`3707c96`, deployed) |
| 2 | Dashboard: "Lokasi Sales" collides with "Status Tim Hari Ini" | No spacing above Lokasi Sales section; overlaps the team panel | Add `.card{margin-bottom:20px}` so stacked cards are separated | ✅ done (dashboard.html, deployed) |
| 3 | Packing List in wrong menu | It's inside Analitik & Laporan; should be its own "Laporan" menu | Create **Laporan** menu; move Packing List → `packing.html`; remove from Analitik | 🔧 subagent (deleg_1587e6e8 t0) |
| 4 | Analitik filter "by staff member" doesn't work | Sales filter no-ops on analytics page | Added `user_id` filter to performance/order-stock/packing-list/store-orders handlers | ✅ done (`ec29205`, deployed) |
| 5 | Analitik menu missing on most pages | Only appears on Dashboard | Master header now shows Analitik on every page | ✅ done (via #1) |
| 6 | Tim + Kunjungan belong under Analitik; Packing + Order-per-Toko under Pesanan; add Edit Order | IA mismatch | Nav dropdown 'Analitik' groups Tim+Kunjungan (subagent t1); Edit Order feature (subagent t3) | 🔧 subagents |
| 7 | Packing List redesign (per-vehicle/day, priority aging, in-route only) | Current = aggregate volume; wrong concept | **BIG — separate blueprint** (see §Packing-List-Redesign); dedicated execution + review | ⏳ queued (separate) |
| 8 | Rename "Rencana Hari" → "Rencana Kunjungan" | Wrong label | Master header dropdown now labeled "Rencana Kunjungan" | ✅ done (via #1) |
| 9 | Toko edit missing NOO fields (kendaraan, nik,…) | Edit form lacks data captured at NOO creation | Added kecamatan/kelurahan/kode_pos/province/kendaraan/nik/npwp/npwp_name to stores.html + backend return | ✅ done (`c47a242`, deployed) |
| 10 | Broken Depo header; master header/footer | Header inconsistent; no shared file | Master header/footer partials + include.js applied to all 17 pages | ✅ done (`3707c96`, deployed) |
| 11 | Produk + Promo one menu with dropdown | Two separate menus | **🏷️ Produk & Promo** dropdown in header | ✅ done (via #1) |
| 12 | Depo rows clickable → popup of users in that depot | No depot→users drilldown | Row click + modal listing users by depot_id | ✅ done (`c47a242`, deployed) |
| 13 | Route/map filter "Semua Sales" shows others' lines + stores vanish | Filtering broken on map | Fix renderAll/filteredStores | 🔧 subagent (deleg_1587e6e8 t2) |

---

## Packing-List Redesign — separate blueprint (#7)

**Concept (from user):**
- Each row = **one day** (not one SKU), only **dalam-rute** orders. Luar-rute orders appear in a
  separate table.
- Columns: **Sales Rep · Tanggal Order (date orders made) · H-tanggal Order (aging: 1=yellow,
  2=red highlight) · Total qty to be sent (incl bonus) · Number of orders**.
- Rows ordered **oldest first** (highest priority to be sent).
- The route == same route the sales rep got the orders in; driver delivers on the same route,
  visiting only the stores in that day's orders (not every store on the rep's route).
- Click **Sales Rep name** → popup listing that day's orders **by time received**, with
  **Cetak Invoice** (downloads a ZIP of all invoices in the list) and **Cetak Surat Jalan**
  (downloads a PDF of the driver route). Orders themselves are clickable → open the invoice
  window (as in Pesanan).
- Future (Fleetbase): add vehicle dimensions vs product dims to show capacity/full. Now: just
  Sales Rep + order count + oldest order, so depo decides priority vehicle.

**Data needed:** `wim_orders` (in-route only = `source='route'`, not off_route), grouped by
`user_id` + `DATE(created_at)`. Aging = days since oldest order. Qty per SKU (from items JSON)
summed (incl bonus). Server endpoint `/api/admin/packing-day` returning per-day rows + per-rep
order list; print endpoints for invoice-zip + surat-jalan-pdf (need a PDF lib server-side).

**Build order:** this is the biggest item → implement as its own task with dedicated subagents
(frontend redesign + server endpoint + zip/pdf prints), review with 3+ subagents, iterate.

---

## Edit-List-Kunjungan redesign — tracking doc (#7 companion)

**User requirements (recap, from 2 messages):**

1. **Monthly-repeating template, not calendar dates.** In Rencana Kunjungan → Edit List Kunjungan → pick a sales, the plan is `day1..day6 × week1..week4` (4 weeks × 6 days = 24 slots), REPEATED every month. Each different day a sales visits different stores in a different region. Currently the UI shows calendar days of the current month — must become the 4×6 day/week template grid.
2. **Store picker filterable by the 4 administrative address inputs** (provinsi → kota → kecamatan → kelurahan) from the NOO region work, so admin can bundle stores close together (by kecamatan/kelurahan) to reduce travel time. Ensures valid data + good filtering.
3. **Route map on the edit screen.** Beside the numbered drag-drop store list, show a map (like the Rute page): numbered markers 1..N matching list order; click/hover shows store name + details; a **red polyline** connects the ordered points; map updates live whenever the list order changes (so admin can fix out-of-place stores by moving up/down).
4. **Simpan (save) button tactile feedback + prominent confirmation.** The current save button has no pressed/loading state and the confirmation is a tiny toast in the top-right corner (too small). Fix: pressing Simpan gives clear pressed/loading feedback, and success/error confirmation is prominent (large, centered/inline), not a small corner toast.

**Process:** consult subagents on best solution (data model, UI, map) → implement → 3-subagent QA per feature.

---

## Execution order (dependency-first)

PB-A: **#10 master header/footer** (foundation) → then #1, #5, #8, #11 all ride on it.
PB-A: **#2 dashboard spacing**, **#4 analytics filter**, **#9 store NOO fields**, **#12 depo popup**, **#13 route filter**.
PB-B: **#3 Laporan menu + move Packing List**, **#6 IA restructure**, **+ Edit Order button**.
PB-C: **#7 Packing List redesign** (separate blueprint, subagent-driven).

Each PB → commit + 3-subagent review → iterate on bad feedback → push.