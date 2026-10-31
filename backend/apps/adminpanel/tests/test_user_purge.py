"""Permanent delete (purge) of a soft-deleted user — accounts/purge.py + /admin/deleted-users/…/purge/.
Money stays (orders, payments, Accounting totals), the person goes; Super Admin only;
a PasarGuard failure deletes nothing."""
import pytest
import responses
from django.core.files.base import ContentFile
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import DeletedUserArchive, Permission, Role, Staff, User
from apps.accounts.purge import purged_username
from apps.adminpanel.tests.test_user_delete import BASE, _delete, _mock_panel, _revenue, world  # noqa: F401
from apps.common.models import AuditLog
from apps.crm.models import CrmEvent, CustomerNote, CustomerProfile
from apps.notifications.models import Notification
from apps.orders.models import Order
from apps.panel.models import Service
from apps.payments_sms.models import Payment
from apps.tickets.models import Ticket, TicketAttachment, TicketMessage, TicketTopic

pytestmark = pytest.mark.django_db


@pytest.fixture
def trashed(staff_client, superadmin, world):  # noqa: F811
    """`ali` with tickets (+ attachment), CRM data, a notification and a session — then soft-deleted."""
    user = world["user"]
    topic = TicketTopic.objects.create(name_fa="فنی", name_en="Tech")
    t = Ticket.objects.create(user=user, topic=topic, subject="vpn down")
    m = TicketMessage.objects.create(ticket=t, author_user=user, body="my phone 09121234567")
    att = TicketAttachment(message=m, size=9, original_name="x.png", content_type="image/png")
    att.file.save("x.png", ContentFile(b"\x89PNG fake"), save=True)
    CustomerProfile.objects.create(user=user)
    CustomerNote.objects.create(user=user, body="called him")
    CrmEvent.objects.create(user=user, kind="note")
    Notification.objects.create(target_user=user, title="hi", body="b")
    RefreshToken.for_user(user)
    c = staff_client(superadmin)
    with responses.RequestsMock() as rsps:
        _mock_panel(rsps, ["ali_1", "ali_2"])
        assert _delete(c, user).status_code == 200
    user.refresh_from_db()
    return {"user": user, "archive": DeletedUserArchive.objects.get(user=user), "file": att.file.name, "c": c}


def _panel(rsps, *, exists=("ali_1", "ali_2"), broken=(), delete=True):
    # the panel token is cached from the soft delete in the fixture
    for n in ("ali_1", "ali_2"):
        if n in broken:
            rsps.add(responses.GET, f"{BASE}/api/user/{n}", json={"detail": "boom"}, status=500)
        elif n in exists:
            rsps.add(responses.GET, f"{BASE}/api/user/{n}", json={"username": n, "status": "disabled"})
            if delete:
                rsps.add(responses.DELETE, f"{BASE}/api/user/{n}", status=200, json={})
                rsps.add(responses.GET, f"{BASE}/api/user/{n}", json={"detail": "nf"}, status=404)
        else:
            rsps.add(responses.GET, f"{BASE}/api/user/{n}", json={"detail": "nf"}, status=404)


def test_preview_lists_what_goes_and_what_stays(trashed):
    c, a = trashed["c"], trashed["archive"]
    with responses.RequestsMock() as rsps:
        _panel(rsps, exists=("ali_1",), delete=False)
        r = c.get(f"/api/v1/admin/deleted-users/purge-preview/?ids={a.id}")
    assert r.status_code == 200, r.data
    row = r.data["results"][0]
    rm = row["removes"]
    assert rm["services"] == 2 and rm["tickets"] == 1 and rm["ticket_attachments"] == 1
    assert rm["crm"]["profile"] == 1 and rm["crm"]["notes"] == 1 and rm["notifications"] >= 1
    assert rm["telegram_linked"] is True and rm["archives"] == 1
    assert rm["kept_orders"] == 2 and rm["kept_payments"] == 2
    assert row["panel_existing"] == 1 and [p["exists"] for p in row["panel_accounts"]] == [True, False]


def test_purge_removes_the_person_and_keeps_the_money(trashed):
    c, a, user = trashed["c"], trashed["archive"], trashed["user"]
    revenue = _revenue(c)
    tx = c.get("/api/v1/admin/transactions/").data["count"]
    orders = set(Order.objects.filter(user=user).values_list("id", flat=True))
    with responses.RequestsMock() as rsps:
        _panel(rsps)
        r = c.post(f"/api/v1/admin/deleted-users/{a.id}/purge/", {"delete_on_panel": True}, format="json")
        deletes = [x.request.url for x in rsps.calls if x.request.method == "DELETE"]
    assert r.status_code == 200, r.data
    assert len(deletes) == 2 and r.data["panel_deleted"] == 2

    user.refresh_from_db()
    assert user.username == purged_username(user.id) == f"کاربر حذف‌شده #{user.id}"
    assert (user.name, user.phone, user.email, user.telegram_id, user.telegram_username) == ("", "", None, None, None)
    assert user.bank_card_number is None and user.admin_note == "" and user.referred_by is None
    assert user.purged_at and not user.has_usable_password() and not user.is_active
    assert not Service.objects.filter(user=user).exists()
    assert not Ticket.objects.filter(user=user).exists() and not TicketAttachment.objects.exists()
    assert not CustomerProfile.objects.filter(user=user).exists() and not CrmEvent.objects.filter(user=user).exists()
    assert not Notification.objects.filter(target_user=user).exists()
    assert not OutstandingToken.objects.filter(user=user).exists()
    assert not DeletedUserArchive.objects.filter(user=user).exists()     # held the original profile
    # money unchanged
    assert set(Order.objects.filter(user=user).values_list("id", flat=True)) == orders
    assert Payment.objects.filter(order__user=user).count() == 2
    assert _revenue(c) == revenue
    assert c.get("/api/v1/admin/transactions/").data["count"] == tx
    rows = c.get("/api/v1/admin/transactions/").data["results"]
    assert {x["user"] for x in rows if x["order_id"] in orders} <= {user.username}
    # audit: who / what, no personal data
    log = AuditLog.objects.get(action="user.purged")
    assert log.staff_label == "boss" and log.target_id == user.id and log.detail["removed"]["tickets"] == 1
    flat = str(log.detail)
    assert "ali" not in flat and "0912" not in flat and "example.com" not in flat


def test_purge_without_panel_delete_keeps_panel_accounts(trashed):
    c, a = trashed["c"], trashed["archive"]
    with responses.RequestsMock():                       # any panel call would fail the test
        r = c.post(f"/api/v1/admin/deleted-users/{a.id}/purge/", {"delete_on_panel": False}, format="json")
    assert r.status_code == 200 and r.data["panel_kept"] == 2


def test_panel_failure_deletes_nothing(trashed):
    c, a, user = trashed["c"], trashed["archive"], trashed["user"]
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        _panel(rsps, broken=("ali_2",))
        r = c.post(f"/api/v1/admin/deleted-users/{a.id}/purge/", {"delete_on_panel": True}, format="json")
        assert not [x for x in rsps.calls if x.request.method == "DELETE"]   # read first, nothing deleted
    assert r.status_code == 502 and "nothing was deleted" in r.data["detail"] and "ali_2" in r.data["detail"]
    user.refresh_from_db()
    assert user.purged_at is None and user.username.startswith("deleted_")
    assert Service.objects.filter(user=user).count() == 2 and Ticket.objects.filter(user=user).exists()
    assert DeletedUserArchive.objects.filter(pk=a.pk).exists()
    assert not AuditLog.objects.filter(action="user.purged").exists()


def test_only_super_admin(trashed):
    a = trashed["archive"]
    codes = ["users.view", "users.delete", "users.purge"]
    role = Role.objects.create(name="almost")
    role.permissions.set([Permission.objects.get_or_create(code=x, defaults={"name": x})[0] for x in codes])
    s = Staff(username="mgr", role=role); s.set_password("Str0ngPass!"); s.save()
    from apps.adminpanel.tokens import issue_tokens
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    assert c.post(f"/api/v1/admin/deleted-users/{a.id}/purge/", {}, format="json").status_code == 403
    assert c.post("/api/v1/admin/deleted-users/bulk-purge/", {"ids": [a.id]}, format="json").status_code == 403
    assert c.get(f"/api/v1/admin/deleted-users/purge-preview/?ids={a.id}").status_code == 403
    role.permissions.set([Permission.objects.get(code="users.view")])
    assert c.get("/api/v1/admin/deleted-users/").status_code == 200        # the trash still opens
    assert c.post(f"/api/v1/admin/deleted-users/{a.id}/purge/", {}, format="json").status_code == 403


def test_bulk_purge_and_only_from_trash(trashed, staff_client, superadmin):
    c, a = trashed["c"], trashed["archive"]
    other = User.objects.create_user("live", "Str0ngPass!")
    with responses.RequestsMock() as rsps:
        _panel(rsps)
        r = c.post("/api/v1/admin/deleted-users/bulk-purge/", {"ids": [a.id], "delete_on_panel": True}, format="json")
    assert r.status_code == 200 and r.data["purged"] == 1
    from apps.accounts.purge import PurgeError, purge_user
    with pytest.raises(PurgeError):
        purge_user(other, staff=superadmin, delete_on_panel=False)       # not in the trash
    other.refresh_from_db()
    assert other.username == "live"
