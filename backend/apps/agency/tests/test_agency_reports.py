"""Accounting reports: period overview, Jalali monthly table, per-reseller month
breakdown, CSV / XLSX exports — all from the ledger (voided entries excluded)."""
import io
import zipfile
from datetime import date
from decimal import Decimal

import jdatetime
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff
from apps.adminpanel.tokens import issue_tokens
from apps.agency import ledger
from apps.agency.models import LedgerEntry

pytestmark = pytest.mark.django_db
URL = "/api/v1/admin/agency/ledger/report/"


def g(jy, jm, jd):
    return jdatetime.date(jy, jm, jd).togregorian()


@pytest.fixture
def c():
    s = Staff(username="boss", is_superadmin=True); s.set_password("x-Str0ng!"); s.save()
    cl = APIClient(); cl.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    # Mehr 1405: ali charged 300 GB (540k) + manual 100k, pays 400k; bea charged 50 GB (90k)
    LedgerEntry.objects.create(admin_username="ali", kind="quota_charge", amount=540000, gb=Decimal("300"), date=g(1405, 7, 3))
    LedgerEntry.objects.create(admin_username="ali", kind="manual_charge", amount=100000, date=g(1405, 7, 10))
    LedgerEntry.objects.create(admin_username="ali", kind="payment", amount=400000, method="card", date=g(1405, 7, 20))
    LedgerEntry.objects.create(admin_username="bea", kind="quota_charge", amount=90000, gb=Decimal("50"), date=g(1405, 7, 25))
    # Shahrivar 1405: ali opening charge 200k; Aban: bea pays 100k (credit 10k); a voided entry
    LedgerEntry.objects.create(admin_username="ali", kind="manual_charge", amount=200000, date=g(1405, 6, 15))
    LedgerEntry.objects.create(admin_username="bea", kind="payment", amount=100000, method="cash", date=g(1405, 8, 2))
    LedgerEntry.objects.create(admin_username="ali", kind="payment", amount=999999, date=g(1405, 7, 5), voided=True, void_reason="x")
    return cl


def test_overview_kpis_series_and_recent_payments(c):
    d = c.get(URL + "overview/", {"from": "1405/07/01", "to": "1405/07/30"}).json()
    assert d["kpis"] == {"charges": 730000, "payments": 400000, "net": 330000, "gb": 350.0, "payments_count": 1,
                         "outstanding": 440000, "credit": 10000, "resellers_owing": 1}
    assert d["bucket"] == "day" and len(d["series"]) == 30 and sum(p["charges"] for p in d["series"]) == 730000
    assert [p["username"] for p in d["recent_payments"]] == ["ali"] and d["recent_payments"][0]["method"] == "card"
    y = c.get(URL + "overview/", {"from": "1405/01/01", "to": "1405/12/29"}).json()
    assert y["bucket"] == "month" and y["series"][6]["key"] == "1405/07" and y["series"][6]["payments"] == 400000
    assert c.get(URL + "overview/", {"from": g(1405, 7, 1).isoformat(), "to": g(1405, 7, 30).isoformat()}).json()["kpis"]["charges"] == 730000


def test_monthly_and_breakdown_with_month_end_balance(c):
    rows = c.get(URL + "monthly/").json()["results"]
    assert [(r["year"], r["month"]) for r in rows] == [(1405, 8), (1405, 7), (1405, 6)]
    mehr = rows[1]
    assert (mehr["gb"], mehr["charges"], mehr["payments"], mehr["net"], mehr["resellers_charged"]) == (350.0, 730000, 400000, 330000, 2)
    b = c.get(URL + "monthly/1405/7/").json()
    by = {r["username"]: r for r in b["rows"]}
    assert by["ali"]["charges"] == 640000 and by["ali"]["payments"] == 400000 and by["ali"]["balance_end"] == 440000   # incl. Shahrivar 200k
    assert by["bea"]["balance_end"] == 90000 and b["totals"]["charges"] == 730000
    assert c.get(URL + "monthly/1405/13/").status_code == 400


def test_exports_csv_and_xlsx(c):
    r = c.get(URL + "monthly/", {"export": "csv", "lang": "fa"})
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv")
    text = r.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("ماه,") and "1405/07,350.0,730000,400000,330000,2,1" in text
    x = c.get(URL + "monthly/1405/7/", {"export": "xlsx", "lang": "en"})
    assert x.status_code == 200 and "spreadsheetml" in x["Content-Type"]
    z = zipfile.ZipFile(io.BytesIO(x.content))
    sheet = z.read("xl/worksheets/sheet1.xml").decode()
    assert "Reseller" in sheet and "<v>640000</v>" in sheet and "Total" in sheet
    assert {"[Content_Types].xml", "xl/workbook.xml", "xl/styles.xml"} <= set(z.namelist())


def test_needs_accounting_permission(c):
    s = Staff(username="viewer"); s.set_password("x-Str0ng!")
    role = Role.objects.create(name="v"); role.permissions.set([Permission.objects.get_or_create(code="agency.view", defaults={"name": "v"})[0]])
    s.role = role; s.save()
    v = APIClient(); v.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    assert v.get(URL + "overview/").status_code == 403
