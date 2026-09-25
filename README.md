# caspintunel

VPN sales system — user site + admin panel + two Telegram bots + an Android SMS
app, on top of a Pasargad / **PasarGuard** panel (consumed over its HTTP API only).

**Stack:** Django + DRF + Celery + Redis + MySQL + Nginx + Docker · API-first
(`/api/v1/`, JWT) · React + Vite + Tailwind SPAs · Jalali calendar · bilingual fa/en.

## Install

```bash
./install.sh            # menu: 1) Install  2) Update  3) Uninstall  4) Exit
./install.sh --offline  # air-gapped server (pre-built images, manual cert)
```

See **[docs/](docs/)** — [install](docs/install.md) · [offline](docs/offline.md) ·
[deploy](docs/deploy.md) · [architecture](docs/architecture.md) · [api](docs/api.md) ·
[operations](docs/operations.md).

## Features

- Register / login (JWT), outage-aware email verification, 3-path password reset, legacy-user import
- Plans (fixed & custom-volume), per-plan panel groups, discounts, enable/disable
- Orders with **atomic unique-amount reservation**; **card-to-card** (receipt + admin approval) and **SMS auto-confirm**
- Panel provisioning — On-Hold for timed plans, renewal keeps the same subscription link, retry-safe
- Telegram sales bot (buy/renew/custom/status/QR, forced channels + phone, first-time → random site account) · separate backup bot
- Admin panel — users (soft delete + deleted-users archive / restore), services (full edit incl. HWID limit, manual create, link an existing panel account), plans, **live payments queue** (WebSocket), **Jalali accounting**, per-card deposit report, broadcast, dynamic branding, roles/RBAC, CMS pages, themes, **Apps & tools** (Android SMS app + iPhone shortcut downloaded from the server)
- Fully responsive admin on phones — bottom nav with the payment queue in the centre, every desktop page reachable from the Settings index
- Offline-safe frontends — all fonts (Vazirmatn / Inter) and assets bundled, no CDN
- Monitoring — 9 health targets, CPU/RAM/disk, automatic backups, service usage/expiry alerts
- Menu-driven `install.sh` (install / update / uninstall) + in-panel **Update** button + `VERSION`; **offline / air-gapped** install path; domain changeable with no rebuild
- Cloudflare DNS automation (A/MX/SPF/DKIM/DMARC); self-hosted mail (Postfix + Dovecot + DKIM); Let's Encrypt **or** manual-upload TLS

## Security

Secrets only in `.env` (git-ignored). Panel password, bot tokens and the cached
panel API token are **encrypted at rest** (`FIELD_ENCRYPTION_KEY`). Rate-limited
auth endpoints, audit log, HTTPS, per-audience tokens (customer / staff / SMS device).

## Licence

Proprietary — All Rights Reserved. See [LICENSE](LICENSE).
