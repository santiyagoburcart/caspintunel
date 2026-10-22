"""CRM: lifecycle stages, inactivity detection + cases, ticket linking, case
actions, leads, reports, customer 360, permissions."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff, User
from apps.adminpanel.tokens import issue_tokens
from apps.crm import services as S
from apps.crm.models import CaseReason, CrmEvent, FollowUpCase, MessageTemplate
from apps.notifications.models import NotificationDelivery
from apps.orders.models import Order
from apps.panel.models import Panel, Service
from apps.plans.models import Plan
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting
from apps.tickets import services as TS
from apps.tickets.models import Ticket, TicketTopic

pytestmark = pytest.mark.django_db
NOW = timezone.now


def staff(name, perms=(), superadmin=False):
    role = None
    if perms:
        role = Role.objects.create(name=f"r-{name}")
        role.permissions.set([Permission.objects.get_or_create(code=c, defaults={"name": c})[0] for c in perms])
    s = Staff(username=name, role=role, is_superadmin=superadmin)
    s.set_password("x-Str0ng!")
    s.save()
    return s


def client_for(s):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


@pytest.fixture
def panel():
    return Panel.objects.create(name="p", base_url="https://p.test", admin_username="a", admin_password_enc="x")


def customer(username="ali", **kw):
    return User.objects.create_user(username, "Str0ngPass!", **kw)


def buy(u, panel, *, days_ago=40, status="active", online=None, expire_in=20, created_ago=None, synced=True):
    plan = Plan.objects.create(name_fa="ماهانه", name_en="Monthly", price=100000, data_limit=50 * 1024 ** 3, duration_days=30, panel=panel)
    o = Order.objects.create(user=u, plan=plan, type="new", amount=100000, amount_unique=100000 + Order.objects.count() + 1,
                             unique_expire_at=NOW(), status="completed")
    Order.objects.filter(pk=o.pk).update(created_at=NOW() - timedelta(days=days_ago))
    s = Service.objects.create(user=u, panel=panel, panel_username=f"{u.username}_{Service.objects.count()}", status=status,
                               online_at=online, expire_at=NOW() + timedelta(days=expire_in) if expire_in is not None else None,
                               data_limit=50 * 1024 ** 3, last_synced_at=NOW() if synced else NOW() - timedelta(days=3))
    if created_ago is not None:
        Service.objects.filter(pk=s.pk).update(created_at=NOW() - created_ago)
        s.refresh_from_db()
    return s


# --- stages --------------------------------------------------------------------------------
def test_stages(panel):
    lead = customer("lead")
    assert S.refresh_stage(lead).stage == "lead"
    new = customer("new")
    buy(new, panel, days_ago=2, online=NOW())
    assert S.refresh_stage(new).stage == "new"
    act = customer("act")
    buy(act, panel, days_ago=40, online=NOW())
    assert S.refresh_stage(act).stage == "active"
    risky = customer("risky")
    buy(risky, panel, days_ago=40, online=NOW(), expire_in=1)
    assert S.refresh_stage(risky).stage == "at_risk"
    exp = customer("exp")
    buy(exp, panel, status="expired", expire_in=-5)
    assert S.refresh_stage(exp).stage == "expired"
    ch = customer("ch")
    s = buy(ch, panel, days_ago=90, status="expired", expire_in=-45)
    p = S.refresh_stage(ch)
    assert p.stage == "churned"
    # buys again → won back, and the change is logged
    s.status, s.expire_at, s.online_at = "active", NOW() + timedelta(days=30), NOW()
    s.save()
    assert S.refresh_stage(ch).stage == "won_back"
    assert CrmEvent.objects.filter(user=ch, kind="stage", detail__new="won_back").exists()
    # manual override wins until cleared
    p = S.profile(lead)
    p.stage_override = "churned"
    p.save()
    assert S.profile(lead).effective_stage == "churned"


# --- detection ------------------------------------------------------------------------------
def test_detection_opens_one_case_per_service_and_ignores_stale_sync(panel):
    a = customer("a")
    idle = buy(a, panel, online=NOW() - timedelta(days=5))
    b = customer("b")
    never = buy(b, panel, status="on_hold", online=None, created_ago=timedelta(hours=60))
    c = customer("c")
    buy(c, panel, status="on_hold", online=None, created_ago=timedelta(hours=10))           # too early
    d = customer("d")
    buy(d, panel, online=NOW() - timedelta(days=9), synced=False)                           # stale sync: no case
    e = customer("e")
    buy(e, panel, online=NOW() - timedelta(hours=5))                                        # fine
    out = S.detect_inactivity()
    assert out["opened"] == 2
    kinds = dict(FollowUpCase.objects.values_list("service_id", "kind"))
    assert kinds == {idle.id: "no_connection", never.id: "never_connected"}
    assert S.detect_inactivity()["opened"] == 0                                             # no duplicates
    assert S.profile(a).stage == "at_risk"


def test_reconnect_closes_case_by_system(panel):
    u = customer()
    s = buy(u, panel, online=NOW() - timedelta(days=5))
    S.detect_inactivity()
    case = FollowUpCase.objects.get()
    s.online_at = NOW()
    s.save()
    out = S.detect_inactivity()
    case.refresh_from_db()
    assert out["closed"] == 1 and case.status == "closed" and case.outcome == "resolved" and case.closed_by_system


def test_thresholds_are_settings(panel):
    set_setting("crm_inactive_days", 10, ValueType.INT)
    u = customer()
    buy(u, panel, online=NOW() - timedelta(days=5))
    assert S.detect_inactivity()["opened"] == 0


def test_auto_message_off_by_default_then_on(panel):
    u = customer(telegram_id=77)
    buy(u, panel, online=NOW() - timedelta(days=8))
    S.detect_inactivity()
    assert not NotificationDelivery.objects.filter(user=u).exists()
    set_setting("crm_auto_message", True, ValueType.BOOL)
    assert S.detect_inactivity()["messaged"] == 1
    n = NotificationDelivery.objects.filter(user=u, channel="site").get().notification
    assert u.username in n.body or "👋" in n.body
    assert "{" not in n.body
    assert S.detect_inactivity()["messaged"] == 0                                           # once per case


# --- tickets ↔ cases -----------------------------------------------------------------------------
def test_connection_ticket_links_open_case(panel, django_capture_on_commit_callbacks):
    u = customer()
    buy(u, panel, online=NOW() - timedelta(days=5))
    S.detect_inactivity()
    conn = TicketTopic.objects.get(name_en="Connection problem")
    with django_capture_on_commit_callbacks(execute=True):
        t = TS.open_ticket(u, topic_id=conn.id, subject="no internet", body="help")
    assert FollowUpCase.objects.get().ticket == t
    other = TicketTopic.objects.get(name_en="Other")
    with django_capture_on_commit_callbacks(execute=True):
        TS.open_ticket(u, topic_id=other.id, subject="x", body="y")
    assert FollowUpCase.objects.get().ticket == t


def test_case_actions_reason_message_ticket_close(panel, django_capture_on_commit_callbacks):
    u = customer(telegram_id=55)
    buy(u, panel, status="on_hold", online=None, created_ago=timedelta(hours=72))
    S.detect_inactivity()
    case = FollowUpCase.objects.get()
    agent = staff("agent", ["crm.view", "crm.manage", "tickets.view"])
    c = client_for(agent)
    reason = CaseReason.objects.get(name_en="App not installed", category="inactivity")
    r = c.patch(f"/api/v1/admin/crm/cases/{case.id}/", {"reason": reason.id, "notes": "called, no app", "assigned_to": agent.id}, format="json")
    assert r.json()["reason"]["name_en"] == "App not installed" and r.json()["assigned_to"]["username"] == "agent"
    tpl = MessageTemplate.objects.get(category="inactivity")
    r = c.post(f"/api/v1/admin/crm/cases/{case.id}/message/", {"template": tpl.id, "via_site": True, "via_bot": False}, format="json")
    assert r.status_code == 200
    body = NotificationDelivery.objects.filter(user=u).last().notification.body
    assert u.username in body and "{" not in body
    with django_capture_on_commit_callbacks(execute=True):
        r = c.post(f"/api/v1/admin/crm/cases/{case.id}/ticket/", {"subject": "Let's get you connected", "body": "Which phone do you use?"}, format="json")
    assert r.status_code == 201
    t = Ticket.objects.get(user=u)
    assert r.json()["ticket"]["number"] == t.number and t.status == "awaiting_user" and t.messages.get().author_staff == agent
    assert c.post(f"/api/v1/admin/crm/cases/{case.id}/ticket/", {"subject": "x", "body": "y"}, format="json").status_code == 409
    r = c.post(f"/api/v1/admin/crm/cases/{case.id}/close/", {"outcome": "resolved", "note": "installed the app"}, format="json")
    assert r.json()["status"] == "closed" and r.json()["outcome"] == "resolved" and r.json()["closed_by"]["username"] == "agent"
    assert c.post(f"/api/v1/admin/crm/cases/{case.id}/close/", {"outcome": "lost"}, format="json").status_code == 409
    kinds = list(CrmEvent.objects.filter(case=case).values_list("kind", flat=True))
    assert {"case_opened", "case_updated", "message", "ticket", "case_closed"} <= set(kinds)


# --- permissions, 360, leads, reports -------------------------------------------------------------
def test_permissions_and_ticketing_role_has_crm_view(panel):
    from django.core.management import call_command

    call_command("seed")
    assert Role.objects.get(name="Ticketing").permissions.filter(code="crm.view").exists()
    u = customer()
    viewer = client_for(staff("viewer", ["crm.view"]))
    assert viewer.get(f"/api/v1/admin/crm/customers/{u.id}/").status_code == 200
    assert viewer.post(f"/api/v1/admin/crm/customers/{u.id}/notes/", {"body": "x"}, format="json").status_code == 403
    assert client_for(staff("nobody", ["users.view"])).get("/api/v1/admin/crm/cases/").status_code == 403


def test_customer_360_and_timeline(panel):
    u = customer(phone="09120000000")
    buy(u, panel, online=NOW())
    m = staff("mgr", ["crm.view", "crm.manage"])
    c = client_for(m)
    r = c.post("/api/v1/admin/crm/tags/", {"name": "VIP", "color": "#ff0000"}, format="json")
    tag = r.json()["id"]
    r = c.patch(f"/api/v1/admin/crm/customers/{u.id}/", {"owner": m.id, "tags": [tag], "stage_override": "at_risk"}, format="json")
    assert r.json()["owner"]["username"] == "mgr" and r.json()["effective_stage"] == "at_risk"
    c.post(f"/api/v1/admin/crm/customers/{u.id}/notes/", {"body": "prefers bot"}, format="json")
    d = c.get(f"/api/v1/admin/crm/customers/{u.id}/").json()
    assert d["user"]["phone"] == "09120000000" and d["money"]["orders"] == 1 and d["payments"] is None
    assert d["services"][0]["status"] == "active" and d["notes"][0]["body"] == "prefers bot"
    assert d["tickets"]["rows"] == []                       # no tickets.view → no ticket rows
    kinds = [x["kind"] for x in c.get(f"/api/v1/admin/crm/customers/{u.id}/timeline/").json()]
    assert {"signup", "order", "crm_owner", "crm_tags", "crm_stage", "crm_note"} <= set(kinds)
    d = client_for(staff("fin", ["crm.view", "payment.view"])).get(f"/api/v1/admin/crm/customers/{u.id}/").json()
    assert d["payments"] == []


def test_leads_list(panel):
    lead = customer("lead1")
    buyer = customer("buyer")
    buy(buyer, panel)
    pre = TicketTopic.objects.get(requires_active_service=False)
    TS.open_ticket(lead, topic_id=pre.id, subject="price?", body="how much")
    c = client_for(staff("v", ["crm.view", "crm.manage"]))
    rows = c.get("/api/v1/admin/crm/leads/").json()["results"]
    assert [r["username"] for r in rows] == ["lead1"] and rows[0]["pre_tickets"] == 1
    assert c.get("/api/v1/admin/crm/leads/?q=nobody").json()["count"] == 0
    r = c.post(f"/api/v1/admin/crm/customers/{lead.id}/cases/", {"kind": "lead", "notes": "call tomorrow"}, format="json")
    assert r.status_code == 201
    assert c.get("/api/v1/admin/crm/leads/").json()["results"][0]["open_cases"] == 1


def test_reports(panel):
    u = customer()
    buy(u, panel, online=NOW() - timedelta(days=5))
    S.detect_inactivity()
    case = FollowUpCase.objects.get()
    S.update_case(case, None, reason_id=CaseReason.objects.get(name_en="Price", category="inactivity").id)
    S.close(case, None, "lost")
    d = client_for(staff("v", ["crm.view"])).get("/api/v1/admin/crm/reports/?days=30").json()
    assert d["opened"] == 1 and d["outcomes"] == {"lost": 1} and d["by_reason"][0]["reason"]["name_en"] == "Price"
    assert d["resolve_hours"]["count"] == 1 and d["closed_by_system"] == 1


def test_settings_reasons_templates(panel):
    c = client_for(staff("m", ["crm.view", "crm.manage"]))
    s = c.patch("/api/v1/admin/crm/settings/", {"crm_inactive_days": 999, "crm_auto_message": True, "crm_guide_url": "ftp://x"}, format="json")
    assert s.status_code == 400
    s = c.patch("/api/v1/admin/crm/settings/", {"crm_inactive_days": 999, "crm_auto_message": True}, format="json").json()["settings"]
    assert s["crm_inactive_days"] == 60 and s["crm_auto_message"] is True
    assert len(c.get("/api/v1/admin/crm/reasons/?category=inactivity").json()) == 7
    assert [x["username"] for x in c.get("/api/v1/admin/crm/staff/").json()] == ["m"]
    r = c.post("/api/v1/admin/crm/reasons/", {"name_fa": "زمان", "name_en": "Time"}, format="json")
    assert r.status_code == 201
    used = CaseReason.objects.get(name_en="Price", category="inactivity")
    FollowUpCase.objects.create(user=customer(), kind="manual", reason=used)
    assert c.delete(f"/api/v1/admin/crm/reasons/{used.id}/").status_code == 409
    assert c.delete(f"/api/v1/admin/crm/reasons/{r.json()['id']}/").status_code == 204
    t = c.post("/api/v1/admin/crm/templates/", {"title": "x", "body_fa": "سلام {name}"}, format="json").json()
    u = customer("reza", name="رضا")
    assert c.get(f"/api/v1/admin/crm/customers/{u.id}/templates/{t['id']}/preview/").json()["body_fa"] == "سلام رضا"
