# Flows

Sequence diagrams of the main business and operations flows, as implemented.
Mermaid source (rendered on GitHub; shown as diagram source in the admin
Documentation page). Function names point at the code.

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

## 3. Renewal

A renewal is paid like a purchase (flows 1–2) with `type=renew` on an existing
service, but it is **not applied immediately**: it waits for the end of the
current cycle so the customer loses nothing.

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant API as web
    participant W as celery_worker
    participant B as celery_beat
    participant PG as PasarGuard panel
    participant DB as MySQL

    C->>API: renew service S with plan P
    API->>DB: Order(type=renew, service=S)
    Note over C,API: payment as in flows 1–2
    W->>DB: fulfill_order → schedule_renewal:<br/>ScheduledRenewal(S, P, renewal_mode + carry_over copied from P)
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
            W->>PG: GET user (adopt it)
        end
    end
    PG-->>W: user object
    W->>DB: apply_user_to_service (mirror) → status on_hold (timed) or active
    W->>DB: order → completed, lock released, audit
    W-->>C: notify site + email, bot gets the QR photo + link
    Note over W,PG: PanelUnavailable → Celery retry,<br/>beat retries paid-but-unprovisioned orders every 10 min
```

Add-on volume orders call `add_service_data_limit` instead (panel first, then
mirror). Every `service_sync_interval_minutes` beat dispatches
`sync_service_task` per live service to refresh usage, expiry and online state.

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
    Bot->>DB: ensure_bot_user(telegram_id)
    alt first contact
        DB-->>Bot: new User(source=bot) with random username + password
    end
    Bot->>T: getChatMember for each required channel
    alt missing channel or no phone
        Bot-->>U: join channels / share contact (asked again on any message)
        U->>Bot: shares contact
        Bot->>DB: link_telegram_phone — matches a site account?<br/>→ merge bot account into it, revoke unverified site password
    end
    Bot-->>U: main menu (screen edited in place)

    U->>T: opens the Mini App
    T->>API: SPA loads, POST /auth/telegram/miniapp/ {initData}
    API->>API: HMAC check with the sales-bot token, auth_date ≤ max age
    API->>DB: ensure_bot_user(telegram_id) — link or create (+ phone gate)
    API-->>T: JWT pair — the SPA never shows a login form inside Telegram
```

## 7. Deploy (`./update.sh`)

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
