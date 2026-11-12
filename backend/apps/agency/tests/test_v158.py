"""v1.58 Agency → «حسابداری» redesign: one table (agency/accounting.py) — per admin sales / paid in the period, debt now, last
payment, open invoices; the summary strip (sales, paid, total debt, debtors, adjustments as information); tabs debtors / all;
group filter + search; sort by any column (asc / desc); pages; the drawer's `?recent=5` statement; the group manager's
accounting rows carry the current debt + open amount and the group totals for its strip."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache

from apps.agency import accounting, ledger, managers
from apps.agency.models import AdminGroup, LedgerEntry, PanelAdmin
from apps.panel.models import Panel
from apps.payments_sms.tests.test_blu import staff_client
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting

pytestmark = pytest.mark.django_db
GB = 1024 ** 3
URL = "/api/v1/admin/agency/ledger/"


@pytest.fixture(autouse=True)
def setup():
    cache.clear()
    set_setting("agency_sync_enabled", True, ValueType.BOOL)
    Panel.objects.create(name="sigma", base_url="https://sigma.test", admin_username="u", admin_password_enc="p", is_active=True)


def _day(n):
    return ledger.today() - timedelta(days=n)


@pytest.fixture
def book():
    """ali: 300,000 charged 3 days ago, −100,000 «کاهش بدهی», +20,000 «افزایش بدهی», 50,000 paid → owes 170,000.
    bea: 100,000 charged 40 days ago (before this month for most days) and paid today. dan: 60,000 charged, nothing paid."""
    for n in ("ali", "bea", "dan"):
        PanelAdmin.objects.create(username=n)
        ledger.set_price(n, 1000, _day(400))
    ledger.record_quota_charge("ali", 0, 300 * GB, by="t", day=_day(3))
    ledger.add_entry("ali", LedgerEntry.KIND_ADJUST, 100000, _day(2), direction="decrease", by="t")
    ledger.add_entry("ali", LedgerEntry.KIND_ADJUST, 20000, _day(1), direction="increase", by="t")
    ledger.add_entry("ali", LedgerEntry.KIND_PAYMENT, 50000, _day(1), method="card", by="t")
    ledger.record_quota_charge("bea", 0, 100 * GB, by="t", day=_day(40))
    ledger.add_entry("bea", LedgerEntry.KIND_PAYMENT, 100000, _day(0), method="card", by="t")
    ledger.record_quota_charge("dan", 0, 60 * GB, by="t", day=_day(5))
    AdminGroup.objects.create(owner_username="ali", member_usernames="dan", name="North")


def test_one_table_numbers_and_strip(book):
    d = accounting.table(period="d7", tab="all")
    r = {x["username"]: x for x in d["results"]}
    assert r["ali"]["sales"] == Decimal(220000) and r["ali"]["paid"] == Decimal(50000) and r["ali"]["debt"] == Decimal(170000)
    assert r["bea"]["sales"] == 0 and r["bea"]["paid"] == Decimal(100000) and r["bea"]["debt"] == 0      # charged before the period
    assert r["dan"]["open_invoices"] == 1 and r["dan"]["open_amount"] == Decimal(60000) and r["dan"]["last_payment"] is None
    assert r["ali"]["open_amount"] == Decimal(300000) - Decimal(100000) - Decimal(50000)                  # what is still owed on it
    sm = d["summary"]
    assert sm["sales"] == Decimal(280000) and sm["paid"] == Decimal(150000) and sm["debt"] == Decimal(230000) and sm["debtors"] == 2
    assert (sm["adjust_count"], sm["adjust_down"], sm["adjust_up"]) == (2, Decimal(100000), Decimal(20000))


def test_tabs_filters_sort_and_pages(book):
    names = lambda d: [x["username"] for x in d["results"]]       # noqa: E731
    assert names(accounting.table(period="d7")) == ["ali", "dan"]                          # debtors, by debt desc
    assert names(accounting.table(period="d7", tab="all", sort="username", desc=False)) == ["ali", "bea", "dan"]
    assert names(accounting.table(period="d7", tab="all", sort="paid")) == ["bea", "ali", "dan"]
    assert names(accounting.table(period="d7", tab="all", sort="last_payment"))[0] == "bea"
    assert names(accounting.table(period="d7", tab="all", sort="open_invoices"))[-1] == "bea"
    g = AdminGroup.objects.get()
    d = accounting.table(period="d7", tab="all", group=g.id)
    assert set(names(d)) == {"ali", "dan"} and d["summary"]["paid"] == Decimal(50000)       # the strip follows the group
    assert names(accounting.table(period="d7", tab="all", q="north")) == ["ali", "dan"]    # search by group name too
    assert accounting.table(period="d7", tab="all", sort="nope")["sort"] == "debt"
    p = accounting.table(period="d7", tab="all", size=5, page=7)
    assert p["page"] == 1 and p["pages"] == 1


def test_api_periods_and_errors(book):
    c = staff_client(["agency.accounting"], "acc8")
    d = c.get(URL, {"period": "prev", "tab": "all"}).json()
    assert d["period"] == "prev" and "from_jalali" in d and d["tab"] == "all"
    d = c.get(URL, {"period": "custom", "from": _day(45).isoformat(), "to": _day(0).isoformat(), "tab": "all", "dir": "asc", "sort": "username"}).json()
    assert [x["username"] for x in d["results"]] == ["ali", "bea", "dan"] and d["desc"] is False
    assert Decimal(str(next(x for x in d["results"] if x["username"] == "bea")["sales"])) == Decimal(100000)
    r = c.get(URL, {"period": "custom"})
    assert r.status_code == 400 and r.json()["detail_fa"]


def test_drawer_recent_entries(book):
    c = staff_client(["agency.accounting"], "acc9")
    st = c.get(URL + "ali/", {"recent": 5}).json()
    assert st["entries_total"] == 4 and len(st["entries"]) == 4 and st["entries"][-1]["kind"] == "payment"
    for i in range(6):
        ledger.add_entry("ali", LedgerEntry.KIND_PAYMENT, 1000, _day(0), method="card", by="t")
    st = c.get(URL + "ali/", {"recent": 5}).json()
    assert st["entries_total"] == 10 and len(st["entries"]) == 5 and Decimal(str(st["balance"])) == Decimal(164000)
    assert len(c.get(URL + "ali/").json()["entries"]) == 10                                  # the full statement is unchanged


def test_manager_rows_carry_current_debt_and_open_amount(book):
    rows = {r["username"]: r for r in managers.admin_summaries(["ali", "dan"], _day(60), _day(10))}
    assert rows["ali"]["balance"] == 0 and rows["ali"]["debt"] == Decimal(170000)           # balance = at range end, debt = now
    assert rows["dan"]["open_amount"] == Decimal(60000) and rows["dan"]["unpaid_invoices"] == 1
