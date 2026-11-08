"""Web Push (v1.33): browser notifications while the page is closed.

Keys: VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY (base64url, P-256) + VAPID_SUBJECT in .env; empty =
feature off (the UI hides the switch). Browsers subscribe through a tiny service worker that
only handles `push` and `notificationclick` (`push-sw.js`, registered with a scope no page
uses, so it never serves or caches pages — the v1.28 cleanup of old caching workers stays).

Sending happens in Celery (`send_push_task`); a 404 / 410 from the push service deletes the
subscription. Payloads carry only a title, a short body, a URL inside our site and a tag.
"""
from __future__ import annotations

import hashlib
import json
import logging

from django.conf import settings
from django.utils import timezone

log = logging.getLogger("caspintunel")

MAX_BODY = 180


def public_key() -> str:
    return (getattr(settings, "VAPID_PUBLIC_KEY", "") or "").strip()


def enabled() -> bool:
    return bool(public_key() and (getattr(settings, "VAPID_PRIVATE_KEY", "") or "").strip())


def endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()


def save_subscription(data: dict, *, user=None, staff=None, reseller: str = "", user_agent: str = ""):
    """{endpoint, keys: {p256dh, auth}} from PushManager.subscribe(). Re-subscribing the same
    browser moves the row to the current owner."""
    from .models import PushSubscription

    endpoint = str((data or {}).get("endpoint") or "").strip()
    keys = (data or {}).get("keys") or {}
    if not endpoint.startswith("https://") or len(endpoint) > 2000 or not keys.get("p256dh") or not keys.get("auth"):
        raise ValueError("invalid push subscription")
    sub, _ = PushSubscription.objects.update_or_create(
        endpoint_hash=endpoint_hash(endpoint),
        defaults={"endpoint": endpoint, "p256dh": str(keys["p256dh"])[:255], "auth": str(keys["auth"])[:255],
                  "user": user, "staff": staff, "reseller": (reseller or "")[:255], "user_agent": (user_agent or "")[:255], "failures": 0})
    return sub


def delete_subscription(endpoint: str, *, user=None, staff=None, reseller: str = "") -> int:
    from .models import PushSubscription

    qs = PushSubscription.objects.filter(endpoint_hash=endpoint_hash(str(endpoint or "")))
    if reseller:
        qs = qs.filter(reseller=reseller)
    else:
        qs = qs.filter(user=user) if user is not None else qs.filter(staff=staff)
    return qs.delete()[0]


def _payload(title: str, body: str, url: str = "", tag: str = "") -> dict:
    body = (body or "").strip()
    return {"title": (title or "")[:120], "body": body if len(body) <= MAX_BODY else body[:MAX_BODY] + "…",
            "url": url if (url or "").startswith("/") else "", "tag": (tag or "")[:64]}


def _queue(ids: list[int], payload: dict) -> int:
    if not ids or not enabled():
        return 0
    from django.db import transaction

    from .tasks import send_push_task

    transaction.on_commit(lambda: send_push_task.delay(ids, payload))
    return len(ids)


def push_to_user(user, title: str, body: str, url: str = "", tag: str = "") -> int:
    from .models import PushSubscription

    if user is None or not enabled():
        return 0
    ids = list(PushSubscription.objects.filter(user=user).values_list("id", flat=True))
    return _queue(ids, _payload(title, body, url, tag))


def push_to_reseller(username: str, title: str, body: str = "", url: str = "", tag: str = "") -> int:
    """v1.38.2 an agency reseller's browsers (subscribed from the /agency/ portal)."""
    from .models import PushSubscription

    if not username or not enabled():
        return 0
    ids = list(PushSubscription.objects.filter(reseller=username).values_list("id", flat=True))
    return _queue(ids, _payload(title, body, url, tag))


def push_to_staff(perm: str | None, title: str, body: str = "", url: str = "", tag: str = "",
                  staff_ids: list[int] | None = None) -> int:
    """Every active staff member with `perm` (or the given ids) and a subscription. `url` is a
    panel route ("/payments/12"); the service worker puts the admin base in front."""
    from .models import PushSubscription

    if not enabled():
        return 0
    qs = PushSubscription.objects.filter(staff__is_active=True).select_related("staff", "staff__role")
    if staff_ids is not None:
        qs = qs.filter(staff_id__in=staff_ids)
    else:
        # v1.47: a store's event reaches only that store's staff; ours only our staff (Staff.tenant NULL)
        from apps.tenancy.context import store_id

        sid = store_id()
        qs = qs.filter(staff__tenant_id=sid) if sid is not None else qs.filter(staff__tenant__isnull=True)
    ids = [s.id for s in qs if perm is None or s.staff.has_perm(perm)]
    return _queue(ids, _payload(title, body, url, tag))


def send_now(sub_ids: list[int], payload: dict) -> dict:
    """The Celery side: one request per subscription; dead ones are removed."""
    from .models import PushSubscription

    if not enabled():
        return {"skipped": "disabled"}
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:            # dependency missing in this image
        log.warning("pywebpush not installed — web push skipped")
        return {"skipped": "no library"}
    ok = gone = failed = 0
    claims = {"sub": getattr(settings, "VAPID_SUBJECT", "") or f"mailto:admin@{settings.DOMAIN}"}
    for sub in PushSubscription.objects.filter(id__in=sub_ids):
        try:
            webpush(subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                    data=json.dumps(payload), vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims=dict(claims), ttl=3600, timeout=10)
            PushSubscription.objects.filter(pk=sub.pk).update(last_ok_at=timezone.now(), failures=0)
            ok += 1
        except WebPushException as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if code in (404, 410):
                sub.delete()
                gone += 1
            else:
                PushSubscription.objects.filter(pk=sub.pk).update(failures=sub.failures + 1)
                failed += 1
                log.warning("web push %s failed: %s", sub.pk, str(exc)[:200])
        except Exception as exc:  # noqa: BLE001 — network: try next time
            failed += 1
            log.warning("web push %s error: %s", sub.pk, str(exc)[:200])
    return {"ok": ok, "gone": gone, "failed": failed}
