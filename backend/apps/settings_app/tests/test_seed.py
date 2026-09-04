import pytest
from django.core.management import call_command

from apps.accounts.models import Permission, Role
from apps.settings_app.models import Page, Setting, SiteConfig, Theme
from apps.telegram.models import TelegramConfig

pytestmark = pytest.mark.django_db


def test_seed_is_idempotent_and_complete():
    call_command("seed")
    call_command("seed")  # second run must not blow up or duplicate

    assert Permission.objects.count() == 15
    assert Role.objects.filter(name="Super Admin").exists()
    assert Role.objects.get(name="Super Admin").permissions.count() == 15

    theme = Theme.objects.get(name="Midnight Aurora")
    assert theme.is_active
    assert "dark" in theme.palette and "light" in theme.palette

    frost = Theme.objects.get(name="Royal Frost")
    assert frost.is_active is False
    assert frost.palette["base"] == "light" and frost.palette["style"] == "frost"

    assert SiteConfig.objects.count() == 1
    assert Setting.objects.get(key="unique_amount_min").typed == 200
    assert Setting.objects.get(key="email_verification_required").typed is False
    assert Page.objects.filter(slug__in=["rules", "tutorial", "faq"]).count() == 3
    assert TelegramConfig.objects.count() == 2


def test_setting_typed_casts():
    s = Setting.objects.create(key="x", value="true", value_type="bool")
    assert s.typed is True


def test_reseeding_never_undoes_an_admin_theme_choice():
    """`seed` runs on every container start / update — it must not silently
    flip the active theme back to Midnight Aurora."""
    call_command("seed")
    frost = Theme.objects.get(name="Royal Frost")
    frost.is_active = True
    frost.save()  # Theme.save() deactivates Midnight Aurora

    call_command("seed")

    frost.refresh_from_db()
    assert frost.is_active is True
    assert Theme.objects.get(name="Midnight Aurora").is_active is False
