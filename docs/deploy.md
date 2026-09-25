# Deploy

## Compose topology

`docker-compose.yml` is dev; `docker-compose.prod.yml` overrides it for production
(gunicorn, static SPA images, `nginx/prod.conf`, no exposed dev ports).

```
nginx ──┬─ /            → frontend_user   (static SPA)
        ├─ /panel/      → frontend_admin  (static SPA)
        ├─ /api/ /admin/ /static/ /media/ → web (Django + gunicorn)
web · celery_worker · celery_beat · bot_sales · bot_backup   (image: caspintunel-backend)
db (MySQL 8) · redis · phpmyadmin · certbot · mailserver
```

`docker-compose.offline.yml` is a third overlay that sets `pull_policy: never`
everywhere — for air-gapped installs from pre-loaded images (see `offline.md`).

## TLS — two modes

nginx listens on 80 and 443. `/nginx-entrypoint.sh` enables the HTTPS vhost
(`conf.d/10-ssl.conf`, from `ssl.conf.template`) as soon as a cert is present —
**a missing cert never stops nginx**, it just serves HTTP. Precedence:

1. **manual** — `nginx/manual-certs/{fullchain,privkey}.pem`
2. **Let's Encrypt** — `nginx/letsencrypt/live/<domain>/`

### auto (Let's Encrypt)
```bash
./scripts/init-letsencrypt.sh --prod           # <domain> + www (+ mail if it resolves)
./scripts/init-letsencrypt.sh --prod --staging  # test against LE staging first
```
DNS preflight (public resolvers) → webroot HTTP-01 → nginx restart. Renews via the
`certbot` service every 12 h; nginx reloads every 6 h. Contact address =
`LETSENCRYPT_EMAIL` (default `admin@<domain>`), never the site-admin email.

### manual (upload a cert — for filtered networks)
Obtain the cert anywhere (DNS-01, a jump host, a commercial CA), then:
```bash
./scripts/ssl-manual.sh --prod  /path/fullchain.pem  /path/privkey.pem
```
It validates the pair (key matches cert), copies them to `nginx/manual-certs/`,
and restarts nginx. The manual cert **wins** over any Let's Encrypt cert, so this
is also how you override a broken auto-renewal.

## Active domain

`DOMAIN` in `.env` is the active domain (currently **`aicaspin.ir`** — the
`caspin.skin` zone has a Cloudflare ToS hold). `install.sh` / `seed` also set
`site_config.site_domain` to it. Everything else derives at runtime:
`ALLOWED_HOSTS` / `CORS` / `CSRF` / email links.

### Changing it — no rebuild
1. `.env`: `DOMAIN=`, `ALLOWED_HOSTS=`, `CORS_ALLOWED_ORIGINS=`, `CSRF_TRUSTED_ORIGINS=`, `PUBLIC_BASE_URL=` → `docker compose up -d` (recreate, no build)
2. panel → Branding, or `docker compose exec web python manage.py seed` → syncs `site_config.site_domain`
3. `DynamicAllowedHostsMiddleware` also adds `site_config.site_domain` (+`www`) to
   `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` at runtime (60 s cache), so the DB
   value alone is enough for host validation even before an env edit.
4. DNS: `configure_dns` (below) with the new zone.

## DNS (Cloudflare)

```bash
docker compose exec web python manage.py configure_dns --no-mail          # dry-run, A + www only
docker compose exec web python manage.py configure_dns --no-mail --apply
docker compose exec web python manage.py configure_dns --apply            # + mail records, when mail is ready
```

`--no-mail` writes only:

| Type | Name | Value | Proxy |
|---|---|---|---|
| A | `<domain>`, `www` | server IP | proxied (orange) |

Full run adds (when the mail server is up):

| Type | Name | Value | Proxy |
|---|---|---|---|
| A | `mail` | server IP | **DNS-only** (grey — SMTP needs the real IP) |
| MX | `<domain>` | `mail.<domain>` (10) | — |
| TXT | `<domain>` | `v=spf1 mx a:mail.<domain> ~all` | — |
| TXT | `_dmarc` | `v=DMARC1; p=quarantine; …` | — |
| TXT | `default._domainkey` | generated DKIM public key | — |

Existing VPN-node subdomain records are never touched.

## Mail server (Postfix + Dovecot)

The `mailserver` compose service is [docker-mailserver](https://docker-mailserver.github.io/)
(Postfix + Dovecot + OpenDKIM + OpenDMARC). It reuses the Let's Encrypt cert
(`SSL_TYPE=manual`, needs `mail.<domain>` in the cert SANs — `init-letsencrypt.sh`
includes it). The app talks to it over the private docker network
(`EMAIL_HOST=mailserver`, port 25, `PERMIT_DOCKER=connected-networks` — no auth).

First-run setup:

```bash
docker compose up -d mailserver
# within 120s, add at least one mailbox:
docker compose exec mailserver setup email add noreply@<domain> '<password>'
docker compose exec mailserver setup config dkim keysize 2048 selector default domain <domain>
# publish the DKIM public key it prints (or re-run configure_dns which reads it):
docker compose exec mailserver setup config dkim   # shows the DNS TXT value
docker compose restart mailserver            # force-recreate if OpenDKIM tables stay empty
docker compose exec mailserver opendkim-testkey -d <domain> -s default -vvv   # -> "key OK"
```

`setup config dkim` generates its own key; publish **that** public key at
`default._domainkey.<domain>` (a `configure_dns --apply` will pick it up from
`mail/config/opendkim/keys/<domain>/default.txt`).

### Outbound port 25 — you need a relay

Vultr / DigitalOcean / most clouds **block outbound port 25**, so the mail server
can't deliver directly to external MX servers (Gmail etc.) — mail to local
`@<domain>` mailboxes works, external mail sits in the queue. Fix with a relay:

```
SMTP_RELAY_HOST=smtp.mailgun.org      # or sendgrid / brevo / SES / smtp.gmail.com
SMTP_RELAY_PORT=587
SMTP_RELAY_USER=postmaster@mg.<domain>
SMTP_RELAY_PASSWORD=...
```

```bash
docker compose up -d --force-recreate mailserver   # RELAY_* is read at start-up
docker compose exec web python manage.py send_test_email you@example.com
```

**Full walkthrough (which provider, domain verification, per-provider
credentials, troubleshooting): [`email-relay.md`](email-relay.md).**

Email is always sent gracefully — an SMTP/relay outage never breaks the app; the
verification step is skipped with a message and can be retried. Email
verification is off by default (`email_verification_required` setting).

## The "Update" button

`POST /api/v1/admin/system/` writes `backups/.update-requested`. A host-side
watcher runs the rollout:

```cron
*/2 * * * * /opt/caspintunel/scripts/watch-update.sh --prod >> /var/log/caspintunel-update.log 2>&1
```

`watch-update.sh` → `update.sh --prod` (prod is also the default without a flag):
DB dump to `backups/pre-update-*.sql.gz` + running images tagged `:rollback` →
`git reset --hard @{upstream}` → build → `up -d` → `migrate` + `seed` →
`collectstatic`. Undo with `./update.sh --rollback` (images; restore the dump for
schema changes). `GET /api/v1/admin/system/`
reports the deployed `VERSION` vs the `VERSION` on the repo's `main` branch.
