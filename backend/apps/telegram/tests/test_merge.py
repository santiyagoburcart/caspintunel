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
from apps.telegram.accounts import ensure_bot_user, handle_contact

pytestmark = pytest.mark.django_db


@pytest.fixture
def site_user():
    return User.objects.create_user("siteuser", "SitePass123!", phone="09107323128", email="s@example.com")


@pytest.fixture
def bot_user():
    user, *_ = ensure_bot_user(9001, telegram_username="botty", name="Bot Name")
    return user


def link_telegram_phone(user, phone):
    """the contact the bot account's owner shares (their own card)"""
    return handle_contact(user.telegram_id, phone, contact_user_id=user.telegram_id)


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
    # the site account keeps its username, password and live session
    assert site_user.username == "siteuser" and site_user.has_usable_password()
    assert web.get("/api/v1/auth/me/").status_code == 200
    assert APIClient().post("/api/v1/auth/login/", {"username": "siteuser", "password": "SitePass123!"},
                            format="json").status_code == 200
    # logged: admin note + audit
    assert "Telegram account merged" in site_user.admin_note and "orders" in site_user.admin_note.lower()
    assert "password unchanged" in site_user.admin_note
    log = AuditLog.objects.get(action="user.merged_telegram")
    assert log.target_id == site_user.pk and log.detail["bot_user"] == bot_user.pk
    assert log.detail["moved"]["orders.Order.user"] == 1 and log.staff_label == "telegram-bot"
    assert log.detail["password_kept"] is True
    # the bot now resolves to the site account
    again, created, _ = ensure_bot_user(9001)
    assert again.pk == site_user.pk and created is False


def test_new_password_via_bot_still_works_after_merge(site_user, bot_user):
    from apps.telegram.accounts import change_password_via_bot

    user = link_telegram_phone(bot_user, "+989107323128").user
    change_password_via_bot(user, "BrandNewPass9!")
    assert APIClient().post("/api/v1/auth/login/", {"username": "siteuser", "password": "BrandNewPass9!"},
                            format="json").status_code == 200


def test_plain_link_when_no_site_account(bot_user):
    res = link_telegram_phone(bot_user, "+98 935 111 2233")
    assert res.status == "phone_saved" and res.user.pk == bot_user.pk
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
    assert res.status == "phone_saved"
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


# --- phone-first flow (no bot account before the contact) -------------------------
def test_no_account_anywhere_creates_one_with_credentials():
    res = handle_contact(7001, "+98 912 000 1111", contact_user_id=7001, telegram_username="newbie", name="N")
    assert res.status == "created" and res.password
    u = User.objects.get(telegram_id=7001)
    assert u.phone == "09120001111" and u.username.startswith("tg_") and u.check_password(res.password)
    assert AuditLog.objects.filter(action="user.created_via_bot", target_id=u.pk).exists()
    assert User.objects.count() == 1


def test_site_account_gets_telegram_linked_and_keeps_its_login(site_user):
    """the hastisaedi case: site signup first, then /start + contact in the bot"""
    refresh = RefreshToken.for_user(site_user)
    res = handle_contact(7002, "۰۹۱۰۷۳۲۳۱۲۸", contact_user_id=7002, telegram_username="hasti", name="Hasti")
    assert res.status == "linked" and res.user.pk == site_user.pk and res.password is None
    site_user.refresh_from_db()
    assert site_user.telegram_id == 7002 and site_user.telegram_username == "hasti"
    assert site_user.username == "siteuser" and site_user.check_password("SitePass123!")
    assert User.objects.count() == 1                             # no second account
    assert APIClient().post("/api/v1/auth/login/", {"username": "siteuser", "password": "SitePass123!"},
                            format="json").status_code == 200
    assert APIClient().post("/api/v1/auth/token/refresh/", {"refresh": str(refresh)},
                            format="json").status_code == 200   # sessions untouched
    log = AuditLog.objects.get(action="user.linked_telegram")
    assert log.target_id == site_user.pk and log.detail["telegram_id"] == 7002
    assert "password unchanged" in site_user.admin_note


@pytest.mark.parametrize("raw", ["+989107323128", "00989107323128", "989107323128", "09107323128",
                                 "۰۹۱۰۷۳۲۳۱۲۸", "+98 910 732 3128"])
def test_every_phone_format_finds_the_site_account(site_user, raw):
    assert handle_contact(7003, raw, contact_user_id=7003).user.pk == site_user.pk


def test_someone_elses_contact_card_is_refused(site_user):
    """sharing another person's contact must never link or create anything"""
    res = handle_contact(7004, "+989107323128", contact_user_id=999)
    assert res.status == "not_own" and not res.ok and res.user is None
    site_user.refresh_from_db()
    assert site_user.telegram_id is None
    assert not User.objects.filter(telegram_id=7004).exists()
    assert handle_contact(7004, "+989107323128", contact_user_id=None).status == "not_own"


def test_phone_linked_to_another_telegram_is_refused_and_staff_told(monkeypatch, django_capture_on_commit_callbacks):
    from apps.telegram import accounts

    other = User.objects.create_user("webuser", "Str0ngPass!", telegram_id=1234, phone="09107323128")
    calls = []
    monkeypatch.setattr(accounts, "notify_staff_conflict", lambda *a: calls.append(a))
    with django_capture_on_commit_callbacks(execute=True):
        res = handle_contact(7005, "+989107323128", contact_user_id=7005, telegram_username="intruder")
    assert res.status == "conflict" and res.user is None
    other.refresh_from_db()
    assert other.telegram_id == 1234 and other.check_password("Str0ngPass!")
    assert not User.objects.filter(telegram_id=7005).exists()
    assert calls == [(7005, "intruder", "09107323128", other.pk)]
    assert AuditLog.objects.filter(action="user.telegram_link_conflict", target_id=other.pk).exists()


def test_conflict_alert_goes_to_linked_staff_with_users_manage(monkeypatch):
    from apps.accounts.models import Staff
    from apps.telegram import accounts, config

    owner = User.objects.create_user("webuser", "Str0ngPass!", telegram_id=1234, phone="09107323128")
    boss = Staff.objects.create(username="boss", is_superadmin=True, telegram_id=555)
    Staff.objects.create(username="nobody", telegram_id=556)          # no users.manage
    sent = []

    class Client:
        def send_message(self, chat_id, text, **kw):
            sent.append((chat_id, text))

    monkeypatch.setattr(config, "sales_client", lambda: Client())
    assert accounts.notify_staff_conflict(7006, "x", "09107323128", owner.pk) == 1
    assert sent[0][0] == boss.telegram_id and "09107323128" in sent[0][1]
    assert accounts.notify_staff_conflict(7006, "x", "09107323128", owner.pk) == 0   # once an hour


def test_old_phoneless_bot_account_merges_into_site_account_keeping_site_login(site_user, bot_user):
    res = handle_contact(9001, "+989107323128", contact_user_id=9001)
    assert res.status == "merged" and res.user.pk == site_user.pk
    assert User.objects.get(pk=site_user.pk).check_password("SitePass123!")
    assert not User.objects.filter(pk=bot_user.pk).exists()


def test_site_signup_with_a_bot_accounts_phone_points_to_login():
    User.objects.create_user("tg_abc", "Str0ngPass!", telegram_id=42, phone="09107323128", source="bot")
    r = APIClient().post("/api/v1/auth/register/", {
        "username": "second", "password": "Str0ngPass!9", "phone": "+989107323128", "terms_accepted": True,
    }, format="json")
    assert r.status_code == 400
    msg = str(r.data["phone"][0])
    assert "ربات" in msg and "رمز" in msg and "Change password" in msg
    assert not User.objects.filter(username="second").exists()


def test_site_signup_with_a_site_accounts_phone_points_to_forgot_password(site_user):
    r = APIClient().post("/api/v1/auth/register/", {
        "username": "second", "password": "Str0ngPass!9", "phone": "09107323128", "terms_accepted": True,
    }, format="json")
    assert r.status_code == 400 and "Forgot password" in str(r.data["phone"][0])
    assert User.objects.count() == 1
