"""CRM accounting & analytics: revenue figures, splits, retention (churn, renewal,
cohorts, lifetime, top LTV), ticket performance, overview, export, permissions."""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.crm import analytics as A
from apps.orders.models import Order
from apps.payments_sms.models import BankCard, Payment
from apps.panel.models import Panel
from apps.plans.models import Plan
from apps.tickets import services as TS
from apps.tickets.models import Ticket, TicketTopic

from .test_crm import client_for, customer, staff

pytestmark = pytest.mark.django_db
TZ = A.TZ


def at(k, day=10, hour=12):
    """an aware datetime inside Jalali month k=(y, m)"""
    d = A.month_start(k) + timedelta(days=day - 1)
    return datetime(d.year, d.month, d.day, hour, tzinfo=TZ)


@pytest.fixture
def setup():
    panel = Panel.objects.create(name="p", base_url="https://p.test", admin_username="a", admin_password_enc="x")
    monthly = Plan.objects.create(name_fa="ماهانه", name_en="Monthly", price=100000, duration_days=30, panel=panel)
    yearly = Plan.objects.create(name_fa="سالانه", name_en="Yearly", price=900000, duration_days=365, panel=panel)
    card = BankCard.objects.create(card_number="6037991234567890", holder_name="x", bank_name="Melli")
    return monthly, yearly, card


def pay(u, plan, when, amount, *, card=None, source="site", type_="new", discount=0):
    n = Order.objects.count() + 1
    o = Order.objects.create(user=u, plan=plan, type=type_, amount=amount, amount_unique=amount + n, discount_amount=discount,
                             unique_expire_at=when, status="completed", source=source)
    Order.objects.filter(pk=o.pk).update(created_at=when)
    Payment.objects.create(order=o, amount=amount, status="approved", method="sms_auto", bank_card=card, confirmed_at=when)
    return o


def test_financial_figures(setup):
    monthly, yearly, card = setup
    k = A.jkey(A.local_date(timezone.now()))
    prev = A.prev_key(k)
    a, b = customer("a"), customer("b")
    pay(a, monthly, at(prev), 100000, card=card)                       # a's first ever (previous month)
    pay(a, monthly, at(k, 2), 100000, card=card, type_="renew")       # returning
    pay(b, yearly, at(k, 3), 810000, source="bot", discount=90000)    # b new, with a win-back discount
    s, e = A.month_range(k)
    f = A.financial(s, max(e, timezone.now() + timedelta(minutes=1)))
    assert f["revenue"] == "910000" and f["payments"] == 2 and f["paying_customers"] == 2
    assert f["aov"] == "455000" and f["arpu"] == "455000"
    assert f["new_revenue"] == "810000" and f["returning_revenue"] == "100000" and f["new_customers"] == 1
    assert f["discount_cost"] == "90000"
    assert {c["channel"]: c["revenue"] for c in f["by_channel"]} == {"bot": "810000", "site": "100000"}
    assert [p["name_en"] for p in f["by_plan"]] == ["Yearly", "Monthly"]
    assert {c["card"] for c in f["by_card"]} == {"7890", "—"}
    assert f["avg_ltv"] == str(round(Decimal(1010000) / 2))
    assert f["monthly"][-1]["new"] == "810000"


def test_retention_churn_renewal_cohorts(setup):
    monthly, _yearly, _card = setup
    now_k = A.jkey(A.local_date(timezone.now()))
    m3 = A.prev_key(A.prev_key(A.prev_key(now_k)))
    m2 = A.next_key(m3)
    stay, leave = customer("stay"), customer("leave")
    pay(stay, monthly, at(m3, 1), 100000)
    pay(stay, monthly, at(m2, 1), 100000, type_="renew")             # renewed within the window
    pay(leave, monthly, at(m3, 10), 100000)                           # never again (covers into m2)
    r = A.retention(*A.month_range(now_k))
    by = {c["month"]: c for c in r["churn"]}
    # month after m2: "leave" (covered m3 → early m2) is gone
    assert by[A.jlabel(m2)]["active"] == 2
    m1 = A.next_key(m2)
    assert by[A.jlabel(m1)]["churned"] >= 1 and by[A.jlabel(m1)]["rate"] > 0
    # three coverages ended (stay ×2, leave ×1); only stay's first was followed by a purchase
    assert sum(x["due"] for x in r["renewal"]) == 3 and sum(x["renewed"] for x in r["renewal"]) == 1
    coh = {c["cohort"]: c for c in r["cohorts"]}[A.jlabel(m3)]
    assert coh["customers"] == 2 and coh["pct"][0] == 100.0
    assert r["avg_lifetime_days"] > 0 and r["top_ltv"][0]["username"] == "stay" and r["top_ltv"][0]["ltv"] == "200000"


def test_ticket_performance(setup):
    u = customer("t", )
    from apps.panel.models import Service

    Service.objects.create(user=u, panel=Panel.objects.first(), panel_username="t1", status="active")
    sara, omid = staff("sara", ["tickets.view", "tickets.reply", "tickets.close", "tickets.assign"]), staff("omid", ["tickets.view", "tickets.reply"])
    conn = TicketTopic.objects.get(name_en="Connection problem")
    t1 = TS.open_ticket(u, topic_id=conn.id, subject="a", body="b")
    Ticket.objects.filter(pk=t1.pk).update(created_at=timezone.now() - timedelta(minutes=30))
    t1.refresh_from_db()
    TS.staff_reply(t1, sara, body="hi")
    TS.staff_reply(t1, omid, body="also")
    TS.set_status(t1, sara, "closed")
    TS.set_status(t1, sara, "awaiting_admin")                         # reopened
    TS.set_status(t1, sara, "closed")                                 # and resolved again
    s, e = timezone.now() - timedelta(days=1), timezone.now() + timedelta(minutes=1)
    d = A.tickets(s, e)
    rows = {x["name"]: x for x in d["staff"]}
    assert rows["sara"]["handled"] == 1 and rows["omid"]["handled"] == 1
    assert 29 <= rows["sara"]["first_response_min"] <= 31 and rows["omid"]["first_response_min"] is None
    assert rows["sara"]["resolved"] == 1 and rows["sara"]["reopened"] == 1
    assert d["topics"][0]["name_en"] == "Connection problem" and d["topics"][0]["opened"] == 1


def test_overview_api_export_and_permissions(setup):
    monthly, _y, card = setup
    pay(customer("a"), monthly, timezone.now() - timedelta(hours=1), 100000, card=card)
    both = client_for(staff("acc", ["accounting.view", "crm.view"]))
    o = both.get("/api/v1/admin/crm/analytics/overview/").json()
    assert o["revenue_month"] == "100000" and len(o["trends"]["revenue"]) == 12 and len(o["trends"]["tickets"]) == 12
    assert {"active_customers", "at_risk", "expired", "winback_rate", "open_tickets", "avg_first_response_min"} <= set(o)
    f = both.get("/api/v1/admin/crm/analytics/financial/?preset=12m").json()
    assert f["revenue"] == "100000" and f["preset"] == "12m"
    jl = A.jkey(A.local_date(timezone.now()))
    f2 = both.get(f"/api/v1/admin/crm/analytics/financial/?from={jl[0]}/{jl[1]:02d}/01&to={jl[0]}/{jl[1]:02d}/28").json()
    assert f2["preset"] == "custom"
    r = both.get("/api/v1/admin/crm/analytics/financial/?preset=this_month&export=csv")
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv") and "100000" in r.content.decode("utf-8-sig")
    r = both.get("/api/v1/admin/crm/analytics/financial/?preset=this_month&export=xlsx&lang=en")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert both.get("/api/v1/admin/crm/analytics/retention/").status_code == 200
    assert both.get("/api/v1/admin/crm/analytics/tickets/").status_code == 403          # needs tickets.view
    crm_only = client_for(staff("crm", ["crm.view", "tickets.view"]))
    assert crm_only.get("/api/v1/admin/crm/analytics/financial/").status_code == 403    # needs accounting.view
    assert crm_only.get("/api/v1/admin/crm/analytics/tickets/").status_code == 200
    # analytics never writes: payments and orders unchanged
    assert Payment.objects.count() == 1 and Order.objects.get().status == "completed"
