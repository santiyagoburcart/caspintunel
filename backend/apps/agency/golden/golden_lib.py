"""Golden comparison: original PAMP v1.5.3 vs the agency port, on the same data
and the same recorded PasarGuard responses.

This module imports NO app code itself — each side passes its own modules in:
  PAMP     : admins.models / admins.tasks / admins.views  (run_pamp.py, PAMP's own
             Django 4.2 image, PAMP's real settings, a throw-away MySQL)
  agency   : apps.agency.models / tasks / enrich           (tests/test_golden.py)

A scenario = initial state (or an imported dump) + rounds; each round mocks the
panel with `responses` (unmatched URLs raise — nothing can reach a real panel),
runs the sync task once (`.apply()`, as PAMP's "Sync now" does) and collects:
every stored field, every model formula, the view numbers (portal, detail,
dashboard), the snapshot table, the SyncLog rows written, and every HTTP call
made — i.e. the enforcement decisions.
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlparse

BASE = "https://panel.golden.test"

FIELDS = [
    "id", "username", "is_sudo", "is_active", "status", "has_data_limit", "admin_limit_bytes",
    "admin_remaining", "total_user_limit", "total_user_used", "user_count", "active_user_count",
    "limited_users", "disabled_users", "expired_users", "on_hold_users", "pamp_blocked", "raw_data",
    "deleted_users_used_bytes",
]
NULLABLE_TIMES = ["pamp_blocked_at", "last_synced_at", "deleted_traffic_reset_at"]
PROPERTIES = [
    "effective_status", "status_code", "status_label", "status_color", "users_count", "active_users",
    "admin_used_bytes", "is_unlimited", "sold_limit_bytes", "hidden_traffic", "hidden_traffic_bytes",
    "usage_percent", "admin_limit_fmt", "admin_remaining_fmt", "admin_used_fmt", "total_user_limit_fmt",
    "total_user_used_fmt", "hidden_traffic_fmt", "total_user_limit_gb", "total_user_used_gb",
    "admin_remaining_gb", "hidden_traffic_gb", "admin_limit_gb",
]
ENRICH_KEYS = [
    "hidden_traffic_fmt", "total_user_limit_fmt", "total_user_used_fmt", "admin_limit_fmt", "admin_used_fmt",
    "admin_remaining_fmt", "usage_percent", "sold_limit_fmt", "sold_limit_value", "deleted_used_fmt",
    "deleted_used_bytes",
]
PORTAL_KEYS = ["is_blocked", "block_reason", "support_telegram", "show_warning", "warning_pct"]
DASHBOARD_KEYS = [
    "admin_count", "active_count", "disabled_count", "pamp_limited_count", "near_limit_count",
    "total_limit_fmt", "total_used_fmt", "total_remaining_fmt", "total_users", "total_active",
    "over_limit_admins",
]


# ------------------------------------------------------------------ users / mocks
def expand_users(spec):
    """A user list, or {"generate": n, ...} for big lists (the 4096 cap)."""
    if isinstance(spec, dict) and "generate" in spec:
        n, used, limit = spec["generate"], spec.get("used", 1000), spec.get("limit", 2000)
        return [{"username": f"{spec.get('prefix', 'g')}{i}", "used_traffic": used + i, "data_limit": limit,
                 "status": "active"} for i in range(n)]
    return spec


def install_round(rsps, rnd, calls):
    """Register the round's recorded panel responses on a `responses.RequestsMock`."""
    import requests

    def record(request):
        u = urlparse(request.url)
        body = request.body
        if isinstance(body, bytes):
            body = body.decode()
        if body and request.headers.get("Content-Type", "").startswith("application/json"):
            body = json.loads(body)
        calls.append({"method": request.method, "path": u.path,
                      "query": {k: v for k, v in sorted(parse_qs(u.query).items())}, "body": body})

    def reply(spec):
        def cb(request):
            record(request)
            if isinstance(spec, dict) and spec.get("__error"):
                raise requests.exceptions.ConnectTimeout(spec["__error"])
            if isinstance(spec, dict) and "__status" in spec:
                return spec["__status"], {}, json.dumps(spec.get("__body", {"detail": "error"}))
            return 200, {"Content-Type": "application/json"}, json.dumps(spec)
        return cb

    rsps.add_callback("POST", f"{BASE}/api/admin/token", callback=reply(rnd.get("token", {"access_token": "golden"})))
    rsps.add_callback("GET", f"{BASE}/api/admins", callback=reply(rnd["admins"]))
    users = rnd.get("users", {})

    def users_cb(request):
        q = parse_qs(urlparse(request.url).query)
        name = (q.get("admin") or [""])[0]
        spec = users.get(name, {"users": []})
        if isinstance(spec, dict) and ("__status" in spec or "__error" in spec):
            return reply(spec)(request)
        body = spec if isinstance(spec, dict) and "users" in spec else {"users": expand_users(spec)}
        return reply(body)(request)

    rsps.add_callback("GET", re.compile(re.escape(BASE) + r"/api/users(\?.*)?$"), callback=users_cb)
    put_status = rnd.get("put_status", {})

    def put_cb(request):
        name = urlparse(request.url).path.rsplit("/", 1)[-1]
        from urllib.parse import unquote

        return reply({"__status": put_status.get(unquote(name), 200), "__body": {}})(request)

    rsps.add_callback("PUT", re.compile(re.escape(BASE) + r"/api/admin/[^/]+$"), callback=put_cb)


# ------------------------------------------------------------------ state
def load_initial(models, initial):
    """Synthetic starting state (the real run starts from the imported dump)."""
    for a in initial.get("admins", []):
        models.PanelAdmin.objects.create(**a)
    for lim in initial.get("limits", []):
        lim = dict(lim)
        pa = models.PanelAdmin.objects.get(username=lim.pop("admin"))
        models.AdminLimit.objects.create(panel_admin=pa, **lim)
    for s in initial.get("snapshots", []):
        pa = models.PanelAdmin.objects.get(username=s["admin"])
        models.UserTrafficSnapshot.objects.create(panel_admin=pa, user_username=s["user"],
                                                  used_traffic_bytes=s["used"])
    for g in initial.get("groups", []):
        models.AdminGroup.objects.create(**g)


def _plain(v):
    return list(v) if isinstance(v, tuple) else v


def collect(models, enrich_fn, portal_fn, dashboard_fn):
    """Everything PAMP stores or shows, as plain JSON."""
    out = {"admins": {}, "snapshots": {}}
    for a in models.PanelAdmin.objects.order_by("username"):
        row = {f: _plain(getattr(a, f)) for f in FIELDS}
        row.update({f"{t}_set": getattr(a, t) is not None for t in NULLABLE_TIMES})
        row.update({p: _plain(getattr(a, p)) for p in PROPERTIES})
        enr = enrich_fn(a)
        row["enrich"] = {k: _plain(enr[k]) for k in ENRICH_KEYS}
        portal = portal_fn(a)
        row["portal"] = {k: _plain(portal[k]) for k in PORTAL_KEYS} if portal is not None else None
        lim = models.AdminLimit.objects.filter(panel_admin=a).first()
        row["limit_config"] = None if lim is None else {
            "limit_bytes": lim.limit_bytes, "warning_sent_80": lim.warning_sent_80, "is_blocked": lim.is_blocked,
            "telegram_username": lim.telegram_username, "support_telegram": lim.support_telegram}
        out["admins"][a.username] = row
        snaps = models.UserTrafficSnapshot.objects.filter(panel_admin=a)
        out["snapshots"][a.username] = {"count": snaps.count(),
                                        "sum": sum(s.used_traffic_bytes for s in snaps),
                                        "users": sorted([s.user_username, s.used_traffic_bytes] for s in snaps)
                                        if snaps.count() <= 50 else None}
    dash = dashboard_fn()
    out["dashboard"] = {k: _plain(dash[k]) for k in DASHBOARD_KEYS}
    return out


def run(models, sync_task, enrich_fn, portal_fn, dashboard_fn, scenario, *, start_from_initial=True):
    """Run all rounds; returns {"initial": state, "rounds": [...]}."""
    import responses

    if start_from_initial and scenario.get("initial"):
        load_initial(models, scenario["initial"])
    result = {"initial": collect(models, enrich_fn, portal_fn, dashboard_fn), "rounds": []}
    for rnd in scenario["rounds"]:
        calls = []
        before = set(models.SyncLog.objects.values_list("id", flat=True))
        # PAMP's Celery default: eager retries re-run without re-raising. Both apps load
        # their config with namespace="CELERY", so set the namespaced key as well.
        conf = sync_task.app.conf
        keys = ("task_eager_propagates", "CELERY_TASK_EAGER_PROPAGATES")
        saved = {k: conf.get(k) for k in keys}
        for k in keys:
            conf[k] = False
        try:
            with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
                install_round(rsps, rnd, calls)
                res = sync_task.apply(throw=False)
        finally:
            for k, v in saved.items():
                conf[k] = v
        logs = [{"status": s.status, "admins_synced": s.admins_synced, "error_message": s.error_message}
                for s in models.SyncLog.objects.exclude(id__in=before).order_by("id")]
        state = collect(models, enrich_fn, portal_fn, dashboard_fn)
        state.update({"result_state": res.state, "result": str(res.result), "sync_logs": logs, "calls": calls})
        result["rounds"].append(state)
    return result


def diff(a, b, path=""):
    """Every difference between two collected results (empty = identical)."""
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f"{path}/{k}: only in {'expected' if k in a else 'actual'}")
            else:
                out += diff(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f"{path}[{i}]")
    elif type(a) is not type(b) or a != b:
        out.append(f"{path}: expected {a!r} got {b!r}")
    return out
