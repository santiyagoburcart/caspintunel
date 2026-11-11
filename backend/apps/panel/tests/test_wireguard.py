"""v1.55 WireGuard configs (panel/wireguard.py).

PasarGuard 5.6 gives ONE zip per user (one .conf per host remark, e.g. «_Ita_bob.conf»); we split it on demand (never
stored) into locations with a country name + flag from «مکان‌های وایرگارد» (unknown code → the code itself), serve each .conf
and a clean-named zip to the OWNER only (rate-limited, audited), send them as documents in the bot / from the Mini App, mirror
`Service.wireguard` from the user's peer IPs, hide the subscription link for «فقط وایرگارد» plans, and check a plan's type
against its groups (a WireGuard group = only WireGuard inbounds — per-location groups later need no code change).
"""
import io
import zipfile
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.common.models import AuditLog
from apps.panel import mappers
from apps.panel import wireguard as W
from apps.panel.models import Panel, Service, ServiceStatus, WireguardLocation
from apps.plans.models import Plan
from apps.settings_app.models import SiteConfig

pytestmark = pytest.mark.django_db
CONF = b"[Interface]\nPrivateKey = k\nAddress = 10.0.0.2/32\n\n[Peer]\nPublicKey = p\nEndpoint = wir.example:7600\n"


def _zip(username, codes=("_Ita", "de", "XX")):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for c in codes:
            z.writestr(f"{c}_{username}.conf", CONF + c.encode())
    return buf.getvalue()


@pytest.fixture
def setup(monkeypatch):
    cache.clear()
    cfg = SiteConfig.load(); cfg.site_name_en = "Caspin Tunel"; cfg.save()
    user = User.objects.create_user("cust", "Str0ngPass!", telegram_id=7070)
    panel = Panel.objects.create(name="P", base_url="https://x", admin_username="a", admin_password_enc="p")
    plan = Plan.objects.create(name_fa="p", price=Decimal("1"), panel=panel, vpn_type="both", group_ids=[5, 10])
    svc = Service.objects.create(user=user, panel=panel, panel_username="bob", current_plan=plan, status=ServiceStatus.ACTIVE,
                                 subscription_url="https://x/sub/tok/", wireguard=True,
                                 expire_at=timezone.now() + timezone.timedelta(days=10))
    calls = []
    monkeypatch.setattr(W, "fetch_zip", lambda s: calls.append(s.panel_username) or _zip(s.panel_username))
    c = APIClient(); c.force_authenticate(user)
    return user, svc, c, calls


def test_locations_are_prefilled_and_the_zip_is_split_per_location(setup):
    user, svc, c, calls = setup
    assert set(WireguardLocation.objects.values_list("code", flat=True)) == {"Ita", "tu", "de", "nl", "IR"}
    r = c.get(f"/api/v1/services/{svc.id}/wireguard/").json()
    rows = {x["code"]: x for x in r["results"]}
    assert rows["Ita"]["name_fa"] == "ایتالیا" and rows["Ita"]["flag"] == "\U0001F1EE\U0001F1F9"
    assert rows["de"]["filename"] == f"CT-{svc.id}-germany.conf" and rows["de"]["name_en"] == "Germany"
    assert rows["XX"]["name_en"] == "XX" and rows["XX"]["flag"] == ""                 # unknown code → the raw code
    assert [x["code"] for x in r["results"]][:2] == ["Ita", "de"]                     # sorted like the table
    f = c.get(f"/api/v1/services/{svc.id}/wireguard/{rows['de']['key']}/")
    assert f.status_code == 200 and f.content == CONF + b"de"
    assert f["Content-Disposition"] == f'attachment; filename="CT-{svc.id}-germany.conf"' and f["Cache-Control"] == "private, no-store"
    a = c.get(f"/api/v1/services/{svc.id}/wireguard/all/")
    names = zipfile.ZipFile(io.BytesIO(a.content)).namelist()
    assert a["Content-Disposition"].endswith(f'CT-{svc.id}-wireguard.zip"') and f"CT-{svc.id}-italy.conf" in names
    assert AuditLog.objects.filter(action="service.wireguard_download").count() == 2
    assert len(calls) == 3                                                               # fetched each time, never stored


def test_only_the_owner_and_only_with_wireguard(setup):
    user, svc, c, _ = setup
    other = User.objects.create_user("mallory", "Str0ngPass!")
    m = APIClient(); m.force_authenticate(other)
    assert m.get(f"/api/v1/services/{svc.id}/wireguard/").status_code == 404
    assert m.get(f"/api/v1/services/{svc.id}/wireguard/all/").status_code == 404
    assert APIClient().get(f"/api/v1/services/{svc.id}/wireguard/").status_code in (401, 403)
    Service.objects.filter(pk=svc.pk).update(wireguard=False)
    assert c.get(f"/api/v1/services/{svc.id}/wireguard/").status_code == 404


def test_a_wireguard_only_plan_shows_no_subscription_link(setup):
    user, svc, c, _ = setup
    d = c.get(f"/api/v1/services/{svc.id}/").json()
    assert d["subscription_url"] and d["show_subscription"] and d["wireguard"] and d["qr"]
    Plan.objects.filter(pk=svc.current_plan_id).update(vpn_type="wireguard")
    d = c.get(f"/api/v1/services/{svc.id}/").json()
    assert d["subscription_url"] == "" and d["show_subscription"] is False and d["qr"] is None and d["plan_vpn_type"] == "wireguard"
    assert c.get(f"/api/v1/services/{svc.id}/qr/").status_code == 404
    from apps.telegram.shop import sub_link_block

    svc.refresh_from_db()
    assert sub_link_block(svc) == ""


def test_the_sync_mirrors_wireguard_access_from_peer_ips(setup):
    user, svc, c, _ = setup
    svc.wireguard = False
    mappers.apply_user_to_service(svc, {"proxy_settings": {"wireguard": {"peer_ips": ["10.0.0.2/32"]}}}, svc.panel)
    assert svc.wireguard is True
    mappers.apply_user_to_service(svc, {"proxy_settings": {"wireguard": {"private_key": "k", "peer_ips": []}}}, svc.panel)
    assert svc.wireguard is False
    svc.wireguard = True
    mappers.apply_user_to_service(svc, {"status": "active"}, svc.panel)                 # no proxy data → unchanged
    assert svc.wireguard is True


def test_plan_type_must_match_its_groups(setup, monkeypatch):
    user, svc, c, _ = setup
    monkeypatch.setattr(W, "group_kinds", lambda panel: {5: {"wireguard": False}, 10: {"wireguard": True},
                                                          77: {"wireguard": True}})
    assert W.check_plan_groups("wireguard", [10], svc.panel) is None
    assert W.check_plan_groups("wireguard", [10, 77], svc.panel) is None                # future per-location groups
    assert "فقط گروه‌های وایرگارد" in W.check_plan_groups("wireguard", [5, 10], svc.panel)
    assert W.check_plan_groups("both", [5, 10], svc.panel) is None
    assert W.check_plan_groups("both", [10], svc.panel)
    assert W.check_plan_groups("sub", [5], svc.panel) is None
    assert W.check_plan_groups("sub", [5, 10], svc.panel)
    from apps.payments_sms.tests.test_blu import staff_client

    boss = staff_client("super", "wg-boss")
    r = boss.patch(f"/api/v1/admin/plans/{svc.current_plan_id}/", {"vpn_type": "wireguard"}, format="json")
    assert r.status_code == 400 and "vpn_type" in r.json()
    r = boss.patch(f"/api/v1/admin/plans/{svc.current_plan_id}/", {"vpn_type": "wireguard", "group_ids": [10]}, format="json")
    assert r.status_code == 200, r.content
    # the panel is down → never blocks saving a plan
    monkeypatch.setattr(W, "group_kinds", lambda panel: (_ for _ in ()).throw(RuntimeError("down")))
    assert W.check_plan_groups("wireguard", [5], svc.panel) is None


def test_wireguard_groups_are_those_with_only_wireguard_inbounds(setup, monkeypatch):
    user, svc, c, _ = setup

    class FakeClient:
        def _request(self, method, path, **kw):
            assert method == "GET"
            return {"cores": [{"type": "wg", "config": {"interface_name": "WG_7600"}},
                              {"type": "wg", "config": {"interface_name": "WG_3535"}},
                              {"type": "xray", "config": {"inbounds": [{"tag": "STR-DE"}]}}]}

        def list_groups(self):
            return [{"id": 10, "name": "wirgard", "inbound_tags": ["WG_7600", "WG_3535"]},
                    {"id": 13, "name": "wg-de", "inbound_tags": ["WG_3535"]},
                    {"id": 8, "name": "tunel", "inbound_tags": ["STR-DE"]},
                    {"id": 9, "name": "mixed", "inbound_tags": ["STR-DE", "WG_7600"]}]

    monkeypatch.setattr("apps.panel.services.client_for", lambda panel: FakeClient())
    k = W.group_kinds(svc.panel)
    assert k[10]["wireguard"] and k[13]["wireguard"] and not k[8]["wireguard"] and not k[9]["wireguard"] and k[9]["has_wireguard"]


def test_locations_are_editable_by_our_staff(setup):
    from apps.payments_sms.tests.test_blu import staff_client

    boss = staff_client("super", "wg-boss2")
    rows = boss.get("/api/v1/admin/wireguard/locations/").json()
    rows = rows["results"] if isinstance(rows, dict) else rows
    de = next(r for r in rows if r["code"] == "de")
    r = boss.patch(f"/api/v1/admin/wireguard/locations/{de['id']}/", {"name_fa": "آلمان (فرانکفورت)", "slug": "Germany FRA"}, format="json")
    assert r.status_code == 200 and r.json()["slug"] == "germany-fra"
    assert boss.post("/api/v1/admin/wireguard/locations/", {"code": "DE", "name_fa": "x", "name_en": "x"}, format="json").status_code == 400
    assert AuditLog.objects.filter(action="wireguard.location_updated").exists()


def test_bot_lists_locations_and_sends_each_conf_as_a_document(setup, monkeypatch):
    from apps.telegram.bot import sales_bot
    from apps.telegram.tests.test_bot_screens import FakeBot, _datas

    user, svc, c, _ = setup
    User.objects.filter(pk=user.pk).update(phone="09120000000", terms_accepted_at=timezone.now())
    monkeypatch.setattr(sales_bot, "close_old_connections", lambda: None)
    import apps.panel.services as ps

    monkeypatch.setattr(ps, "refresh_watchable_services", lambda svcs: False)

    class DocBot(FakeBot):
        def send_document(self, chat_id, document, visible_file_name=None, caption=None, **kw):
            self.out.append(("doc", visible_file_name, document.read()))

    b = DocBot()
    sales_bot._register(b)
    assert f"s:{svc.id}:wg" in _datas(b.click(f"s:{svc.id}")[0][2])
    out = b.click(f"s:{svc.id}:wg")
    datas = _datas(out[0][2])
    assert f"s:{svc.id}:wg:all" in datas and any(d.endswith(":wg:de") for d in datas)
    out = b.click(f"s:{svc.id}:wg:de")
    assert out[-1][0] == "doc" and out[-1][1] == f"CT-{svc.id}-germany.conf" and out[-1][2] == CONF + b"de"
    assert AuditLog.objects.filter(action="service.wireguard_download", detail__via="bot").exists()
    Service.objects.filter(pk=svc.pk).update(wireguard=False)
    assert not any(d.endswith(":wg") for d in _datas(b.click(f"s:{svc.id}")[0][2]))      # no WireGuard → no button


def test_mini_app_sends_the_file_to_the_users_chat(setup, monkeypatch):
    user, svc, c, _ = setup
    sent = []

    class Client:
        def send_document_bytes(self, chat_id, name, data, **kw):
            sent.append((chat_id, name, data))

    monkeypatch.setattr("apps.telegram.config.sales_client", lambda: Client())
    r = c.post(f"/api/v1/services/{svc.id}/wireguard/all/send/", {}, format="json")
    assert r.status_code == 200, r.content
    assert sent[0][0] == 7070 and sent[0][1] == f"CT-{svc.id}-wireguard.zip"
