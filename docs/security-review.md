# Security review (v1.0.0)

Reviewed at the close of Phase 11. Findings and their disposition.

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

## Accepted risks / operator notes
| # | Item | Note |
|---|------|------|
| 1 | **Media (receipts) served without auth** | URL path is dated + unguessable but not access-controlled. Low sensitivity (a bank transfer screenshot). To lock down: serve `/media/receipts/` via an authenticated Django view or nginx `internal` + `X-Accel-Redirect`. |
| 2 | **phpMyAdmin** | dev-only host port; in prod it is `expose`-only (not published) and not routed by the main nginx. Recommend removing the service entirely in prod or fronting it with basic-auth + IP allow-list. |
| 3 | **Panel password visible in Django admin** | the `admin_password_enc` field renders decrypted in the change form for staff who can reach Django admin (superusers). The DRF admin API never exposes it. |
| 4 | **Staff refresh tokens are not rotated/blacklisted** | 30-minute access window limits exposure; acceptable for an internal panel. |
| 5 | **No Content-Security-Policy header** | SPAs load same-origin JS/CSS + Google Fonts only. Add a CSP in `nginx/prod.conf` if desired. |
| 6 | **Secrets pasted in the build transcript** | the panel password, GitHub PAT and Cloudflare token were provided in plaintext during setup — **rotate them** now that setup is complete. |
| 7 | **`db/init` test-grant script** | grants the app user rights on `test\_%` databases only; harmless in prod, used by the test suite. |

## Not applicable
- SSRF: no user-controlled outbound URLs.
- Mass assignment: DRF serializers enumerate fields explicitly.
- Secrets in logs: the `caspintunel` logger never logs credential values;
  encrypted fields log as ciphertext.
