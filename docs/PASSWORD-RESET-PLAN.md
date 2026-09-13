# Password Reset & Change — Implementation Record

> **Status:** IMPLEMENTED + DEPLOYED + LIVE-VERIFIED (2026-09-12) · supersedes PLAN status in the same doc

## What was built (additive, reversible)

### Data model — `deploy/db/init/16-password-reset.sql` (applied live)
```sql
CREATE TABLE wim_password_resets (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES wim_users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,          -- SHA-256, never plaintext
    created_by INT REFERENCES wim_users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,            -- NOW()+24h
    used_at TIMESTAMP                          -- NULL until consumed (single-use)
);
ALTER TABLE wim_users ADD COLUMN password_changed_at TIMESTAMP;  -- audit
```
Indexes on `user_id` and `expires_at`. Grants added for `wim_app`.

### Middleware API — `frontend/serve.py`
| Route | Who | Behavior |
|---|---|---|
| `POST /api/admin/users/:id/password/reset` | admin | issues a **one-time token** (returned as `/reset-password.html?token=<T>` link), 24h expiry, records `created_by` |
| `POST /api/admin/users/:id/password/set` | admin | admin sets a temp password directly (bcrypt) |
| `POST /api/reset-password` | public (token holder) | validates token (exists + unexpired + unused), sets new bcrypt password, marks `used_at`, **revokes all the user's sessions** |
| `POST /api/password/change` | authenticated | self-serve change with `{old_password, new_password}` (cookie session) |

All password writes go through bcrypt. Reset/set revoke the user's active sessions (force re-login) — secure against a leaked password. `secrets.token_urlsafe(32)` for tokens; only SHA-256 stored.

### Frontend
- **`admin/users.html`** edit popup gains two actions:
  - **🔗 Reset via link** — generates a one-time link and shows it in a prompt for the admin to copy→WhatsApp (link is `https://sales.sqa.web.id/reset-password.html?token=…`).
  - **🔑 Set password** — admin types a temp password directly.
- **`frontend/reset-password.html`** — mobile-friendly page (no login needed): user enters new password + confirm from the `?token=` prefilled field → calls `api/reset-password`.

### Deploy
- LXC 111 (middleware `serve.py` + `reset-password.html`) and LXC 113 (`admin-server.py` + `users.html`) redeployed; both services restarted.

## Deployment notes
- Middleware `serve.py` on LXC 111, admin `admin-server.py`+`users.html` on LXC 113.
- **IMPORTANT — public UI origin is LXC 112 nginx (`/var/www/wim-sales`), NOT the middleware docroot.** The reset page `frontend/reset-password.html` must be copied to LXC 112's webroot so `https://sales.sqa.web.id/reset-password.html` resolves (otherwise the link lands on the login page via nginx try_files fallback).

## Live verification (real API calls, 2026-09-12)
- ✅ Admin issues reset link (id 3 / budi) → `{status:ok, link, expiresInHours:24}`
- ✅ Token completes reset → sets password
- ✅ **Token reuse rejected** (`400 "Link tidak valid, sudah dipakai, atau kadaluarsa"`)
- ✅ Login with the new password succeeds; old password fails
- ✅ Admin direct-set works (old pw invalidated)
- ✅ Self-serve change (old→new, cookie session) works; wrong old-password → `403`
- ✅ Sessions revoked on reset/set (test user forced re-login)
- 🧹 Test tokens cleaned from `wim_password_resets`

## Notes
- **No SMTP** — exactly as the user wanted: the reset link is admin-generated and delivered however the admin prefers (WhatsApp).
- **Security stance** (per expert review): SHA-256 token in DB is fine because tokens are high-entropy `secrets.token_urlsafe(32)`; bcrypt reserved for actual passwords. Single-use + 24h expiry + session-revoke covers the realistic risks.
- Design/analysis in the earlier section of this file.
- **QA:** 10 subagent login/usecase tests + 1 regression-check subagent dispatched after deployment.

---

## Expert review (3 subagents, deleg_667ff084) — verdict: "ACCEPTABLE-WITH-FIXES"

Reviewed the design pre/post-implementation. Core shipped design confirmed correct: SHA-256-hashed 256-bit token (rejected bcrypt — a slow KDF is pointless for server-random high-entropy tokens and breaks hash-indexed lookup), single-use atomic consume, 24h expiry, revoke-sessions-on-use, admin-initiated link primary.

**Applied immediately (additive DDL, cannot break running QA):**
- ✅ `idx_sessions_user` on `wim_sessions(user_id)` — makes session-revoke fast (recommended)
- ✅ `idx_pr_exp_unused` partial index on `wim_password_resets(expires_at) WHERE used_at IS NULL` — cheap sweeper

**Post-QA fixes (from the 10-subagent batch, deleg_6678ebbe):**
- ✅ **`reset-password.html` missing from the public origin** — deployed to LXC 112 nginx webroot `/var/www/wim-sales/` (public UI host), so `https://sales.sqa.web.id/reset-password.html` now serves the reset form (was returning the login page via nginx try_files fallback).
- ✅ **Session revocation on password reset was a no-op in practice** — `_revoke_user_sessions` deleted the `wim_sessions` DB row but NOT the in-memory `SESSIONS` cache, so old session cookies stayed valid (subagent task 3 FAIL). Fixed to purge both the `SESSIONS` dict (matching on cached `id`) and the DB rows. Re-verified live: session 200 → (reset) → 401.

**Deferred (behavioral; will not ship mid-QA — intentionally waiting for the 10-subagent batch to finish):**
1. Single-active-pending-reset per user (a new generate invalidates prior rows) — prevents admin double-sends / token confusion
2. Revoke a user's outstanding unused reset tokens on admin direct-set
3. `must_change_password` flag on the admin-set temp-password path (force change on next login)
4. Rate-limit / lockout on `POST /api/reset-password` (per-token attempt counter)
5. Enumeration-safe uniform error responses for unknown-user vs bad-token
6. New-password policy: forbid reusing current password
7. Optional `revoked_at` column for explicit soft-revoke

**Rejected as overkill (per experts):** bcrypt token hashes, TOTP primary, separate password-change audit table, storing IP/UA/device, plaintext tokens, row retention/partitioning.