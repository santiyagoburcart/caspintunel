# Flows

Sequence diagrams of the main business and operations flows, as implemented.
Mermaid (rendered on GitHub and in the admin Documentation page). Function names point at the code.

Related: [architecture.md](architecture.md) · [erd.md](erd.md).

## 1. Purchase + card-to-card payment

A customer buys on the site, in the Mini App or in the sales bot — all three
call the same order API. The invoice amount is unique, so the bank SMS can
identify the order.

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant UI as Site / Mini App / Bot
    participant API as web (orders)
    participant DB as MySQL
    participant Q as Admin payments queue (WebSocket)
    actor A as Admin

    C->>UI: choose plan (or custom GB)
    UI->>API: POST create order
    API->>DB: reuse own still-reserved pending order for the same purchase?
    API->>DB: amount_unique = price + random 200..1500 T<br/>(unique lock, not used by this user in 24 h)
    API-->>UI: invoice: exact amount, bank card, expires in 30 min
    C->>C: card-to-card transfer of the EXACT amount
    alt customer uploads a receipt
        C->>UI: upload receipt image
        UI->>API: POST receipt (throttled 20/h)
        API->>DB: Payment(card_manual, pending)
        API-->>Q: live event → queue badge
        A->>API: approve (or reject with reason)
        API->>API: approve_payment → mark_paid_and_fulfill
        Note over API: reject_payment closes the order,<br/>it is never reused
    else the bank SMS arrives first
        Note over API: see flow 2 — auto-confirm
    end
    API->>DB: order → paid (lock kept until provisioned)
    API-)API: fulfill_order (Celery, on commit)
    Note over API: see flow 4 — provisioning
    API-->>C: "service ready" (site + bot + email) with QR + link
    Note over DB: beat every 5 min: unpaid pending orders past<br/>unique_expire_at → expired, lock released<br/>(orders with a receipt under review are kept)
```

## 2. SMS auto-confirm (exact match / near-miss review)

An operator phone (Android SMS Bridge or iPhone Shortcut) forwards each bank
SMS. Rules: one explicit unit, converted to tomans once, **exact** match only —
never a tolerance, never a ×10 / ÷10 retry (incident 2026-10-15).

```mermaid
sequenceDiagram
    autonumber
    participant P as Operator phone
    participant API as web /payments/sms/inbound/
    participant M as matching.ingest_sms
    participant DB as MySQL
    participant Q as Admin queue (WebSocket)
    actor A as Admin

    P->>API: {text, sender[, received_at]} + X-Device-Token
    API->>M: ingest_sms(device, text, sender)
    M->>DB: resolve sender → SmsSource (allow-list)
    M->>M: deposit_amount(text, unit from SMS<br/>else SmsSource.amount_unit, default Rial) → tomans
    M->>DB: SmsMessage(raw, parsed amount/unit)
    alt sender not allowed
        M->>DB: note "sender not in bank numbers" — stop
    else pending order with amount_unique == SMS tomans (exactly)
        M->>DB: Payment(sms_auto, approved, confirmed_by=system)
        M->>M: mark_paid_and_fulfill → fulfill_order
        M->>DB: audit payment.sms_auto_confirmed
        M-->>Q: sms_approved
    else near miss: equal only after ×10/÷10, or within ±20 % of an open invoice
        M->>DB: SmsMessage.mismatch_order + less/more
        M->>DB: Payment(sms_mismatch, PENDING)<br/>(or attach SMS to an existing pending receipt)
        M->>DB: audit payment.sms_amount_mismatch
        M-->>Q: sms_mismatch (both amounts + difference)
        A->>API: review → approve_payment / reject_payment
        Note over DB: order with a pending payment does not expire
    else nothing close
        M->>DB: note why (no amount, not whole, no order, order not pending)
    end
    API-->>P: {matched, order_id | reason}
```

Matching happens at `received_at` — when the phone got the SMS. An order counts
as open for an SMS if it is still pending, or it expired since but was still open
when the SMS arrived (deadline and close time after it); an order created after
the SMS arrived never matches (5 min clock skew allowed). The iPhone Shortcut
(v1.1+) saves every SMS to a queue file on the phone **before** any network call
and uploads the whole queue to `/payments/sms/inbound-batch/`, which is
idempotent — see [sms-batch.md](sms-batch.md).

## 3. Renewal

A renewal is paid like a purchase (flows 1–2) with `type=renew` on an existing
service, but it is **not applied immediately**: it waits for the end of the
current cycle so the customer loses nothing. It always runs on the **same PasarGuard
username and subscription link** — never an account-name step, never a new account.

Which plan (`orders.services.renewal_plans` = active, fixed-volume, same panel;
`renewable_plan` = the service's own plan if it is one of them):
- own plan → one tap (site: summary dialog → checkout; bot `s:<id>:rn` → «✅ تمدید با همین پلن»);
- «تغییر پلن / ارتقا» (site `checkout?renew=<id>&pick=1`, bot `s:<id>:rnp`) → any renewal plan;
- no usable plan (e.g. linked manually by staff) → the plan list straight away with a short note.
`GET /services/<id>/renew-info/` returns `plan`, `plans`, `needs_plan`. Custom-volume plans are
refused for renewals (the renewal applies the plan's fixed volume). Discount codes apply as usual.
After payment `schedule_renewal` makes the paid plan the service's plan (audit
`service.plan_changed`, via `renewal`). Staff can set / change / clear a service's plan on
Admin → Services → edit (or when linking an account); filter «بدون پلن» lists services without one.

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant API as web
    participant W as celery_worker
    participant B as celery_beat
    participant PG as PasarGuard panel
    participant DB as MySQL

    C->>API: GET /services/S/renew-info/ → own plan, or plan list (needs_plan)
    C->>API: renew service S with plan P (own plan, or changed / chosen)
    API->>DB: Order(type=renew, service=S, plan=P) — no account name
    Note over C,API: payment as in flows 1–2
    W->>DB: fulfill_order → schedule_renewal:<br/>ScheduledRenewal(S, P, renewal_mode + carry_over copied from P)<br/>S.current_plan = P
    W->>DB: order → completed (no "delivered" message yet)
    loop every 5 min
        B->>W: apply_due_scheduled_renewals
        W->>DB: renewals whose service reached the end of its cycle
    end
    alt renewal_mode = reset
        W->>PG: PUT same username: new limit + expiry, reset usage
    else renewal_mode = carry_over
        W->>W: add leftover volume and/or time (both / volume_only / time_only)
        W->>PG: PUT same username with the combined values
    end
    PG-->>W: user
    W->>DB: mirror panel → Service, applied_at = now (never twice)
    W-->>C: "your service was renewed" (site + bot + email)
    Note over C: same username, same subscription link
```

## 4. Service provisioning

```mermaid
sequenceDiagram
    autonumber
    participant W as celery_worker (fulfill_order)
    participant DB as MySQL
    participant PG as PasarGuard panel (plan's panel)
    actor C as Customer

    W->>DB: order (new) → _ensure_service: Service(pending, panel username)
    W->>W: provision_service(service, plan)
    alt already provisioned (has subscription URL)
        W->>PG: GET user → resync only
    else
        W->>PG: POST /api/user (limit, expiry or on_hold_expire_duration,<br/>plan group_ids or panel defaults, HWID limit)
        alt 409 — username exists
            W->>PG: GET user
            alt our own earlier attempt (note caspintunel#id, not older than the service)
                W->>W: adopt it
            else someone else's account (e.g. a reseller's customer)
                W->>DB: drop the pending Service, order stays paid + needs_new_name (no auto retry)
                W-->>C: "choose another name" (site form, bot button nn:id, email)
                C->>W: new name → checked in DB + on the panel → fulfil again
            end
        end
    end
    PG-->>W: user object
    W->>DB: apply_user_to_service (mirror) → status on_hold (timed) or active
    W->>DB: order → completed, lock released, audit
    W-->>C: notify site + email, bot gets the QR photo + link
    Note over W,PG: PanelUnavailable → Celery retry,<br/>beat retries paid-but-unprovisioned orders every 10 min
```

Account names are checked **in our DB and on the panel** when the order is placed
(`orders.services.check_account_name`, site + bot ask for another name; an unreachable
panel does not block the sale — the 409 guard above still never attaches). Staff manual
creation refuses a name that exists on the panel and offers **Link existing account**; linking
an account owned by another panel admin needs `confirm_other_admin` (a checkbox in the modal).

Add-on volume orders call `add_service_data_limit` instead (panel first, then
mirror).

**Service sync (v1.28).** Every `service_sync_interval_minutes` (Settings; currently every minute) the beat runs
`sync_all_services`: **every** service with a panel account — whatever its status, expired /
limited / disabled included — is read from PasarGuard (status, expiry, volume, usage, on-hold,
online / last seen) and mirrored. A renewal, usage reset, top-up or re-enable done directly on
PasarGuard is detected (`service.changed_on_panel` audit) and re-arms the volume / expiry
reminders. One run at a time (cache lock). Staff **Sync** (`services/sync-now/`) runs it in the
request and answers `{checked, updated, errors, skipped, rows}` (40 s budget, the rest continues
in the background); each row has its own sync (`services/{id}/sync/`). The customer's services
page re-reads ended services (≤ once a minute) and on-hold ones (15 s). Changing the subscription
link signature / `online_at` alone is not counted as an update.

Before 1.28 the beat skipped expired services, so a service renewed directly on PasarGuard after
it expired stayed "expired" here forever (incident 2026-10-28, `hadis_sadeghi`).

**Reminders never use stale numbers.** A warning (80 % / 95 %, 3 / 1 days) is only created after
the service was re-read from PasarGuard (or synced < 2 min ago); if the panel can't be asked no
warning goes out. A queued bot / email warning is dropped when the service was renewed / reset
before delivery. Win-back only marks services synced in the last 30 minutes.

## 5. Agency sync + enforcement + ledger charge

```mermaid
sequenceDiagram
    autonumber
    participant B as celery_beat
    participant W as celery_worker
    participant PG as PasarGuard panel
    participant DB as MySQL
    actor A as Admin (agency.manage)
    actor R as Reseller (portal)

    B->>W: sync_panel_admins (every agency_sync_interval_minutes)
    alt agency_sync_enabled is off
        W-->>B: "disabled" — nothing done
    else
        W->>PG: GET admins + each admin's users
        alt panel call failed
            W->>DB: SyncLog(failed) — stop, nothing changed
        else
            W->>DB: update PanelAdmin counters
            W->>DB: deleted-user tracking via UserTrafficSnapshot<br/>(skipped on a truncated list)
            W->>DB: remove admins gone from the panel (never on an empty list)
            opt agency_enforcement_enabled
                W->>PG: used ≥ limit → disable admin (pamp_blocked)<br/>used < limit and blocked → enable admin
            end
            W->>DB: SyncLog(success | partial)
        end
    end

    A->>W: Limits & actions → preview (set / add / reduce, GB)
    W-->>A: old → new limit, remaining, charge = ΔGB × price per GB on that date
    A->>W: confirm set-limit
    W->>PG: set admin data_limit
    W->>DB: PanelAdmin limit + remaining
    W->>DB: increase only → LedgerEntry(quota_charge, gb, price_per_gb, old/new)
    W-->>A: "Limit set to 5,200 GB (5.08 TB)"
    A->>DB: record payment / manual charge / adjustment / void
    R->>W: portal: usage, limit, statement + balance
```

## 5b. Create a PasarGuard admin from the Agency panel

```mermaid
sequenceDiagram
    autonumber
    actor A as Admin (agency.manage)
    participant UI as /panel/agency/admins/new
    participant API as web agency/panel-admins/
    participant PG as PasarGuard (picked panel)
    participant DB as MySQL

    UI->>API: GET options/?panel=
    API->>PG: GET /api/admin-roles/simple, /api/admin-role/{id}, /api/groups/simple, /api/user_templates/simple
    API-->>UI: panels + roles (owner flag, allowed groups / templates, limits)
    A->>UI: username, password (generator), role, contact, subscription, notifications, overrides, variables, note, limit + price + group
    UI->>API: POST (validated: username, password ≥ 8, role, ids, URLs)
    API->>PG: POST /api/admin (AdminCreate)
    PG-->>API: created (409 → "already exists")
    API->>PG: GET /api/admins?username= (read back)
    opt the agency panel
        API->>DB: PanelAdmin row (next sync fills the PAMP numbers)
        API->>DB: AdminPrice + LedgerEntry quota_charge (limit × price) · group member
    end
    API->>DB: AuditLog agency.admin_created (no password)
    API-->>UI: send-to-reseller card: portal link + username + password (once) + toast
```

Edit (`PATCH`, only changed fields, password reset shown once) and delete
(`DELETE`, typed username; local row + group membership removed, ledger kept)
follow the same panel-first rule.

## 5c. Group manager gives volume → staff approve / reject

```mermaid
sequenceDiagram
    autonumber
    actor M as Group manager
    participant MP as /panel/ (group-manager menu)
    participant API as web agency/manager/
    participant PG as PasarGuard
    participant DB as MySQL
    actor S as Staff (agency.manage + agency.accounting)
    participant AP as /panel/agency/approvals

    M->>MP: sign in at /panel/login (staff JWT, role "Group manager")
    Note over MP,API: every other /api/v1/admin/ endpoint → 403 for this staff (StaffPermission default-deny)
    M->>MP: + volume (GB) on an admin of their group
    MP->>API: POST admins/{u}/add-volume/ {gb}
    API->>API: own group? not sudo? GB > 0? cap (pending + GB ≤ max)?
    alt forbidden / cap reached
        API-->>MP: 403 / 409 cap_reached — nothing changed
    end
    API->>PG: GET /api/admins?username= (live limit; unlimited → 403)
    API->>PG: PUT /api/admin/{u} data_limit = live + GB
    API->>DB: PanelAdmin limit · VolumeRequest(pending) · AdminLimitChange(add, source manager)
    API->>DB: AuditLog agency.manager.volume_added (manager, group)
    API-->>MP: live at once — "pending approval"
    AP->>API: GET approvals/badge/ (every 30 s → menu badge + toast)
    S->>AP: Approve (price × GB shown; price asked if the admin has none)
    AP->>API: POST approvals/{id}/approve/
    API->>DB: LedgerEntry quota_charge (old → new, price of that day) · link to the limit-history row
    API->>DB: AuditLog agency.approval.approved
    S->>AP: or Reject (confirm)
    AP->>API: POST approvals/{id}/reject/ {confirm: true}
    API->>PG: PUT data_limit = live − GB (never 0 = unlimited)
    API->>DB: AdminLimitChange(reduce) · request rejected · no charge
```

A new admin made by a manager (`POST admins/`) follows the same path: created on
PasarGuard with an allowed role and the initial GB, added to the group, request `create`.

## 6. Bot and Mini App login

```mermaid
sequenceDiagram
    autonumber
    actor U as Telegram user
    participant T as Telegram
    participant Bot as bot_sales
    participant API as web
    participant DB as MySQL

    U->>T: /start (or any message)
    T->>Bot: update (long polling)
    alt force_share_phone on and no account with this telegram_id
        Bot-->>U: welcome + "share phone" button (no account created)
        U->>Bot: shares contact
        Bot->>Bot: contact.user_id == sender? else refuse
        Bot->>DB: handle_contact — normalize phone, find account by phone
        alt account with that phone, no Telegram
            DB-->>Bot: link telegram_id to it (username + password kept), audit user.linked_telegram
        else account linked to another Telegram id
            Bot-->>U: refused, contact support
            Bot->>T: DM staff (users.manage) / backup chat, audit user.telegram_link_conflict
        else no account
            DB-->>Bot: new User(source=bot) — random username + password sent once
        end
    else gate off / account exists
        Bot->>DB: ensure_bot_user(telegram_id)
    end
    Bot->>T: getChatMember for each required channel
    alt missing channel
        Bot-->>U: join channels (asked again on any message)
    end
    Bot-->>U: main menu (screen edited in place)

    U->>T: opens the Mini App
    T->>API: SPA loads, POST /auth/telegram/miniapp/ {initData}
    API->>API: HMAC check with the sales-bot token, auth_date ≤ max age
    API->>DB: phone gate on and no account → 403 phone_required (nothing created);<br/>the SPA asks Telegram for the contact → bot handle_contact → retry
    API->>DB: ensure_bot_user(telegram_id) — existing account
    API-->>T: JWT pair — the SPA never shows a login form inside Telegram
```

## 7. Ticket lifecycle and notifications

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant API as web /tickets/
    participant DB as MySQL
    participant W as celery_worker (notify)
    participant WS as daphne /ws/admin/tickets/
    actor S as Staff (scope covers topic)

    C->>API: GET /tickets/topics/
    API-->>C: topics with available / locked + renew hint (never purchased → only pre-purchase)
    C->>API: POST /tickets/ (topic, subject, body, ≤3 files)
    API->>API: topic active? needs active service? open tickets < limit?<br/>files: sniffed type, Pillow decode, ≤5 MB
    API->>DB: Ticket(open, number) + message + attachments + event created
    API-)W: notify new_ticket (on commit)
    W->>WS: event + badge to each staff in scope (or the assignee)
    W-->>S: bot DM if Telegram linked, email if set
    S->>API: GET /admin/tickets/ (inbox, only scoped topics) → detail (marks read)
    alt internal note
        S->>API: POST reply internal=true
        API->>DB: staff-only message + event internal_note (status unchanged)
    else answer
        S->>API: POST /admin/tickets/{id}/reply/
        API->>DB: status awaiting_user, first_response_at, auto-assign to the replier,<br/>event staff_replied, AuditLog
        API-)W: notify staff_reply
        W-->>C: site bell (real-time, links to the chat) + email + bot message with Reply / Open
    end
    C->>API: POST /tickets/{id}/reply/
    API->>DB: status awaiting_admin, event user_replied
    API-)W: notify user_reply → assignee only
    opt staff
        S->>API: assign (target must cover the topic) · status · priority
        API->>DB: event + AuditLog
    end
    loop beat every hour
        W->>DB: awaiting_user longer than tickets_auto_close_days → closed (system), event auto_closed
        W-->>C: site notification
    end
    C->>API: POST /tickets/{id}/reopen/ (within tickets_reopen_days, under the open limit)
    API->>DB: status awaiting_admin, event reopened
```

## 8. Tickets in the bot

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer (Telegram)
    participant Bot as bot_sales
    participant Svc as tickets.services
    participant W as celery_worker (notify)
    actor S as Staff (linked Telegram)

    C->>Bot: 🎫 Support / tickets → New ticket
    Bot-->>C: allowed topics as buttons (+ renew hint if all services expired)
    C->>Bot: topic → subject (typed) → message (text or photo / PDF)
    Bot->>Svc: open_ticket(channel=bot) — same rules as the site
    Svc-)W: new_ticket
    W-->>S: DM: #number + Reply · Open · Assign to me · Close
    S->>Bot: Assign to me / Reply (force-reply) → text or photo
    Note over Bot: staff callbacks st:* skip the customer gate,<br/>scope + permission checked, no customer account
    Bot->>Svc: staff_reply(channel=bot)
    Svc-)W: staff_reply
    W-->>C: bot message with Reply / Open + site bell + email
    C->>Bot: Reply → text / photo → user_reply(channel=bot)
    C->>Bot: Close / Reopen
```

## 9. Staff Telegram linking

```mermaid
sequenceDiagram
    autonumber
    actor S as Staff
    participant P as Panel API /admin/tickets/telegram-link/
    participant R as Redis cache
    participant T as Telegram
    participant Bot as bot_sales
    participant DB as MySQL

    S->>P: POST (logged in)
    P->>R: sha256(code) → staff id, 10 min
    P-->>S: code + deep link t.me/<bot>?start=staff-CODE
    S->>T: opens the link (or sends /start staff-CODE)
    T->>Bot: /start staff-CODE
    Bot->>R: look up and delete the code (single use)
    alt valid and this Telegram not linked to another staff
        Bot->>DB: Staff.telegram_id, telegram_linked_at + AuditLog
        Bot-->>S: linked ✅
    else
        Bot-->>S: invalid / expired / already linked
    end
    Note over Bot: no customer account is created for this message
```

## 10. CRM inactivity follow-up

```mermaid
sequenceDiagram
    autonumber
    participant B as celery_beat (hourly)
    participant W as celery_worker
    participant DB as MySQL
    actor C as Customer
    actor S as Staff (crm.manage)

    Note over W,DB: service sync keeps Service.online_at from PasarGuard
    B->>W: crm_detect_task
    W->>DB: services synced < 24 h: active + no connection for N days → no_connection case,<br/>on hold / never connected N hours after purchase → never_connected case (one open per service)
    W->>DB: stage → at_risk (CrmEvent)
    opt crm_auto_message on, inactive N days
        W-->>C: friendly message (site + bot) from the template, once per case
    end
    C->>DB: opens a "Connection problem" ticket → linked to the open case
    S->>DB: queue "نیاز به پیگیری" → case: reason, notes, assignee
    alt help the customer
        S-->>C: message from a template (site / bot / email)
        S->>DB: or open a ticket on their behalf (linked to the case)
    end
    S->>DB: close with outcome resolved / still inactive / lost
    loop next runs
        W->>DB: the service connected again → case closed (resolved, by the system), stage recomputed
    end
```

## 11. Pre-expiry warning and win-back

```mermaid
sequenceDiagram
    autonumber
    participant B as celery_beat
    participant W as celery_worker (crm.retention)
    participant DB as MySQL
    actor C as Customer
    actor S as Staff (crm.manage)

    B->>W: every 30 min: run_warnings
    W->>DB: due thresholds (data % / days left) → ServiceWarning (unique per service period)
    W-->>C: site bell now (→ /renew/<service>)
    alt quiet hours (default 00:00–08:00 Tehran)
        W->>DB: bot / email due at the end of the quiet hours
    else
        W-->>C: bot message with 🔄 renew button + email
    end
    C->>DB: renews within N days → warning converted
    Note over W,DB: hourly: run_winback
    W->>DB: service expired / used up → ServiceEndMark
    W->>DB: still ended after the grace (24 h), no other live service → winback case
    opt auto first message (off by default)
        W-->>C: win-back message (renew link)
    end
    S->>DB: queue "بازگشت مشتری": reason, owner, notes
    S->>DB: discount code (percent, N days, one per customer)
    S-->>C: win-back message from a template with {renew} {code} {percent}
    C->>DB: checkout with the code → order amount −percent (code reserved), paid → code used
    W->>DB: live again within the window → case closed won_back + recovered revenue
    S->>DB: otherwise: close as lost with a reason
```

## 12. Analytics (read-only)

```mermaid
sequenceDiagram
    autonumber
    actor A as Admin (accounting.view + crm.view)
    participant UI as /panel/analytics
    participant API as web crm/analytics/<what>/
    participant DB as MySQL

    A->>UI: overview · finance · retention · support, period (preset or Jalali range)
    UI->>API: GET ?preset= | ?from=&to=
    API->>DB: approved payments (revenue), orders (coverage, discounts), services, CRM profiles / cases, ticket events
    Note over API: computed on request — nothing is written
    API-->>UI: figures + series (Jalali months)
    A->>UI: Export
    UI->>API: GET financial/?export=csv|xlsx&lang=
    API-->>A: file (UTF-8 BOM CSV / RTL Excel in fa)
```

## 13. Domain change (Settings → Domain & Cloudflare)

```mermaid
sequenceDiagram
    autonumber
    actor A as Super admin
    participant UI as /panel/settings/domain
    participant API as web (settings_app/domain.py)
    participant CF as Cloudflare API
    participant DNS as Public DoH resolvers
    participant H as Host (scripts/domain.sh, cron 1 min)
    participant N as nginx
    participant C as certbot

    A->>UI: new domain (+ www), zone or manual DNS
    UI->>API: POST domain/start/
    API->>CF: zone check: list records + temporary TXT create / delete (DNS edit?)
    API->>CF: A @ / www / mail → server IP (DNS-only)
    UI->>API: Check DNS
    API->>DNS: name → A ? (must be this IP)
    UI->>API: Request certificate
    API->>H: backups/.domain-request.json {cert}
    H->>C: certbot certonly --webroot (@, www, mail)
    H->>H: mail server: DKIM key for the new domain (selector mail)
    H-->>API: .domain-status.json (ok + expiry | reason) + DKIM record
    API->>CF: MX, SPF (ip4), DMARC p=none, DKIM TXT
    API->>DNS: MX / TXT answered? (apply waits)
    A->>UI: Switch (confirm)
    UI->>API: POST domain/<id>/apply/
    API->>H: request {apply, old, new, transition_days}
    H->>N: render nginx/domain/active.conf (new + old → 301), nginx -t, reload
    H->>H: .env DOMAIN / ALLOWED_HOSTS / CSRF / PUBLIC_BASE_URL / MAIL_DOMAIN / sender
    H->>H: recreate app containers (web + daphne rolling, celery, bots, mailserver)
    H->>N: verify https://new/api/v1/health/ = 200, old → 301, mail server = mail.new
    alt any step fails
        H->>H: restore .env + nginx config + containers
        H-->>API: status: rolled back + reason
    else ok
        H-->>API: status ok
        API->>API: site_config.site_domain, Telegram menu button, audit
    end
    Note over API: beat (5 min): transition over → request {retire}
    H->>N: old domain removed, .env without the old names
    opt rollback (panel or ./scripts/domain.sh rollback)
        H->>N: same switch back to the previous domain
    end
```

## 13b. Access mode switch (Direct / Cloudflare proxy / Iran tunnel)

```mermaid
sequenceDiagram
    autonumber
    actor A as Super admin
    participant UI as Domain & Cloudflare page
    participant W as celery_worker (access_switch_task)
    participant CF as Cloudflare API
    participant DNS as public DoH
    participant P as new path (Iran IP / this server / CF edge)

    A->>UI: mode (+ Iran IPs, tunnel sources, PROXY ports)
    UI->>W: request_switch(mode)
    W->>CF: zone + proxy mode: SSL/TLS = Full (strict) (set, else stop)
    W->>P: HTTPS for the domain (SNI) → 200 + our cert + X-Caspin-Instance
    alt path broken
        W-->>UI: failed (nothing changed)
    else ok
        W->>CF: A @ / www → target (mail.* never), previous records saved
        W->>DNS: until public DNS answers the target
        W->>P: check again
        alt broken
            W->>CF: put the previous records back
            W-->>UI: reverted + reason
        else ok
            W-->>UI: ok — mode shown in the header
        end
    end
```

## 14. Deploy (`./update.sh`)

```mermaid
sequenceDiagram
    autonumber
    actor O as Operator (shell or panel Update button)
    participant H as Host (update.sh / watch-update.sh)
    participant D as Docker
    participant DB as MySQL
    participant N as nginx

    alt panel Update button
        O->>H: sentinel file → watch-update.sh (cron, 2 min) runs update.sh
    else shell
        O->>H: ./update.sh
    end
    H->>DB: mysqldump → backups/pre-update-<ver>-<ts>.sql.gz
    H->>D: tag running app images :rollback
    H->>H: git pull
    H->>D: build images (backend, frontend-user, frontend-admin, nginx)
    H->>D: one-off container (new image): migrate + seed + collectstatic
    Note over D: old release still serving — migrations must be backward compatible
    loop web, daphne, frontend_user, frontend_admin
        H->>D: start new container next to the old one
        D-->>H: healthy (compose healthcheck)
        H->>D: remove the old container
        Note over N: nginx re-resolves names every 2 s and retries —<br/>no failed requests
    end
    H->>D: up the rest only where changed (celery, bots, mail) — never two beats/bots
    H->>N: nginx reload, Docker cleanup (keep :latest + :rollback)
    H-->>O: "now on version X"
    opt something is wrong
        O->>H: ./update.sh --rollback (images, restore the dump if a migration must be undone)
    end
```

Release routine (development side): tests on the isolated stack
(`./scripts/test.sh`), bump `VERSION`, PROGRESS entry, commit, tag `vX.Y.Z`,
push, `./update.sh`, GitHub release ([development.md](development.md)).


## 5d. Super Admin deletes (voids) a transaction → restore

```mermaid
sequenceDiagram
    autonumber
    actor SA as Super Admin
    participant TX as /panel/transactions
    participant API as web admin/transactions/
    participant PG as PasarGuard
    participant DB as MySQL

    SA->>TX: Delete (row or bulk)
    TX->>API: GET {id}/delete-preview/
    API-->>TX: TX number, amount, linked order + service, choices keep | disable | delete
    SA->>TX: reason (required) + choice (default keep)
    TX->>API: POST {id}/delete/ {reason, service_action}
    API->>API: Super Admin? (else 403) · reason? · not already deleted?
    API->>API: service_action required (missing / unknown → 400)
    API->>DB: BEGIN · lock payment + order
    opt disable / delete
        API->>PG: PUT user status=disabled  /  DELETE user
        API->>PG: GET user (disabled? / 404?) — verify
        alt refused / error / not verified
            API->>DB: ROLLBACK · AuditLog payment.void_failed (+ PasarGuard calls)
            API-->>TX: 502 "PasarGuard: … — nothing was deleted"
        end
        API->>DB: service row disabled / deleted
    end
    API->>DB: order → cancelled (choice, or the payment was still pending) · drop unapplied renewal
    API->>DB: payment.voided_at / voided_by / void_reason / void_service_action
    API->>DB: AuditLog payment.voided (who, reason, amount, TX, order, choice)
    API-->>TX: row hidden; cards, Accounting, Analytics, reports no longer count it
    SA->>TX: Show deleted → Restore (≤ 30 days)
    TX->>API: POST {id}/restore/
    API->>DB: clear voided_*; order status back (lapsed pending → expired)
    API->>DB: AuditLog payment.restored
```

## 5e. Staff page → Group manager role (v1.25.2)

```mermaid
sequenceDiagram
    autonumber
    actor S as Staff with roles.manage
    participant P as Panel (Roles & staff)
    participant API as admin/staff/
    participant M as agency.managers
    S->>P: edit staff, role = Group manager
    P->>API: GET staff/group-manager-options/ (groups + PasarGuard roles, owner roles left out)
    S->>P: tick groups, allowed roles per group, cap
    P->>API: PATCH staff/<id>/ {role, group_manager: {assignments, max_unapproved_gb}}
    API->>M: sync_from_staff (same transaction as the staff save)
    alt role is Group manager
        M->>M: link / create GroupManager (same username + password hash)
        M->>M: _clean_assignments (owner role / unknown group → 400, nothing saved)
        M-->>API: manager + warnings (no_group / no_role)
    else role removed / superadmin
        M->>M: unlink, disable manager, end its portal sessions, audit agency.manager.unlinked
    end
    API-->>P: staff row incl. group_manager {assignments, cap, warnings}
    Note over P: Agency → Group managers edits the same record — both pages show the same groups
```

## 15. Disk full protection (v1.25.2)

```mermaid
sequenceDiagram
    autonumber
    participant B as celery beat
    participant W as worker (ops)
    participant H as host cron (disk-report.sh)
    participant T as Telegram (backup chat + monitoring staff)
    loop every 5 min
        B->>W: resource_sample_task
        W->>W: check_disk_alert() before any DB write
        alt ≥ 80 % (warn) / ≥ 90 % (critical), new level or repeat due
            W->>T: alert + biggest folders
        else back below 77 %
            W->>T: back to normal
        end
    end
    H->>H: 03:17 daily: du of folders / volumes / binlogs → backups/.disk-report.json
    B->>W: daily disk report
    W->>T: only if above warn, growth ≥ 1 GB/day, or report missing / stale
```

## 16. Discount code at checkout (v1.26)

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer (site / Mini App / bot)
    participant API as orders API / bot
    participant E as crm.discounts.evaluate
    participant O as orders.create_order
    participant M as SMS matcher / card review
    C->>API: plan (+ volume / service) + code
    API->>E: quote (POST /orders/quote/ or the bot's code step)
    alt refused
        E-->>C: reason in Persian / English (expired, not for this plan, not for you, used up, …)
    else ok
        E-->>C: original · discount · final
        C->>API: confirm
        API->>O: create_order(discount_code)
        O->>E: evaluate again (limits are checked at this moment)
        O->>O: amount = original − discount; amount_unique = amount + surcharge (unique)
        O-->>C: invoice: pay amount_unique (shows original, code, discount)
        C->>M: card-to-card / SMS for amount_unique
        M->>O: matches amount_unique → paid (the code's use is now counted as used)
    end
```

