# Multi-tenant reseller storefronts — design

> **Status: design approved 2026-11-04 (decisions D1–D7 below). Phase 0 shipped in v1.39.0. Phase 1 Release A shipped in
> v1.40.0** (tenant tables, nullable `tenant_id`, default tenant + backfill), **Release B in v1.41.0** (host → tenant
> middleware, scoped managers, JWT `tid`, per-tenant unique constraints, isolation sweep) **and Release C in v1.42.0**
> (`tenant_id` NOT NULL on the 34 tenant tables, old global uniques dropped, strict mode in the web process) — **Phase 1 done.**
> **Phase 2 Release A in v1.43.0** (our «فروشگاه» tab, `tenant_branding`, `tenant_setting` + `TENANT_KEYS`, themes / pages per
> store, server-side store mode) **and Release B in v1.44.0** (admin panel store mode: store menu + badge, store dashboard /
> branding / settings / pages / themes, no platform polling; user site without our brand fallbacks, letter favicon) —
> **Phase 2 done.** **Phase 3 (domains & TLS) built in v1.45.0** (store domains on «فروشگاه», DNS / TXT / proxied checks, HTTP-01 per
> host via the host watcher `scripts/tenants.sh`, per-host nginx files, health, renewal, alerts — architecture.md + flows.md 16c).
> The Iran-side PROXY-protocol sender (§7 "Real client IP") was skipped by the owner on 2026-11-08: tunnel visitors keep the
> per-browser limits. **Phase 4 (catalog + PasarGuard) built in v1.46.0** (Celery tasks carry the store, set_owner
> provisioning, quota guard + 20 / 10 % warnings, store plans bounded by the reseller's admin — architecture.md + flows.md 16d).
> **Phase 5 (payments + SMS) built in v1.47.0** (pools per store, SMS on the store's domain, store payments panel, alerts /
> push / live socket per store — flows.md 16e). The Android APK is unchanged (server URL = store domain); a QR / store-name
> screen needs a new APK build. Next: Phase 6 (bots + Mini App). Written against v1.38.4, decisions recorded in v1.38.6.
> When a phase is approved and built, the matching parts move into `architecture.md` / `erd.md` / `flows.md` and this page
> keeps only what is still planned.

Every agency admin (reseller) can get a white-label store — site, Telegram Mini App and their own Telegram bot — on their own
domain, served by the same codebase and database. Our current store becomes the **default tenant** and keeps working
unchanged. The reseller sells their own plans at their own prices, customers pay to the reseller's bank cards, services are
created under the reseller's PasarGuard admin (so they use the reseller's quota, which we keep invoicing per GB), and the
reseller runs the store — catalog, customers, orders, payment queue, tickets, CRM, discounts, branding, staff — from
the store admin on their own domain (the existing panel pages in store mode). **Only we enable a store and set its domains and
bot token** (Agency → admin → «فروشگاه»); the reseller manages branding, plans, cards, customers, orders, tickets, discounts,
staff and SMS devices.

Contents: [1 Decisions](#1-decisions-and-what-needs-your-answer) · [2 Architecture](#2-architecture) ·
[3 Tenant scoping](#3-tenant-scoping-the-isolation-guarantee) · [4 Data model](#4-data-model-erd-changes) ·
[5 Changes per app](#5-changes-per-existing-app) · [6 Flows](#6-flows) · [7 Domains and TLS](#7-domains-tls-and-routing) ·
[8 Bots](#8-telegram-bots-and-the-mini-app) · [9 Payments and SMS](#9-payments-unique-amounts-and-the-sms-app) ·
[10 PasarGuard and quota](#10-pasarguard-ownership-and-quota) · [11 Reseller staff](#11-reseller-staff-and-permissions) ·
[12 Email](#12-email-per-tenant) · [13 Rate limits](#13-rate-limits) · [14 Backups and export](#14-backups-and-tenant-export) ·
[15 Import](#15-import-from-other-systems-last-phase) · [16 Security](#16-security) · [17 Filtering risk](#17-filtering-and-abuse-risk-of-reseller-domains) ·
[18 Migration](#18-moving-todays-data-into-the-default-tenant) · [19 Capacity](#19-server-capacity) ·
[20 Phases](#20-phased-plan-and-size) · [21 Risks](#21-risks)

---

## 1. Decisions

Brief: one codebase, one MySQL database, tenant chosen by the `Host` header; full feature parity per tenant; reseller-set plans
and prices; services under the reseller's PasarGuard admin with a quota guard; payments to the reseller's cards, reviewed by the
reseller, auto-confirmed by our Android SMS app; reseller sub-staff with a grant ceiling we control; tenant bots by webhook;
per-tenant export (switchable); importers last; a monthly-fee hook (off).

**Answered by the owner (2026-11-04):**

| # | Question | Decision |
|---|---|---|
| D1 | Store admin UI | **Reuse the existing panel pages in store mode** (the admin SPA with a store menu and tenant-scoped API) — not new pages inside `/agency/`. |
| D2 | Where the store admin lives | **On the reseller's own domain**, at the admin path (`https://store.example/panel/`). `/agency/` keeps the reseller portal and links to it. |
| D3 | Default tenant | **`caspintunel.com`** (the live domain today; `aicaspin.ir` is the old domain and is not a tenant). The default tenant is a row, not a hard-coded host. |
| D4 | Customers | **Separate customer accounts per store** (same DB, tenant-scoped); the same phone / Telegram may exist in several stores. |
| D5 | Who opens a store | **Only stores we enable, and only we set them up**: internal panel → Agency → create / edit admin → «فروشگاه»: enable store, domain(s), bot token. Resellers cannot add domains or bots; they see the status read-only and manage branding, plans, cards, customers, tickets, discounts, staff, SMS devices in their store admin. |
| D6 | Quota | **The existing agency quota numbers** (synced remaining / limit, same as enforcement): block a sale when the remaining quota is short, warn at **20 % and 10 % remaining** (= 80 % and 90 % used; 80 % is the portal's existing warning level). |
| D7 | DNS and access | The reseller keeps DNS on **their own Cloudflare account**. We tell them which A record to create: **our Finland IP (direct)** or **our Iran IP (Iran tunnel, same 80/443 passthrough as caspintunel.com)**. DNS-only and proxied (their Cloudflare) must both work; the real client IP comes from Cloudflare's ranges / the tunnel sources exactly as today. Per store we store the mode, show the exact A record to give them, verify DNS, issue TLS automatically (HTTP-01, through the tunnel and through their Cloudflare) and health-check. |
| — | Capacity | **Stay on the current server (2 vCPU / 3.7 GiB); the owner increases swap.** §19 sizes the platform for that. |
| — | Importers | Later — the owner sends the bot names and samples then. |

## 2. Architecture

```mermaid
flowchart LR
    subgraph clients[Customers and resellers]
        b1([store-a.example browser / Mini App])
        b2([store-b.example browser / Mini App])
        b0([caspintunel.com default store])
        tg([Telegram])
        sms([Reseller's Android SMS app])
    end
    b1 & b2 & b0 -->|443, SNI = tenant domain| nginx
    tg -->|POST /tg/hook/TENANT_ID/ + secret header| nginx
    sms -->|X-Device-Token| nginx
    subgraph host[This server]
        nginx[nginx<br/>one server block + cert per tenant domain]
        web[web<br/>TenantMiddleware → contextvar]
        worker[celery_worker<br/>tasks carry tenant_id]
        beat[celery_beat]
        db[(MySQL<br/>tenant_id on every tenant table)]
        redis[(redis<br/>keys prefixed t:ID:)]
    end
    nginx --> web
    web --> db & redis
    worker --> db & redis
    worker -->|create user, then set_owner to the reseller admin| pg[(PasarGuard 5.6)]
    worker -->|Bot API with the tenant's token| tg
```

- **Tenant** = one store. `tenant_id` is resolved once per request from the `Host` header against *verified* `TenantDomain`
  rows (exact match, `www.` redirects like today). Unknown host → 404 (never the default store — a stranger's domain pointed at
  our IP must not show our shop).
- **Same SPAs, branded at runtime**: the user SPA already reads `/api/v1/config/` and `/api/v1/theme/`; these answer per
  tenant. The admin SPA runs in "store mode" for reseller staff (D1).
- **One web pool, one worker pool.** No process per tenant. Bots by webhook (§8). Celery tasks take `tenant_id` and set the
  tenant context before touching models.
- **Platform vs tenant data.** Platform tables (panels, agency ledger / invoices / payments, Blu, ops, backups, health, our
  staff) stay global. Customer-facing tables get `tenant_id` (§4).

## 3. Tenant scoping (the isolation guarantee)

MySQL has no row-level security, so isolation is enforced in four layers, each tested:

1. **Model field.** Every tenant table has `tenant = ForeignKey(Tenant, on_delete=PROTECT, db_index=True)` — denormalized on
   child tables too (payment, ticket message, service…), so every list query filters one indexed column and a child can be
   checked against its parent (`save()` refuses `child.tenant != parent.tenant`).
2. **Context + middleware.** `TenantMiddleware` sets a `contextvars` value (`current_tenant`) from the host; the SMS API sets it
   from the device token; the bot webhook from the URL + secret; Celery tasks from their `tenant_id` argument; management
   commands must pass `--tenant` or `--all-tenants`. No context → tenant-scoped queries **raise** (fail closed).
3. **Default manager.** `TenantManager` filters `tenant=current_tenant()` on every queryset of a tenant model; `Model.unscoped`
   is the only way around it and is allowed only in platform code paths (our staff with the tenant filter, ops, migrations),
   listed in one allow-list file. `create()` fills `tenant` from the context.
4. **Tokens and sessions.** Customer JWTs and store-staff JWTs carry `tid`; a token used on another tenant's host → 401. Cache
   keys, rate-limit buckets, WebSocket groups and media paths are prefixed `t:<id>:` / `tenants/<id>/`.

**Tests that guarantee it** (run on every release):

- *Inventory test*: every model holding customer data has a `tenant` field and `TenantManager` (fails when someone adds a model
  without it, or a new model is not classified in `tenancy/registry.py`).
- *Cross-tenant API sweep*: two tenants with the same fixtures (same usernames, phones, amounts); for **every** URL pattern
  (generated from the resolver, like `test_mobile_nav`), as tenant A's customer and staff: list / detail / write on B's ids →
  404, lists never contain B's rows, counts and totals equal A's only.
- *Unscoped-access lint*: `.unscoped` / `all_tenants()` used outside the allow-list → test failure.
- *Context tests*: a Celery task without `tenant_id`, an SMS from a device of tenant A matching a B order, a bot update with a
  wrong secret, a JWT replayed on another host — each refused.
- *Unique-amount test*: the same amount open in A and B; an SMS on A's device approves only A's order.

## 4. Data model (ERD changes)

```mermaid
erDiagram
    tenant ||--o{ tenant_domain : has
    tenant ||--o| tenant_bot : has
    tenant ||--o| tenant_branding : has
    tenant ||--o{ tenant_setting : overrides
    tenant ||--o{ tenant_permission_ceiling : allows
    tenant ||--o{ tenant_export : exports
    tenant ||--o{ import_job : imports
    tenant ||--o| tenant_billing : fee
    agency_panel_admin ||--o| tenant : "reseller (owner)"
    tenant ||--o{ user : customers
    tenant ||--o{ staff : "store staff"
    tenant ||--o{ plan : sells
    tenant ||--o{ bank_card : receives
    tenant ||--o{ sms_app_device : confirms

    tenant {
        bigint id PK
        string slug UK
        string name
        string reseller_username FK "agency_panel_admin, null = default tenant"
        string status "draft | active | suspended | closed"
        bool is_default "exactly one"
        bool export_allowed "set by us"
        int quota_warn_percent "default 20"
        json limits "orders/min, staff count, bots"
        datetime created_at
    }
    tenant_domain {
        bigint id PK
        bigint tenant_id FK
        string host UK "store.example (lowercase, IDNA)"
        string role "site | admin | both"
        string mode "direct | tunnel | cloudflare"
        string verify_token "TXT _caspin-verify.HOST"
        string state "pending_dns | verified | cert_pending | active | failed | removed"
        datetime cert_expires_at
        datetime last_check_at
        string last_error
    }
    tenant_bot {
        bigint id PK
        bigint tenant_id FK
        string username
        text token_enc "encrypted"
        string webhook_secret_enc "encrypted, X-Telegram-Bot-Api-Secret-Token"
        string state "unset | ok | error"
        datetime last_update_at
    }
    tenant_branding {
        bigint tenant_id PK
        string title_fa
        string title_en
        string logo
        string favicon
        json palette "theme colours, light / dark"
        json support "telegram, phone, url"
        json bot_texts "overrides of bot/texts.py keys"
    }
    tenant_setting {
        bigint id PK
        bigint tenant_id FK
        string key "only keys in TENANT_KEYS"
        text value
    }
    tenant_permission_ceiling {
        bigint id PK
        bigint tenant_id FK
        string permission_code "what the reseller may grant"
    }
    tenant_export {
        bigint id PK
        bigint tenant_id FK
        string requested_by
        string state "queued | running | ready | expired | failed"
        string file "private media, tenants/ID/exports/"
        datetime expires_at
    }
    import_job {
        bigint id PK
        bigint tenant_id FK
        string importer "csv | mirza | wizwiz | marzban_bot | pasarguard_users ..."
        string state "uploaded | previewed | running | done | failed"
        json mapping
        json report "counts, conflicts, skipped rows"
    }
    tenant_billing {
        bigint tenant_id PK
        bool fee_enabled "off for now"
        decimal monthly_fee
        date next_due
    }
```

**`tenant_id` added to** (NOT NULL after the backfill, §18):

| App | Tables |
|---|---|
| accounts | `user`, `deleted_user_archive`, `staff` (**nullable** = platform staff), `role` (nullable = platform role) |
| panel / plans | `service` (denormalized from user), `plan` |
| orders | `order`, `scheduled_renewal`, `manual_invoice` |
| payments_sms | `payment`, `bank_card`, `sms_source`, `sms_app_device`, `sms_message` |
| notifications | `notification`, `notification_delivery`, `push_subscription` (nullable — staff / reseller rows) |
| telegram | `required_channel` (per tenant bot), `telegram_stats` |
| settings_app | `site_config` → replaced by `tenant_branding`, `theme`, `page` |
| tickets | `ticket_topic`, `ticket`, `ticket_message`, `ticket_attachment`, `ticket_event`, `ticket_canned_reply` |
| crm | all 11 tables (`crm_tag` … `crm_discount_code`) |
| common | `audit_log` (nullable — platform actions) |

**Stays global:** `panel`, every `agency_*` table, `blu_transaction`, `blu_collector`, `setting` (platform keys), `email_settings`
(platform relay), `domain_config`, `domain_change`, `app_release`, `telegram_config` (our two bots), all `ops` tables, `permission`.

**Unique constraints that become per-tenant** (composite with `tenant_id`): `user.username`, `user.telegram_id`,
`user.referral_code`, `crm_discount_code.code`, `crm_tag.name`, `crm_warning_rule (kind, threshold)`, `page.slug`, `theme.name`.
`order.amount_unique_lock` becomes `(tenant_pool, amount_unique_lock)` (§9). `payment.number` (TX) and `ticket.number` stay global
sequences (simple, never collide) but are shown per tenant.

## 5. Changes per existing app

| App | Change |
|---|---|
| `common` | `tenancy/` package: `Tenant*` models, `current_tenant` contextvar, `TenantMiddleware`, `TenantManager`, registry + allow-list, cache-key helper, `tenant_task` Celery decorator. `DynamicAllowedHostsMiddleware` reads verified tenant domains. Audit rows get `tenant`. |
| `accounts` | Customer auth per tenant (login / register / reset / Mini App all resolve the tenant first); phone normalization unchanged, uniqueness per tenant; JWT `tid` claim; `Staff.tenant` + store roles; grant ceiling (§11). Reseller owner = a `Staff` row of their tenant linked to the `PanelAdmin` (like group managers today). |
| `plans` | Plans per tenant; reseller sets prices; panel groups limited to what the reseller's PasarGuard role allows. |
| `panel` | Provisioning uses our admin token, then `PUT /api/user/{username}/set_owner?admin_username=<reseller>` (verified in PasarGuard 5.6.0 openapi); account-name check per panel stays global (one PasarGuard namespace). Quota guard before every sale / renewal / add-on (§10). Sync unchanged (global). |
| `orders` | Orders per tenant; `create_order` checks quota + tenant status; unique amounts from the tenant's pool; renewals / scheduled renewals unchanged otherwise. |
| `payments_sms` | Cards, sources, devices, SMS log per tenant; matching only inside the device's tenant; `approve_payment` unchanged (it is the only approve path); Blu stays default-tenant only + agency payments. Receipts under `tenants/<id>/receipts/`. |
| `notifications` | `notify_user` sends through the tenant's bot and tenant-branded email; site notifications per tenant; Web Push works per origin automatically (each domain has its own service worker scope) — one VAPID key pair for all. |
| `telegram` | Webhook endpoint for tenant bots (§8); our two bots unchanged (polling); screens / texts take the tenant's branding and overrides; forced channels per tenant. |
| `settings_app` | `tenant_branding` replaces `site_config` for tenants (the default tenant's row is migrated from `site_config`); `TENANT_KEYS` = settings a tenant may override (checkout timer, ticket limits, retention quiet hours, alerts…); platform-only keys stay global; themes / pages per tenant. |
| `tickets` | Topics, tickets, canned replies, scopes per tenant; attachments under `tenants/<id>/tickets/`. |
| `crm` | Everything per tenant (profiles, cases, templates, retention rules, discount codes, analytics). Analytics already read-only — they gain the tenant filter. |
| `agency` | New «فروشگاه» section on the staff create / edit admin page (**our staff only**): enable store, domains + mode, bot token, export permission, limits, status, health. `/agency/` shows the reseller the store status (read-only) and links to their store admin. Store sales feed the reseller's usage; our per-GB invoicing is unchanged. |
| `adminpanel` | Every view runs under the tenant context; our staff get a **tenant filter** (default: all) and a tenant column; store staff are confined to theirs. `StaffPermission` checks the ceiling for store roles. |
| `ops` | Health per tenant domain (cert days left, DNS still pointing to us, bot webhook state); alerts to us and to the reseller. Backups stay global. |
| frontends | User SPA: no code per tenant — branding from the API, `manifest` / favicon per host. Admin SPA: store mode (menu filtered by the store role, tenant filter for us). Portal `/agency/`: «فروشگاه من» entry. |

## 6. Flows

### 6.1 A request to a tenant store

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant N as nginx
    participant M as TenantMiddleware
    participant V as API view
    participant DB as MySQL
    C->>N: GET https://store-a.example/api/v1/plans/ (SNI store-a.example)
    N->>N: server block of store-a.example (its own certificate)
    N->>M: Host store-a.example
    M->>DB: TenantDomain(host, state=active) → tenant A (cached 60 s)
    alt unknown or not active
        M-->>C: 404 (never the default store)
    else tenant A
        M->>M: current_tenant = A
        V->>DB: Plan.objects.all() → WHERE tenant_id = A
        V-->>C: A's plans, A's branding
    end
```

### 6.2 Domain onboarding (our staff only)

```mermaid
sequenceDiagram
    autonumber
    actor R as Our staff
    participant P as Agency → admin → «فروشگاه»
    participant W as Celery
    participant H as Host watcher (domain.sh-style)
    participant LE as Let's Encrypt
    R->>P: add store-a.example, mode direct (Finland IP) or tunnel (Iran IP)
    P-->>R: the exact records to send the reseller: A store-a.example → IP (DNS-only or proxied) + TXT _caspin-verify.store-a.example = TOKEN
    loop every 5 min until verified (or "check now")
        W->>W: resolve A and TXT through public resolvers
    end
    W->>H: request: issue a certificate for store-a.example
    H->>LE: HTTP-01 via /.well-known/acme-challenge/ (webroot on 80 and 443, works through the tunnel and their Cloudflare)
    LE-->>H: certificate
    H->>H: render nginx/tenants/store-a.example.conf, nginx -t, reload (rollback on failure)
    H-->>W: result
    W->>W: health check over TLS (status 200, right tenant)
    W-->>P: state = active (shown to us, read-only to the reseller)
    Note over W,H: renewal: certbot renew for every tenant cert, 30 days before expiry, alert at 14 days
```

### 6.3 Purchase in a tenant store

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer of tenant A
    participant API as web (tenant A)
    participant Q as Quota guard
    participant PG as PasarGuard
    participant SMS as A's SMS device
    actor R as Reseller A
    C->>API: POST /orders/ (A's plan)
    API->>Q: reseller remaining quota ≥ plan volume?
    alt not enough
        Q-->>C: "temporarily unavailable" (no order)
        Q->>R: alert (panel + bot + push) and to us
    else enough
        API->>API: unique amount from A's pool, A's bank card
        API-->>C: invoice (card, exact amount, timer)
        alt SMS from A's device matches exactly
            SMS->>API: inbound (device token → tenant A)
            API->>API: approve_payment (auto)
        else receipt
            C->>API: receipt upload
            R->>API: approve in A's payments queue
        end
        API->>PG: create user with our admin token
        API->>PG: PUT /api/user/NAME/set_owner?admin_username=reseller-A
        PG-->>API: owned by A — usage counts against A's quota
        API-->>C: service + subscription (A's bot / site)
    end
```

### 6.4 Tenant bot update (webhook)

```mermaid
sequenceDiagram
    autonumber
    participant T as Telegram
    participant N as nginx
    participant H as TenantBotHook
    participant S as bot screens
    T->>N: POST /tg/hook/TENANT_ID/ header X-Telegram-Bot-Api-Secret-Token
    N->>H: forward (rate-limited per tenant)
    H->>H: constant-time compare with tenant_bot.webhook_secret
    alt wrong secret / suspended tenant
        H-->>T: 403 (nothing processed)
    else ok
        H->>H: current_tenant = TENANT_ID, dedupe update_id (Redis, 24 h)
        H->>S: same screens / router as the sales bot, tenant texts and bot token
        H-->>T: 200 quickly (heavy work queued to Celery)
    end
```

### 6.5 Reseller grants a permission to their staff

```mermaid
sequenceDiagram
    autonumber
    actor O as Our staff
    actor R as Reseller (store owner)
    participant API as Store admin API
    O->>API: set tenant A ceiling (e.g. tickets.*, payment.view, payment.approve)
    R->>API: create role «پشتیبانی» with tickets.view, tickets.reply
    API->>API: every code ⊆ ceiling(A) AND ⊆ reseller's own codes?
    alt outside the ceiling
        API-->>R: 403 with the codes refused
    else inside
        API-->>R: role saved (tenant A only)
    end
    O->>API: lower the ceiling later
    API->>API: codes above the new ceiling are removed from A's roles at once (audit)
```

### 6.6 Tenant export and import (preview first)

```mermaid
sequenceDiagram
    autonumber
    actor R as Reseller
    participant API as Store admin
    participant W as Celery
    R->>API: «پشتیبان‌گیری» (only if export_allowed)
    API->>W: tenant_export(tenant A)
    W->>W: customers, services, orders, payments, tickets, settings → JSON + CSV, zip, encrypted with a one-time password
    W-->>R: download link (private, 24 h, shown once) + password
    R->>API: upload an import file (source format chosen)
    API->>W: importer.preview(file) → mapping report, conflicts, nothing written
    W-->>R: report (new / matched / skipped rows, PasarGuard users found or missing)
    R->>API: confirm
    W->>W: importer.run in batches, idempotent (source ids kept), audit per batch
```

## 7. Domains, TLS and routing

- **Who**: only our staff add / remove a store domain (Agency → admin → «فروشگاه»); the reseller sees the state.
- **What we give the reseller** (shown on the page, copyable): one A record `store.example → <IP>` where IP = our **Finland IP**
  (mode *direct*) or our **Iran IP** (mode *tunnel*, the same 80/443 TCP passthrough that serves caspintunel.com), the optional
  `www` record, and a TXT `_caspin-verify.store.example = <token>`. The reseller's Cloudflare may be **DNS-only or proxied**.
- **Verification**: the TXT token proves control. The A check accepts our IP for its mode — or, when proxied, Cloudflare's
  ranges (we cannot see the origin IP then, so we confirm with an HTTP probe: `GET http://store.example/.well-known/caspin/<token>`
  must reach us). Re-checked daily; a domain that stops reaching us is marked and alerted (after 3 days the store page says
  "moved").
- **Certificates**: HTTP-01 per host (the DNS is the reseller's, so DNS-01 through our Cloudflare is not possible). nginx serves
  `/.well-known/acme-challenge/` on **port 80 and on 443** for every pending host (443 with a temporary self-signed certificate
  until the real one exists), so issuance works when:
  - *direct, DNS-only*: Let's Encrypt → our port 80;
  - *tunnel*: Let's Encrypt → Iran IP:80 → passthrough → our port 80 (as caspintunel.com today);
  - *proxied by their Cloudflare*: Cloudflare → our 80 (SSL mode "Flexible") or 443 (SSL mode "Full"); the reseller must not use
    "Full (strict)" until the certificate exists, and Cloudflare's "Always Use HTTPS" is fine (the challenge is served on 443 too).
  One certificate per host (`store.example` + `www`), own lineage under `nginx/letsencrypt/`, renewed by the existing `certbot`
  container (`certbot renew` covers webroot lineages); alert 14 days before expiry. Let's Encrypt limits (50 certificates per
  registered domain per week, 300 new orders per account per 3 h) are far above our need; issuance is queued one at a time.
- **Real client IP**: unchanged rules — `CF-Connecting-IP` trusted only from Cloudflare's published ranges (refreshed daily by
  `access_tick_task`), the tunnel's PROXY-protocol / source addresses only from the configured tunnel sources; never a header a
  client can set. Throttles and audit use that IP.
  **Fixed 2026-11-04:** caspintunel.com is in access mode *tunnel* with source `10.10.10.1` (backhaul), so tunnel visitors are
  limited per client, not as one IP. Their **real IP is still unknown** (backhaul's port forwarder opens a new TCP connection,
  no PROXY protocol). For per-IP limits / audit of tunnel-mode stores, the Iran side needs a PROXY-protocol sender (e.g. HAProxy
  `send-proxy-v2` over the existing tun link) + our per-port PROXY switch — planned before Phase 3, with the owner's go.
- **nginx**: one generated file per store host in `nginx/tenants/` (template + render, like `paths/active.conf`) with every route
  of the default site (site, admin path, `/api/`, `/ws/`, `/media/`) and the PROXY-protocol listener for tunnel mode. Changes
  only through a host watcher (`scripts/tenants.sh apply-request`, cron every minute): render → `nginx -t` → reload → verify over
  TLS → rollback. The container never reloads the host by itself (same rule as `domain.sh`).
- **Health**: every 5 min per active host — TLS handshake, days to expiry, `GET /api/v1/health/` answers for the right tenant,
  DNS still reaching us; shown in «فروشگاه» and (read-only) to the reseller; alerts to us.

## 8. Telegram bots and the Mini App

- **Webhook mode for every tenant bot**: `setWebhook(url=https://<our platform host>/tg/hook/<tenant_id>/, secret_token=…,
  allowed_updates=[…])`. One endpoint, per-tenant secret (Telegram sends it in `X-Telegram-Bot-Api-Secret-Token`), no process per
  bot. The hook answers within a second and queues heavy work; `update_id` deduplicated. The webhook URL is on **our platform
  host** (not the tenant's domain), so a tenant domain problem does not stop the bot.
- **Setting the token** (**our staff only**, Agency → admin → «فروشگاه»): `getMe` check, store encrypted, set webhook, set the menu
  and the Mini App button to `https://<tenant domain>/`. Clearing the token deletes the webhook. The reseller sees the bot's
  username and state, and edits the bot **texts** (branding), not the token.
- **Mini App**: initData is validated with **that tenant's** bot token (today: the sales-bot token). The phone gate and
  `handle_contact` run per tenant.
- **Our two bots** (sales, backup) stay as they are (polling containers) for the default tenant and for us.
- Cost: no extra memory per bot; one HTTP request per update through `web` (bots are low-traffic compared with the site).

## 9. Payments, unique amounts and the SMS app

- **Cards per tenant**; the checkout shows only the tenant's cards. Card numbers encrypted at rest (shown to that tenant's
  customers only).
- **Unique-amount pools**: today one global pool (`order.amount_unique_lock` unique, agency payments share it). New: pool key =
  the **set of SMS devices / bank accounts that confirm the payment**. Default tenant + agency payments + Blu keep the current
  pool; each reseller tenant has its own pool (`unique (pool_id, amount_unique_lock)`). Two tenants can show the same amount at
  the same time because their SMS come from different devices.
- **Matching**: an SMS is matched only against open orders of the device's tenant (device token → tenant). Every existing rule
  stays (exact match only, near-miss review, rounded rule, received_at window, idempotent batch).
- **Review**: the reseller's payments queue (live WebSocket per tenant), Telegram alert through **their** bot, push, sound.
- **Android SMS app (improved)**: first screen asks for **store domain + device token** (or scans a QR from the store admin);
  the app calls `https://<domain>/api/v1/payments/sms/ping/` to confirm and shows the store name. The same APK works for every
  tenant (no per-tenant build); downloads from the store admin. Bank sender numbers per tenant. *iPhone Shortcut per tenant*:
  optional, same builder with the tenant domain (signing remains manual, as today).
- **Blu** stays ours only (default tenant + agency payments).

## 10. PasarGuard ownership and quota

- Create the PasarGuard user with **our** admin token (no reseller password stored), then `set_owner` to the reseller's admin
  — PasarGuard then counts the user's traffic against the reseller (their `data_limit` / remaining). Read back and mirror as today.
- **Quota guard** (D6) before order creation, renewal, add-on and manual invoice with a service action, on the **existing agency
  numbers** (the synced `admin_limit_bytes` / remaining that enforcement uses, at most one sync old — 2 min; a live GET when within
  10 % of the limit): remaining − open reservations of that tenant ≥ requested volume. Not enough → sale blocked with a friendly
  message, reseller alerted, we are alerted. Unlimited reseller admins are not blocked.
- **Warnings** at **20 % and 10 % remaining** (80 % / 90 % used; 80 % is the portal's existing warning): store admin banner + bot +
  push + the existing portal warning; the reseller can request volume with the existing «درخواست شارژ» (our approvals + per-GB
  invoicing unchanged).
- Account names stay unique across the whole panel (one PasarGuard namespace) — the existing `check_account_name` applies.

## 11. Reseller staff and permissions

- A store has **store roles** (`role.tenant = A`) and **store staff** (`staff.tenant = A`); sign-in on the store's admin path
  with the store's own JWT audience (`tid` claim).
- **Ceiling**: we set, per tenant, the permission codes a reseller may hold and grant (`tenant_permission_ceiling`; a default
  template for new stores). The reseller's own store-owner role = the ceiling. A store role can only contain codes ⊆ ceiling
  ⊆ the reseller's role; lowering the ceiling strips codes from that tenant's roles immediately.
- Platform-only codes are never in a ceiling (settings.manage, paths, domain wizard, **store domains and bot token** (D5),
  users.purge of other tenants, agency.*, accounting of the platform…). A test checks the list.

## 12. Email per tenant

- Default: sent by our relay from `noreply@<our domain>` with the **tenant's store name** as the display name and the tenant's
  support address as `Reply-To` — no DNS work for resellers, deliverability stays ours.
- Optional per tenant: their own SMTP relay (encrypted credentials, test button) to send from their domain; then SPF / DKIM are
  their responsibility (instructions shown). Our mail server never hosts tenant domains.

## 13. Rate limits

- Existing DRF throttles become per tenant + per client IP (`t:<id>:` in the bucket key) so one store's traffic cannot use
  another's budget; auth throttles stay strict.
- Per-tenant caps (in `tenant.limits`, we set them): orders per minute, SMS inbound per minute per device, bot updates per second,
  tickets per hour, staff count. Over the cap → 429 for that tenant only + an alert to us.
- nginx: `limit_req` zone per server name for `/api/` and the bot hook.

## 14. Backups and tenant export

- **Our backups unchanged**: full DB dump to Telegram, retention as today (every tenant's data is in it).
- **Tenant export** (when `export_allowed`, which we switch per reseller): JSON + CSV of customers, services, orders, payments,
  tickets, discount codes, settings and branding; zip encrypted with a one-time password; private download for 24 h; audited;
  at most one export per 6 h. No secrets (bot token, card numbers masked except the last 4).
- Restore of a single tenant from our full backup is a manual, staff-only operation (documented runbook), never self-service.

## 15. Import from other systems (last phase)

Pluggable importers (`tenancy/importers/<name>.py`) with one interface: `detect(file)`, `preview(file) → mapping report`,
`run(file, mapping)` (idempotent, source ids stored, batches of 500, audit). PasarGuard users are **linked, never created**:
an imported service is matched to an existing PasarGuard user owned by the reseller (by username / note / sub link);
missing ones are listed in the report.

**Source formats to support (in this order):**

| Importer | What it reads |
|---|---|
| `csv` / Excel | our template: customers (name, phone, Telegram id, balance), services (PasarGuard username), orders / payments (optional) |
| `pasarguard_users` | the reseller's users straight from PasarGuard (owner = reseller) → customers + services, linked by Telegram id or note |
| MySQL dumps of common Iranian VPN sales bots | e.g. **MirzaBot**, **WizWiz**, Marzban / PasarGuard sales bots built on the usual PHP + MySQL templates, 3x-ui / Hiddify bot databases — each needs a sample to map its tables |
| JSON exports | bots that export users / orders as JSON |

**What I need from you before phase 10:** for each source the resellers actually use — the name / repository of the bot, one
**anonymized** sample dump or export (a few hundred rows is enough), and which fields matter (balance? wallet? referral?). Also
your rule for customer balances (import as a store credit, or ignore).

## 16. Security

- **Isolation** — §3; it is the release gate of every phase.
- **Secrets**: bot tokens, webhook secrets, tenant SMTP passwords: `EncryptedTextField` (Fernet, `FIELD_ENCRYPTION_KEY`); never
  returned by an API (write-only, "set" / "not set"), never audited in clear, masked in logs. Card numbers encrypted at rest.
- **Auth**: tokens carry `tid`; sign-in endpoints still never authenticate (`FreshAuthMixin`); CSRF / CORS origins per verified
  domain; cookies are not used for the API.
- **Media**: private files under `tenants/<id>/…`, served only through the auth-checked API (`X-Accel-Redirect`), tenant checked.
- **Our staff**: see everything with a tenant filter; every action on a tenant's data is audited with the tenant.
- **Store staff**: can never reach platform endpoints (default-deny like group managers today).
- **Suspension**: one switch per tenant — store shows a maintenance page, bot answers "temporarily unavailable", sales blocked,
  existing services untouched.
- **Domains**: only verified hosts are routed; a removed domain's nginx file and certificate are removed.

## 17. Filtering and abuse risk of reseller domains

- All tenant domains in "direct" mode resolve to **our IP**. If Iran filters one tenant domain, only SNI is affected; if a tenant
  attracts an **IP block** or abuse complaints (phishing, spam), every store on that IP — and our default store — suffers.
- **The PasarGuard nodes on this host share our IP today.** A VPN node IP is exactly what gets filtered; that is a reason to move
  the nodes off this host before onboarding stores (§19).
- Mitigations: stores in "tunnel" mode through Iran tunnel IPs (as our access mode), the ability to put a tenant on its own
  tunnel / IP later, terms of use + suspension switch, daily DNS checks, abuse contact on every store footer, our default store
  can switch access mode independently.

## 18. Moving today's data into the default tenant

Backward compatible, two releases per step (CLAUDE.md migration rule):

1. **Release A**: create `tenant` (+ default row from `site_config`, `caspintunel.com` as its verified `tenant_domain`), add nullable
   `tenant_id` to every tenant table; a data migration fills `tenant_id = default` in batches (today's DB is 23 MB — seconds).
   Code still ignores it.
2. **Release B**: `TenantMiddleware` + managers active; all hosts that are not the default domain → 404; composite unique
   constraints added *next to* the old ones.
3. **Release C** ✅ v1.42.0: `tenant_id` NOT NULL (after the last backfill, `tenancy.0004`); old single-column unique constraints
   dropped (per-store "already exists" checks in the admin serializers; customers sign in through `TenantModelBackend`);
   strict mode (`TENANCY_STRICT`, default on): a tenant-table query without a tenant in the web process raises `NoTenant` —
   processes without a request still use the default tenant. Turned on after 44 h of Release B with zero "query without a
   tenant" warnings. The isolation test suite is a required check.

Rollback at every step = previous image (the columns are additive). Pre-update dump as always.

## 19. Server capacity

**Decision: stay on the current server** (2 vCPU AMD EPYC, 3.7 GiB RAM, 38 GB disk; the owner enlarges swap). Measured
2026-11-04: ~2.8 GiB RAM used, ~1 GiB of 2 GiB swap in use, short memory stalls; our containers ~1.2 GiB; the three PasarGuard
nodes + x-ui + tunnel ~0.7 GiB; dockerd, page cache and admin sessions the rest. The platform is sized to fit, not to grow fast.

**How it fits (Phase 0, before any tenant work):**

- **No process per store or bot**: tenant bots by webhook only, handled by the existing `web` workers; our own two polling bots
  stay as they are.
- **Memory limits per container** (`mem_limit` in `docker-compose.prod.yml`, swap allowed up to the same amount again):

  | Container | Limit | Today | Notes |
  |---|---|---|---|
  | web | 640 MB | ~210–270 MB | gunicorn 3 sync workers, recycled every ~1000 requests |
  | daphne | 192 MB | ~25 MB | WebSockets |
  | celery_worker | 640 MB | ~205 MB | concurrency 2, child recycled after 200 tasks or ~250 MB (runs the DB dump too) |
  | celery_beat | 192 MB | ~25–95 MB | |
  | db (MySQL 8) | 640 MB | ~210 MB | `performance_schema` off (~100+ MB saved), `max_connections` 60, buffer pool 128 MB (the DB is 23 MB) |
  | redis | 160 MB | ~10 MB | `maxmemory 100mb`, `volatile-lru` — only keys with a TTL (cache, throttles) can be evicted, never Celery queues |
  | nginx | 128 MB | ~7 MB | one server block + cert per store adds little |
  | bot_sales / bot_backup | 192 MB each | ~27 MB | |
  | frontend_user / frontend_admin | 48 MB each | ~3 MB | static files |
  | mailserver | 256 MB | ~26 MB | SMTP only |
  | certbot | 96 MB | ~2 MB | |
  | **Sum of limits** | **≈ 3.4 GB** | **≈ 0.8–1 GB** | limits are caps, not reservations; a runaway container is killed and restarted alone instead of pushing the host into swap |

- **PasarGuard nodes on this host**: they stay (the owner's decision). They are not ours to limit; if memory stalls persist after
  Phase 0, moving them is still the single biggest relief (≈ 0.7 GiB and the shared-IP filtering risk, §17).

**Realistic size on this server** (tenant features add rows and requests, not processes):

| Load | Fits? |
|---|---|
| up to **10 stores**, ≈ 1,000 customers in total, ≈ 100 orders/day, ≈ 10 webhook bots, one SMS device per store | **yes, comfortably** |
| 10–25 stores, ≈ 3,000 customers, ≈ 300 orders/day | **yes, watching the metrics below**; may need gunicorn 4 workers and less swap use |
| more, or a store with heavy bot traffic (broadcasts to thousands) | **upgrade first** (4 vCPU / 8 GB) or move the PasarGuard nodes off the host |

**Metrics to watch** (Monitoring page + Telegram alerts; Phase 0 adds the container card):

- **memory per container** vs its limit (alert at 85 %), **OOM kills / restarts** (alert at once);
- host **swap in use** (alert above 1.5 GB for 30 min) and **memory pressure** (`/proc/pressure/memory` `some avg60` > 10 %);
- **load average** > 2.0 (= the 2 vCPUs) for 15 min, CPU steal;
- **Celery queue length / age of the oldest task** (provisioning and notifications must stay under a minute);
- **API latency** (p95 of `/api/` > 1 s) and gunicorn worker timeouts in the logs;
- **MySQL** connections and slow queries; **disk** > 80 % (existing alert).

**Upgrade triggers** (any of them for a week): swap > 1.5 GB most of the day, pressure alerts daily, p95 > 1 s at peak, an
OOM kill per week, or more than 25 active stores.

## 20. Phased plan and size

Size = my estimate of working days for build + tests + browser checks + docs (one developer), and the releases it becomes.

| Phase | Content | Size | Releases |
|---|---|---|---|
| **0 — Prepare (current server)** ✅ v1.39.0 | Container memory limits, tuned gunicorn / Celery / MySQL / Redis, container memory + swap + pressure metrics with alerts (Monitoring card), docs. The owner enlarges swap. | 1–2 days | v1.39.0 |
| **1 — Tenant core** (A ✅ v1.40.0, B ✅ v1.41.0) | `tenancy/` (models, contextvar, middleware, managers, registry, allow-list), `tenant_id` on all tenant tables + default backfill (Release A→C), JWT `tid`, isolation test suite (inventory, API sweep, lint) | 6–8 days | 3 (A, B, C) |
| **2 — Store admin + branding** ✅ (A v1.43.0, B v1.44.0) | Store mode of the admin SPA (D1), «فروشگاه» tab for us, `tenant_branding`, `TENANT_KEYS`, pages / themes per tenant, user SPA branding per host | 5–6 days | 2 |
| **3 — Domains & TLS** | «فروشگاه» section (our staff): domains + mode + exact A record, TXT / A / proxied verification, HTTP-01 per host on 80 + 443, nginx per-tenant files via host watcher, health, read-only status for the reseller, renewal + alerts | 5–7 days | 2 |
| **4 — Catalog & PasarGuard** | Plans per tenant, `set_owner` provisioning, quota guard + warnings, renew / add-on per tenant | 4–5 days | 1–2 |
| **5 — Payments & SMS** | Cards / sources / devices per tenant, unique-amount pools, matching per tenant, reseller payments queue, Android SMS app update (domain + token, QR) | 6–8 days | 2 (+ APK) |
| **6 — Bots & Mini App** | Webhook endpoint, tenant bot token set by our staff, screens with tenant texts (edited by the reseller), Mini App per tenant | 5–6 days | 1–2 |
| **7 — Tickets, CRM, retention, discounts, analytics, notifications, push, email** | Scope everything, tenant email display name / optional relay, per-tenant rate limits | 6–8 days | 2 |
| **8 — Reseller staff** | Store roles, ceiling, sign-in on the store admin path | 3–4 days | 1 |
| **9 — Pilot** | One reseller, one domain, real sales for 2 weeks; daily isolation + health review; fixes | 2–3 days + 2 weeks | fixes |
| **10 — Tenant export** | Export job, encrypted zip, permission switch | 2–3 days | 1 |
| **11 — Importers** | Framework + `csv` + `pasarguard_users`; then one per source bot from your samples | 4 days + 2–3 per source | 1 each |
| **12 — Fee hook** | `tenant_billing`, monthly invoice generator (off), suspension on unpaid (off) | 1–2 days | 1 |

Total before the pilot (0–8): about **41–54 working days**. Every phase ends with the isolation suite green, browser checks
(phone + desktop, fa / en, light / dark) and the docs moved into architecture / erd / flows.

**Pilot rollout**: pick one reseller with steady sales and a domain on their own Cloudflare → staging store on a test subdomain
of caspintunel.com first → their domain (we set it up, D5) → 2 weeks with sales capped (`tenant.limits`) → open to more resellers
in small groups (≤ 5 per wave, metrics reviewed between waves).

## 21. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Tunnel clients have no real IP (`10.10.10.1`) | per-client limits only (a bot can rotate client ids — the total cap bounds it), no IP in audits | sources configured (done); PROXY protocol on the Iran side before tunnel-mode stores |
| A missed tenant filter leaks data between stores | severe | four-layer scoping, fail-closed context, inventory + API sweep tests as a release gate, unscoped allow-list |
| Shared IP filtered / blocked | all stores down | move nodes off host, tunnel mode per store, suspension switch, monitoring |
| Reseller quota runs out mid-checkout | paid order cannot be provisioned | guard before the invoice, re-check before provisioning, paid-but-blocked → staff + reseller alert, retry when quota arrives |
| Let's Encrypt failures (DNS changed, tunnel without port 80) | store without TLS | state machine with clear errors, manual-certificate path, alerts 14 days before expiry |
| Bot token leaked by a reseller | their bot hijacked | token encrypted, webhook secret rotated on every token change, one-click reset |
| Load growth on the small server (owner keeps 2 vCPU / 3.7 GiB) | slow checkout, OOM kills | Phase 0 limits + tuning, webhooks only, metrics + alerts, upgrade triggers (§19), cap stores per wave |
| Unique amounts collide across stores | wrong approval | per-pool constraint, device→tenant matching, unique-amount test |
| Importer maps balances / services wrongly | wrong customer state | preview + report first, idempotent runs, no PasarGuard writes during import |
| Support load (our staff see everything) | slower operations | tenant filter everywhere, per-tenant alerts go to the reseller first |
