"""Portal link + QR in the admin panel follow the configured portal path."""
import io

import pytest
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import Staff
from apps.adminpanel.tokens import issue_tokens
from apps.settings_app.models import SiteConfig

pytestmark = pytest.mark.django_db


@pytest.fixture
def c():
    s = Staff(username="boss", is_superadmin=True); s.set_password("x-Str0ng!"); s.save()
    cl = APIClient(); cl.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return cl


def test_portal_link_follows_the_configured_path(c, tmp_path, settings):
    settings.UPDATE_SENTINEL_PATH = str(tmp_path / ".update-requested")
    cfg = SiteConfig.load(); cfg.site_domain = "aicaspin.ir"; cfg.save()
    assert c.get("/api/v1/admin/agency/portal-link/").json() == {"path": "/agency", "url": "https://aicaspin.ir/agency/"}
    (tmp_path / ".paths-status.json").write_text('{"ok": true, "admin": "/panel", "portal": "/resellers"}')
    assert c.get("/api/v1/admin/agency/portal-link/").json()["url"] == "https://aicaspin.ir/resellers/"
    r = c.get("/api/v1/admin/agency/portal-link/qr.png")
    assert r.status_code == 200 and r["Content-Type"] == "image/png" and Image.open(io.BytesIO(r.content)).size[0] > 100


def test_admin_list_has_user_breakdown(c):
    from apps.agency.models import PanelAdmin
    PanelAdmin.objects.create(username="ali", user_count=13, active_user_count=12, on_hold_users=1, limited_users=2,
                              disabled_users=3, expired_users=4)
    row = c.get("/api/v1/admin/agency/admins/").json()["results"][0]
    assert (row["user_count"], row["active_user_count"]) == (13, 12)
    assert row["user_counts"] == {"active": 12, "on_hold": 1, "limited": 2, "disabled": 3, "expired": 4}
