# Security review (v1.0.0)

Reviewed at the close of Phase 11. Findings and their disposition.
Post-1.0 follow-up (2026-09) resolved items 1–5 below — see **Resolved** section.

## Handled well
- **Secrets** — only in `.env` (git-ignored, `chmod 600` by `install.sh`).
  `Panel.admin_password_enc`, `Panel.token_cache`, `TelegramConfig.token` are
  Fernet-encrypted at rest (`FIELD_ENCRYPTION_KEY`). DKIM private key in
  `backend/mail-keys/` (git-ignored, `0600`).
- **Token audiences are separate** — customer JWT (SimpleJWT, 30 m access, 7 d
  refresh, rotation + blacklist), staff JWT (HS256, `type=staff_access` claim),
  SMS device token (`secrets.token_urlsafe(32)`, `is_active`, rotatable).
- **Rate limiting** — `auth` 10/min (login/register/reset/verify), `receipt`
  20/hour, `sms_ingest` 240/min; anon 60/min, user 600/min.
- **Prod hardening** (`config/settings/prod.py`) — `DEBUG=False`, refuses to boot
  without a real `SECRET_KEY`/`FIELD_ENCRYPTION_KEY`, HSTS, `nosniff`,
  `X-Frame-Options: DENY`, secure cookies, SSL redirect, proxy SSL header.
- **ALLOWED_HOSTS** — env baseline; the panel-set domain is *added* at runtime,
  never allowed to remove the baseline. Not `*` in prod.
- **Injection** — 100% Django ORM; the Cloudflare/DNS/health clients use params.
- **Uploads** — receipts are `ImageField` (Pillow validates), size-capped at 12 MB
  (`DATA_UPLOAD_MAX_MEMORY_SIZE` + nginx `client_max_body_size`), stored under a
  dated path with Django's filename sanitisation.
- **Update flow** — the web container only writes a sentinel file (no RCE); the
  host watcher pulls from the **private** repo's `main` via `git reset --hard`.
- **`setup_github.sh`** — pushes with a command-scoped `http.extraheader`; the
  token is never persisted in `.git/config`.
- **mysqldump** — password passed via `MYSQL_PWD` env, not argv.
- **DKIM/SPF/DMARC** — 2048-bit RSA, `~all` softfail, `p=quarantine`.

## Resolved (post-1.0, 2026-09)

| # | Item | Fix |
|---|------|-----|
| 1 | **Media (receipts) served without auth** | `GET /api/v1/payments/<id>/receipt/` (`ReceiptFileView`) authorises first — receipt owner, or a panel operator with `payment.view` — then streams the file (dev) or `X-Accel-Redirect`s to an nginx `internal` location (`SERVE_MEDIA_VIA_XACCEL`, prod default). nginx returns **404** for `/media/receipts/` directly (both dev + prod confs). The serializer now emits `receipt_url` (the API endpoint), never a media path; the admin SPA fetches it as an authenticated blob. |
| 2 | **phpMyAdmin exposed** | Moved to the compose `profiles: ["tools"]` — a normal `docker compose up` **does not start it**. When explicitly run (`--profile tools`) the port binds to `127.0.0.1` only (SSH-tunnel access). Prod override no longer publishes it. |
| 3 | **Panel password visible in Django admin** | `PanelAdminForm` — `admin_password` is a write-only `PasswordInput(render_value=False)`, the stored value is never rendered; blank = keep. Same treatment applied to `TelegramConfigForm` (bot token). List view shows a "password set" / "token set" boolean. |
| 4 | **Staff refresh tokens not rotated** | `/api/v1/admin/auth/refresh/` now rotates: the consumed refresh token's `jti` is blacklisted in the cache until its natural expiry (`revoke_refresh`), `decode()` rejects a re-used `staff_refresh`. The SPA already stored the rotated pair. Refresh tokens are single-use. |
| 5 | **No Content-Security-Policy** | `nginx/prod.conf` sets a strict CSP (`default-src 'self'`, `script-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`, …) plus `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `X-Frame-Options`, `nosniff`. `nginx/conf.d/caspintunel.conf` (dev) sets the same headers with a Vite-compatible CSP (`'unsafe-inline' 'unsafe-eval'`, `ws:`). |

## Accepted risks / operator notes
| # | Item | Note |
|---|------|------|
| 6 | **Secrets pasted in the build transcript** | the panel password, GitHub PAT and Cloudflare token were provided in plaintext during setup — **rotate them** now that setup is complete. |
| 7 | **`db/init` test-grant script** | grants the app user rights on `test\_%` databases only; harmless in prod, used by the test suite. |
| 8 | **CSP allows `style-src 'unsafe-inline'`** | React sets element `style` attributes and the Monitoring page injects a `<style>` block; inline styles are low-risk (no script execution). Scripts remain `'self'`-only in prod. |
| 9 | **phpMyAdmin, when opted in, has no extra auth** | it's localhost-bound and meant for short-lived tunnelled sessions; stop it (`docker compose stop phpmyadmin`) when done. Add HTTP basic-auth in front if you leave it running. |
| 10 | **Django admin (`/admin/`) still reachable** | protected by the Django superuser login; break-glass only. Consider an IP allow-list at nginx if not needed day-to-day. |
| 11 | **User site is frameable by `*.telegram.org`** | required for the Telegram Mini App (Telegram Desktop/Web embed it in an iframe). Scoped to the user site only — `/panel/`, `/api/`, `/admin/` keep `frame-ancestors 'none'` + Django's `X-Frame-Options: DENY`. A Mini App session is a plain customer JWT (no ambient cookie auth), so clickjacking a framed user site can't drive privileged actions. |
| 12 | **Mini App loads `telegram.org/js/telegram-web-app.js`** | Telegram's official SDK, `script-src`-allowed on the user site only (not the panel). Loaded from Telegram's CDN as they recommend (keeps it current); it makes no network calls of its own. |

### Mini App validation (see `docs/telegram-miniapp.md`)
`POST /api/v1/auth/telegram/miniapp/` verifies Telegram's `initData` HMAC against
the **sales bot token, server-side**, on every launch (`telegram_auth.validate_init_data`
— constant-time compare, `auth_date` freshness, `hash`/`signature` handled per
spec). Only then is a normal customer JWT issued for the `telegram_id`-linked
account. The bot token never reaches the frontend. Forged / tampered / expired /
wrong-token initData → **401**; unconfigured → **503**. Covered by 11 tests in
`apps/accounts/tests/test_telegram_miniapp.py`.

## Not applicable
- SSRF: no user-controlled outbound URLs.
- Mass assignment: DRF serializers enumerate fields explicitly.
- Secrets in logs: the `caspintunel` logger never logs credential values;
  encrypted fields log as ciphertext.
