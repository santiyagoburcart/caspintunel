import pytest
import responses

pytestmark = pytest.mark.django_db


@pytest.fixture
def boss(staff_client, superadmin):
    return staff_client(superadmin)


@responses.activate
def test_system_reports_version_and_update(boss, settings, tmp_path):
    settings.VERSION = "1.0.0"
    settings.GITHUB_TOKEN = ""  # force the plain UPDATE_CHECK_URL path
    settings.UPDATE_CHECK_URL = "https://example.test/VERSION"
    settings.UPDATE_SENTINEL_PATH = str(tmp_path / ".update-requested")
    responses.add(responses.GET, settings.UPDATE_CHECK_URL, body="1.2.0\n")

    r = boss.get("/api/v1/admin/system/")
    assert r.data["version"] == "1.0.0"
    assert r.data["latest_version"] == "1.2.0"
    assert r.data["update_available"] is True
    assert r.data["update_requested"] is False


def test_request_update_writes_sentinel(boss, settings, tmp_path):
    sentinel = tmp_path / ".update-requested"
    settings.UPDATE_SENTINEL_PATH = str(sentinel)
    r = boss.post("/api/v1/admin/system/")
    assert r.status_code == 202
    assert sentinel.exists()


def test_system_update_requires_permission(staff_client, perms):
    from apps.adminpanel.tests.conftest import make_staff

    weak = make_staff("weak", ["monitoring.view"], perms)
    c = staff_client(weak)
    assert c.get("/api/v1/admin/system/").status_code == 200      # monitoring.view ok
    assert c.post("/api/v1/admin/system/").status_code == 403     # needs settings.manage
