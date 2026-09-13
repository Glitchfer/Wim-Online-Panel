# Transcript Insights — WIM Meeting Recordings 11 & 12 (2026-09-07)

> Source: auto-transcribed meeting recordings (poor quality, some mistranscribed).
> Per Rein's instruction, these are used ONLY as reinforcement / additional context, NOT as truth source.
> Only points that align with the meeting notes doc or the live API mapping are captured here.

## Reinforced core findings

### 1. The trust problem is THE #1 driver (confirmed twice)
- Rep types "jumlah order" (e.g., 30 karton) in **GooVi**, then creates the actual order in **KlikOrder** — the two are never cross-validated. Rep can type 30 in GooVi but only order 20 in KlikOrder with zero warning.
- Manager: *"Saya tidak terlalu percaya sama EC yang ada di GooVi"* — EC (Effective Call) counts an outlet only if "jumlah order" was typed in GooVi; if the rep leaves it blank but still orders in KlikOrder, the outlet silently drops out of EC/portfolio stats.
- **Result:** incentives and EC are computed from KlikOrder (source of truth), GooVi is used only for productivity (check-in/out, photo, duration). Manager explicitly distrusts GooVi's order-derived numbers.
- → Core rule: **order > 0 must be backed by a verified order record in the same system** (no hand-typed count to trust).

### 2. "One app, not two" (validates unified platform approach)
- Manager: *"Paling benernya satu aplikasi, jadi gak mungkin salah"* — today the sales rep jumps between GooVi (check-in, visit card) and KlikOrder (order entry), exits/enters repeatedly, and the split is exactly where errors creep in.
- Tool split today: GooVi = management/monitoring; KlikOrder = all sales order workflow.

### 3. Forgotten checkout = deleted visit = lost orders & KPIs
- If a rep finishes entering an order but forgets to hit **checkout/Kirim Kunjungan**, the visit is deleted, any order placed is lost, and the KPI count drops. Manager reports had 5 reps return to stores to redo visits that day.
- **Requirement:** visit completion must be explicit and enforced, but order data must NEVER be silently destroyed — a visit can be resumed/completed; order lines survive even if the visit flow breaks (timeout, app close, session drop).

### 4. Store-stock input UX causes data abandonment (stock analysis unusable)
- The stock check ("Ketersediaan stock di toko") requires horizontal scrolling in a cramped UI, so reps skip it. Result: the "Analisa Order vs Stock" reports are unusable because the input data doesn't exist.
- Manager explicitly asked: **make stock input simple in the new app** (one-tap per SKU, big touch targets). → This is a first-class G2/G4 requirement, not a nice-to-have.

### 5. Promo/export readability is broken today
- Order exports show promo codes (e.g., "banding 8-4") instead of promo names — the manager must manually pivot/lookup codes to reconcile; sometimes export totals don't match (felt unreliable → manual checks).
- Bonus (free) products are merged into the same lines as bought products, making BOGO ("buy 1 get 1", "buy 2 get 1") reconciliation a manual mess across two export tabs (T1/T2).
- **Requirement:** exports must separate **product order lines** from **bonus lines** (product, qty, unit, bonus product, bonus qty), and show human-readable promo names + promo reference (nomor surat promo).

### 6. EC / effective-call semantics (for analytics)
- Portfolio Sales stats: total outlets, active outlets, inactive outlets, active ratio (e.g., 40 visited → 6 active → 34 inactive). Outlet counted active only if an order exists.
- Also split "order" vs "tidak order" routes in route visualization (blue = transacted, red = not).

### 7. Promo configuration is vendor-controlled (both directions)
- WIM currently sends promo template + nomor surat promo to the vendor; vendor configures the program in-app. WIM only edits dasar price (per depot, one-by-one — painful, PRD). Strata pricing is vendor-only.
- New (recent): WIM got access to submit promos in-app (import promo rules) and edit promo, but manager doesn't trust it yet ("takutnya mereka salah" — worried about wrong perception/setting).
- → WIM Online gives **full self-service promo control** — a selling point, since promo is core to their operation.

### 8. Cost structure being replaced (self-host motivation)
- OTP verification costs ~Rp500 per OTP sent (per visit, per phone change).
- Admin accounts: Admin Depo ~Rp50k/account/month; Admin Wilayah cheaper but limited; per-device single-session; extra modules (driver) cost more per account.
- **No SLA / no compensation** when the server is down (server full → everything manual, no official records).
- → Self-hosted PostgreSQL stack removes recurring per-seat licensing + OTP costs and gives uptime control.

## New operational details (flag for scope)

### Route plan & visit planning
- Route plans are **4 weeks/month × 5 days/week**, imported via a 3-sheet Excel format (WIM must request import access from vendor; vendor sets the format).
- Plans assign stores to sales by week + day; reps see "Rencana Kunjungan" today's list with in-route/out-route.
- **New depo setup:** submit pengajuan depo (nama depo, SKU, jenis sales, kode karyawan) → THEN activate brand access per depo ("Update AksesBrand") or the depo doesn't appear in the app. WIM wants this automated.
- **Customer transfer between sales** (perpindahan pelanggan): 3-sheet format, must be done at night so daily visits don't break, needs advance notice. WIM wants this simpler/faster.

### Roles & user taxonomy (for wim_users / wim_admin_roles)
- Roles in GooVi: **Sales, Driver, Helper, Kepala Depo, Kepala Gudang** (+ admin variants).
- Jenis sales (sub-type filter): **SPG, TO (Trade Outlet), Motoris, SMD, SPC, Kanvaser**, etc. Jenis sales is a filter only (no actual permission difference).
- All personnel (transaction or not) live in GooVi; KlikOrder accounts only for those placing orders.

### Depot/program structure
- Depots are split by program: e.g., Purwokerto **TO** vs Purwokerto **SPC**, Semarang TO/SPC — separate depots so the TO and SPC promo programs don't clash under one account. Known depots: Tambun, Tapos, Bintaro (Tangsel), Serpong, Purwokerto, Semarang (expanding).
- → WIM Online depot system must support per-depot brand access + per-depot promo scoping.

### Session / device handling (current pain)
- Single-session enforcement causes "Anda login di perangkat lain" lockouts; reps switching devices (or clearing Chrome data to fix GPS freeze) lose sessions; previously required support intervention, now self-serve reset was added.
- GPS freeze issue in Chrome requires clearing app data to fix.
- → WIM Online should support per-device sessions with graceful re-login (or multi-session tolerance) + robust GPS handling in the sales frontend.

### KlikOrder super admin (order-side)
- Data Pesanan Produk: exports per depo/sales; mass PDF (surat jalan/faktur) bulk download.
- Order By Admin: scan store barcode (Google Lens) → same order flow as sales.
- Setting Promo: filter by status/period/depo → download catalog promo (packing list per invoice, printable).
- Pre-packing view: e.g., 86 invoices to prep, batch print.
- Invoice shows BOGO programs; manager wants bonus as clearly separate product-bonus columns.

### Driver module (future, not today)
- Manager hasn't onboarded drivers yet (licensing cost + not ready); vision: driver takes order while delivering (kanvas). Sales first, drivers later.
- → Supports existing roadmap: driver/delivery module = post-V1 phase (G5+ / future).

### Timeline expectation
- Manager estimates the replacement could be done in ~2 weeks ("2 minggu kelar") — realistic only if scope stays lean (core features already exist per meeting notes). Set expectations: G0–G3 core flow first, reporting thereafter.

## What this changes in the project docs

| Doc | Change |
|---|---|
| NON-NEGOTIABLES.md | + Visit-completion enforcement (orders never destroyed); EC computed from verified orders; promo/bonus export separation |
| SCOPE.md | + Simple stock-input UX (G2); checkout/complete-visit enforcement; promo config self-service |
| DATA-MODEL.md | + Role/jenis-sales taxonomy; depot brand-access per depot; EC analytics fields |
| PROJECT-CHARTER.md | + Cost/risk motivation for self-hosting (OTP Rp500, ~Rp50k/seat admin, no SLA) |
| ROADMAP.md | G2/G4 requirement notes reinforced; driver phase confirmed post-V1 |