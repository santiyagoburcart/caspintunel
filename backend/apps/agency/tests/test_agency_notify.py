"""v1.33 agency events on Telegram: approval requests with Approve / Reject buttons (permission-
checked like the panel), cap reached, admin enabled / disabled by a manager; and the clearer
adjustment (increase / decrease debt, positive amount)."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.accounts.models import Permission, Role, Staff
from apps.agency import notify
from apps.agency.models import LedgerEntry, VolumeRequest
from apps.agency.tests.test_group_managers import M, make_manager, manager_client, pg, staff_client  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(notify, "alert_staff", lambda text, **kw: out.append((text, kw)) or 1)
    return out


class FakeBot:
    def __init__(self):
        self.msgs, self.edits = [], []

    def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.msgs.append((text, reply_markup))

    def edit_message_text(self, text, chat_id, message_id, **kw):
        self.edits.append(text)


def tg_staff(perms, tg=700, name="op"):
    role = Role.objects.create(name=f"tg-{name}")
    role.permissions.set([Permission.objects.get_or_create(code=c, defaults={"name": c})[0] for c in perms])
    s = Staff(username=name, role=role, telegram_id=tg)
    s.set_password("x-Str0ng!")
    s.save()
    return s


def press(data, tg=700):
    bot = FakeBot()
    msg = SimpleNamespace(text="🟡 request", message_id=5)
    return notify.handle_callback(bot, 1, msg, tg, data), bot


def test_add_volume_sends_an_approval_with_buttons(pg, sent, django_capture_on_commit_callbacks):  # noqa: F811
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    with django_capture_on_commit_callbacks(execute=True):
        assert manager_client().post(M + "admins/g1-a/add-volume/", {"gb": 20}, format="json").status_code == 200
    rid = VolumeRequest.objects.get().id
    text, kw = sent[0]
    assert f"#{rid}" in text and "g1-a" in text and "+20 GB" in text and kw["perm"] == "agency.manage"
    assert [b["callback_data"] for b in kw["buttons"][0]] == [f"ag:a:{rid}", f"ag:r:{rid}"]
    assert kw["push"]["url"] == "/agency/approvals"


def test_telegram_approve_and_reject_use_the_panel_rules(pg, sent, django_capture_on_commit_callbacks):  # noqa: F811
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    mc = manager_client()
    for n in ("g1-a", "g1-owner"):
        with django_capture_on_commit_callbacks(execute=True):
            mc.post(M + f"admins/{n}/add-volume/", {"gb": 10}, format="json")
    r1, r2 = VolumeRequest.objects.order_by("id")
    assert press(f"ag:a:{r1.id}", tg=999)[0] == "no_staff"
    tg_staff(["agency.view"], tg=701, name="viewer")
    assert press(f"ag:a:{r1.id}", tg=701)[0] == "forbidden"
    tg_staff(["agency.manage"], tg=702, name="mgr")
    res, bot = press(f"ag:a:{r1.id}", tg=702)
    assert res == "forbidden" and "agency.accounting" in bot.msgs[0][0]        # approving records a charge
    tg_staff(["agency.manage", "agency.accounting"], tg=703, name="acc")
    res, bot = press(f"ag:a:{r1.id}", tg=703)
    assert res == "approved" and "acc" in bot.edits[0]
    r1.refresh_from_db()
    assert r1.status == "approved" and LedgerEntry.objects.filter(kind="quota_charge").count() == 1
    assert press(f"ag:a:{r1.id}", tg=703)[0] == "not_pending"                 # once only
    # reject: a confirm step first, then the same reject as the panel (volume back, no charge)
    res, bot = press(f"ag:r:{r2.id}", tg=702)
    assert res == "confirm" and VolumeRequest.objects.get(pk=r2.id).status == "pending"
    res, bot = press(f"ag:rc:{r2.id}", tg=702)
    assert res == "rejected" and VolumeRequest.objects.get(pk=r2.id).status == "rejected"
    assert pg["fake"].admins["g1-owner"]["data_limit"] == 500 * 1024 ** 3


def test_cap_reached_alerts_staff(pg, sent, django_capture_on_commit_callbacks):  # noqa: F811
    boss = staff_client(superadmin=True)
    make_manager(boss, pg, cap="100")
    mc = manager_client()
    with django_capture_on_commit_callbacks(execute=True):
        mc.post(M + "admins/g1-a/add-volume/", {"gb": 100}, format="json")      # exactly at the cap
    assert any("سقف" in t and "mona" in t for t, _ in sent)
    sent.clear()
    assert mc.post(M + "admins/g1-a/add-volume/", {"gb": 5}, format="json").status_code == 409
    assert any("سقف" in t for t, _ in sent)


def test_manager_disabling_an_admin_is_announced(pg, sent, django_capture_on_commit_callbacks):  # noqa: F811
    boss = staff_client(superadmin=True)
    make_manager(boss, pg)
    with django_capture_on_commit_callbacks(execute=True):
        r = manager_client().post(M + "admins/g1-a/disable/", {}, format="json")
    assert r.status_code == 200, r.json()
    text, kw = sent[-1]
    assert "g1-a" in text and "غیرفعال" in text and kw.get("silent") is False


def test_adjustment_direction_buttons(pg):  # noqa: F811
    boss = staff_client(superadmin=True)
    url = "/api/v1/admin/agency/ledger/g1-a/entries/"
    r = boss.post(url, {"kind": "adjustment", "direction": "decrease", "amount": "250000"}, format="json")
    assert r.status_code == 201, r.json()
    e = LedgerEntry.objects.get(kind="adjustment")
    assert e.amount == Decimal("-250000") and e.signed_amount == Decimal("-250000")
    assert boss.post(url, {"kind": "adjustment", "direction": "increase", "amount": "-5"}, format="json").status_code == 400
    assert boss.post(url, {"kind": "adjustment", "direction": "sideways", "amount": "5"}, format="json").status_code == 400
    assert boss.post(url, {"kind": "adjustment", "direction": "increase", "amount": "1000"}, format="json").status_code == 201
    assert LedgerEntry.objects.get(kind="adjustment", amount__gt=0).signed_amount == Decimal("1000")
    # old signed API still works (existing clients)
    assert boss.post(url, {"kind": "adjustment", "amount": "-10"}, format="json").status_code == 201
