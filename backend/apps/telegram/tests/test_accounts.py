import pytest

from apps.accounts.models import Source, User
from apps.telegram.accounts import ensure_bot_user, link_phone

pytestmark = pytest.mark.django_db


def test_first_time_user_gets_random_credentials():
    user, created, password = ensure_bot_user(555, telegram_username="neo", name="Neo A")
    assert created is True
    assert password and len(password) >= 8
    assert user.username.startswith("tg_")
    assert user.source == Source.BOT
    assert user.telegram_id == 555
    assert user.check_password(password)


def test_returning_user_is_synced_not_recreated():
    u1, *_ = ensure_bot_user(555, telegram_username="neo")
    u2, created, password = ensure_bot_user(555, telegram_username="neo2", name="Neo")
    assert created is False and password is None
    assert u1.pk == u2.pk
    u2.refresh_from_db()
    assert u2.telegram_username == "neo2" and u2.name == "Neo"
    assert User.objects.filter(telegram_id=555).count() == 1


def test_link_phone_only_sets_when_missing():
    user, *_ = ensure_bot_user(777)
    link_phone(user, "09120001122")
    user.refresh_from_db()
    assert user.phone == "09120001122"
    link_phone(user, "09000000000")
    user.refresh_from_db()
    assert user.phone == "09120001122"  # unchanged — already set
