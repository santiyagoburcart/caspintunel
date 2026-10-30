"""Login must always work with correct credentials, whatever the browser still holds
(v1.30.2, incident 2026-10-30: staff stuck on /panel/login until they cleared storage).

What the browser may still carry:
- an old / expired / foreign `Authorization: Bearer …` header (the SPA attached its stored
  token to the login request; the staff login ran the customer JWT check, which rejects
  every staff token → 401 "token_not_valid", the refresh then succeeded and the retry
  failed again — a loop until storage was cleared);
- Django-admin cookies (`sessionid` / `csrftoken` on Path=/) → session auth + CSRF on
  every API POST without a JWT;
- tokens of the other app on the same origin (customer site and /panel/ share it).
"""
from datetime import timedelta

import jwt
import pytest
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Staff, StaffRevokedToken, User
from apps.adminpanel.tokens import issue_tokens

pytestmark = pytest.mark.django_db
PW = "Str0ngPass!"


@pytest.fixture
def staff():
    s = Staff(username="boss", is_superadmin=True)
    s.set_password(PW)
    s.save()
    return s


@pytest.fixture
def customer():
    return User.objects.create_user("alice", PW)


def _expired_staff_access(staff):
    now = timezone.now() - timedelta(days=2)
    return jwt.encode({"staff_id": staff.id, "username": staff.username, "iat": now, "tv": staff.token_version,
                       "type": "staff_access", "exp": now + timedelta(minutes=30)}, settings.SECRET_KEY,
                      algorithm="HS256")


def _expired_customer_access(user):
    t = RefreshToken.for_user(user).access_token
    t.set_exp(lifetime=-timedelta(minutes=1))
    return str(t)


def _client(bearer=None, csrf=False):
    c = APIClient(enforce_csrf_checks=csrf)
    if bearer:
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {bearer}")
    return c


def _stale_headers(staff, customer):
    return {
        "valid staff token": issue_tokens(staff)["access"],
        "expired staff token": _expired_staff_access(staff),
        "valid customer token": str(RefreshToken.for_user(customer).access_token),
        "expired customer token": _expired_customer_access(customer),
        "garbage": "not.a.jwt",
    }


# --- 1. an old token never blocks a login ------------------------------------------
def test_staff_login_ignores_any_old_token(staff, customer):
    for label, bearer in _stale_headers(staff, customer).items():
        r = _client(bearer).post("/api/v1/admin/auth/login/", {"username": "boss", "password": PW}, format="json")
        assert r.status_code == 200, (label, r.status_code, r.data)
        assert r.data["access"] and r.data["staff"]["username"] == "boss"


def test_staff_login_still_refuses_a_wrong_password_with_its_own_code(staff, customer):
    r = _client(_expired_staff_access(staff)).post("/api/v1/admin/auth/login/",
                                                   {"username": "boss", "password": "nope"}, format="json")
    assert r.status_code == 401 and r.data["code"] == "invalid_credentials"


def test_staff_refresh_ignores_an_old_access_header(staff):
    refresh = issue_tokens(staff)["refresh"]
    r = _client(_expired_staff_access(staff)).post("/api/v1/admin/auth/refresh/", {"refresh": refresh}, format="json")
    assert r.status_code == 200 and r.data["access"]


def test_customer_auth_endpoints_ignore_any_old_token(staff, customer):
    for label, bearer in _stale_headers(staff, customer).items():
        c = _client(bearer)
        r = c.post("/api/v1/auth/login/", {"username": "alice", "password": PW}, format="json")
        assert r.status_code == 200, (label, "login", r.data)
        r = c.post("/api/v1/auth/token/refresh/", {"refresh": r.data["refresh"]}, format="json")
        assert r.status_code == 200, (label, "refresh", r.data)
        r = c.post("/api/v1/auth/password/reset/", {"identifier": "alice"}, format="json")
        assert r.status_code != 401, (label, "reset", r.data)
    r = _client("not.a.jwt").post("/api/v1/auth/register/", {
        "username": "newbie", "password": PW, "phone": "09120000009", "terms_accepted": True}, format="json")
    assert r.status_code == 201, r.data


def test_logout_works_with_an_expired_access_token(staff, customer):
    refresh = RefreshToken.for_user(customer)
    r = _client(_expired_customer_access(customer)).post("/api/v1/auth/logout/", {"refresh": str(refresh)},
                                                         format="json")
    assert r.status_code == 205, r.data
    r = _client().post("/api/v1/auth/token/refresh/", {"refresh": str(refresh)}, format="json")
    assert r.status_code == 401                       # the logged-out refresh token is dead


def test_staff_logout_revokes_the_refresh_token(staff):
    pair = issue_tokens(staff)
    r = _client(_expired_staff_access(staff)).post("/api/v1/admin/auth/logout/", {"refresh": pair["refresh"]},
                                                   format="json")
    assert r.status_code == 200, r.data
    assert StaffRevokedToken.objects.count() == 1
    r = _client().post("/api/v1/admin/auth/refresh/", {"refresh": pair["refresh"]}, format="json")
    assert r.status_code == 401
    # an unknown / garbage token still logs out cleanly (nothing to revoke)
    assert _client().post("/api/v1/admin/auth/logout/", {"refresh": "x"}, format="json").status_code == 200


# --- 2. Django-admin cookies / CSRF never reach the API -----------------------------
def _django_admin_session(customer):
    customer.is_staff = customer.is_superuser = True
    customer.save()
    s = SessionStore()
    s["_auth_user_id"] = str(customer.pk)
    s["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
    s["_auth_user_hash"] = customer.get_session_auth_hash()
    s.create()
    return s.session_key


def test_old_session_and_csrf_cookies_do_not_block_logins(staff, customer):
    key = _django_admin_session(customer)
    c = _client(csrf=True)
    # cookies of an older version (Path=/) and of the current Django admin, with a stale CSRF token
    for name in ("sessionid", settings.SESSION_COOKIE_NAME):
        c.cookies[name] = key
    for name in ("csrftoken", settings.CSRF_COOKIE_NAME):
        c.cookies[name] = "stale-csrf-token-from-an-old-deploy-xxxxxxxxx"
    r = c.post("/api/v1/admin/auth/login/", {"username": "boss", "password": PW}, format="json")
    assert r.status_code == 200, r.data
    r = c.post("/api/v1/auth/login/", {"username": "alice", "password": PW}, format="json")
    assert r.status_code == 200, r.data
    r = c.post("/api/v1/auth/register/", {"username": "bob_1", "password": PW, "phone": "09120000008",
                                          "terms_accepted": True}, format="json")
    assert r.status_code == 201, r.data
    # an API write with only the session cookie is plain "not logged in", never a CSRF 403
    r = c.post("/api/v1/orders/", {"plan": 1}, format="json")
    assert r.status_code == 401, (r.status_code, r.data)


def test_login_responses_expire_the_old_root_cookies_and_are_not_cached(staff, customer):
    for url, body in (("/api/v1/admin/auth/login/", {"username": "boss", "password": PW}),
                      ("/api/v1/auth/login/", {"username": "alice", "password": PW})):
        c = _client()
        c.cookies["sessionid"] = "old"
        c.cookies["csrftoken"] = "old"
        r = c.post(url, body, format="json")
        assert r.status_code == 200
        for name in ("sessionid", "csrftoken"):
            morsel = r.cookies[name]
            assert morsel["max-age"] == 0 and morsel["path"] == "/", (url, name, morsel)
        assert "no-store" in r["Cache-Control"]


def test_django_admin_cookies_are_scoped_to_admin_with_their_own_names():
    assert settings.SESSION_COOKIE_PATH == settings.CSRF_COOKIE_PATH == "/admin/"
    assert settings.SESSION_COOKIE_NAME not in ("sessionid", "csrftoken")
    assert settings.CSRF_COOKIE_NAME not in ("sessionid", "csrftoken")
    assert settings.SESSION_COOKIE_DOMAIN is None and settings.CSRF_COOKIE_DOMAIN is None   # host-only
    assert settings.SESSION_COOKIE_HTTPONLY is True
    assert "rest_framework.authentication.SessionAuthentication" not in \
        settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]


# --- 3. customer + staff in the same browser ----------------------------------------
def test_customer_and_staff_sessions_do_not_interfere(staff, customer):
    staff_pair = _client().post("/api/v1/admin/auth/login/", {"username": "boss", "password": PW},
                                format="json").data
    cust_pair = _client().post("/api/v1/auth/login/", {"username": "alice", "password": PW}, format="json").data
    # each token works only on its own API
    assert _client(staff_pair["access"]).get("/api/v1/admin/auth/me/").data["username"] == "boss"
    assert _client(cust_pair["access"]).get("/api/v1/auth/me/").data["username"] == "alice"
    assert _client(staff_pair["access"]).get("/api/v1/auth/me/").status_code == 401
    assert _client(cust_pair["access"]).get("/api/v1/admin/auth/me/").status_code == 401
    # logging in to one app (with the other's token still attached) leaves the other session valid
    _client(cust_pair["access"]).post("/api/v1/admin/auth/login/", {"username": "boss", "password": PW},
                                      format="json")
    _client(staff_pair["access"]).post("/api/v1/auth/login/", {"username": "alice", "password": PW},
                                       format="json")
    assert _client(cust_pair["access"]).get("/api/v1/auth/me/").status_code == 200
    assert _client(staff_pair["access"]).get("/api/v1/admin/auth/me/").status_code == 200
    # each refresh token only refreshes its own kind
    assert _client().post("/api/v1/admin/auth/refresh/", {"refresh": cust_pair["refresh"]},
                          format="json").status_code == 401
    assert _client().post("/api/v1/auth/token/refresh/", {"refresh": staff_pair["refresh"]},
                          format="json").status_code == 401
