import pytest

from apps.accounts.models import Permission, Role, Staff, User

pytestmark = pytest.mark.django_db


def test_user_gets_unique_referral_code():
    u1 = User.objects.create_user("alice", "pw12345!")
    u2 = User.objects.create_user("bob", "pw12345!")
    assert len(u1.referral_code) == 6
    assert u1.referral_code != u2.referral_code


def test_referral_relationship_and_count():
    ref = User.objects.create_user("ref", "pw12345!")
    User.objects.create_user("c1", "pw12345!", referred_by=ref)
    User.objects.create_user("c2", "pw12345!", referred_by=ref)
    assert ref.referral_count == 2


def test_superuser_flags():
    su = User.objects.create_superuser("root", "pw12345!")
    assert su.is_staff and su.is_superuser


def test_staff_password_hash_and_perms():
    role = Role.objects.create(name="R")
    p = Permission.objects.create(code="payment.approve", name="x")
    role.permissions.add(p)
    s = Staff(username="op", role=role)
    s.set_password("secret")
    s.save()
    assert s.password_hash != "secret"
    assert s.check_password("secret")
    assert s.has_perm("payment.approve")
    assert not s.has_perm("roles.manage")


def test_staff_superadmin_bypasses():
    s = Staff(username="boss", is_superadmin=True)
    s.set_password("x")
    s.save()
    assert s.has_perm("anything.at.all")
