"""Settings → Domain & Cloudflare → Access mode (direct / Cloudflare proxy / Iran tunnel):
DNS through a mocked Cloudflare API (root + www only, mail never), path checks before
and after the DNS change, automatic revert, Full (strict), editable Iran IPs + tunnel
sources + PROXY ports, auto-detect, tunnel-aware throttling, Cloudflare ranges, DNS-01."""
import json
import re
from urllib.parse import parse_qs, urlparse

import pytest
import responses
from django.test import RequestFactory

from apps.common.models import AuditLog
from apps.settings_app import access as A
from apps.settings_app.models import DomainConfig

pytestmark = pytest.mark.django_db
CF = "https://api.cloudflare.com/client/v4"
DOH = "https://doh.test/dns-query"
IP, IRAN, IRAN2, EDGE = "203.0.113.7", "185.124.174.13", "185.124.174.14", "104.16.5.5"
TOKEN = "cf-token-abcdefghijklmnopqrstuvwxyz"


@pytest.fixture
def env(settings, tmp_path, monkeypatch):
    settings.UPDATE_SENTINEL_PATH = str(tmp_path / ".update-requested")
    settings.SERVER_IP = IP
    settings.DOMAIN = "site.example"
    settings.CLOUDFLARE_API_TOKEN = ""
    settings.DOMAIN_DOH_URLS = [DOH]
    settings.DOMAIN_ACCESS_POLL_SECONDS = 0
    settings.DOMAIN_ACCESS_PROPAGATION_SECONDS = 0
    DomainConfig.objects.update_or_create(pk=1, defaults={"cloudflare_token": TOKEN})
    paths = {}                                             # ip → ok? (the fake TLS check)

    def fake_probe(ip, domain, path="/api/v1/health/", timeout=10):
        ok = paths.get(ip, False)
        return {"ip": ip, "ok": ok, "status": 200 if ok else None, "error": "" if ok else f"no answer on {ip}:443"}

    monkeypatch.setattr(A, "probe", fake_probe)
    return {"dir": tmp_path, "paths": paths}


def ok(result):
    return {"success": True, "result": result, "errors": []}


def mock_cf(ssl="full", ssl_editable=True):
    """zone site.example with A @ / www / mail → this server; dns_records CRUD; settings/ssl"""
    store = {f"r{i}": {"id": f"r{i}", "type": "A", "name": n, "content": IP, "proxied": False, "ttl": 1}
             for i, n in enumerate(["site.example", "www.site.example", "mail.site.example"])}
    st = {"ssl": ssl}
    responses.add(responses.GET, f"{CF}/zones", json=ok([{"id": "z1", "name": "site.example", "status": "active",
                                                          "permissions": ["#dns_records:edit"]}]))

    def listing(req):
        q = {k: v[0] for k, v in parse_qs(urlparse(req.url).query).items()}
        return 200, {}, json.dumps(ok([r for r in store.values() if q.get("name", r["name"]) == r["name"]
                                       and q.get("type", r["type"]) == r["type"]]))

    def create(req):
        b = json.loads(req.body)
        rid = f"n{len(store)}{b['content']}"
        store[rid] = {**b, "id": rid}
        return 200, {}, json.dumps(ok(store[rid]))

    def change(req):
        rid = req.url.rsplit("/", 1)[1]
        if req.method == "DELETE":
            store.pop(rid)
            return 200, {}, json.dumps(ok({"id": rid}))
        store[rid] = {**store[rid], **json.loads(req.body)}
        return 200, {}, json.dumps(ok(store[rid]))

    def ssl_cb(req):
        if req.method == "PATCH":
            if not ssl_editable:
                return 403, {}, json.dumps({"success": False, "result": None, "errors": [{"code": 10000, "message": "Authentication error"}]})
            st["ssl"] = json.loads(req.body)["value"]
        return 200, {}, json.dumps(ok({"id": "ssl", "value": st["ssl"]}))

    responses.add_callback(responses.GET, f"{CF}/zones/z1/dns_records", callback=listing)
    responses.add_callback(responses.POST, f"{CF}/zones/z1/dns_records", callback=create)
    for m in (responses.PUT, responses.PATCH, responses.DELETE):
        responses.add_callback(m, re.compile(rf"{re.escape(CF)}/zones/z1/dns_records/.+"), callback=change)
    responses.add_callback(responses.GET, f"{CF}/zones/z1/settings/ssl", callback=ssl_cb)
    responses.add_callback(responses.PATCH, f"{CF}/zones/z1/settings/ssl", callback=ssl_cb)

    def doh(req):                                         # public DNS answers what the zone says (proxied → an edge)
        name = parse_qs(urlparse(req.url).query)["name"][0]
        ans = [EDGE if r.get("proxied") else r["content"] for r in store.values() if r["name"] == name and r["type"] == "A"]
        return 200, {}, json.dumps({"Status": 0, "Answer": [{"type": 1, "data": a} for a in ans]})

    responses.add_callback(responses.GET, DOH, callback=doh)
    return store, st


def a(store, name):
    return sorted((r["content"], r.get("proxied", False)) for r in store.values() if r["name"] == name)


def writes():
    return [c for c in responses.calls if c.request.method in ("POST", "PUT", "PATCH", "DELETE") and "/dns_records" in c.request.url]


@pytest.fixture
def boss(superadmin, staff_client):
    return staff_client(superadmin)


def setup_tunnel(boss, iran=(IRAN,), sources=("172.19.0.1",)):
    r = boss.post("/api/v1/admin/domain/access/settings/", {"iran_ips": list(iran), "tunnel_sources": list(sources)}, format="json")
    assert r.status_code == 200, r.json()
    return r


# ------------------------------------------------------------------ tunnel
@responses.activate
def test_tunnel_switch_checks_first_then_moves_root_and_www_only(env, boss):
    store, _ = mock_cf()
    setup_tunnel(boss, iran=(IRAN, IRAN2))
    env["paths"].update({IRAN: True, IRAN2: True})
    r = boss.post("/api/v1/admin/domain/access/", {"mode": "tunnel"}, format="json")
    assert r.status_code == 200, r.json()
    acc = boss.get("/api/v1/admin/domain/").json()["access"]
    sw = acc["switch"]
    assert acc["mode"] == "tunnel" and sw["status"] == "ok", sw
    assert set(sw["steps"]) == {"check", "preverify", "dns", "propagate", "verify"}
    assert a(store, "site.example") == [(IRAN, False), (IRAN2, False)] == a(store, "www.site.example")
    assert a(store, "mail.site.example") == [(IP, False)]                       # mail never touched
    assert {r["ttl"] for r in store.values() if r["content"] in (IRAN, IRAN2)} == {60}
    assert not any("mail.site.example" in (c.request.body or b"").decode() if isinstance(c.request.body, bytes)
                   else "mail.site.example" in (c.request.body or "") for c in writes())
    assert AuditLog.objects.filter(action="domain.access_ok").exists()


@responses.activate
def test_tunnel_path_broken_means_nothing_changes(env, boss):
    store, _ = mock_cf()
    setup_tunnel(boss)
    responses.calls.reset()
    boss.post("/api/v1/admin/domain/access/", {"mode": "tunnel"}, format="json")
    acc = boss.get("/api/v1/admin/domain/").json()["access"]
    assert acc["mode"] == "direct" and acc["switch"]["status"] == "failed"
    err = acc["switch"]["error"]
    assert err["key"] == "ax_path" and IRAN in err["en"] and err["fa"] and "443" in err["raw"]
    assert not writes() and a(store, "site.example") == [(IP, False)]


@responses.activate
def test_failure_after_the_dns_change_puts_dns_back(env, boss, monkeypatch):
    store, _ = mock_cf()
    setup_tunnel(boss)
    calls = []

    def flaky(ip, domain, path="/api/v1/health/", timeout=10):
        calls.append(ip)
        good = len(calls) == 1                              # fine before DNS, broken after
        return {"ip": ip, "ok": good, "status": 200 if good else 403, "error": "" if good else "HTTP 403 from something that is not this server"}

    monkeypatch.setattr(A, "probe", flaky)
    boss.post("/api/v1/admin/domain/access/", {"mode": "tunnel"}, format="json")
    acc = boss.get("/api/v1/admin/domain/").json()["access"]
    assert acc["switch"]["status"] == "reverted" and acc["mode"] == "direct"
    assert acc["switch"]["steps"]["revert"]["state"] == "ok" and acc["switch"]["error"]["key"] == "ax_reverted"
    assert a(store, "site.example") == [(IP, False)] == a(store, "www.site.example")


@responses.activate
def test_new_iran_ip_updates_dns_and_back_returns_to_direct(env, boss):
    store, _ = mock_cf()
    setup_tunnel(boss)
    env["paths"].update({IRAN: True, IRAN2: True, IP: True})
    boss.post("/api/v1/admin/domain/access/", {"mode": "tunnel"}, format="json")
    r = boss.post("/api/v1/admin/domain/access/settings/", {"iran_ips": [IRAN2]}, format="json")   # the Iran IP changed
    assert r.status_code == 200
    assert a(store, "site.example") == [(IRAN2, False)]
    boss.post("/api/v1/admin/domain/access/back/", format="json")
    acc = boss.get("/api/v1/admin/domain/").json()["access"]
    assert acc["mode"] == "direct" and a(store, "site.example") == [(IP, False)]


# ------------------------------------------------------------------ Cloudflare proxy
@responses.activate
def test_cloudflare_mode_sets_full_strict_and_orange_cloud(env, boss):
    store, st = mock_cf(ssl="flexible")
    env["paths"].update({IP: True, EDGE: True})
    boss.post("/api/v1/admin/domain/access/", {"mode": "cloudflare"}, format="json")
    acc = boss.get("/api/v1/admin/domain/").json()["access"]
    assert acc["mode"] == "cloudflare", acc["switch"]
    assert st["ssl"] == "strict" and acc["switch"]["steps"]["ssl"]["state"] == "ok"
    assert a(store, "site.example") == [(IP, True)] == a(store, "www.site.example")
    assert a(store, "mail.site.example") == [(IP, False)]                       # mail stays DNS-only
    assert acc["switch"]["steps"]["verify"]["probes"][0]["ip"] == EDGE           # checked through a Cloudflare edge


@responses.activate
def test_cloudflare_mode_refused_when_strict_cannot_be_set(env, boss):
    store, st = mock_cf(ssl="flexible", ssl_editable=False)
    env["paths"].update({IP: True})
    boss.post("/api/v1/admin/domain/access/", {"mode": "cloudflare"}, format="json")
    acc = boss.get("/api/v1/admin/domain/").json()["access"]
    assert acc["switch"]["status"] == "failed" and acc["switch"]["error"]["key"] == "ax_ssl"
    assert "Full (strict)" in acc["switch"]["error"]["en"] and st["ssl"] == "flexible" and not writes()


# ------------------------------------------------------------------ settings + validation
@responses.activate
def test_validation_and_nginx_params_for_the_host(env, boss):
    mock_cf()
    bad = boss.post("/api/v1/admin/domain/access/settings/", {"iran_ips": ["10.0.0.5"]}, format="json")
    assert bad.status_code == 400 and bad.json()["error"]["key"] == "ax_bad_ip"
    assert boss.post("/api/v1/admin/domain/access/settings/", {"tunnel_sources": ["not-an-ip"]}, format="json").status_code == 400
    r = boss.post("/api/v1/admin/domain/access/", {"mode": "tunnel"}, format="json")
    assert r.status_code == 400 and r.json()["error"]["key"] == "ax_no_iran"
    boss.post("/api/v1/admin/domain/access/settings/", {"iran_ips": [IRAN]}, format="json")
    r = boss.post("/api/v1/admin/domain/access/", {"mode": "tunnel"}, format="json")
    assert r.json()["error"]["key"] == "ax_no_sources" and "Auto-detect" in r.json()["detail"]
    r = boss.post("/api/v1/admin/domain/access/settings/", {
        "tunnel_sources": ["172.19.0.1", "10.10.0.0/24", "127.0.0.1", "fd00::/64", "172.19.0.1"],
        "proxy_protocol": {"443": True}}, format="json")
    acc = r.json()["access"]
    assert acc["tunnel_sources"] == ["172.19.0.1", "10.10.0.0/24", "127.0.0.1", "fd00::/64"]
    assert acc["proxy_protocol"] == {"80": False, "443": True} and acc["switch"]["nginx"]["state"] == "running"
    params = json.loads((env["dir"] / ".access-nginx.json").read_text())
    assert params["sources"] == acc["tunnel_sources"] and params["proxy_ports"] == ["443"] and "173.245.48.0/20" in params["cf_v4"]
    req = json.loads((env["dir"] / ".domain-request.json").read_text())
    assert req["action"] == "access"
    # the host's result is folded in
    (env["dir"] / ".domain-request.json").unlink()
    (env["dir"] / ".domain-status.json").write_text(json.dumps({"ok": True, "action": "access", "message": "access: nginx updated",
                                                                "at": "2026-10-25T10:00:00Z", "id": None}))
    assert boss.get("/api/v1/admin/domain/").json()["access"]["switch"]["nginx"]["state"] == "ok"


@responses.activate
def test_wizard_in_progress_blocks_a_switch(env, boss):
    from apps.settings_app.models import DomainChange

    mock_cf()
    DomainChange.objects.create(old_domain="site.example", new_domain="new.example", status="draft", server_ip=IP)
    r = boss.post("/api/v1/admin/domain/access/", {"mode": "direct"}, format="json")
    assert r.status_code == 400 and r.json()["error"]["key"] == "ax_wizard"


# ------------------------------------------------------------------ auto-detect + tunnel requests
@responses.activate
def test_auto_detect_reports_the_tunnel_source(env, boss, monkeypatch, client):
    mock_cf()
    boss.post("/api/v1/admin/domain/access/settings/", {"iran_ips": [IRAN]}, format="json")

    def through_tunnel(ip, domain, path="/api/v1/health/", timeout=10):       # the request arrives from the tunnel
        r = client.get(path, HTTP_X_CONN_ADDR="172.19.0.1", HTTP_X_FORWARDED_FOR="172.19.0.1")
        return {"ip": ip, "ok": r.status_code == 200 and r["X-Caspin-Instance"] == A.instance_id(), "error": ""}

    monkeypatch.setattr(A, "probe", through_tunnel)
    out = boss.post("/api/v1/admin/domain/access/detect/", format="json").json()
    assert out["found"] == ["172.19.0.1"] and "--resolve" in out["command"] and out["nonce"] in out["command"]
    assert client.get("/api/v1/domain-probe/unknown/").status_code == 404
    assert client.get("/api/v1/health/")["X-Caspin-Instance"] == A.instance_id()


def test_tunnel_requests_are_keyed_per_client_not_per_ip(db):
    from apps.common.throttling import AnonRateThrottle, TunnelAggregateThrottle, tunnel_ident

    DomainConfig.objects.update_or_create(pk=1, defaults={"tunnel_sources": ["172.19.0.0/16"]})
    from django.core.cache import cache

    cache.delete(A.SOURCES_CACHE)
    rf = RequestFactory()
    t1 = rf.get("/", HTTP_X_CONN_ADDR="172.19.0.1", HTTP_X_FORWARDED_FOR="172.19.0.1", HTTP_X_CLIENT_ID="client-aaaaaaaa")
    t2 = rf.get("/", HTTP_X_CONN_ADDR="172.19.0.1", HTTP_X_FORWARDED_FOR="172.19.0.1", HTTP_X_CLIENT_ID="client-bbbbbbbb")
    resolved = rf.get("/", HTTP_X_CONN_ADDR="172.19.0.1", HTTP_X_FORWARDED_FOR="5.6.7.8")      # PROXY protocol: real IP known
    direct = rf.get("/", HTTP_X_CONN_ADDR="9.9.9.9", HTTP_X_FORWARDED_FOR="9.9.9.9")
    th = AnonRateThrottle()
    assert th.get_ident(t1) == "tunnel:client-aaaaaaaa" != th.get_ident(t2)
    assert th.get_ident(resolved) == "5.6.7.8" and th.get_ident(direct) == "9.9.9.9"
    assert tunnel_ident(direct) is None
    agg = TunnelAggregateThrottle()
    assert agg.get_cache_key(t1, None) == agg.get_cache_key(t2, None) and agg.get_cache_key(direct, None) is None
    no_id = rf.get("/", HTTP_X_CONN_ADDR="172.19.0.1", HTTP_X_FORWARDED_FOR="172.19.0.1", HTTP_USER_AGENT="Safari")
    assert th.get_ident(no_id).startswith("tunnel:h")


# ------------------------------------------------------------------ Cloudflare ranges + DNS-01
@responses.activate
def test_cloudflare_ranges_refresh(env):
    responses.add(responses.GET, f"{CF}/ips", json=ok({"ipv4_cidrs": ["173.245.48.0/20", "104.16.0.0/13"], "ipv6_cidrs": ["2606:4700::/32"]}))
    assert A.refresh_cf_ranges() is True
    cfg = DomainConfig.load()
    assert cfg.cf_ranges["v4"] == ["104.16.0.0/13", "173.245.48.0/20"] and A.is_cloudflare_ip("104.16.5.5")
    assert not A.is_cloudflare_ip("185.124.174.13")
    params = json.loads((env["dir"] / ".access-nginx.json").read_text())
    assert params["cf_v6"] == ["2606:4700::/32"]
    (env["dir"] / ".domain-request.json").unlink()
    assert A.refresh_cf_ranges() is False                    # unchanged → no re-render needed once applied? (not yet applied: re-queued)


@responses.activate
def test_dns01_request_and_host_result(env, boss):
    r = boss.post("/api/v1/admin/domain/access/dns01/", format="json")
    assert r.status_code == 200 and r.json()["access"]["dns01"]["state"] == "running"
    assert json.loads((env["dir"] / ".domain-request.json").read_text())["action"] == "dns01"
    (env["dir"] / ".domain-request.json").unlink()
    (env["dir"] / ".domain-status.json").write_text(json.dumps({"ok": True, "action": "dns01", "at": "2026-10-25T10:00:00Z",
                                                                "message": "dns01: site.example renews via DNS-01", "id": None}))
    d = boss.get("/api/v1/admin/domain/").json()["access"]["dns01"]
    assert d["state"] == "ok" and d["enabled"] is True
    # a new token is handed to the host again
    boss.post("/api/v1/admin/domain/token/", {"token": "another-" + TOKEN}, format="json")
    assert json.loads((env["dir"] / ".domain-request.json").read_text())["action"] == "dns01"
    assert TOKEN not in (env["dir"] / ".domain-request.json").read_text()
