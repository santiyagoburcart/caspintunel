"""Disk protection (v1.25.2, after the 2026-10-28 disk-full outage).

* `check_disk_alert()` — every resource sample (5 min): Telegram alert when the disk
  passes `disk_alert_warn_percent` (80) and again at `disk_alert_crit_percent` (90);
  repeated while it stays there (warn every 6 h, critical every hour) and a
  "recovered" note once it drops back below warn − 3. Runs BEFORE anything is
  written to the database, and its own state lives in Redis with an in-process
  fallback, so it still works while MySQL / Redis cannot write.
* `daily_report()` — reads `backups/.disk-report.json`, written once a day by the
  host (`scripts/disk-report.sh`: biggest folders, Docker volumes, MySQL binlogs),
  adds day-over-day growth, and is shown on the Monitoring page. A Telegram
  summary is sent when the disk is above warn, something grew ≥ 1 GB in a day, or
  the host report is missing / stale.

Recipients: the backup-bot chat, plus every active staff with a linked Telegram
who is superadmin or holds `monitoring.view` (via the sales bot).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone as dt_tz
from pathlib import Path

import psutil
from django.conf import settings
from django.core.cache import cache

log = logging.getLogger("caspintunel")

STATE_KEY = "ops:disk_alert"
REPEAT = {1: 6 * 3600, 2: 3600}            # seconds between repeats per level
HYSTERESIS = 3.0
GROWTH_ALERT_BYTES = 1024 ** 3             # 1 GB / day
REPORT_STALE = timedelta(hours=36)
_mem_state: dict = {}                      # used when Redis refuses writes


def thresholds() -> tuple[float, float]:
    from apps.settings_app.utils import get_setting

    try:
        warn = float(get_setting("disk_alert_warn_percent", 80))
        crit = float(get_setting("disk_alert_crit_percent", 90))
    except (TypeError, ValueError):
        warn, crit = 80.0, 90.0
    warn = min(max(warn, 1.0), 99.0)
    crit = min(max(crit, warn), 99.5)
    return warn, crit


def disk_usage() -> dict:
    try:
        du = psutil.disk_usage(settings.RESOURCE_DISK_PATH)
    except OSError:
        du = psutil.disk_usage("/")
    return {"total": du.total, "used": du.used, "free": du.free, "percent": round(du.percent, 1)}


def level_for(percent: float, prev_level: int, warn: float, crit: float) -> int:
    if percent >= crit:
        return 2
    if percent >= warn:
        return 1
    # hysteresis: stay at warn until clearly below it
    if prev_level and percent >= warn - HYSTERESIS:
        return 1
    return 0


def _get_state() -> dict:
    try:
        st = cache.get(STATE_KEY)
        if st is not None:
            return st
    except Exception:  # noqa: BLE001 - Redis may be read-only while the disk is full
        pass
    return dict(_mem_state) or {"level": 0, "sent_at": 0}


def _set_state(st: dict) -> None:
    _mem_state.clear()
    _mem_state.update(st)
    try:
        cache.set(STATE_KEY, st, None)
    except Exception:  # noqa: BLE001
        pass


def _fmt(n) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def recipients() -> list[int]:
    from apps.accounts.models import Staff

    ids = []
    for s in Staff.objects.filter(is_active=True, telegram_id__isnull=False).select_related("role"):
        if s.is_superadmin or (not s.is_group_manager and s.has_perm("monitoring.view")):
            ids.append(s.telegram_id)
    return ids


def send(text: str) -> int:
    """Best effort to the backup chat + linked monitoring staff. Returns deliveries."""
    sent = 0
    try:
        from apps.telegram.config import backup_client, get_bot_config
        from apps.telegram.models import BotType

        cfg = get_bot_config(BotType.BACKUP)
        client = backup_client()
        if client and cfg and cfg.backup_chat_id:
            client.send_message(cfg.backup_chat_id, text, parse_mode=None)
            sent += 1
    except Exception as exc:  # noqa: BLE001
        log.warning("disk alert to backup chat failed: %s", exc)
    try:
        from apps.telegram.config import sales_client

        client = sales_client()
        if client is not None:
            for tg in recipients():
                try:
                    client.send_message(tg, text, parse_mode=None)
                    sent += 1
                except Exception as exc:  # noqa: BLE001
                    log.warning("disk alert to staff %s failed: %s", tg, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("disk alert (staff) failed: %s", exc)
    return sent


def _top_lines(n: int = 5) -> str:
    rep = load_report()
    if not rep:
        return ""
    rows = sorted(rep.get("items", []), key=lambda i: -int(i.get("bytes") or 0))[:n]
    if not rows:
        return ""
    lines = "\n".join(f"• {r['label']}: {_fmt(r['bytes'])}" for r in rows)
    return f"\n\nBiggest (host report {rep.get('generated_at', '?')}):\n{lines}"


def check_disk_alert(now: float | None = None, usage: dict | None = None) -> dict:
    now = time.time() if now is None else now
    du = usage or disk_usage()
    warn, crit = thresholds()
    st = _get_state()
    prev = int(st.get("level") or 0)
    lvl = level_for(du["percent"], prev, warn, crit)
    due = lvl > prev or (lvl and now - float(st.get("sent_at") or 0) >= REPEAT[lvl])
    recovered = prev and not lvl
    result = {"percent": du["percent"], "level": lvl, "previous": prev, "sent": 0}
    if not (due or recovered):
        if lvl != prev:
            _set_state({**st, "level": lvl})
        return result
    host = getattr(settings, "DOMAIN", "") or "server"
    if recovered:
        text = (f"✅ Disk back to normal on {host}: {du['percent']}% used, {_fmt(du['free'])} free "
                f"(alert level {warn:.0f}%).")
    else:
        icon, word = ("🔴", "CRITICAL") if lvl == 2 else ("🟠", "WARNING")
        text = (f"{icon} Disk {word} on {host}: {du['percent']}% used — {_fmt(du['free'])} free of "
                f"{_fmt(du['total'])} (alerts at {warn:.0f}% / {crit:.0f}%).\n"
                "When the disk is full MySQL and Redis stop accepting writes (orders, payments, bots)."
                f"{_top_lines()}")
    result["sent"] = send(text)
    _set_state({"level": lvl, "sent_at": now if not recovered else 0, "percent": du["percent"]})
    log.warning("disk alert: %s%% level %s (was %s), %s message(s)", du["percent"], lvl, prev, result["sent"])
    return result


# ------------------------------------------------------------------ daily host report
def _report_path(name: str = ".disk-report.json") -> Path:
    from .retention import backup_dir

    return backup_dir() / name


def load_report(name: str = ".disk-report.json") -> dict | None:
    try:
        return json.loads(_report_path(name).read_text())
    except (OSError, ValueError):
        return None


def _parse_ts(s) -> datetime | None:
    try:
        return datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt_tz.utc)
    except (TypeError, ValueError):
        return None


def report_snapshot(now: datetime | None = None) -> dict:
    """The daily host report + growth vs the previous one (Monitoring page)."""
    now = now or datetime.now(dt_tz.utc)
    rep, prev = load_report(), load_report(".disk-report.prev.json")
    warn, crit = thresholds()
    st = _get_state()
    out = {"warn_percent": warn, "crit_percent": crit, "alert_level": int(st.get("level") or 0),
           "report": None, "stale": True}
    if not rep:
        return out
    gen = _parse_ts(rep.get("generated_at"))
    pgen = _parse_ts((prev or {}).get("generated_at"))
    before = {i["label"]: int(i.get("bytes") or 0) for i in (prev or {}).get("items", [])}
    days = ((gen - pgen).total_seconds() / 86400) if gen and pgen and gen > pgen else None
    items = []
    for i in sorted(rep.get("items", []), key=lambda x: -int(x.get("bytes") or 0)):
        b = int(i.get("bytes") or 0)
        growth = None
        if days and i["label"] in before:
            growth = round((b - before[i["label"]]) / days)
        items.append({"label": i["label"], "path": i.get("path", ""), "bytes": b, "growth_per_day": growth})
    out.update({"report": {"generated_at": gen, "disk": rep.get("disk"), "items": items[:15],
                           "docker": rep.get("docker", "")},
                "stale": gen is None or now - gen > REPORT_STALE})
    return out


def daily_report(now: datetime | None = None) -> dict:
    snap = report_snapshot(now)
    du = disk_usage()
    warn, _ = thresholds()
    reasons = []
    if snap["report"] is None:
        reasons.append("the host disk report (scripts/disk-report.sh, daily cron) is missing")
    elif snap["stale"]:
        reasons.append(f"the host disk report is stale (last {snap['report']['generated_at']:%Y-%m-%d %H:%M} UTC)")
    growing = [i for i in (snap["report"] or {}).get("items", [])
               if (i["growth_per_day"] or 0) >= GROWTH_ALERT_BYTES]
    if growing:
        reasons.append("fast growth: " + ", ".join(f"{i['label']} +{_fmt(i['growth_per_day'])}/day" for i in growing))
    if du["percent"] >= warn:
        reasons.append(f"disk at {du['percent']}% (alert level {warn:.0f}%)")
    sent = 0
    if reasons:
        text = (f"🗂 Daily disk check: {du['percent']}% used, {_fmt(du['free'])} free.\n"
                + "\n".join(f"• {r}" for r in reasons) + _top_lines())
        sent = send(text)
    return {"percent": du["percent"], "reasons": reasons, "sent": sent}
