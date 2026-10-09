"""iPhone Shortcut distribution via iCloud: iOS 15+ only imports signed
shortcuts, so the official install is the iCloud link stored in the
`ios_shortcut_icloud_url` setting (validated; a device token never goes in it).
The unsigned repo build stays available as the "advanced" download."""
import io

import pytest
from django.core.management import call_command
from PIL import Image

from apps.adminpanel.tests.conftest import make_staff
from apps.common.models import AuditLog
from apps.payments_sms.models import SmsAppDevice
from apps.settings_app import shortcut
from apps.settings_app.utils import get_setting, set_setting

pytestmark = pytest.mark.django_db
GOOD = "https://www.icloud.com/shortcuts/0a1b2c3d4e5f60718293a4b5c6d7e8f9"


@pytest.mark.parametrize("url", [GOOD, GOOD + "/", "https://www.icloud.com/shortcuts/AbC12345"])
def test_valid_icloud_links(url):
    assert shortcut.clean_icloud_url(f"  {url} ") == url


@pytest.mark.parametrize("url", [
    "http://www.icloud.com/shortcuts/0a1b2c3d4e5f6071",            # not https
    "https://icloud.com/shortcuts/0a1b2c3d4e5f6071",               # wrong host
    "https://www.icloud.com.evil.example/shortcuts/0a1b2c3d",      # look-alike host
    "https://www.icloud.com/shortcuts/",                           # no id
    GOOD + "?token=abc",                                           # query string
    GOOD + "#abc",                                                 # fragment
    GOOD + "/extra",                                               # extra path
    "javascript:alert(1)",
])
def test_invalid_icloud_links_are_rejected(url):
    with pytest.raises(ValueError):
        shortcut.clean_icloud_url(url)


def test_a_device_token_is_never_accepted_in_the_link():
    dev = SmsAppDevice.objects.create(name="iPhone")
    dev.api_token = "Tok3nTok3nTok3nTok3nTok3n12"
    dev.save()
    with pytest.raises(ValueError, match="token"):
        shortcut.clean_icloud_url(f"https://www.icloud.com/shortcuts/{dev.api_token}")


def test_empty_clears_and_a_bad_stored_value_is_ignored():
    assert shortcut.clean_icloud_url("") == "" and shortcut.clean_icloud_url(None) == ""
    set_setting(shortcut.ICLOUD_SETTING, "https://evil.example/x")
    assert shortcut.icloud_url() == ""


def test_settings_api_edits_and_validates_the_link(staff_client, superadmin):
    c = staff_client(superadmin)
    keys = {s["key"] for s in c.get("/api/v1/admin/settings/").json()["settings"]}
    assert shortcut.ICLOUD_SETTING in keys
    bad = c.put("/api/v1/admin/settings/", {shortcut.ICLOUD_SETTING: "https://example.com/x"}, format="json")
    assert bad.status_code == 400 and bad.json()["field"] == shortcut.ICLOUD_SETTING
    ok = c.put("/api/v1/admin/settings/", {shortcut.ICLOUD_SETTING: GOOD}, format="json")
    assert ok.status_code == 200
    assert get_setting(shortcut.ICLOUD_SETTING) == GOOD


def test_apps_page_reads_and_saves_the_link(staff_client, superadmin):
    c = staff_client(superadmin)
    ios = next(r for r in c.get("/api/v1/admin/apps/").json()["results"] if r["platform"] == "ios")
    assert ios["icloud_url"] == ""
    r = c.post("/api/v1/admin/apps/ios/", {"icloud_url": GOOD, "notes": "v1"})
    assert r.status_code == 200 and r.json()["icloud_url"] == GOOD
    assert get_setting(shortcut.ICLOUD_SETTING) == GOOD
    log = AuditLog.objects.filter(action="apps.release_updated").latest("id")
    assert log.detail.get("icloud_url_changed") is True
    # rejected values change nothing
    r = c.post("/api/v1/admin/apps/ios/", {"icloud_url": "https://www.icloud.com/shortcuts/abc12345?t=1", "notes": "v2"})
    assert r.status_code == 400 and r.json()["field"] == "icloud_url"
    assert get_setting(shortcut.ICLOUD_SETTING) == GOOD
    # clearing it is allowed
    assert c.post("/api/v1/admin/apps/ios/", {"icloud_url": ""}).json()["icloud_url"] == ""


def test_qr_code_of_the_link(staff_client, superadmin):
    c = staff_client(superadmin)
    assert c.get("/api/v1/admin/apps/ios/qr/").status_code == 404
    set_setting(shortcut.ICLOUD_SETTING, GOOD)
    r = c.get("/api/v1/admin/apps/ios/qr/")
    assert r.status_code == 200 and r["Content-Type"] == "image/png"
    assert "no-store" in r["Cache-Control"]
    img = Image.open(io.BytesIO(r.content))
    assert img.size[0] == img.size[1] and img.size[0] > 100


def test_icloud_endpoints_need_settings_manage(staff_client, perms):
    nobody = staff_client(make_staff("n", ["users.view"], perms))
    assert nobody.get("/api/v1/admin/apps/ios/qr/").status_code == 403
    assert nobody.post("/api/v1/admin/apps/ios/", {"icloud_url": GOOD}).status_code == 403
    assert get_setting(shortcut.ICLOUD_SETTING, "") == ""


def test_unsigned_download_still_available(staff_client, superadmin):
    r = staff_client(superadmin).get("/api/v1/admin/apps/ios/download/")
    assert r.status_code == 200 and r["Content-Disposition"].endswith('CaspinSMS.shortcut"')


def test_seed_never_overwrites_the_panel_value():
    set_setting(shortcut.ICLOUD_SETTING, GOOD)
    call_command("seed")
    assert get_setting(shortcut.ICLOUD_SETTING) == GOOD
