"""Blu collector health over SSH — read-only, without touching the collector.

Every `blu_ssh_check_minutes` (beat `blu_service_check_task`) the worker runs ONE fixed
command on the Iran server (`BLU_SSH_HOST`, key auth, files mounted read-only at `BLU_SSH_DIR`):

    systemctl is-active <service>; journalctl -u <service> --since -10min (read-only)

v1.33.1 — liveness is the last SUCCESSFUL POLL, not the last deposit (a quiet account is not an
outage; the old "no deposit for N min" alert fired every night):

  * the collector prints one line per successful poll, containing "poll ok" (see
    docs/blu-webhook.md for the exact line) → `last_poll_ok_at`; alert when there was none for
    `blu_poll_stale_minutes` (default 10);
  * until it prints such lines, polling failure is inferred from "poll error" lines: at least
    80 % of the polls expected in the window failed (45 s poll → 11 of the last 10 min);
  * session / login / OTP errors on the poll → alert «نشست بلو منقضی شده — دوباره وارد شوید»;
  * service not active; SSH to the Iran server failed 3 times in a row (we are blind).

One alert per incident (`svc_alert`), one silent "back online" when it is fine again. State lives
on `BluCollector` (pk=1). Push failures to our webhook are not polling problems and never count.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import BluCollector

log = logging.getLogger("caspintunel")

SSH_FAILS_ALERT = 3
JOURNAL_WINDOW = "-10min"
_SERVICE_RE = re.compile(r"^[A-Za-z0-9@._-]+\.service$")
_HOST_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_ERROR_RE = re.compile(
    r"\b(error|err!|fail(?:ed|ure|s)?|refused|denied|forbidden|unauthori[sz]ed|timeout|timed out|"
    r"econn\w*|eai_again|enotfound|exception|http\s*[45]\d\d|status\s*[45]\d\d)\b", re.I)
_OK_RE = re.compile(r"Deactivated successfully|Started |Stopped |Stopping |Consumed .* CPU time", re.I)
_POLL_OK_RE = re.compile(r"\bpoll ok\b", re.I)
_POLL_ERR_RE = re.compile(r"\bpoll error\b", re.I)
_PUSH_RE = re.compile(r"\bpush\b|outbox|delivered", re.I)          # our webhook side, not Blu
_SESSION_RE = re.compile(r"session|expired|re-?login|\blogin\b|sign[ -]?in|\botp\b|unauthori[sz]ed|\b401\b|"
                         r"invalid[ _-]?token|token[ _-]?expired|authenticat", re.I)
_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:?\d{2}|Z)?)")


def ssh_host() -> str:
    host = (getattr(settings, "BLU_SSH_HOST", "") or "").strip()
    return host if _HOST_RE.match(host or "-") and host else ""


def service_name() -> str:
    name = (getattr(settings, "BLU_COLLECTOR_SERVICE", "") or "blu-collector.service").strip()
    if not _SERVICE_RE.match(name):
        raise ValueError("BLU_COLLECTOR_SERVICE must look like name.service")
    return name


def remote_command(service: str) -> str:
    """The only thing ever run on the Iran server: two read-only commands."""
    return (f"systemctl is-active {service}; echo ---JOURNAL---; "
            f"journalctl -u {service} --since {JOURNAL_WINDOW} --no-pager -o short-iso -q")


def ssh_argv(host: str, service: str) -> list[str]:
    d = getattr(settings, "BLU_SSH_DIR", "/run/blu-ssh") or "/run/blu-ssh"
    argv = ["ssh"]
    if os.path.exists(os.path.join(d, "config")):
        argv += ["-F", os.path.join(d, "config")]     # resolves the alias (HostName / User / Port)
    argv += ["-i", os.path.join(d, "id_ed25519_iran"),
             "-o", f"UserKnownHostsFile={os.path.join(d, 'known_hosts')}",
             "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
             "-o", "ConnectTimeout=10", "-o", "LogLevel=ERROR", "-T", host, remote_command(service)]
    return argv


def mask_line(line: str) -> str:
    line = re.sub(r"[0-9a-fA-F]{32,}", "***", line)
    line = re.sub(r"(?<!\d)(\d{6})\d{2,6}(\d{4})(?!\d)", r"\1******\2", line)   # card-like runs
    line = re.sub(r"(?i)(password|secret|token|key)=\S+", r"\1=***", line)
    return line.strip()[:255]


def parse(output: str) -> tuple[str, list[str]]:
    head, _, journal = output.partition("---JOURNAL---")
    state = (head.strip().splitlines() or ["unknown"])[-1].strip()[:16] or "unknown"
    errors = [ln for ln in journal.splitlines() if _ERROR_RE.search(ln) and not _OK_RE.search(ln)]
    return state, errors


def _ts(line: str):
    from datetime import datetime

    m = _TS_RE.match(line.strip())
    if not m:
        return None
    raw = m.group(1).replace("Z", "+00:00")
    if re.search(r"[+-]\d{4}$", raw):
        raw = raw[:-2] + ":" + raw[-2:]
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo else timezone.make_aware(dt)


def parse_polls(output: str) -> dict:
    """From the journal part: last "poll ok" time, the "poll error" lines and the session errors."""
    _, _, journal = output.partition("---JOURNAL---")
    lines = journal.splitlines()
    oks = [t for t in (_ts(ln) for ln in lines if _POLL_OK_RE.search(ln)) if t]
    poll_errs = [ln for ln in lines if _POLL_ERR_RE.search(ln) and not _PUSH_RE.search(ln.split("poll error", 1)[0])]
    session = [ln for ln in lines if _SESSION_RE.search(ln) and not _PUSH_RE.search(ln) and not _OK_RE.search(ln)]
    return {"last_ok": max(oks) if oks else None, "poll_errors": poll_errs, "session": session}


def poll_stale_minutes() -> int:
    from apps.settings_app.utils import get_setting

    try:
        return max(2, int(get_setting("blu_poll_stale_minutes", 10) or 10))
    except (TypeError, ValueError):
        return 10


def failing_threshold() -> int:
    """Without "poll ok" lines: how many "poll error" lines in the 10-min window mean that polling
    has been failing for the whole stale period (80 % of the expected polls)."""
    import math

    poll = max(10, int(getattr(settings, "BLU_COLLECTOR_POLL_SECONDS", 45) or 45))
    minutes = min(poll_stale_minutes(), 10)
    return max(3, math.ceil(minutes * 60 / poll * 0.8))


def run_check() -> dict:
    """One SSH round trip; returns {"ok": bool, "state", "errors", "error"}."""
    host = ssh_host()
    try:
        r = subprocess.run(ssh_argv(host, service_name()), capture_output=True, text=True, timeout=40)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": mask_line(f"ssh: {exc}")}
    if r.returncode == 255:                              # ssh itself failed (connect / auth / host key)
        return {"ok": False, "error": mask_line((r.stderr or "ssh failed").strip().splitlines()[-1])}
    state, errors = parse(r.stdout or "")
    return {"ok": True, "state": state, "errors": errors, **parse_polls(r.stdout or "")}


def check_service() -> str:
    """Beat task body. Returns a short status for the task result."""
    if not ssh_host():
        return "disabled"
    res = run_check()
    now = timezone.now()
    with transaction.atomic():
        c = BluCollector.objects.select_for_update().get(pk=BluCollector.get().pk)
        c.svc_checked_at = now
        if res["ok"]:
            c.ssh_failures, c.ssh_error = 0, ""
            c.svc_state = res["state"]
            c.svc_error_count = len(res["errors"])
            c.poll_error_count = len(res["poll_errors"])
            if res["errors"]:
                c.svc_error_line = mask_line(res["errors"][-1])
            if res["session"]:
                c.svc_error_line = mask_line(res["session"][-1])
            if res["last_ok"] and (c.last_poll_ok_at is None or res["last_ok"] > c.last_poll_ok_at):
                c.last_poll_ok_at = res["last_ok"]
        else:
            c.ssh_failures += 1
            c.ssh_error = res["error"]
        problem = ""
        if not res["ok"]:
            if c.ssh_failures >= SSH_FAILS_ALERT:
                problem = "ssh"
        elif c.svc_state != "active":
            problem = "inactive"
        elif res["session"]:
            problem = "session"
        elif c.last_poll_ok_at is not None:
            # the collector reports its successful polls: that is the liveness signal
            if now - c.last_poll_ok_at > timedelta(minutes=poll_stale_minutes()):
                problem = "poll"
        elif c.poll_error_count >= failing_threshold():
            problem = "poll"            # no "poll ok" lines yet: nearly every poll in the window failed
        # an SSH hiccup (1–2 failures) keeps the previous verdict: no alert, no recovery
        if not res["ok"] and not problem:
            c.save()
            return "ssh_failed"
        before = c.svc_alert
        c.svc_alert = problem
        c.save()
    if problem and not before:
        _alert(problem, c)
        return f"alert:{problem}"
    if before and not problem:
        _recovered()
        return "recovered"
    return problem or "ok"


_TEXT = {
    "inactive": ("سرویس جمع‌کنندهٔ بلو روی سرور ایران فعال نیست (وضعیت: {state}). تأیید خودکار بلو متوقف است؛ پیامک آیفون همچنان کار می‌کند.",
                 "Blu collector service on the Iran server is not active ({state}). Blu auto-confirm is paused."),
    "ssh": ("اتصال SSH به سرور ایران {n} بار پشت سر هم ناموفق بود — وضعیت جمع‌کنندهٔ بلو نامعلوم است. ({err})",
            "SSH to the Iran server failed {n} times in a row — Blu collector state unknown. ({err})"),
    "session": ("نشست بلو منقضی شده — دوباره وارد شوید. تأیید خودکار بلو تا ورود دوباره متوقف است. ({line})",
                "Blu session expired — sign in again. Blu auto-confirm is paused until then. ({line})"),
    "poll": ("جمع‌کنندهٔ بلو {m} دقیقه است حساب را با موفقیت نخوانده — تأیید خودکار بلو متوقف است؛ پیامک آیفون همچنان کار می‌کند. آخرین خطا: {line}",
             "Blu collector has not polled the account successfully for {m} min — Blu auto-confirm is paused. Last error: {line}"),
}


def _alert(kind: str, c: BluCollector) -> None:
    from apps.common.staff_alert import alert_staff
    from apps.notifications.live import push_payments_event

    if kind == "poll" and c.last_poll_ok_at:
        minutes = int((timezone.now() - c.last_poll_ok_at).total_seconds() // 60)
    else:
        minutes = poll_stale_minutes()
    vals = {"state": c.svc_state, "n": c.ssh_failures if kind == "ssh" else c.svc_error_count,
            "err": c.ssh_error, "line": c.svc_error_line or "—", "m": minutes}
    fa, en = _TEXT[kind]
    alert_staff(f"⚠️ {fa.format(**vals)}\n{en.format(**vals)}", perm="payment.view",
                dedupe_key=f"blu:svc:{kind}:{c.svc_checked_at:%Y%m%d%H%M}", ttl=600)
    push_payments_event("blu_service", ok=False, kind=kind, state=c.svc_state)
    log.warning("Blu collector service alert: %s", kind)


def _recovered() -> None:
    from apps.common.staff_alert import alert_staff
    from apps.notifications.live import push_payments_event

    alert_staff("✅ سرویس جمع‌کنندهٔ بلو دوباره سالم است.\nBlu collector service is healthy again.", perm="payment.view",
                silent=True)
    push_payments_event("blu_service", ok=True)


def service_health() -> dict:
    c = BluCollector.get()
    return {"configured": bool(ssh_host()), "state": c.svc_state, "checked_at": c.svc_checked_at,
            "error_line": c.svc_error_line, "error_count": c.svc_error_count,
            "ssh_failures": c.ssh_failures, "ssh_error": c.ssh_error, "alert": c.svc_alert,
            # v1.33.1: the liveness signal (null until the collector prints "poll ok" lines)
            "last_poll_ok_at": c.last_poll_ok_at, "poll_error_count": c.poll_error_count,
            "poll_ok_logged": c.last_poll_ok_at is not None, "poll_stale_minutes": poll_stale_minutes()}
