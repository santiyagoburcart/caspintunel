"""Configurable admin / portal paths: validation (same rules as nginx/render-paths.sh),
superadmin-only request file for the host watcher, status read back."""
import json

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff
from apps.adminpanel.tokens import issue_tokens
from apps.settings_app import paths

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def tmp_dir(tmp_path, settings):
    settings.UPDATE_SENTINEL_PATH = str(tmp_path / ".update-requested")
    return tmp_path


def client(superadmin=True):
    s = Staff(username="boss" if superadmin else "ops", is_superadmin=superadmin)
    if not superadmin:
        role = Role.objects.create(name="ops")
        role.permissions.set([Permission.objects.get_or_create(code="settings.manage", defaults={"name": "s"})[0]])
        s.role = role
    s.set_password("x-Str0ng!"); s.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


@pytest.mark.parametrize("admin,portal,bad", [
    ("/ctrl-x9", "/resellers", None), ("/panel", "/agency", None),
    ("/api", "/agency", "admin"), ("/admin", "/agency", "admin"), ("/x", "/agency", "admin"),
    ("/My-Panel", "/agency", "admin"), ("/a b", "/agency", "admin"), ("/../etc", "/agency", "admin"),
    ("/p;q", "/agency", "admin"), ("/ctrl", "/ctrl", "portal"), ("/ctrl", "/panel", "portal"),
    ("/ctrl", "/login", "portal"), ("/ctrl", "/static", "portal"), ("/ctrl", "/" + "a" * 41, "portal"),
])
def test_validation(admin, portal, bad):
    errors = paths.validate(admin, portal)
    assert (bad is None and errors == {}) or bad in errors


def test_request_file_status_and_permissions(tmp_dir):
    c = client()
    assert c.get("/api/v1/admin/paths/").json()["admin"] == "/panel"
    r = c.post("/api/v1/admin/paths/", {"admin": "/Ctrl-X9/", "portal": "/resellers"}, format="json")
    assert r.status_code == 202 and r.json()["pending"]["admin"] == "/ctrl-x9"
    req = json.loads((tmp_dir / ".paths-request.json").read_text())
    assert req == {**req, "admin": "/ctrl-x9", "portal": "/resellers", "requested_by": "boss"}
    assert c.post("/api/v1/admin/paths/", {"admin": "/api"}, format="json").status_code == 400
    assert client(superadmin=False).post("/api/v1/admin/paths/", {"admin": "/zzz"}, format="json").status_code == 403
    # the host watcher reports back
    (tmp_dir / ".paths-request.json").unlink()
    (tmp_dir / ".paths-status.json").write_text(json.dumps({"ok": True, "admin": "/ctrl-x9", "portal": "/resellers",
                                                            "message": "applied", "at": "2026-10-16T00:00:00Z"}))
    st = c.get("/api/v1/admin/paths/").json()
    assert st["admin"] == "/ctrl-x9" and st["portal"] == "/resellers" and st["pending"] is None and st["last"]["ok"]
    assert c.post("/api/v1/admin/paths/", {"admin": "/ctrl-x9", "portal": "/resellers"}, format="json").json()["detail"] == "nothing to change"
