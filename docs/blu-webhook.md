# Blu Bank deposits — collector webhook (v1.31)

An Iran-side collector reads the Blu account history and pushes deposits to the
panel. The panel stores each one once and auto-confirms an order only with the
same exact-amount rule as the bank SMS (`payments_sms/matching.py`).

## Settings (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `BLU_PUSH_SECRET` | empty | HMAC-SHA256 secret shared with the collector, at least 32 characters. Empty or shorter → the webhook answers 503 (feature off). Changing it needs `docker compose up -d` of the backend containers (a restart does not reload `.env`). |
| `BLU_LATE_GRACE_MINUTES` | 30 | how long after an order's reservation ended a deposit may still pay it (fallback — see below) |
| `BLU_STALE_MINUTES` | 360 | no batch for this long → one "collector offline" alert. The collector sends nothing when there are no new deposits, so keep this long. (fallback — see below) |
| `BLU_COLLECTOR_POLL_SECONDS` | 45 | the collector's own poll interval, shown on the tab (information only) |
| `BLU_SSH_HOST` | empty | SSH host (alias in the mounted ssh config) for the service check; empty = off |
| `BLU_COLLECTOR_SERVICE` | `blu-collector.service` | systemd unit checked |
| `BLU_ERROR_REPEAT` | 3 | journal error lines within 10 min that count as "repeating" |

**Panel overrides (v1.32).** On the «واریزهای بلو» tab a Super Admin sets the SSH check
interval (`blu_ssh_check_minutes`, default 5, min 1), the offline threshold (`blu_stale_minutes`)
and the late grace (`blu_late_grace_minutes`). They are stored in the `setting` table, win over
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
4a. (v1.32, checked before 4) Slightly BELOW exactly one pending invoice — shortfall ≤
   max(`rounded_max_toman` 2,000 T, `rounded_max_percent` 1 %), inside the same window — AND the
   customer uploaded a receipt for that order or the payer card's last 4 digits paid one of
   their orders before → approved with `auto_rule = rounded` (amount = what was paid,
   `shortfall` recorded), Telegram + `rounded_approved` live event. Otherwise step 4 as before,
   with the evaluated conditions on the pending payment. See `payments_sms/rounded.py`.
5. Otherwise `unmatched`. Staff can attach it to an order from Payments → «واریزهای بلو»
   (`POST /api/v1/admin/payments/blu-transactions/<id>/attach/`, `payment.approve`).

The deposit's reference / tracking numbers are on the payment too, so a receipt with the
same document number on another order shows the "duplicate document" warning.
