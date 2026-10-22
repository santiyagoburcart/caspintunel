# Roadmap

Planned phases after v1.15.x. Nothing on this page is built yet. Each phase
ships as its own releases (tests on the isolated stack, fa/en, light/dark,
desktop + 390 px) and **must update [architecture.md](architecture.md),
[erd.md](erd.md) and [flows.md](flows.md)** in the same release.

| Phase | Theme | Depends on |
|---|---|---|
| 0 | Documentation refresh (architecture, ERD, flows, roadmap) — **done (v1.15.8)** | — |
| 1 | Ticketing core — models, rules, RBAC + scopes, notifications, API — **done (v1.16.0)** | — |
| 2 | Ticketing UIs — customer chat (site + bot, synced), staff inbox — **done (v1.17.0)** | 1 |
| A | Agency improvements — toasts, PasarGuard admin CRUD, admin detail tabs — **done (v1.18.0)** | — |
| 3 | CRM — customer 360, inactivity + reasons — **done (v1.19.0)** | 1–2 |
| 4 | Retention — warnings, win-back queue — **done (v1.20.0)** | 3 |
| 5 | CRM accounting — LTV, renewal / churn reports | 3, 4 |

## Phases 1–2 — Ticketing

**Phase 1 (done, v1.16.0)** — backend only: app `tickets` (topics with
active-service gate, tickets, messages + attachments, events), limits and
auto-close / reopen settings, RBAC (`tickets.view|reply|assign|close|manage_topics`,
role "Ticketing"), per-staff topic scopes, notifications (customer: site / bot /
email; staff: real-time badge, bot DM after linking Telegram, email), user and
staff API. See [architecture.md](architecture.md#ticketing), [erd.md](erd.md),
[flows.md](flows.md).

**Phase 2 (done, v1.17.0)** — Telegram-like customer chat on the site and in
the sales bot (synced), staff inbox (split view, internal notes, saved replies,
timeline, customer side panel), topics / saved replies / settings page, staff
topic scopes + display name + email in Roles, "My Telegram" link code, live
badge (sidebar, Settings index, mobile Settings tab), staff ticket handling in
the bot. Rule change: anyone who ever had a service may use every topic; only
never-purchased users are limited to pre-purchase; an expired-service hint with
"renew" above the form. Still open from the original list: response-time
reports per admin (first response / resolution) — candidate for Phase 3 / 5.


One ticket system used from the **site** and the **sales bot**, kept in sync:
a reply written in either place shows up in both.

- **Topics are configurable** in the panel (name fa/en, active, order, who may
  use it). Example: sales question, payment problem, connection problem,
  renewal.
- **Pre-purchase rule:** a user without an active service may only open
  tickets in topics marked *pre-purchase* (e.g. "questions before buying").
  Users with an active service get every active topic.
- **Ticketing role** with **per-admin topic scopes**: a staff member sees and
  answers only the topics assigned to them; supervisors see all.
- **Chat UI like Telegram**, mobile-first: message bubbles, timestamps (Jalali),
  read state, attachments (images, with the same private-media rules as
  receipts), quick replies; the admin side is an inbox with filters (topic,
  status, assignee, waiting for us / waiting for customer).
- **Notifications** on new tickets and replies through the existing channels:
  site (WebSocket + bell), bot message, email — per-user channel rules as in
  `notify_user`.
- **Accountability:** every ticket keeps who replied, who assigned (to whom)
  and who closed / reopened it, with timestamps (`AuditLog` + ticket events),
  so response time per admin can be measured.
- Statuses: open → waiting on customer / waiting on staff → closed (reopen
  allowed for N days).
- Data model sketch (to be finalised in erd.md): `ticket_topic`,
  `ticket` (user, topic, status, assignee, opened_via site/bot),
  `ticket_message` (author user | staff, body, attachment, via),
  `ticket_event` (assigned / closed / reopened / topic changed, by staff),
  `staff_topic_scope`.
- Phase 1 = backend + site + admin inbox; phase 2 = bot parity + sync,
  notifications, reports (first response time, resolution time per admin).

## Phase A — Agency improvements

**Done in v1.18.0.** Notes from building it: PasarGuard 5.4.1 has no `is_sudo`
— admins get a role (owner roles = sudo), and allowed groups / user templates
belong to the role, so the create form shows the live role list with what each
role allows instead of per-admin group lists.

Improvements to the agency panel and reseller portal; each item is its own
release. Fixed constraint: the PAMP formulas, sync order and enforcement stay
verbatim (golden test) — changes go around them, never into them.

- **Global toasts, top-centre and animated** — one toast system for the whole
  admin panel (and the reseller portal): shown top-centre on every screen size,
  slide / fade in and out (reduced-motion respected), stacked, success / error /
  info tones, same placement in fa and en.
- **Create / edit / delete PasarGuard admins from the Agency Panel** with every
  field the PasarGuard admin API accepts — the field list is taken from the
  live panel's API schema when this is built, not from memory — panel first then read
  back and mirror, confirmation for delete, audited; the next sync stays the
  source of truth for the numbers.
- **Admin detail split into tabs** — e.g. Overview (numbers, limit), Limits &
  actions, Users, Accounting / statement, History (snapshots, syncs) — instead of
  one long page, with the selected tab in the URL; tabs usable on phones.

## Phase 3 — CRM

**Done in v1.19.0** (see [architecture.md](architecture.md#crm)): customer 360, lifecycle stages with override, owner, tags, notes,
timeline; inactivity detection from PasarGuard connection data with a follow-up queue, reasons, outcomes, messages from
templates, tickets on the customer's behalf, optional automatic message; leads list; reports. Original plan:

- **Customer 360** page: profile, services (status, usage, expiry), orders and
  payments, tickets, notifications sent, source (site / bot / referral),
  lifetime value (from phase 5), notes and tags.
- **Inactivity detection:** customers whose service expired / ran out and was
  not renewed within N days, or who have not connected for N days (from
  service `online_at` sync) — a list with filters.
- **Reason tracking:** staff (or the customer via a short bot / site survey)
  record why a customer left or stopped using the service (configurable reason
  list: price, speed, moved to another provider, no longer needed, …), with
  history.
- **Linked to tickets:** a customer's tickets and their outcomes appear on the
  360 page; a ticket can be tagged with a churn reason.

## Phase 4 — Retention

**Done in v1.20.0** (see [architecture.md](architecture.md#retention)): configurable pre-expiry warnings with quiet hours,
per-threshold templates and one-click renew; win-back queue with discount codes, auto won-back and revenue recovered;
retention reports. Original plan:

- **Configurable warnings:** expiry (days before) and volume (percent used)
  thresholds, multiple steps, channels (site / bot / email) and texts in fa/en,
  replacing the fixed thresholds of today's `service_alerts_task`.
- **Win-back queue for expired customers:** a worklist of recently expired /
  inactive customers (from phase 3) with suggested action (renewal link,
  discount code, contact), assignment to staff, outcome tracking (renewed /
  declined + reason / no answer).
- Measured: renewal rate after a warning, win-back success rate.

## Phase 5 — CRM accounting

- **LTV** per customer and per acquisition source (total paid, number of
  orders, months active).
- **Renewal / churn reports** per Jalali month: active base, new, renewed,
  churned, churn reasons, revenue from renewals vs new sales; export CSV /
  Excel like the agency reports.
- Cohorts by first-purchase month.
