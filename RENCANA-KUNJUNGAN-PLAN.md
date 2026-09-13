# WIM Online — Rencana Kunjungan (Visit Plan) Rework

> **Date:** 2026-09-10
> **Purpose:** Rework the admin **Rencana Kunjungan** page into two menus surfaced by the nav
> dropdown — **(1) Lihat List Kunjungan** (view) and **(2) Edit List Kunjungan** (edit) — with a
> full edit workflow (sales → week/day → drag-drop stores), a rich view (calendar → sales table →
> per-visit detail drill-down), and a **sales-webapp fix separating the check-in selfie from
> "foto tambahan"** (merchandise photos).
>
> **Legend:** AS = admin-server, AD = admin HTML, MB = middleware `serve.py`, SO = sales app.

---

## 1. Nav change

Replace the single `today-plan.html` nav link with a **dropdown** "🗓️ Rencana Kunjungan":
- **👁️ Lihat List Kunjungan** → `today-plan.html` (view)
- **✏️ Edit List Kunjungan** → `plan-edit.html` (edit)

Keeps client-side filtering; two pages.

---

## 2. Edit List Kunjungan (`plan-edit.html`)

Flow (3 steps, each its own view):

1. **Sales list** — all sales members in a table (reuse the same query options as viewing:
   **remove the date filters on top**, keep sales / region / depot dropdowns + search / CSV).
   Click a sales row → go to step 2.
   - Columns: Sales (name/email), Depo, Region, # rencana this week.
2. **Week calendar** — a month/period view: **Week 1 … Week 4**, each with **6 days a week**
   (Mon–Sat). Each day cell shows the date + whether it has a kunjungan list (dot/count).
   Click a day → step 3.
3. **Day editor (drag-drop)** — **two columns**:
   - **Left: Available stores** with a **search bar** + **query by store area (region)** filter.
   - **Right: Kunjungan list** — the plan for that sales/day, **numbered** (1..N). The admin
     **drags a store from left → right** to append it (auto-numbered). Row order = visit order.
   - Save (POST to visit-plan upsert for that user+date), remove-row, reorder buttons.

**Persistence:** reuses `wim_visit_plan(user_id, place_uuid, visit_date, source, status)`. New rows
added from the picker default to `source='route'`, `status='pending'`. Order = the order they appear.

**API:** a new `GET /api/admin/plan-edit/stores` (all stores filtered by region/search, no date
constraint) + POST upsert per (user,date,store). Reuse existing `do_VISIT_PLAN` POST for the write.

---

## 3. View List Kunjungan (`today-plan.html`) — rework

1. **Calendar on top** — a month view; admin picks a **date** → filters the sales table below.
2. **Sales table** (per date) — columns:
   | Sales | Region | Status (🟡 Berjalan / ⚪ Belum Masuk / 🟢 Sudah Selesai) | Nominal Toko dalam Rute | Nominal Toko Luar Rute | Detail |
3. **Detail** (click) → per-sales day drill-down table with, per store:
   - name, time visited (check-in→check-out)
   - **order / no order** (if no order, show **alasan tidak order** in red background)
   - buttons: **Foto Checkin**, **Foto Tambahan**, **Cek Pesanan**, **Stock Toko**

### Detail modals
- **Foto Checkin** — the check-in **selfie** photo of the salesperson.
- **Foto Tambahan** — merchandise photos + their descriptions.
- **Cek Pesanan** — the store's orders (order ID, SKU/items, amounts as in the Pesanan page);
  **greyed out if no order**.
- **Stock Toko** — the store's remaining stock (from `wim_stock_check`).

---

## 4. Sales webapp — check-in selfie vs foto tambahan (bug fix)

**Bug:** currently the check-in triggers `handlePhoto()` which opens the **photos/camera (environment
camera)** and both the check-in photo and "foto tambahan" live in one `photos` array → the admin
cannot tell the check-in selfie apart.

**Fix:**
- **Check-in → selfie camera**: on check-in, open a **selfie (front/user-facing)** camera window.
  After the salesperson takes the selfie it **closes** automatically. Stored as the visit's
  "checkin photo".
- **Foto Tambahan**: a separate button "📸 Foto Tambahan" opens the **environment camera** for
  merchandise photos (+ description) — different flow.
- **Storage:** store the check-in selfie separately so the admin detail can show it. Add a field
  `checkin_photo` to `wim_visits` (base64) OR a `photo_type` on `wim_store_photos`
  (`'selfie'` vs `'tambahan'`). Simplest: keep `wim_visits.photos` for tambahan and add
  `wim_visits.checkin_photo` for the selfie.

---

## 5. Documentation / verification

- `CHANGELOG.md`, this plan, `DATABASE-MAPPING.md` (visit `checkin_photo`).
- Deploy MB → CT111, AS → CT113, SO → CT112.
- **QA:** 3 subagents per function (view flow, edit flow, photos) → iterate fix loop until verdicts good.

---

## Precedence (implement in this order)
1. Nav dropdown + edit page scaffold (sales list → week → day editor) w/ drag-drop + persistence.
2. View rework (calendar + sales table + detail drill-down modals).
3. Photo bug fix (selfie vs tambahan) + admin detail showing them.
4. QA loops.