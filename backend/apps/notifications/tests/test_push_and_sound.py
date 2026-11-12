"""v1.33: panel sound preferences, Web Push subscriptions (staff + customer) and sending,
Telegram messages ring unless low priority, Monitoring shows the Blu collector."""
import json

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Staff, User
from apps.adminpanel.tokens import issue_tokens
from apps.notifications import webpush
from apps.notifications.models import PushSubscription

pytestmark = pytest.mark.django_db

SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "BPk", "auth": "au"}}


def staff_c(superadmin=True, name="boss"):
    s = Staff(username=name, is_superadmin=superadmin)
    s.set_password("x-Str0ng!")
    s.save()
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c, s


@pytest.fixture
def vapid(settings, monkeypatch):
    settings.VAPID_PUBLIC_KEY, settings.VAPID_PRIVATE_KEY = "PUB", "PRIV"
    queued = []
    monkeypatch.setattr(webpush, "_queue", lambda ids, payload: queued.append((sorted(ids), payload)) or len(ids))
    return queued


def test_staff_prefs_round_trip():
    c, s = staff_c()
    assert c.get("/api/v1/admin/auth/me/").json()["notify_prefs"] == {"sound": True, "volume": 60, "nav_open": None}
    r = c.patch("/api/v1/admin/auth/me/prefs/", {"sound": False, "volume": 140}, format="json")
    assert r.json() == {"sound": False, "volume": 100, "nav_open": None}
    assert c.get("/api/v1/admin/auth/me/prefs/").json()["sound"] is False
    assert c.patch("/api/v1/admin/auth/me/prefs/", {"volume": "x"}, format="json").status_code == 400


def test_push_off_without_vapid(settings):
    settings.VAPID_PUBLIC_KEY = settings.VAPID_PRIVATE_KEY = ""
    c, _ = staff_c()
    assert c.get("/api/v1/admin/push/").json()["enabled"] is False
    assert c.post("/api/v1/admin/push/subscribe/", {"subscription": SUB}, format="json").status_code == 503


def test_staff_subscribe_test_unsubscribe(vapid):
    c, s = staff_c()
    assert c.get("/api/v1/admin/push/").json() == {"enabled": True, "public_key": "PUB", "subscriptions": 0}
    r = c.post("/api/v1/admin/push/subscribe/", {"subscription": SUB}, format="json")
    assert r.status_code == 200 and r.json()["message_fa"]
    assert c.post("/api/v1/admin/push/subscribe/", {"subscription": {"endpoint": "http://x"}}, format="json").status_code == 400
    sub = PushSubscription.objects.get()
    assert sub.staff_id == s.id and sub.user_id is None
    assert c.post("/api/v1/admin/push/test/", {}, format="json").json()["sent"] == 1
    assert vapid[0][0] == [sub.id] and vapid[0][1]["url"] == "/"
    c.post("/api/v1/admin/push/unsubscribe/", {"endpoint": SUB["endpoint"]}, format="json")
    assert not PushSubscription.objects.exists()


def test_staff_push_follows_permissions(vapid):
    _, boss = staff_c(name="boss")
    _, plain = staff_c(superadmin=False, name="plain")
    webpush.save_subscription(SUB, staff=boss)
    webpush.save_subscription({**SUB, "endpoint": "https://push.example/2"}, staff=plain)
    assert webpush.push_to_staff("payment.approve", "t", "b", url="/payments/1") == 1


def test_customer_push_and_notify_user_hook(vapid):
    u = User.objects.create_user("cust", "Str0ngPass!")
    c = APIClient()
    c.force_authenticate(u)
    assert c.post("/api/v1/notifications/push/subscribe/", {"subscription": SUB}, format="json").status_code == 200
    from apps.notifications.dispatch import notify_user

    notify_user(u, title="پرداخت تأیید شد", body="سفارش #5", link="/orders")
    assert vapid[-1][1]["title"] == "پرداخت تأیید شد" and vapid[-1][1]["url"] == "/orders"
    # the customer's own sound switch
    r = c.patch("/api/v1/auth/me/", {"notify_sound": False}, format="json")
    assert r.status_code == 200, r.content
    u.refresh_from_db()
    assert u.notify_sound is False


def test_send_now_removes_dead_subscriptions(settings, monkeypatch):
    settings.VAPID_PUBLIC_KEY, settings.VAPID_PRIVATE_KEY = "PUB", "PRIV"
    pywebpush = pytest.importorskip("pywebpush")     # in the image from v1.33 on

    class Resp:
        status_code = 410
    calls = []

    def fake(subscription_info, data, **kw):
        calls.append(json.loads(data))
        if subscription_info["endpoint"].endswith("dead"):
            raise pywebpush.WebPushException("gone", response=Resp())
    monkeypatch.setattr(pywebpush, "webpush", fake)
    a = webpush.save_subscription(SUB, user=User.objects.create_user("a", "Str0ngPass!"))
    b = webpush.save_subscription({**SUB, "endpoint": "https://push.example/dead"}, user=a.user)
    assert webpush.send_now([a.id, b.id], {"title": "t"}) == {"ok": 1, "gone": 1, "failed": 0}
    assert list(PushSubscription.objects.values_list("id", flat=True)) == [a.id]


def test_telegram_messages_ring_unless_low_priority(monkeypatch):
    from apps.common import staff_alert
    from apps.telegram import client as tclient

    seen = []
    monkeypatch.setattr(tclient.TelegramClient, "_call", lambda self, m, **p: seen.append((m, p)) or {})
    Staff.objects.create(username="t1", is_superadmin=True, telegram_id=55)
    monkeypatch.setattr("apps.telegram.config.our_sales_client", lambda: tclient.TelegramClient("1:x"))   # v1.49: staff = our bot
    staff_alert.alert_staff("hi", perm="payment.view")
    staff_alert.alert_staff("ok again", perm="payment.view", silent=True,
                            buttons=[[{"text": "b", "callback_data": "x"}]])
    assert seen[0][1]["disable_notification"] == "false" and "reply_markup" not in seen[0][1]
    assert seen[1][1]["disable_notification"] == "true" and "inline_keyboard" in seen[1][1]["reply_markup"]


def test_monitoring_has_the_blu_collector():
    c, _ = staff_c()
    blu = c.get("/api/v1/admin/monitoring/").json()["blu"]
    assert set(blu) >= {"enabled", "connected", "last_batch_at", "service"} and "settings" not in blu
