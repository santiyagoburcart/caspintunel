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

Production runs on a server in Finland. Update a running server with `./update.sh` (backup → build → migrate → rolling swap;
`./update.sh --rollback` to undo). Tests: `./scripts/test.sh` (isolated stack only).

See **[docs/](docs/)** — [install](docs/install.md) · [offline](docs/offline.md) ·
[deploy](docs/deploy.md) · [architecture](docs/architecture.md) · [data model](docs/erd.md) · [flows](docs/flows.md) · [roadmap](docs/roadmap.md) · [api](docs/api.md) ·
[operations](docs/operations.md) · [server migration](docs/migration.md) · [paths](docs/paths.md) · [domain](docs/domain.md) · [agency](docs/agency.md) · [bots](docs/bots.md) · [development](docs/development.md).
The same pages are readable in the admin panel → **Documentation**.

All roadmap phases are built — see [docs/roadmap.md](docs/roadmap.md).

## Features

- Register / login (JWT), outage-aware email verification, 3-path password reset, legacy-user import
- Plans (fixed & custom-volume), per-plan panel groups, discounts, enable/disable
- Orders with **atomic unique-amount reservation**; **card-to-card** (receipt + admin approval) and **SMS auto-confirm** — exact amount only; near misses (±20 % or a ×10/÷10 unit slip) go to the payments queue for manual review
- Panel provisioning — On-Hold for timed plans, renewal keeps the same subscription link, retry-safe
- Telegram sales bot with site parity (buy/renew/custom volume/receipt/status, services, purchase history with the real paid amount, account, rules, guide, configurable support message, forced channels + phone, first-time → random site account) · Telegram **Mini App auto-login** · separate backup bot
- Subscription QR codes on a branded background (6 built-in designs or a custom upload; the code itself untouched and decode-tested)
- Rejected orders kept visible with the reason; late approvals still fulfil; admin **SMS log** with the match/no-match reason
- Admin panel — users (soft delete + deleted-users archive / restore), services (full edit incl. HWID limit, manual create, link an existing panel account), plans, **live payments queue** (WebSocket), **Jalali accounting**, per-card deposit report, broadcast, dynamic branding, roles/RBAC, CMS pages, themes, **Apps & tools** (Android SMS app + iPhone shortcut downloaded from the server)
- **Agency panel** — PasarGuard reseller admins (1:1 port of PAMP v1.5.3) + **create / edit / delete admins on the panel** (every API field, roles, price + quota charge, send-to-reseller card), tabbed admin pages: limits in GB, usage / sold / hidden / deleted-users traffic, enforcement, account groups, sync logs; **reseller portal** (`/agency/`, panel login); **accounting** (price per GB, automatic quota charges, payments, statements, period / monthly reports, CSV + Excel)
- **CRM** — customer 360 (profile, services, LTV, tickets, notes, tags, owner, activity timeline), automatic lifecycle stages (lead → churned / won back), **inactivity detection** from PasarGuard connection data with a follow-up queue (reasons, outcomes, template messages, tickets on the customer's behalf, optional automatic message), leads, reports
- **Retention** — configurable pre-expiry warnings (data % / days left, quiet hours, one-click renew on site / bot / email), win-back queue (discount codes at checkout, automatic won-back with recovered revenue), retention reports
- **Business analytics** — overview dashboard with trends, customer finance (LTV, AOV, ARPU, new vs returning, by plan / channel / card, discount cost, CSV / Excel), retention (churn, renewal, cohorts, lifetime, top LTV), support performance per staff and topic
- Configurable admin-panel and portal **paths** (Settings → Paths)
- **Domain & Cloudflare** (Settings, super admin): encrypted Cloudflare token, a step-by-step domain-change wizard with automatic rollback, a 301 transition for the old domain and `./scripts/domain.sh` recovery
- **Ticketing** — Telegram-like chat on the site and in the sales bot (synced), staff inbox (split view, internal notes, saved replies, timeline, customer panel, live badge), staff ticket handling from Telegram; topics (pre-purchase open to everyone, the rest to anyone who ever bought), attachments, internal notes, assignment, priorities, full history, auto-close / reopen, **Ticketing role + per-staff topic scopes**, notifications to customers (site / bot / email) and staff (live badge, Telegram DM after linking, email)
- Fully responsive admin on phones — bottom nav with the payment queue in the centre, compact record cards, every desktop page reachable from the Settings index
- In-panel **Documentation** page (this repo's `docs/`, rendered read-only with contents + search, Mermaid diagrams drawn with a bundled library)
- Offline-safe frontends — all fonts (Vazirmatn / Inter) and assets bundled, no CDN
- Monitoring — 9 health targets, CPU/RAM/disk, automatic backups to Telegram with **local retention** (deleted only after Telegram confirmed), service usage/expiry alerts
- Menu-driven `install.sh` (install / update / uninstall) + in-panel **Update** button + `VERSION`; **offline / air-gapped** install path; domain changeable with no rebuild
- Cloudflare DNS automation (A/MX/SPF/DKIM/DMARC); self-hosted mail (Postfix + Dovecot + DKIM); Let's Encrypt **or** manual-upload TLS

## Security

Secrets only in `.env` (git-ignored). Panel password, bot tokens and the cached
panel API token are **encrypted at rest** (`FIELD_ENCRYPTION_KEY`). Rate-limited
auth endpoints, audit log, HTTPS, per-audience tokens (customer / staff / SMS device).

## Licence

Proprietary — All Rights Reserved. See [LICENSE](LICENSE).
