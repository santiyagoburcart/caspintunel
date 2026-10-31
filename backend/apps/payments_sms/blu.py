"""Blu Bank deposits pushed by the Iran-side collector.

The collector POSTs signed batches to /api/v1/payments/blu/webhook/:
  X-Blu-Timestamp  unix seconds (±300 s of our clock)
  X-Blu-Signature  hex(HMAC_SHA256(BLU_PUSH_SECRET, f"{timestamp}." + raw body))
Each item is stored once (`BluTransaction.bank_id`); matching runs afterwards in
Celery (`matching.match_blu_transaction`) with the same exact-amount rule as SMS.
An empty batch is a heartbeat (collector health + offline alert).

Card numbers never leave this module unmasked: the collector already sends
first6******last4, and anything that still looks like a full card number in the
item is masked before it is stored.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .checks import normalize_ref
from .models import BLU_CREDIT, BluCollector, BluStatus, BluTransaction

log = logging.getLogger("caspintunel")

MAX_SKEW_SECONDS = 300
MIN_SECRET_LEN = 32
_CARD = re.compile(r"(?<!\d)(\d{4})[\s-]?(\d{2})(\d{2})[\s-]?(\d{4})[\s-]?(\d{4})(?!\d)")


def push_secret() -> str:
    """The shared secret, or "" when the feature is off (unset or too short)."""
    secret = (getattr(settings, "BLU_PUSH_SECRET", "") or "").strip()
    if secret and len(secret) < MIN_SECRET_LEN:
        log.error("BLU_PUSH_SECRET is shorter than %s characters — Blu webhook disabled", MIN_SECRET_LEN)
        return ""
    return secret


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def verify(secret: str, timestamp: str | None, signature: str | None, body: bytes, now: float | None = None) -> str:
    """"" when the request is authentic, else a short reason (for the log, never the secret)."""
    ts = (timestamp or "").strip()
    if not ts.isdigit():
        return "timestamp missing or not digits"
    if abs((now if now is not None else time.time()) - int(ts)) > MAX_SKEW_SECONDS:
        return "timestamp outside ±300 s"
    sig = (signature or "").strip().lower()
    if not sig or not hmac.compare_digest(sign(secret, ts, body), sig):
        return "signature mismatch"
    return ""


# --- masking ------------------------------------------------------------------------
def mask_card(value) -> str:
    """first6******last4 — whatever the input (full number, already masked, spaced)."""
    s = str(value or "").strip()
    digits = re.sub(r"\D", "", s)
    if "*" in s and len(digits) >= 10:
        return f"{digits[:6]}******{digits[-4:]}"
    if len(digits) >= 16:
        return f"{digits[:6]}******{digits[-4:]}"
    if len(digits) >= 4:
        return "******" + digits[-4:]
    return ""


def _mask_text(text: str) -> str:
    return _CARD.sub(lambda m: f"{m.group(1)}{m.group(2)}******{m.group(5)}", text)


def mask_raw(value):
    """The item as stored in `raw`: every full card number masked (description, card lists…)."""
    if isinstance(value, str):
        return _mask_text(value)
    if isinstance(value, list):
        return [mask_raw(v) for v in value]
    if isinstance(value, dict):
        return {k: mask_raw(v) for k, v in value.items()}
    return value


# --- one item -----------------------------------------------------------------------
class BadItem(ValueError):
    pass


def _int(value, name) -> int:
    if isinstance(value, bool):
        raise BadItem(f"{name} is not a number")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    raise BadItem(f"{name} is not a whole number")


def _str(item: dict, key: str, size: int) -> str:
    v = item.get(key)
    return "" if v is None else str(v).strip()[:size]


def fields_from_item(item) -> dict:
    """Validated model fields for one item; BadItem when id / amount_irr / timestamp is unusable."""
    if not isinstance(item, dict):
        raise BadItem("item is not an object")
    bank_id = str(item.get("id") or "").strip()
    if not bank_id or len(bank_id) > 255:
        raise BadItem("id missing or longer than 255")
    amount = _int(item.get("amount_irr"), "amount_irr")
    ts = _int(item.get("timestamp"), "timestamp")
    try:
        occurred = datetime.fromtimestamp(ts, tz=dt_timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise BadItem("timestamp out of range") from exc
    card = mask_card(item.get("payer_card")) if item.get("payer_card") else ""
    last4 = re.sub(r"\D", "", str(item.get("payer_card_last4") or ""))[-4:] or (card[-4:] if card else "")
    balance = item.get("balance_after_irr")
    try:
        balance = _int(balance, "balance_after_irr") if balance is not None else None
    except BadItem:
        balance = None
    direction = _str(item, "direction", 32)
    status, note = BluStatus.UNMATCHED, ""
    if direction and direction != BLU_CREDIT:
        status, note = BluStatus.IGNORED, f"not a deposit (direction {direction})"
    elif amount <= 0:
        status, note = BluStatus.IGNORED, "amount is not positive"
    return dict(
        bank_id=bank_id, amount_irr=amount,
        amount_toman=amount // 10 if amount > 0 and amount % 10 == 0 else None,
        occurred_at=occurred, direction=direction, type_label=_str(item, "type", 64),
        jalali_date=_str(item, "jalali_date", 16), time_str=_str(item, "time", 16),
        payer_name=_str(item, "counterparty_name", 128), payer_card=card, payer_last4=last4,
        receipt=normalize_ref(item.get("receipt"))[:32], reference=normalize_ref(item.get("reference"))[:32],
        account_iban=_str(item, "account_iban", 34), balance_after_irr=balance,
        raw=mask_raw(item), status=status, match_note=note,
    )


# --- a batch ------------------------------------------------------------------------
def ingest_batch(items: list, *, batch_id: str = "") -> dict:
    """Store new items (existing bank_ids are left untouched), queue matching for the new
    deposits after commit, record collector health. A bad item is logged and skipped."""
    from .tasks import match_blu_transaction_task

    received, created = len(items), 0
    with transaction.atomic():
        for n, item in enumerate(items):
            try:
                fields = fields_from_item(item)
            except BadItem as exc:
                log.warning("Blu batch %s: item %s skipped: %s", batch_id or "-", n, exc)
                continue
            bank_id = fields.pop("bank_id")
            try:
                with transaction.atomic():
                    tx, made = BluTransaction.objects.get_or_create(bank_id=bank_id, defaults=fields)
            except IntegrityError:          # the same item in a concurrent retry
                continue
            except Exception:  # noqa: BLE001 — one bad row never fails the batch
                log.exception("Blu batch %s: item %s not stored", batch_id or "-", n)
                continue
            if not made:
                continue
            created += 1
            if tx.status == BluStatus.UNMATCHED:
                transaction.on_commit(lambda pk=tx.pk: match_blu_transaction_task.delay(pk))
        _record_batch(batch_id, received)
    log.info("Blu batch %s: %s item(s), %s new", batch_id or "-", received, created)
    return {"ok": True, "received": received, "created": created}


def _record_batch(batch_id: str, items: int) -> None:
    c = BluCollector.get()
    was_stale = c.stale_alerted_at is not None
    BluCollector.objects.filter(pk=c.pk).update(
        last_batch_at=timezone.now(), last_batch_id=(batch_id or "")[:64], last_items=items,
        batches=F("batches") + 1, stale_alerted_at=None)
    if was_stale:
        transaction.on_commit(_alert_back_online)


def _alert_back_online() -> None:
    from apps.common.staff_alert import alert_staff
    from apps.notifications.live import push_payments_event

    alert_staff("✅ جمع‌کنندهٔ واریزهای بلو دوباره وصل شد.\nBlu deposit collector is back online.",
                perm="payment.view")
    push_payments_event("blu_collector", connected=True)


# --- health + offline alert -----------------------------------------------------------
def stale_after() -> timedelta:
    return timedelta(minutes=max(1, int(getattr(settings, "BLU_STALE_MINUTES", 15) or 15)))


def collector_health() -> dict:
    c = BluCollector.get()
    connected = bool(c.last_batch_at and timezone.now() - c.last_batch_at <= stale_after())
    return {"enabled": bool(push_secret()), "connected": connected, "last_batch_at": c.last_batch_at,
            "last_batch_id": c.last_batch_id, "last_items": c.last_items, "batches": c.batches,
            "stale_minutes": int(stale_after().total_seconds() // 60), "service": _service()}


def _service() -> dict:
    from .blu_service import service_health

    return service_health()


def check_stale() -> str:
    """Beat task: one Telegram + panel alert when no batch arrived for BLU_STALE_MINUTES
    (only once the collector has spoken at least once; cleared by the next batch)."""
    if not push_secret():
        return "disabled"
    c = BluCollector.get()
    if c.last_batch_at is None:
        return "never"
    age = timezone.now() - c.last_batch_at
    if age <= stale_after():
        return "ok"
    if c.stale_alerted_at is not None:
        return "alerted"
    from apps.common.staff_alert import alert_staff
    from apps.notifications.live import push_payments_event

    minutes = int(age.total_seconds() // 60)
    alert_staff(f"⚠️ از جمع‌کنندهٔ واریزهای بلو {minutes} دقیقه است خبری نیست — تأیید خودکار بلو متوقف است "
                f"(پیامک آیفون همچنان کار می‌کند).\n"
                f"Blu deposit collector silent for {minutes} min — Blu auto-confirm is paused.",
                perm="payment.view", dedupe_key=f"blu:stale:{c.last_batch_at.timestamp():.0f}", ttl=86400)
    BluCollector.objects.filter(pk=c.pk).update(stale_alerted_at=timezone.now())
    push_payments_event("blu_collector", connected=False, minutes=minutes)
    return "alert"
