# Visit Check-in Fix — Root-Cause Analysis, Plan & Implementation

> **Date:** 2026-09-11 · **Status:** Plan → Implement
> Reported: check-in photo → **nginx 413 Entity Too Large**; afterwards the frontend
> thinks "not checked in" while the DB already has the visit → can't re-check-in → can't
> finish the visit. The 3-min timer/checked-in state also didn't restore after moving pages.

## 1. Root-cause analysis

### A. nginx 413 (Entity Too Large)
- The field app's visit check-in sends the **selfie as a full-resolution base64 data-URL**
  inside the JSON body (`wim_visits.checkin_photo`).
- `visit-card.html` does **NOT** compress images. A phone selfie is ~1.5–4 MB → base64
  inflates ~33% → **> 1MB**.
- nginx on LXC 112 has **no `client_max_body_size`**, so it uses the **default 1 MB** and
  answers **413 Request Entity Too Large** *before* the request reaches the middleware.
  => The check-in POST is rejected; **no visit row is created on the server**, but the
  user (reasonably) believes they checked in.

**Evidence:** `cat /etc/nginx/sites-enabled/wim-sales` shows no `client_max_body_size`,
so default 1MB. The published absensi page already had a `compressImage()` helper —
**visit-card never got it** — so absensi avoided 413 but visit-card did not.

### B. Check-in state desync (frontend vs DB)
`visit-card.html` only loads the active visit **once on page load** (`loadActiveVisit()`).
- `openStore()` sets `checkinDone=false` and shows "📍 Check-in di Toko" **unless**
  `activeVisit.placeUuid===uuid` (i.e. the *once-loaded* active visit matches).
- If the user moves pages (to order / stock / back) and the in-memory `activeVisit` is
  stale, or `loadActiveVisit` returned nothing on the previous visit, reopening the store
  shows "not checked in" **even though `wim_visits` has an active row**.
- `restoreCheckinState()` only runs when `activeVisit` matches — so the 3-min timer and
  "✅ Check-in Berhasil" button never restore in the desynced case.

**Evidence:** Live DB has rows with `checkout_at IS NULL` (e.g. user 2 = Andi has FOUR
open visits), yet the UI can show "Check-in di Toko".

### C. Multiple active visits / no per-store query
- The check-in guard is `WHERE user_id AND place_uuid AND checkout_at IS NULL` — it only
  blocks a *second* check-in to the **same** store, not a second active visit overall.
  A rep can end up with several open visits, which is what made the DB look "already
  checked in" for other stores.
- `/api/visits/active` returns the newest open visit with no `place_uuid` filter, so the
  frontend can't ask "is THIS store checked in right now?".

## 2. Fixes

### Frontend — `visit-card.html`
1. **Add `compressImage(dataUrl, maxWidth=900, quality=0.62)`** (reuse the proven helper
   already in absensi.html) and route **both** the check-in selfie (`useSelfieFilePicker`)
   and the store photos (`useFilePicker`) through it before storing/sending. This shrinks
   payloads well under the body limit → no more 413.
2. **Make check-in state DB-authoritative (idempotent re-check on store open):**
   - New `async function loadActiveVisitFor(placeUuid)` → `GET /api/visits/active?place_uuid=X`
     and returns the open visit for that exact store (or null).
   - In `openStore()`, replace the reliance on the stale global `activeVisit` with an await
     of `loadActiveVisitFor(storeUuid)`: if an active visit exists → `restoreCheckinState()`
     (sets ✅ button + restores the timer from server `checkin_at`); else show "Check-in".
   - `restoreCheckinState` becomes the single source of truth for checked-in UI.
3. **Remove the duplicate `handleCheckin` definition** (two identical ones exist — the
   second shadows the first; harmless but confusing).
4. After check-in succeeds, still set the local flag + timer (immediate feedback), but the
   reopen path now always re-verifies from the DB.

### Backend — `frontend/serve.py`
1. **`/api/visits/active` accepts optional `?place_uuid=`** to filter the active visit to a
   specific store:
   `WHERE user_id=%s AND checkout_at IS NULL AND (%s::text IS NULL OR place_uuid=%s) ORDER BY id DESC LIMIT 1`.
2. **Check-in: prevent a second concurrent active visit.** When checking in, if the user
   already has an open visit at a *different* store, return `409` with a clear message
   ("Selesaikan kunjungan sebelumnya dulu") so we never accumulate multi-open visits.
   (Keeps the per-store dedup AND adds per-user guard.)
3. Raise the `_read_body` guard is already 5MB; with compression that's fine — no change
   strictly needed, but keep.

### Infra — nginx (LXC 112)
1. Add `client_max_body_size 20m;` to the `wim-sales` server block (server-level so the
   `/api/` proxy inherits it). This is a robust safety net even before compression; with
   compression the payload is ~100–250 KB but the larger cap prevents *any* future 413.
2. `nginx -t && nginx -s reload`.

## 3. Deploy steps
- Edit files in repo, `python3 -m py_compile frontend/serve.py`, node-check visit-card inline JS.
- Commit + push.
- Deploy `frontend/serve.py` → LXC 111, `frontend/visit-card.html` → LXC 112 (/var/www/wim-sales).
- Update nginx on LXC 112 + reload.
- Restart `wim-mid` on LXC 111.

## 4. QA
Deploy **5 subagents acting as sales reps** to walk the full workflow on the live site:
check-in (selfie) → input stock → create order → finish kunjungan — plus the failure
modes (photo must be compressed → no 413; reload during an active visit → must restore
checked-in state + timer; no duplicate check-in). Iterate on failures until all pass.
Steps after the fix:
```
- Andi @ sales.sqa.web.id / visit-card.html
- Pick a store (e.g. GROSIR JAKARTA or a stable route store)
- Check-in with selfie  → expect 200 (no 413), button ✅
- Reload page, reopen store → must show ✅ + timer running (DB-authoritative)
- Input stock → submit → success
- Buat pesanan → order created
- Selesaikan kunjungan → status visited, checkout_at set
```