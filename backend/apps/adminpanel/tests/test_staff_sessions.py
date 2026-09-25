"""Staff session revocation: token_version ("tv" claim) + durable (DB) refresh
blacklist. Customers' SimpleJWT tokens are never affected."""
import jwt
import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import StaffRevokedToken, User
from apps.adminpanel.tokens import issue_tokens

pytestmark = pytest.mark.django_db

ME = "/api/v1/admin/auth/me/"
REFRESH = "/api/v1/admin/auth/refresh/"


def _as(token):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return c


def test_token_without_version_claim_is_rejected(superadmin):
    """Tokens issued before versioning (no "tv") are dead."""
    legacy = jwt.decode(issue_tokens(superadmin)["access"], options={"verify_signature": False})
    legacy.pop("tv")
    old = jwt.encode(legacy, settings.SECRET_KEY, algorithm="HS256")
    r = _as(old).get(ME)
    assert r.status_code == 401 and r.data["code"] == "token_revoked"


def test_revoke_command_kills_staff_tokens_but_not_customers(superadmin, api):
    old = issue_tokens(superadmin)
    customer = User.objects.create_user("cust", "Str0ngPass!1")
    cust_access = str(RefreshToken.for_user(customer).access_token)
    assert _as(old["access"]).get(ME).status_code == 200

    call_command("revoke_staff_sessions")

    assert _as(old["access"]).get(ME).status_code == 401
    assert api.post(REFRESH, {"refresh": old["refresh"]}, format="json").status_code == 401
    # a fresh login works
    r = api.post("/api/v1/admin/auth/login/", {"username": "boss", "password": "Str0ngPass!"}, format="json")
    assert r.status_code == 200 and _as(r.data["access"]).get(ME).status_code == 200
    # customer session untouched
    assert _as(cust_access).get("/api/v1/auth/me/").status_code == 200


def test_password_change_ends_that_staffs_sessions(superadmin):
    old = issue_tokens(superadmin)
    superadmin.set_password("An0therPass!")
    superadmin.save()
    assert _as(old["access"]).get(ME).status_code == 401


def test_refresh_is_single_use_and_survives_a_cache_flush(superadmin, api):
    t = issue_tokens(superadmin)
    first = api.post(REFRESH, {"refresh": t["refresh"]}, format="json")
    assert first.status_code == 200
    assert StaffRevokedToken.objects.count() == 1

    cache.clear()  # used to re-enable spent tokens when the blacklist lived in Redis
    again = api.post(REFRESH, {"refresh": t["refresh"]}, format="json")
    assert again.status_code == 401
    # the rotated token still works
    assert api.post(REFRESH, {"refresh": first.data["refresh"]}, format="json").status_code == 200


def test_expired_blacklist_rows_are_pruned(superadmin, api):
    from datetime import timedelta

    from django.utils import timezone

    StaffRevokedToken.objects.create(jti="old", expires_at=timezone.now() - timedelta(days=1))
    api.post(REFRESH, {"refresh": issue_tokens(superadmin)["refresh"]}, format="json")
    assert not StaffRevokedToken.objects.filter(jti="old").exists()


@pytest.mark.django_db(transaction=True)
def test_revoked_staff_cannot_open_payments_socket(superadmin):
    from asgiref.sync import async_to_sync

    from apps.notifications.consumers import _staff_from_token

    token = issue_tokens(superadmin)["access"]
    assert async_to_sync(_staff_from_token)(token) is not None
    call_command("revoke_staff_sessions")
    assert async_to_sync(_staff_from_token)(token) is None
