"""v1.38.3 Transactions cards «واریزی‌های امروز / این ماه» = exactly what the list shows under the same filters: same query,
same date (payment date: confirmed_at, else created_at), Tehran days and the Jalali month — not a rolling 24 h / 30 days by
UTC. Voided rows and agency payments never count; a manual invoice counts on its entered payment date."""
from datetime import datetime, timedelta, timezone as dt_tz
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.agency.models import AgencyPayment
from apps.common import jalali
from apps.orders.models import Order, OrderStatus, OrderType
from apps.payments_sms.models import Payment, PaymentStatus
from apps.payments_sms.tests.test_blu import staff_client

pytestmark = pytest.mark.django_db
TZ = jalali.TZ
NOW = datetime(2026, 11, 4, 10, 0, tzinfo=dt_tz.utc)          # 1405/08/13 13:30 Tehran


def at(day_offset, hh, mm=0):
    """A moment in Tehran time relative to NOW's Tehran day."""
    d = NOW.astimezone(TZ).date() + timedelta(days=day_offset)
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=TZ)


def pay(user, amount, *, created, confirmed=None, status=PaymentStatus.APPROVED, voided=False):
    o = Order.objects.create(user=user, type=OrderType.NEW, status=OrderStatus.COMPLETED, amount=Decimal(amount),
                             amount_unique=Decimal(amount), unique_expire_at=created + timedelta(minutes=30))
    p = Payment.objects.create(order=o, amount=Decimal(amount), status=status, method="blu_auto",
                               confirmed_at=confirmed if status == PaymentStatus.APPROVED else None)
    Payment.objects.filter(pk=p.pk).update(created_at=created, voided_at=NOW if voided else None)
    return p.pk


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: NOW)
    return NOW


def test_cards_match_the_list_on_tehran_days(frozen):
    u = User.objects.create_user("c1", "Str0ngPass!")
    boss = staff_client("super", "boss")
    y_evening = pay(u, 175688, created=at(-1, 19, 6), confirmed=at(-1, 19, 6))       # in a rolling 24 h, NOT today
    early = pay(u, 251258, created=at(0, 1, 48), confirmed=at(0, 1, 48))             # 22:18 UTC yesterday = today in Tehran
    noon = pay(u, 470212, created=at(0, 12, 43), confirmed=at(0, 12, 43))
    pay(u, 999999, created=at(0, 9), confirmed=at(0, 9), voided=True)                 # deleted → never
    pending = pay(u, 120000, created=at(0, 11), status=PaymentStatus.PENDING)          # in «همه», not a deposit
    manual = pay(u, 250000, created=at(0, 10), confirmed=at(-20, 12))                  # entered today, paid 20 days ago
    AgencyPayment.objects.create(payer_kind="admin", payer_username="ag1", amount=Decimal(5000000), amount_unique=Decimal(5000300), status="approved",
                                 confirmed_at=at(0, 8), unique_expire_at=at(0, 9))     # agency: separate table

    s = boss.get("/api/v1/admin/transactions/summary/").json()
    today = jalali.tehran_today().isoformat()
    lst = boss.get(f"/api/v1/admin/transactions/?from={today}&to={today}&limit=100").json()["results"]
    assert {r["id"] for r in lst} == {early, noon, pending}                            # «همه» for today
    approved = boss.get(f"/api/v1/admin/transactions/?from={today}&to={today}&status=approved&limit=100").json()["results"]
    assert {r["id"] for r in approved} == {early, noon}
    assert s["today"]["count"] == len(approved) == 2
    assert Decimal(str(s["today"]["revenue"])) == Decimal(251258 + 470212)
    assert s["today"]["from_iso"] == s["today"]["to_iso"] == today and s["today"]["from"] == "1405/08/13"
    assert y_evening not in {r["id"] for r in approved} and manual not in {r["id"] for r in lst}

    # this Jalali month (1405/08/01 … 1405/08/30), the same way
    m = s["month"]
    assert (m["from"], m["to"]) == ("1405/08/01", "1405/08/30")
    rows = boss.get(f"/api/v1/admin/transactions/?from={m['from_iso']}&to={m['to_iso']}&status=approved&limit=100").json()["results"]
    assert {r["id"] for r in rows} == {y_evening, early, noon}                          # manual paid in the previous month
    assert m["count"] == 3 and Decimal(str(m["revenue"])) == Decimal(175688 + 251258 + 470212)
    # the cards follow the list's other filters too, and the row date is the payment date
    assert boss.get("/api/v1/admin/transactions/summary/?search=nobody-matches").json()["today"]["count"] == 0
    row = next(r for r in lst if r["id"] == early)
    assert row["pay_date"].startswith("2026-11-03T22:18")                              # stored UTC, a Tehran-today payment


def test_day_filter_and_display_use_tehran_time(frozen):
    assert jalali.to_jalali_str(datetime(2026, 11, 3, 22, 18, tzinfo=dt_tz.utc)) == "1405/08/13 01:48"
    from apps.adminpanel.views.finance import _parse_any_date

    start, end = _parse_any_date("1405/08/13"), _parse_any_date("2026-11-04", end_of_day=True)
    assert start == datetime(2026, 11, 4, 0, 0, tzinfo=TZ) and end.astimezone(TZ).strftime("%H:%M:%S") == "23:59:59"
    assert jalali.jalali_month_bounds()[0] == datetime(2026, 10, 23, 0, 0, tzinfo=TZ)   # 1405/08/01
