import pytest

from apps.adminpanel.tests.conftest import make_staff
from apps.panel.models import Panel
from apps.telegram.models import BotType, TelegramConfig

pytestmark = pytest.mark.django_db


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
