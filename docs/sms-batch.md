# SMS offline queue (iPhone Shortcut v1.1+)

iOS Shortcuts has no try/catch: when *Get Contents of URL* fails ("The network
connection was lost") the shortcut just stops — v1.0.0 lost that bank SMS. v1.1.0
**saves first, sends after**:

1. Message automation → `{text, sender, received_at = now (ISO 8601)}` → JSON →
   **Append to Text File** `CaspinSMS-queue.txt` (Shortcuts folder) — before any network call.
2. The whole queue file → `POST /api/v1/payments/sms/inbound-batch/` (`X-Device-Token`).
3. Answer `"result": "stored"` → the shortcut removes exactly the text it sent (an SMS
   appended meanwhile stays). Anything else (no network, HTTP error, wrong token) →
   the queue stays and goes with the next SMS or the home-screen button.
4. Run without SMS input (home-screen **ارسال صف پیامک**) = flush only, no alert.

## Server (`apps/payments_sms/batch.py`)

| | |
|---|---|
| Body | JSON array, or JSON objects one after another (NDJSON; BOM, blank lines, missing newlines, pretty-printed objects are fine), raw or as a multipart file. At most 1000 per upload. |
| Idempotent | `dedupe_key = sha256(device \| received_at (UTC, seconds) \| text)`, unique in `sms_message` — re-sending the queue (or two parallel uploads) never stores, matches or approves an SMS twice. |
| Time | matched at `received_at` (`matching.open_orders_at`): a pending order, or one that **expired while the SMS was queued** (deadline and close time after the SMS); never an order created after the SMS (5 min clock skew). All other rules unchanged: unit-aware, exact amount only, near-miss → manual review. A late-matched expired order is paid without taking back its unique amount if another order holds it now. |
| Refused | `received_at` > 5 min in the future (phone clock) or > 72 h old (confirm by hand), missing / not ISO 8601, empty text, not JSON — stored in the SMS log as `refused (batch upload): <reason>` (deduped too), never matched. |
| Answer | `{"ok": true, "result": "stored", "count", "new", "duplicate", "refused", "matched", "results": [{index, status, message_id, matched, order_id, reason, late}]}` — `ok` only when every item reached a final state. |
| SMS log | `received_at` (on the phone) vs `uploaded_at` (reached the server); **delivered late** badge when > 2 min apart. |

The old `POST /payments/sms/inbound/` (Android app, Shortcut 1.0.0) is unchanged.
