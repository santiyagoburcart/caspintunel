import pytest
import responses

from apps.adminpanel.tests.conftest import make_staff
from apps.panel.models import Panel
from apps.telegram.models import BotType, TelegramConfig

pytestmark = pytest.mark.django_db


def _panel():
    return Panel.objects.create(
        name="Pasargad", base_url="https://panel.test", admin_username="root",
        admin_password_enc="pw", is_active=True,
    )


@pytest.fixture
def boss(staff_client, superadmin):
    return staff_client(superadmin)


# --- panel ---------------------------------------------------------
def test_panel_config_roundtrip_hides_password(boss):
    r = boss.put("/api/v1/admin/integrations/panel/", {
        "base_url": "https://panel.example.test",
        "admin_username": "root",
        "admin_password": "s3cr3t",
        "default_group_ids": [5, 6],
    }, format="json")
    assert r.status_code == 200
    assert r.data["admin_password_set"] is True
    assert "admin_password" not in r.data
    assert "s3cr3t" not in str(r.data)

    panel = Panel.objects.get()
    assert panel.admin_password_enc == "s3cr3t"  # decrypted by the field


def test_panel_blank_password_keeps_stored_one(boss):
    boss.put("/api/v1/admin/integrations/panel/", {
        "base_url": "https://a.test", "admin_username": "u", "admin_password": "keepme",
    }, format="json")
    boss.patch("/api/v1/admin/integrations/panel/", {
        "base_url": "https://b.test", "admin_password": "",
    }, format="json")
    panel = Panel.objects.get()
    assert panel.base_url == "https://b.test"
    assert panel.admin_password_enc == "keepme"


@responses.activate
def test_panel_groups_lists_id_and_name(boss):
    _panel()
    responses.add(responses.POST, "https://panel.test/api/admin/token",
                  json={"access_token": "t"}, status=200)
    responses.add(responses.GET, "https://panel.test/api/groups",
                  json={"groups": [{"id": 5, "name": "Germany"}, {"id": 8, "name": "France"}]},
                  status=200)
    r = boss.get("/api/v1/admin/integrations/panel/groups/")
    assert r.status_code == 200
    assert r.data["groups"] == [{"id": 5, "name": "Germany"}, {"id": 8, "name": "France"}]


def test_panel_groups_needs_configured_panel(boss):
    r = boss.get("/api/v1/admin/integrations/panel/groups/")
    assert r.status_code == 400


@responses.activate
def test_panel_groups_reports_panel_failure(boss):
    _panel()
    responses.add(responses.POST, "https://panel.test/api/admin/token", status=401)
    r = boss.get("/api/v1/admin/integrations/panel/groups/")
    assert r.status_code == 502


def test_panel_config_requires_settings_manage(staff_client, perms):
    weak = staff_client(make_staff("weak", ["monitoring.view"], perms))
    assert weak.get("/api/v1/admin/integrations/panel/").status_code == 403
    ok = staff_client(make_staff("ok", ["settings.manage"], perms))
    assert ok.get("/api/v1/admin/integrations/panel/").status_code == 200


# --- telegram -----------------------------------------------------
def test_telegram_config_per_bot(boss):
    r = boss.put("/api/v1/admin/integrations/telegram/", {
        "sales": {"token": "sales-tok", "proxy_url": "socks5://127.0.0.1:9050", "is_active": True},
        "backup": {"token": "backup-tok", "backup_chat_id": -100123},
    }, format="json")
    assert r.status_code == 200
    assert r.data["sales"]["token_set"] is True
    assert r.data["sales"]["proxy_url"] == "socks5://127.0.0.1:9050"
    assert r.data["backup"]["backup_chat_id"] == -100123
    assert "sales-tok" not in str(r.data)

    assert TelegramConfig.objects.get(bot_type=BotType.SALES).token == "sales-tok"
    assert TelegramConfig.objects.get(bot_type=BotType.BACKUP).token == "backup-tok"


def test_telegram_blank_token_keeps_stored_one(boss):
    boss.put("/api/v1/admin/integrations/telegram/",
             {"sales": {"token": "first"}}, format="json")
    boss.put("/api/v1/admin/integrations/telegram/",
             {"sales": {"token": "", "is_active": True}}, format="json")
    cfg = TelegramConfig.objects.get(bot_type=BotType.SALES)
    assert cfg.token == "first"
    assert cfg.is_active is True


def test_telegram_config_requires_bots_manage(staff_client, perms):
    weak = staff_client(make_staff("weak2", ["settings.manage"], perms))
    assert weak.get("/api/v1/admin/integrations/telegram/").status_code == 403
    ok = staff_client(make_staff("ok2", ["bots.manage"], perms))
    assert ok.get("/api/v1/admin/integrations/telegram/").status_code == 200


# --- email status -------------------------------------------------
def test_email_status_reports_relay_state(boss, settings):
    settings.EMAIL_HOST = "mailserver"
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.SMTP_RELAY_HOST = ""
    r = boss.get("/api/v1/admin/integrations/email/")
    assert r.status_code == 200
    assert r.data["configured"] is True
    assert r.data["relay_configured"] is False
    assert r.data["external_delivery_ready"] is False

    settings.SMTP_RELAY_HOST = "smtp.mailgun.org"
    r = boss.get("/api/v1/admin/integrations/email/")
    assert r.data["relay_configured"] is True
    assert r.data["external_delivery_ready"] is True


def test_email_test_send_uses_locmem_backend(boss, settings):
    settings.EMAIL_HOST = "mailserver"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    from django.core import mail
    mail.outbox = []
    r = boss.post("/api/v1/admin/integrations/email/", {"to": "ops@example.com"}, format="json")
    assert r.status_code == 200 and r.data["ok"] is True
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["ops@example.com"]


def test_email_status_requires_settings_manage(staff_client, perms):
    weak = staff_client(make_staff("weak3", ["monitoring.view"], perms))
    assert weak.get("/api/v1/admin/integrations/email/").status_code == 403
