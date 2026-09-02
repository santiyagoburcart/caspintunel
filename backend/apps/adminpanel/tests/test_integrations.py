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


# --- multi-panel manager (MP-Phase 2) -----------------------------
def test_panels_crud_add_second_and_third(boss):
    p1 = _panel()

    r2 = boss.post("/api/v1/admin/panels/", {
        "name": "Wireguard", "base_url": "https://wg.test", "admin_username": "a",
        "admin_password": "pw2", "default_group_ids": [7], "is_active": True,
    }, format="json")
    assert r2.status_code == 201, r2.data
    assert r2.data["admin_password_set"] is True and "admin_password" not in r2.data

    r3 = boss.post("/api/v1/admin/panels/", {
        "name": "Volume", "base_url": "https://vol.test", "admin_username": "a",
        "admin_password": "pw3",
    }, format="json")
    assert r3.status_code == 201

    listing = boss.get("/api/v1/admin/panels/")
    names = {row["name"] for row in listing.data["results"]}
    assert names == {"Pasargad", "Wireguard", "Volume"}
    assert "pw2" not in str(listing.data) and "pw3" not in str(listing.data)

    # edit without a password keeps the stored one
    edit = boss.patch(f"/api/v1/admin/panels/{r2.data['id']}/",
                      {"name": "WG"}, format="json")
    assert edit.status_code == 200
    assert Panel.objects.get(pk=r2.data["id"]).admin_password_enc == "pw2"


def test_panel_new_requires_password(boss):
    r = boss.post("/api/v1/admin/panels/", {
        "name": "X", "base_url": "https://x.test", "admin_username": "a",
    }, format="json")
    assert r.status_code == 400


def test_panel_delete_blocked_while_a_plan_uses_it(boss):
    from decimal import Decimal

    from apps.plans.models import Plan

    p = _panel()
    Plan.objects.create(panel=p, name_fa="on-p", price=Decimal("1"))
    r = boss.delete(f"/api/v1/admin/panels/{p.id}/")
    assert r.status_code == 409
    assert Panel.objects.filter(pk=p.id).exists()


def test_panel_delete_ok_when_unused(boss):
    p = _panel()
    p2 = Panel.objects.create(name="spare", base_url="https://s.test",
                              admin_username="a", admin_password_enc="pw")
    assert boss.delete(f"/api/v1/admin/panels/{p2.id}/").status_code == 204
    assert not Panel.objects.filter(pk=p2.id).exists()


@responses.activate
def test_panel_groups_action_targets_that_panel(boss):
    p = _panel()
    responses.add(responses.POST, "https://panel.test/api/admin/token",
                  json={"access_token": "t"}, status=200)
    responses.add(responses.GET, "https://panel.test/api/groups",
                  json={"groups": [{"id": 7, "name": "WG-DE"}]}, status=200)
    r = boss.get(f"/api/v1/admin/panels/{p.id}/groups/")
    assert r.status_code == 200
    assert r.data["groups"] == [{"id": 7, "name": "WG-DE"}]


def test_panels_require_settings_manage(staff_client, perms):
    weak = staff_client(make_staff("weakp", ["plans.manage"], perms))
    assert weak.get("/api/v1/admin/panels/").status_code == 403
    ok = staff_client(make_staff("okp", ["settings.manage"], perms))
    assert ok.get("/api/v1/admin/panels/").status_code == 200


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


# --- required channels (forced-join) -----------------------------
def test_required_channels_crud_and_normalisation(boss):
    from apps.telegram.models import RequiredChannel

    r = boss.post("/api/v1/admin/channels/",
                  {"channel_id": "mychan", "title": "My Channel"}, format="json")
    assert r.status_code == 201
    assert r.data["channel_id"] == "@mychan"                 # bare name normalised

    r2 = boss.post("/api/v1/admin/channels/",
                   {"channel_id": "-1001234567890", "invite_link": "https://t.me/+abc"},
                   format="json")
    assert r2.status_code == 201 and r2.data["channel_id"] == "-1001234567890"

    lst = boss.get("/api/v1/admin/channels/")
    assert len(lst.data["results"]) == 2
    assert lst.data["enforcement"] == {"force_channel_join": False, "force_share_phone": False}

    cid = r.data["id"]
    assert boss.patch(f"/api/v1/admin/channels/{cid}/", {"is_active": False},
                      format="json").status_code == 200
    assert boss.delete(f"/api/v1/admin/channels/{cid}/").status_code == 204
    assert RequiredChannel.objects.count() == 1


def test_channel_enforcement_toggles(boss):
    from apps.settings_app.utils import get_setting

    r = boss.patch("/api/v1/admin/channels/enforcement/",
                   {"force_channel_join": True, "force_share_phone": True}, format="json")
    assert r.status_code == 200
    assert r.data == {"force_channel_join": True, "force_share_phone": True}
    assert get_setting("force_channel_join") is True
    assert get_setting("force_share_phone") is True


@responses.activate
def test_channel_test_action_reports_bot_admin_status(boss):
    from apps.telegram.models import BotType, RequiredChannel, TelegramConfig

    TelegramConfig.objects.create(bot_type=BotType.SALES, token="123:abc", is_active=True)
    ch = RequiredChannel.objects.create(channel_id="@vip", title="VIP")

    B = "https://api.telegram.org/bot123:abc"
    responses.add(responses.POST, f"{B}/getChat",
                  json={"ok": True, "result": {"id": -100, "title": "VIP CHAN", "type": "channel"}})
    responses.add(responses.POST, f"{B}/getChatMemberCount",
                  json={"ok": True, "result": 4210})
    responses.add(responses.POST, f"{B}/getMe",
                  json={"ok": True, "result": {"id": 777, "is_bot": True}})
    responses.add(responses.POST, f"{B}/getChatMember",
                  json={"ok": True, "result": {"status": "administrator"}})

    r = boss.post(f"/api/v1/admin/channels/{ch.id}/test/")
    assert r.data["ok"] is True and r.data["bot_is_admin"] is True
    assert r.data["member_count"] == 4210
    ch.refresh_from_db()
    assert ch.title == "VIP CHAN" and ch.member_count == 4210 and ch.last_synced_at


@responses.activate
def test_channel_test_warns_when_bot_not_admin(boss):
    from apps.telegram.models import BotType, RequiredChannel, TelegramConfig

    TelegramConfig.objects.create(bot_type=BotType.SALES, token="123:abc", is_active=True)
    ch = RequiredChannel.objects.create(channel_id="@vip")

    B = "https://api.telegram.org/bot123:abc"
    responses.add(responses.POST, f"{B}/getChat",
                  json={"ok": True, "result": {"id": -100, "title": "VIP", "type": "channel"}})
    responses.add(responses.POST, f"{B}/getChatMemberCount", json={"ok": True, "result": 10})
    responses.add(responses.POST, f"{B}/getMe", json={"ok": True, "result": {"id": 777}})
    responses.add(responses.POST, f"{B}/getChatMember",
                  json={"ok": True, "result": {"status": "left"}})

    r = boss.post(f"/api/v1/admin/channels/{ch.id}/test/")
    assert r.data["ok"] is False and r.data["bot_is_admin"] is False


def test_channels_require_bots_manage(staff_client, perms):
    weak = staff_client(make_staff("weakc", ["settings.manage"], perms))
    assert weak.get("/api/v1/admin/channels/").status_code == 403
    ok = staff_client(make_staff("okc", ["bots.manage"], perms))
    assert ok.get("/api/v1/admin/channels/").status_code == 200


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
