# Packing List (Per-Hari Dispatch) — Design, Plan & User Flow

> **Status:** Pending implementation · **Date:** 2026-09-11
> Replaces the old SKU-volume packing list with a **per-day dispatch / per-car view**
> inside the **Pesanan** menu (moved OUT of the Laporan menu per the latest instruction).

## 1. What the user asked (recap)
- The packing list must live as a **submenu inside Pesanan** (not under Analitik, not under Laporan).
- The current page is wrong: each row must represent **one day / one car/vehicle to send**, not the total SKU volume.
- Table columns: **Sales Rep · Tanggal Order · H-Tanggal (aging) · Total Qty dikirim (incl bonus) · Jumlah Order**.
- Each row = a different day; **oldest first** (highest priority to send).
- Only **dalam-rute** orders appear here; **luar-rute** orders go in a **separate table**.
- Clicking a **sales name** opens a popup listing that sales' orders for that day (by time received), with:
  - **Cetak Surat Jalan** → downloads a **PDF** of the driver's route.
  - **Cetak Invoice** → downloads a **ZIP** of all invoices in that list.
  - Each order in the list is **clickable** → opens the invoice window (same as the Pesanan page).
- Future (documented, NOT built now): Fleetbase vehicle/product dimensions → show vehicle capacity full/not-full. Not now.

## 2. Data model
No new tables required. All driven off existing `wim_orders`:

| Concept | Source |
|---|---|
| Dalam rute | `wim_orders.off_route_reason IS NULL OR ''` |
| Luar rute | `wim_orders.off_route_reason IS NOT NULL AND != ''` |
| Per-day key | `user_id + DATE(created_at)` |
| Total qty incl bonus | sum of `qty` over `jsonb_array_elements(items)` |
| Jumlah order | `count(*)` |
| Aging (H) | `CURRENT_DATE - DATE(created_at)` (0=today, 1=yellow, ≥2=red) |
| Order time | `created_at` (popup sorts by this ASC) |
| Store/route | `wim_stores` join on `store_uuid` (name, address, lat/lng) |

## 3. Backend endpoints (add to `frontend/serve.py` + proxy in `admin/admin-server.py`)
All are additive `GET` handlers under `/api/analytics/*` (auth: admin role / admin key), proxied by the admin server as `/api/admin/analytics/*`.

1. **`GET /api/admin/analytics/packing-grouped`** — the per-day dispatch table.
   - Filters: `date_from, date_to, depot_id, region_id, user_id`.
   - Returns rows grouped by `user_id + DATE(created_at)` where `off_route_reason` empty:
     `{ sales_rep, user_id, order_date, total_qty, bonus_qty, num_orders, oldest_at, h, status_class }`
   - Ordered **date ASC** (oldest first → highest priority).
2. **`GET /api/admin/analytics/packing-day-orders?user_id=&date=`** — popup list.
   Returns that sales' dalam-rute orders on that calendar day, sorted `created_at ASC`:
   each `{ order_uuid, order_ref, status, created_at, store_name, store_address, items_qty, grand_total, has_invoice }`.
3. **`GET /api/admin/analytics/packing-surat-jalan?user_id=&date=`** — **PDF**.
   reportlab-generated Surat Jalan: header (No SJ, date, sales rep, depot) + sequenced store route
   (1..N) with order ref, store name, address, qty. Returns `application/pdf`.
4. **`GET /api/admin/analytics/packing-invoice-zip?user_id=&date=`** — **ZIP** of invoice PDFs.
   For each order in the day list, generate an invoice PDF (reportlab) and bundle → `application/zip`
   named `invoices-<date>-<n>.zip`.
5. **`GET /api/admin/analytics/packing-luarrute`** — separate table for luar-rute orders
   (`off_route_reason` set), same per-day grouping but tagged, so depo can handle off-route separately.

## 4. Frontend (`admin/packing.html` rewrite + nav)
- **Nav:** move Packing List into a **Pesanan ▾ submenu** (out of Laporan). Adjust `partials/header.html`.
- **Packing page tabs:**
  1. **Dispatch Per Hari (Dalam Rute)** — main table (default): Sales Rep · Tanggal · H (badge: green=0, yellow=1, red=≥2) · Total Qty (incl bonus) · Jumlah Order. Row sorted oldest-first. **Click sales name → popup.**
  2. **Luar Rute** — separate table of off-route orders.
  3. **Muatan SKU** — keep the legacy product-volume loading sheet (still useful to pack actual SKU qty).
- **Popup (per sales/day):** lists that day's orders (time received, clickable → reuse `openOrderDetail`/`renderInvoice`/invoice modal from orders.html) + two buttons:
  - **Cetak Surat Jalan** (⌛→ downloads PDF)
  - **Cetak Invoice (ZIP)** (⌛→ downloads ZIP)
- **Simpan feedback requirement:** (from related request) not applicable here, but download buttons show busy→done state.

## 5. User flow (end-to-end)
1. Depo admin opens **Pesanan → Packing List**.
2. Default tab **Dispatch Per Hari** loads the dispatch table (dalam-rute orders, oldest day at top).
   - Each row = one sales rep + one order date = one car/day to send.
   - **H** badge highlights aging: yellow = 1 day old, red = ≥2 days (priority).
3. Admin clicks a **sales name** → popup opens listing that day's orders (by time received).
   - Admin reviews; each order is clickable and opens the invoice window (same as Pesanan).
   - **Cetak Surat Jalan** → browser downloads a PDF with the numbered store route for the driver.
   - **Cetak Invoice** → browser downloads a ZIP of per-order invoice PDFs.
4. Admin switches to **Luar Rute** tab to see off-route orders (handled separately by design).
5. Admin can open **Muatan SKU** tab to see per-SKU volume to actually load.

## 6. Acceptance criteria
- [ ] Packing List appears as submenu under Pesanan (not Laporan/Analitik).
- [ ] Dispatch table groups oleh sales+hari; row per day; oldest first.
- [ ] H aging badge 0/1/≥2 with green/yellow/red.
- [ ] Total qty includes bonus; Jumlah Order correct.
- [ ] Dalam-rute only here; Luar Rute in its own table.
- [ ] Click sales name → popup with order list (time order) + Cetak SJ (PDF) + Cetak Invoice (ZIP).
- [ ] Order clickable in popup → invoice window.
- [ ] 3 QA subagents verify the flow end-to-end.

## 7. Rollback
- New endpoints are additive `GET`s; old SKU packing page/endpoint retained as "Muatan SKU" tab.
- Nav revert = one-line change in `partials/header.html`. No DB migration required → trivially reversible.
