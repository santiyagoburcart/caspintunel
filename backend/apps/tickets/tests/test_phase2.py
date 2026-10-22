"""Phase 2: API additions (topic availability, staff names, saved replies, customer
panel, live pushes) and the ticket flows in the sales bot (customer + staff),
driven through the real handlers on a fake bot (no network)."""
import io
from types import SimpleNamespace as NS

import pytest
from PIL import Image

from apps.panel.models import Panel, Service
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting
from apps.telegram.bot import sales_bot
from apps.telegram.tests.test_bot_gate import FakeBot, _msg
from apps.tickets import notify, services
from apps.tickets.models import CannedReply, Ticket, TicketAttachment, TicketTopic

from .test_tickets import CODES, customer, staff, staff_client, user_client

pytestmark = pytest.mark.django_db
TG, STAFF_TG = 7001, 9001


def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (6, 6), "blue").save(buf, "PNG")
    return buf.getvalue()


class Bot(FakeBot):
    def get_file(self, file_id):
        return NS(file_path=f"photos/{file_id}.jpg")

    def download_file(self, path):
        return png_bytes()


@pytest.fixture
def tbot(monkeypatch):
    monkeypatch.setattr(sales_bot, "close_old_connections", lambda: None)
    b = Bot()
    sales_bot._register(b)
    return b


def click(b, data, tg=TG):
    b.sent.clear()
    c = NS(id="cb", data=data, from_user=NS(id=tg, username="u", first_name="A", last_name=""),
           message=NS(chat=NS(id=tg)))
    for func, fn in b.cb_handlers:
        if func is None or func(c):
            fn(c)
            return b.sent


def texts(sent):
    return "\n".join(str(t) for t, _ in sent)


def buttons(sent):
    return " ".join(m.to_json() for _, m in sent if m is not None and hasattr(m, "to_json"))


@pytest.fixture
def topics():
    return {t.name_en: t for t in TicketTopic.objects.all()}


def bot_customer(active=True):
    u = customer("tguser", active=active)
    u.telegram_id = TG
    u.save()
    return u


# --- API ----------------------------------------------------------------------
def test_staff_name_shown_to_customer_only_when_enabled(topics):
    u = customer(active=True)
    s = staff("sara", CODES, display_name="Sara K.")
    t = services.open_ticket(u, topic_id=topics["Connection problem"].id, subject="x", body="hi")
    services.staff_reply(t, s, body="hello")
    msgs = user_client(u).get(f"/api/v1/tickets/{t.id}/").json()["messages"]
    assert msgs[1]["author"] == "staff" and msgs[1]["author_name"] is None
    set_setting("tickets_show_staff_name", True, ValueType.BOOL)
    msgs = user_client(u).get(f"/api/v1/tickets/{t.id}/").json()["messages"]
    assert msgs[1]["author_name"] == "Sara K."
    mgr = staff_client(staff("mgr", CODES))
    r = mgr.patch("/api/v1/admin/tickets/settings/", {"tickets_show_staff_name": False}, format="json").json()
    assert r["settings"]["tickets_show_staff_name"] is False


def test_list_previews_hide_internal_notes(topics):
    u = customer(active=True)
    s = staff("sara", CODES)
    t = services.open_ticket(u, topic_id=topics["Other"].id, subject="anything", body="free text question")
    services.staff_reply(t, s, body="secret note", internal=True)
    row = user_client(u).get("/api/v1/tickets/").json()["results"][0]
    assert row["last_message"]["body"] == "free text question" and row["last_message"]["author"] == "user"
    srow = staff_client(s).get("/api/v1/admin/tickets/").json()["results"][0]
    assert srow["last_message"]["body"] == "secret note"


def test_canned_replies_per_topic(topics):
    mgr = staff_client(staff("mgr", CODES))
    agent = staff_client(staff("agent", ["tickets.view", "tickets.reply"]))
    conn, pay = topics["Connection problem"], topics["Payment problem"]
    mgr.post("/api/v1/admin/tickets/canned/", {"title": "Restart", "body": "Restart the app", "topic": conn.id}, format="json")
    mgr.post("/api/v1/admin/tickets/canned/", {"title": "Thanks", "body": "Thank you"}, format="json")
    off = mgr.post("/api/v1/admin/tickets/canned/", {"title": "Old", "body": "x", "topic": conn.id,
                                                      "is_active": False}, format="json").json()
    assert [c["title"] for c in agent.get(f"/api/v1/admin/tickets/canned/?topic={conn.id}").json()] == ["Restart", "Thanks"]
    assert [c["title"] for c in agent.get(f"/api/v1/admin/tickets/canned/?topic={pay.id}").json()] == ["Thanks"]
    assert len(mgr.get("/api/v1/admin/tickets/canned/?all=1").json()) == 3
    assert agent.post("/api/v1/admin/tickets/canned/", {"title": "a", "body": "b"}, format="json").status_code == 403
    assert mgr.delete(f"/api/v1/admin/tickets/canned/{off['id']}/").status_code == 204
    assert CannedReply.objects.count() == 2


def test_customer_panel_payments_need_payment_view(topics):
    u = customer(active=True)
    t = services.open_ticket(u, topic_id=topics["Other"].id, subject="x", body="y")
    services.open_ticket(u, topic_id=topics["Payment problem"].id, subject="z", body="y")
    d = staff_client(staff("agent", CODES)).get(f"/api/v1/admin/tickets/{t.id}/customer/").json()
    assert d["user"]["username"] == u.username and d["payments"] is None and d["open_tickets"] == 1
    assert d["services"][0]["status"] == "active"
    d = staff_client(staff("fin", CODES + ["payment.view"])).get(f"/api/v1/admin/tickets/{t.id}/customer/").json()
    assert d["payments"] == []
    assert len(staff_client(staff("lead", CODES)).get("/api/v1/admin/tickets/staff/").json()) == 3


def test_live_pushes_reach_customer_socket_but_not_for_internal_notes(topics, monkeypatch, django_capture_on_commit_callbacks):
    sent = []
    monkeypatch.setattr(notify, "_group_send", lambda group, message: sent.append((group, message["type"])))
    u = customer(active=True)
    s = staff("sara", CODES)
    with django_capture_on_commit_callbacks(execute=True):
        t = services.open_ticket(u, topic_id=topics["Other"].id, subject="x", body="y")
    with django_capture_on_commit_callbacks(execute=True):
        services.staff_reply(t, s, body="note", internal=True)
    assert (f"notifications_{u.id}", "ticket.event") in sent[:2]          # new ticket
    assert sent[-1] == (f"staff_tickets_{s.id}", "tickets.event")         # internal note: staff only
    sent.clear()
    with django_capture_on_commit_callbacks(execute=True):
        services.set_priority(t, s, "high")
    assert (f"notifications_{u.id}", "ticket.event") in sent and (f"staff_tickets_{s.id}", "tickets.event") in sent


# --- bot: customer ---------------------------------------------------------------
def test_bot_customer_opens_ticket_replies_with_photo_and_closes(tbot, topics):
    u = bot_customer()
    assert "tk:home" in buttons(tbot.feed(_msg(text="/start", tg=TG)))
    assert "tk:new" in buttons(click(tbot, "tk:home"))
    sent = click(tbot, "tk:new")
    assert "tk:nt:" in buttons(sent) and "منقضی" not in texts(sent)
    click(tbot, f"tk:nt:{topics['Other'].id}")
    tbot.feed(_msg(text="slow at night", tg=TG))                      # subject
    sent = tbot.feed(_msg(text="it gets slow after 10pm", tg=TG))      # first message
    t = Ticket.objects.get(user=u)
    assert t.subject == "slow at night" and t.source == "bot" and t.messages.get().channel == "bot"
    assert f"#{t.number}" in texts(sent) and f"tk:r:{t.id}" in buttons(sent)

    click(tbot, f"tk:r:{t.id}")
    photo = NS(**{**vars(_msg("photo", tg=TG)), "photo": [NS(file_id="abc")], "caption": "screenshot"})
    tbot.feed(photo)
    m = t.messages.order_by("-id").first()
    assert m.body == "screenshot" and m.attachments.get().content_type == "image/png"
    t.refresh_from_db()
    assert t.status == "awaiting_admin"

    sent = click(tbot, f"tk:c:{t.id}")
    t.refresh_from_db()
    assert t.status == "closed" and f"tk:o:{t.id}" in buttons(sent)
    sent = click(tbot, "tk:list:0")
    assert f"#{t.number}" in buttons(sent)


def test_bot_never_purchased_sees_only_pre_purchase_and_expired_sees_hint(tbot, topics):
    u = bot_customer(active=False)
    tbot.feed(_msg(text="/start", tg=TG))
    sent = click(tbot, "tk:new")
    assert buttons(sent).count("tk:nt:") == 1 and f"tk:nt:{topics['Pre-purchase questions'].id}" in buttons(sent)
    # a forged button for a service topic is refused
    click(tbot, f"tk:nt:{topics['Connection problem'].id}")
    assert Ticket.objects.count() == 0
    Service.objects.create(user=u, panel=Panel.objects.create(name="p", base_url="https://p.test",
                                                              admin_username="a", admin_password_enc="x"),
                           panel_username="old", status="limited")
    sent = click(tbot, "tk:new")
    assert buttons(sent).count("tk:nt:") == 5 and "منقضی" in texts(sent)


def test_bot_user_cannot_open_someone_elses_ticket(tbot, topics):
    other = customer("other", active=True)
    t = services.open_ticket(other, topic_id=topics["Other"].id, subject="private", body="secret")
    bot_customer()
    tbot.feed(_msg(text="/start", tg=TG))
    sent = click(tbot, f"tk:v:{t.id}")
    assert "secret" not in texts(sent)


def test_reply_alert_has_reply_button(topics, monkeypatch, django_capture_on_commit_callbacks):
    out = []

    class Fake:
        def send_message(self, chat_id, text, reply_markup=None, **kw):
            out.append((chat_id, text, reply_markup))

    monkeypatch.setattr("apps.telegram.config.sales_client", lambda: Fake())
    u = bot_customer()
    t = services.open_ticket(u, topic_id=topics["Other"].id, subject="x", body="y")
    with django_capture_on_commit_callbacks(execute=True):
        services.staff_reply(t, staff("sara", CODES), body="answer here")
    chat, text, markup = out[-1]
    assert chat == TG and "answer here" in text
    assert markup["inline_keyboard"][0][0]["callback_data"] == f"tk:r:{t.id}"


# --- bot: staff -------------------------------------------------------------------
def linked_staff(**kw):
    return staff("agent", CODES, telegram_id=STAFF_TG, **kw)


def test_bot_staff_inbox_assign_reply_close(tbot, topics):
    from apps.accounts.models import User

    u = customer(active=True)
    t = services.open_ticket(u, topic_id=topics["Connection problem"].id, subject="no internet", body="help")
    s = linked_staff()
    users_before = User.objects.count()
    sent = tbot.feed(_msg(text="/tickets", tg=STAFF_TG))
    assert f"st:v:{t.id}" in buttons(sent)
    sent = click(tbot, f"st:v:{t.id}", tg=STAFF_TG)
    assert "help" in texts(sent) and f"st:a:{t.id}" in buttons(sent)
    click(tbot, f"st:a:{t.id}", tg=STAFF_TG)
    t.refresh_from_db()
    assert t.assigned_to == s
    assert f"st:v:{t.id}" in buttons(click(tbot, "st:l:m:0", tg=STAFF_TG))

    sent = click(tbot, f"st:r:{t.id}", tg=STAFF_TG)
    assert any(type(m).__name__ == "ForceReply" for _, m in sent)
    tbot.feed(_msg(text="please restart the router", tg=STAFF_TG))
    m = t.messages.order_by("-id").first()
    assert m.author_staff == s and m.channel == "bot" and m.body == "please restart the router"
    t.refresh_from_db()
    assert t.status == "awaiting_user"

    click(tbot, f"st:c:{t.id}", tg=STAFF_TG)
    t.refresh_from_db()
    assert t.status == "closed" and t.closed_by == s
    assert User.objects.count() == users_before            # the staff member never became a customer


def test_bot_staff_scope_and_unlinked_refused(tbot, topics):
    u = customer(active=True)
    t = services.open_ticket(u, topic_id=topics["Payment problem"].id, subject="money", body="x")
    s = linked_staff()
    s.ticket_topics.set([topics["Connection problem"]])
    sent = click(tbot, f"st:v:{t.id}", tg=STAFF_TG)
    assert "money" not in texts(sent)
    sent = click(tbot, f"st:v:{t.id}", tg=1234)            # not linked
    assert "⛔️" in texts(sent)
    viewer = staff("viewer", ["tickets.view"], telegram_id=5555)
    t2 = services.open_ticket(u, topic_id=topics["Other"].id, subject="y", body="z")
    sent = click(tbot, f"st:v:{t2.id}", tg=5555)
    assert f"st:r:{t2.id}" not in buttons(sent) and f"st:c:{t2.id}" not in buttons(sent)
    click(tbot, f"st:c:{t2.id}", tg=5555)
    t2.refresh_from_db()
    assert t2.status != "closed" and viewer


def test_staff_alert_buttons(topics, monkeypatch, django_capture_on_commit_callbacks):
    out = []

    class Fake:
        def send_message(self, chat_id, text, reply_markup=None, **kw):
            out.append((chat_id, reply_markup))

    monkeypatch.setattr("apps.telegram.config.sales_client", lambda: Fake())
    linked_staff()
    with django_capture_on_commit_callbacks(execute=True):
        t = services.open_ticket(customer(active=True), topic_id=topics["Other"].id, subject="x", body="y")
    chat, markup = out[-1]
    data = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
    assert chat == STAFF_TG and data == [f"st:r:{t.id}", f"st:v:{t.id}", f"st:a:{t.id}", f"st:c:{t.id}"]


def test_bot_photo_on_staff_reply_becomes_attachment(tbot, topics, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    t = services.open_ticket(customer(active=True), topic_id=topics["Other"].id, subject="x", body="y")
    linked_staff()
    click(tbot, f"st:r:{t.id}", tg=STAFF_TG)
    tbot.feed(NS(**{**vars(_msg("photo", tg=STAFF_TG)), "photo": [NS(file_id="p1")], "caption": ""}))
    assert TicketAttachment.objects.filter(message__author_staff__isnull=False).count() == 1
