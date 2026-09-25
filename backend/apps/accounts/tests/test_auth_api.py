import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import set_password_by_admin
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def _register(client, **over):
    payload = {"username": "alice", "password": "Str0ngPass!", "email": "alice@example.com",
               "name": "Alice", "phone": "09120000000"}
    payload.update(over)
    return client.post("/api/v1/auth/register/", payload, format="json")


# --- registration --------------------------------------------------------
def test_register_success_returns_tokens(client):
    r = _register(client)
    assert r.status_code == 201, r.data
    assert r.data["access"] and r.data["refresh"]
    assert r.data["email_status"] == "skipped"          # feature off by default
    assert len(r.data["user"]["referral_code"]) == 6


def test_register_with_referral_links_referrer(client):
    _register(client)
    ref = User.objects.get(username="alice").referral_code
    r = _register(client, username="bob", email="bob@example.com", phone="09120000001",
                  referral_code=ref.lower())
    assert r.status_code == 201
    assert User.objects.get(username="bob").referred_by.username == "alice"
    assert User.objects.get(username="alice").referral_count == 1


def test_register_rejects_bad_referral(client):
    r = _register(client, referral_code="ZZZZZZ")
    assert r.status_code == 400
    assert "referral_code" in r.data


def test_register_duplicate_username(client):
    _register(client)
    r = _register(client, email="other@example.com")
    assert r.status_code == 400


# --- email verification (flowchart 1.1) --------------------------------
def test_verification_graceful_when_smtp_down(client):
    set_setting("email_verification_required", "true", "bool")
    r = _register(client)
    assert r.status_code == 201
    assert r.data["email_status"] == "not_sent"          # no EMAIL_HOST in tests
    user = User.objects.get(username="alice")
    assert user.is_active and not user.email_verified     # account still usable

    # and the user can still log in
    login = client.post("/api/v1/auth/login/", {"username": "alice", "password": "Str0ngPass!"}, format="json")
    assert login.status_code == 200


def test_email_verify_confirm_flow(client):
    from apps.accounts import tokens
    _register(client)
    user = User.objects.get(username="alice")
    token = tokens.make_email_verify_token(user)
    r = client.post("/api/v1/auth/email/verify/confirm/", {"token": token}, format="json")
    assert r.status_code == 200
    user.refresh_from_db()
    assert user.email_verified


def test_email_verify_confirm_rejects_garbage(client):
    r = client.post("/api/v1/auth/email/verify/confirm/", {"token": "nope"}, format="json")
    assert r.status_code == 400


# --- login / logout ----------------------------------------------------
def test_login_returns_profile_and_logout_blacklists(client):
    _register(client)
    login = client.post("/api/v1/auth/login/", {"username": "alice", "password": "Str0ngPass!"}, format="json")
    assert login.status_code == 200
    assert login.data["user"]["username"] == "alice"
    access, refresh = login.data["access"], login.data["refresh"]

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    out = client.post("/api/v1/auth/logout/", {"refresh": refresh}, format="json")
    assert out.status_code == 205

    # blacklisted refresh can no longer be used
    again = client.post("/api/v1/auth/token/refresh/", {"refresh": refresh}, format="json")
    assert again.status_code == 401


def test_login_disabled_account(client):
    _register(client)
    User.objects.filter(username="alice").update(is_active=False)
    r = client.post("/api/v1/auth/login/", {"username": "alice", "password": "Str0ngPass!"}, format="json")
    assert r.status_code in (400, 401)


# --- change password ---------------------------------------------------
def test_change_password(client):
    _register(client)
    login = client.post("/api/v1/auth/login/", {"username": "alice", "password": "Str0ngPass!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    r = client.post("/api/v1/auth/password/change/",
                    {"current_password": "Str0ngPass!", "new_password": "EvenStr0nger!"}, format="json")
    assert r.status_code == 200
    assert client.post("/api/v1/auth/login/",
                       {"username": "alice", "password": "EvenStr0nger!"}, format="json").status_code == 200


def test_change_password_wrong_current(client):
    _register(client)
    login = client.post("/api/v1/auth/login/", {"username": "alice", "password": "Str0ngPass!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    r = client.post("/api/v1/auth/password/change/",
                    {"current_password": "wrong", "new_password": "EvenStr0nger!"}, format="json")
    assert r.status_code == 400


# --- password reset (flowchart 1.6) ----------------------------------
def test_reset_request_points_to_alternatives_when_no_email(client):
    _register(client)
    r = client.post("/api/v1/auth/password/reset/", {"identifier": "alice"}, format="json")
    assert r.status_code == 200
    assert r.data["email_sent"] is False
    assert "telegram_bot" in r.data["alternative_paths"]


def test_reset_request_unknown_user_is_generic(client):
    r = client.post("/api/v1/auth/password/reset/", {"identifier": "ghost"}, format="json")
    assert r.status_code == 200
    assert r.data["email_sent"] is False


def test_reset_confirm_with_valid_token(client, settings):
    settings.EMAIL_HOST = "mail.test"          # make smtp "configured"
    _register(client)
    user = User.objects.get(username="alice")
    from apps.accounts import tokens
    token = tokens.make_password_reset_token(user)
    r = client.post("/api/v1/auth/password/reset/confirm/",
                    {"token": token, "new_password": "BrandNewP4ss!"}, format="json")
    assert r.status_code == 200
    assert client.post("/api/v1/auth/login/",
                       {"username": "alice", "password": "BrandNewP4ss!"}, format="json").status_code == 200


# --- legacy import ---------------------------------------------------
def test_legacy_import_endpoint_and_login(client):
    admin = User.objects.create_superuser("root", "Str0ngPass!")
    client.force_authenticate(admin)
    payload = {"users": [
        {"username": "old1", "name": "Old One", "password": "LegacyP4ss!"},
        {"username": "old2", "name": "No Password"},
    ]}
    r = client.post("/api/v1/auth/legacy/import/", payload, format="json")
    assert r.status_code == 201
    assert r.data["created"] == 2

    o1, o2 = User.objects.get(username="old1"), User.objects.get(username="old2")
    assert o1.is_legacy and o2.is_legacy
    assert o1.has_usable_password() and not o2.has_usable_password()

    client.credentials()
    assert client.post("/api/v1/auth/login/",
                       {"username": "old1", "password": "LegacyP4ss!"}, format="json").status_code == 200

    # passwordless legacy user logs in after admin sets a password
    set_password_by_admin(o2, "AdminSetP4ss!")
    assert client.post("/api/v1/auth/login/",
                       {"username": "old2", "password": "AdminSetP4ss!"}, format="json").status_code == 200


def test_legacy_import_requires_admin(client):
    _register(client)
    login = client.post("/api/v1/auth/login/", {"username": "alice", "password": "Str0ngPass!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    r = client.post("/api/v1/auth/legacy/import/", {"users": []}, format="json")
    assert r.status_code == 403
