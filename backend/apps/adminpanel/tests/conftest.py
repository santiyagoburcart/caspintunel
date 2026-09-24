import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff, User


@pytest.fixture
def perms(db):
    codes = [
        "users.view", "users.manage", "plans.manage", "payment.view", "payment.approve",
        "accounting.view", "broadcast.send", "settings.manage", "roles.manage",
        "pages.manage", "themes.manage", "monitoring.view", "audit.view", "sms.manage",
        "bots.manage", "services.manage",
    ]
    # get_or_create: "services.manage" (and any future perm seeded by a data
    # migration) may already exist in the test DB by the time this fixture runs
    return {c: Permission.objects.get_or_create(code=c, defaults={"name": c})[0] for c in codes}


@pytest.fixture
def superadmin(db):
    s = Staff(username="boss", is_superadmin=True)
    s.set_password("Str0ngPass!")
    s.save()
    return s


def make_staff(username, perm_codes, perms):
    role = Role.objects.create(name=f"role-{username}")
    role.permissions.set([perms[c] for c in perm_codes])
    s = Staff(username=username, role=role)
    s.set_password("Str0ngPass!")
    s.save()
    return s


@pytest.fixture
def staff_client(db):
    def _make(staff):
        from apps.adminpanel.tokens import issue_tokens

        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(staff)['access']}")
        return c

    return _make


@pytest.fixture
def api():
    return APIClient()
