# Deploy

## Compose topology

`docker-compose.yml` is dev; `docker-compose.prod.yml` overrides it for production
(gunicorn, static SPA images, `nginx/prod.conf`, no exposed dev ports).

```
nginx ──┬─ /            → frontend_user   (static SPA)
        ├─ /panel/      → frontend_admin  (static SPA)
        ├─ /api/ /admin/ /static/ /media/ → web (Django + gunicorn)
web · celery_worker · celery_beat · bot_sales · bot_backup   (image: caspintunel-backend)
db (MySQL 8) · redis · phpmyadmin
```

## TLS

Nginx listens on 80 and 443. Put a cert + key at `nginx/certs/` (e.g. `certbot
certonly --standalone -d caspin.skin -d www.caspin.skin` then copy `fullchain.pem`
/ `privkey.pem`) and add the `ssl_certificate` lines to `nginx/prod.conf`, or
terminate TLS at Cloudflare (proxied A records) and keep origin on 80.

## Changing the domain — no rebuild

The site domain lives in `site_config.site_domain` (panel → Branding). A change
there is picked up within 60 s by `DynamicAllowedHostsMiddleware`, which adds the
new host + `www.` to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` at runtime. The
env `ALLOWED_HOSTS` stays as the always-valid baseline. Update the Cloudflare
records with `manage.py configure_dns --apply --domain newdomain`.

## DNS + mail (Cloudflare)

```bash
docker compose exec web python manage.py configure_dns            # dry-run
docker compose exec web python manage.py configure_dns --apply
```

Records managed (existing VPN-node records are never touched):

| Type | Name | Value | Proxy |
|---|---|---|---|
| A | `caspin.skin`, `www` | server IP | proxied |
| A | `mail` | server IP | **DNS-only** (SMTP needs the real IP) |
| MX | `caspin.skin` | `mail.caspin.skin` (10) | — |
| TXT | `caspin.skin` | `v=spf1 mx a:mail.caspin.skin ~all` | — |
| TXT | `_dmarc` | `v=DMARC1; p=quarantine; …` | — |
| TXT | `default._domainkey` | generated DKIM public key | — |

The DKIM **private** key is written to `backend/mail-keys/default.private`
(git-ignored, `chmod 600`). Point your mail server (OpenDKIM / docker-mailserver)
at it with selector `default`. The self-hosted mail server itself (Postfix/Dovecot)
is out of scope of this repo — wire `EMAIL_HOST=mail.caspin.skin` in `.env` once
it is up; email is always sent gracefully (an outage never breaks the app).

## The "Update" button

`POST /api/v1/admin/system/` writes `backups/.update-requested`. A host-side
watcher runs the rollout:

```cron
*/2 * * * * /opt/caspintunel/scripts/watch-update.sh --prod >> /var/log/caspintunel-update.log 2>&1
```

`watch-update.sh` → `update.sh --prod`: `git reset --hard @{upstream}` → build →
`up -d` → `migrate` + `seed` → `collectstatic`. `GET /api/v1/admin/system/`
reports the deployed `VERSION` vs the `VERSION` on the repo's `main` branch.
