# caspintunel

VPN sales system — user site + admin panel + two Telegram bots + an Android SMS
app, on top of a Pasargad / **PasarGuard** panel (consumed over its HTTP API only).

**Stack:** Django + DRF + Celery + Redis + MySQL + Nginx + Docker · API-first
(`/api/v1/`, JWT) · React + Vite + Tailwind SPAs · Jalali calendar · bilingual fa/en.

## Install

```bash
./install.sh --prod
```

See **[docs/](docs/)** — [install](docs/install.md) · [deploy](docs/deploy.md) ·
[architecture](docs/architecture.md) · [api](docs/api.md) · [operations](docs/operations.md).

## Features

- Register / login (JWT), outage-aware email verification, 3-path password reset, legacy-user import
- Plans (fixed & custom-volume), per-plan panel groups, discounts, enable/disable
- Orders with **atomic unique-amount reservation**; **card-to-card** (receipt + admin approval) and **SMS auto-confirm**
- Panel provisioning — On-Hold for timed plans, renewal keeps the same subscription link, retry-safe
- Telegram sales bot (buy/renew/custom/status/QR, forced channels + phone, first-time → random site account) · separate backup bot
- Admin panel — users, plans, payments queue, **Jalali accounting**, per-card deposit report, broadcast, dynamic branding, roles/RBAC, CMS pages, themes
- Monitoring — 9 health targets, CPU/RAM/disk, automatic backups, service usage/expiry alerts
- One-click `install.sh` / `update.sh` + in-panel **Update** button + `VERSION`; domain changeable with no rebuild
- Cloudflare DNS automation (A/MX/SPF/DKIM/DMARC, mail record DNS-only)

## Security

Secrets only in `.env` (git-ignored). Panel password, bot tokens and the cached
panel API token are **encrypted at rest** (`FIELD_ENCRYPTION_KEY`). Rate-limited
auth endpoints, audit log, HTTPS, per-audience tokens (customer / staff / SMS device).

## Licence

Proprietary — All Rights Reserved. See [LICENSE](LICENSE).
