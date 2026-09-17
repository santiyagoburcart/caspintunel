from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.adminpanel.tests.conftest import make_staff
from apps.orders.models import Order, OrderStatus
from apps.panel.models import Panel, Service, ServiceStatus
from apps.payments_sms.models import (
    BankCard,
    ConfirmedBy,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from apps.plans.models import Plan
from apps.settings_app.models import Page, SiteConfig, Theme

pytestmark = pytest.mark.django_db


@pytest.fixture
def boss(staff_client, superadmin):
    return staff_client(superadmin)


# --- users ------------------------------------------------------
def test_user_list_filter_and_actions(boss):
    User.objects.create_user("a1", "Str0ngPass!", is_active=True)
    User.objects.create_user("a2", "Str0ngPass!", is_active=False)
    r = boss.get("/api/v1/admin/users/?is_active=false")
    assert r.status_code == 200
    assert [u["username"] for u in r.data["results"]] == ["a2"]

    uid = User.objects.get(username="a1").id
    assert boss.post(f"/api/v1/admin/users/{uid}/disable/").data["is_active"] is False
    assert boss.post(f"/api/v1/admin/users/{uid}/enable/").data["is_active"] is True
    assert boss.post(f"/api/v1/admin/users/{uid}/set-password/",
                     {"password": "N3wStr0ngPass!"}, format="json").status_code == 200


def test_user_create(boss):
    r = boss.post("/api/v1/admin/users/", {"username": "created", "password": "Str0ngPass!",
                                           "name": "C", "phone": "0912"}, format="json")
    assert r.status_code == 201
    assert User.objects.get(username="created").check_password("Str0ngPass!")


# --- cards + per-card deposit report --------------------------
def _paid_payment(card, amount, source="site"):
    user = User.objects.create_user(f"u{amount}{source}", "Str0ngPass!")
    plan = Plan.objects.create(name_fa="p", price=Decimal(amount))
    order = Order.objects.create(user=user, plan=plan, amount=amount, amount_unique=amount,
                                 unique_expire_at=timezone.now(), status=OrderStatus.COMPLETED,
                                 source=source)
    return Payment.objects.create(order=order, bank_card=card, method=PaymentMethod.CARD_MANUAL,
                                  amount=amount, status=PaymentStatus.APPROVED,
                                  confirmed_by=ConfirmedBy.ADMIN, confirmed_at=timezone.now())


def test_per_card_deposit_report(boss):
    c1 = BankCard.objects.create(card_number="1111", holder_name="A", sort_order=1)
    c2 = BankCard.objects.create(card_number="2222", holder_name="B", sort_order=2)
    _paid_payment(c1, 100000)
    _paid_payment(c1, 50000)
    _paid_payment(c2, 30000)

    r = boss.get("/api/v1/admin/cards/deposit-report/")
    assert r.status_code == 200
    by_card = {c["card_number"]: c for c in r.data["cards"]}
    assert by_card["1111"]["deposit_total"] == 150000
    assert by_card["1111"]["deposit_count"] == 2
    assert by_card["2222"]["deposit_total"] == 30000
    assert Decimal(r.data["grand_total"]) == Decimal("180000")


# --- transactions --------------------------------------------
def test_transactions_show_card_confirmer_source(boss):
    card = BankCard.objects.create(card_number="9999", holder_name="X")
    _paid_payment(card, 77000, source="bot")
    r = boss.get("/api/v1/admin/transactions/")
    row = r.data["results"][0]
    assert row["card"] == "9999"
    assert row["confirmer"] == "admin"
    assert row["order_source"] == "bot"


# --- accounting (Jalali) -----------------------------------
def test_accounting_revenue_and_breakdown(boss):
    card = BankCard.objects.create(card_number="1", holder_name="A")
    _paid_payment(card, 120000, source="site")
    _paid_payment(card, 80000, source="bot")

    r = boss.get("/api/v1/admin/accounting/?period=monthly")
    assert r.status_code == 200
    assert r.data["revenue"] == 200000
    assert r.data["transactions"] == 2
    assert "/" in r.data["range"]["from"]                 # Jalali formatted
    sources = {row["order__source"]: row["revenue"] for row in r.data["by_source"]}
    assert sources == {"site": 120000, "bot": 80000}


def test_accounting_accepts_jalali_range(boss):
    r = boss.get("/api/v1/admin/accounting/?from=1403/01/01&to=1403/12/29")
    assert r.status_code == 200
    assert r.data["range"]["from_gregorian"].startswith("2024-")


def test_accounting_revenue_split_by_panel(boss):
    p_wg = Panel.objects.create(name="Wireguard", base_url="https://wg.test",
                                admin_username="a", admin_password_enc="pw")
    p_vol = Panel.objects.create(name="Volume", base_url="https://vol.test",
                                 admin_username="a", admin_password_enc="pw")
    card = BankCard.objects.create(card_number="1", holder_name="A")

    def _pay(panel, amount):
        u = User.objects.create_user(f"u{panel.id}{amount}", "Str0ngPass!")
        plan = Plan.objects.create(panel=panel, name_fa="p", price=Decimal(amount))
        o = Order.objects.create(user=u, plan=plan, amount=amount, amount_unique=amount,
                                 unique_expire_at=timezone.now(), status=OrderStatus.COMPLETED)
        Payment.objects.create(order=o, bank_card=card, method=PaymentMethod.CARD_MANUAL,
                               amount=amount, status=PaymentStatus.APPROVED,
                               confirmed_by=ConfirmedBy.ADMIN, confirmed_at=timezone.now())

    _pay(p_wg, 120000)
    _pay(p_wg, 30000)
    _pay(p_vol, 50000)

    r = boss.get("/api/v1/admin/accounting/?period=monthly")
    by_panel = {row["panel"]: (row["revenue"], row["count"]) for row in r.data["by_panel"]}
    assert by_panel == {"Wireguard": (150000, 2), "Volume": (50000, 1)}
    # highest-revenue panel first
    assert r.data["by_panel"][0]["panel"] == "Wireguard"


# --- broadcast ---------------------------------------------
def test_broadcast_creates_notification(boss):
    User.objects.create_user("x1", "Str0ngPass!")
    User.objects.create_user("x2", "Str0ngPass!")
    r = boss.post("/api/v1/admin/notifications/",
                  {"title": "سلام", "body": "متن", "via_site": True, "via_bot": True}, format="json")
    assert r.status_code == 201
    assert r.data["type"] == "admin_broadcast"
    assert r.data["audience"] >= 2


# --- branding --------------------------------------------
def test_branding_get_update_and_public(boss, api):
    r = boss.get("/api/v1/admin/branding/")
    assert r.status_code == 200 and r.data["site_name_en"] == "caspintunel"

    upd = boss.patch("/api/v1/admin/branding/", {"site_name_fa": "کسپین", "support_telegram": "@cx"},
                     format="json")
    assert upd.status_code == 200 and upd.data["site_name_fa"] == "کسپین"

    pub = api.get("/api/v1/config/")
    assert pub.status_code == 200 and pub.data["site_name_fa"] == "کسپین"
    assert "logo" in pub.data  # branding fields exposed publicly


# --- service lists --------------------------------------
def test_service_lists_by_filter(boss):
    user = User.objects.create_user("svcowner", "Str0ngPass!")
    panel = Panel.objects.create(name="P", base_url="https://x", admin_username="a", admin_password_enc="p")
    Service.objects.create(user=user, panel=panel, panel_username="s-exp", status=ServiceStatus.EXPIRED)
    Service.objects.create(user=user, panel=panel, panel_username="s-hold", status=ServiceStatus.ON_HOLD)
    Service.objects.create(user=user, panel=panel, panel_username="s-on", status=ServiceStatus.ACTIVE,
                           online_at=timezone.now())

    assert [s["panel_username"] for s in boss.get("/api/v1/admin/services/?filter=expired").data["results"]] == ["s-exp"]
    assert [s["panel_username"] for s in boss.get("/api/v1/admin/services/?filter=on_hold").data["results"]] == ["s-hold"]
    assert [s["panel_username"] for s in boss.get("/api/v1/admin/services/?filter=online").data["results"]] == ["s-on"]


# --- rbac / roles ---------------------------------------
def test_role_crud_with_permission_codes(boss, perms):
    r = boss.post("/api/v1/admin/roles/", {"name": "Support", "description": "d",
                                           "permission_codes": ["users.view", "payment.approve"]},
                  format="json")
    assert r.status_code == 201
    assert set(r.data["permission_codes"]) == {"users.view", "payment.approve"}


# --- pages / themes -------------------------------------
def test_page_crud_and_public(boss, api):
    # a distinct slug — "rules" itself is now seeded with real content by
    # settings_app migration 0007 and shouldn't be clobbered by this test
    Page.objects.create(slug="test-page", title_fa="صفحه تست", is_active=True, body_fa="متن قوانین")
    assert api.get("/api/v1/pages/test-page/").data["body_fa"] == "متن قوانین"

    pid = Page.objects.get(slug="test-page").id
    boss.patch(f"/api/v1/admin/pages/{pid}/", {"body_fa": "به‌روزشد"}, format="json")
    assert api.get("/api/v1/pages/test-page/").data["body_fa"] == "به‌روزشد"


def test_theme_activate_and_public(boss, api):
    t1 = Theme.objects.create(name="Aurora", palette={"dark": {}}, is_active=True)
    t2 = Theme.objects.create(name="Sunset", palette={"light": {}}, is_active=False)
    boss.post(f"/api/v1/admin/themes/{t2.id}/activate/")
    t1.refresh_from_db()
    assert t1.is_active is False
    assert api.get("/api/v1/theme/").data["name"] == "Sunset"
