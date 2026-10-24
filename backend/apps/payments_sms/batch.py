"""Offline SMS queue upload (iPhone Shortcut v1.1+, docs/sms-batch.md).

The Shortcut saves every SMS to a queue file BEFORE any network call and then
uploads the whole file here; when the answer says the batch was stored it
clears the file. So this endpoint must be safe to call again and again with
the same SMS:

- body: a JSON array, or JSON objects one after another (NDJSON — tolerant of
  missing / extra newlines, BOM, and pretty-printed objects);
- every SMS gets `dedupe_key = sha256(device | received_at | text)` (unique) —
  re-sending the queue never stores, matches or approves anything twice;
- matching runs at `received_at` (matching.py), the time the phone got it;
- received_at in the future (> clock skew) or older than 72 h is refused with
  a reason and logged (so the queue can still be cleared);
- `ok: true` (+ `result: "stored"`) only when every item reached a final state
  (new / duplicate / refused-and-logged).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .matching import CLOCK_SKEW, ingest_sms
from .models import SmsMessage

log = logging.getLogger("caspintunel")

MAX_AGE = timedelta(hours=72)
MAX_ITEMS = 1000


def parse_body(raw: str) -> list:
    """JSON array or a stream of JSON values → list of items; an unreadable
    fragment becomes ("bad", text) so it is reported (and logged), not dropped."""
    raw = (raw or "").lstrip("﻿").strip()
    if not raw:
        return []
    dec, out, i, n = json.JSONDecoder(), [], 0, len(raw)
    while i < n:
        while i < n and raw[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        try:
            value, i = dec.raw_decode(raw, i)
        except ValueError:
            end = raw.find("\n", i)
            end = n if end < 0 else end
            out.append(("bad", raw[i:end]))
            i = end + 1
            continue
        out.extend(value if isinstance(value, list) else [value])
    return out


def parse_time(value):
    """ISO 8601 as iOS writes it (…+03:30, …+0330, …Z); no offset = server time zone."""
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip().replace(" ", "T", 1) if "T" not in value else value.strip()
    s = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", s)
    try:
        dt = parse_datetime(s)
    except ValueError:
        return None
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = dt.replace(tzinfo=ZoneInfo(settings.TIME_ZONE))
    return dt


def key_for(device_id, received_at, text: str) -> str:
    text = (text or "").replace("\r\n", "\n")
    stamp = received_at.astimezone(ZoneInfo("UTC")).replace(microsecond=0).isoformat() if received_at else "-"
    return hashlib.sha256(f"{device_id}\n{stamp}\n{text}".encode()).hexdigest()


def _refuse(device, *, index, reason, text="", sender="", received_at=None, key) -> dict:
    """Refused for good (bad time / bad item): logged once in the SMS log, never matched."""
    now = timezone.now()
    try:
        with transaction.atomic():
            msg = SmsMessage.objects.create(
                device=device, raw_text=(text or "")[:2000], sender=(sender or "")[:64],
                received_at=received_at or now, uploaded_at=now, dedupe_key=key,
                note=f"refused (batch upload): {reason}"[:255])
    except IntegrityError:
        return {"index": index, "status": "duplicate", "reason": reason}
    return {"index": index, "status": "refused", "message_id": msg.id, "reason": reason}


def ingest_batch(device, raw: str) -> dict:
    items = parse_body(raw)
    if len(items) > MAX_ITEMS:
        return {"ok": False, "result": "too_large", "detail": f"at most {MAX_ITEMS} SMS per upload"}
    now = timezone.now()
    todo, results = [], []
    for index, item in enumerate(items):
        if isinstance(item, tuple):
            results.append(_refuse(device, index=index, reason="not valid JSON", text=item[1],
                                   key=key_for(device.id, None, "bad:" + item[1])))
            continue
        if not isinstance(item, dict):
            results.append(_refuse(device, index=index, reason="not a JSON object", text=json.dumps(item)[:2000],
                                   key=key_for(device.id, None, "bad:" + json.dumps(item))))
            continue
        text = item.get("text") if isinstance(item.get("text"), str) else ""
        sender = item.get("sender") if isinstance(item.get("sender"), str) else ""
        at = parse_time(item.get("received_at"))
        if not text.strip():
            reason = "empty text (the automation must pass the message as Shortcut Input)"
        elif len(text) > 2000:
            reason, text = "text longer than 2000 characters", text[:2000]
        elif at is None:
            reason = "received_at missing or not ISO 8601"
        elif at > now + CLOCK_SKEW:
            reason = f"received_at {at.isoformat()} is in the future — check the phone's clock"
        elif at < now - MAX_AGE:
            reason = f"received_at {at.isoformat()} is older than 72 hours — confirm this payment by hand"
        else:
            todo.append((at, index, text, sender))
            continue
        results.append(_refuse(device, index=index, reason=reason, text=text, sender=sender, received_at=at,
                               key=key_for(device.id, at, "refused:" + text)))

    for at, index, text, sender in sorted(todo, key=lambda x: (x[0], x[1])):   # oldest SMS first
        key = key_for(device.id, at, text)
        if SmsMessage.objects.filter(dedupe_key=key).exists():
            results.append({"index": index, "status": "duplicate"})
            continue
        try:
            msg, res = ingest_sms(device=device, raw_text=text, sender=sender or None, received_at=at, dedupe_key=key)
        except IntegrityError:                       # the same SMS in a parallel upload: it was stored there
            results.append({"index": index, "status": "duplicate"})
            continue
        results.append({"index": index, "status": "new", **res})

    results.sort(key=lambda r: r["index"])
    counts = {k: sum(r["status"] == k for r in results) for k in ("new", "duplicate", "refused")}
    counts["matched"] = sum(bool(r.get("matched")) for r in results)
    if results:
        log.info("SMS batch from device %s: %s", device.id, counts)
    return {"ok": True, "result": "stored", "count": len(results), **counts, "results": results}
