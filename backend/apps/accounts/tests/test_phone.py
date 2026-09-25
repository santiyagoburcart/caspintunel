"""Phone normalization + the site-side phone rules (Phase 2)."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.phone import normalize_ir_phone, normalize_phone
from apps.settings_app.utils import set_setting


@pytest.mark.parametrize("raw", [
    "09107323128", "+989107323128", "989107323128", "00989107323128", "9107323128",
    "۰۹۱۰۷۳۲۳۱۲۸", "٠٩١٠٧٣٢٣١٢٨", "+۹۸۹۱۰۷۳۲۳۱۲۸",
    "0910 732 3128", "0910-732-3128", " +98 (910) 732-3128 ", "+98 0910 732 3128", "0098-910-7323128",
    "۰۹۱۰‌۷۳۲‌۳۱۲۸",   # with ZWNJ
])
def test_normalize_ir_phone_accepts_all_formats(raw):
    assert normalize_ir_phone(raw) == "09107323128"


@pytest.mark.parametrize("raw", [
    None, "", "   ", "abc", "0912", "091012345678", "0910732312",      # too short / long
    "08107323128",        # not a mobile (09…)
    "+14155552671", "004915112345678", "+9109107323128",            # foreign
    "12345678901", "+98", "0910732312a",
])
def test_normalize_ir_phone_rejects_invalid(raw):
    assert normalize_ir_phone(raw) is None


def test_normalize_phone_keeps_foreign_numbers_international():
    assert normalize_phone("+1 415 555 2671") == "+14155552671"
    assert normalize_phone("004915112345678") == "+4915112345678"
    assert normalize_phone("+989107323128") == "09107323128"
    assert normalize_phone("hello") is None


# --- site API ---------------------------------------------------------------


def _register(**over):
    payload = {"username": "alice", "password": "Str0ngPass!", "phone": "۰۹۱۲ ۱۲۳ ۴۵۶۷", "terms_accepted": True}
    payload.update(over)
    return APIClient().post("/api/v1/auth/register/", payload, format="json")


@pytest.mark.django_db
def test_register_normalizes_persian_digits():
    r = _register()
    assert r.status_code == 201, r.data
    assert User.objects.get(username="alice").phone == "09121234567"


@pytest.mark.django_db
def test_register_requires_phone_when_iran_only():
    r = _register(phone="")
    assert r.status_code == 400 and "phone" in r.data
    r = APIClient().post("/api/v1/auth/register/", {"username": "bob", "password": "Str0ngPass!", "terms_accepted": True}, format="json")
    assert r.status_code == 400 and "phone" in r.data


@pytest.mark.django_db
def test_register_rejects_foreign_phone_with_clear_message():
    r = _register(phone="+14155552671")
    assert r.status_code == 400
    msg = str(r.data["phone"][0])
    assert "با 09 شروع" in msg and "09121234567" in msg
    assert not any("\u06f0" <= ch <= "\u06f9" for ch in msg)  # Latin digits only


@pytest.mark.django_db
def test_register_phone_optional_and_international_when_setting_off():
    set_setting("iran_phone_only", "false", "bool")
    assert _register(phone="").status_code == 201
    r = _register(username="bob", phone="+1 415 555 2671")
    assert r.status_code == 201, r.data
    assert User.objects.get(username="bob").phone == "+14155552671"


@pytest.mark.django_db
def test_register_duplicate_phone_is_rejected():
    assert _register().status_code == 201
    r = _register(username="bob", phone="+989121234567")
    assert r.status_code == 400 and "phone" in r.data


@pytest.mark.django_db
def test_site_cannot_claim_a_bot_users_phone():
    User.objects.create_user("tg_x", "Str0ngPass!", telegram_id=42, phone="09107323128")
    r = _register(phone="+989107323128")
    assert r.status_code == 400
    assert "ربات" in str(r.data["phone"][0])           # "share it from inside the bot"
    assert User.objects.get(telegram_id=42).phone == "09107323128"   # no merge from the site side


@pytest.mark.django_db
def test_profile_phone_update_validates_and_normalizes():
    u = User.objects.create_user("carol", "Str0ngPass!", phone="09121111111")
    User.objects.create_user("tg_y", "Str0ngPass!", telegram_id=7, phone="09352222222")
    c = APIClient()
    c.force_authenticate(u)
    assert c.patch("/api/v1/auth/me/", {"phone": "0912"}, format="json").status_code == 400
    r = c.patch("/api/v1/auth/me/", {"phone": "09352222222"}, format="json")
    assert r.status_code == 400 and r.data["code"] == "phone_in_bot"
    r = c.patch("/api/v1/auth/me/", {"phone": "+98 912 333 4444"}, format="json")
    assert r.status_code == 200 and r.data["user"]["phone"] == "09123334444"
    # own number again is not a "duplicate"; other fields don't touch the phone rule
    assert c.patch("/api/v1/auth/me/", {"phone": "09123334444"}, format="json").status_code == 200
    assert c.patch("/api/v1/auth/me/", {"name": "Carol"}, format="json").status_code == 200


@pytest.mark.django_db
def test_migration_normalizes_and_reports_duplicates(capsys):
    import importlib

    from django.apps import apps as django_apps

    mig = importlib.import_module("apps.accounts.migrations.0005_normalize_user_phones")
    User.objects.create_user("a", "x" * 10, phone="989107323128")
    User.objects.create_user("b", "x" * 10, phone="09107323128")
    User.objects.create_user("c", "x" * 10, phone="۰۹۳۵ ۱۱۱ ۲۲۳۳")
    mig.normalize(django_apps, None)
    assert set(User.objects.values_list("phone", flat=True)) == {"09107323128", "09351112233"}
    out = capsys.readouterr().out
    assert "09107323128" in out and "shared by several accounts" in out
