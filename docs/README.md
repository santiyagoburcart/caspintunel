# caspintunel — documentation

| Doc | Contents |
|-----|----------|
| [install.md](install.md) | one-command menu installer (install / update / uninstall) |
| [offline.md](offline.md) | air-gapped install — pre-built images, manual TLS |
| [deploy.md](deploy.md) | server layout, TLS (auto + manual), DNS/mail, the update button |
| [architecture.md](architecture.md) | how the system is put together: containers, request flow, Celery schedule, bots, PasarGuard, agency sync, host jobs, backups, deploy, production server |
| [erd.md](erd.md) | data model — Mermaid ER diagrams per app + every table explained |
| [flows.md](flows.md) | sequence diagrams: purchase + card-to-card + SMS auto-confirm, renewal, provisioning, agency sync + ledger, bot / Mini App login, domain change, deploy |
| [roadmap.md](roadmap.md) | planned phases: ticketing, agency, CRM, retention, CRM accounting |
| [api.md](api.md) | API surface overview (full spec at `/api/schema/`, UI at `/api/docs/`) |
| [operations.md](operations.md) | day-2: backups, monitoring, alerts, user delete/restore, SMS devices & apps, common tasks |
| [migration.md](migration.md) · [فارسی](migration-fa.md) | moving to a new server: export / import scripts, pre-DNS test, runbook, rollback, server specs |
| [paths.md](paths.md) | admin-panel and reseller-portal paths: Settings → Paths, host watcher, recovery CLI |
| [domain.md](domain.md) | Settings → Domain & Cloudflare: encrypted token, domain-change wizard, transition, rollback, recovery CLI |
| [access-mode.md](access-mode.md) | Domain & Cloudflare → Access mode: Direct / Cloudflare proxy / Iran tunnel, switch + verify + auto-revert, real IP, DNS-01, Iran-side diagnosis |
| [sms-batch.md](sms-batch.md) | iPhone Shortcut offline SMS queue: save first, upload the queue to `inbound-batch` (idempotent, matched at received_at) |
| [agency.md](agency.md) | agency panel (reseller admins, PAMP port): switches, data import, golden test |
| [bots.md](bots.md) | the Telegram sales bot: menus, support message, purchase history, QR photos |
| [telegram-miniapp.md](telegram-miniapp.md) | Telegram Mini App auto-login |
| [email-relay.md](email-relay.md) | outbound mail through a relay |
| [development.md](development.md) | tests (isolated stack), UI rules, releasing |
| [security-review.md](security-review.md) | security review notes (repo only — not shown in the admin panel) |

These pages are also readable in the admin panel → **Documentation** (`/panel/docs`,
permission `settings.manage`): rendered read-only with a table of contents and search.
Mermaid diagrams (```` ```mermaid ```` blocks in `architecture.md`, `erd.md`, `flows.md`) are drawn in the panel
too — the library is bundled with the admin SPA (lazy chunk, no CDN); a diagram that fails to parse shows its source.
Only `docs/*.md` is served; a `NAME=value` line whose name looks like a secret
(`*PASSWORD*`, `*TOKEN*`, `*SECRET*`, `*_KEY`) is masked unless it is a placeholder.

> The Pasargad / PasarGuard panel is **only consumed over its HTTP API**. None of
> its (AGPL) source is included in this repository.
