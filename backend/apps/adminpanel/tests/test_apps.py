"""Admin "Apps" page: operator tools downloaded from our own server."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.adminpanel.tests.conftest import make_staff
from apps.common.models import AuditLog
from apps.payments_sms.models import SmsAppDevice
from apps.settings_app.models import AppRelease

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _dirs(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    rel = tmp_path / "releases"
    rel.mkdir()
    settings.APP_RELEASES_DIR = str(rel)
    return rel


def test_bundled_apk_is_listed_and_downloadable(staff_client, superadmin, _dirs):
    (_dirs / "CaspinTunelSmsBridge-debug.apk").write_bytes(b"PK\x03\x04apk")
    c = staff_client(superadmin)
    rows = {r["platform"]: r for r in c.get("/api/v1/admin/apps/").data["results"]}
    assert rows["android"]["source"] == "bundled" and rows["android"]["size"] == 7
    assert rows["ios"]["source"] == "repo" and rows["ios"]["file_name"] == "CaspinSMS.shortcut"
    r = c.get("/api/v1/admin/apps/android/download/")
    assert r.status_code == 200 and b"".join(r.streaming_content) == b"PK\x03\x04apk"
    assert r["Content-Type"] == "application/vnd.android.package-archive"
    assert 'filename="CaspinTunelSmsBridge-debug.apk"' in r["Content-Disposition"]
    assert c.get("/api/v1/admin/apps/ios/download/").status_code == 200   # built from the repo template


def test_ios_is_never_uploaded_but_link_and_notes_are_editable(staff_client, superadmin):
    c = staff_client(superadmin)
    r = c.post("/api/v1/admin/apps/ios/", {"file": SimpleUploadedFile("x.shortcut", b"s")}, format="multipart")
    assert r.status_code == 400 and "repository" in r.data["detail"]
    r = c.post("/api/v1/admin/apps/ios/", {"link": "https://www.icloud.com/shortcuts/abc", "notes": "iOS 17+"},
               format="multipart")
    assert r.status_code == 200 and r.data["link"].startswith("https://www.icloud.com") and r.data["source"] == "repo"
    assert AuditLog.objects.filter(action="apps.release_updated").exists()


def test_uploaded_apk_wins_over_bundled(staff_client, superadmin, _dirs):
    (_dirs / "CaspinTunelSmsBridge-debug.apk").write_bytes(b"PK\x03\x04apk")
    c = staff_client(superadmin)
    c.post("/api/v1/admin/apps/android/", {"file": SimpleUploadedFile("bridge-2.0.apk", b"new")}, format="multipart")
    assert c.get("/api/v1/admin/apps/").data["results"][0]["source"] == "upload"


def test_upload_guards_and_permission(staff_client, superadmin, perms):
    c = staff_client(superadmin)
    bad = c.post("/api/v1/admin/apps/android/", {"file": SimpleUploadedFile("x.exe", b"x")}, format="multipart")
    assert bad.status_code == 400
    assert c.post("/api/v1/admin/apps/ios/", {"link": "javascript:alert(1)"}, format="multipart").status_code == 400
    assert c.get("/api/v1/admin/apps/windows/download/").status_code == 404
    viewer = make_staff("viewer", ["users.view"], perms)
    assert staff_client(viewer).get("/api/v1/admin/apps/").status_code == 403
    assert not AppRelease.objects.filter(platform="android").exclude(file="").exists()



# ---------------------------------------------------------------- v1.48 Android setup QR
STORE_HOST = "shop-qr.example"


@pytest.fixture
def qr_content(monkeypatch):
    """What the setup QR encodes (the PNG itself is qrcode's job)."""
    from apps.adminpanel.views import apps as view

    seen = []
    real = view.qrcode.make

    def make(data, **kw):
        seen.append(data)
        return real(data, **kw)

    monkeypatch.setattr(view.qrcode, "make", make)
    return seen


def _parse_like_the_app(uri):
    """Mirror of mobile_sms SetupQr.parse(): caspin-sms://host[:port]?token=… → (https://host[:port], token)."""
    from urllib.parse import parse_qs, urlsplit

    parts = urlsplit(uri)
    assert parts.scheme == "caspin-sms" and parts.path == "" and not parts.fragment
    return f"https://{parts.netloc}", parse_qs(parts.query)["token"][0]


def test_android_setup_qr_on_our_domain(staff_client, superadmin, perms, qr_content):
    from apps.settings_app.models import SiteConfig

    cfg = SiteConfig.load(); cfg.site_domain = "caspin.example"; cfg.save()
    device = SmsAppDevice.objects.create(name="Test phone")
    c = staff_client(superadmin)
    assert c.get("/api/v1/admin/apps/android/qr/").status_code == 404
    assert c.get("/api/v1/admin/apps/android/qr/?device=99999").status_code == 404
    r = c.get(f"/api/v1/admin/apps/android/qr/?device={device.id}")
    assert r.status_code == 200 and r["Content-Type"] == "image/png" and r.content[:4] == b"\x89PNG"
    assert r["Cache-Control"] == "private, no-store"
    assert _parse_like_the_app(qr_content[-1]) == ("https://caspin.example", device.api_token)
    log = AuditLog.objects.get(action="apps.android_qr")
    assert device.api_token not in str(log.detail)                       # never the token in the audit log
    android = c.get("/api/v1/admin/apps/").data["results"][0]
    assert android["platform"] == "android" and android["server"] == "https://caspin.example"
    viewer = make_staff("viewer2", ["settings.manage"], perms)           # sms.manage reveals tokens; settings alone not
    assert staff_client(viewer).get(f"/api/v1/admin/apps/android/qr/?device={device.id}").status_code == 403
    device.is_active = False; device.save()
    assert c.get(f"/api/v1/admin/apps/android/qr/?device={device.id}").status_code == 404


def test_android_setup_qr_on_a_store_domain_points_the_app_at_that_store(qr_content):
    from rest_framework.test import APIClient

    from apps.payments_sms.tests.test_blu import staff_client as blu_staff
    from apps.tenancy import context
    from apps.tenancy.models import Tenant, TenantDomain

    t = Tenant.objects.create(slug="sqr", name="Store QR", status="active", reseller_username="sqradmin")
    TenantDomain.objects.create(tenant=t, host=STORE_HOST, state="active")
    with context.tenant_context(t.pk):
        device = SmsAppDevice.objects.create(name="reseller phone")
    boss = blu_staff("super", "qr-boss")
    boss.defaults["HTTP_HOST"] = STORE_HOST
    r = boss.get(f"/api/v1/admin/apps/android/qr/?device={device.id}")
    assert r.status_code == 200, r.content
    base, token = _parse_like_the_app(qr_content[-1])
    assert (base, token) == (f"https://{STORE_HOST}", device.api_token)
    rows = {x["platform"]: x for x in boss.get("/api/v1/admin/apps/").data["results"]}
    assert rows["android"]["server"] == base
    assert rows["ios"]["endpoint"] == f"{base}/api/v1/payments/sms/inbound-batch/"   # the Shortcut too (was our domain)
    # what the app then does with it: ping on that host with that token → the store's device
    app = APIClient(HTTP_HOST=STORE_HOST)
    app.credentials(HTTP_X_DEVICE_TOKEN=token)
    ping = app.get("/api/v1/payments/sms/ping/")
    assert ping.status_code == 200 and ping.json()["device"] == "reseller phone"
    # our panel never sees a store's device
    ours = blu_staff("super", "qr-ours")
    assert ours.get(f"/api/v1/admin/apps/android/qr/?device={device.id}").status_code == 404


# ---------------------------------------------------------------- v1.48 CI-built APK
def test_ci_apk_is_served_from_here_between_upload_and_bundled(staff_client, superadmin, _dirs, tmp_path, monkeypatch):
    from apps.settings_app import ci_apk

    (_dirs / "CaspinTunelSmsBridge-debug.apk").write_bytes(b"PK\x03\x04apk")
    ci = tmp_path / "SmsBridge-1.2.0.apk"
    ci.write_bytes(b"PK\x03\x04signed")
    monkeypatch.setattr(ci_apk, "latest", lambda: {"name": ci.name, "version": "1.2.0", "size": 10})
    monkeypatch.setattr(ci_apk, "local_file", lambda: ci)
    c = staff_client(superadmin)
    android = c.get("/api/v1/admin/apps/").data["results"][0]
    assert (android["source"], android["version"], android["file_name"]) == ("ci", "1.2.0", "SmsBridge-1.2.0.apk")
    r = c.get("/api/v1/admin/apps/android/download/")
    assert r.status_code == 200 and b"".join(r.streaming_content) == b"PK\x03\x04signed"   # bytes, never a redirect
    assert 'filename="SmsBridge-1.2.0.apk"' in r["Content-Disposition"]
    c.post("/api/v1/admin/apps/android/", {"file": SimpleUploadedFile("bridge-9.apk", b"upl")}, format="multipart")
    assert c.get("/api/v1/admin/apps/").data["results"][0]["source"] == "upload"
    AppRelease.objects.filter(platform="android").update(file="")
    monkeypatch.setattr(ci_apk, "latest", lambda: None)
    monkeypatch.setattr(ci_apk, "local_file", lambda: None)
    assert c.get("/api/v1/admin/apps/").data["results"][0]["source"] == "bundled"
    assert b"".join(c.get("/api/v1/admin/apps/android/download/").streaming_content) == b"PK\x03\x04apk"


class _Resp:
    def __init__(self, status=200, data=None, body=b""):
        self.status_code, self._data, self._body = status, data, body

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def iter_content(self, n):
        yield self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_ci_apk_copy_checks_size_and_digest(settings, monkeypatch, _dirs):
    import hashlib

    import requests
    from django.core.cache import cache

    from apps.settings_app import ci_apk

    settings.CI_APK_FROM_GITHUB = True
    body = b"PK\x03\x04release"
    release = {"tag_name": "v1.48.0", "assets": [
        {"name": "notes.txt", "size": 3, "url": "x"},
        {"name": "SmsBridge-1.2.0.apk", "size": len(body), "url": "https://api.github.com/assets/1",
         "digest": "sha256:" + hashlib.sha256(body).hexdigest()}]}
    served = {"body": body}

    def get(url, **kw):
        return _Resp(data=release) if "releases/latest" in url else _Resp(body=served["body"])

    monkeypatch.setattr(requests, "get", get)
    cache.delete(ci_apk.CACHE_KEY)
    assert ci_apk.latest()["version"] == "1.2.0"
    served["body"] = b"PK\x03\x04tampered"                       # wrong bytes → refused, nothing kept
    assert ci_apk.local_file() is None and not list(ci_apk.ci_dir().glob("*"))
    served["body"] = body
    got = ci_apk.local_file()
    assert got.name == "SmsBridge-1.2.0.apk" and got.read_bytes() == body
    cache.delete(ci_apk.CACHE_KEY)
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(status=500))
    assert ci_apk.latest() is None and ci_apk.local_file() == got  # GitHub down: keep serving the copy we have
