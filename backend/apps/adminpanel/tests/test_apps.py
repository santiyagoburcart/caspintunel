"""Admin "Apps" page: operator tools downloaded from our own server."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.adminpanel.tests.conftest import make_staff
from apps.common.models import AuditLog
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
    assert rows["ios"]["source"] is None
    r = c.get("/api/v1/admin/apps/android/download/")
    assert r.status_code == 200 and b"".join(r.streaming_content) == b"PK\x03\x04apk"
    assert r["Content-Type"] == "application/vnd.android.package-archive"
    assert 'filename="CaspinTunelSmsBridge-debug.apk"' in r["Content-Disposition"]
    assert c.get("/api/v1/admin/apps/ios/download/").status_code == 404


def test_upload_ios_shortcut_and_download(staff_client, superadmin):
    c = staff_client(superadmin)
    f = SimpleUploadedFile("Caspin SMS.shortcut", b"shortcut-bytes")
    r = c.post("/api/v1/admin/apps/ios/", {"file": f, "version": "1.3", "link": "https://www.icloud.com/shortcuts/abc",
                                          "notes": "iOS 17+"}, format="multipart")
    assert r.status_code == 200, r.data
    assert r.data["source"] == "upload" and r.data["version"] == "1.3" and r.data["file_name"] == "ios.shortcut"
    d = c.get("/api/v1/admin/apps/ios/download/")
    assert d.status_code == 200 and b"".join(d.streaming_content) == b"shortcut-bytes"
    assert AuditLog.objects.filter(action="apps.release_updated").exists()
    # an uploaded APK wins over the bundled one
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
