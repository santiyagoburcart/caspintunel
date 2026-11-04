"""v1.39.0 container memory watch (multi-tenant Phase 0, docs/multi-tenant.md §19).

The host cron `scripts/container-stats.sh` (every 5 min, read-only `docker stats` / `inspect`, /proc) writes
`backups/.container-stats.json`; this module reads it — the app never gets the Docker socket. Used by the Monitoring
card and by `resource_sample_task` (every 5 min) for Telegram alerts (same channel as the disk alerts):

- a container of this project at ≥ CONTAINER_WARN_PCT of its memory limit;
- a container OOM-killed, or restarted since the last sample;
- host swap above SWAP_ALERT_BYTES for SWAP_ALERT_FOR;
- memory pressure (`/proc/pressure/memory` some avg60) ≥ PSI_ALERT;
- load average (15 min) above the CPU count;
- the host report itself stale (the cron is missing).

Each alert kind repeats at most every REPEAT per container / host; one "back to normal" line when it clears.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_tz

from django.core.cache import cache

from .disk import _parse_ts, load_report, send

log = logging.getLogger("caspintunel")

REPORT = ".container-stats.json"
PROJECT = "caspintunel"
CONTAINER_WARN_PCT = 85.0
SWAP_ALERT_BYTES = int(1.5 * 1024 ** 3)
SWAP_ALERT_FOR = timedelta(minutes=30)
PSI_ALERT = 10.0
STALE_AFTER = timedelta(minutes=20)
REPEAT = timedelta(hours=6)
_STATE_KEY = "ops:containers:state"
_MB = 1024 ** 2


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def snapshot(now: datetime | None = None) -> dict:
    """The latest sample, our containers first (Monitoring page)."""
    now = now or datetime.now(dt_tz.utc)
    rep = load_report(REPORT)
    if not rep:
        return {"report": False, "stale": True, "containers": [], "host": None}
    gen = _parse_ts(rep.get("generated_at"))
    rows = []
    for c in rep.get("containers", []):
        used, limit = int(_num(c.get("mem_used"))), int(_num(c.get("mem_limit")))
        rows.append({
            "name": c.get("name", ""), "service": c.get("service") or c.get("name", ""),
            "ours": c.get("project") == PROJECT,
            "cpu": _num(c.get("cpu")), "mem_used": used, "mem_limit": limit,
            "percent": round(used * 100 / limit, 1) if limit else None,
            "oom_killed": bool(c.get("oom_killed")), "restarts": int(_num(c.get("restarts"))),
            "state": c.get("state", ""),
        })
    rows.sort(key=lambda r: (not r["ours"], -(r["percent"] or 0), -r["mem_used"]))
    return {"report": True, "generated_at": gen, "stale": gen is None or now - gen > STALE_AFTER,
            "host": rep.get("host") or {}, "containers": rows,
            "thresholds": {"container_pct": CONTAINER_WARN_PCT, "swap_bytes": SWAP_ALERT_BYTES, "psi": PSI_ALERT}}


def _problems(snap: dict, state: dict, now: datetime) -> dict[str, str]:
    """{key: text} of what is wrong right now."""
    out: dict[str, str] = {}
    if not snap["report"] or snap["stale"]:
        out["report"] = "the host container report (scripts/container-stats.sh, cron every 5 min) is missing or stale"
        return out
    for r in snap["containers"]:
        if not r["ours"]:
            continue
        if r["percent"] is not None and r["percent"] >= CONTAINER_WARN_PCT:
            out[f"mem:{r['service']}"] = (f"{r['service']} uses {r['mem_used'] // _MB} MB of its {r['mem_limit'] // _MB} MB "
                                          f"limit ({r['percent']}%)")
        if r["oom_killed"]:
            out[f"oom:{r['service']}"] = f"{r['service']} was killed for running out of memory (OOM)"
        last = (state.get("restarts") or {}).get(r["name"])
        if last is not None and r["restarts"] > last:
            out[f"restart:{r['service']}"] = f"{r['service']} restarted ({r['restarts'] - last}× since the last check)"
    h = snap["host"] or {}
    swap = int(_num(h.get("swap_used")))
    if swap >= SWAP_ALERT_BYTES:
        since = state.get("swap_high_since")
        since_dt = datetime.fromisoformat(since) if since else now
        if now - since_dt >= SWAP_ALERT_FOR:
            out["swap"] = f"swap in use {swap / 1024 ** 3:.1f} GB for more than {int(SWAP_ALERT_FOR.total_seconds() // 60)} min"
    if _num(h.get("psi_some_avg60")) >= PSI_ALERT:
        out["psi"] = f"memory pressure {h.get('psi_some_avg60')}% (processes waiting for memory, 60 s average)"
    cpus = max(int(_num(h.get("cpus"), 1)), 1)
    if _num(h.get("load15")) > cpus:
        out["load"] = f"load average {h.get('load15')} (15 min) above the {cpus} CPUs"
    return out


def check(now: datetime | None = None) -> dict:
    """Run from resource_sample_task: alert on new / repeating problems, once on recovery."""
    now = now or datetime.now(dt_tz.utc)
    snap = snapshot(now)
    state = cache.get(_STATE_KEY) or {}
    h = snap.get("host") or {}
    if int(_num(h.get("swap_used"))) >= SWAP_ALERT_BYTES:
        state.setdefault("swap_high_since", now.isoformat())
    else:
        state.pop("swap_high_since", None)
    problems = _problems(snap, state, now)
    sent_at = state.get("sent") or {}
    fresh = []
    for key, text in problems.items():
        last = sent_at.get(key)
        if not last or now - datetime.fromisoformat(last) >= REPEAT:
            fresh.append(text)
            sent_at[key] = now.isoformat()
    cleared = [k for k in list(sent_at) if k not in problems]
    for k in cleared:
        sent_at.pop(k, None)
    lines = []
    if fresh:
        lines.append("🧠 Memory / load watch:\n" + "\n".join(f"• {t}" for t in fresh))
    if cleared and not problems:
        lines.append("✅ Memory / load back to normal.")
    sent = send("\n".join(lines)) if lines else 0
    if snap["report"]:
        state["restarts"] = {r["name"]: r["restarts"] for r in snap["containers"]}
    state["sent"] = sent_at
    cache.set(_STATE_KEY, state, None)
    return {"problems": list(problems), "alerted": len(fresh), "sent": sent}
