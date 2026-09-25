import pytest
from django.core.management import call_command

from apps.accounts.models import Permission, Role
from apps.settings_app.management.commands.seed import PERMISSIONS
from apps.settings_app.models import Page, Setting, SiteConfig, Theme
from apps.telegram.models import TelegramConfig

pytestmark = pytest.mark.django_db


def test_seed_is_idempotent_and_complete():
    call_command("seed")
    call_command("seed")  # second run must not blow up or duplicate

    assert Permission.objects.count() == len(PERMISSIONS)
    assert Role.objects.filter(name="Super Admin").exists()
    assert Role.objects.get(name="Super Admin").permissions.count() == len(PERMISSIONS)

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


def test_reseeding_keeps_the_admin_sync_interval(settings):
    """seed used to rebuild the sync task from PANEL_SYNC_INTERVAL_MINUTES,
    silently undoing the interval chosen in the admin panel."""
    from django_celery_beat.models import PeriodicTask

    from apps.settings_app.utils import set_setting

    call_command("seed")
    set_setting("service_sync_interval_minutes", 7, "int")
    call_command("seed")

    task = PeriodicTask.objects.get(name="panel: sync all services")
    assert task.interval.every == 7 and task.enabled


def test_env_panel_is_seed_only(settings):
    """PANEL_* env vars create the first panel on an empty install and are
    ignored (never overwrite / duplicate) once any panel exists."""
    from apps.panel.models import Panel

    settings.PANEL_BASE_URL = "https://env-panel.example"
    settings.PANEL_ADMIN_USERNAME = "envadmin"
    settings.PANEL_ADMIN_PASSWORD = "envpw"
    call_command("seed")
    assert Panel.objects.count() == 1

    p = Panel.objects.get()
    p.name, p.base_url = "Edited in panel", "https://real.example"
    p.save()
    call_command("seed")
    assert Panel.objects.count() == 1
    p.refresh_from_db()
    assert (p.name, p.base_url) == ("Edited in panel", "https://real.example")


def test_seed_without_env_tokens_keeps_bot_tokens(monkeypatch):
    """Bot tokens are managed in the admin panel; an empty BOT_*_TOKEN env
    must never blank or deactivate an existing bot."""
    monkeypatch.delenv("BOT_SALES_TOKEN", raising=False)
    call_command("seed")
    bot = TelegramConfig.objects.get(bot_type="sales")
    bot.token, bot.is_active = "123:abc", True
    bot.save()

    call_command("seed")
    bot.refresh_from_db()
    assert bot.token == "123:abc" and bot.is_active
