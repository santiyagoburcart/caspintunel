import pytest
import responses
from django.utils import timezone

from apps.panel.client import PasarGuardClient
from apps.panel.exceptions import PanelAuthError, PanelNotFound, PanelUnavailable
from apps.panel.models import Panel

pytestmark = pytest.mark.django_db

BASE = "https://panel.test"


@pytest.fixture
def panel():
    return Panel.objects.create(
        name="T", base_url=BASE, admin_username="adm", admin_password_enc="pw",
        default_group_ids=[1],
    )


def _token_ok(rsps):
    rsps.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "tok-123"}, status=200)


@responses.activate
def test_authenticate_caches_token(panel):
    _token_ok(responses)
    responses.add(responses.GET, f"{BASE}/api/system", json={"version": "5.3.0"}, status=200)

    client = PasarGuardClient(panel)
    assert client.check() is True

    panel.refresh_from_db()
    assert panel.token_cache == "tok-123"
    assert panel.token_expires_at > timezone.now()

    responses.add(responses.GET, f"{BASE}/api/system", json={}, status=200)
    client.check()
    token_calls = [c for c in responses.calls if c.request.url.endswith("/api/admin/token")]
    assert len(token_calls) == 1


@responses.activate
def test_bad_credentials_raise_auth_error(panel):
    responses.add(responses.POST, f"{BASE}/api/admin/token", status=401)
    with pytest.raises(PanelAuthError):
        PasarGuardClient(panel).check()


@responses.activate
def test_5xx_is_treated_as_unavailable(panel):
    _token_ok(responses)
    responses.add(responses.GET, f"{BASE}/api/user/bob", status=503)
    with pytest.raises(PanelUnavailable):
        PasarGuardClient(panel).get_user("bob")


@responses.activate
def test_404_is_not_found(panel):
    _token_ok(responses)
    responses.add(responses.GET, f"{BASE}/api/user/ghost", status=404)
    with pytest.raises(PanelNotFound):
        PasarGuardClient(panel).get_user("ghost")


@responses.activate
def test_401_triggers_single_reauth_then_succeeds(panel):
    panel.token_cache = "stale"
    panel.token_expires_at = timezone.now() + timezone.timedelta(hours=1)
    panel.save()

    responses.add(responses.GET, f"{BASE}/api/user/bob", status=401)
    responses.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "fresh"}, status=200)
    responses.add(responses.GET, f"{BASE}/api/user/bob", json={"username": "bob"}, status=200)

    out = PasarGuardClient(panel).get_user("bob")
    assert out["username"] == "bob"
    panel.refresh_from_db()
    assert panel.token_cache == "fresh"
