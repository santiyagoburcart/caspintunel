"""v1.59 — agency payments: an expired payment has no approve / reject, only «تأیید با تأخیر» when a deposit of exactly its
amount arrived later (linked + what was paid); a payment whose invoices were all paid by another payment (or another way)
becomes «جایگزین شد» (superseded_by) with no actions; the data fix migration. Store CRM + «تحلیل کسب‌وکار»: on a store's
domain only its own data (opt-in codes, not in the default ceiling); our panel sees a store with ?store=; a store can never
use ?store= to look at another; CRM settings stay ours."""
import importlib
from datetime import timedelta
from decimal import Decimal

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from apps.accounts.models import User
from apps.agency import billing, ledger
from apps.agency.models import AgencyInvoice, AgencyPayment, LedgerEntry
from apps.agency.tests.test_group_managers import pg, staff_client  # noqa: F401
from apps.agency.tests.test_invoices import quiet  # noqa: F401
from apps.crm.models import FollowUpCase
from apps.payments_sms.models import SmsMessage
from apps.tenancy import context
from apps.tenancy import staff as S
from apps.tenancy.tests.test_phase8 import _boss, _client
from apps.tenancy.tests.test_v153_export_fee import _store, codes  # noqa: F401

pytestmark = pytest.mark.django_db
URL = "/api/v1/admin/agency/payments/"


def _invoice(admin="g1-a", amount="100000"):
    e = LedgerEntry.objects.create(admin_username=admin, kind="manual_charge", amount=Decimal(amount), date=ledger.today())
    return billing.issue_for_entry(e)


def _pay(invs, admin="g1-a"):
    return billing.create_payment([i.id for i in invs], payer_kind="admin", payer_username=admin, allowed_admins=[admin])


def _expire(p):
    AgencyPayment.objects.filter(pk=p.pk).update(unique_expire_at=timezone.now() - timedelta(minutes=1))
    assert billing.expire_stale() >= 1
    p.refresh_from_db()
    assert p.status == "expired"
    return p


def _row(c, p):
    return next(r for r in c.get(URL, {"status": "all"}).json()["results"] if r["id"] == p.id)


# ------------------------------------------------------------------ 1) expired: no actions, late approval only with a deposit
def test_expired_payment_has_no_actions_until_a_matching_deposit(pg, quiet):  # noqa: F811
    boss = staff_client(superadmin=True)
    inv = _invoice()
    p = _expire(_pay([inv]))
    r = _row(boss, p)
    assert r["actions"] == [] and r["late_deposit"] is None
    assert boss.post(f"{URL}{p.id}/approve/", {}, format="json").status_code == 409
    assert boss.post(f"{URL}{p.id}/approve/", {"late": True}, format="json").status_code == 409     # no deposit yet
    assert boss.post(f"{URL}{p.id}/reject/", {"reason": "late"}, format="json").status_code == 409
    # a deposit of exactly the unique amount arrives later (outside the auto-match window) → «تأیید با تأخیر»
    sms = SmsMessage.objects.create(raw_text="deposit", parsed_amount=p.amount_unique, received_at=timezone.now())
    SmsMessage.objects.create(raw_text="other", parsed_amount=p.amount_unique + 1, received_at=timezone.now())
    r = _row(boss, p)
    assert r["actions"] == ["late_approve"] and Decimal(str(r["late_deposit"]["amount"])) == p.amount_unique
    assert boss.post(f"{URL}{p.id}/approve/", {}, format="json").status_code == 409                 # must say «late»
    ok = boss.post(f"{URL}{p.id}/approve/", {"late": True}, format="json")
    assert ok.status_code == 200, ok.content
    p.refresh_from_db(); inv.refresh_from_db()
    assert p.status == "approved" and p.sms_message_id == sms.id and p.paid_amount == p.amount_unique and inv.status == "paid"
    assert _row(boss, p)["actions"] == []


def test_a_deposit_before_the_payment_or_already_used_never_counts(pg, quiet):  # noqa: F811
    inv = _invoice()
    p = _pay([inv])
    SmsMessage.objects.create(raw_text="old", parsed_amount=p.amount_unique, received_at=p.created_at - timedelta(hours=1))
    p = _expire(p)
    assert billing.late_deposit(p) is None
    other = _expire(_pay([_invoice(amount="50000")]))
    used = SmsMessage.objects.create(raw_text="used", parsed_amount=p.amount_unique, received_at=timezone.now())
    AgencyPayment.objects.filter(pk=other.pk).update(sms_message=used)
    assert billing.late_deposit(p) is None


# ------------------------------------------------------------------ 2) superseded
def test_an_old_payment_is_superseded_when_another_pays_its_invoices(pg, quiet):  # noqa: F811
    boss = staff_client(superadmin=True)
    a, b = _invoice(amount="100000"), _invoice(amount="200000")
    old = _expire(_pay([a, b]))                                     # like AP-000026
    new = _pay([a, b, _invoice(amount="50000")])                    # like AP-000028 (the same invoices + one more)
    billing.approve_payment(new.id, staff=None, source="manual")
    old.refresh_from_db()
    assert old.status == "superseded" and old.superseded_by_id == new.id
    r = _row(boss, old)
    assert r["actions"] == [] and r["superseded_by"] == {"id": new.id, "number": new.number}
    assert boss.post(f"{URL}{old.id}/approve/", {"late": True}, format="json").status_code == 409
    assert old.amount_unique_lock is None


def test_a_checkout_superseded_by_a_ledger_payment_and_one_still_open_is_cancelled(pg, quiet):  # noqa: F811
    a, b = _invoice(amount="100000"), _invoice(amount="80000")
    both = _expire(_pay([a, b]))
    only_a = _pay([a])
    ledger.add_entry("g1-a", LedgerEntry.KIND_PAYMENT, 100000, ledger.today(), method="card", by="t", invoice_ids=[a.id])
    a.refresh_from_db(); b.refresh_from_db(); both.refresh_from_db(); only_a.refresh_from_db()
    assert a.status == "paid" and b.status == "unpaid"
    assert only_a.status == "superseded" and only_a.superseded_by_id is None                  # paid another way
    assert both.status == "expired"                                                            # b still open → stays


def test_data_fix_migration_expires_and_supersedes(pg, quiet, capsys):  # noqa: F811
    a, b = _invoice(amount="100000"), _invoice(amount="200000")
    old = _pay([a, b])
    AgencyPayment.objects.filter(pk=old.pk).update(status="expired", amount_unique_lock=None)    # expired before the fix
    new = _pay([a, b])
    billing.approve_payment(new.id, staff=None, source="manual")
    AgencyPayment.objects.filter(pk=old.pk).update(status="expired", superseded_by=None)        # what production had
    stale = _pay([_invoice(amount="70000")])
    AgencyPayment.objects.filter(pk=stale.pk).update(unique_expire_at=timezone.now() - timedelta(hours=3))
    mig = importlib.import_module("apps.agency.migrations.0017_supersede_and_expire_payments")
    mig.forwards(django_apps, None)
    old.refresh_from_db(); stale.refresh_from_db()
    assert old.status == "superseded" and old.superseded_by_id == new.id and stale.status == "expired"
    out = capsys.readouterr().out
    assert stale.number in out and f"{old.number}→{new.number}" in out


# ------------------------------------------------------------------ 6) store CRM + analytics
HOST, HOST_B = "crm-x.example", "crm-y.example"


@pytest.fixture
def stores(codes):  # noqa: F811
    from apps.accounts.models import Permission

    Permission.objects.get_or_create(code="crm.analytics", defaults={"name": "crm.analytics"})
    x, y = _store("cx", HOST, "resx"), _store("cy", HOST_B, "resy")
    ours = User.objects.create_user("our_cust", "Str0ngPass!")
    FollowUpCase.objects.create(user=ours, kind="manual", notes="OURS")
    out = {"ours": ours}
    for t, mark in ((x, "XX"), (y, "YY")):
        with context.tenant_context(t.pk):
            u = User.objects.create_user(f"{mark.lower()}_cust", "Str0ngPass!")
            FollowUpCase.objects.create(user=u, kind="manual", notes=mark)
            out[mark] = u
    return {"x": x, "y": y, **out}


def _owner_client(t, host, crm=True):
    S.set_ceiling(t, sorted(S.STORE_CODES) if crm else S.DEFAULT_CEILING)       # the real default = no crm.*
    owner, _ = S.ensure_owner(t, f"own-{t.slug}")
    return _client(owner, host)


def test_crm_codes_are_opt_in_per_store(stores):
    assert not (S.OPT_IN_CODES & set(S.DEFAULT_CEILING)) and S.OPT_IN_CODES <= S.STORE_CODES
    c = _owner_client(stores["x"], HOST, crm=False)
    assert c.get("/api/v1/admin/crm/cases/").status_code == 403                               # not switched on
    assert c.get("/api/v1/admin/crm/analytics/overview/").status_code == 403


def test_store_crm_sees_only_its_own_and_cannot_peek(stores):
    c = _owner_client(stores["x"], HOST)
    notes = {r["notes"] for r in c.get("/api/v1/admin/crm/cases/", {"status": "all"}).json()["results"]}
    assert notes == {"XX"}
    assert c.get(f"/api/v1/admin/crm/customers/{stores['XX'].id}/").status_code == 200
    assert c.get(f"/api/v1/admin/crm/customers/{stores['ours'].id}/").status_code == 404
    assert c.get(f"/api/v1/admin/crm/customers/{stores['YY'].id}/").status_code == 404
    peek = c.get("/api/v1/admin/crm/cases/", {"status": "all", "store": stores["y"].id}).json()["results"]
    assert {r["notes"] for r in peek} == {"XX"}                                                # ?store= ignored on a store
    assert c.get("/api/v1/admin/crm/analytics/overview/").status_code == 200
    assert c.get("/api/v1/admin/crm/settings/").status_code in (403, 404)                       # CRM rules stay ours
    assert c.get("/api/v1/admin/crm/stores/").status_code in (403, 404)


def test_our_panel_sees_ours_by_default_and_a_store_with_the_filter(stores):
    boss = _boss()
    cases = lambda **q: {r["notes"] for r in boss.get("/api/v1/admin/crm/cases/", {"status": "all", **q}).json()["results"]}  # noqa: E731
    assert cases() == {"OURS"}
    assert cases(store=stores["x"].id) == {"XX"} and cases(store=stores["y"].id) == {"YY"}
    assert cases(store=99999) == {"OURS"}                                                      # unknown store → ours
    assert boss.get(f"/api/v1/admin/crm/customers/{stores['XX'].id}/", {"store": stores["x"].id}).status_code == 200
    assert {s["name"] for s in boss.get("/api/v1/admin/crm/stores/").json()} == {stores["x"].name, stores["y"].name}
    assert boss.get("/api/v1/admin/crm/analytics/overview/", {"store": stores["x"].id}).status_code == 200
