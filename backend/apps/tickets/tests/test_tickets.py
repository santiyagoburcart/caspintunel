"""Ticketing core: rules enforced in the API, RBAC + topic scopes, attachments,
history, notifications, auto-close / reopen, staff Telegram linking."""
import io
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff, User
from apps.adminpanel.tokens import issue_tokens
from apps.notifications.models import NotificationDelivery
from apps.panel.models import Panel, Service
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting
from apps.tickets import notify, rules, services, staff_link
from apps.tickets.models import EventKind, Ticket, TicketAttachment, TicketStatus, TicketTopic

pytestmark = pytest.mark.django_db
CODES = ["tickets.view", "tickets.reply", "tickets.assign", "tickets.close", "tickets.manage_topics"]


# --- helpers ------------------------------------------------------------------
@pytest.fixture
def topics():
    pre = TicketTopic.objects.get(name_en="Pre-purchase questions")
    conn = TicketTopic.objects.get(name_en="Connection problem")
    pay = TicketTopic.objects.get(name_en="Payment problem")
    return {"pre": pre, "conn": conn, "pay": pay}


def customer(name="ali", active=False):
    u = User.objects.create_user(name, "Str0ngPass!")
    if active:
        panel = Panel.objects.first() or Panel.objects.create(name="p", base_url="https://p.test",
                                                              admin_username="a", admin_password_enc="x")
        Service.objects.create(user=u, panel=panel, panel_username=f"{name}_svc", status="active")
    return u


def user_client(u):
    c = APIClient()
    c.force_authenticate(u)
    return c


def staff(name, codes=(), superadmin=False, topics=(), **kw):
    role = None
    if codes:
        role = Role.objects.create(name=f"r-{name}")
        role.permissions.set([Permission.objects.get_or_create(code=c, defaults={"name": c})[0] for c in codes])
    s = Staff(username=name, role=role, is_superadmin=superadmin, **kw)
    s.set_password("Str0ngPass!")
    s.save()
    if topics:
        s.ticket_topics.set(topics)
    return s


def staff_client(s):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


def png(name="shot.png", size=(8, 8)):
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def open_via_api(u, topic, **extra):
    data = {"topic": topic.id, "subject": "no internet", "body": "please help", **extra}
    return user_client(u).post("/api/v1/tickets/", data, format="multipart")


@pytest.fixture
def pushes(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "_push", lambda s, kind, t: sent.append((s.username, kind, t.number)))
    return sent


@pytest.fixture
def bot(monkeypatch):
    msgs = []

    class Fake:
        def send_message(self, chat_id, text, **kw):
            msgs.append((chat_id, text))

        def get_me(self):
            return {"username": "caspin_bot"}

    monkeypatch.setattr("apps.telegram.config.sales_client", lambda: Fake())
    return msgs


# --- topics + the active-service rule ------------------------------------------
def test_seeded_topics_and_only_pre_purchase_without_service(topics):
    assert TicketTopic.objects.count() == 5
    assert list(TicketTopic.objects.filter(requires_active_service=False).values_list("name_fa", flat=True)) \
        == ["سوالات قبل از خرید"]
    r = user_client(customer()).get("/api/v1/tickets/topics/").json()
    assert r["has_active_service"] is False and [t["name_en"] for t in r["topics"]] == ["Pre-purchase questions"]
    r = user_client(customer("bea", active=True)).get("/api/v1/tickets/topics/").json()
    assert r["has_active_service"] is True and len(r["topics"]) == 5


def test_api_refuses_service_topic_without_active_service(topics):
    u = customer()
    r = open_via_api(u, topics["conn"])
    assert r.status_code == 403 and r.json()["code"] == "needs_active_service"
    assert not Ticket.objects.exists()
    # an expired service is not an active one
    Service.objects.create(user=u, panel=Panel.objects.create(name="p", base_url="https://p.test",
                                                              admin_username="a", admin_password_enc="x"),
                           panel_username="old", status="expired")
    assert open_via_api(u, topics["conn"]).status_code == 403
    assert open_via_api(u, topics["pre"]).status_code == 201


def test_inactive_topic_refused(topics):
    topics["pre"].is_active = False
    topics["pre"].save()
    r = open_via_api(customer(), topics["pre"])
    assert r.status_code == 400 and r.json()["code"] == "topic"


def test_open_ticket_numbering_history_and_open_limit(topics, pushes):
    set_setting("tickets_max_open_per_user", 2, ValueType.INT)
    u = customer(active=True)
    r = open_via_api(u, topics["conn"])
    assert r.status_code == 201
    d = r.json()
    t = Ticket.objects.get(pk=d["id"])
    assert t.number == str(100000 + t.id) and d["status"] == "open" and t.source == "site"
    assert [m["author"] for m in d["messages"]] == ["user"]
    assert list(t.events.values_list("kind", flat=True)) == [EventKind.CREATED]
    assert open_via_api(u, topics["conn"]).status_code == 201
    r = open_via_api(u, topics["pay"])
    assert r.status_code == 409 and r.json()["code"] == "too_many_open"


def test_related_service_must_be_mine(topics):
    u, other = customer(active=True), customer("bea", active=True)
    svc = Service.objects.get(user=other)
    r = open_via_api(u, topics["conn"], service=svc.id)
    assert r.status_code == 400 and r.json()["code"] == "service"


# --- the conversation ------------------------------------------------------------
def test_reply_cycle_statuses_first_response_and_auto_assign(topics, pushes, bot, django_capture_on_commit_callbacks):
    u = customer(active=True)
    u.telegram_id = 555
    u.save()
    s = staff("sara", CODES)
    with django_capture_on_commit_callbacks(execute=True):
        t = Ticket.objects.get(pk=open_via_api(u, topics["conn"]).json()["id"])
    assert ("sara", "new_ticket", t.number) in pushes

    sc = staff_client(s)
    with django_capture_on_commit_callbacks(execute=True):
        r = sc.post(f"/api/v1/admin/tickets/{t.id}/reply/", {"body": "restart the app"}, format="multipart")
    assert r.status_code == 201
    t.refresh_from_db()
    assert t.status == TicketStatus.AWAITING_USER and t.first_response_at and t.assigned_to == s
    # the customer is notified on site + bot + email
    channels = set(NotificationDelivery.objects.filter(user=u).values_list("channel", flat=True))
    assert channels == {"site", "bot", "email"}
    assert any(chat == 555 and t.number in text for chat, text in bot)

    with django_capture_on_commit_callbacks(execute=True):
        r = user_client(u).post(f"/api/v1/tickets/{t.id}/reply/", {"body": "still down"}, format="multipart")
    assert r.status_code == 201
    t.refresh_from_db()
    assert t.status == TicketStatus.AWAITING_ADMIN
    # assigned → only the assignee hears about the reply
    assert pushes[-1] == ("sara", "user_reply", t.number)
    kinds = list(t.events.values_list("kind", flat=True))
    assert kinds == ["created", "assigned", "staff_replied", "user_replied"]
    assert t.events.get(kind="staff_replied").actor_label == "staff:sara"


def test_user_sees_no_internal_notes_and_no_staff_names(topics):
    u = customer(active=True)
    s = staff("sara", CODES)
    t = services.open_ticket(u, topic_id=topics["conn"].id, subject="x", body="hi")
    services.staff_reply(t, s, body="secret: user is abusing", internal=True)
    services.staff_reply(t, s, body="hello")
    d = user_client(u).get(f"/api/v1/tickets/{t.id}/").json()
    assert [m["body"] for m in d["messages"]] == ["hi", "hello"]
    assert all("staff" not in m or m["author"] in ("user", "staff") for m in d["messages"])
    assert "sara" not in str(d)
    sd = staff_client(s).get(f"/api/v1/admin/tickets/{t.id}/").json()
    assert [m["is_internal"] for m in sd["messages"]] == [False, True, False]
    assert sd["messages"][2]["staff"] == "sara"
    # an internal note does not change the status
    assert t.events.filter(kind="internal_note").count() == 1


def test_read_state_per_side(topics):
    u = customer(active=True)
    s = staff("sara", CODES)
    t = services.open_ticket(u, topic_id=topics["conn"].id, subject="x", body="hi")
    services.staff_reply(t, s, body="answer")
    assert user_client(u).get("/api/v1/tickets/").json()["results"][0]["unread"] == 1
    user_client(u).get(f"/api/v1/tickets/{t.id}/")
    assert user_client(u).get("/api/v1/tickets/").json()["results"][0]["unread"] == 0
    assert staff_client(s).get("/api/v1/admin/tickets/").json()["results"][0]["unread"] == 0
    services.user_reply(t, u, body="more")
    assert staff_client(s).get("/api/v1/admin/tickets/").json()["results"][0]["unread"] == 1


def test_closed_ticket_reply_refused_and_reopen_window(topics):
    set_setting("tickets_reopen_days", 3, ValueType.INT)
    u = customer(active=True)
    t = services.open_ticket(u, topic_id=topics["conn"].id, subject="x", body="hi")
    c = user_client(u)
    assert c.post(f"/api/v1/tickets/{t.id}/close/").json()["status"] == "closed"
    t.refresh_from_db()
    assert t.closed_by_kind == "user" and t.closed_by is None
    r = c.post(f"/api/v1/tickets/{t.id}/reply/", {"body": "again"}, format="multipart")
    assert r.status_code == 409 and r.json()["code"] == "closed"
    assert c.post(f"/api/v1/tickets/{t.id}/reopen/").json()["status"] == "awaiting_admin"
    c.post(f"/api/v1/tickets/{t.id}/close/")
    Ticket.objects.filter(pk=t.pk).update(closed_at=timezone.now() - timedelta(days=4))
    r = c.post(f"/api/v1/tickets/{t.id}/reopen/")
    assert r.status_code == 409 and r.json()["code"] == "reopen_expired"
    assert list(t.events.values_list("kind", flat=True)).count("reopened") == 1


def test_auto_close_awaiting_user_after_n_days(topics, django_capture_on_commit_callbacks):
    set_setting("tickets_auto_close_days", 5, ValueType.INT)
    u = customer(active=True)
    s = staff("sara", CODES)
    old = services.open_ticket(u, topic_id=topics["conn"].id, subject="old", body="hi")
    services.staff_reply(old, s, body="try this")
    fresh = services.open_ticket(u, topic_id=topics["pay"].id, subject="fresh", body="hi")
    services.staff_reply(fresh, s, body="try that")
    Ticket.objects.filter(pk=old.pk).update(status_changed_at=timezone.now() - timedelta(days=6))
    from apps.tickets.tasks import auto_close_tickets_task

    with django_capture_on_commit_callbacks(execute=True):
        assert auto_close_tickets_task() == {"closed": 1}
    old.refresh_from_db()
    fresh.refresh_from_db()
    assert old.status == "closed" and old.closed_by_kind == "system" and fresh.status == "awaiting_user"
    assert old.events.filter(kind="auto_closed").exists()
    assert NotificationDelivery.objects.filter(user=u, notification__title__contains=old.number,
                                               channel="site").exists()


def test_seed_registers_auto_close_task_and_ticketing_role():
    from django.core.management import call_command
    from django_celery_beat.models import PeriodicTask

    call_command("seed")
    assert PeriodicTask.objects.get(name="tickets: auto-close stale").task == "apps.tickets.tasks.auto_close_tickets_task"
    role = Role.objects.get(name="Ticketing")
    assert set(role.permissions.values_list("code", flat=True)) == {"tickets.view", "tickets.reply",
                                                                     "tickets.assign", "tickets.close"}
    # an admin's edit to the role survives the next seed
    role.permissions.remove(Permission.objects.get(code="tickets.close"))
    call_command("seed")
    assert "tickets.close" not in set(role.permissions.values_list("code", flat=True))
    assert set(CODES) <= set(Role.objects.get(name="Super Admin").permissions.values_list("code", flat=True))


# --- RBAC + scopes ----------------------------------------------------------------
def test_permissions(topics):
    u = customer(active=True)
    t = services.open_ticket(u, topic_id=topics["conn"].id, subject="x", body="hi")
    nobody = staff_client(staff("nobody", ["users.view"]))
    assert nobody.get("/api/v1/admin/tickets/").status_code == 403
    viewer = staff_client(staff("viewer", ["tickets.view"]))
    assert viewer.get("/api/v1/admin/tickets/").status_code == 200
    assert viewer.post(f"/api/v1/admin/tickets/{t.id}/reply/", {"body": "x"}).status_code == 403
    replier = staff_client(staff("replier", ["tickets.view", "tickets.reply"]))
    r = replier.post(f"/api/v1/admin/tickets/{t.id}/status/", {"status": "closed"})
    assert r.status_code == 403
    assert replier.post(f"/api/v1/admin/tickets/{t.id}/status/", {"status": "on_hold"}).json()["status"] == "on_hold"
    assert replier.post("/api/v1/admin/tickets/topics/", {"name_fa": "a", "name_en": "a"}).status_code == 403
    closer = staff_client(staff("closer", ["tickets.view", "tickets.reply", "tickets.close"]))
    assert closer.post(f"/api/v1/admin/tickets/{t.id}/status/", {"status": "closed"}).json()["status"] == "closed"
    t.refresh_from_db()
    assert t.closed_by.username == "closer" and t.closed_by_kind == "staff"
    # a customer token never reaches the staff API, and a staff token is no customer
    assert user_client(u).get("/api/v1/admin/tickets/").status_code in (401, 403)
    assert closer.get("/api/v1/tickets/").status_code in (401, 403)


def test_topic_scope_limits_inbox_detail_and_assignment(topics, pushes, django_capture_on_commit_callbacks):
    u = customer(active=True)
    conn_only = staff("conn", CODES[:4], topics=[topics["conn"]])
    pay_only = staff("pay", CODES[:4], topics=[topics["pay"]])
    allround = staff("all", CODES[:4])            # no scope rows = every topic
    boss = staff("boss", superadmin=True, topics=[topics["pay"]])
    with django_capture_on_commit_callbacks(execute=True):
        t = services.open_ticket(u, topic_id=topics["conn"].id, subject="x", body="hi")
    assert {p[0] for p in pushes} == {"conn", "all", "boss"}

    def inbox(s):
        return [r["id"] for r in staff_client(s).get("/api/v1/admin/tickets/").json()["results"]]

    assert inbox(conn_only) == [t.id] and inbox(pay_only) == [] and inbox(allround) == [t.id] and inbox(boss) == [t.id]
    assert staff_client(pay_only).get(f"/api/v1/admin/tickets/{t.id}/").status_code == 404
    assert staff_client(pay_only).post(f"/api/v1/admin/tickets/{t.id}/reply/", {"body": "x"}).status_code == 404
    r = staff_client(allround).post(f"/api/v1/admin/tickets/{t.id}/assign/", {"staff": pay_only.id})
    assert r.status_code == 400 and r.json()["code"] == "assignee_scope"
    with django_capture_on_commit_callbacks(execute=True):
        r = staff_client(allround).post(f"/api/v1/admin/tickets/{t.id}/assign/", {"staff": conn_only.id})
    assert r.json()["assigned_to"]["username"] == "conn"
    assert ("conn", "assigned", t.number) in pushes
    ev = t.events.get(kind="assigned")
    assert ev.actor_label == "staff:all" and ev.new_value == "conn"
    assignable = staff_client(allround).get(f"/api/v1/admin/tickets/{t.id}/assignable/").json()
    assert {s["username"] for s in assignable} == {"conn", "all", "boss"}


def test_scope_admin_and_topic_crud(topics):
    mgr = staff_client(staff("mgr", CODES))
    agent = staff("agent", ["tickets.view"])
    r = mgr.put(f"/api/v1/admin/tickets/staff-scopes/{agent.id}/", {"topic_ids": [topics["pay"].id]}, format="json")
    assert r.json()["topic_ids"] == [topics["pay"].id]
    rows = {r["username"]: r for r in mgr.get("/api/v1/admin/tickets/staff-scopes/").json()}
    assert rows["agent"]["topic_ids"] == [topics["pay"].id] and "nobody" not in rows
    new = mgr.post("/api/v1/admin/tickets/topics/", {"name_fa": "فنی", "name_en": "Technical",
                                                      "requires_active_service": False}, format="json").json()
    assert new["requires_active_service"] is False
    assert mgr.patch(f"/api/v1/admin/tickets/topics/{new['id']}/", {"is_active": False}, format="json").json()["is_active"] is False
    services.open_ticket(customer(), topic_id=topics["pre"].id, subject="x", body="y")
    assert mgr.delete(f"/api/v1/admin/tickets/topics/{topics['pre'].id}/").status_code == 409
    assert mgr.delete(f"/api/v1/admin/tickets/topics/{new['id']}/").status_code == 204
    s = mgr.patch("/api/v1/admin/tickets/settings/", {"tickets_max_open_per_user": 999}, format="json").json()
    assert s["settings"]["tickets_max_open_per_user"] == 50


def test_inbox_filters_and_badge(topics):
    u, v = customer(active=True), customer("bea", active=True)
    me, other = staff("me", CODES), staff("other", CODES)
    a = services.open_ticket(u, topic_id=topics["conn"].id, subject="wifi", body="x")
    b = services.open_ticket(v, topic_id=topics["pay"].id, subject="money", body="x")
    services.assign(b, me, other)
    c = staff_client(me)

    def ids(qs):
        return [r["id"] for r in c.get(f"/api/v1/admin/tickets/?{qs}").json()["results"]]

    assert ids("assigned=none") == [a.id] and ids("assigned=" + str(other.id)) == [b.id]
    assert ids(f"topic={topics['pay'].id}") == [b.id] and ids("q=wifi") == [a.id] and ids(f"q=%23{b.number}") == [b.id]
    assert ids("q=bea") == [b.id]
    assert c.get("/api/v1/admin/tickets/badge/").json()["badge"] == 1            # b belongs to `other`
    services.set_priority(a, me, "urgent")
    assert ids("priority=urgent") == [a.id]
    assert c.get("/api/v1/admin/tickets/").json()["status_counts"]["open"] == 2


# --- attachments ----------------------------------------------------------------
def test_attachments_validated_and_private(topics, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    u, intruder = customer(active=True), customer("eve", active=True)
    pdf = SimpleUploadedFile("bill.pdf", b"%PDF-1.4\n%fake but signed\n", content_type="application/pdf")
    r = open_via_api(u, topics["conn"], attachments=[png(), pdf])
    assert r.status_code == 201
    atts = r.json()["messages"][0]["attachments"]
    assert [a["content_type"] for a in atts] == ["image/png", "application/pdf"]
    stored = TicketAttachment.objects.get(pk=atts[0]["id"])
    assert stored.file.name.startswith("tickets/") and "shot" not in stored.file.name   # random name on disk
    assert user_client(u).get(atts[0]["url"]).status_code == 200
    assert user_client(intruder).get(atts[0]["url"]).status_code == 404
    assert APIClient().get(atts[0]["url"]).status_code == 401
    resp = user_client(u).get(atts[1]["url"])
    assert resp["Content-Disposition"].startswith("attachment")

    t = Ticket.objects.get(pk=r.json()["id"])
    bad = [
        SimpleUploadedFile("evil.png", b"<script>alert(1)</script>", content_type="image/png"),
        SimpleUploadedFile("x.png", b"\x89PNG\r\n\x1a\nnot really", content_type="image/png"),
        SimpleUploadedFile("big.pdf", b"%PDF-" + b"0" * (rules.MAX_BYTES + 1), content_type="application/pdf"),
    ]
    for f in bad:
        r = user_client(u).post(f"/api/v1/tickets/{t.id}/reply/", {"body": "x", "attachments": [f]}, format="multipart")
        assert r.status_code == 400 and r.json()["code"] == "attachment", f.name
    r = user_client(u).post(f"/api/v1/tickets/{t.id}/reply/",
                            {"attachments": [png(f"{i}.png") for i in range(4)]}, format="multipart")
    assert r.status_code == 400

    # staff out of scope and internal-note attachments
    out = staff("out", CODES, topics=[topics["pay"]])
    assert staff_client(out).get(atts[0]["url"]).status_code == 404
    s = staff("in", CODES)
    services.staff_reply(t, s, body="note", files=[png("n.png")], internal=True)
    note_att = TicketAttachment.objects.filter(message__is_internal=True).get()
    assert user_client(u).get(f"/api/v1/tickets/attachments/{note_att.id}/").status_code == 404
    assert staff_client(s).get(f"/api/v1/tickets/attachments/{note_att.id}/").status_code == 200


def test_empty_message_refused(topics):
    r = open_via_api(customer(), topics["pre"], body="")
    assert r.status_code == 400 and r.json()["code"] == "empty"


# --- staff notifications + Telegram linking ------------------------------------------
def test_staff_bot_and_email_only_when_linked(topics, bot, settings, django_capture_on_commit_callbacks, monkeypatch):
    sent_mail = []
    monkeypatch.setattr("apps.common.mail.mail_configured", lambda: True)
    monkeypatch.setattr("django.core.mail.send_mail", lambda *a, **k: sent_mail.append(a[3]))
    staff("linked", CODES, telegram_id=777, email="ops@example.test")
    staff("plain", CODES)
    with django_capture_on_commit_callbacks(execute=True):
        services.open_ticket(customer(), topic_id=topics["pre"].id, subject="price?", body="how much")
    assert [chat for chat, _ in bot] == [777] and "price?" in bot[0][1]
    assert sent_mail == [["ops@example.test"]]


def test_telegram_link_flow(bot):
    s = staff("sara", CODES)
    c = staff_client(s)
    r = c.post("/api/v1/admin/tickets/telegram-link/").json()
    assert r["deep_link"] == f"https://t.me/caspin_bot?start=staff-{r['code']}" and r["expires_in"] == 600
    from apps.telegram.bot.sales_bot import staff_link_reply

    users_before = User.objects.count()
    assert "✅" in staff_link_reply(r["code"].lower(), 4242)
    assert User.objects.count() == users_before                    # no customer account was created
    s.refresh_from_db()
    assert s.telegram_id == 4242 and c.get("/api/v1/admin/tickets/telegram-link/").json()["linked"] is True
    assert staff_link.redeem(r["code"], 4242) == "invalid"         # single use
    other = staff("omid", CODES)
    assert staff_link.redeem(staff_link.new_code(other), 4242) == "taken"
    assert c.delete("/api/v1/admin/tickets/telegram-link/").json()["linked"] is False
    s.refresh_from_db()
    assert s.telegram_id is None


def test_start_payload_routes_to_staff_link_before_customer_account(bot, monkeypatch):
    """The /start handler answers staff-<code> without ensure_bot_user."""
    import apps.telegram.bot.sales_bot as sb

    called = []
    monkeypatch.setattr(sb, "_user", lambda tg: called.append(tg) or (None, False, None))
    monkeypatch.setattr(sb, "close_old_connections", lambda: None)

    class Bot:
        handlers = {}
        sent = []

        def message_handler(self, **kw):
            def deco(fn):
                self.handlers.setdefault(tuple(kw.get("commands") or ()), fn)
                return fn
            return deco

        def callback_query_handler(self, **kw):
            return lambda fn: fn

        def send_message(self, chat_id, text, **kw):
            self.sent.append(text)

    fake = Bot()
    sb._register(fake)

    class Msg:
        text = "/start staff-NOPE1234"
        chat = type("C", (), {"id": 1})()
        from_user = type("U", (), {"id": 99, "username": "x", "first_name": "x", "last_name": ""})()

    fake.handlers[("start",)](Msg())
    assert called == [] and "⛔️" in fake.sent[-1]
