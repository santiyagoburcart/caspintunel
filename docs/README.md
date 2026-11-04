# caspintunel — documentation

| Doc | Contents |
|-----|----------|
| [install.md](install.md) | one-command menu installer (install / update / uninstall) |
| [offline.md](offline.md) | air-gapped install — pre-built images, manual TLS |
| [deploy.md](deploy.md) | server layout, TLS (auto + manual), DNS/mail, the update button |
| [architecture.md](architecture.md) | how the system is put together: production server + capacity, containers, request flow, apps, **permissions**, Celery schedule, bots, PasarGuard, agency, tickets, CRM / retention / analytics / discounts, notifications + push, transactions, manual invoices, host jobs, backups, deploy |
| [erd.md](erd.md) | data model — Mermaid ER diagrams per app + every table explained |
| [flows.md](flows.md) | sequence diagrams: 2.x payments (card-to-card, SMS, Blu, rounded, alerts, manual invoices, void, discounts, cards), renewal, provisioning, 5.x agency (sync, CRUD, group managers, approvals, invoices, payments, access), sign-in + account linking + purge, tickets, CRM, retention, analytics, domain / access mode, deploy, disk |
| [roadmap.md](roadmap.md) | phases built since v1.15, releases since v1.22, and what is planned next (multi-tenant reseller storefronts) |
| [multi-tenant.md](multi-tenant.md) | **proposal (not built)**: multi-tenant reseller storefronts — architecture, tenant scoping, ERD, flows, domains / TLS, bots, payments, capacity, phases, risks |
| [api.md](api.md) | API surface overview (full spec at `/api/schema/`, UI at `/api/docs/`) |
| [operations.md](operations.md) | day-2: backups, monitoring, alerts, user delete/restore, SMS devices & apps, common tasks |
| [migration.md](migration.md) · [فارسی](migration-fa.md) | moving to a new server: export / import scripts, pre-DNS test, runbook, rollback, server specs |
| [paths.md](paths.md) | admin-panel and reseller-portal paths: Settings → Paths, host watcher, recovery CLI |
| [domain.md](domain.md) | Settings → Domain & Cloudflare: encrypted token, domain-change wizard, transition, rollback, recovery CLI |
| [access-mode.md](access-mode.md) | Domain & Cloudflare → Access mode: Direct / Cloudflare proxy / Iran tunnel, switch + verify + auto-revert, real IP, DNS-01, Iran-side diagnosis |
| [sms-batch.md](sms-batch.md) | iPhone Shortcut offline SMS queue: save first, upload the queue to `inbound-batch` (idempotent, matched at received_at) |
| [agency.md](agency.md) | agency panel (reseller admins, PAMP port): switches, import, golden test, portal, ledger, limit history, groups, group managers, approvals, invoices / payments, access rules |
| [blu-webhook.md](blu-webhook.md) | Blu Bank deposits: signed collector webhook, matching (customer orders, then agency payments), SSH health check, liveness |
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
