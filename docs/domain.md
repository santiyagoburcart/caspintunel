# Domain & Cloudflare

**Settings → Domain & Cloudflare** (`/panel/settings/domain`, super admins only) holds the Cloudflare API token and
moves the whole site to a new domain step by step, with a status per step, a transition period for the old domain
and a one-click rollback. Recovery on the server: `./scripts/domain.sh show | rollback`.

## Cloudflare token

* Stored **encrypted** in the DB (`domain_config.cloudflare_token`, `FIELD_ENCRYPTION_KEY`), write-only like the bot
  tokens: the API never returns it. `.env` `CLOUDFLARE_API_TOKEN` stays the fallback (`ops/cloudflare.configured_token`:
  panel first, then .env — also used by `manage.py configure_dns`).
* **Test** verifies the typed token, or else the saved one: `GET /user/tokens/verify` (must be *active*), then the zones
  it can see with the permissions Cloudflare reports per zone. A clear error is shown if it sees no zone or
  has no `#dns_records:edit` (**Zone → DNS → Edit**). Token for the wizard: *Zone → Zone → Read* + *Zone → DNS → Edit*.

## The wizard

| Step | Where | What happens |
|---|---|---|
| a) new domain | panel | domain (+ `www`), the Cloudflare zone (auto-picked from the token's zones) or **manual DNS** |
| b) DNS | panel → Cloudflare API | A records `@`, `www`, `mail` → this server's IP (`SERVER_IP`), DNS-only. Manual: the exact records to create. **Check DNS** asks public DNS-over-HTTPS resolvers (Cloudflare, Google) — what Let's Encrypt sees; `@` and `www` must answer this IP (`mail` optional) |
| c) TLS | host | `certbot certonly --webroot --cert-name <domain>` in the certbot container (`mail.` included when it resolves); the cert is checked (valid, covers the names) |
| d) apply | host | see below — all or nothing |
| e) transition | host | the old domain answers **301** to the new one (308 for POST etc., so e.g. the SMS app's POSTs keep their body) for `transition_days` (setting, default 14; 0 = none). Then the beat task asks the host to remove it, or **Remove the old domain now** |
| f) checklist | panel | manual steps with links: iPhone Shortcut URL, Android SMS app URL, BotFather (login domain / Mini App link), Brevo sender domain, mail server, tell resellers / customers |

**Apply** (`scripts/domain.sh`): certificate check → `nginx/domain/active.conf` (HTTPS vhost of the new domain + the
old domain's redirect vhosts) → `nginx -t` + reload → `.env`: `DOMAIN`, `PUBLIC_BASE_URL`, `ALLOWED_HOSTS` and
`CSRF_TRUSTED_ORIGINS` (+ the new names; the old ones stay until the transition ends), `MINIAPP_URL` (if it used the old
domain), `CLOUDFLARE_ZONE`, and `MAIL_DOMAIN` pinned to the old domain (the mail server keeps its identity; moving mail
is manual) → app containers recreated with the new `.env` (`web`, `daphne` rolling like `update.sh`; celery, bots) →
**verify through nginx over TLS**: `https://<new>/api/v1/health/` = 200 and the old domain redirects. Any failure:
`.env`, the nginx config and the containers go back to the previous state and the reason is shown.

After a successful apply the panel updates `site_config.site_domain` (portal / renew / ticket / bot / Shortcut links —
unless it was set by hand to something else) and the sales bot's **Mini App menu button** (Telegram
`setChatMenuButton`). Email links follow `PUBLIC_BASE_URL`.

**Rollback** (panel button or `./scripts/domain.sh rollback`): the same switch back to the previous domain (its
certificate must still be valid — certbot keeps renewing it while its DNS points here); the current domain is no
longer served.

Every step is audit-logged (`domain.*`); every action and host result is a toast with the real reason.

## Files

| File | Written by | |
|---|---|---|
| `backups/.domain-request.json` | panel | one request at a time; the host deletes it before acting (never a loop) |
| `backups/.domain-status.json` | host | last result `{id, action, ok, message, at}` — folded into the wizard by `domain.sync()` (on every panel call and every 5 min in beat) |
| `backups/.domain-state.json` | host | current / old / previous domain (no secrets) |
| `nginx/domain/active.conf` | host | mounted at `/etc/nginx/domain`; when present the nginx entrypoint includes it instead of the `.env` domain's vhost (a manual upload in `nginx/manual-certs` still wins — the wizard refuses while one is active) |
| `.domain-state/` | host | root-only: `state.json`, the `.env` / nginx backups of the switch in progress |

The host side runs from cron, like Paths:

```cron
* * * * * /root/caspintunel/scripts/domain.sh apply-request >> /var/log/caspintunel-domain.log 2>&1
```

## Test

`./scripts/test-domain.sh` — throw-away stack (`domaintest`), fake domains `old.test → new.test`, a mock Cloudflare
API + DoH (`scripts/domaintest/cfmock.py`) and a fake certbot (self-signed); everything else real: token save / test,
DNS records, DNS check, certificate, apply (redirects 301/308, `.env`, rolling restart, nginx restart), retire,
panel rollback, an apply that fails `nginx -t` and is rolled back, CLI rollback, audit. Unit tests:
`apps/adminpanel/tests/test_domain.py`.
