"""Telegram contact share -> phone link / site-account merge (Phase 2 · 4)."""
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.common.models import AuditLog
from apps.notifications.dispatch import notify_user
from apps.notifications.models import Notification, NotificationDelivery
from apps.orders.models import Order, OrderStatus
from apps.panel.models import Panel, Service, ServiceStatus
from apps.payments_sms.models import Payment, PaymentStatus
from apps.plans.models import Plan
from apps.settings_app.utils import set_setting
from apps.telegram.accounts import ensure_bot_user, link_telegram_phone

pytestmark = pytest.mark.django_db


@pytest.fixture
def site_user():
    return User.objects.create_user("siteuser", "SitePass123!", phone="09107323128", email="s@example.com")


@pytest.fixture
def bot_user():
    user, *_ = ensure_bot_user(9001, telegram_username="botty", name="Bot Name")
    return user


def _give_data(user):
    plan = Plan.objects.create(name_fa="p", price=Decimal("1000"))
    panel = Panel.objects.create(name="P", base_url="https://x", admin_username="a", admin_password_enc="p")
    order = Order.objects.create(user=user, plan=plan, amount=1000, amount_unique=1234,
                                 unique_expire_at=timezone.now(), status=OrderStatus.COMPLETED)
    Payment.objects.create(order=order, amount=1234, status=PaymentStatus.APPROVED)
    Service.objects.create(user=user, panel=panel, panel_username="botsvc", current_plan=plan,
                           status=ServiceStatus.ACTIVE)
    notify_user(user, title="t", body="b")
    User.objects.create_user("referred", "Str0ngPass!", referred_by=user)
    return order


def test_contact_matching_site_account_merges(site_user, bot_user):
    order = _give_data(bot_user)
    # a live website session exists before the merge
    refresh = RefreshToken.for_user(site_user)
    web = APIClient()
    web.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    assert web.get("/api/v1/auth/me/").status_code == 200

    res = link_telegram_phone(bot_user, "+989107323128")      # what Telegram sends

    assert res.status == "merged" and res.user.pk == site_user.pk
    site_user.refresh_from_db()
    assert site_user.telegram_id == 9001
    assert site_user.phone == "09107323128"
    assert site_user.telegram_username == "botty"
    # everything moved
    assert Order.objects.get(pk=order.pk).user_id == site_user.pk
    assert Payment.objects.get(order=order).order.user_id == site_user.pk
    assert Service.objects.get(panel_username="botsvc").user_id == site_user.pk
    assert NotificationDelivery.objects.filter(user=site_user).count() == 1
    assert Notification.objects.filter(target_user=site_user).count() == 1
    assert User.objects.get(username="referred").referred_by_id == site_user.pk
    assert res.moved["orders.Order.user"] == 1 and res.moved["panel.Service.user"] == 1
    # bot-only account is gone
    assert not User.objects.filter(pk=bot_user.pk).exists()
    # security: unverified site password invalidated + sessions revoked
    assert not site_user.has_usable_password()
    assert web.get("/api/v1/auth/me/").status_code == 401                         # access token dead
    r = APIClient().post("/api/v1/auth/token/refresh/", {"refresh": str(refresh)}, format="json")
    assert r.status_code == 401                                                    # refresh blacklisted
    assert APIClient().post("/api/v1/auth/login/", {"username": "siteuser", "password": "SitePass123!"},
                            format="json").status_code == 401
    # logged: admin note + audit
    assert "Telegram account merged" in site_user.admin_note and "orders" in site_user.admin_note.lower()
    log = AuditLog.objects.get(action="user.merged_telegram")
    assert log.target_id == site_user.pk and log.detail["bot_user"] == bot_user.pk
    assert log.detail["moved"]["orders.Order.user"] == 1 and log.staff_label == "telegram-bot"
    # the bot now resolves to the site account
    again, created, _ = ensure_bot_user(9001)
    assert again.pk == site_user.pk and created is False


def test_new_password_via_bot_restores_site_login(site_user, bot_user):
    from apps.telegram.accounts import change_password_via_bot

    user = link_telegram_phone(bot_user, "+989107323128").user
    change_password_via_bot(user, "BrandNewPass9!")
    assert APIClient().post("/api/v1/auth/login/", {"username": "siteuser", "password": "BrandNewPass9!"},
                            format="json").status_code == 200


def test_plain_link_when_no_site_account(bot_user):
    res = link_telegram_phone(bot_user, "+98 935 111 2233")
    assert res.status == "linked" and res.user.pk == bot_user.pk
    bot_user.refresh_from_db()
    assert bot_user.phone == "09351112233" and bot_user.has_usable_password()
    assert link_telegram_phone(bot_user, "989351112233").status == "already"


def test_non_iranian_contact_rejected_when_iran_only(bot_user):
    res = link_telegram_phone(bot_user, "+14155552671")
    assert res.status == "not_iranian" and not res.ok
    bot_user.refresh_from_db()
    assert bot_user.phone == ""


def test_non_iranian_contact_allowed_when_setting_off(bot_user):
    set_setting("iran_phone_only", "false", "bool")
    res = link_telegram_phone(bot_user, "+14155552671")
    assert res.status == "linked"
    bot_user.refresh_from_db()
    assert bot_user.phone == "+14155552671"


def test_number_owned_by_other_telegram_account_is_a_conflict(bot_user):
    other = User.objects.create_user("tg_other", "Str0ngPass!", telegram_id=1234, phone="09107323128")
    res = link_telegram_phone(bot_user, "+989107323128")
    assert res.status == "conflict"
    bot_user.refresh_from_db()
    other.refresh_from_db()
    assert bot_user.phone == "" and other.telegram_id == 1234 and other.has_usable_password()


def test_old_tokens_without_claim_still_work_for_normal_users(site_user):
    """Deploying CHECK_REVOKE_TOKEN must not log everybody out."""
    from rest_framework_simplejwt.settings import api_settings

    access = RefreshToken.for_user(site_user).access_token
    del access[api_settings.REVOKE_TOKEN_CLAIM]           # a pre-deploy token
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    assert c.get("/api/v1/auth/me/").status_code == 200


def test_site_password_change_keeps_current_session(site_user):
    c = APIClient()
    old = RefreshToken.for_user(site_user)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {old.access_token}")
    r = c.post("/api/v1/auth/password/change/",
               {"current_password": "SitePass123!", "new_password": "AnotherPass77!"}, format="json")
    assert r.status_code == 200 and r.data["access"]
    assert c.get("/api/v1/auth/me/").status_code == 401            # old token revoked
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
    assert c.get("/api/v1/auth/me/").status_code == 200            # fresh one works
