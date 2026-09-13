# WIM Online — User Flows & UI/UX Specification

> Complete user flow analysis covering all use cases from the legacy GooVi + KlikOrder
> replacement, implemented as a **standalone PostgreSQL-backed system** (not dependent on Fleetbase).
> **Purpose:** Reference for AI subagent coders during implementation and for QA testers
> during validation. Every flow is defined with step-by-step paths, states, error handling,
> and data persistence rules.

---

## Table of Contents

1. [Personas & Actors](#1-personas--actors)
2. [App Architecture Overview](#2-app-architecture-overview)
3. [Authentication Flow](#3-authentication-flow)
4. [Dashboard Flow](#4-dashboard-flow)
5. [Absensi (Attendance) Flow](#5-absensi-attendance-flow)
6. [Visit Card (Kunjungan) Flow](#6-visit-card-kunjungan-flow)
7. [NOO (New Outlet Opening) Flow](#7-noo-new-outlet-opening-flow)
8. [Order Management Flow](#8-order-management-flow)
9. [Report & Analytics Flow](#9-report--analytics-flow)
10. [Admin Management Flow](#10-admin-management-flow)
11. [Route Management Flow](#11-route-management-flow)
12. [Promo Management Flow](#12-promo-management-flow)
13. [Export & Data Download Flow](#13-export--data-download-flow)
14. [Settings & Configuration Flow](#14-settings--configuration-flow)
15. [Edge Cases & Error States](#15-edge-cases--error-states)
16. [Data Flow Architecture](#16-data-flow-architecture)
17. [UI/UX Improvements Log](#17-uiux-improvements-log)

---

## 1. Personas & Actors

### Persona A: Sales Rep (Field Sales)
- **Role:** `sales` in WIM Online, `jenis_sales` = TO, Motoris, SPC, SPG, Kanvaser
- **Primary device:** Mobile phone (Android/iOS via browser), limited desktop
- **Goal:** Complete daily visit plan, record attendance, take orders, submit reports
- **Pain points (from live data):** 51% of out-route orders placed via WA/Telepon instead of app; cramped stock-check UX leads to reps skipping it

### Persona B: Depot Admin (Supervisor)
- **Role:** `admin` in WIM Online, Admin_Wilayah in legacy system
- **Primary device:** Desktop + mobile
- **Goal:** Manage sales reps, route plans, review reports, export data, handle admin orders
- **Pain points:** Dual-system data entry (GooVi + KlikOrder), no unified dashboard

### Persona C: Super Admin (Management)
- **Role:** `admin` with full system access
- **Primary device:** Desktop
- **Goal:** Full analytics, promo management, user & product management, system configuration
- **Pain points:** No promo/free-product data in export history, vendor lock-in on username changes

---

## 2. App Architecture Overview

### Navigation Structure

```
Bottom Nav (mobile-first, persistent across all pages)
┌─────────┬─────────┬─────────┬─────────┬─────────┐
│ 🏠      │ ⏰      │ 📋      │ ➕      │ 📊      │
│ Beranda │ Absensi │ Kunjungan│ NOO    │ Laporan │
└─────────┴─────────┴─────────┴─────────┴─────────┘
```

### Page Map

| Slug | Page | Access | Persona | Status in V1 |
|------|------|--------|---------|-------------|
| `index.html` | Login | Public | All | ✅ Built |
| `dashboard.html` | Dashboard | Auth required | All | ✅ Built |
| `absensi.html` | Absensi | Auth required | Sales | ✅ Built |
| `visit-card.html` | Kunjungan | Auth required | Sales | ✅ Built |
| `noo.html` | NOO | Auth required | Sales | ✅ Built |
| `report.html` | Laporan | Auth required | Sales | ✅ Built |
| `admin.html` | Admin Panel | Auth required (admin role) | Admin | 🟡 Shell only |
| — | Order Create | Auth required | Sales | 🔴 Not built |
| — | Store Detail | Auth required | Sales | 🟡 Modal only |
| — | Promo Manager | Auth required (admin) | Admin | 🔴 Not built |
| — | Route Map | Auth required | Sales | 🔴 Not built |
| — | Stock Check | Auth required | Sales | 🔴 Stub only |

### API Endpoint Map

| Endpoint | Method | Purpose | Auth | Status |
|----------|--------|---------|------|--------|
| `/api/auth/login` | POST | Email/password login | No | ✅ Built |
| `/api/auth/session` | GET | Validate session cookie | Cookie | ✅ Built |
| `/api/auth/logout` | POST | Destroy session | Cookie | ✅ Built |
| `/api/dashboard` | GET | Per-user dashboard data | Cookie | ✅ Built |
| `/api/absensi` | GET/POST | Attendance CRUD | Cookie | ✅ Built |
| `/api/stores` | GET | Today's visit plan stores | Cookie | ✅ Built |
| `/api/stores/all` | GET | Search all stores | Cookie | ✅ Built |
| `/api/visit_plan` | POST | Add luar rute store | Cookie | ✅ Built |
| `/api/visits` | GET/POST | Visits CRUD | Cookie | ✅ Built |
| `/api/report` | GET | Per-user report | Cookie | ✅ Built |
| `/api/log` | POST | Client-side logging | Cookie | ✅ Built |
| `/api/logs` | GET | Read server logs | Cookie | ✅ Built |
| `/api/stores/{id}/last-order` | GET | Last order per store | Cookie | ✅ Built |
| `/api/stores/orders` | GET | Store order history | Cookie | ✅ Built |
| `/api/stock` | POST | Stock check | Cookie | ✅ Built |
| `/api/admin/*` | — | Admin-specific endpoints | Cookie+Role | 🔴 Not built |
| `/api/orders/*` | — | Order CRUD endpoints | Cookie | 🔴 Not built |
| `/api/stock/*` | — | Stock check endpoints | Cookie | 🔴 Not built |
| `/api/promos/*` | — | Promo management | Cookie+Role | 🔴 Not built |

---

## 3. Authentication Flow

### 3.1 Login

**Actor:** All personas (Sales Rep, Depot Admin, Super Admin)

**Entry point:** `POST /api/auth/login` (from `index.html`)

**Step-by-step:**

```
1. USER opens index.html → sees login form
   - Email field (placeholder: "nama@perusahaan.com")
   - Password field (placeholder: "••••••••")
   - "Masuk" button
   - Empty state: all fields blank, no pre-filled data

2. USER enters email + password → taps "Masuk"
   UI: Button shows "Memverifikasi...", disabled

3. FRONTEND sends POST /api/auth/login {email, password}
   - Content-Type: application/json
   - No cookie needed (unauthenticated)

4. BACKEND validates:
   a. Read body → parse JSON
      - Error: empty body → 400 {"error": "Invalid JSON"}
      - Error: body is not object (array, string, number) → 400 {"error": "Request body must be a JSON object"}
   b. Extract email, trim + lowercase
   c. Extract password
   d. Check email + password not empty → 400 {"error": "Email dan password diperlukan"}
   e. Rate limit check (5 attempts per email+IP per 5 minutes)
      - Blocked: 429 {"error": "Terlalu banyak percobaan. Coba lagi dalam X detik"}
   f. Query PostgreSQL: wim_users table WHERE email=%s AND status='active' AND deleted_at IS NULL
      - Not found → 401 {"error": "Email atau password salah"} + record fail
   g. Verify bcrypt password
      - Wrong → 401 {"error": "Email atau password salah"} + record fail
   h. On success: clear rate limit attempts
   i. Create session: INSERT wim_auth.sessions (id, user_id, expires_at)
   j. Return 200 with Set-Cookie: wim_session=xxx (HttpOnly, SameSite=Lax, 7 days)
      Body: {token, user: {name, email, role, karyawan_id, driver_uuid}}

5. FRONTEND stores user info in sessionStorage:
   - wim_user_name, wim_user_email, wim_user_role, wim_driver_id, wim_token

6. FRONTEND redirects to dashboard.html
```

**Session persistence:** Cookie is HttpOnly (not accessible to JS), auto-sent on every request via `credentials: 'same-origin'`.

**States:**
| State | UI | Notes |
|-------|----|-------|
| Loading | Button "Memverifikasi...", disabled | 3-second max |
| Error: empty fields | Red error banner "Masukkan email dan password" | |
| Error: wrong credentials | Red error banner "Gagal: Email atau password salah" | |
| Error: rate limited | Red error banner "Gagal: Terlalu banyak percobaan..." | |
| Error: network | Red error banner "Gagal: Network error..." | |
| Success | Redirect to dashboard.html | |

### 3.2 Session Validation

**Used by:** Every page on DOMContentLoaded

```
1. FRONTEND calls GET /api/auth/session (cookie auto-sent)
2. BACKEND reads wim_session cookie → looks up in cache + PostgreSQL
   - No cookie → 401 {"error": "Session expired"}
   - Invalid cookie → 401 {"error": "Session expired"}
   - Expired → 401 {"error": "Session expired"} + clears cookie
3. On success → returns {user: {name, email, role, karyawan_id, driver_uuid}}
4. FRONTEND stores user in sessionStorage
5. On failure → FRONTEND redirects to index.html
```

### 3.3 Logout

```
1. USER taps logout button (⏻ in dashboard header)
2. Confirm dialog: "Keluar dari aplikasi?"
3. POST /api/auth/logout → destroys session (PostgreSQL + cache)
4. Set-Cookie: wim_session=; Max-Age=0
5. Clear sessionStorage
6. Redirect to index.html
```

---

## 4. Dashboard Flow

**Actor:** Sales Rep

**Entry point:** `dashboard.html` (after login)

**API call:** `GET /api/dashboard` (per-user, session-scoped)

**Backend queries (PostgreSQL):**
- `wim_visit_plan` WHERE user_id=X AND visit_date=today → plan counts by source
- `wim_orders` WHERE driver_assigned_uuid=driver_uuid → order count
- `wim_attendance` WHERE user_id=X AND date=today → clock in/out status
- `wim_visits` WHERE user_id=X AND DATE(checkin_at)=today → visit count + recent 5

**Response shape:**
```json
{
  "plan": {"route": 3, "luar_rute": 2, "total": 5},
  "orders": 1,
  "attendance": {"clockIn": "08:00", "clockOut": "17:00", "duration": "9h"},
  "visitsToday": 4,
  "recentVisits": [
    {"placeName": "TOKO BERKAH", "checkinAt": "2026-09-08 08:15", "checkoutAt": "2026-09-08 08:45", "status": "visited", "source": "route"}
  ]
}
```

**UI layout:**
```
┌────────────────────────────────┐
│  ⏻ (logout)                   │
│  Halo, [user name]!           │
│  WIM Online — Dashboard       │
├────────────────────────────────┤
│ ┌──────┐ ┌──────┐             │
│ │  5   │ │  1   │             │
│ │Kunjgn│ │Pesanan│             │
│ └──────┘ └──────┘             │
│ ┌──────┐ ┌──────┐             │
│ │  4   │ │  🕐  │             │
│ │Dikunj│ │Absensi│             │
│ └──────┘ └──────┘             │
├────────────────────────────────┤
│ Aksi Cepat                    │
│ ┌─────────┬──────────┐       │
│ │ ⏰ Absen│ 📋 Kunjgn│       │
│ ├─────────┼──────────┤       │
│ │ ➕ NOO  │ 📊 Lapor │       │
│ └─────────┴──────────┘       │
├────────────────────────────────┤
│ Rencana Kunjungan Hari Ini    │
│ "5 toko"                      │
│ ┌ TOKO BERKAH (Dalam Rute)  ›│
│ ┌ TOKO JAYA (Dalam Rute)    ›│
│ ┌ TOKO BARU (Luar Rute)     ›│
├────────────────────────────────┤
│ Aktivitas Terakhir             │
│ 📍 TOKO BERKAH 08:15 • Dalam  │
│ 📍 TOKO JAYA  09:30 • Dalam   │
└────────────────────────────────┘
```

**States:**
| State | UI |
|-------|----|
| Loading | Spinner in store list |
| Empty (no plan) | "Belum ada kunjungan hari ini" |
| No activity | "Belum ada aktivitas hari ini" |
| Error | "Gagal memuat data: [message]" |

**User interactions:**
- Tap a store → navigates to `visit-card.html?store=<uuid>`
- Tap button → navigates to respective page
- Tap ⏻ → triggers logout

---

## 5. Absensi (Attendance) Flow

**Actor:** Sales Rep

**Entry point:** `absensi.html` (from bottom nav or dashboard shortcut)

**API calls:**
- `GET /api/absensi?date=YYYY-MM-DD` → load today's attendance
- `POST /api/absensi {action: "clock_in", ...}` → clock in
- `POST /api/absensi {action: "clock_out", ...}` → clock out

### 5.1 Clock In

```
1. USER opens absensi.html
   → FRONTEND calls GET /api/absensi?date=today
   → If no record → shows "Belum Absen", "Mulai hari kerja Anda"

2. USER taps "🟢 Mulai Kerja"

3. FRONTEND checks if clockInPhoto exists in localStorage
   a. NO photo → opens camera modal (takePhoto('clockIn'))
      - Try getUserMedia (front camera environment)
      - Fallback: file input with capture="environment"
      - USER takes photo → compressed to 800px JPEG 0.6 → stored in localStorage
      - Continue to clockIn()

4. FRONTEND gets GPS location (3s timeout, low accuracy, 60s cache)
   - Success: lat, lng captured
   - Timeout/fail: lat, lng = null

5. FRONTEND sends POST /api/absensi {
     action: "clock_in",
     date: today,
     time: "08:00",
     photo: "data:image/jpeg;base64,...",
     lat: -6.2088, lng: 106.8456
   }

6. BACKEND: INSERT INTO wim_attendance (user_id, date, clock_in, clock_in_photo, lat, lng)
   ON CONFLICT (user_id, date) DO UPDATE SET clock_in, clock_in_photo...

7. UI updates: "🕐 Sedang Bekerja", "Mulai: 08:00", status icon changes, clock-out section appears
```

### 5.2 Clock Out

```
1. USER taps "🔴 Selesai Kerja"

2. FRONTEND checks if clockOutPhoto exists → same camera flow as clock in

3. FRONTEND calculates duration from clockInTs to now

4. FRONTEND sends POST /api/absensi {
     action: "clock_out",
     date: today,
     time: "17:00",
     photo: "data:image/jpeg;base64,...",
     duration: "9h"
   }

5. BACKEND: UPDATE wim_attendance SET clock_out, clock_out_photo, duration

6. UI updates: "✅ Selesai Kerja", "Selesai: 17:00", "Durasi: 9h"
   Both sections hidden, reset button shown
```

**States:**
| State | UI | Icon |
|-------|----|------|
| Not started | "Belum Absen" / "Mulai hari kerja Anda" | ⏰ |
| Working | "Sedang Bekerja" / "Mulai: 08:00" | 🕐 |
| Finished | "Selesai Kerja" / "Selesai: 17:00" / "Durasi: 9h" | ✅ |
| Camera error | Alert "Gagal mengakses kamera" | — |
| GPS error | Clock in proceeds without location | — |

**Data persistence:**
- **Primary:** PostgreSQL via API (server-side, durable)
- **Cache:** localStorage (wim_absen_today) for offline resilience
- Photo compression: 800px max width, JPEG 0.6 quality

---

## 6. Visit Card (Kunjungan) Flow

**Actor:** Sales Rep

**Entry point:** `visit-card.html` (from bottom nav or dashboard)

**API calls:**
- `GET /api/stores` → today's planned stores
- `GET /api/stores/all?q=search` → search all stores
- `POST /api/visit_plan {place_uuid}` → add luar rute store
- `POST /api/visits {action: "checkin", ...}` → check in
- `POST /api/visits {action: "checkout", ...}` → check out

### 6.1 View Today's Visit Plan

```
1. FRONTEND calls GET /api/stores → returns {stores: [...], total: N}

2. UI renders store list with:
   - Store name
   - City
   - Badge: "📍 Dalam Rute" (green) or "📍 Luar Rute" (yellow)
   - Status dot: ✅ if visited, else store initial letter

3. USER can filter by:
   - "Semua" (all stores)
   - "Dalam Rute" (source=route)
   - "Luar Rute" (source=luar_rute)
```

### 6.2 Visit a Store (Check-in → Timer → Check-out)

**This is the core workflow — the most complex flow in the app.**

```
1. USER taps a store in the list → opens modal

   Modal shows:
   ┌──────────────────────────────┐
   │ TOKO BERKAH (PASAR TANAH     │
   │ ABANG)                       │
   │ Alamat: Jl. Contoh No. 123   │
   │                              │
   │        ⏱ 3:00                │
   │   Waktu minimum kunjungan    │
   │                              │
   │ 📍 Check-in di Toko          │
   │ 📸 Ambil Foto                │
   │ 📦 Input Stok                │
   │ 🛒 Buat Pesanan              │
   │ ❌ Tidak Ada Pesanan         │
   │                              │
   │  ✅ Selesaikan Kunjungan     │
   └──────────────────────────────┘

2. 3-minute timer starts automatically on modal open
   - Visual: mm:ss countdown from 3:00
   - Timer must complete before "Selesaikan Kunjungan" is enabled
   - Timer runs in browser (VisitTimer class), not server-side

3. USER taps "📍 Check-in di Toko"
   → Frontend sends POST /api/visits {action: "checkin", place_uuid, place_name, lat, lng, source}
   → BACKEND validation:
     - place_uuid required → 400 "place_uuid diperlukan"
     - No open check-in for this place → 409 "Kunjungan sudah check-in, selesaikan dulu"
     - INSERT INTO wim_visits (user_id, store_uuid, checkin_at, lat, lng, source)
   → Button changes to "✅ Check-in Berhasil" (green, disabled)
   → checkinDone = true

4. OPTIONAL: USER taps "📸 Ambil Foto"
   → Opens camera modal (same as absensi)
   → Capture photo(s) → compressed → stored in storePhotos array
   → Photo preview + status "✅ Foto berhasil"
   → Can take multiple photos

5. OPTIONAL: USER taps "📦 Input Stok"
   → Prompt: "Stok SANQUA PET 220ML (karton):"
   → Sends POST /api/stock {store_uuid, product_uuid, quantity}
   → INSERT INTO wim_stock_check (user_id, store_uuid, product_uuid, quantity, checked_at)

6. OPTIONAL: USER taps "🛒 Buat Pesanan"
   → Requires checkinDone = true (otherwise alert "Check-in dulu!")
   → Stores currentStore in localStorage
   → Redirects to noo.html?store=<uuid>
   → (This is the order creation flow — see Order Management §8)

7. OPTIONAL: USER taps "❌ Tidak Ada Pesanan"
   → Opens no-order reason modal:
     ┌──────────────────────────────┐
     │ Alasan Tidak Ada Pesanan    │
     │ [Dropdown: Stok masih penuh │
     │  Toko tutup                  │
     │  Pemilik tidak ada           │
     │  Harga belum cocok           │
     │  Lainnya (tulis sendiri)]    │
     │                              │
     │ [Lainnya: textarea]          │
     │                              │
     │       [Kirim] [Batal]        │
     └──────────────────────────────┘
   → On submit: checkout with status='no_order' + reason in notes
   → Modal closes, store marked as visited

8. USER taps "✅ Selesaikan Kunjungan"
   → Requires checkinDone = true (otherwise alert)
   → Requires timer complete (otherwise alert "Tunggu timer selesai")
   → Sends POST /api/visits {action: "checkout", place_uuid, place_name, photos, notes, durationSeconds, status}
   → BACKEND validation:
     - No open check-in → 400 "Belum ada check-in untuk toko ini"
     - UPDATE wim_visits SET checkout_at, duration_seconds, photos, notes, status
     - UPDATE wim_visit_plan SET status='visited'
   → Alert "✅ Kunjungan selesai!"
   → Modal closes, store list refreshes

9. Double-checkin guard:
   - If USER tries to check-in again (same place, open checkout_at=NULL) → 409
   - Must re-open store modal, complete checkout, then can check-in again

10. Double-checkout guard:
    - If USER tries to checkout without checkin → 400
    - If USER tries to checkout twice → 400 (no open check-in record)
```

### 6.3 Add Luar Rute Store

```
1. USER taps "➕ Tambah Toko Luar Rute" (below store list)

2. Modal opens with search box:
   ┌──────────────────────────────┐
   │ Tambah Toko Luar Rute       │
   │ [Cari nama toko...]          │
   │                              │
   │ ┌ TOKO ABC (Jakarta) ○     │
   │ ┌ TOKO XYZ (Bandung) ○     │
   │ ┌ TOKO 123 (Surabaya) ✓    │
   │                              │
   │ [✅ Tambahkan ke Daftar]    │
   │ [Batal]                     │
   └──────────────────────────────┘

3. USER types in search → GET /api/stores/all?q=search
   - Returns stores with inPlan flag
   - Already-planned stores show "Sudah ada" badge, disabled

4. USER taps a store → store selected (highlighted, ● indicator)
   → "Tambahkan ke Daftar" becomes enabled

5. USER taps "Tambahkan ke Daftar"
   → POST /api/visit_plan {place_uuid}
   → BACKEND: INSERT INTO wim_visit_plan (user_id, place_uuid, visit_date, source='luar_rute', status='pending')
     ON CONFLICT DO NOTHING
   → Alert "Toko ditambahkan ke daftar kunjungan"
   → Modal closes, store list refreshes
```

**States:**
| State | UI |
|-------|----|
| Loading stores | Spinner |
| No stores | "Tidak ada toko dalam daftar" |
| Filter: route | Only stores with "Dalam Rute" badge |
| Filter: luar_rute | Only stores with "Luar Rute" badge |
| Empty search | "Tidak ada toko tersedia" |
| Store already planned | "Sudah ada" badge, disabled selection |
| Checkin done | "✅ Check-in Berhasil" (green, disabled) |
| Checkin pending | "📍 Check-in di Toko" (primary) |
| Timer running | mm:ss countdown |
| Timer done | "Selesai ✅" (green text) |
| Enable finish | Timer done + checkin done → button enabled |
| Camera error | Alert "Gagal mengakses kamera" |
| Photo taken | "✅ Foto berhasil" |
| Submitting no-order | — |
| Server error | Alert "Gagal: [message]" |

**Timeline (minimum visit duration):**
```
t=0:      Modal opens → timer starts (3:00)
t=0:      Check-in (must be done for any action)
t=0-3:00  Photo, stock, order, or no-order
t=3:00:   Timer done → "Selesaikan Kunjungan" enabled
t=3:00+:  Checkout submitted
```

---

## 7. NOO (New Outlet Opening) Flow

**Actor:** Sales Rep

**Entry point:** `noo.html` (from bottom nav, or from visit-card redirect)

**API calls:**
- `POST /api/stores` → create new store
- `POST /api/stores/draft` → save NOO as draft (future)
- `POST /api/visit_plan` → add to today's visit plan after creation

**Form fields (14+):**
```
┌──────────────────────────────────┐
│ 📝 NOO — Toko Baru              │
│                                  │
│ Nama Toko * [______________]     │
│ Nama Pemilik * [______________]  │
│ No. HP * [________________]      │
│ Kontak Person [______________]   │
│                                  │
│ Alamat * [____________________]  │
│ │ [__________________________]  │
│                                  │
│ Provinsi [▼ Pilih provinsi]     │
│ Kota [▼ Pilih kota]             │
│ Kecamatan [______________]      │
│ Kelurahan [______________]      │
│ Kode Pos [______________]       │
│                                  │
│ Channel * [▼ GT / MT / Horeka]  │
│ Kategori * [▼ Retail Kecil /...]│
│ Jenis Kendaraan [______________]│
│                                  │
│ GPS: -6.2088, 106.8456 📍       │
│ [Deteksi Otomatis / Input Manual]│
│                                  │
│ NIK [________________]           │
│ NPWP [________________]          │
│ Nama NPWP [______________]      │
│                                  │
│ [📷 Foto Toko (opsional)]       │
│                                  │
│ [✅ Simpan] [❌ Batal]           │
└──────────────────────────────────┘
```

**Flow:**
```
1. USER opens noo.html
   - If redirected from visit-card, store context in localStorage
   - GPS auto-detects current location (3s timeout)

2. USER fills form fields (required marked with *)
   - Nama Toko, Nama Pemilik, No. HP, Alamat, Channel, Kategori

3. USER taps "📍 Deteksi Otomatis" for GPS
   - Or manually enters coordinates

4. USER taps "✅ Simpan"

5. FRONTEND validates required fields
   - Missing: highlights field + error message

6. FRONTEND creates Store via local API:
   POST /api/stores {
     name, street1, city, province, district, subdistrict,
     postal_code, latitude, longitude,
     phone, owner_name, owner_nik, owner_npwp,
     channel, category, vehicle_type
   }

7. INSERT INTO wim_pelanggan (...) VALUES (...)

8. If redirected from visit-card → adds to visit plan:
   POST /api/visit_plan {place_uuid: new_store_uuid}

9. Success: Alert "Toko baru berhasil dibuat!" → redirect to visit-card.html
```

**NOT YET IMPLEMENTED but required from GooVi:**
- OTP verification (WA to depo PIC)
- NOO draft save
- Category selection with icons
- Channel auto-population from API

---

## 8. Order Management Flow

**Actor:** Sales Rep, Depot Admin

**Status:** 🔴 NOT BUILT (requires new backend endpoints + frontend)

### 8.1 Create Order (Sales Rep at Store)

**Flow from legacy system:**

```
1. USER is at store visit → taps "🛒 Buat Pesanan"
   → Redirects to order creation page (or modal)

2. Product selection:
   - Brand filter (SANQUA, LEVONTE, BATAVIA, etc.)
   - Product category filter (Air Mineral, Minuman Ringan, dll.)
   - Product search
   - Product grid/list with name, price, stock

3. Cart:
   - Add items with quantity
   - Auto-calculate totals
   - Apply promos (bundling, strata, discounts)
   - View free items from promos

4. Promo check:
   - GET /api/promos/store/{storeID} → active promos for store
   - POST /api/promos/check-bundling → bundling eligibility
   - POST /api/promos/check-strata → strata discount levels
   - POST /api/promos/calculate-combined → combined discounts

5. Checkout:
   - OTP verification (optional, to store owner WA)
   - Confirm order
   - POST /api/orders {customer_id, items, promos, payment_method, meta}
   - INSERT INTO wim_orders + wim_order_items
   - Generate order reference
   - QR code for warehouse scanning

6. Order confirmation:
   - Show order summary
   - Option to download QR/barcode
   - Complete visit
```

**States:**
| State | UI |
|-------|----|
| Loading products | Spinner |
| No products | "Tidak ada produk tersedia" |
| Empty cart | "Keranjang masih kosong" |
| Promo applied | "Diskon strata: Rp 15.000" / "Bonus: 1 karton Free" |
| Checkout success | "✅ Pesanan berhasil dibuat!" |
| OTP sent | "Kode OTP telah dikirim ke WA pemilik toko" |

### 8.2 Admin Order (Create Order for Store)

**Actor:** Depot Admin

```
1. ADMIN opens admin order page
2. Selects store (search by name/code)
3. Same product selection as sales rep
4. Can override prices or add ad-hoc items
5. No OTP verification needed (admin override)
6. Order created with meta.ordered_by_admin = true
```

### 8.3 Order History

```
1. USER opens order history
2. GET /api/orders?user_id=X&period=month
3. List: order date, store, total, status, promo info
4. Each order expandable → line items, bonuses, freebies
```

---

## 9. Report & Analytics Flow

**Actor:** Sales Rep

**Entry point:** `report.html` (from bottom nav)

**API call:** `GET /api/report?period=bulanan`

**Backend queries (PostgreSQL):**
- Attendance count this month
- Total visits this month
- Distinct stores visited this month
- Orders assigned to driver
- Daily breakdown (last 7 days): date, clock in, clock out, duration, visits

**UI layout:**
```
┌────────────────────────────────┐
│ ← Laporan                     │
│ WIM Online — Laporan Saya     │
├────────────────────────────────┤
│ ┌──────┐ ┌──────┐             │
│ │  20  │ │  85  │             │
│ │Hari  │ │Kunjgn│             │
│ │Masuk │ │      │             │
│ └──────┘ └──────┘             │
│ ┌──────┐ ┌──────┐             │
│ │  42  │ │  12  │             │
│ │Toko  │ │Pesanan│             │
│ └──────┘ └──────┘             │
├────────────────────────────────┤
│ Ringkasan Bulan Ini           │
│ 📅 September 2026             │
│ ⏰ Absensi: 20 hari masuk     │
│ 📍 Kunjungan: 85 kali ke 42   │
│ 📋 Pesanan ditugaskan: 12     │
├────────────────────────────────┤
│ 📥 Export Data                 │
│ 📍 Export Kunjungan Saya (JSON)│
│ ⏰ Export Absensi Saya (JSON)  │
│ 📊 Export Laporan (CSV)        │
├────────────────────────────────┤
│ Aktivitas 7 Hari Terakhir     │
│ 📅 08 Sep • 🕐 08:00-17:00    │
│               • 📍 5 kunjungan│
│ 📅 07 Sep • 🕐 08:15-16:45    │
│               • 📍 3 kunjungan│
└────────────────────────────────┘
```

**Export functions:**
- `exportVisits()` → `GET /api/visits?date=2026-09-01&date=2026-09-30` → JSON download
- `exportAttendance()` → `GET /api/absensi?date=2026-09-01&date=2026-09-30` → JSON download
- `exportCSV()` → Fetch all data → build CSV blob → download

### 9.1 Super Admin Report (NOT BUILT)

**Required from legacy systems:**
- Visit monitoring (daily/monthly with filters)
- Photo gallery with descriptions
- Visit recap per sales member
- Attendance & photo check-in report
- Store stock check report
- Out-of-route order report
- Sales performance per depot (charts)
- Order vs stock analysis
- Order history export
- Shipped order detail export
- Surat tugas (task document) list + export
- Packing list download
- Invoice PDF mass download

---

## 10. Admin Management Flow

**Actor:** Depot Admin, Super Admin

**Status:** 🟡 SHELL ONLY (admin.html exists, but NO backend endpoints)

### 10.1 Admin Dashboard (NOT BUILT)

**Required from legacy systems:**
- KPI cards: Total Omset, Total Invoice, Total Qty, Total Pelanggan, Avg Order
- Trend Penjualan Harian (daily sales trend line chart)
- Order Source donut (sales vs admin vs pelanggan)
- Penjualan Per Depo (sales by depot bar chart)
- Status Pesanan donut (Batal, Dikirim, Dipesan, Pending, Selesai)
- Penjualan Per Sales (sales per salesperson line chart)
- Top Produk (top 10 products by qty - horizontal bar)
- Distribusi Produk Per Depo (stacked bar)

### 10.2 Master Data Management (NOT BUILT)

**Required from legacy systems:**
| Module | CRUD | Import | PostgreSQL Table |
|--------|------|--------|-----------------|
| Depo (Depot) | ✅ | ✅ | `wim_depo` |
| Karyawan (Employee) | ✅ | ✅ | `wim_karyawan` |
| User | ✅ | ✅ | `wim_users` (linked to karyawan) |
| Pelanggan (Store) | ✅ | ✅ | `wim_pelanggan` (14+ fields) |
| Produk (Product) | ✅ | — | `wim_produk` (multi-brand catalog) |
| Rencana Kunjungan (Visit Plan) | ✅ | ✅ | `wim_visit_plan` (4-week × 5-day CSV) |
| Kendaraan (Vehicle) | ✅ | — | `wim_kendaraan` |
| Supplier | ✅ | — | `wim_supplier` |
| Kategori Pelanggan | ✅ | ✅ | `wim_store_categories` |
| Channel | ✅ | — | `wim_channels` |

### 10.3 Admin Order Entry (NOT BUILT)

**From legacy system:**
- Select store
- Browse products
- Create order with admin override
- Packing list download
- Invoice PDF

### 10.4 Promo Management (NOT BUILT)

**From legacy system:**
- Promo CRUD: nama_promo, jenis_promo (bundling, strata, diskon, bonus), status, periode
- SKU-level promo assignment → `wim_promos` + `wim_promo_items`
- Promo catalog download
- Bonus product tracking in exports

### 10.5 User Session Management (NOT BUILT)

**From legacy system:**
- View all active sessions → `wim_auth.sessions`
- Force-reset session
- Bulk session reset
- Single-session lockout enforcement (optional)

---

## 11. Route Management Flow

**Actor:** Depot Admin, Super Admin

**Status:** 🔴 NOT BUILT

### 11.1 Route Plan Import

```
1. ADMIN prepares CSV file (4-week cycle × 5-day week)
   Columns: employee_id, day_of_week, week_of_month, store_id, order

2. Upload via import endpoint
   POST /api/admin/visit-plans/import (multipart file)

3. BACKEND processes:
   - Parse file
   - Validate stores exist in wim_pelanggan
   - INSERT INTO wim_visit_plan entries for each day
   - Return success/failure report

4. UI shows import result: "235 kunjungan berhasil diimpor, 3 gagal"
```

### 11.2 Route Plan Assignment

```
1. ADMIN views all sales reps
2. Selects a rep → sees their route for the week
3. Can add/remove stores from route
4. Can set priority order
5. Can mark stores as in-route or out-of-route
```

### 11.3 Route Map Visualization

```
1. SALES REP opens route map view
2. Shows all today's stores on map with markers
3. In-route markers: green, in planned order
4. Out-route markers: orange
5. Visited stores: checkmark overlay
6. Tap marker → open store detail
```

---

## 12. Promo Management Flow

**Actor:** Super Admin

**Status:** 🔴 NOT BUILT (requires custom Promo model in PostgreSQL)

### 12.1 Promo Types

**From legacy system:**
| Type | Description | Example |
|------|-------------|---------|
| Bundling | Buy X, get Y free | Buy 10 SANQUA PET 550ML, get 1 free |
| Strata | Tiered discount based on qty | 10-20 pcs: 5% off, 21-50: 10% off |
| Diskon | Direct discount | Rp 5,000 off per item |
| Bonus | Free product with purchase | Free LEVONTE CUP with SANQUA order |

### 12.2 Promo Lifecycle

```
1. ADMIN creates promo: POST /api/admin/promos
   {nama_promo, jenis_promo, status, periode_start, periode_end, depo_id, sku_produk, harga_strata, bonus_sku, bonus_qty}
   → INSERT INTO wim_promos

2. Promo appears in product catalog for sales reps
   - Products with active promo show "PROMO" badge
   - Price shows original + promo price

3. During order creation:
   - Cart auto-checks promo eligibility
   - Bundling: auto-adds free item when threshold met
   - Strata: recalculates discount based on cart qty
   - Combined discount calculation

4. Fulfillment:
   - Free items shown in order line items (is_bonus flag)
   - Export includes promo name + bonus items
   - Packing list includes free items
```

---

## 13. Export & Data Download Flow

**Actor:** All personas

**Built for sales rep:**
| Export | Format | API | Notes |
|--------|--------|-----|-------|
| My Visits | JSON | GET /api/visits | Date range filter |
| My Attendance | JSON | GET /api/absensi | Date range filter |
| Full Report | CSV | Frontend-generated | Combines visit + attendance data |

**Required from legacy systems (NOT BUILT):**
| Export | Format | Notes |
|--------|--------|-------|
| Visit monitoring | CSV/XLSX | Date range + depo + karyawan filters |
| Photo gallery | Zip | Visit photos with descriptions |
| Activity log | CSV/XLSX | App usage tracking |
| Daily recap (per sales) | CSV/XLSX | Per-sales summary |
| Attendance | CSV/XLSX | With export button |
| Stock check report | CSV/XLSX | Per-store stock |
| Out-of-route order report | CSV/XLSX | |
| Shipped order detail | CSV/XLSX | |
| Surat tugas (task doc) | CSV/XLSX | |
| Order vs stock analysis | CSV/XLSX | |
| Invoice PDF | XLSX | Mass download |
| Packing list | PDF | Route-level |
| Promo catalog | PDF | Active promos |

---

## 14. Settings & Configuration Flow

**Actor:** Super Admin

**Status:** 🔴 NOT BUILT

**Required from legacy systems:**
- Depot brand access management (which depots sell which brands)
- WhatsApp account management (for OTP)
- OTP PIC per depot
- Depot configuration (key-value settings)
- User session management (view active, force-reset)
- Bulk session reset

---

## 15. Edge Cases & Error States

### 15.1 Authentication

| Scenario | Expected Behavior | Status |
|----------|-------------------|--------|
| Wrong password | 401 + "Email atau password salah" | ✅ Built |
| Locked account after 5 fails | 429 + "Terlalu banyak percobaan" | ✅ Built |
| Expired session | 401 + "Session expired" + redirect to login | ✅ Built |
| Invalid JSON body | 400 + "Invalid JSON" | ✅ Built |
| Array body instead of object | 400 + "Request body must be a JSON object" | ✅ Built |
| Empty email/password | 400 + "Email dan password diperlukan" | ✅ Built |
| No cookie sent | 401 + "Session expired" | ✅ Built |
| Garbage cookie | 401 + "Session expired" | ✅ Built |
| Cross-origin request | CORS headers allow all origins (cookie blocked by SameSite=Lax) | ✅ Built |
| Concurrent login attempts | Rate limit hits at 5 attempts per email+IP per 5min | ✅ Built |

### 15.2 Visit Card

| Scenario | Expected Behavior | Status |
|----------|-------------------|--------|
| Checkin without place_uuid | 400 + "place_uuid diperlukan" | ✅ Built |
| Double checkin (same store) | 409 + "Kunjungan sudah check-in, selesaikan dulu" | ✅ Built |
| Checkout without checkin | 400 + "Belum ada check-in untuk toko ini" | ✅ Built |
| Double checkout | 400 + "Belum ada check-in untuk toko ini" | ✅ Built |
| Finish without timer done | Alert "Tunggu timer selesai" | ✅ Built |
| Finish without checkin | Alert "Check-in dulu!" | ✅ Built |
| Order without checkin | Alert "Check-in dulu!" | ✅ Built |
| No-order with empty reason | Alert "Pilih alasan" | ✅ Built |
| No-order "Lainnya" empty | Alert "Tulis alasan" | ✅ Built |
| Add store already in plan | "Toko sudah ada dalam daftar" | ✅ Built |
| Store search no results | "Tidak ada toko tersedia" | ✅ Built |
| No stores assigned to today | "Tidak ada toko dalam daftar" | ✅ Built |
| Camera permission denied | File input fallback | ✅ Built |
| GPS timeout | Checkin proceeds without location | ✅ Built |

### 15.3 Absensi

| Scenario | Expected Behavior | Status |
|----------|-------------------|--------|
| Clock out without clock in | Alert "Anda belum mulai kerja hari ini" | ✅ Built |
| Empty clockIn from DB | Normalized to null in response | ✅ Built |
| Unknown action | 400 + "Unknown action: X" | ✅ Built |
| Camera unavailable | File input fallback | ✅ Built |
| GPS timeout | Clock in proceeds without location | ✅ Built |
| localStorage full | Error logged, attempt proceeds | ✅ Built |

### 15.4 Dashboard

| Scenario | Expected Behavior | Status |
|----------|-------------------|--------|
| No visit plan today | "Belum ada kunjungan hari ini" | ✅ Built |
| No activity today | "Belum ada aktivitas hari ini" | ✅ Built |
| No attendance record | Absensi stat shows "—" | ✅ Built |
| No driver assigned | Orders = 0 | ✅ Built |

### 15.5 Network & Server

| Scenario | Expected Behavior | Status |
|----------|-------------------|--------|
| PostgreSQL connection failure | 500 + "DB connection failed" | ✅ Built |
| Connection pool exhausted | New connection created (ping check first) | ✅ Built |
| Body too large (over 5MB) | 400 + "Body too large" | ✅ Built |
| Unknown endpoint | 404 (static file fallback) | ✅ Built |
| Concurrent requests (5+) | All return 200 (connection pool handles) | ✅ Built |
| Server restart after crash | Server starts fresh, sessions in DB survive | ✅ Built |
| Session cache stale | 5-min cleanup thread purges expired | ✅ Built |

### 15.6 Data Integrity (from legacy complaints)

| Scenario | Expected Behavior | Notes |
|----------|-------------------|-------|
| Visit crash during checkout | Visit stays as "checkin" (no auto-delete) | GooVi deletes forgot-checkout visits — a core pain |
| Order > 0 without checkin | Blocked by frontend (checkin required) | Also blocked by backend (no driver context) |
| Out-of-route via WA/Telepon | Must use app "Tambah Luar Rute" → order flow | Current 51% avoidance rate |
| Promo data missing in export | Bonus items tracked in order line items | Legacy loses promo data |
| Username change | Supported natively in PostgreSQL | No vendor lock |

---

## 16. Data Flow Architecture

### 16.1 Request Flow Diagram

```
Browser (Mobile Web)
    │
    │ Cookie: wim_session=xxx (HttpOnly, SameSite=Lax)
    │
    ▼
┌──────────────────────────────────────────────────┐
│ WIM Server (Python http.server)                  │
│ Port 8080 on LXC 106 (192.168.6.223)             │
│                                                  │
│ ┌─────────────┐  ┌──────────────────────────┐   │
│ │ Static Files│  │ API Handlers              │   │
│ │ /index.html │  │ /api/auth/*               │   │
│ │ /dashboard  │  │ /api/dashboard            │   │
│ │ /visit-card │  │ /api/visits, /api/stores  │   │
│ │ /js/*.js    │  │ /api/absensi, /api/report │   │
│ │ /css/*.css  │  │ /api/visit_plan           │   │
│ └─────────────┘  │ /api/orders, /api/stock   │   │
│                  │ /api/admin/*               │   │
│                  │ /api/promos                │   │
│                  └──────────┬───────────────┘   │
└─────────────────────────────┼────────────────────┘
                              │
                              ▼
                  ┌──────────────────────────────┐
                  │    PostgreSQL (wim_sfa)        │
                  │  ┌────────────────────────┐  │
                  │  │ wim_auth.sessions      │  │
                  │  │ wim_users              │  │
                  │  │ wim_karyawan           │  │
                  │  │ wim_depo               │  │
                  │  │ wim_pelanggan (stores) │  │
                  │  │ wim_produk (products)  │  │
                  │  │ wim_visit_plan         │  │
                  │  │ wim_visits             │  │
                  │  │ wim_attendance         │  │
                  │  │ wim_orders             │  │
                  │  │ wim_order_items        │  │
                  │  │ wim_stock_check        │  │
                  │  │ wim_promos             │  │
                  │  │ wim_kendaraan          │  │
                  │  └────────────────────────┘  │
                  └──────────────────────────────┘
```

### 16.2 Data Persistence Rules

| Data | Stored In | Owner | Backup |
|------|-----------|-------|--------|
| User accounts | `wim_users` | WIM Server | PostgreSQL dump |
| Sessions | `wim_auth.sessions` + in-memory cache | WIM Server | DB + cache |
| Visits (checkin/checkout) | `wim_visits` | WIM Server | PostgreSQL |
| Attendance | `wim_attendance` | WIM Server | PostgreSQL |
| Visit plans | `wim_visit_plan` | WIM Server | PostgreSQL |
| Stores | `wim_pelanggan` | WIM Server | PostgreSQL |
| Orders | `wim_orders` + `wim_order_items` | WIM Server | PostgreSQL |
| Products | `wim_produk` | WIM Server | PostgreSQL |
| Promos | `wim_promos` | WIM Server | PostgreSQL |
| Stock checks | `wim_stock_check` | WIM Server | PostgreSQL |
| Attendance photos | localStorage (browser) | Browser | Lost on clear |
| Visit photos | wim_visits.photos (JSON) | PostgreSQL | DB |
| Login rate limit | In-memory (LOGIN_ATTEMPTS dict) | WIM Server | Lost on restart |

### 16.3 Session Lifecycle

```
1. Login → INSERT wim_auth.sessions (expires: NOW + 7 days)
2. Cache → SESSIONS[sid] = {user_data, expires: time() + 300}
3. Subsequent requests → check cache first (5 min TTL)
4. Cache miss → query PostgreSQL, repopulate cache
5. Session cleanup thread (runs every 5 min) → purge expired from cache
6. Logout → DELETE from DB + remove from cache
```

---

## 17. UI/UX Improvements Log

*This section tracks findings from UI/UX professional reviews and improvements applied.*
*5 expert reviewers consulted: Mobile Field-Sales UX, Information Architecture, B2B Admin Dashboard, Accessibility & Micro-interaction, Business Process Analysis.*

### V1.0 Improvements (current)

| # | Issue | Category | Source | Applied |
|---|-------|----------|--------|---------|
| 1 | Hardcoded admin email in login form | Security | Internal | ✅ Removed |
| 2 | Order button was a stub — now redirects to NOO | Functionality | Internal | ✅ Fixed |
| 3 | No feedback on checkin/checkout success | UX | Internal | ✅ Alert + visual change |
| 4 | 3-min timer not visible at modal open | UX | Internal | ✅ Prominent display |
| 5 | Missing "Lainnya" text input for no-order | UX | Internal | ✅ Added |
| 6 | Photo camera fallback for HTTP (mobile) | UX | Internal | ✅ File input capture |
| 7 | Bottom nav consistent across all pages | UX | Internal | ✅ All pages |
| 8 | Login error messages in Bahasa Indonesia | UX | Internal | ✅ All messages |
| 9 | Session expiry redirects to login | UX | Internal | ✅ checkOrRedirect() |
| 10 | GPS timeout doesn't block flow | UX | Internal | ✅ 3s timeout, proceeds null |

### V1.1 Improvements (from 5 UX Expert Reviews)

| # | Issue | Category | Priority | Status |
|---|-------|----------|----------|--------|
| 1 | **Timer starts at check-in, not modal open** | UX — sales rep | P0 | ✅ Implemented |
| 2 | **Server-side minimum visit duration (180s)** | Integrity | P0 | ✅ Implemented |
| 3 | **Role-based redirect: admin → admin.html** | IA | P0 | ✅ Implemented |
| 4 | **Stock check persistence** | Functionality | P0 | ✅ Implemented (`POST /api/stock`) |
| 5 | **Confirm dialog on checkout/Selesaikan** | UX | P0 | ✅ Implemented |
| 6 | **Toast notification system (replaces alert())** | Accessibility | P0 | ✅ Implemented |
| 7 | **"Buat Pesanan" → coming soon stub (not wrong NOO page)** | IA | P0 | ✅ Fixed |
| 8 | **Loading states on all POST buttons** | UX | P0 | ✅ Implemented |
| 9 | **Debounce (300ms) on store search** | UX | P0 | ✅ Implemented |
| 10 | **Store order history context in visit modal (last 3 orders)** | UX | P1 | ✅ Implemented |
| 11 | **Store order history API endpoint** | Backend | P1 | ✅ Implemented (`GET /api/stores/orders`) |
| 12 | **Timer color progression (green→yellow→red)** | UX | P1 | ✅ Implemented |
| 13 | **Vibration feedback on timer completion** | UX | P1 | ✅ Implemented |
| 14 | **Timer done animation (pulse)** | UX | P1 | ✅ Implemented |
| 15 | **Toast animation (slideIn)** | CSS | P1 | ✅ Implemented |
| 16 | **wim_stock_check DB table created** | Backend | P1 | ✅ Implemented |
| 17 | **MIN_VISIT_SECONDS env var (configurable)** | Architecture | P1 | ✅ Implemented |

### V1.2 Required — Not Yet Implemented

| # | Issue | Category | Priority | Source |
|---|-------|----------|----------|--------|
| 1 | **Order creation flow** (cart, checkout, promo) | Functionality | P0 | Business Process Audit |
| 2 | **Visit→order cross-validation** (`meta.checkin_id` on orders) | Integrity | P0 | Business Process Audit |
| 3 | **Barcode/QR verification loop** | Integrity | P0 | Business Process Audit |
| 4 | **Attendance GPS geofence (depot zone)** | Integrity | P1 | Business Process Audit |
| 5 | **Attendance: mandatory photo on clock-out** | Integrity | P1 | Business Process Audit |
| 6 | **Attendance: server-generated timestamps** | Integrity | P1 | Business Process Audit |
| 7 | **Anti-WA-bypass: enforce visit_plan entry before order** | Integrity | P1 | Business Process Audit |
| 8 | **Attendance: GPS mandatory (10s timeout, no skip)** | Integrity | P1 | Business Process Audit |
| 9 | **Admin dashboard (KPI cards + 7 chart widgets)** | Admin | P1 | B2B Admin Review |
| 10 | **Admin role-based navigation (separate nav stack)** | IA | P1 | IA Review |
| 11 | **Offline queue (IndexedDB + Service Worker + request replay)** | Architecture | P1 | Accessibility Review |
| 12 | **Photo uploads immediately after capture (not on form submit)** | Architecture | P1 | Mobile UX Review |
| 13 | **wim_audit_log table for admin actions** | Integrity | P2 | Business Process Audit |
| 14 | **Promo export schema (purchased vs bonus separation)** | Export | P2 | Business Process Audit |
| 15 | **"Luar Rute" badge: blue (#007bff) not yellow** | Accessibility | P2 | Accessibility Review |
| 16 | **NOO form split into Step 1 (wajib, 5 fields) + Step 2 (opsional)** | UX | P2 | Mobile UX Review |
| 17 | **NOO draft auto-save to IndexedDB** | UX | P2 | Mobile UX Review |
| 18 | **Loading skeletons (not generic spinner)** | UX | P2 | Accessibility Review |
| 19 | **Photo processing feedback ("Memproses foto...")** | UX | P2 | Accessibility Review |
| 20 | **Rate limit countdown (live seconds remaining)** | UX | P2 | Accessibility Review |
| 21 | **Accessibility: touch targets ≥48px** | Accessibility | P2 | Accessibility Review |
| 22 | **Keyboard input types for NOO fields** | Accessibility | P2 | Accessibility Review |
| 23 | **Offline search index for stores** | Architecture | P2 | Accessibility Review |
| 24 | **Network status banner (persistent offline indicator)** | UX | P2 | Accessibility Review |
| 25 | **No-order anomaly detector (admin dashboard widget)** | Admin | P2 | Business Process Audit |
| 26 | **sales_channel field on orders (app/wa/telepon/admin)** | Integrity | P2 | Business Process Audit |
| 27 | **Route map visualization** | UX | P3 | Mobile UX Review |
| 28 | **Pull-to-refresh on visit list** | UX | P3 | All reviews |
| 29 | **Dark mode** | UX | P3 | Accessibility Review |
| 30 | **Haptic feedback on all success actions** | UX | P3 | Accessibility Review |

---

## Appendix A: GooVi → WIM Online Feature Mapping

| GooVi Feature | WIM Online Status | Notes |
|---------------|-------------------|-------|
| Login (email/password + device_info) | ✅ Replaced | No device_info needed |
| Visit card (today's plan) | ✅ Built | GET /api/stores |
| Check-in/check-out | ✅ Built | POST /api/visits |
| In-route/out-route flag | ✅ Built | source field |
| Ad-hoc store (luar rute) | ✅ Built | POST /api/visit_plan |
| Set visit priority | 🔴 Not built | |
| Selfie photo (wajib) | ✅ Built | 1 mandatory on visit |
| Additional photos | ✅ Built | Optional, multiple |
| Stock check | 🟡 Partial | Built but limited |
| NOO (new outlet) | 🟡 Partial | Creates store, no OTP, no draft |
| OTP verification (WA) | 🔴 Not built | Needs WhatsApp gateway |
| Order creation | 🔴 Not built | Needs full order flow |
| Promo/bundling | 🔴 Not built | Needs custom Promo model |
| Dashboard (sales) | ✅ Built | GET /api/dashboard |
| Route map | 🔴 Not built | |
| Presensi (absensi) | ✅ Built | POST /api/absensi |
| Report (sales) | ✅ Built | GET /api/report |
| Report via KlikOrder | 🔴 Not built | |
| Edit phone number | 🔴 Not built | |

## Appendix B: KlikOrder → WIM Online Feature Mapping

| KlikOrder Feature | WIM Online Status | Notes |
|-------------------|-------------------|-------|
| Product catalog | 🔴 Not built | wim_produk table exists |
| Brand-based pages | 🔴 Not built | |
| Cart with bundling | 🔴 Not built | |
| Promo visibility | 🔴 Not built | Custom Promo model needed |
| Checkout (COD) | 🔴 Not built | |
| Barcode generation | 🔴 Not built | Order ref → QR |
| Order history | 🔴 Not built | GET /api/orders |
| Export to Excel | 🟡 Partial | Sales rep only, no admin |
| Out-of-route ordering | 🔴 Not built | Needs off_route_reason |
| Admin order creation | 🔴 Not built | |
| Packing list | 🔴 Not built | |
| Invoice PDF | 🔴 Not built | |
| Promo management | 🔴 Not built | wim_promos table |
| Dashboard KPIs (admin) | 🔴 Not built | 7+ chart widgets |
| Gamification (koin) | 🚫 Out of scope | Not planned |