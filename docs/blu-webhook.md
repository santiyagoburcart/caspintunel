# Blu Bank deposits — collector webhook (v1.31)

An Iran-side collector reads the Blu account history and pushes deposits to the
panel. The panel stores each one once and auto-confirms an order only with the
same exact-amount rule as the bank SMS (`payments_sms/matching.py`).

## Settings (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `BLU_PUSH_SECRET` | empty | HMAC-SHA256 secret shared with the collector, at least 32 characters. Empty or shorter → the webhook answers 503 (feature off). Changing it needs `docker compose up -d` of the backend containers (a restart does not reload `.env`). |
| `BLU_LATE_GRACE_MINUTES` | 30 | how long after an order's reservation ended a deposit may still pay it (fallback — see below) |
| `BLU_COLLECTOR_POLL_SECONDS` | 45 | the collector's own poll interval, shown on the tab (information only) |
| `BLU_SSH_HOST` | empty | SSH host (alias in the mounted ssh config) for the service check; empty = off |
| `BLU_COLLECTOR_SERVICE` | `blu-collector.service` | systemd unit checked |

**Panel overrides (v1.32).** On the «واریزهای بلو» tab a Super Admin sets the SSH check
interval (`blu_ssh_check_minutes`, default 5, min 1), the alert threshold "no successful poll for N
minutes" (`blu_poll_stale_minutes`, default 10, min 2) and the late grace (`blu_late_grace_minutes`). They are stored in the `setting` table, win over
`.env` and apply without a restart (the tab says which source each value comes from).

## Service check over SSH (v1.31.1)

Every `blu_ssh_check_minutes` (default 5) the Celery worker runs exactly
`systemctl is-active <unit>; journalctl -u <unit> --since -10min --no-pager -o short-iso -q`
on `BLU_SSH_HOST` (BatchMode, strict host key). Files mounted read-only into `celery_worker`
(`docker-compose.prod.yml`): `BLU_SSH_KEY_FILE` → `/run/blu-ssh/id_ed25519_iran`,
`BLU_SSH_KNOWN_HOSTS` → `/run/blu-ssh/known_hosts`, `BLU_SSH_CONFIG_FILE` → `/run/blu-ssh/config`
(defaults: the files in `/root/.ssh`). The tab shows active / inactive, last check and the last
error line (secrets and card numbers masked).

## Request

`POST /api/v1/payments/blu/webhook/` — no account, throttle scope `blu_webhook` (120/min).

| Header | Value |
|---|---|
| `X-Blu-Timestamp` | unix seconds; refused when more than 300 s from the server clock |
| `X-Blu-Signature` | `hex(HMAC_SHA256(secret, "<timestamp>." + raw body bytes))` |
| `X-Blu-Batch-Id` | uuid, logged and kept as "last batch" |

Body: `{"source": "blu", "batch_id": "…", "sent_at": "…", "items": [ … ]}`. Per item only
`id`, `amount_irr` and `timestamp` (unix seconds, UTC) are required; also read:
`direction`, `type`, `jalali_date`, `time`, `counterparty_name`, `payer_card`,
`payer_card_last4`, `receipt` (شماره پیگیری), `reference` (شماره مرجع),
`account_iban`, `balance_after_irr`. The whole item is kept in `raw` with every
full card number masked. `items: []` is a heartbeat.

## Responses

| Status | When |
|---|---|
| 200 `{"ok": true, "received": n, "created": m}` | signature valid and JSON well-formed — also for retries (`created: 0`) and for batches with bad items (those are logged and skipped) |
| 400 | body is not JSON or has no `items` list |
| 403 | timestamp missing / not digits / too far off, or signature mismatch |
| 503 | `BLU_PUSH_SECRET` not configured |

## Matching (Celery, after commit)

1. `amount_irr` not a multiple of 10 → stays `unmatched` ("not a whole toman").
2. Order `pending_payment` with `amount_unique_lock == amount_irr / 10`, and the deposit
   between `created_at − 2 min` and `unique_expire_at + BLU_LATE_GRACE_MINUTES` →
   approved (`blu_auto`, confirmed by system), fulfilled, `blu_approved` live event.
   Outside that window (the unique amount was reused) → stays `unmatched`.
3. The same amount already paid inside that window (e.g. by the iPhone SMS) → `duplicate`.
4. Within ±20 % (or equal after ×10 / ÷10) of an open invoice → pending `blu_mismatch`
   payment in the Payments queue, Telegram to staff with `payment.approve`; never approved
   automatically.
4a. (v1.32, widened v1.44.1, checked before 4) Within ±`rounded_max_toman` (default 2,000 T) of exactly
   one pending invoice (order or agency payment), inside the same window, and the deposit has not already
   paid something (exact or rounded) → approved with `auto_rule = rounded` (amount = what was paid,
   `shortfall` = invoice − paid, negative = paid more), Telegram «کمتر X» / «بیشتر X» + `rounded_approved`
   live event. BELOW the invoice it also needs evidence: a receipt for that order or a payer card (last 4)
   that paid one of their orders before. ABOVE needs none. Otherwise step 4 as before,
   with the evaluated conditions on the pending payment. See `payments_sms/rounded.py`.
4b. (v1.34) **Agency payments** share the unique-amount pool with customer orders. Customer orders are checked
   first; a deposit equal to an open customer order AND an open agency payment is never auto-approved — both go to
   review (`agency.billing.hold_ambiguous`, payment `pending_review`, live `agency_mismatch`). No customer order took
   it → an agency payment of exactly that amount inside its window is approved (`billing.match_deposit` →
   `billing.approve_payment`, method `blu_auto`; already paid → `duplicate`). Rounded and near-miss rules apply to
   agency payments the same way. Agency money never becomes a customer `Payment` (separate revenue).
5. Otherwise `unmatched`. Staff link it from Payments → «واریزهای بلو» (v1.42.2, `payments_sms/blu_link.py`):
   `POST …/blu-transactions/<id>/attach/ {ref, confirm}` (`payment.approve`) — `ref` = an order id, `TX-`, `MI-` (manual
   invoice), `INV-` / `AP-` (agency); `GET …/<id>/candidates/?q=` suggests targets (amount ±20 %, ±3 days, payer name,
   tracking / reference number). **Not paid yet** → approved with the deposit (a different amount needs `confirm`; a
   shorter one records the shortfall). **Already approved** (manual invoice, staff receipt, SMS) → **link only**: status
   `linked` («متصل به پرداخت موجود»), the payment shows the deposit (payer, card, tracking / reference) — no new approval,
   nothing counted twice (Accounting / Transactions / Analytics count payments, never deposits). `POST …/<id>/unlink/`
   (Super Admin, audit `blu.unlinked`) undoes a link-only connection; an approval is undone by voiding the payment.
6. **Auto-link** (v1.42.2, `payments_sms/signals.py`): when a payment / agency payment is approved by any route (not Blu,
   not cash), an `unmatched` deposit with the same tracking / reference number — else exactly ONE with the same amount
   within 24 h and the same payer name when both are known — is linked (link only). `manage.py link_blu_deposits
   [--dry-run]` runs the same rule over the last 60 days. Match notes are stored in English and shown in Persian
   (`blu_notes.note_fa`).

The deposit's reference / tracking numbers are on the payment too, so a receipt with the
same document number on another order shows the "duplicate document" warning.

## Liveness (v1.33.1)

A batch only arrives when there are deposits, so "no batch for N minutes" is not an outage (the old
`BLU_STALE_MINUTES` alert fired every quiet night and is retired). Health now comes from the SSH check
(`blu_service.py`, same single read-only command):

| Signal (journal of the last 10 min) | Alert |
|---|---|
| service not `active` | «سرویس جمع‌کننده … فعال نیست» |
| a poll / login line mentioning session, expired, login, OTP, 401, unauthorized, token | «نشست بلو منقضی شده — دوباره وارد شوید» |
| last "poll ok" line older than `blu_poll_stale_minutes` (default 10) | «… دقیقه است حساب را با موفقیت نخوانده» |
| no "poll ok" lines at all yet: ≥ 80 % of the expected polls in the window are "poll error" (45 s poll → 11) | same |
| SSH to the Iran server failed 3 checks in a row | «اتصال SSH … ناموفق» |

One alert per incident, one silent "healthy again". Push failures to our webhook never count.
How long the account has had no deposit is shown on the tab and on Monitoring as neutral info
(«X ساعت بدون واریزی»).

**Line the collector should print once per successful poll** (it does not today — until it does,
the inference from "poll error" lines is used):

```
poll ok new=<number of new items in this poll>
```

e.g. `console.log(`poll ok new=${fresh.length}`)` right after a successful `/transactions` call,
whether or not it found anything. Only the words `poll ok` matter (case-insensitive); the time is
taken from the journal. From the first such line on, "no successful poll for N minutes" is the
liveness signal.
