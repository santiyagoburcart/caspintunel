"""v1.25.5: a group manager's Settings tab (profile + own password) and Persian notes."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Staff
from apps.adminpanel.tokens import issue_tokens
from apps.agency import ledger, managers
from apps.agency.models import AdminGroup, GroupManager, LedgerEntry
from apps.agency.notes import to_fa

pytestmark = pytest.mark.django_db
GB = 1024 ** 3


@pytest.fixture(autouse=True)
def catalog(monkeypatch):
    monkeypatch.setattr(managers, "roles_catalog", lambda fresh=False: {
        6: {"id": 6, "name": "operator pouya", "is_owner": False, "inbounds": ["Mix"], "all_inbounds": False}})


@pytest.fixture
def gm():
    g = AdminGroup.objects.create(owner_username="VEX2", member_usernames="Iman", name="Vox")
    m = managers.save_manager(None, {"username": "imantorabian", "password": "Old-pass-123",
                                     "assignments": [{"group_id": g.id, "role_ids": [6]}]}, by="boss")
    m.refresh_from_db()
    return m


def _client(staff):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(staff)['access']}")
    return c


def test_me_has_role_and_cap_for_the_settings_tab(gm):
    d = _client(gm.staff).get("/api/v1/agency/manager/me/").json()
    assert d["manager"]["role"] == "Group manager" and d["manager"]["role_fa"] == "مدیر گروه"
    assert [g["name"] for g in d["groups"]] == ["Vox"]


def test_manager_changes_own_password(gm):
    staff = gm.staff
    c = _client(staff)
    url = "/api/v1/agency/manager/password/"
    r = c.post(url, {"current_password": "wrong-one-1", "new_password": "New-pass-456"}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "wrong_password"
    r = c.post(url, {"current_password": "Old-pass-123", "new_password": "short"}, format="json")
    assert r.status_code == 400 and r.json()["field"] == "new_password"
    r = c.post(url, {"current_password": "Old-pass-123", "new_password": "New-pass-456"}, format="json")
    assert r.status_code == 200 and r.json()["access"] and r.json()["refresh"]
    staff.refresh_from_db(); gm.refresh_from_db()
    assert staff.check_password("New-pass-456") and gm.password == staff.password_hash
    assert c.get("/api/v1/agency/manager/me/").status_code == 401           # old token ended
    fresh = APIClient()
    fresh.credentials(HTTP_AUTHORIZATION=f"Bearer {r.json()['access']}")
    assert fresh.get("/api/v1/agency/manager/me/").status_code == 200       # this session continues
    login = APIClient().post("/api/v1/admin/auth/login/", {"username": "imantorabian", "password": "New-pass-456"},
                             format="json")
    assert login.status_code == 200


def test_password_endpoint_is_for_managers_only(gm):
    s = Staff(username="boss", is_superadmin=True)
    s.set_password("Str0ngPass!")
    s.save()
    r = _client(s).post("/api/v1/agency/manager/password/", {"current_password": "Str0ngPass!",
                                                             "new_password": "Another-1234"}, format="json")
    assert r.status_code == 403


@pytest.mark.parametrize("en,fa", [
    ("no price per GB set for this date — add an adjustment", "برای این تاریخ قیمت هر گیگ ثبت نشده بود — با اصلاحیه درست کنید"),
    ("approved request #12 — group manager imantorabian", "درخواست #12 تأیید شد — مدیر گروه imantorabian"),
    ("group manager imantorabian: +100 GB — pending approval #3", "مدیر گروه imantorabian: ‎+100 گیگ — در انتظار تأیید #3"),
    ("approved request #5 — group manager x · no price per GB set for this date — add an adjustment",
     "درخواست #5 تأیید شد — مدیر گروه x · برای این تاریخ قیمت هر گیگ ثبت نشده بود — با اصلاحیه درست کنید"),
    ("add 100 GB", "افزودن 100 گیگ"),
    ("امروز پرداخت کرد", "امروز پرداخت کرد"),             # typed by a person: unchanged
    ("", ""),
])
def test_notes_in_persian(en, fa):
    assert to_fa(en) == fa


def test_statements_carry_note_fa_and_persian_exports(gm):
    ledger.record_quota_charge("Iman", 0, 100 * GB, by="boss")
    e = LedgerEntry.objects.get()
    assert ledger.statement("Iman")["entries"][0]["note_fa"].startswith("برای این تاریخ")
    st = managers.group_statement(AdminGroup.objects.get())
    assert st["entries"][0]["note_fa"] == to_fa(e.note)
    rows = managers.group_statement_rows(st, "fa")
    assert any("برای این تاریخ" in str(c) for row in rows for c in row)
    assert any("no price per GB" in str(c) for row in managers.group_statement_rows(st, "en") for c in row)
    c = _client(gm.staff)
    r = c.get(f"/api/v1/agency/manager/groups/{AdminGroup.objects.get().id}/statement/")
    assert r.json()["entries"][0]["note_fa"].startswith("برای این تاریخ")
