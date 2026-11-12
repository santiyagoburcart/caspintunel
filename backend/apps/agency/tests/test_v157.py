"""v1.57 — (1) «فروش» = charges + adjustments is THE sales figure (no gross charges anywhere), «اصلاحیه‌ها» only as an
information total (count + debt decreases / increases); (3) accounting filters (admin, group, «فقط بدهکارها», sort by debt,
pages) with the collapsed summary (debt, last payment, unpaid invoices); (4) «گواهی‌های SSL» on Monitoring; (5) the sidebar
accordion's per-staff memory (auth/me/prefs `nav_open`)."""
from datetime import datetime, timedelta, timezone as dt_tz
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.agency import history, ledger, managers, reports
from apps.agency.models import AdminGroup, AgencyInvoice, LedgerEntry, PanelAdmin
from apps.common.models import AuditLog
from apps.ops import ssl_certs as S
from apps.ops.models import SslCertificate
from apps.panel.models import Panel
from apps.payments_sms.tests.test_blu import staff_client
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db
GB = 1024 ** 3


@pytest.fixture(autouse=True)
def setup():
    cache.clear()
    set_setting("agency_sync_enabled", True, ValueType.BOOL)
    Panel.objects.create(name="sigma", base_url="https://sigma.test:8443", admin_username="u", admin_password_enc="p", is_active=True)


def _day(n):
    return ledger.today() - timedelta(days=n)


@pytest.fixture
def book():
    """ali: 300,000 T of charges, a 100,000 «کاهش بدهی» (a wrong charge corrected) and a 20,000 «افزایش بدهی», 50,000 paid.
    bea: 100,000 charged, fully paid. cyrus: nothing owed but an unpaid invoice is impossible → only a price."""
    for n in ("ali", "bea", "cyrus"):
        PanelAdmin.objects.create(username=n)
        ledger.set_price(n, 1000, _day(400))
    ledger.record_quota_charge("ali", 0, 300 * GB, by="t", day=_day(3))
    ledger.add_entry("ali", LedgerEntry.KIND_ADJUST, 100000, _day(2), direction="decrease", by="t")
    ledger.add_entry("ali", LedgerEntry.KIND_ADJUST, 20000, _day(1), direction="increase", by="t")
    ledger.add_entry("ali", LedgerEntry.KIND_PAYMENT, 50000, _day(1), method="card", by="t")
    ledger.record_quota_charge("bea", 0, 100 * GB, by="t", day=_day(4))
    ledger.add_entry("bea", LedgerEntry.KIND_PAYMENT, 100000, _day(0), method="card", by="t")
    AdminGroup.objects.create(owner_username="ali", member_usernames="bea", name="North")


# ------------------------------------------------------------------ (1) one sales figure
def test_sales_includes_adjustments_and_they_are_reported_apart(book):
    s = history.summary(["ali"], *history.bounds("d7"))
    assert s["sales"] == Decimal(220000)                                  # 300,000 − 100,000 + 20,000
    assert (s["adjust_count"], s["adjust_down"], s["adjust_up"]) == (2, Decimal(100000), Decimal(20000))
    k = reports.overview(_day(6), _day(0))["kpis"]
    assert k["sales"] == 320000 and k["adjust_count"] == 2 and k["adjust_down"] == 100000 and k["adjust_up"] == 20000
    st = ledger.statement("ali")
    assert st["sales"] == Decimal(220000) and st["balance"] == Decimal(170000) and st["adjust_count"] == 2
    assert {e["kind"] for e in st["entries"]} == {"quota_charge", "adjustment", "payment"}     # «اصلاحیه» is its own row type
    g = managers.group_statement(AdminGroup.objects.get(owner_username="ali"))
    assert g["sales"] == Decimal(320000) and g["adjust_count"] == 2
    rows = managers.admin_summaries(["ali", "bea"])
    a = next(r for r in rows if r["username"] == "ali")
    assert a["sales"] == Decimal(220000) and a["last_payment"] == _day(1) and a["unpaid_invoices"] >= 1


def test_no_gross_column_in_any_export(book):
    texts = []
    texts.append(ledger.statement_csv("ali"))
    cells = lambda rows: [" | ".join(str(c) for c in r) for r in rows]          # noqa: E731
    texts += cells(history.export_rows(history.report(["ali", "bea"], "d7"), "fa"))
    texts += cells(reports.monthly_rows("fa"))
    jy, jm = reports.jkey(ledger.today())
    texts += cells(reports.breakdown_rows(jy, jm, "fa"))
    g = managers.group_statement(AdminGroup.objects.get(owner_username="ali"))
    texts += cells(managers.group_statement_rows(g, "fa"))
    texts += cells(managers.summary_rows(managers.admin_summaries(["ali", "bea"]), "fa"))
    blob = "\n".join(texts)
    assert "ناخالص" not in blob and "gross" not in blob.lower() and "فروش خالص" not in blob
    assert blob.count("اصلاحیه‌ها (فقط اطلاع") >= 3 and "adjustments_info" in blob
    head = history.export_rows(history.report(["ali"], "d7"), "fa")[0]
    assert head[2] == "فروش (تومان)" and not any("اصلاحیه" in c for c in head)       # never a column


def test_this_month_numbers_match_the_ledger(book):
    jy, jm = reports.jkey(ledger.today())
    a, b = reports.jmonth_bounds(jy, jm)
    live = LedgerEntry.objects.filter(voided=False, date__gte=a, date__lte=b)
    charges = sum((e.amount for e in live if e.kind in ("quota_charge", "manual_charge")), Decimal(0))
    adj = sum((e.amount for e in live if e.kind == "adjustment"), Decimal(0))
    k = reports.overview(a, b)["kpis"]
    assert k["sales"] == int(charges + adj) and k["adjust_down"] == int(-sum((e.amount for e in live if e.kind == "adjustment" and e.amount < 0), Decimal(0)))


# ------------------------------------------------------------------ (3) accounting filters
def test_ledger_overview_filters_sort_and_pages(book):
    c = staff_client(["agency.accounting"], "acc")
    url = "/api/v1/admin/agency/ledger/"
    d = c.get(url).json()
    assert {r["username"] for r in d["results"]} == {"ali", "bea", "cyrus"} and d["count"] == 3
    ali = next(r for r in d["results"] if r["username"] == "ali")
    assert ali["last_payment"] == _day(1).isoformat() and ali["unpaid_invoices"] >= 1 and ali["group"]["name"] == "North"
    assert Decimal(str(ali["balance"])) == Decimal(170000)
    d = c.get(url, {"debtors": 1}).json()
    assert [r["username"] for r in d["results"]] == ["ali"] and d["debtors_count"] == 1
    d = c.get(url, {"group": AdminGroup.objects.get().id}).json()
    assert {r["username"] for r in d["results"]} == {"ali", "bea"}
    assert [r["username"] for r in c.get(url, {"q": "BE"}).json()["results"]] == ["bea"]
    assert c.get(url, {"sort": "debt"}).json()["results"][0]["username"] == "ali"
    p = c.get(url, {"page_size": 5, "page": 9}).json()
    assert p["page"] == 1 and p["pages"] == 1 and p["page_size"] == 5
    for i in range(8):
        PanelAdmin.objects.create(username=f"z{i}")
        ledger.set_price(f"z{i}", 1000, _day(400))
    p2 = c.get(url, {"page_size": 5, "page": 3}).json()
    assert p2["pages"] == 3 and len(p2["results"]) == 1 and p2["count"] == 11
    assert staff_client(["agency.view"], "viewer").get(url).status_code == 403


# ------------------------------------------------------------------ (4) SSL certificates
class FakePG:
    def _request(self, method, path, **kw):
        assert method == "GET"
        if path == "/api/hosts":
            return [{"address": ["cdn.example.net"], "security": "tls", "sni": ["cdn.example.net"], "port": 8443, "remark": "a"},
                    {"address": ["203.0.113.5"], "security": "tls", "sni": ["edge.example.net"], "port": 2053, "remark": "b"},
                    {"address": ["wg.example.net"], "security": "inbound_default", "sni": [], "port": None, "remark": "wg"},
                    {"address": ["198.51.100.7"], "security": "inbound_default", "sni": [], "port": None, "remark": "ip"},
                    {"address": ["off.example.net"], "security": "tls", "is_disabled": True, "remark": "off"}]
        if path == "/api/nodes":
            return [{"address": "192.0.2.1", "name": "n1"}]
        raise AssertionError(path)


def test_ssl_targets_from_every_source(monkeypatch, settings):
    monkeypatch.setattr("apps.settings_app.domain.current_domain", lambda: "shop.test")
    monkeypatch.setattr("apps.panel.services.client_for", lambda panel: FakePG())
    t = S.targets()
    keys = set(t["targets"])
    assert {("shop.test", 443, ""), ("www.shop.test", 443, ""), ("sigma.test", 8443, ""), ("cdn.example.net", 8443, ""),
            ("203.0.113.5", 2053, "edge.example.net"), ("wg.example.net", 443, "")} <= keys
    assert not any(k[0] in ("198.51.100.7", "off.example.net", "192.0.2.1") for k in keys)    # IP without a name / disabled / node
    assert t["targets"][("wg.example.net", 443, "")]["expect_tls"] is False
    assert any("addressed by IP" in n for n in t["notes"])


def _res(days=None, ok=True, **kw):
    if not ok:
        return {"ok": False, **kw}
    return {"ok": True, "issuer": "Let's Encrypt", "subject": "x", "not_after": timezone.now() + timedelta(days=days, hours=1),
            "verified": True, "error": "", **kw}


def test_ssl_states_and_alerts_once_per_level(monkeypatch):
    sent = []
    monkeypatch.setattr(S, "_send", lambda text, silent=False: sent.append((text, silent)))
    monkeypatch.setattr(S, "targets", lambda: {"targets": {("a.test", 443, ""): {"sources": [{"kind": "site", "label": "a.test"}],
                                                                                    "expect_tls": True},
                                                           ("wg.test", 443, ""): {"sources": [], "expect_tls": False}}, "notes": []})
    plan = {"a.test": _res(40), "wg.test": _res(ok=False, error="timeout", unreachable=True)}
    monkeypatch.setattr(S, "probe", lambda h, p, sni: plan[h])
    S.run()
    a, wg = SslCertificate.objects.get(host="a.test"), SslCertificate.objects.get(host="wg.test")
    assert (a.state, a.days_left, a.alerted) == ("ok", 40, 0) and wg.state == "no_tls" and sent == []
    plan["a.test"] = _res(20)
    S.run()
    assert SslCertificate.objects.get(host="a.test").state == "soon" and sent == []          # amber, no alert yet
    plan["a.test"] = _res(13)
    S.run(); S.run()
    assert SslCertificate.objects.get(host="a.test").state == "urgent" and len(sent) == 1 and "13" in sent[0][0]
    plan["a.test"] = _res(2)
    S.run(); S.run()
    assert len(sent) == 2 and SslCertificate.objects.get(host="a.test").alerted == 3
    plan["a.test"] = _res(ok=False, error="DNS: nope", unreachable=True)
    S.run(); S.run()
    a = SslCertificate.objects.get(host="a.test")
    assert a.state == "error" and len(sent) == 3 and a.failing_since is not None and a.days_left == 2   # last good values kept
    plan["a.test"] = _res(89)
    S.run()
    a = SslCertificate.objects.get(host="a.test")
    assert a.state == "ok" and a.alerted == 0 and len(sent) == 4 and sent[-1][1] is True     # one silent «OK again»
    plan["a.test"] = _res(-1)
    S.run()
    assert SslCertificate.objects.get(host="a.test").state == "expired" and len(sent) == 5
    monkeypatch.setattr(S, "targets", lambda: {"targets": {}, "notes": []})
    S.run()
    assert not SslCertificate.objects.exists()                                                # gone from every source


def test_ssl_unverified_certificate_is_an_error_where_tls_is_expected():
    r = {"ok": True, "verified": False, "error": "hostname mismatch", "not_after": timezone.now() + timedelta(days=60)}
    assert S.classify(60, r, True) == "error" and S.classify(60, r, False) == "no_tls"
    assert S.classify(31, _res(31), True) == "ok" and S.classify(30, _res(30), True) == "soon"
    assert S.classify(14, _res(14), True) == "soon" and S.classify(13, _res(13), True) == "urgent"


def test_ssl_api_lists_and_checks_now(monkeypatch):
    monkeypatch.setattr(S, "targets", lambda: {"targets": {("a.test", 443, ""): {"sources": [{"kind": "store", "label": "Shop"}],
                                                                                    "expect_tls": True}}, "notes": ["n"]})
    monkeypatch.setattr(S, "probe", lambda h, p, sni: _res(50))
    monkeypatch.setattr(S, "_send", lambda *a, **k: None)
    c = staff_client(["monitoring.view"], "mon")
    assert c.get("/api/v1/admin/monitoring/ssl/").json()["results"] == []
    r = c.post("/api/v1/admin/monitoring/ssl/", {}, format="json")
    assert r.status_code == 202                                               # eager in tests: already checked
    d = c.get("/api/v1/admin/monitoring/ssl/").json()
    assert d["results"][0]["host"] == "a.test" and d["results"][0]["state"] == "ok" and d["notes"] == ["n"] and d["busy"] is False
    assert AuditLog.objects.filter(action="ops.ssl_check").exists()
    assert staff_client(["agency.view"], "nope").get("/api/v1/admin/monitoring/ssl/").status_code == 403


def test_ssl_probe_reads_a_real_handshake_shape(monkeypatch):
    """probe() never raises: a DNS failure is a result, not an exception."""
    out = S.probe("does-not-exist.invalid", 443)
    assert out["ok"] is False and out.get("error")


# ------------------------------------------------------------------ (5) sidebar memory
def test_nav_open_pref_is_validated_and_kept():
    c = staff_client(["monitoring.view"], "nav")
    u = "/api/v1/admin/auth/me/prefs/"
    assert c.get(u).json()["nav_open"] is None
    r = c.patch(u, {"nav_open": {"nav_group_core": True, "nav_group_finance": False}}, format="json")
    assert r.status_code == 200 and r.json()["nav_open"] == {"nav_group_core": True, "nav_group_finance": False}
    assert c.get(u).json()["nav_open"]["nav_group_finance"] is False and c.get(u).json()["sound"] is True
    assert c.patch(u, {"nav_open": {"x": "yes"}}, format="json").status_code == 400
    assert c.patch(u, {"nav_open": ["a"]}, format="json").status_code == 400
    assert c.patch(u, {"nav_open": {f"k{i}": True for i in range(40)}}, format="json").status_code == 400
