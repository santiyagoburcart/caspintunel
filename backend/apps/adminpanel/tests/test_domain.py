"""Settings → Domain & Cloudflare: write-only encrypted token + test, the wizard
(Cloudflare and manual DNS) through the API with a mocked Cloudflare API,
mocked public DNS and a simulated host watcher (request / status files),
transition → automatic retire, rollback, audit, super-admin only."""
import json
import re
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
import responses
from django.db import connection
from django.utils import timezone

from apps.common.models import AuditLog
from apps.settings_app import domain as D
from apps.settings_app.models import DomainChange, DomainConfig, EmailSettings, SiteConfig

from .conftest import make_staff

CF = "https://api.cloudflare.com/client/v4"
DOH = "https://doh.test/dns-query"
IP = "203.0.113.7"
TOKEN = "cf-token-abcdefghijklmnopqrstuvwxyz"
pytestmark = pytest.mark.django_db


@pytest.fixture
def env(settings, tmp_path, monkeypatch):
    settings.UPDATE_SENTINEL_PATH = str(tmp_path / ".update-requested")
    settings.SERVER_IP = IP
    settings.DOMAIN = "old.example"
    settings.CLOUDFLARE_API_TOKEN = ""
    settings.DOMAIN_DOH_URLS = [DOH]
    settings.MINIAPP_URL = "https://old.example"
    sc = SiteConfig.load()
    sc.site_domain = "old.example"
    sc.save()
    es = EmailSettings.load()
    es.from_email = "no-reply@old.example"
    es.save()
    calls = []

    class Bot:
        def set_chat_menu_button(self, **kw):
            calls.append(kw)

    monkeypatch.setattr("apps.telegram.config.sales_client", lambda: Bot())
    return {"dir": tmp_path, "menu": calls}


def ok(result):
    return {"success": True, "result": result, "errors": []}


def mock_cf(zones=None, dns_edit=True, status="active", refuse=None):
    """a small in-memory Cloudflare: token verify, zones, dns_records list / create / delete.
    dns_edit=False refuses every write (10000); refuse={name: (http, code, message)} refuses one name."""
    store = {}
    perms = ["#zone:read", "#dns_records:read"] + (["#dns_records:edit"] if dns_edit else [])
    zones = zones or [{"id": "z1", "name": "new.example", "status": "active", "permissions": perms}]
    responses.add(responses.GET, f"{CF}/user/tokens/verify", json=ok({"id": "t1", "status": status}))
    responses.add(responses.GET, f"{CF}/zones", json=ok(zones))

    def list_records(req):
        q = {k: v[0] for k, v in parse_qs(urlparse(req.url).query).items()}
        return 200, {}, json.dumps(ok([r for r in store.values() if q.get("name", r["name"]) == r["name"] and q.get("type", r["type"]) == r["type"]]))

    def fail(http, code, message):
        return http, {}, json.dumps({"success": False, "result": None, "errors": [{"code": code, "message": message}]})

    def create(req):
        body = json.loads(req.body)
        if not dns_edit:
            return fail(403, 10000, "Authentication error")
        if body["name"] in (refuse or {}):
            return fail(*refuse[body["name"]])
        rid = f"r{len(store) + 1}"
        while rid in store:
            rid += "x"
        store[rid] = {**body, "id": rid}
        return 200, {}, json.dumps(ok(store[rid]))

    def delete(req):
        store.pop(req.url.rsplit("/", 1)[1], None)
        return 200, {}, json.dumps(ok({}))

    responses.add_callback(responses.GET, f"{CF}/zones/z1/dns_records", callback=list_records)
    responses.add_callback(responses.POST, f"{CF}/zones/z1/dns_records", callback=create)
    responses.add_callback(responses.DELETE, re.compile(rf"{re.escape(CF)}/zones/z1/dns_records/.+"), callback=delete)
    return store


CODES = {"A": 1, "MX": 15, "TXT": 16}


def mock_dns(answers, store=None):
    """public DNS: A from `answers`, MX / TXT from `answers[(name, type)]` or the mocked Cloudflare store
    (TXT quoted and split into 255-byte chunks, like real resolvers answer)"""
    def cb(req):
        q = parse_qs(urlparse(req.url).query)
        name, rtype = q["name"][0], q["type"][0]
        if rtype == "A":
            vals = answers.get(name, [])
        else:
            vals = list(answers.get((name, rtype), []))
            for rec in (store or {}).values():
                if rec["name"] == name and rec["type"] == rtype:
                    vals.append(f"{rec['priority']} {rec['content']}." if rtype == "MX"
                                else " ".join(f'"{rec["content"][i:i + 255]}"' for i in range(0, len(rec["content"]), 255)))
        return 200, {}, json.dumps({"Status": 0, "Answer": [{"type": CODES[rtype], "data": v} for v in vals]})

    responses.add_callback(responses.GET, DOH, callback=cb)


DKIM_TXT = "v=DKIM1; h=sha256; k=rsa; p=" + "A" * 380


def write_dkim(e, domain):
    (e["dir"] / ".domain-dkim.json").write_text(json.dumps({"domain": domain, "selector": "mail", "txt": DKIM_TXT}))


def host_done(e, action, ok_=True, message="done", **extra):
    """what scripts/domain.sh does: consume the request, write the status"""
    req = json.loads((e["dir"] / ".domain-request.json").read_text())
    assert req["action"] == action
    (e["dir"] / ".domain-request.json").unlink()
    (e["dir"] / ".domain-status.json").write_text(json.dumps({
        "ok": ok_, "message": message, "id": req["id"], "action": action, "requested_by": req["requested_by"],
        "at": timezone.now().isoformat(), **extra}))
    return req


@pytest.fixture
def boss(superadmin, staff_client):
    return staff_client(superadmin)


@responses.activate
def test_token_write_only_encrypted_and_tested(env, boss, perms, staff_client):
    r = boss.post("/api/v1/admin/domain/token/", {"token": TOKEN}, format="json")
    assert r.status_code == 200 and r.json()["cloudflare"] == {**r.json()["cloudflare"], "token_set": True, "source": "panel"}
    assert TOKEN not in json.dumps(boss.get("/api/v1/admin/domain/").json())
    with connection.cursor() as c:
        c.execute("SELECT cloudflare_token FROM domain_config")
        raw = c.fetchone()[0]
    assert raw.startswith("enc:v1:") and TOKEN not in raw
    assert DomainConfig.load().cloudflare_token == TOKEN

    mock_cf()
    t = boss.post("/api/v1/admin/domain/token/test/", {}, format="json").json()
    z = t["zones"][0]
    assert t["ok"] and t["source"] == "panel" and z == {**z, "id": "z1", "name": "new.example", "read": True, "dns_edit": True, "error": None}
    assert "#dns_records:edit" in t["permissions"] and DomainConfig.load().last_test["ok"]
    # the edit check really wrote a temporary TXT record and deleted it again
    posts = [json.loads(c.request.body) for c in responses.calls if c.request.method == "POST"]
    assert [p["type"] for p in posts] == ["TXT"] and posts[0]["name"].startswith("_caspintunel-check-")
    assert any(c.request.method == "DELETE" for c in responses.calls) and "leftover" not in z

    responses.reset()
    mock_cf(dns_edit=False)
    t = boss.post("/api/v1/admin/domain/token/test/", {"token": "typed-" + TOKEN}, format="json").json()
    assert not t["ok"] and "not allowed to edit DNS in new.example" in t["error"] and t["source"] == "typed"
    assert t["explain"]["key"] == "cf_perm" and "Zone · DNS · Edit" in t["error_fa"] and "new.example" in t["error_fa"]
    assert t["explain"]["raw"] == "10000: Authentication error"
    assert t["zones"][0]["read"] is True and t["zones"][0]["dns_edit"] is False
    assert responses.calls[0].request.headers["Authorization"] == "Bearer typed-" + TOKEN

    responses.reset()
    mock_cf(status="disabled")
    t = boss.post("/api/v1/admin/domain/token/test/", {}, format="json").json()
    assert t["explain"]["key"] == "cf_inactive" and "“disabled”" in t["error"]

    assert boss.post("/api/v1/admin/domain/token/", {"token": "short"}, format="json").status_code == 400
    boss.post("/api/v1/admin/domain/token/", {"token": ""}, format="json")
    assert boss.get("/api/v1/admin/domain/").json()["cloudflare"]["token_set"] is False
    # super admins only — even with settings.manage
    other = staff_client(make_staff("ops", ["settings.manage"], perms))
    assert other.get("/api/v1/admin/domain/").status_code == 403
    assert other.post("/api/v1/admin/domain/token/", {"token": TOKEN}, format="json").status_code == 403
    assert AuditLog.objects.filter(action="domain.token_saved").exists() and AuditLog.objects.filter(action="domain.token_tested").count() == 3


@responses.activate
def test_full_wizard_cloudflare(env, boss):
    DomainConfig.objects.update_or_create(pk=1, defaults={"cloudflare_token": TOKEN, "transition_days": 14})
    store = mock_cf()
    answers = {"new.example": [IP], "www.new.example": ["198.51.100.1"], "mail.new.example": [IP]}
    mock_dns(answers, store)
    # a) start: zone picked from the token's zones
    r = boss.post("/api/v1/admin/domain/start/", {"domain": "https://WWW.New.Example/", "mode": "cloudflare"}, format="json")
    assert r.status_code == 200, r.json()
    c = r.json()["change"]
    assert c["new_domain"] == "new.example" and c["old_domain"] == "old.example" and c["zone_name"] == "new.example"
    assert [x["name"] for x in c["records"]] == ["new.example", "www.new.example", "mail.new.example"]
    assert all(x["required"] for x in c["records"])                     # mail moves with the domain
    cid = c["id"]
    # one change at a time
    assert "Finish or cancel" in boss.post("/api/v1/admin/domain/start/", {"domain": "x.example"}, format="json").json()["detail"]
    # b) DNS through the API (DNS-only), www still points elsewhere → waiting
    s = boss.post(f"/api/v1/admin/domain/{cid}/dns/", format="json").json()["change"]["steps"]["dns"]
    assert {r["name"]: (r["content"], r["proxied"]) for r in store.values() if r["type"] == "A"} == {
        "new.example": (IP, False), "www.new.example": (IP, False), "mail.new.example": (IP, False)}
    assert s["state"] == "waiting" and "www.new.example" in s["message"]
    assert s["detail"]["zone_check"] == {"read": True, "dns_edit": True, "error": None}       # checked before writing
    why = s["detail"]["error"]
    assert why["key"] == "dns_wrong" and "198.51.100.1" in why["en"] and IP in why["fa"] and "doh.test" in why["raw"]
    assert boss.post(f"/api/v1/admin/domain/{cid}/tls/", format="json").json()["detail"].startswith("DNS must resolve")
    answers["www.new.example"] = [IP]                           # propagated; mail is optional
    s = boss.post(f"/api/v1/admin/domain/{cid}/dns-check/", format="json").json()["change"]["steps"]["dns"]
    assert s["state"] == "ok"
    # c) TLS by the host
    r = boss.post(f"/api/v1/admin/domain/{cid}/apply/", format="json").json()
    assert r["detail"].startswith("The certificate must be issued") and r["detail_fa"].startswith("اول باید گواهی") and r["error"]["key"] == "need_tls"
    st = boss.post(f"/api/v1/admin/domain/{cid}/tls/", format="json").json()
    assert st["pending"]["action"] == "cert" and st["change"]["steps"]["tls"]["state"] == "running"
    assert "already queued" in boss.post(f"/api/v1/admin/domain/{cid}/tls/", format="json").json()["detail"]
    write_dkim(env, "new.example")                                      # the mail server made the key
    req = host_done(env, "cert", message="certificate issued for new.example www.new.example mail.new.example", expires="Jan 21 2027")
    assert req == {**req, "domain": "new.example", "www": True, "mail": True}
    c = boss.get("/api/v1/admin/domain/").json()["change"]
    assert c["steps"]["tls"]["state"] == "ok"
    # mail records published in Cloudflare right after the certificate, and found in public DNS
    mail = {(r["type"], r["name"]): r for r in store.values() if r["type"] != "A"}
    assert mail[("MX", "new.example")]["content"] == "mail.new.example" and mail[("MX", "new.example")]["priority"] == 10
    assert mail[("TXT", "new.example")]["content"] == f"v=spf1 ip4:{IP} mx ~all"
    assert mail[("TXT", "_dmarc.new.example")]["content"].startswith("v=DMARC1; p=none")
    assert mail[("TXT", "mail._domainkey.new.example")]["content"] == DKIM_TXT
    assert c["steps"]["mail"]["state"] == "ok", c["steps"]["mail"]
    assert {r["type"] for r in c["mail_records"]} == {"MX", "TXT"} and c["mail_records"][-1]["content"] == DKIM_TXT
    # d) apply by the host → links + telegram, transition
    st = boss.post(f"/api/v1/admin/domain/{cid}/apply/", format="json").json()
    assert st["change"]["status"] == "applying"
    req = host_done(env, "apply", message="live on https://new.example")
    assert req["mail"] is True and req["old_domain"] == "old.example" and req["transition_days"] == 14 and req["zone"] == "new.example"
    (env["dir"] / ".domain-state.json").write_text(json.dumps({"domain": "new.example", "old_domain": "old.example", "previous_domain": "old.example"}))
    st = boss.get("/api/v1/admin/domain/").json()
    c = st["change"]
    assert c["status"] == "transition" and c["steps"]["apply"]["state"] == "ok" and c["steps"]["links"]["state"] == "ok"
    assert SiteConfig.load().site_domain == "new.example" and EmailSettings.load().from_email == "no-reply@new.example"
    assert env["menu"] == [{"text": "🌐 اپ", "url": "https://new.example"}]
    assert st["current"]["domain"] == "new.example" and st["rollback"]["to"] == "old.example"
    # f) checklist
    assert st["checklist_keys"] == ["shortcut", "sms_app", "botfather", "ptr", "notify"]
    boss.post(f"/api/v1/admin/domain/{cid}/checklist/", {"key": "ptr", "done": True}, format="json")
    assert DomainChange.objects.get(pk=cid).checklist == {"ptr": True}
    assert boss.post(f"/api/v1/admin/domain/{cid}/checklist/", {"key": "nope", "done": True}, format="json").status_code == 400
    # e) transition over → the beat task asks the host to remove the old domain
    D.tick()
    assert not (env["dir"] / ".domain-request.json").exists()
    DomainChange.objects.filter(pk=cid).update(old_until=timezone.now() - timedelta(minutes=1))
    D.tick()
    host_done(env, "retire", message="old.example removed")
    st = boss.get("/api/v1/admin/domain/").json()
    assert st["change"]["status"] == "done" and st["change"]["steps"]["transition"]["state"] == "ok"
    # rollback → old domain, links back
    st = boss.post("/api/v1/admin/domain/rollback/", format="json").json()
    assert st["pending"]["action"] == "rollback"
    req = host_done(env, "rollback", message="back on https://old.example")
    assert req["domain"] == "old.example" and req["from"] == "new.example"
    st = boss.get("/api/v1/admin/domain/").json()
    assert st["change"]["status"] == "rolled_back" and SiteConfig.load().site_domain == "old.example"
    assert env["menu"][-1]["url"] == "https://old.example"
    acts = set(AuditLog.objects.filter(action__startswith="domain.").values_list("action", flat=True))
    assert {"domain.started", "domain.dns_records", "domain.dns_checked", "domain.tls_requested", "domain.host_cert_ok",
            "domain.apply_requested", "domain.host_apply_ok", "domain.links_updated", "domain.retire_requested",
            "domain.host_retire_ok", "domain.rollback_requested", "domain.host_rollback_ok", "domain.checklist",
            "domain.mail_records", "domain.mail_checked"} <= acts


@responses.activate
def test_manual_dns_failures_and_validation(env, boss):
    assert "valid domain" in boss.post("/api/v1/admin/domain/start/", {"domain": "not a domain", "mode": "manual"}, format="json").json()["detail"]
    assert "already" in boss.post("/api/v1/admin/domain/start/", {"domain": "old.example", "mode": "manual"}, format="json").json()["detail"]
    assert "No Cloudflare token" in boss.post("/api/v1/admin/domain/start/", {"domain": "n.example"}, format="json").json()["detail"]
    c = boss.post("/api/v1/admin/domain/start/", {"domain": "n.example", "mode": "manual", "include_www": False}, format="json").json()["change"]
    assert [r["name"] for r in c["records"]] == ["n.example", "mail.n.example"]
    assert [(r["type"], r["name"]) for r in c["mail_records"]] == [("MX", "n.example"), ("TXT", "n.example"), ("TXT", "_dmarc.n.example"), ("TXT", "mail._domainkey.n.example")]
    s = boss.post(f"/api/v1/admin/domain/{c['id']}/dns/", format="json").json()["change"]["steps"]["dns"]
    assert s["state"] == "waiting" and "DNS provider" in s["message"]
    assert not responses.calls                                  # manual: nothing called yet
    answers = {"n.example": [IP]}
    mock_dns(answers)
    assert boss.post(f"/api/v1/admin/domain/{c['id']}/dns-check/", format="json").json()["change"]["steps"]["dns"]["state"] == "waiting"
    answers["mail.n.example"] = [IP]
    assert boss.post(f"/api/v1/admin/domain/{c['id']}/dns-check/", format="json").json()["change"]["steps"]["dns"]["state"] == "ok"
    boss.post(f"/api/v1/admin/domain/{c['id']}/tls/", format="json")
    host_done(env, "cert", ok_=False, message="certificate not issued: Detail: 203.0.113.7: Fetching http://n.example/.well-known/acme-challenge/x: Timeout")
    st = boss.get("/api/v1/admin/domain/").json()["change"]["steps"]["tls"]
    assert st["state"] == "failed" and "Timeout" in st["message"]
    assert st["detail"]["error"]["key"] == "le_port80" and "port 80" in st["detail"]["error"]["en"]
    assert boss.get("/api/v1/admin/domain/").json()["last"]["explain"]["key"] == "le_port80"
    boss.post(f"/api/v1/admin/domain/{c['id']}/tls/", format="json")
    write_dkim(env, "n.example")
    host_done(env, "cert")
    st = boss.get("/api/v1/admin/domain/").json()["change"]
    assert st["steps"]["mail"]["state"] == "waiting" and "MX n.example" in st["steps"]["mail"]["message"]
    assert "mail records" in boss.post(f"/api/v1/admin/domain/{c['id']}/apply/", format="json").json()["detail"]
    # the admin adds them at the DNS provider (quoted / split as resolvers answer)
    answers[("n.example", "MX")] = ["10 mail.n.example."]
    answers[("n.example", "TXT")] = ['"google-site-verification=x"', f'"v=spf1 ip4:{IP} mx ~all"']
    answers[("_dmarc.n.example", "TXT")] = ['"v=DMARC1; p=none; adkim=r; aspf=r"']
    answers[("mail._domainkey.n.example", "TXT")] = ['"' + DKIM_TXT[:255] + '" "' + DKIM_TXT[255:] + '"']
    assert boss.post(f"/api/v1/admin/domain/{c['id']}/mail-check/", format="json").json()["change"]["steps"]["mail"]["state"] == "ok"
    assert not [x for x in responses.calls if "cloudflare" in x.request.url]   # manual: Cloudflare never called
    boss.post(f"/api/v1/admin/domain/{c['id']}/apply/", format="json")
    host_done(env, "apply", ok_=False, message="rolled back to old.example: https://n.example/api/v1/health/ answered 400")
    st = boss.get("/api/v1/admin/domain/").json()
    assert st["change"]["status"] == "draft" and "answered 400" in st["change"]["steps"]["apply"]["message"]
    assert st["change"]["steps"]["apply"]["detail"]["error"]["key"] == "apply_health"
    assert SiteConfig.load().site_domain == "old.example" and not env["menu"] and st["rollback"] is None
    assert "Nothing to roll back" in boss.post("/api/v1/admin/domain/rollback/", format="json").json()["detail"]
    assert boss.post(f"/api/v1/admin/domain/{c['id']}/cancel/", format="json").json()["change"]["status"] == "cancelled"
    assert AuditLog.objects.filter(action="domain.host_apply_failed").exists()
    # settings
    assert boss.post("/api/v1/admin/domain/settings/", {"transition_days": 120}, format="json").status_code == 400
    assert boss.post("/api/v1/admin/domain/settings/", {"transition_days": 7}, format="json").json()["transition_days"] == 7


def cf_fail(status, *errors, chain=None):
    errs = [{"code": c, "message": m, **({"error_chain": chain} if chain else {})} for c, m in errors]
    return {"status": status, "json": {"success": False, "result": None, "errors": errs}}


@responses.activate
@pytest.mark.parametrize("status,errors,chain,key", [
    (403, [(10000, "Authentication error")], None, "cf_perm"),
    (403, [(9109, "Unauthorized to access requested resource")], None, "cf_perm"),
    (400, [(6003, "Invalid request headers")], None, "cf_perm"),
    (400, [(6003, "Invalid request headers")], [{"code": 6111, "message": "Invalid format for Authorization header"}], "cf_invalid"),
    (401, [(1000, "Invalid API Token")], None, "cf_invalid"),
    (403, [(9109, "Invalid access token")], None, "cf_invalid"),
    (403, [(9109, "Cannot use the access token from location: 203.0.113.7")], None, "cf_ip"),
    (404, [(7003, "Could not route to /zones/x/dns_records, perhaps your object identifier is invalid?")], None, "cf_zone"),
    (429, [(971, "Please wait and consider throttling your request speed")], None, "cf_rate"),
    (400, [(81057, "Record already exists.")], None, "cf_exists"),
    (400, [(81053, "An A, AAAA, or CNAME record with that host already exists.")], None, "cf_cname"),
    (400, [(9005, "Content for A record must be a valid IPv4 address.")], None, "cf_record"),
    (502, [], None, "cf_down"),
])
def test_cloudflare_codes_explained(env, status, errors, chain, key):
    from apps.ops.cloudflare import Cloudflare, CloudflareError
    from apps.settings_app import domain_errors as E

    responses.add(responses.GET, f"{CF}/zones", **cf_fail(status, *errors, chain=chain))
    with pytest.raises(CloudflareError) as ei:
        Cloudflare(TOKEN).zones()
    info = E.cloudflare(ei.value, zone="new.example", name="www.new.example", ip=IP)
    assert info["key"] == key, info
    assert info["en"] and info["fa"] and info["en"] != info["fa"]
    for c, m in errors:                                              # the raw code + message stay visible
        assert f"{c}: {m}" in info["raw"]
    if key == "cf_perm":
        assert info["fa"].startswith("توکن اجازهٔ ویرایش DNS در دامنهٔ new.example را ندارد") and "Zone Resources شامل new.example" in info["fa"]
    if key == "cf_ip":
        assert IP in info["en"] and "Client IP Address Filtering" in info["en"]
    if key == "cf_cname":
        assert "www.new.example" in info["fa"]


def test_dns_and_host_messages_explained():
    from apps.settings_app import domain_errors as E

    def r(*ips):
        return [{"resolver": "a.test", "ips": list(ips)}, {"resolver": "b.test", "ips": list(ips)}]

    assert E.dns_host("n.example", IP, r(IP)) is None
    assert E.dns_host("n.example", IP, r())["key"] == "dns_none"
    assert E.dns_host("n.example", IP, r("104.21.3.4", "172.67.1.2"))["key"] == "dns_proxied"
    assert E.dns_host("n.example", IP, r("198.51.100.9"))["key"] == "dns_wrong"
    assert E.dns_host("n.example", IP, [{"resolver": "a.test", "ips": [IP]}, {"resolver": "b.test", "ips": []}])["key"] == "dns_partial"
    assert E.dns_host("n.example", IP, [{"resolver": "a.test", "ips": [], "error": "ConnectTimeout"}])["key"] == "dns_doh"
    cases = {
        ("cert", "certificate not issued: Type: rateLimited Detail: too many certificates (5) already issued"): "le_rate",
        ("cert", "certificate not issued: Detail: DNS problem: NXDOMAIN looking up A for n.example"): "le_dns",
        ("cert", "certificate not issued: Detail: CAA record for n.example prevents issuance"): "le_caa",
        ("cert", "certificate not issued: Type: connection Detail: 203.0.113.7: Fetching http://n.example/.well-known/acme-challenge/x: Timeout during connect"): "le_port80",
        ("cert", "certificate not issued: Type: unauthorized Detail: Invalid response from http://n.example/.well-known/acme-challenge/x: 404"): "le_challenge",
        ("cert", "certificate ok, but no DKIM key: the mail server is not running"): "dkim_fail",
        ("cert", "a manually uploaded certificate is active (nginx/manual-certs) — remove it first"): "manual_cert",
        ("cert", "certificate not issued: something odd"): "le_other",
        ("apply", 'rolled back to old.example: nginx -t rejected the config: nginx: [emerg] unknown directive "x"'): "nginx_test",
        ("apply", "rolled back to old.example: https://n.example/api/v1/health/ answered 502"): "apply_health",
        ("apply", "rolled back to old.example: the mail server answers as 'mail.old.example', not mail.n.example"): "apply_mail",
        ("apply", "rolled back to old.example: web: the new container never became healthy"): "apply_container",
        ("apply", "not switched: the certificate does not cover mail.n.example"): "le_check",
        ("apply", "rejected: the site is on x.example, not old.example"): "apply_moved",
        ("rollback", "rolled back to new.example: https://old.example does not redirect to new.example"): "apply_redirect",
        ("apply", "rolled back to old.example: Timeout"): "apply_other",
    }
    for (action, msg), key in cases.items():
        info = E.host(action, msg, "n.example", IP)
        assert info["key"] == key, (msg, info)
        assert info["raw"] == msg and info["fa"]


@responses.activate
def test_zone_checked_before_dns_and_friendly_failures(env, boss):
    DomainConfig.objects.update_or_create(pk=1, defaults={"cloudflare_token": TOKEN})
    store = mock_cf(dns_edit=False)
    c = boss.post("/api/v1/admin/domain/start/", {"domain": "new.example"}, format="json").json()["change"]
    r = boss.post(f"/api/v1/admin/domain/{c['id']}/dns/", format="json")
    d = r.json()
    assert r.status_code == 400 and d["error"]["key"] == "cf_perm" and d["error"]["raw"] == "10000: Authentication error"
    assert d["detail_fa"].startswith("توکن اجازهٔ ویرایش DNS در دامنهٔ new.example را ندارد")
    s = d["change"]["steps"]["dns"]
    assert s["state"] == "failed" and s["detail"]["zone_check"]["dns_edit"] is False and s["detail"]["error"]["key"] == "cf_perm"
    assert not store                                                     # nothing written
    assert AuditLog.objects.filter(action="domain.dns_failed").exists()
    # the token may edit, but www is a CNAME: the error names the record and the fix
    responses.reset()
    store = mock_cf(refuse={"www.new.example": (400, 81053, "An A, AAAA, or CNAME record with that host already exists.")})
    d = boss.post(f"/api/v1/admin/domain/{c['id']}/dns/", format="json").json()
    assert d["error"]["key"] == "cf_cname" and "www.new.example" in d["detail"] and "81053" in d["error"]["raw"]
    assert d["change"]["steps"]["dns"]["detail"]["zone_check"]["dns_edit"] is True
    assert [r["name"] for r in store.values()] == ["new.example"]        # the zone check's TXT record was deleted again


@responses.activate
def test_mail_check_explains_each_record(env, boss):
    c = boss.post("/api/v1/admin/domain/start/", {"domain": "m.example", "mode": "manual", "include_www": False}, format="json").json()["change"]
    answers = {"m.example": [IP], "mail.m.example": [IP]}
    mock_dns(answers)
    boss.post(f"/api/v1/admin/domain/{c['id']}/dns-check/", format="json")
    boss.post(f"/api/v1/admin/domain/{c['id']}/tls/", format="json")
    write_dkim(env, "m.example")
    answers[("m.example", "MX")] = ["10 mx.oldmail.example."]
    answers[("m.example", "TXT")] = [f'"v=spf1 ip4:{IP} mx ~all"', '"v=spf1 include:_spf.brevo.com ~all"']
    answers[("_dmarc.m.example", "TXT")] = ['"v=DMARC1; p=none; adkim=r; aspf=r"']
    answers[("mail._domainkey.m.example", "TXT")] = ['"v=DKIM1; k=rsa; p=OLDKEY"']
    host_done(env, "cert")
    step = boss.get("/api/v1/admin/domain/").json()["change"]["steps"]["mail"]
    rows = {(h["type"], h["name"]): h for h in step["detail"]["hosts"]}
    assert step["state"] == "waiting" and step["detail"]["error"]["key"] == "mail_mx"
    assert rows[("MX", "m.example")]["why"]["key"] == "mail_mx" and "mx.oldmail.example" in rows[("MX", "m.example")]["why"]["en"]
    assert rows[("TXT", "m.example")]["why"]["key"] == "spf_multi"
    assert rows[("TXT", "_dmarc.m.example")]["ok"] and rows[("TXT", "_dmarc.m.example")]["why"] is None
    dk = rows[("TXT", "mail._domainkey.m.example")]["why"]
    assert dk["key"] == "mail_diff" and "DKIM" in dk["en"] and "OLDKEY" in dk["raw"]
