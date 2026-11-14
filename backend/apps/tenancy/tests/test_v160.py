"""v1.60 — store domains as five steps with a «stuck» alert; stores follow our theme; white-label SMS tools (setup code, no
brand, no iPhone file); store service management (own services only, reseller-owned PasarGuard users only, quota guard,
codes opt-in)."""
import importlib
from datetime import timedelta
from decimal import Decimal

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from apps.accounts.models import Permission, User
from apps.agency.models import PanelAdmin
from apps.panel.exceptions import PanelNotFound
from apps.panel.models import Panel, Service, ServiceStatus
from apps.payments_sms.device_url import parse_setup_code, setup_code
from apps.payments_sms.models import SmsAppDevice
from apps.plans.models import Plan
from apps.settings_app.models import TenantBranding, Theme
from apps.tenancy import context, domains
from apps.tenancy import staff as S
from apps.tenancy.models import Tenant, TenantDomain
from apps.tenancy.tests.test_phase8 import _boss, _client

pytestmark = pytest.mark.django_db
GB = 1024 ** 3
HOST, HOST_B = "shop-v160.example", "other-v160.example"
SVC = "/api/v1/admin/services/"


@pytest.fixture
def codes(_default_tenant):
    for c in sorted(S.STORE_CODES | {"agency.manage", "agency.view", "themes.manage", "services.delete", "monitoring.view"}):
        Permission.objects.get_or_create(code=c, defaults={"name": c})


@pytest.fixture
def panel(_default_tenant):
    return Panel.objects.create(name="OURPANELNAME", base_url="https://panel.test", admin_username="adm",
                                admin_password_enc="pw", is_active=True)


def _mk_store(slug, host, reseller, ceiling=None):
    t = Tenant.objects.create(slug=slug, name=f"Store {slug}", status="active", reseller_username=reseller,
                              permission_ceiling=sorted(ceiling if ceiling is not None else S.STORE_CODES))
    TenantDomain.objects.create(tenant=t, host=host, state="active")
    PanelAdmin.objects.get_or_create(username=reseller, defaults={"has_data_limit": True, "admin_limit_bytes": 100 * GB,
                                                                  "admin_remaining": 50 * GB})
    return t


def _owner(t, host, crm=True):
    owner, _ = S.ensure_owner(t, f"own-{t.slug}")
    return _client(owner, host)


# ------------------------------------------------------------------ 1) domain steps + stuck alert
def _dom(t, state, **kw):
    return TenantDomain.objects.create(tenant=t, host=f"{state}-{t.slug}.example", state=state, **kw)


def test_domain_steps_follow_the_walk(codes):
    t = _mk_store("dsteps", HOST, "rs-steps")
    d = _dom(t, "pending_dns", last_error="TXT not found")
    st = domains.steps(d, {})
    assert [x["key"] for x in st] == ["dns", "cert", "nginx", "health", "active"]
    assert st[0]["state"] == "error" and st[0]["error"] == "TXT not found" and st[1]["state"] == "waiting"

    d.state, d.verified_at, d.retry_token = "cert_pending", timezone.now(), 2
    assert domains.stage_of(d, {"retry": 1})["waiting_watcher"]                       # watcher has not seen the retry
    st = domains.steps(d, {"retry": 2, "cert_ok": True, "nginx_ok": False, "nginx_error": "nginx -t failed", "nginx_at": "x"})
    assert [x["state"] for x in st] == ["done", "done", "error", "waiting", "waiting"] and st[2]["error"] == "nginx -t failed"
    st = domains.steps(d, {"retry": 2, "cert_ok": True, "nginx_ok": True})
    assert [x["state"] for x in st][:4] == ["done", "done", "done", "current"]

    d.state, d.cert_issued_at, d.health = "active", timezone.now(), {"ok": True, "at": "now"}
    assert [x["state"] for x in domains.steps(d, {})] == ["done"] * 5
    d.health = {"ok": False, "error": "timeout", "at": "now"}
    st = domains.steps(d, {})
    assert st[3]["state"] == "error" and st[3]["error"] == "timeout"
    # the store's own view: the steps, never our raw errors
    assert all(x["error"] == "" for x in domains.row(d, {}, staff=False)["steps"])


def test_a_domain_stuck_on_one_step_alerts_us_once(codes, monkeypatch, django_capture_on_commit_callbacks):
    from apps.common import staff_alert

    sent = []
    monkeypatch.setattr(staff_alert, "alert_staff", lambda text, **kw: sent.append((text, kw)) or 1)
    t = _mk_store("dstuck", HOST, "rs-stuck")
    d = _dom(t, "cert_pending", verified_at=timezone.now())
    st = {"retry": 0, "cert_ok": False, "cert_error": "too many requests"}
    now = timezone.now()
    with django_capture_on_commit_callbacks(execute=True):
        domains._track_stage(d, st, now)                                  # enters «cert»
        domains._track_stage(d, st, now + timedelta(minutes=10))          # not yet
    assert d.stage == "cert" and not sent
    with django_capture_on_commit_callbacks(execute=True):
        domains._track_stage(d, st, now + timedelta(minutes=16))
        domains._track_stage(d, st, now + timedelta(minutes=30))          # once per step
    assert len(sent) == 1 and "گواهی" in sent[0][0] and "too many requests" in sent[0][0] and sent[0][1]["platform"] is True
    with django_capture_on_commit_callbacks(execute=True):                # next step resets the clock
        domains._track_stage(d, {"retry": 0, "cert_ok": True, "nginx_ok": False}, now + timedelta(minutes=31))
    d.refresh_from_db()
    assert d.stage == "nginx" and d.stage_alerted == ""


def test_store_card_says_why_it_is_not_reachable(codes):
    from apps.tenancy import stores

    t = _mk_store("dwhy", HOST, "rs-why")
    Tenant.objects.filter(pk=t.pk).update(status="draft")
    TenantDomain.objects.filter(tenant=t).update(state="cert_pending")
    t.refresh_from_db()
    row = stores.row(t)
    assert not row["reachable"] and row["unreachable_because"] == ["store_inactive", "no_active_domain"]
    assert "steps" in row["domains"][0]


# ------------------------------------------------------------------ 2) themes: stores follow ours
@pytest.fixture
def themes(_default_tenant):
    a = Theme.objects.create(name="Alpha", palette={"style": "caspian"}, is_active=True)
    b = Theme.objects.create(name="Beta", palette={"style": "aurora"})
    return a, b


def test_a_store_cannot_manage_themes(codes, themes):
    t = _mk_store("tth", HOST, "rs-th")
    assert "themes.manage" not in S.STORE_CODES
    with pytest.raises(S.StaffError):
        S.set_ceiling(t, ["themes.manage"])
    c = _owner(t, HOST)
    assert c.get("/api/v1/admin/themes/").status_code in (403, 404)
    assert c.post(f"/api/v1/admin/themes/{themes[1].id}/activate/").status_code in (403, 404)


def test_stores_follow_our_theme_unless_we_pin_one(codes, themes):
    from rest_framework.test import APIClient

    a, b = themes
    t = _mk_store("tfol", HOST, "rs-fol")
    with context.tenant_context(t.pk):
        own = Theme.objects.create(name="StoreOwn", palette={"style": "x"}, tenant=t)
        TenantBranding.objects.create(site_name_fa="s", theme=own)                  # a theme a store picked before v1.60
    pub = lambda: APIClient(HTTP_HOST=HOST).get("/api/v1/theme/").json()["name"]  # noqa: E731
    assert pub() == "Alpha"                                                         # its own theme is ignored → ours
    b.is_active = True
    b.save()                                                                        # we switch ours → the store follows
    assert pub() == "Beta"
    boss = _boss()
    url = f"/api/v1/admin/agency/panel-admins/{t.reseller_username}/store/theme/"
    assert boss.put(url, {"theme": own.id}, format="json").status_code == 400       # never a store's own theme
    r = boss.put(url, {"theme": a.id}, format="json")
    assert r.status_code == 200 and r.json()["override"] == a.id
    assert pub() == "Alpha"                                                         # pinned
    assert boss.put(url, {"theme": None}, format="json").json()["follows"] is True
    assert pub() == "Beta"


def test_theme_migration_strips_the_code_and_resets_stores(codes, themes):
    from apps.accounts.models import Role

    t = _mk_store("tmig", HOST, "rs-mig", ceiling=sorted(S.STORE_CODES))
    Tenant.objects.filter(pk=t.pk).update(permission_ceiling=sorted(S.STORE_CODES | {"themes.manage"}))
    role = Role.objects.create(tenant=t, name="r1")
    role.permissions.add(Permission.objects.get(code="themes.manage"))
    with context.tenant_context(t.pk):
        TenantBranding.objects.create(site_name_fa="s", theme=themes[1])
    mig = importlib.import_module("apps.tenancy.migrations.0012_stores_follow_our_theme")
    mig.forwards(django_apps, None)
    t.refresh_from_db()
    assert "themes.manage" not in t.permission_ceiling and not role.permissions.filter(code="themes.manage").exists()
    with context.tenant_context(t.pk):
        assert TenantBranding.objects.get().theme_id is None


# ------------------------------------------------------------------ 3) white-label SMS tools
def test_setup_code_round_trip():
    code = setup_code("https://shop.example/", "tok-123")
    assert code.startswith("SMS1:") and "=" not in code
    assert parse_setup_code(code) == {"u": "https://shop.example", "t": "tok-123"}
    with pytest.raises(ValueError):
        parse_setup_code("hello")


@pytest.fixture
def releases(settings, tmp_path):
    settings.APP_RELEASES_DIR = str(tmp_path)
    return tmp_path


def test_store_apps_page_is_white_label(codes, releases):
    (releases / "CaspinTunelSmsBridge-debug.apk").write_bytes(b"old")
    t = _mk_store("apps", HOST, "rs-apps")
    c = _owner(t, HOST)
    with context.tenant_context(t.pk):
        dev = SmsAppDevice.objects.create(name="phone")
    r = c.get("/api/v1/admin/apps/")
    assert r.status_code == 200
    body = r.content.decode().lower()
    assert "caspin" not in body and "icloud.com" not in body
    rows = {x["platform"]: x for x in r.json()["results"]}
    assert rows["android"]["source"] is None                                   # the old (branded) APK is never offered
    assert rows["ios"]["endpoint"] == f"https://{HOST}/api/v1/payments/sms/inbound/"
    assert c.get("/api/v1/admin/apps/android/download/").status_code == 404
    assert c.get("/api/v1/admin/apps/ios/download/").status_code == 404
    code = c.get(f"/api/v1/admin/sms-devices/{dev.id}/setup-code/").json()["code"]
    assert parse_setup_code(code) == {"u": f"https://{HOST}", "t": dev.api_token}
    # once the white-label build is in release/, the store downloads it under a neutral name
    (releases / "sms-confirm-2.0.0.apk").write_bytes(b"new")
    row = {x["platform"]: x for x in c.get("/api/v1/admin/apps/").json()["results"]}["android"]
    assert row["file_name"] == "sms-confirm.apk" and row["version"] == "2.0.0"
    from apps.adminpanel.views.apps import _info

    ours = _info("android")                       # our page: the new build is not flagged as «نسخهٔ قدیمی»
    assert ours["whitelabel"] is True and ours["version"] == "2.0.0" and ours["file_name"] == "sms-confirm-2.0.0.apk"
    d = c.get("/api/v1/admin/apps/android/download/")
    assert d.status_code == 200 and 'filename="sms-confirm.apk"' in d["Content-Disposition"]


# ------------------------------------------------------------------ 4) store services
class FakePG:
    """A PasarGuard stand-in: users by name with their owner admin."""

    def __init__(self):
        self.users, self.calls = {}, []

    def add(self, name, owner, gb=10):
        self.users[name] = {"username": name, "status": "active", "data_limit": gb * GB, "used_traffic": 0, "expire": None,
                            "subscription_url": f"/sub/{name}", "note": "", "admin": {"username": owner}, "group_ids": []}

    def get_user(self, name):
        self.calls.append(("get", name))
        if name not in self.users:
            raise PanelNotFound(name)
        return dict(self.users[name])

    def create_user(self, payload):
        self.calls.append(("create", payload["username"]))
        self.add(payload["username"], "adm")
        return dict(self.users[payload["username"]])

    def set_owner(self, name, owner):
        self.calls.append(("set_owner", name, owner))
        self.users[name]["admin"] = {"username": owner}
        return dict(self.users[name])

    def update_user(self, name, payload):
        self.calls.append(("update", name, payload))
        self.users[name].update(payload)
        return dict(self.users[name])

    def delete_user(self, name):
        self.calls.append(("delete", name))
        self.users.pop(name, None)

    def list_users(self, search="", limit=20, offset=0, admin=None):
        self.calls.append(("list", search, tuple(admin or ())))
        rows = [u for u in self.users.values() if search in u["username"]]
        return rows, len(rows)


@pytest.fixture
def world(codes, panel, monkeypatch):
    from apps.agency import panel_api
    from apps.panel import services as panel_services

    pg = FakePG()
    monkeypatch.setattr(panel_services, "client_for", lambda p: pg)
    monkeypatch.setattr("apps.adminpanel.views.ops.client_for", lambda p: pg)
    monkeypatch.setattr(panel_api, "agency_panel", lambda: panel)
    x = _mk_store("svx", HOST, "resx")
    y = _mk_store("svy", HOST_B, "resy")
    out = {"pg": pg, "x": x, "y": y, "panel": panel}
    ours = User.objects.create_user("our_buyer", "Str0ngPass!")
    out["ours_svc"] = Service.objects.create(user=ours, panel=panel, panel_username="ours_acc", status=ServiceStatus.ACTIVE)
    for t, m in ((x, "x"), (y, "y")):
        with context.tenant_context(t.pk):
            u = User.objects.create_user(f"{m}_buyer", "Str0ngPass!")
            out[f"{m}_user"] = u
            out[f"{m}_plan"] = Plan.objects.create(panel=panel, name_fa=f"{m} plan", price=Decimal("100000"),
                                                   duration_days=30, data_limit=10 * GB)
            out[f"{m}_svc"] = Service.objects.create(user=u, panel=panel, panel_username=f"{m}_acc", status=ServiceStatus.ACTIVE)
    return out


def test_service_codes_are_opt_in(world):
    t = world["x"]
    assert {"services.view", "services.manage", "services.link", "services.create", "payments.manual_invoice"} <= S.OPT_IN_CODES
    assert not (S.OPT_IN_CODES & set(S.DEFAULT_CEILING)) and "services.delete" not in S.STORE_CODES
    S.set_ceiling(t, S.DEFAULT_CEILING)
    c = _owner(t, HOST)
    assert c.get(SVC).status_code == 403
    assert c.get(f"/api/v1/admin/users/{world['x_user'].id}/manual-invoices/options/").status_code == 403


def test_a_store_sees_and_edits_only_its_own_services(world):
    c = _owner(world["x"], HOST)
    r = c.get(SVC, {"limit": 200})
    assert r.status_code == 200
    names = {s["panel_username"] for s in r.json()["results"]}
    assert names == {"x_acc"} and all(s["panel_name"] is None for s in r.json()["results"])
    for other in (world["y_svc"], world["ours_svc"]):
        assert c.get(f"{SVC}{other.id}/").status_code == 404
        assert c.post(f"{SVC}{other.id}/sync/").status_code == 404
        assert c.patch(f"{SVC}{other.id}/", {"note": "x"}, format="json").status_code == 404
    assert c.delete(f"{SVC}{world['x_svc'].id}/").status_code == 403                     # never delete from a store
    assert c.post(f"{SVC}{world['x_svc'].id}/reset/").status_code == 403
    assert c.patch(f"{SVC}{world['x_svc'].id}/", {"group_ids": [1]}, format="json").status_code == 400
    world["pg"].add("x_acc", "resx")
    ok = c.patch(f"{SVC}{world['x_svc'].id}/", {"note": "hello"}, format="json")
    assert ok.status_code == 200, ok.content


def test_link_only_the_resellers_own_users(world):
    pg, c = world["pg"], _owner(world["x"], HOST)
    pg.add("mine1", "resx")
    pg.add("theirs1", "resy")
    pg.add("ourpg1", "adm")
    rows = c.get(f"{SVC}panel-users/", {"search": ""}).json()["results"]
    assert {r["username"] for r in rows} == {"mine1"}                                     # filtered by owner
    assert ("list", "", ("resx",)) in pg.calls                                            # asked with admin=<reseller>
    body = {"panel_username": "theirs1", "user": world["x_user"].id, "confirm_other_admin": True}
    assert c.post(f"{SVC}link/", body, format="json").status_code == 403                  # another admin's user
    assert c.post(f"{SVC}link/", {**body, "panel_username": "ourpg1"}, format="json").status_code == 403
    assert c.post(f"{SVC}link/", {**body, "user": world["y_user"].id, "panel_username": "mine1"}, format="json").status_code == 400
    r = c.post(f"{SVC}link/", {**body, "panel_username": "mine1"}, format="json")
    assert r.status_code == 201, r.content
    with context.tenant_context(world["x"].pk):
        assert Service.objects.filter(panel_username="mine1", user=world["x_user"]).exists()
    # already linked by another store → refused without saying whose
    pg.add("y_acc", "resx")
    r = c.post(f"{SVC}link/", {**body, "panel_username": "y_acc"}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "linked_elsewhere" and "y_buyer" not in r.content.decode()


def test_manual_create_under_the_reseller_with_the_quota_guard(world):
    pg, c = world["pg"], _owner(world["x"], HOST)
    body = {"user": world["x_user"].id, "plan": world["x_plan"].id, "account_name": "x_new1"}
    r = c.post(SVC, body, format="json")
    assert r.status_code == 201, r.content
    assert ("set_owner", "x_new1", "resx") in pg.calls and pg.users["x_new1"]["admin"]["username"] == "resx"
    assert c.post(SVC, {**body, "plan": world["y_plan"].id, "account_name": "x_new2"}, format="json").status_code == 400
    PanelAdmin.objects.filter(username="resx").update(admin_remaining=1 * GB)              # short → 409, nothing on PasarGuard
    before = len(pg.calls)
    r = c.post(SVC, {**body, "account_name": "x_new3"}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "quota" and "x_new3" not in pg.users
    assert not any(k[0] == "create" for k in pg.calls[before:])


def test_store_manual_invoice_uses_the_store_s_own_plans(world):
    c = _owner(world["x"], HOST)
    r = c.get(f"/api/v1/admin/users/{world['x_user'].id}/manual-invoices/options/")
    assert r.status_code == 200
    assert {p["id"] for p in r.json()["plans"]} == {world["x_plan"].id}
    assert c.get(f"/api/v1/admin/users/{world['y_user'].id}/manual-invoices/options/").status_code == 404


def test_our_panel_keeps_its_own_service_rules(world):
    boss = _boss()
    names = {s["panel_username"] for s in boss.get(SVC, {"limit": 200}).json()["results"]}
    assert names == {"ours_acc"}
