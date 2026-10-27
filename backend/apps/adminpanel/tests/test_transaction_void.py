"""v1.25 Transactions: TX numbers (sequential, unique, backfilled, searchable, CSV) and the
Super Admin "Delete transaction" = void (apps/payments_sms/voiding.py): hidden from the
list and from every total (Transactions cards, Accounting, Analytics, card report), restore
for 30 days, audit, order / service choice, 403 for everyone else."""
import csv
import importlib
import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff, User
from apps.adminpanel.tokens import issue_tokens
from apps.common.models import AuditLog
from apps.crm import analytics as A
from apps.orders.models import Order, OrderStatus, ScheduledRenewal
from apps.panel.models import Panel, Service, ServiceStatus
from apps.payments_sms.models import BankCard, Payment, PaymentMethod, PaymentStatus
from apps.payments_sms.services import PaymentError, approve_payment
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db
T = "/api/v1/admin/transactions/"


def staff(name, perms=(), superadmin=False):
    role = None
    if perms:
        role = Role.objects.create(name=f"r-{name}")
        role.permissions.set([Permission.objects.get_or_create(code=c, defaults={"name": c})[0] for c in perms])
    s = Staff(username=name, role=role, is_superadmin=superadmin)
    s.set_password("x-Str0ng!")
    s.save()
    return s


def client(s):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


@pytest.fixture
def world():
    panel = Panel.objects.create(name="p", base_url="https://p.test", admin_username="a", admin_password_enc="x")
    plan = Plan.objects.create(name_fa="ماهانه", name_en="Monthly", price=100000, duration_days=30, panel=panel)
    card = BankCard.objects.create(card_number="6037991234567890", holder_name="x", bank_name="Melli")
    boss = staff("boss", superadmin=True)
    support = staff("sup", perms=("payment.view", "payment.approve", "accounting.view"))
    return {"panel": panel, "plan": plan, "card": card, "boss": boss, "support": support}


def pay(w, username, amount, *, status="approved", service=True, when=None):
    u = User.objects.filter(username=username).first() or User.objects.create_user(username, "Str0ngPass!", name=username.title())
    when = when or timezone.now()
    n = Order.objects.count() + 1
    svc = Service.objects.create(user=u, panel=w["panel"], panel_username=f"{username}-{n}", current_plan=w["plan"],
                                 status=ServiceStatus.ACTIVE) if service else None
    o = Order.objects.create(user=u, plan=w["plan"], type="new", amount=amount, amount_unique=amount + n,
                             unique_expire_at=when + timedelta(minutes=30), service=svc,
                             status="completed" if status == "approved" else "pending_payment")
    o.sync_unique_lock()
    o.save()
    return Payment.objects.create(order=o, amount=amount, status=status, method=PaymentMethod.CARD_MANUAL,
                                  bank_card=w["card"], confirmed_at=when if status == "approved" else None)


def totals(w):
    """Every figure the Transactions cards + Accounting + Analytics + card report show."""
    c = client(w["boss"])
    acc = c.get("/api/v1/admin/accounting/?period=monthly").json()
    day = c.get("/api/v1/admin/accounting/?period=daily").json()
    now = timezone.now()
    fin = A.financial(now - timedelta(days=40), now + timedelta(minutes=1))
    ret = A.retention(now - timedelta(days=40), now + timedelta(minutes=1))
    cards = c.get("/api/v1/admin/cards/deposit-report/").json()
    return {
        "month": Decimal(str(acc["revenue"])), "month_n": acc["transactions"], "today": Decimal(str(day["revenue"])),
        "list": c.get(T).json()["count"], "pending": c.get(T + "?status=pending").json()["count"],
        "queue": c.get("/api/v1/admin/payments/pending/").json()["count"],
        "analytics": Decimal(fin["revenue"]), "ltv": {r["username"]: Decimal(r["ltv"]) for r in ret["top_ltv"]},
        "customers": ret["customers"], "cards": Decimal(str(cards["grand_total"])),
    }


# ------------------------------------------------------------------ TX number
def test_number_is_sequential_unique_and_formatted(world):
    a, b = pay(world, "ali", 100000), pay(world, "sara", 200000)
    a.refresh_from_db(); b.refresh_from_db()
    assert a.number == a.id and b.number == b.id and b.number > a.number
    assert a.tx_number == f"TX-{a.id:06d}"
    row = client(world["boss"]).get(T).json()["results"][0]
    assert row["tx_number"] == b.tx_number and row["number"] == b.number


def test_backfill_migration_numbers_old_rows(world):
    p = pay(world, "ali", 100000)
    Payment.objects.filter(pk=p.pk).update(number=None)
    from django.apps import apps as live_apps

    importlib.import_module("apps.payments_sms.migrations.0009_payment_number_void").backfill(live_apps, None)
    p.refresh_from_db()
    assert p.number == p.id


def test_search_by_number_user_and_account(world):
    a, b = pay(world, "ali", 100000), pay(world, "sara", 200000)
    c = client(world["support"])
    for term in (b.tx_number, b.tx_number.lower(), f"TX{b.number}", str(b.number)):
        ids = [r["id"] for r in c.get(T, {"search": term}).json()["results"]]
        assert b.id in ids, term
        if term.lower().startswith("tx"):
            assert ids == [b.id], term
    assert [r["id"] for r in c.get(T, {"search": "ali"}).json()["results"]] == [a.id]
    assert [r["id"] for r in c.get(T, {"search": a.order.service.panel_username}).json()["results"]] == [a.id]


def test_csv_export_has_the_number_first(world):
    a = pay(world, "ali", 100000)
    r = client(world["support"]).get(T, {"export": "csv", "lang": "en"})
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0][0] == "Transaction" and rows[1][0] == a.tx_number and rows[1][2] == "100000"


def test_customer_order_and_bot_show_the_number(world):
    from apps.telegram.bot import screens

    p = pay(world, "ali", 100000)
    u = p.order.user
    c = APIClient()
    c.force_authenticate(u)
    rows = c.get("/api/v1/orders/").json()
    rows = rows.get("results", rows)
    assert rows[0]["tx_number"] == p.tx_number
    assert p.tx_number in screens.order_status(u, Order.objects.get(pk=p.order_id)).text


# ------------------------------------------------------------------ delete (void) + totals
def test_totals_before_delete_after_delete_and_after_restore(world):
    keep = pay(world, "ali", 100000)
    gone = pay(world, "sara", 250000)
    pend = pay(world, "reza", 70000, status="pending", service=False)
    before = totals(world)
    assert before["month"] == before["today"] == before["analytics"] == before["cards"] == Decimal(350000)
    assert before["month_n"] == 2 and before["list"] == 3 and before["pending"] == 1 and before["queue"] == 1
    assert before["ltv"] == {"sara": 250000, "ali": 100000} and before["customers"] == 2

    c = client(world["boss"])
    r = c.post(T + f"{gone.id}/delete/", {"reason": "duplicate test payment", "service_action": "keep"}, format="json")
    assert r.status_code == 200 and r.json()["voided"] is True
    r = c.post(T + f"{pend.id}/delete/", {"reason": "fake receipt", "service_action": "keep"}, format="json")
    assert r.status_code == 200
    after = totals(world)
    assert after["month"] == after["today"] == after["analytics"] == after["cards"] == Decimal(100000)
    assert after["month_n"] == 1 and after["list"] == 1 and after["pending"] == 0 and after["queue"] == 0
    assert after["ltv"] == {"ali": 100000} and after["customers"] == 1
    # "keep" (default) left sara's order + service alone; the pending one closed its order
    assert Order.objects.get(pk=gone.order_id).status == OrderStatus.COMPLETED
    assert Service.objects.get(pk=gone.order.service_id).status == ServiceStatus.ACTIVE
    po = Order.objects.get(pk=pend.order_id)
    assert po.status == OrderStatus.CANCELLED and po.amount_unique_lock is None
    # "Show deleted"
    shown = c.get(T, {"deleted": "1"}).json()
    assert shown["count"] == 3 and {r["id"] for r in shown["results"] if r["voided"]} == {gone.id, pend.id}
    only = c.get(T, {"deleted": "only"}).json()
    assert {r["id"] for r in only["results"]} == {gone.id, pend.id}
    assert all(r["restorable_until"] for r in only["results"])

    assert c.post(T + f"{gone.id}/restore/").status_code == 200
    assert c.post(T + f"{pend.id}/restore/").status_code == 200
    again = totals(world)
    assert again == before
    assert Order.objects.get(pk=pend.order_id).status == OrderStatus.PENDING_PAYMENT


def test_audit_records_who_when_reason_amount(world):
    p = pay(world, "ali", 123000)
    c = client(world["boss"])
    c.post(T + f"{p.id}/delete/", {"reason": "wrong amount typed", "service_action": "keep"}, format="json")
    c.post(T + f"{p.id}/restore/")
    v = AuditLog.objects.get(action="payment.voided")
    assert v.staff_label == "boss" and v.created_at and v.detail["reason"] == "wrong amount typed"
    assert v.detail["amount"] == "123000" and v.detail["tx"] == p.tx_number
    r = AuditLog.objects.get(action="payment.restored")
    assert r.staff_label == "boss" and r.detail["voided_by"] == "boss" and r.detail["amount"] == "123000"


def test_reason_required_and_double_delete(world):
    p = pay(world, "ali", 100000)
    c = client(world["boss"])
    r = c.post(T + f"{p.id}/delete/", {"reason": " ", "service_action": "keep"}, format="json")
    assert r.status_code == 400 and r.json()["field"] == "reason"
    assert not Payment.objects.get(pk=p.pk).voided_at
    assert c.post(T + f"{p.id}/delete/", {"reason": "dup row", "service_action": "keep"}, format="json").status_code == 200
    assert c.post(T + f"{p.id}/delete/", {"reason": "dup row", "service_action": "keep"}, format="json").status_code == 409


def test_restore_only_within_30_days(world):
    p = pay(world, "ali", 100000)
    c = client(world["boss"])
    c.post(T + f"{p.id}/delete/", {"reason": "dup row", "service_action": "keep"}, format="json")
    Payment.objects.filter(pk=p.pk).update(voided_at=timezone.now() - timedelta(days=31))
    r = c.post(T + f"{p.id}/restore/")
    assert r.status_code == 409 and r.json()["code"] == "expired"
    Payment.objects.filter(pk=p.pk).update(voided_at=timezone.now() - timedelta(days=29))
    assert c.post(T + f"{p.id}/restore/").status_code == 200


def test_other_roles_get_403(world):
    p = pay(world, "ali", 100000)
    full = staff("full", perms=("payment.view", "payment.approve", "accounting.view", "roles.manage", "settings.manage"))
    for s in (world["support"], full):
        c = client(s)
        assert c.get(T + f"{p.id}/delete-preview/").status_code == 403
        assert c.post(T + f"{p.id}/delete/", {"reason": "nope nope", "service_action": "keep"}, format="json").status_code == 403
        assert c.post(T + "bulk-delete/", {"ids": [p.id], "reason": "nope nope", "service_action": "keep"}, format="json").status_code == 403
        assert c.post(T + f"{p.id}/restore/").status_code == 403
        assert c.post(T + "bulk-restore/", {"ids": [p.id]}, format="json").status_code == 403
    assert not Payment.objects.get(pk=p.pk).voided_at
    client(world["boss"]).post(T + f"{p.id}/delete/", {"reason": "dup row", "service_action": "keep"}, format="json")
    # deleted rows stay hidden from other roles, even when they ask for them
    c = client(world["support"])
    assert c.get(T, {"deleted": "1"}).json()["count"] == 0
    assert c.get(T + f"{p.id}/").status_code == 404
    assert c.post(T + f"{p.id}/restore/").status_code == 403


def test_preview_shows_the_linked_order_and_service(world):
    p = pay(world, "ali", 100000)
    d = client(world["boss"]).get(T + f"{p.id}/delete-preview/").json()
    assert d["tx_number"] == p.tx_number and d["order"]["id"] == p.order_id
    assert d["service"]["panel_username"] == p.order.service.panel_username
    assert d["default_action"] == "keep" and d["actions"] == ["keep", "disable", "delete"]
    nosvc = pay(world, "sara", 1000, service=False)
    assert client(world["boss"]).get(T + f"{nosvc.id}/delete-preview/").json()["actions"] == ["keep"]


class FakePasarGuard:
    """Stands in for PasarGuard at PasarGuardClient._request, so the real client methods run;
    records every HTTP call. fail = {(METHOD, "path-prefix"): exception} injects errors."""

    def __init__(self, monkeypatch, users=()):
        from apps.panel.client import PasarGuardClient

        self.users = {u: {"username": u, "status": "active", "used_traffic": 123, "admin": {"username": "caspin"}}
                      for u in users}
        self.calls, self.fail, self.ignore_delete, self.ignore_disable = [], {}, False, False
        fake = self

        def _request(client, method, path, **kw):
            fake.calls.append((method, path, kw.get("json")))
            for (m, prefix), exc in fake.fail.items():
                if m == method and path.startswith(prefix):
                    raise exc
            from apps.panel.exceptions import PanelNotFound

            name = path.split("/api/user/", 1)[1].split("/")[0]
            if name not in fake.users:
                raise PanelNotFound(f"user {name} not found")
            if method == "DELETE":
                if not fake.ignore_delete:
                    fake.users.pop(name)
                return None
            if method == "PUT":
                if not fake.ignore_disable:
                    fake.users[name].update(kw.get("json") or {})
                return dict(fake.users[name])
            return dict(fake.users[name])

        monkeypatch.setattr(PasarGuardClient, "_request", _request)


def _svc_name(p):
    return Service.objects.get(pk=p.order.service_id).panel_username


def test_option_is_required_never_silently_keep(world):
    p = pay(world, "ali", 100000)
    c = client(world["boss"])
    for body in ({"reason": "refunded"}, {"reason": "refunded", "service_action": ""},
                 {"reason": "refunded", "service_action": "remove"}):
        r = c.post(T + f"{p.id}/delete/", body, format="json")
        assert r.status_code == 400 and r.json()["field"] == "service_action", body
    r = c.post(T + "bulk-delete/", {"ids": [p.id], "reason": "refunded"}, format="json")
    assert r.status_code == 400 and r.json()["field"] == "service_action"
    assert Payment.objects.get(pk=p.pk).voided_at is None


def test_delete_option_reaches_pasarguard_and_removes_the_service(world, monkeypatch):
    p = pay(world, "ali", 100000)
    name, svc_id = _svc_name(p), p.order.service_id
    pg = FakePasarGuard(monkeypatch, users=[name, "someone-else"])
    r = client(world["boss"]).post(T + f"{p.id}/delete/", {"reason": "refunded", "service_action": "delete"}, format="json")
    assert r.status_code == 200, r.json()
    assert r.json()["service_result"] == "deleted" and r.json()["void_service_action"] == "delete"
    assert ("DELETE", f"/api/user/{name}", None) in pg.calls
    assert name not in pg.users and "someone-else" in pg.users          # only that account
    assert not Service.objects.filter(pk=svc_id).exists()                 # and gone in our DB
    assert Order.objects.get(pk=p.order_id).status == OrderStatus.CANCELLED
    v = AuditLog.objects.get(action="payment.voided").detail
    assert v["service_action"] == "delete" and v["service_result"] == "deleted"
    assert [c["call"] for c in v["panel_calls"]] == [f"DELETE /api/user/{name}", f"GET /api/user/{name}"]
    assert AuditLog.objects.filter(action="service.deleted").exists()


@pytest.mark.parametrize("action", ["delete", "disable"])
def test_pasarguard_error_rolls_back_the_whole_delete(world, monkeypatch, action):
    from apps.panel.exceptions import PanelUnavailable

    p = pay(world, "ali", 100000)
    name, svc_id = _svc_name(p), p.order.service_id
    pg = FakePasarGuard(monkeypatch, users=[name])
    pg.fail[("DELETE" if action == "delete" else "PUT", "/api/user/")] = PanelUnavailable("panel request failed: 502")
    before = totals(world)
    r = client(world["boss"]).post(T + f"{p.id}/delete/", {"reason": "refunded", "service_action": action}, format="json")
    assert r.status_code == 502
    assert "PasarGuard" in r.json()["detail"] and "nothing was deleted" in r.json()["detail"]
    assert Payment.objects.get(pk=p.pk).voided_at is None
    assert Order.objects.get(pk=p.order_id).status == OrderStatus.COMPLETED
    assert Service.objects.get(pk=svc_id).status == ServiceStatus.ACTIVE
    assert name in pg.users and totals(world) == before
    assert not AuditLog.objects.filter(action="payment.voided").exists()
    f = AuditLog.objects.get(action="payment.void_failed").detail
    assert f["service_action"] == action and "502" in f["panel_calls"][-1]["error"]


def test_account_still_there_after_delete_rolls_back(world, monkeypatch):
    p = pay(world, "ali", 100000)
    name, svc_id = _svc_name(p), p.order.service_id
    pg = FakePasarGuard(monkeypatch, users=[name])
    pg.ignore_delete = True                                       # PasarGuard answers OK but keeps it
    r = client(world["boss"]).post(T + f"{p.id}/delete/", {"reason": "refunded", "service_action": "delete"}, format="json")
    assert r.status_code == 502 and "still exists" in r.json()["detail"]
    assert Payment.objects.get(pk=p.pk).voided_at is None and Service.objects.filter(pk=svc_id).exists()


def test_unexpected_error_rolls_back(world, monkeypatch):
    p = pay(world, "ali", 100000)
    pg = FakePasarGuard(monkeypatch, users=[_svc_name(p)])
    pg.fail[("DELETE", "/api/user/")] = ConnectionError("reset by peer")
    r = client(world["boss"]).post(T + f"{p.id}/delete/", {"reason": "refunded", "service_action": "delete"}, format="json")
    assert r.status_code == 502 and "ConnectionError" in r.json()["detail"]
    assert Payment.objects.get(pk=p.pk).voided_at is None


def test_disable_option_reaches_pasarguard(world, monkeypatch):
    p = pay(world, "ali", 100000)
    name = _svc_name(p)
    pg = FakePasarGuard(monkeypatch, users=[name])
    c = client(world["boss"])
    r = c.post(T + f"{p.id}/delete/", {"reason": "refunded", "service_action": "disable"}, format="json")
    assert r.status_code == 200 and r.json()["service_result"] == "disabled"
    assert ("PUT", f"/api/user/{name}", {"status": "disabled"}) in pg.calls and pg.users[name]["status"] == "disabled"
    assert Service.objects.get(pk=p.order.service_id).status == ServiceStatus.DISABLED
    assert Order.objects.get(pk=p.order_id).status == OrderStatus.CANCELLED
    c.post(T + f"{p.id}/restore/")
    assert Order.objects.get(pk=p.order_id).status == OrderStatus.COMPLETED


def test_disable_not_applied_rolls_back(world, monkeypatch):
    p = pay(world, "ali", 100000)
    pg = FakePasarGuard(monkeypatch, users=[_svc_name(p)])
    pg.ignore_disable = True
    r = client(world["boss"]).post(T + f"{p.id}/delete/", {"reason": "refunded", "service_action": "disable"}, format="json")
    assert r.status_code == 502 and "still" in r.json()["detail"]
    assert Payment.objects.get(pk=p.pk).voided_at is None
    assert Order.objects.get(pk=p.order_id).status == OrderStatus.COMPLETED


@pytest.mark.parametrize("action", ["delete", "disable"])
def test_bulk_passes_the_option_and_isolates_failures(world, monkeypatch, action):
    from apps.panel.exceptions import PanelUnavailable

    a, b = pay(world, "ali", 1000), pay(world, "sara", 2000)
    nosvc = pay(world, "reza", 3000, service=False)
    pg = FakePasarGuard(monkeypatch, users=[_svc_name(a), _svc_name(b)])
    pg.fail[("DELETE" if action == "delete" else "PUT", f"/api/user/{_svc_name(b)}")] = PanelUnavailable("down")
    r = client(world["boss"]).post(T + "bulk-delete/", {"ids": [a.id, b.id, nosvc.id], "reason": "test rows",
                                                        "service_action": action}, format="json").json()
    res = {x["id"]: x for x in r["results"]}
    assert res[a.id]["ok"] and res[a.id]["service_result"] == ("deleted" if action == "delete" else "disabled")
    assert not res[b.id]["ok"] and res[b.id]["code"] == "panel_error"
    assert res[nosvc.id]["ok"] and res[nosvc.id]["service_result"] == "no_service"
    assert Payment.objects.get(pk=a.pk).voided_at and Payment.objects.get(pk=nosvc.pk).voided_at
    assert Payment.objects.get(pk=b.pk).voided_at is None                         # untouched
    assert Order.objects.get(pk=b.order_id).status == OrderStatus.COMPLETED
    assert Service.objects.filter(pk=b.order.service_id, status=ServiceStatus.ACTIVE).exists()


def test_cancel_drops_an_unapplied_scheduled_renewal(world):
    p = pay(world, "ali", 100000)
    o = p.order
    o.type = "renew"
    o.save()
    ScheduledRenewal.objects.create(service=o.service, plan=world["plan"], order=o, renewal_mode="x")
    from apps.payments_sms.voiding import void_payment

    with pytest.MonkeyPatch.context() as mp:
        FakePasarGuard(mp, users=[o.service.panel_username])
        void_payment(p.id, staff=world["boss"], reason="refunded", service_action="disable")
    assert not ScheduledRenewal.objects.filter(order=o).exists()


def test_voided_payment_cannot_be_approved(world):
    p = pay(world, "ali", 70000, status="pending", service=False)
    client(world["boss"]).post(T + f"{p.id}/delete/", {"reason": "fake receipt", "service_action": "keep"}, format="json")
    with pytest.raises(PaymentError):
        approve_payment(p.id, actor=world["boss"])
    r = client(world["support"]).post(f"/api/v1/admin/payments/{p.id}/approve/", {}, format="json")
    assert r.status_code == 400
    assert Payment.objects.get(pk=p.pk).status == PaymentStatus.PENDING


def test_cancelled_order_is_never_fulfilled(world):
    from apps.orders.tasks import fulfill_order

    p = pay(world, "ali", 70000, status="pending", service=False)
    client(world["boss"]).post(T + f"{p.id}/delete/", {"reason": "fake receipt", "service_action": "keep"}, format="json")
    assert fulfill_order.run(p.order_id) == {"skipped": "cancelled"}


def test_bulk_delete_and_restore(world):
    a, b, c_ = pay(world, "ali", 1000), pay(world, "sara", 2000), pay(world, "reza", 3000, service=False)
    c = client(world["boss"])
    assert c.post(T + "bulk-delete/", {"ids": [a.id, b.id, c_.id], "reason": "", "service_action": "keep"}, format="json").status_code == 400
    r = c.post(T + "bulk-delete/", {"ids": [a.id, b.id, c_.id, 999999], "reason": "test rows", "service_action": "keep"}, format="json").json()
    assert r["ok"] == 3 and r["failed"] == 1
    assert Payment.objects.live().count() == 0
    assert totals(world)["month"] == 0
    r = c.post(T + "bulk-restore/", {"ids": [a.id, b.id, c_.id]}, format="json").json()
    assert r["ok"] == 3 and Payment.objects.live().count() == 3
