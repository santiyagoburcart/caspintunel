"""Health probes for every moving part (data-model · `health_check`)."""
from __future__ import annotations

import logging
import time

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from .models import HealthCheck, HealthTarget

log = logging.getLogger("caspintunel")

# bots publish a heartbeat under these cache keys (see run_*_bot commands)
BOT_HEARTBEAT_KEYS = {
    HealthTarget.BOT_SALES: "hb:bot_sales",
    HealthTarget.BOT_BACKUP: "hb:bot_backup",
}


def _timed(fn):
    start = time.monotonic()
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001 - a probe must never raise
        ok, detail = False, str(exc)[:250]
    return ok, detail, int((time.monotonic() - start) * 1000)


def _check_site():
    # The probe talks to the app server directly (http://web:8000/...) — present
    # it the way nginx does (public Host + TLS already terminated), otherwise the
    # prod settings answer 400 (unknown host) / 301 (SSL redirect) and a healthy
    # site reports as down.
    r = requests.get(
        settings.HEALTHCHECK_SITE_URL, timeout=5, allow_redirects=False,
        headers={"Host": settings.DOMAIN, "X-Forwarded-Proto": "https"},
    )
    return r.status_code == 200, f"HTTP {r.status_code}"


def _check_mysql():
    with connection.cursor() as cur:
        cur.execute("SELECT 1")
        cur.fetchone()
    return True, "ok"


def _check_redis():
    cache.set("hb:redis-probe", "1", 10)
    return cache.get("hb:redis-probe") == "1", "ok"


def _check_worker():
    from config.celery import app

    replies = app.control.ping(timeout=2) or []
    return bool(replies), f"{len(replies)} node(s)"


def _check_beat():
    from django_celery_beat.models import PeriodicTask

    last = (
        PeriodicTask.objects.filter(enabled=True, last_run_at__isnull=False)
        .order_by("-last_run_at")
        .values_list("last_run_at", flat=True)
        .first()
    )
    if not last:
        return False, "no task has run yet"
    age = (timezone.now() - last).total_seconds()
    return age < 1800, f"last dispatch {int(age)}s ago"


def _check_bot(target):
    beat = cache.get(BOT_HEARTBEAT_KEYS[target])
    if not beat:
        return False, "no heartbeat"
    return True, "alive"


def _probe_one_panel(panel):
    from apps.panel.services import client_for

    client_for(panel).check()
    return True, "auth ok"


def _run_panel_checks():
    """One HealthCheck row per active panel + one aggregate row (panel=NULL).
    Returns the list of per-target result dicts (all target='panel')."""
    from apps.panel.models import Panel

    panels = list(Panel.objects.filter(is_active=True).order_by("id"))
    results = []
    up = 0
    worst_latency = 0
    for panel in panels:
        ok, detail, latency = _timed(lambda p=panel: _probe_one_panel(p))
        worst_latency = max(worst_latency, latency)
        up += 1 if ok else 0
        HealthCheck.objects.create(
            target=HealthTarget.PANEL, panel=panel, is_up=ok,
            latency_ms=latency, detail=detail,
        )
        results.append({"target": HealthTarget.PANEL, "panel": panel.id,
                        "panel_name": panel.name, "is_up": ok,
                        "latency_ms": latency, "detail": detail})
        if not ok:
            log.warning("health: panel %s DOWN — %s", panel.name, detail)

    if panels:
        agg_ok = up == len(panels)
        agg_detail = f"{up}/{len(panels)} panels up"
    else:
        agg_ok, agg_detail = False, "no active panel configured"
    HealthCheck.objects.create(
        target=HealthTarget.PANEL, panel=None, is_up=agg_ok,
        latency_ms=worst_latency or None, detail=agg_detail,
    )
    results.append({"target": HealthTarget.PANEL, "panel": None,
                    "is_up": agg_ok, "latency_ms": worst_latency or None,
                    "detail": agg_detail})
    return results


def _check_mail():
    if not settings.EMAIL_HOST:
        return False, "SMTP not configured"
    from django.core.mail import get_connection

    conn = get_connection(fail_silently=False)
    conn.open()
    conn.close()
    return True, "SMTP reachable"


_PROBES = {
    HealthTarget.SITE: _check_site,
    HealthTarget.MYSQL: _check_mysql,
    HealthTarget.REDIS: _check_redis,
    HealthTarget.CELERY_WORKER: _check_worker,
    HealthTarget.CELERY_BEAT: _check_beat,
    HealthTarget.BOT_SALES: lambda: _check_bot(HealthTarget.BOT_SALES),
    HealthTarget.BOT_BACKUP: lambda: _check_bot(HealthTarget.BOT_BACKUP),
    HealthTarget.MAIL: _check_mail,
}


def run_health_checks() -> list[dict]:
    results = []
    for target, probe in _PROBES.items():
        ok, detail, latency = _timed(probe)
        HealthCheck.objects.create(target=target, is_up=ok, latency_ms=latency, detail=detail)
        results.append({"target": target, "is_up": ok, "latency_ms": latency, "detail": detail})
        if not ok:
            log.warning("health: %s DOWN — %s", target, detail)
    results.extend(_run_panel_checks())
    return results


def bot_heartbeat(target: str) -> None:
    cache.set(BOT_HEARTBEAT_KEYS[target], timezone.now().isoformat(), settings.BOT_HEARTBEAT_TTL)
