"""Phase 4 — admin "delete user" (soft delete + archive) and restore."""
import json
from decimal import Decimal

import pytest
import responses
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import DeletedUserArchive, Permission, User
from apps.adminpanel.tests.conftest import make_staff
from apps.common.models import AuditLog
from apps.orders.models import Order, OrderStatus, OrderType
from apps.panel.models import Panel, Service, ServiceStatus
from apps.payments_sms.models import BankCard, ConfirmedBy, Payment, PaymentMethod, PaymentStatus
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db
BASE = "https://panel.test"
GB = 1024 ** 3


@pytest.fixture
def world(superadmin):
    panel = Panel.objects.create(name="P1", base_url=BASE, admin_username="a", admin_password_enc="p")
    plan = Plan.objects.create(panel=panel, name_fa="یک ماهه", name_en="1 month", price=Decimal("100000"),
                               duration_days=30, data_limit=50 * GB)
    referrer = User.objects.create_user("ref", "Str0ngPass!")
    user = User.objects.create_user("ali", "Str0ngPass!", name="Ali", phone="09121234567",
                                    email="ali@example.com", telegram_id=555, telegram_username="ali_tg",
                                    referred_by=referrer, admin_note="vip")
    s1 = Service.objects.create(user=user, panel=panel, panel_username="ali_1", current_plan=plan,
                                status=ServiceStatus.ACTIVE, data_limit=50 * GB, data_used=3 * GB,
                                subscription_url="https://sub/ali_1")
    s2 = Service.objects.create(user=user, panel=panel, panel_username="ali_2", current_plan=plan,
                                status=ServiceStatus.ON_HOLD)
    card = BankCard.objects.create(card_number="6037991234567890", holder_name="Owner", bank_name="Melli")
    order = Order(user=user, plan=plan, service=s1, type=OrderType.NEW, amount=100000, amount_unique=100345,
                  unique_expire_at=timezone.now(), status=OrderStatus.COMPLETED)
    order.sync_unique_lock()
    order.save()
    Payment.objects.create(order=order, bank_card=card, method=PaymentMethod.CARD_MANUAL, amount=100345,
                           status=PaymentStatus.APPROVED, confirmed_by=ConfirmedBy.ADMIN,
                           confirmed_by_staff=superadmin, confirmed_at=timezone.now())
    rejected = Order(user=user, plan=plan, type=OrderType.RENEW, amount=100000, amount_unique=100777,
                     unique_expire_at=timezone.now(), status=OrderStatus.REJECTED)
    rejected.sync_unique_lock()
    rejected.save()
    Payment.objects.create(order=rejected, method=PaymentMethod.CARD_MANUAL, amount=100777,
                           status=PaymentStatus.REJECTED, reject_reason="fake")
    return {"panel": panel, "plan": plan, "user": user, "services": [s1, s2], "order": order}


def _mock_panel(rsps, names, *, missing=(), broken=()):
    rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    for n in names:
        if n in broken:
            rsps.add(responses.PUT, f"{BASE}/api/user/{n}", json={"detail": "boom"}, status=500)
        elif n in missing:
            rsps.add(responses.PUT, f"{BASE}/api/user/{n}", json={"detail": "nf"}, status=404)
        else:
            rsps.add(responses.PUT, f"{BASE}/api/user/{n}", json={"username": n})
            rsps.add(responses.GET, f"{BASE}/api/user/{n}",
                     json={"username": n, "status": "disabled", "used_traffic": 4 * GB, "data_limit": 50 * GB})


def _delete(client, user, reason="fraud"):
    return client.post(f"/api/v1/admin/users/{user.id}/delete/", {"reason": reason}, format="json")


def _revenue(client):
    return client.get("/api/v1/admin/accounting/?period=monthly").data["revenue"]


def test_delete_flow(staff_client, superadmin, world):
    user = world["user"]
    c = staff_client(superadmin)
    refresh = RefreshToken.for_user(user)                          # an open login session
    revenue_before = _revenue(c)
    tx_before = c.get("/api/v1/admin/transactions/").data["count"]

    with responses.RequestsMock() as rsps:
        _mock_panel(rsps, ["ali_1", "ali_2"])
        r = _delete(c, user, "chargeback fraud")
        puts = [json.loads(call.request.body) for call in rsps.calls if call.request.method == "PUT"]
        assert not any(call.request.method == "DELETE" for call in rsps.calls)   # never deleted
    assert r.status_code == 200, r.data
    assert puts == [{"status": "disabled"}, {"status": "disabled"}]

    # services disabled on our side too
    assert set(Service.objects.filter(user=user).values_list("status", flat=True)) == {ServiceStatus.DISABLED}

    # soft delete + freed unique fields + telegram unlinked
    user.refresh_from_db()
    assert user.deleted_at and user.deleted_by == superadmin and user.delete_reason == "chargeback fraud"
    assert user.is_active is False and user.telegram_id is None
    assert user.username == f"deleted_{user.id}_ali"
    assert user.phone.startswith(f"deleted_{user.id}_") and user.email == f"deleted_{user.id}_ali@example.com"

    # sessions revoked
    assert BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists()
    assert APIClient().post("/api/v1/auth/token/refresh/", {"refresh": str(refresh)}, format="json").status_code == 401

    # full snapshot
    a = DeletedUserArchive.objects.get(user=user)
    assert (a.original_username, a.original_phone, a.original_email, a.original_telegram_id) == \
        ("ali", "09121234567", "ali@example.com", 555)
    assert a.orders_count == 2 and a.total_paid == 100345 and a.deleted_by_label == "boss"
    snap = a.snapshot
    assert snap["profile"]["referred_by"]["username"] == "ref" and snap["profile"]["admin_note"] == "vip"
    assert snap["profile"]["referral_code"] == user.referral_code
    paid = next(o for o in snap["orders"] if o["id"] == world["order"].id)
    assert paid["payment"]["card"]["number"] == "6037991234567890"
    assert paid["payment"]["confirmer"] == "boss" and paid["plan"]["name_en"] == "1 month"
    svc = {s["panel_username"]: s for s in snap["services"]}
    assert svc["ali_1"]["status_before"] == "active" and svc["ali_1"]["subscription_url"] == "https://sub/ali_1"
    assert svc["ali_1"]["panel_result"] == "disabled" and svc["ali_2"]["status_before"] == "on_hold"
    assert "notifications" in snap

    # accounting untouched: orders / payments still there, still owned by the user
    assert Order.objects.filter(user=user).count() == 2
    assert _revenue(c) == revenue_before == 100345
    assert c.get("/api/v1/admin/transactions/").data["count"] == tx_before

    # gone from the users list + stats, visible in the archive
    assert user.id not in [u["id"] for u in c.get("/api/v1/admin/users/").data["results"]]
    arch = c.get("/api/v1/admin/deleted-users/").data["results"]
    assert arch[0]["original_username"] == "ali" and arch[0]["deleted_by"] == "boss"
    assert c.get(f"/api/v1/admin/users/{user.id}/orders/").status_code == 200   # history still reachable
    assert AuditLog.objects.filter(action="user.deleted", target_id=user.id).exists()


def test_same_person_can_register_again(staff_client, superadmin, world):
    with responses.RequestsMock() as rsps:
        _mock_panel(rsps, ["ali_1", "ali_2"])
        assert _delete(staff_client(superadmin), world["user"]).status_code == 200
    r = APIClient().post("/api/v1/auth/register/", {
        "username": "ali", "password": "An0therPass!", "email": "ali@example.com", "phone": "09121234567",
    }, format="json")
    assert r.status_code == 201, r.data
    # the bot sees the telegram id as a brand-new user
    from apps.telegram.accounts import ensure_bot_user
    new, created, _ = ensure_bot_user(555)
    assert created and new.pk != world["user"].pk


def test_panel_failure_aborts_delete(staff_client, superadmin, world):
    user = world["user"]
    with responses.RequestsMock() as rsps:
        _mock_panel(rsps, ["ali_1", "ali_2"], broken=("ali_2",))
        r = _delete(staff_client(superadmin), user)
    assert r.status_code == 502 and r.data["failed_services"][0]["panel_username"] == "ali_2"
    user.refresh_from_db()
    assert user.deleted_at is None and user.username == "ali" and user.is_active
    assert not DeletedUserArchive.objects.exists()


def test_account_missing_on_panel_is_not_an_error(staff_client, superadmin, world):
    with responses.RequestsMock() as rsps:
        _mock_panel(rsps, ["ali_1", "ali_2"], missing=("ali_2",))
        assert _delete(staff_client(superadmin), world["user"]).status_code == 200
    snap = DeletedUserArchive.objects.get().snapshot
    assert {s["panel_username"]: s["panel_result"] for s in snap["services"]} == {"ali_1": "disabled", "ali_2": "missing"}


def test_reason_required_and_permission(staff_client, superadmin, perms, world):
    user = world["user"]
    assert _delete(staff_client(superadmin), user, "  ").status_code == 400
    manager = make_staff("mgr", ["users.view", "users.manage"], perms)
    assert _delete(staff_client(manager), user).status_code == 403
    perms["users.delete"] = Permission.objects.get(code="users.delete")      # seeded by migration
    deleter = make_staff("del", ["users.view", "users.delete"], perms)
    with responses.RequestsMock() as rsps:
        _mock_panel(rsps, ["ali_1", "ali_2"])
        assert _delete(staff_client(deleter), user).status_code == 200
    # hard DELETE is refused (it would cascade into accounting)
    assert staff_client(superadmin).delete(f"/api/v1/admin/users/{user.id}/").status_code == 405


def _deleted(staff_client, superadmin, world):
    with responses.RequestsMock() as rsps:
        _mock_panel(rsps, ["ali_1", "ali_2"])
        assert _delete(staff_client(superadmin), world["user"]).status_code == 200
    return DeletedUserArchive.objects.get(user=world["user"])


def test_restore_without_conflicts(staff_client, superadmin, world):
    a = _deleted(staff_client, superadmin, world)
    c = staff_client(superadmin)
    detail = c.get(f"/api/v1/admin/deleted-users/{a.id}/").data
    assert detail["can_restore"] and detail["restore_conflicts"] == {}
    assert detail["snapshot"]["profile"]["username"] == "ali"

    r = c.post(f"/api/v1/admin/deleted-users/{a.id}/restore/")
    assert r.status_code == 200, r.data
    assert r.data["telegram_restored"] is True
    u = User.objects.get(pk=world["user"].pk)
    assert (u.username, u.phone, u.email, u.telegram_id) == ("ali", "09121234567", "ali@example.com", 555)
    assert u.is_active and u.deleted_at is None and u.delete_reason == ""
    # services stay disabled until an admin re-enables them
    assert set(Service.objects.filter(user=u).values_list("status", flat=True)) == {ServiceStatus.DISABLED}
    a.refresh_from_db()
    assert a.restored_at and a.restored_by == superadmin
    assert c.post(f"/api/v1/admin/deleted-users/{a.id}/restore/").status_code == 400   # only once
    assert AuditLog.objects.filter(action="user.restored", target_id=u.id).exists()


def test_restore_blocked_by_conflicts(staff_client, superadmin, world):
    a = _deleted(staff_client, superadmin, world)
    User.objects.create_user("ALI", "Str0ngPass!", phone="09121234567")          # re-registered
    c = staff_client(superadmin)
    assert set(c.get(f"/api/v1/admin/deleted-users/{a.id}/").data["restore_conflicts"]) == {"username", "phone"}
    r = c.post(f"/api/v1/admin/deleted-users/{a.id}/restore/")
    assert r.status_code == 409
    assert set(r.data["conflicts"]) == {"username", "phone"}
    assert r.data["conflicts"]["username"]["username"] == "ALI"
    u = User.objects.get(pk=world["user"].pk)
    assert u.deleted_at is not None and not u.is_active                            # untouched


def test_restore_with_telegram_taken_relinks_nothing(staff_client, superadmin, world):
    a = _deleted(staff_client, superadmin, world)
    User.objects.create_user("tg_new", "Str0ngPass!", telegram_id=555)          # came back via the bot
    r = staff_client(superadmin).post(f"/api/v1/admin/deleted-users/{a.id}/restore/")
    assert r.status_code == 200 and r.data["telegram_restored"] is False
    assert r.data["warnings"] == ["telegram_id_in_use"]
    assert User.objects.get(pk=world["user"].pk).telegram_id is None


def test_archive_search_and_date_filter(staff_client, superadmin, perms, world):
    a = _deleted(staff_client, superadmin, world)
    viewer = make_staff("viewer", ["users.view"], perms)
    c = staff_client(viewer)
    assert [r["id"] for r in c.get("/api/v1/admin/deleted-users/?search=0912123").data["results"]] == [a.id]
    assert [r["id"] for r in c.get("/api/v1/admin/deleted-users/?search=555").data["results"]] == [a.id]
    assert c.get("/api/v1/admin/deleted-users/?search=nobody").data["results"] == []
    assert c.get("/api/v1/admin/deleted-users/?from=2000-01-01&to=2000-01-02").data["results"] == []
    assert c.get("/api/v1/admin/deleted-users/?state=restored").data["results"] == []
    # users.view may look but not restore
    assert c.post(f"/api/v1/admin/deleted-users/{a.id}/restore/").status_code == 403
