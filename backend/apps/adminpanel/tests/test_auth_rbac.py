import pytest

from apps.accounts.models import User
from apps.adminpanel.tests.conftest import make_staff

pytestmark = pytest.mark.django_db


def test_staff_login_returns_tokens_and_profile(api, superadmin):
    r = api.post("/api/v1/admin/auth/login/", {"username": "boss", "password": "Str0ngPass!"}, format="json")
    assert r.status_code == 200
    assert r.data["access"] and r.data["refresh"]
    assert r.data["staff"]["is_superadmin"] is True
    assert r.data["staff"]["permissions"] == ["*"]


def test_staff_login_bad_password(api, superadmin):
    r = api.post("/api/v1/admin/auth/login/", {"username": "boss", "password": "nope"}, format="json")
    assert r.status_code == 401


def test_me_and_refresh(api, superadmin):
    login = api.post("/api/v1/admin/auth/login/", {"username": "boss", "password": "Str0ngPass!"}, format="json")
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    assert api.get("/api/v1/admin/auth/me/").data["username"] == "boss"

    api.credentials()
    r = api.post("/api/v1/admin/auth/refresh/", {"refresh": login.data["refresh"]}, format="json")
    assert r.status_code == 200 and r.data["access"]


def test_staff_refresh_token_is_single_use(api, superadmin):
    login = api.post("/api/v1/admin/auth/login/",
                     {"username": "boss", "password": "Str0ngPass!"}, format="json")
    rt = login.data["refresh"]

    first = api.post("/api/v1/admin/auth/refresh/", {"refresh": rt}, format="json")
    assert first.status_code == 200
    new_rt = first.data["refresh"]
    assert new_rt and new_rt != rt

    # the consumed token is now revoked
    replay = api.post("/api/v1/admin/auth/refresh/", {"refresh": rt}, format="json")
    assert replay.status_code == 401
    # but the freshly issued one still works
    assert api.post("/api/v1/admin/auth/refresh/",
                    {"refresh": new_rt}, format="json").status_code == 200


def test_permission_enforced_per_endpoint(staff_client, perms):
    viewer = make_staff("viewer", ["users.view"], perms)
    c = staff_client(viewer)
    assert c.get("/api/v1/admin/users/").status_code == 200
    # creating a user needs users.manage
    r = c.post("/api/v1/admin/users/", {"username": "newbie", "password": "Str0ngPass!"}, format="json")
    assert r.status_code == 403


def test_superadmin_bypasses_all(staff_client, superadmin):
    c = staff_client(superadmin)
    assert c.get("/api/v1/admin/roles/").status_code == 200
    assert c.get("/api/v1/admin/accounting/").status_code == 200


def test_django_superuser_break_glass(api):
    su = User.objects.create_superuser("root", "Str0ngPass!")
    api.force_authenticate(su)
    assert api.get("/api/v1/admin/dashboard/").status_code == 200


def test_anonymous_denied(api):
    assert api.get("/api/v1/admin/users/").status_code in (401, 403)
