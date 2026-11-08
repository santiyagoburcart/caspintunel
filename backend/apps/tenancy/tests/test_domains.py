"""Multi-tenant Phase 3 (v1.45): store domains + TLS (apps/tenancy/domains.py). Our staff add a domain on Agency → admin →
«فروشگاه» and get the exact records (A → Finland / Iran IP, www, TXT); DNS checks (DNS-only and the reseller's Cloudflare
proxy, confirmed by the /.well-known/caspin/<token> probe); the host watcher's results move it to active; failures, retry,
removal, health / expiry alerts; the reseller sees the state read-only; isolation between stores."""
import json
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.agency.models import PanelAdmin
from apps.common.models import AuditLog
from apps.payments_sms.tests.test_blu import staff_client
from apps.settings_app import domain as D
from apps.settings_app.access import instance_id
from apps.settings_app.models import DomainConfig
from apps.tenancy import domains
from apps.tenancy.models import Tenant, TenantDomain

pytestmark = pytest.mark.django_db
FI, IR, CF = "203.0.113.10", "198.51.100.7", "104.16.1.1"
U = "/api/v1/admin/agency/panel-admins/reseller1/store/"


@pytest.fixture
def env(settings, tmp_path, monkeypatch):
    settings.SERVER_IP = FI
    settings.UPDATE_SENTINEL_PATH = str(tmp_path / ".update-requested")
    cfg = DomainConfig.load()
    cfg.iran_ips = [IR]
    cfg.save()
    dns = {}
    monkeypatch.setattr(D, "resolve", lambda name, rtype="A": {"name": name, "resolvers": [
        {"resolver": "dns.test", "ips": list(dns.get((name, rtype), []))}]})
    from apps.settings_app import access

    monkeypatch.setattr(access, "is_cloudflare_ip", lambda ip, cfg=None: ip.startswith("104.16."))
    alerts = []
    from apps.common import staff_alert

    monkeypatch.setattr(staff_alert, "alert_staff", lambda text, **kw: alerts.append(text) or 1)
    return {"dns": dns, "alerts": alerts, "dir": tmp_path}


@pytest.fixture
def store(_default_tenant):
    PanelAdmin.objects.create(username="reseller1")
    from apps.tenancy import stores

    t = stores.enable("reseller1", name="فروشگاه یک")
    Tenant.objects.filter(pk=t.pk).update(status="active")
    return Tenant.objects.get(pk=t.pk)


_N = [0]


def _add(host="shop.example.com", mode="direct", www=True):
    _N[0] += 1
    r = staff_client("super", f"boss-{_N[0]}").post(U + "domains/", {"host": host, "mode": mode, "www": www}, format="json")
    return r


def _point(env, d, ip, *, www=True, txt=True):
    if txt:
        env["dns"][(f"_caspin-verify.{d.host}", "TXT")] = [f'"{d.verify_token}"']
    env["dns"][(d.host, "A")] = [ip]
    if www:
        env["dns"][(f"www.{d.host}", "A")] = [ip]


def _status(env, host, **st):
    p = env["dir"] / ".tenant-status.json"
    cur = json.loads(p.read_text()) if p.exists() else {"hosts": {}}
    cur["hosts"][host] = {"retry": TenantDomain.objects.get(host=host).retry_token, **st}
    p.write_text(json.dumps(cur))


def _desired(env):
    p = env["dir"] / ".tenant-domains.json"
    return [h["host"] for h in json.loads(p.read_text())["hosts"]] if p.exists() else []


# ------------------------------------------------------------------ adding a domain
def test_staff_add_a_domain_and_get_the_exact_records(env, store):
    r = _add("Shop.Example.com/", "direct")
    assert r.status_code == 201, r.content
    d = TenantDomain.objects.get(host="shop.example.com")
    assert d.tenant_id == store.pk and d.state == "pending_dns" and d.include_www
    recs = r.json()["domain"]["instructions"]["records"]
    assert {"type": "A", "name": "shop.example.com", "value": FI, "proxy": "dns_only_or_proxied"} in recs
    assert any(x["name"] == "www.shop.example.com" and x["value"] == FI for x in recs)
    assert {"type": "TXT", "name": "_caspin-verify.shop.example.com", "value": d.verify_token, "proxy": "dns_only"} in recs
    assert AuditLog.objects.filter(action="store.domain_added", target_id=d.pk).exists()
    r2 = _add("tun.example.org", "tunnel", www=False)
    recs2 = r2.json()["domain"]["instructions"]["records"]
    assert recs2[0]["value"] == IR and not any(x["name"].startswith("www.") for x in recs2)


@pytest.mark.parametrize("host,code", [("", 400), ("1.2.3.4", 400), ("not a domain", 400), ("localhost", 400)])
def test_bad_hosts_are_refused(env, store, host, code):
    r = _add(host)
    assert r.status_code == code and r.json()["detail_fa"]


def test_our_own_domain_and_duplicates_are_refused(env, store, settings):
    settings.DOMAIN = "caspintunel.test"
    assert _add("caspintunel.test").status_code == 400
    assert _add("mail.caspintunel.test").status_code == 400
    assert _add("shop.example.com").status_code == 201
    r = _add("shop.example.com")
    assert r.status_code == 409 and "همین فروشگاه" in r.json()["detail_fa"]
    other = Tenant.objects.create(slug="other", name="Other", status="active", reseller_username="r2")
    with pytest.raises(domains.DomainError) as exc:
        domains.add(other, "www.shop.example.com")
    assert exc.value.status == 409 and "فروشگاه دیگری" in exc.value.fa


def test_tunnel_mode_needs_an_iran_ip_and_the_default_store_is_refused(env, store, _default_tenant):
    cfg = DomainConfig.load()
    cfg.iran_ips = []
    cfg.save()
    r = _add("tun.example.org", "tunnel")
    assert r.status_code == 400 and r.json()["field"] == "mode"
    with pytest.raises(domains.DomainError) as exc:
        domains.add(_default_tenant, "x.example.com")
    assert exc.value.status == 403


def test_only_agency_manage_may_change_domains(env, store):
    viewer = staff_client(["agency.view"], "dviewer")
    assert viewer.post(U + "domains/", {"host": "a.example.com"}, format="json").status_code == 403
    assert _add("a.example.com").status_code == 201
    d = TenantDomain.objects.get(host="a.example.com")
    assert viewer.delete(f"{U}domains/{d.pk}/").status_code == 403
    assert viewer.get(U).json()["store"]["domains"][0]["host"] == "a.example.com"


# ------------------------------------------------------------------ the probe endpoint
def test_probe_answers_for_a_registered_host_even_before_it_is_live(env, store):
    _add("shop.example.com")
    d = TenantDomain.objects.get(tenant=store)
    for host in ("shop.example.com", "www.shop.example.com", "shop.example.com:80"):
        r = APIClient(HTTP_HOST=host).get(f"/.well-known/caspin/{d.verify_token}")
        assert r.status_code == 200 and r.content.decode() == d.verify_token, host
        assert r["X-Caspin-Instance"] == instance_id() and r["Cache-Control"] == "no-store"
    assert APIClient(HTTP_HOST="shop.example.com").get("/.well-known/caspin/" + "x" * 32).status_code == 404
    assert APIClient(HTTP_HOST="other.example.com").get(f"/.well-known/caspin/{d.verify_token}").status_code == 404
    assert APIClient(HTTP_HOST="shop.example.com").post(f"/.well-known/caspin/{d.verify_token}").status_code == 404
    assert APIClient(HTTP_HOST="shop.example.com").get("/api/v1/config/").status_code in (400, 404)   # not live yet
    domains.remove(d)
    assert APIClient(HTTP_HOST="shop.example.com").get(f"/.well-known/caspin/{d.verify_token}").status_code == 404


# ------------------------------------------------------------------ DNS → certificate → active
def test_dns_only_direct_walks_to_active(env, store, django_capture_on_commit_callbacks, monkeypatch):
    _add("shop.example.com")
    d = TenantDomain.objects.get(tenant=store)
    domains.tick()
    d.refresh_from_db()
    assert d.state == "pending_dns" and "TXT" in d.last_error and _desired(env) == []
    _point(env, d, FI)
    TenantDomain.objects.filter(pk=d.pk).update(last_check_at=None)
    domains.tick()
    d.refresh_from_db()
    assert d.state == "cert_pending" and d.verified_at and not d.proxied and d.last_error == ""
    assert _desired(env) == ["shop.example.com"]
    want = json.loads((env["dir"] / ".tenant-domains.json").read_text())["hosts"][0]
    assert want["www"] is True and want["token"] == d.verify_token and want["tenant"] == store.pk
    # the host watcher issued the certificate and wrote the vhost; health over TLS passes → active
    _status(env, d.host, cert_ok=True, nginx_ok=True, cert_expires=(timezone.now() + timedelta(days=89)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    monkeypatch.setattr(domains, "health", lambda d: {"ok": True, "at": "x", "ip": FI, "status": 200, "error": ""})
    with django_capture_on_commit_callbacks(execute=True):
        domains.tick()
    d.refresh_from_db()
    assert d.state == "active" and d.cert_expires_at and d.cert_issued_at
    assert any("فعال شد" in a for a in env["alerts"])
    cfg = APIClient(HTTP_HOST="shop.example.com").get("/api/v1/config/").json()
    assert cfg["site_name_fa"] == "فروشگاه یک"
    assert APIClient(HTTP_HOST="www.shop.example.com").get("/api/v1/config/").json()["site_name_fa"] == "فروشگاه یک"


def test_wrong_a_record_stays_pending_with_the_reason(env, store):
    _add("shop.example.com")
    d = TenantDomain.objects.get(tenant=store)
    _point(env, d, "192.0.2.99")
    domains.tick()
    d.refresh_from_db()
    assert d.state == "pending_dns" and "192.0.2.99" in d.last_error and FI in d.last_error


def test_tunnel_mode_expects_the_iran_ip(env, store):
    _add("tun.example.org", "tunnel", www=False)
    d = TenantDomain.objects.get(tenant=store)
    _point(env, d, FI, www=False)
    domains.tick()
    d.refresh_from_db()
    assert d.state == "pending_dns"
    _point(env, d, IR, www=False)
    TenantDomain.objects.filter(pk=d.pk).update(last_check_at=None)
    domains.tick()
    d.refresh_from_db()
    assert d.state == "cert_pending"


def test_proxied_by_their_cloudflare_needs_the_probe_to_reach_us(env, store, monkeypatch):
    _add("shop.example.com")
    d = TenantDomain.objects.get(tenant=store)
    _point(env, d, CF)
    seen = []
    monkeypatch.setattr(domains, "reach", lambda host, token, **kw: seen.append(host) or
                        {"ok": False, "url": f"http://{host}/x", "error": "HTTP 526"})
    domains.tick()
    d.refresh_from_db()
    assert d.state == "pending_dns" and d.proxied and "HTTP 526" in d.last_error and seen == ["shop.example.com"]
    monkeypatch.setattr(domains, "reach", lambda host, token, **kw: {"ok": True, "url": "u", "error": ""})
    TenantDomain.objects.filter(pk=d.pk).update(last_check_at=None)
    domains.tick()
    d.refresh_from_db()
    assert d.state == "cert_pending" and d.proxied


def test_dns_is_not_rechecked_more_than_every_5_minutes(env, store, monkeypatch):
    _add("shop.example.com")
    calls = []
    real = domains.check_dns
    monkeypatch.setattr(domains, "check_dns", lambda d: calls.append(1) or real(d))
    domains.tick()
    domains.tick()
    assert len(calls) == 1


# ------------------------------------------------------------------ certificate failures, retry, removal
def _verified(env, host="shop.example.com"):
    _add(host)
    d = TenantDomain.objects.get(host=host)
    _point(env, d, FI)
    domains.tick()
    d.refresh_from_db()
    assert d.state == "cert_pending"
    return d


def test_three_lets_encrypt_failures_fail_it_and_retry_brings_it_back(env, store, django_capture_on_commit_callbacks):
    d = _verified(env)
    _status(env, d.host, cert_ok=False, challenge_ok=False, challenge_error="http://shop/… no answer", challenge_at="2026-01-01T00:00:00Z")
    domains.tick()
    d.refresh_from_db()
    assert d.state == "cert_pending" and d.cert_failures == 0 and "no answer" in d.last_error     # pre-check: free
    for i in range(3):
        _status(env, d.host, cert_ok=False, cert_error="Type: unauthorized Detail: 404", cert_tried_at=f"2026-01-01T0{i + 1}:00:00Z")
        with django_capture_on_commit_callbacks(execute=True):
            domains.tick()
    d.refresh_from_db()
    assert d.state == "failed" and d.cert_failures == 3 and "unauthorized" in d.last_error
    assert _desired(env) == [] and any("صادر نشد" in a for a in env["alerts"])
    r = staff_client("super", "retry-boss").post(f"{U}domains/{d.pk}/check/")
    assert r.status_code == 200, r.content
    d.refresh_from_db()
    assert d.state == "cert_pending" and d.cert_failures == 0 and d.retry_token == 1
    assert _desired(env) == ["shop.example.com"]
    _status(env, d.host, cert_ok=False, cert_error="old", cert_tried_at="2026-01-01T05:00:00Z", retry=0)
    domains.tick()                                                     # a status from before the retry is ignored
    d.refresh_from_db()
    assert d.cert_failures == 0


def test_remove_stops_the_store_answering_and_the_host_can_be_reused(env, store, monkeypatch):
    d = _verified(env)
    TenantDomain.objects.filter(pk=d.pk).update(state="active")
    from apps.tenancy.middleware import forget_hosts

    forget_hosts(store.pk)
    assert APIClient(HTTP_HOST=d.host).get("/api/v1/config/").status_code == 200
    r = staff_client("super", "rm-boss").delete(f"{U}domains/{d.pk}/")
    assert r.status_code == 200 and r.json()["store"]["domains"] == []
    d.refresh_from_db()
    assert d.state == "removed" and _desired(env) == []
    assert APIClient(HTTP_HOST=d.host).get("/api/v1/config/").status_code == 404
    assert AuditLog.objects.filter(action="store.domain_removed", target_id=d.pk).exists()
    other = Tenant.objects.create(slug="other", name="Other", status="active", reseller_username="r2")
    d2 = domains.add(other, d.host)
    assert d2.tenant_id == other.pk and d2.verify_token != d.verify_token


def test_www_change_on_an_active_domain_needs_a_new_certificate(env, store):
    d = _verified(env)
    TenantDomain.objects.filter(pk=d.pk).update(state="active")
    r = staff_client("super", "www-boss").patch(f"{U}domains/{d.pk}/", {"www": False}, format="json")
    assert r.status_code == 200
    d.refresh_from_db()
    assert d.state == "cert_pending" and not d.include_www
    r = staff_client("super", "mode-boss").patch(f"{U}domains/{d.pk}/", {"mode": "tunnel"}, format="json")
    d.refresh_from_db()
    assert d.state == "pending_dns" and d.mode == "tunnel" and d.verified_at is None


# ------------------------------------------------------------------ health + expiry on active domains
def test_unhealthy_for_30_minutes_and_expiring_certificates_alert(env, store, monkeypatch, django_capture_on_commit_callbacks):
    d = _verified(env)
    soon = timezone.now() + timedelta(days=10)
    TenantDomain.objects.filter(pk=d.pk).update(state="active", last_check_at=None, cert_expires_at=soon,
                                                unhealthy_since=timezone.now() - timedelta(minutes=31),
                                                dns={"at": timezone.now().isoformat()})
    monkeypatch.setattr(domains, "health", lambda d: {"ok": False, "at": "x", "error": "TLS: certificate not valid"})
    with django_capture_on_commit_callbacks(execute=True):
        domains.tick()
    d.refresh_from_db()
    assert d.state == "active" and d.unhealthy_since and "TLS" in d.last_error
    assert any("در دسترس نیست" in a for a in env["alerts"]) and any("منقضی" in a for a in env["alerts"])
    monkeypatch.setattr(domains, "health", lambda d: {"ok": True, "at": "x", "error": ""})
    TenantDomain.objects.filter(pk=d.pk).update(last_check_at=None)
    domains.tick()
    d.refresh_from_db()
    assert d.unhealthy_since is None and d.last_error == ""


# ------------------------------------------------------------------ reseller view + isolation
def test_reseller_sees_only_their_own_domains_read_only(env, store):
    d = _verified(env)
    TenantDomain.objects.filter(pk=d.pk).update(state="active", last_error="internal detail")
    other = Tenant.objects.create(slug="other", name="Other", status="active", reseller_username="r2")
    TenantDomain.objects.create(tenant=other, host="other-store.example.net", state="active")
    from apps.tenancy.middleware import forget_hosts

    forget_hosts(store.pk)
    boss = staff_client("super", "store-view")
    boss.defaults["HTTP_HOST"] = d.host
    dash = boss.get("/api/v1/admin/dashboard/").json()
    assert [x["host"] for x in dash["domains"]] == [d.host]
    row = dash["domains"][0]
    assert "instructions" not in row and "last_error" not in row and "dns" not in row and row["state"] == "active"
    # the domain endpoints are platform pages: never on a store's domain
    assert boss.post(U + "domains/", {"host": "x.example.com"}, format="json").status_code in (403, 404)
    assert boss.get(U).status_code in (403, 404)


def test_desired_file_has_only_verified_live_domains(env, store):
    d = _verified(env)
    _add("pending.example.com")
    TenantDomain.objects.create(tenant=store, host="gone.example.com", state="removed", verified_at=timezone.now())
    domains.write_desired()
    assert _desired(env) == [d.host]
