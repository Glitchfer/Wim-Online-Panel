# WIM Online — Test Accounts

## Sales Rep (primary test user)
| Field | Value |
|-------|-------|
| Email | `andi@wim.sales` |
| Password | `sandi123` |
| Name | Andi Sales |
| Role | Sales Rep |
| Driver ID | `driver_z0crayures` (linked) |
| Status | Active, has visit plans, orders, attendance records |

Test at **https://sales.sqa.web.id** (public domain, works on mobile)

## What this user can test

| Feature | How |
|---------|-----|
| **Dashboard** | Shows 5 stores planned, 3 orders, 10 visited today, absensi status |
| **Kunjungan** | 5 stores (3 route + 2 luar rute), visit check-in/checkout with timer |
| **Route Map** 🗺️ | Leaflet map with 5 store markers (blue=route, green=visited, orange=luar rute) + 3 depots (red circles, 50m radius) + GPS marker |
| **Absensi** | Clock in/out with photo + GPS. Automatically checks if you're within **50m of a depot** (logs `in_depot` or `outside` in DB) |
| **NOO** | New Outlet Opening form with **channel→kategori cascade**: GT → retail/grosir; MT → minimarket/supermarket; Horeka → hotel/restoran; Institutional → kantor/sekolah |
| **Order (Cart)** | 8 products (SANQUA, LEVONTE, BATAVIA). Promo bundling (10+2 free), strata (10+:5%, 21+:10%), diskon (Rp5000). Server-side calculation |
| **Laporan** | Per-period report with visit/order/duration stats |
| **Tambah Toko Luar Rute** | Search stores from database and add to visit plan |

## Depot Locations (geofence check at clock-in)

| Depot | Coordinates |
|-------|------------|
| Gudang WIM Jakarta Pusat | -6.2088, 106.8456 |
| Depo WIM Jakarta Barat | -6.1865, 106.7350 |
| Depo WIM Jakarta Timur | -6.2450, 106.8900 |

**How geofence works:** When you clock in, your GPS is checked against all 3 depots. If you're within 50m, it's logged as `in_depot` (with the depot ID). If not, `outside`.

## Admin
| Field | Value |
|-------|-------|
| Email | `reinharttanto@gmail.com` |
| Password | ask Rein |
| Name | Reinhart Tanto |
| Role | Admin |

---

## For Testing Flow

1. Login at sales.sqa.web.id with `andi@wim.sales` / `sandi123`
2. **Dashboard** → see KPIs (5 kunjungan, 3 pesanan, etc.)
3. **🗺️ Rute** → see map with 5 store markers + 3 depot circles
4. **Absensi** → clock in (GPS sends location, geofence checked)
5. **Kunjungan** → tap a store → check in (180s timer) → checkout
6. **Buat Pesanan** (during visit) → browse products → add to cart → promo calculated → confirm order
7. **NOO** → try changing channel (GT/MT/Horeka/Institutional) → kategori options change dynamically
8. **Laporan** → view daily stats