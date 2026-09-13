# WIM Online — Accessibility & Micro-Interaction Expert Review

> **Reviewer:** Hermes Agent (Accessibility, Micro-Interaction & Error-State Expert)
> **Date:** 2026-09-08
> **Audience:** AI subagent coders, QA testers, product owner
> **App:** WIM Online — 200+ field sales reps, low-end Android, browser-based, HTTPS (sales.sqa.web.id)

---

## Executive Summary

WIM Online has solid error-state coverage on the backend but **critical gaps in the frontend UX layer** — especially for the target audience (field reps on 2G/3G in bright outdoor light, possibly with wet/gloved hands). The most concerning findings:

1. **Photo data in localStorage with no backup** — offline-taken photos are silently lost on cache clear, low-storage eviction, or session expiry
2. **"Luar Rute" badge has illegible contrast** — yellow text on white fails WCAG AA
3. **No offline queue or Service Worker** — total failure on network loss mid-flow
4. **Touch targets unspecified** — likely too small for gloved/wet hands on 720p phones
5. **Timer UX lacks urgency cues** — no color progression, no sound/haptic on completion
6. **Form validation error messages not specified** — inline vs blocking? Real-time or on-submit?

---

## (A) Verdict Per Interaction Area

### A1. §15 — Error States ⚠️ **NEEDS WORK**

| Area | Verdict | Rationale |
|------|---------|-----------|
| Auth errors | ✅ **Good backend coverage** | 400, 401, 429 all handled. Messages in Bahasa. Rate limit documented. |
| Auth error UI | ⚠️ **Incomplete** | "Red error banner" is the only UI specified. No auto-dismiss, no dismiss action, no animation. |
| Rate limiting | ⚠️ **Needs UX polish** | "Coba lagi dalam X detik" shows static text — no live countdown, no visual timer. On lockout, user has no idea when retry is safe. |
| Visit card errors | ✅ **Good coverage** | Double checkin (409), checkout without checkin (400), timer not done, no-order reason empty — all guarded. |
| Visit card error UI | ❌ **Critical gap** | Uses `alert()` for all user-facing errors. No toast/notification system. `alert()` blocks the JS thread, crashes on aggressive Android battery saver, and gives no visual hierarchy. |
| NOO errors | ❌ **Underspecified** | "Highlights field + error message" — no detail on error placement, color, iconography, or dismiss behavior. |
| Server errors (500/502) | ❌ **No retry affordance** | "Gagal memuat data: [message]" — generic string with no retry button, no auto-retry, no offline fallback. |
| 409 conflict | ✅ **Good message** | "Kunjungan sudah check-in, selesaikan dulu" — clear, actionable. But delivered via `alert()`. |
| Network error | ❌ **No offline detection** | "Gagal: Network error..." is reactive (after fetch fails). No proactive "Koneksi terputus" banner. |

### A2. Touch Targets ❌ **UNSPECIFIED — HIGH RISK**

| Element | Estimation | Concern |
|---------|-----------|---------|
| Bottom nav tabs (5) | ~48px if well-designed on 720p | On 5" 720p screens at 320dpi, 5 tabs leave ~64px per tab. Adequate **if** icons are padded. Risk: crammed. |
| Dashboard stat cards (4) | ~60-80px labels | Likely fine for tap, but numeric values may be small text targets. |
| "Aksi Cepat" buttons (2×2 grid) | **RISKY** | 2-column grid on mobile means narrow buttons (~40% viewport width). With padding & text, real target ~40-44px. Borderline for gloved hands. |
| Store list items | **RISKY** | Name + city + badge in one row → text target may be too thin vertically. 51% avoidance rate partly explained by poor interaction design. |
| Modal action buttons | **RISKY** | "📍 Check-in di Toko", "📸 Ambil Foto" etc. in a list — if these are < 44px, field reps with wet hands will miss repeatedly. |
| Camera button / photo preview | **RISKY** | Small "triggers" in camera modal. Photos are mandatory — if the capture button is tiny, reps tap multiple times → frustration. |
| "Selesaikan Kunjungan" | **Critical** | This is the primary action. It starts disabled (timer guard). Must be large (≥ 56px), well-spaced, and visually prominent. |

### A3. Contrast & Color ❌ **CONTAINS FAILURES**

| Element | Colors | Ratio | Verdict |
|---------|--------|-------|---------|
| **"Luar Rute" badge** | 🟡 Yellow (#ffc107) on white (#fff) | **1.4:1** | ❌ **FAILS WCAG AA**. Illegible in sunlight. Reps can't tell route from luar-rute at a glance. |
| "Dalam Rute" badge | 🟢 Green (#28a745) on white | ~3.0:1 | ⚠️ **Fails WCAG AA for small text** (needs 4.5:1). Passes AA Large. In bright outdoor light, borderline. |
| Status dot: visited | 🟢 Green check | ~3.0:1 against list bg | ⚠️ Small indicator, hard to distinguish from unvisited in glare. |
| Error banners | 🔴 Red on white | ~4.0:1 (typical Bootstrap) | ⚠️ Borderline for small error text. On a phone in direct sunlight, invisible. |
| Primary buttons | Green (#28a745) on white | ~3.0:1 | ⚠️ Fails AA for button text labels. "Mulai Kerja", "Selesaikan Kunjungan" in green text may blend. |
| Dashboard stat numbers | **UNSPECIFIED** | Unknown | If numbers are colored (e.g., 5 in green bold), contrast needs verification. |
| Empty state text | Gray on white | ~3.0:1 (typical #6c757d) | ⚠️ "Belum ada kunjungan hari ini" in gray is hard to read outdoors. |

### A4. Loading & Photo Feedback ⚠️ **UNDERSPECIFIED — SLOW-NETWORK RISK**

| Interaction | Current | Gap |
|-------------|---------|-----|
| Auth submit | "Memverifikasi...", disabled | No progress bar. On 2G (3-5s RTT), user sees frozen button for 3+ seconds. |
| Dashboard load | "Spinner" | Generic spinner. No skeleton layout. On 2G, entire page is blank + spinner. |
| Store list load | "Spinner" | Same issue. No cached/stale list shown while loading. |
| Photo capture | "Compressed to 800px JPEG 0.6" | **No "Memproses foto..." indicator.** Compression takes 1-3 seconds on low-end MTK chips. User may tap again → multiple photos. |
| Photo upload (base64) | Sent as data URI in POST body | **BASE64 BLOBS ARE 33% LARGER THAN BINARY.** A 800px JPEG at 0.6 quality is ~100-200KB → ~150-270KB as base64. On 2G upload (50 KB/s), that's 3-5 seconds per photo with no progress bar. |
| Multiple photos | "Can take multiple photos" | Each photo = separate base64 upload delay. If user takes 3 photos → 9-15 seconds of uploading with no feedback. |
| NOO submit | Unspecified | "Menyimpan..." while creating store + contact records. On slow network, 5-10 seconds of blank state. |
| Export CSV | "Build CSV blob → download" | No progress. Large export locks the UI thread. |
| GPS detection | "3s timeout" | User sees nothing for 3s. No "Mendeteksi lokasi..." spinner. |

### A5. Offline Behavior ❌ **CRITICAL GAP**

| Scenario | What Happens | Risk |
|----------|-------------|------|
| **Photo stored in localStorage** | ❌ Photo saved only in browser. On cache clear/phone storage cleanup → **photo is lost permanently**. No backup to server until POST succeeds. |
| **Loss of localStorage** | Android Cleaner apps, "Clear Cache" in Chrome, low-storage eviction → attendance photo gone. | ✓ Documented in §16.2 as "Lost on clear" — but not surfaced to user. |
| **Network drops mid-visit** | ❌ No offline queue (planned for V1.1 — not built). User loses all work. | Rep is at store, network drops → enters data → taps save → failure → retype everything. |
| **Network drops on checkin** | ❌ Checkin POST fails → `alert("Gagal: Network error...")` → user has no checkin event → timer was running → wasted 3 minutes. | |
| **Offline store search** | ❌ "Cari nama toko..." requires API call. On 2G, search takes 2-5s per keystroke if live-search. | No debounce specified. No local store index. |
| **Timer during offline** | ❌ Timer runs client-side (VisitTimer class). If page is refreshed or network returns, timer resets. | No server-side timer checkpoint. |
| **Page refresh mid-visit** | ❌ All modal state lost. Store context in localStorage may persist, but timer resets, checkin status lost. | User must start over. |

### A6. Form Validation (NOO §7) ⚠️ **UNDERSPECIFIED**

| Aspect | Status | Gap |
|--------|--------|-----|
| Required fields | Marked with `*` | **No `aria-required` or `required` attribute** mentioned. Color-only `*` fails for screen readers. |
| Validation timing | Unspecified: "Missing: highlights field + error message" | Is this on-blur (real-time) or on-submit (blocking)? Real-time is far better for 14 fields. |
| Error placement | Unspecified | Above field? Below? Tooltip? For field use, **inline below-field** is best (not blocking, not covered by thumb). |
| Error iconography | Unspecified | Text-only error messages. Icons (⚠️, ❌) help reps with low literacy scan for problems. |
| Province → City cascade | Unspecified behavior | If this triggers an API call, slow network leaves dropdowns empty. User may submit with defaults. |
| GPS detection timeout | 3s, proceeds null | Good fallback — but null lat/lng submitted with no user warning. |
| OTP verification | 🔴 Not built | When built: must handle retry, cooldown, SMS-delivery delay UI. |
| Draft save | 🔴 Not built | 14 fields lost on back-navigation or page refresh. **HIGH impact for field use** — reps work in interrupted environments. |
| Character limits | Not specified | No `maxlength`, no remaining-char counter. On slow keyboards, reps may type past invisible limits. |
| Keyboard type | Not specified | No. HP should get `inputmode="tel"`, NIK `inputmode="numeric"`. On soft keyboard, wrong keyboard type = friction. |

### A7. Timer UX ⚠️ **FUNCTIONAL BUT MISSING CUES**

| Aspect | Current | Recommendation |
|--------|---------|----------------|
| Display | `mm:ss` countdown | Acceptable, but **progress ring** is more glanceable. At 3:00, reps need to know "how much longer" without reading digits. |
| Color | Unspecified | No color progression. **Red in last 30s** communicates urgency. Green when done triggers dopamine. |
| Completion signal | Green text "Selesai ✅" | **No sound/vibration.** On noisy street or in glove, visual-only is easy to miss. |
| Pre-completion guard | "Tunggu timer selesai" alert | Correct, but alert is jarring. **Disable + subtle tooltip** is better UX. |
| State on modal reopen | Unspecified | If user closes modal and reopens — does timer persist? If not, 3-minute wait starts over → **extremely frustrating**. |
| Server-side checkpoint | ❌ Not present | Timer is pure client-side. Rep could manipulate JS, close/reopen to skip. Backend should enforce minimum duration. |
| Button enabled state | Enabled on timer + checkin done | Good. Should also show visual count on the button itself ("Selesaikan (2:15)"). |

---

## (B) Prioritized Accessibility & Micro-Interaction Fixes

### 🔴 P0 — Critical (Fix Before Launch)

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| **P0.1** | **Offline photo loss** | §5, §6, §16.2 | **Upload photo immediately after capture**, not on form submit. Send `POST /api/absensi` photo asynchronously as soon as compressed. Surface localStorage-only status in-app: "📸 Foto tersimpan offline — akan dikirim saat online" with a sync-pending badge. |
| **P0.2** | **No offline queue** | §17 V1.1 #7 | Implement a **request queue** (`localStorage` + `IndexedDB` + `navigator.onLine` listener). Failed POSTs (checkin, checkout, absensi) are queued and replayed on connectivity restore. Show queue count in header: "📤 3 antrean pending". Service Worker registration for cache-first static assets. |
| **P0.3** | **Yellow-on-white badge** | §6.1 | "Luar Rute" badge: change to **blue (#007bff) or dark orange (#e67e22)** on white → passes WCAG AA (4.5:1+). Yellow is only acceptable as a background on dark text. |
| **P0.4** | **Base64 photo upload blocking** | §5, §6 | Convert photos to **binary FormData** upload instead of JSON base64. Shows native upload progress. Reduces payload by 33%. Use `XMLHttpRequest` with `upload.onprogress` for a progress bar. |
| **P0.5** | **`alert()` for all errors** | §6, §15 | Replace with **non-blocking toast/notification component**. `alert()` blocks JS, crashes on aggressive Android, and has zero accessibility affordances. Use a bottom-sheet toast with auto-dismiss (5s) and action button when applicable. |

### 🟠 P1 — High (Fix in Current Sprint)

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| **P1.1** | **Touch targets underspecified** | All pages | Enforce **minimum 48×48px** for all interactive elements, **56×56px for primary actions** (Selesaikan Kunjungan, Mulai Kerja, Simpan). Document in the spec. Use `@media (pointer: coarse)` to add padding on touch devices. |
| **P1.2** | **Loading skeletons** | §4, §6, §7 | Replace generic spinner with **skeleton placeholders** matching the final layout. On dashboard, show gray blocks where stat cards will render. On visit list, show 3-4 store-shaped skeletons. On 2G, this prevents layout shift and gives a mental model. |
| **P1.3** | **Photo processing feedback** | §5.1, §6.2 step 4 | Show **"📸 Memproses foto..."** overlay during compression (Canvas → blob). Then show **"📤 Mengirim..."** during upload. Both with spinner. Prevents double-tap. |
| **P1.4** | **Timer progress ring + sound** | §6.2 | Add **circular progress ring** around the timer (green → yellow at 1:00 → red at 0:30). Use **`navigator.vibrate(200)`** on mobile when timer completes. Blink the "Selesaikan" button gently. |
| **P1.5** | **Timer persistence on modal dismiss** | §6.2 | Timer must **survive modal close/reopen**. Store `timerStart` timestamp in `sessionStorage`. On modal reopen, calculate remaining time. Don't restart the clock. |
| **P1.6** | **Server error retry affordance** | All API calls | Every error banner should have a **"Coba Lagi"** (Retry) button alongside the message. For 502/network errors, add exponential backoff auto-retry (3 attempts, visible countdown: "Mencoba lagi dalam 5 detik..."). |
| **P1.7** | **Rate limit countdown** | §3.1 | Show a **live seconds-remaining countdown** in the error message: "Terlalu banyak percobaan. Coba lagi dalam 45 detik" with a visual bar depleting. |
| **P1.8** | **Green text on white contrast** | Badges, buttons | Change all small green text to **#1e7e34 or darker green**. For large text/buttons, **#2d8a3e** is safer. Verify with `@contrast` in CSS. |

### 🟡 P2 — Medium (Next Sprint)

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| **P2.1** | **Real-time field validation** | §7 NOO | Implement **on-blur validation** for each NOO field. Show error icon (⚠️) + message below field immediately. Use `aria-describedby` to link error to field. Mark fields with `aria-required="true"`. |
| **P2.2** | **GPS detection feedback** | §5, §7 | Show **"🔍 Mendeteksi lokasi..."** with a pulsing dot during GPS acquisition. If timeout, show "📍 Lokasi tidak terdeteksi, lanjut tanpa lokasi" as a discrete info bar — not silent. |
| **P2.3** | **Empty state text contrast** | §4, §6 | Gray text ("Belum ada kunjungan hari ini") → use **#495057** (darker gray) to meet 4.5:1 against white. Add a small illustration or icon per empty state for scannability. |
| **P2.4** | **Keyboard input types** | §7 NOO | Add `inputmode="tel"` for No. HP, `inputmode="numeric"` for NIK, NPWP, Kode Pos. Add `autocomplete` attributes for all fields. |
| **P2.5** | **Progress bar for long operations** | §7 NOO, §9 export | NOO submit (2 sequential API calls): show **"Menyimpan toko... (1/2)"** then "Menyimpan kontak... (2/2)". CSV export: show **"Menyiapkan data..."** → **"Mengunduh..."**. |
| **P2.6** | **Network status banner** | Global | Persistent **"Koneksi terputus"** banner at top when `navigator.onLine === false`. Shows "🔄 Mencoba menyambung..." with reconnect spinner. Auto-hides on reconnect. |
| **P2.7** | **Badge accessible labeling** | §6.1 | Add `aria-label="Dalam Rute"` / `aria-label="Luar Rute"` to badges. Screen readers will read unicode location emoji as garbage — add visually-hidden accessible text. |
| **P2.8** | **Form draft auto-save** | §7 NOO | Auto-save to `sessionStorage` on every field blur. Show "💾 Draft tersimpan" indicator. On page load, prompt "Lanjutkan draft sebelumnya?" if draft exists. |

### 🔵 P3 — Low (Backlog)

| # | Issue | Location | Fix |
|---|-------|----------|-----|
| P3.1 | Pull-to-refresh | §6 visit list | Native pull-to-refresh for store list. |
| P3.2 | Animated page transitions | All | Fade transitions between pages (reduces cognitive load). |
| P3.3 | Dark mode | All | Auto dark mode based on `prefers-color-scheme`. Reduces glare for reps who work late. |
| P3.4 | Haptic feedback on complete actions | Checkin, checkout, absensi | `navigator.vibrate(100)` on success. Confirms action without looking at screen. |
| P3.5 | Font size scaling | All | Support `font-size` adjustment for reps with vision issues. Use `rem` units, not `px`. |

---

## (C) Offline & Low-Bandwidth Strategy Recommendations

### C1. Architecture Decision: Offline-First Is NOT Optional

This app serves 200+ reps visiting ~5 stores/day. Field conditions guarantee intermittent connectivity. The current architecture (live-API-only, localStorage for photos) will cause **data loss, rep frustration, and back-office confusion daily**.

**Recommended architecture: Cache-First + Queue Sync**

```
                     ┌───────────────────────────┐
                     │   Service Worker           │
                     │   ┌─────────────────────┐  │
                     │   │ Static Cache        │  │
                     │   │ (HTML, CSS, JS,     │  │
                     │   │  icons, fonts)       │  │
                     │   └─────────────────────┘  │
                     │   ┌─────────────────────┐  │
                     │   │ API Cache           │  │
                     │   │ (stores list,       │  │
                     │   │  dashboard data)     │  │
                     │   └─────────────────────┘  │
                     └───────────┬───────────────┘
                                 │
Browser ←→ IndexedDB ←→ Service Worker ←→ Network
           (offline             │
            queue +              │
            draft store)         │
                         ┌───────┴────────┐
                         │ On reconnect:  │
                         │ replay queue → │
                         │ POST successes │
                         │ → clear queue  │
                         │ POST failures  │
                         │ → keep, alert  │
                         └────────────────┘
```

### C2. Specific Offline Recommendations

| # | Layer | Recommendation |
|---|-------|----------------|
| **O1** | **Service Worker** | Register SW that caches `index.html`, `dashboard.html`, `visit-card.html`, `noo.html`, `report.html`, all JS/CSS/fonts. Network-first for API, cache-first for static assets. |
| **O2** | **IndexedDB Request Queue** | On any POST failure → enqueue `{url, method, body, timestamp, retryCount}`. Background sync when online. Show queue badge in header. |
| **O3** | **Photo Upload Strategy** | Upload photo to server **immediately** after compression, before user continues. If offline → store in IndexedDB (not localStorage — higher quota, survives cache clear). Server returns photo UUID → use that in checkin/checkout payload. |
| **O4** | **Store List Cache** | Cache `GET /api/stores` response in IndexedDB. Show cached list immediately on page load while fetching fresh data. If offline, show cached data with "Data tersimpan — mungkin tidak terbaru" banner. |
| **O5** | **Search Index** | For "Cari toko" (luar rute search), cache all stores locally. Perform client-side search from cache. Only sync on explicit refresh. Eliminates 2-5s search delay on 2G. |
| **O6** | **Checkin/Checkout Queue** | If POST fails → queue with auto-retry every 30s. Store timestamp + place_uuid + photo UUIDs. On success → clear from queue. User sees checkin as "pending" with clock icon until confirmed. |
| **O7** | **Draft NOO Save** | Save NOO form as JSON draft in IndexedDB on each blur. Restore on page load or show "Lanjutkan draft" prompt. Prevents 14-field re-entry on accidental navigation. |
| **O8** | **Bandwidth Detection** | Use `navigator.connection.effectiveType` (Chrome) to detect 2G → disable photo upload (store offline), reduce image quality to 0.4, defer non-critical API calls. |

### C3. Low-Bandwidth Settings (V1.1)

Add a **"Mode Hemat Data"** toggle in Settings:
- **Photo quality cap:** JPEG 0.4 (instead of 0.6) → ~60-80KB per photo instead of 100-200KB
- **Disable animations / spinners**
- **Reduce image quality** on store item photos
- **Batch upload** photos after form completion instead of inline
- **Show estimated data usage** per session

---

## (D) Specific Error-State Improvements

### D1. Error Message Pattern (Standardize)

Every error state should follow this pattern:

```
┌──────────────────────────────────────┐
│ ⚠️ [or ❌ / ℹ️]  Title (Bahasa)       │
│ Deskripsi singkat (optional)          │
│                                       │
│ [🔄 Coba Lagi]  [✕ Tutup]            │
└──────────────────────────────────────┘
```

**Rules:**
- Icon (⚠️ = warning, ❌ = error, ℹ️ = info, ✅ = success)
- Title: 1 line, bold, Bahasa
- Description: 1-2 lines max
- Retry button for all mutable errors
- Dismiss button (auto-dismiss after 8s only for non-critical)
- Color-coded border (red/orange/blue/green)
- Not blocking — use fixed-bottom toast or inline banner
- `role="alert"` for screen readers

### D2. Specific Error Message Improvements

| Current | Problem | Improved |
|---------|---------|----------|
| "Gagal memuat data: [message]" | Generic, no retry | "⚠️ Gagal memuat data toko. [🔄 Coba Lagi]" |
| "Gagal: Network error..." | Reactive only | Proactive: "📡 Koneksi terputus. Data akan disimpan offline" |
| "Tunggu timer selesai" | Alert, blocking | Inline: disable button + show "⏱ Tunggu {remaining}" on the button itself |
| "Terlalu banyak percobaan. Coba lagi dalam X detik" | Static text | Live countdown: "🔒 Coba lagi dalam 45 detik" with progress bar |
| "Session expired" redirect | No context | Brief toast before redirect: "Sesi berakhir. Silakan login ulang." |
| Checkout without photos | Not warned | "ℹ️ Belum ada foto kunjungan. Ambil foto dulu?" (optional reminder) |
| No-store-empty-state | "Tidak ada toko dalam daftar" | Add "Hubungi admin jika seharusnya ada kunjungan hari ini" — actionable |

### D3. Server 400/409/500 — Retry & Recovery Matrix

| Status | User Facing Message | Retry? | Fallback |
|--------|--------------------|--------|----------|
| 400 (bad request) | "❌ Data tidak valid: [detail]" | ❌ No (fix input) | Keep form state, highlight field |
| 409 (conflict) | "⚠️ Kunjungan sudah ada. Selesaikan kunjungan sebelumnya." | ❌ No (resolve conflict) | Navigate to open visit |
| 429 (rate limit) | "🔒 Terlalu banyak permintaan. Coba lagi N detik." | ✅ Auto-retry | Show countdown, enable button when done |
| 500 (server error) | "⚠️ Gagal menyimpan. Coba lagi." | ✅ Yes (3 attempts) | Queue offline after 3 failures |
| 502 (bad gateway) | "⚠️ Layanan sedang sibuk. Coba lagi." | ✅ Yes (exponential backoff) | Queue offline after 3 failures |
| Network offline | "📡 Tidak ada koneksi. Data disimpan lokal." | ✅ Auto on reconnect | Queue + sync icon |

### D4. Visit Crash Recovery (§15.6)

The spec says: "Visit stays as 'checkin' (no auto-delete)" — this is **good as a data-integrity choice** but needs a **recovery UI**:

```
Visit Card → Store list shows:
┌──────────────────────────────────────┐
│ 🏪 TOKO BERKAH (PASAR TANAH ABANG)   │
│ ⚠️ Kunjungan belum selesai            │
│ [▶️ Lanjutkan]  [❌ Batalkan]         │
└──────────────────────────────────────┘
```

- "Lanjutkan" → reopens modal, resumes timer (2:30 remaining from stored `timerStart`)
- "Batalkan" → sends checkout with status='cancelled', duration=null
- If user navigates to another store → "Selesaikan kunjungan di Toko Berkah dulu"

---

## Appendix: Micro-Interaction Checklist (For QA)

| ✅ | Micro-interaction | Pass Criteria |
|----|-------------------|--------------|
| ☐ | Button state change | Enabled → Disabled → Spinner → Success/Error — visually distinct |
| ☐ | Form field focus | Visible outline/highlight (not just browser default blue) |
| ☐ | Error-to-field association | `aria-describedby` links error to field; message is adjacent |
| ☐ | Dark-mode ready | All color pairs pass WCAG AA in `prefers-color-scheme: dark` |
| ☐ | Touch target padding | `min-height: 48px` on every tap target |
| ☐ | Timer completion feedback | Color change + vibration + button glow |
| ☐ | Photo upload progress | "Memproses..." → "Mengirim..." → "✅ Terkirim" |
| ☐ | Offline banner | Persistent when offline, auto-hides on reconnect |
| ☐ | Loading skeleton | Layout-matched gray blocks, not standalone spinner |
| ☐ | Retry affordance | Every error banner has "Coba Lagi" button |
| ☐ | Empty state action | Every empty state has a CTA ("Tambah Toko" / "Hubungi Admin") |
| ☐ | Session expiry grace | Toast before redirect, preserve intent in sessionStorage |

---

*End of review. All recommendations reference the USER-FLOWS.md specification line numbers. For color contrast values, assumed Bootstrap palette — verify against actual CSS.*