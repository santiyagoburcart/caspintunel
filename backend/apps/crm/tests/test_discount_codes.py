"""v1.26 discount codes: rules, limits, the final amount is what every payment check
uses (SMS exact amount incl. the unique digits, card-to-card review), admin API +
permissions + audit, reports, bot flow; win-back codes keep working."""
import io
from datetime import timedelta
from decimal import Decimal

import pytest
import responses
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff, User
from apps.adminpanel.tokens import issue_tokens
from apps.common.models import AuditLog
from apps.crm import discounts as D
from apps.crm.models import DiscountCode
from apps.orders.models import Order
from apps.orders.services import DiscountCodeRefused, create_order, quote_order
from apps.panel.models import Panel
from apps.payments_sms.models import Payment, SmsAppDevice
from apps.payments_sms.services import approve_payment, reject_payment, submit_receipt
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db
GB = 1024 ** 3
BASE = "https://panel.test"


@pytest.fixture
def panel():
    return Panel.objects.create(name="P", base_url=BASE, admin_username="a", admin_password_enc="p", default_group_ids=[6])


@pytest.fixture
def plan(panel):
    return Plan.objects.create(name_fa="ماهانه", name_en="Monthly", price=Decimal("200000"), data_limit=50 * GB,
                               duration_days=30, group_ids=[6], panel=panel)


@pytest.fixture
def plan2(panel):
    return Plan.objects.create(name_fa="سه‌ماهه", name_en="3 months", price=Decimal("500000"), data_limit=150 * GB,
                               duration_days=90, group_ids=[6], panel=panel)


def cust(name="ali", **kw):
    return User.objects.create_user(name, "Str0ngPass!", **kw)


def code(**kw):
    m2m = {k: kw.pop(k) for k in ("customers", "plans") if k in kw}
    kw.setdefault("code", "OFF20")
    kw.setdefault("kind", "campaign")
    kw.setdefault("percent", 20)
    dc = DiscountCode.objects.create(**kw)
    for k, v in m2m.items():
        getattr(dc, k).set(v)
    return dc


def buy(u, plan, c=None, name=None, **kw):
    return create_order(user=u, plan_id=plan.id, order_type="new", requested_account_name=name or f"{u.username}-x",
                        discount_code=c, **kw)


def refused(reason, fn, *a, **kw):
    with pytest.raises(DiscountCodeRefused) as e:
        fn(*a, **kw)
    assert e.value.code == reason, e.value.code
    return e.value


def _png():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="PNG")
    return SimpleUploadedFile("r.png", buf.getvalue(), content_type="image/png")


# ------------------------------------------------------------------ amounts
def test_percent_cap_and_fixed_amounts(plan):
    u = cust()
    code(code="P20")
    code(code="P50CAP", percent=50, max_discount=Decimal("30000"))
    code(code="FIX", discount_type="fixed", percent=0, amount_off=Decimal("45000"))
    code(code="BIG", discount_type="fixed", percent=0, amount_off=Decimal("999999"))
    q = quote_order(user=u, plan_id=plan.id, discount_code="p20")
    assert (q["original"], q["discount"], q["final"]) == (Decimal(200000), Decimal(40000), Decimal(160000))
    assert quote_order(user=u, plan_id=plan.id, discount_code="P50CAP")["discount"] == Decimal(30000)
    assert quote_order(user=u, plan_id=plan.id, discount_code="FIX")["final"] == Decimal(155000)
    assert quote_order(user=u, plan_id=plan.id, discount_code="BIG")["final"] == Decimal(0)   # never negative
    assert quote_order(user=u, plan_id=plan.id, discount_code=" ۱".replace("۱", "") + "p20 ")["code"] == "P20"


def test_order_stores_original_discount_final_and_code(plan):
    u = cust()
    dc = code()
    o = buy(u, plan, "off20")
    assert (o.original_amount, o.discount_amount, o.amount) == (Decimal(200000), Decimal(40000), Decimal(160000))
    assert o.discount_code == dc and o.discount_code_text == "OFF20"
    # what the customer pays = final + the unique digits (200..1500)
    assert Decimal(160200) <= o.amount_unique <= Decimal(161500)
    plain = buy(cust("bob"), plan)
    assert plain.original_amount == plain.amount == Decimal(200000) and plain.discount_code is None


# ------------------------------------------------------------------ payment checks use the final amount
@responses.activate
def test_sms_matches_the_discounted_exact_amount(plan, django_capture_on_commit_callbacks):
    responses.add(responses.POST, f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add(responses.POST, f"{BASE}/api/user", json={"username": "ali-x", "status": "on_hold",
                                                            "subscription_url": f"{BASE}/s/"}, status=200)
    device = SmsAppDevice.objects.create(name="pixel", is_active=True)
    code()
    o = buy(cust(), plan, "OFF20")
    c = APIClient()
    c.credentials(HTTP_X_DEVICE_TOKEN=device.api_token)
    # the undiscounted price never matches
    r = c.post("/api/v1/payments/sms/inbound/", {"text": f"مبلغ {int(Decimal(200000) * 10):,} ریال واریز شد"}, format="json")
    assert r.data["matched"] is False
    with django_capture_on_commit_callbacks(execute=True):
        r = c.post("/api/v1/payments/sms/inbound/", {"text": f"مبلغ {int(o.amount_unique * 10):,} ریال واریز شد"}, format="json")
    assert r.data["matched"] is True and r.data["order_id"] == o.id
    pay = Payment.objects.get(order=o)
    assert pay.amount == o.amount_unique and pay.status == "approved"


def test_card_review_uses_the_discounted_amount_and_revenue(plan):
    u = cust()
    code()
    o = buy(u, plan, "OFF20")
    submit_receipt(order=o, image=_png(), user=u)
    pay = Payment.objects.get(order=o)
    assert pay.amount == o.amount_unique < Decimal(200000)
    approve_payment(pay.id)
    st = D.stats(DiscountCode.objects.get(code="OFF20"))
    assert st["uses"] == 1 and st["customers"] == 1 and st["discount"] == Decimal(40000) and st["revenue"] == o.amount_unique


def test_unique_amount_reuse_keeps_the_same_discounted_invoice(plan):
    u = cust()
    code()
    o1 = buy(u, plan, "OFF20")
    o2 = buy(u, plan, "OFF20")
    assert o1.id == o2.id and getattr(o2, "reused", False)
    # the same purchase without the code: a new invoice at full price; the discounted one is dropped
    o3 = buy(u, plan)
    o1.refresh_from_db()
    assert o3.id != o1.id and o1.status == "expired" and o3.amount == Decimal(200000)


# ------------------------------------------------------------------ rules
def test_dates_active_and_unknown(plan):
    u = cust()
    now = timezone.now()
    code(code="SOON", starts_at=now + timedelta(hours=2))
    code(code="OLD", expires_at=now - timedelta(minutes=1))
    code(code="OFFLINE", is_active=False)
    refused("not_started", quote_order, user=u, plan_id=plan.id, discount_code="SOON")
    refused("expired", quote_order, user=u, plan_id=plan.id, discount_code="OLD")
    refused("inactive", quote_order, user=u, plan_id=plan.id, discount_code="OFFLINE")
    e = refused("invalid", quote_order, user=u, plan_id=plan.id, discount_code="NOPE")
    assert e.fa == "کد تخفیف معتبر نیست." and e.en == "This discount code is not valid."


def test_customers_plans_types_min_and_first_purchase(plan, plan2):
    a, b = cust("a"), cust("b")
    code(code="VIP", audience="selected", customers=[a])
    code(code="ONLY3M", plans=[plan2])
    code(code="RENEWONLY", applies_to="renew")
    code(code="MIN", min_order_amount=Decimal("300000"))
    code(code="FIRST", first_purchase_only=True)
    assert quote_order(user=a, plan_id=plan.id, discount_code="VIP")["discount"] > 0
    assert refused("not_for_you", quote_order, user=b, plan_id=plan.id, discount_code="VIP").fa == "این کد تخفیف برای حساب شما نیست."
    refused("not_for_plan", quote_order, user=a, plan_id=plan.id, discount_code="ONLY3M")
    assert quote_order(user=a, plan_id=plan2.id, discount_code="ONLY3M")["discount"] == Decimal(100000)
    refused("not_for_new", quote_order, user=a, plan_id=plan.id, discount_code="RENEWONLY")
    e = refused("min_amount", quote_order, user=a, plan_id=plan.id, discount_code="MIN")
    assert "300,000" in e.fa
    assert quote_order(user=a, plan_id=plan2.id, discount_code="MIN")["discount"] > 0
    assert quote_order(user=a, plan_id=plan.id, discount_code="FIRST")["discount"] > 0
    o = buy(a, plan)
    Order.objects.filter(pk=o.pk).update(status="completed")
    refused("first_purchase", quote_order, user=a, plan_id=plan.id, discount_code="FIRST")


def test_total_and_per_customer_limits_count_reservations_and_give_back(plan):
    a, b, c = cust("a"), cust("b"), cust("c")
    code(code="TWO", max_uses=2, max_uses_per_customer=1)
    oa = buy(a, plan, "TWO")
    buy(b, plan, "TWO")
    refused("used_up", buy, c, plan, "TWO")                      # two open invoices hold both uses
    oa.status = "expired"
    oa.save()
    assert buy(c, plan, "TWO").discount_amount > 0               # an expired invoice gives its use back
    Order.objects.filter(user=b).update(status="completed")
    refused("already_used", buy, b, plan, "TWO", name="b-second")


def test_customer_can_retry_with_the_same_code(plan):
    a = cust("a")
    code(code="ONE", max_uses=1)
    first = buy(a, plan, "ONE", name="a-one")
    second = buy(a, plan, "ONE", name="a-two")                   # other name: the first unpaid invoice is replaced
    first.refresh_from_db()
    assert first.status == "expired" and second.discount_amount > 0


def test_rejected_payment_gives_the_use_back(plan):
    a, b = cust("a"), cust("b")
    code(code="ONE", max_uses=1)
    o = buy(a, plan, "ONE")
    submit_receipt(order=o, image=_png(), user=a)
    refused("used_up", buy, b, plan, "ONE")                      # receipt waiting for review holds it
    reject_payment(Payment.objects.get(order=o).id, reason="wrong")
    assert buy(b, plan, "ONE").discount_amount > 0


# ------------------------------------------------------------------ win-back stays the same
def test_winback_codes_still_work_and_are_personal(plan):
    owner, other = cust("owner"), cust("other")
    wb = DiscountCode.objects.create(code="WBABCDEFGH", kind="winback", user=owner, percent=10, max_uses=1,
                                     expires_at=timezone.now() + timedelta(days=3))
    refused("invalid", buy, other, plan, "WBABCDEFGH")
    o = buy(owner, plan, "wbabcdefgh")
    wb.refresh_from_db()
    assert o.discount_amount == Decimal(20000) and wb.order == o
    o.status = "paid"
    o.save()
    wb.refresh_from_db()
    assert wb.used_at is not None
    refused("already_used", buy, owner, plan, "WBABCDEFGH", name="owner-2")


# ------------------------------------------------------------------ API
def staff(perms=(), superadmin=False, name="s1"):
    s = Staff(username=name, is_superadmin=superadmin)
    if perms:
        r = Role.objects.create(name=f"r-{name}")
        r.permissions.set([Permission.objects.get_or_create(code=p, defaults={"name": p})[0] for p in perms])
        s.role = r
    s.set_password("Str0ngPass!")
    s.save()
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


def test_admin_api_permissions_create_edit_disable_and_audit(plan, plan2):
    viewer, manager, boss, nobody = (staff(["discounts.view"], name="v"), staff(["discounts.manage", "discounts.view"], name="m"),
                                     staff(superadmin=True, name="boss"), staff(["users.view"], name="n"))
    a = cust("a")
    body = {"code": "yalda1405", "name": "Yalda", "discount_type": "percent", "percent": 15, "max_discount": "50000",
            "starts_at": "2026-12-20T00:00:00+03:30", "expires_at": "2026-12-23T23:59:00+03:30",
            "audience": "selected", "customer_ids": [a.id], "plan_ids": [plan2.id], "applies_to": "both",
            "max_uses": 100, "max_uses_per_customer": 1, "min_order_amount": "100000", "first_purchase_only": False}
    assert nobody.get("/api/v1/admin/discounts/").status_code == 403
    assert viewer.post("/api/v1/admin/discounts/", body, format="json").status_code == 403
    r = manager.post("/api/v1/admin/discounts/", body, format="json")
    assert r.status_code == 201, r.content
    d = r.json()
    assert d["code"] == "YALDA1405" and d["kind"] == "campaign" and [c["id"] for c in d["customers"]] == [a.id]
    assert d["status"] == "scheduled" and d["stats"]["uses"] == 0
    assert AuditLog.objects.filter(action="discount.created", target_id=d["id"]).exists()
    assert viewer.get("/api/v1/admin/discounts/").json()["count"] == 1
    r = manager.patch(f"/api/v1/admin/discounts/{d['id']}/", {"is_active": False}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "disabled"
    log = AuditLog.objects.get(action="discount.disabled", target_id=d["id"])
    assert log.detail["changes"]["is_active"] == [True, False]
    r = boss.patch(f"/api/v1/admin/discounts/{d['id']}/", {"percent": 30, "plan_ids": [plan.id, plan2.id]}, format="json")
    assert r.status_code == 200
    assert AuditLog.objects.filter(action="discount.updated", target_id=d["id"]).exists()
    # validation
    assert manager.post("/api/v1/admin/discounts/", {**body, "code": "YALDA1405"}, format="json").status_code == 400
    assert manager.post("/api/v1/admin/discounts/", {**body, "code": "", "audience": "selected", "customer_ids": []},
                        format="json").status_code == 400
    assert manager.post("/api/v1/admin/discounts/", {**body, "code": "X2", "percent": 0}, format="json").status_code == 400
    assert manager.post("/api/v1/admin/discounts/", {**body, "code": "FIXNOAMT", "discount_type": "fixed"},
                        format="json").status_code == 400
    r = manager.post("/api/v1/admin/discounts/", {"discount_type": "fixed", "amount_off": "20000"}, format="json")
    assert r.status_code == 201 and len(r.json()["code"]) == 8                # random code
    assert manager.delete(f"/api/v1/admin/discounts/{d['id']}/").status_code == 405   # never deleted


def test_admin_cannot_rewrite_a_winback_code_but_can_disable_it(plan):
    owner = cust("owner")
    wb = DiscountCode.objects.create(code="WBXYZ", kind="winback", user=owner, percent=10, max_uses=1,
                                     expires_at=timezone.now() + timedelta(days=3))
    boss = staff(superadmin=True)
    assert boss.patch(f"/api/v1/admin/discounts/{wb.id}/", {"percent": 90}, format="json").status_code == 400
    r = boss.patch(f"/api/v1/admin/discounts/{wb.id}/", {"is_active": False}, format="json")
    assert r.status_code == 200 and r.json()["kind"] == "winback"
    refused("inactive", buy, owner, plan, "WBXYZ")
    listed = boss.get("/api/v1/admin/discounts/?kind=winback").json()["results"]
    assert [x["code"] for x in listed] == ["WBXYZ"] and listed[0]["owner"]["username"] == "owner"


def test_report_customers_options_and_accounting(plan):
    boss = staff(superadmin=True)
    u = cust("ali", phone="09120000000")
    dc = code()
    o = buy(u, plan, "OFF20")
    submit_receipt(order=o, image=_png(), user=u)
    approve_payment(Payment.objects.get(order=o).id)
    r = boss.get(f"/api/v1/admin/discounts/{dc.id}/report/").json()
    assert r["orders"][0]["original"] == "200000" and r["orders"][0]["discount"] == "40000"
    assert r["stats"]["uses"] == 1
    assert boss.get("/api/v1/admin/discounts/customers/?q=0912").json()["results"][0]["username"] == "ali"
    assert any(p["id"] == plan.id for p in boss.get("/api/v1/admin/discounts/options/").json()["plans"])
    acc = boss.get("/api/v1/admin/accounting/?period=daily").json()
    assert acc["discounts"]["uses"] == 1 and Decimal(acc["discounts"]["discount"]) == Decimal(40000)
    assert acc["discounts"]["by_code"][0]["code"] == "OFF20"
    s = boss.get("/api/v1/admin/discounts/summary/").json()
    assert s["uses"] == 1 and s["active"] == 1


def test_site_quote_and_order_errors_in_persian_and_english(plan):
    u = cust()
    c = APIClient()
    c.force_authenticate(u)
    code(code="OLD", expires_at=timezone.now() - timedelta(minutes=1))
    code()
    r = c.post("/api/v1/orders/quote/", {"plan": plan.id, "type": "new", "discount_code": "OLD"}, format="json")
    assert r.status_code == 400 and r.json()["discount_error"] == "expired"
    assert r.json()["discount_code"] == ["مهلت این کد تخفیف تمام شده است."]
    r = c.post("/api/v1/orders/quote/", {"plan": plan.id, "type": "new", "discount_code": "OLD", "lang": "en"}, format="json")
    assert r.json()["discount_code"] == ["This discount code has expired."]
    r = c.post("/api/v1/orders/quote/", {"plan": plan.id, "type": "new", "discount_code": "off20"}, format="json")
    assert r.status_code == 200 and r.json() == {"original": "200000", "discount": "40000", "final": "160000",
                                                 "code": "OFF20", "percent": 20}
    r = c.post("/api/v1/orders/", {"plan": plan.id, "type": "new", "requested_account_name": "ali-1",
                                   "discount_code": "OLD"}, format="json")
    assert r.status_code == 400 and r.json()["discount_error"] == "expired"
    r = c.post("/api/v1/orders/", {"plan": plan.id, "type": "new", "requested_account_name": "ali-1",
                                   "discount_code": "OFF20"}, format="json")
    assert r.status_code == 201
    o = r.json()["order"] if "order" in r.json() else r.json()
    assert o["original_amount"] == "200000" and o["discount_amount"] == "40000" and o["discount_code_text"] == "OFF20"


# ------------------------------------------------------------------ bot
class FakeBot:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text, **kw):
        self.sent.append(text)

    def edit_message_text(self, text, *a, **kw):
        self.sent.append(text)


def test_bot_asks_for_a_code_applies_it_and_shows_it_on_the_invoice(plan, monkeypatch):
    from apps.telegram.bot import sales_bot as SB

    u = cust("tg", telegram_id=777, terms_accepted_at=timezone.now())
    store = {}
    monkeypatch.setattr(SB, "get_state", lambda tg: dict(store))
    monkeypatch.setattr(SB, "set_state", lambda tg, **v: store.update(v) or store)
    monkeypatch.setattr(SB, "clear_state", lambda tg: store.clear())
    shown = []
    monkeypatch.setattr(SB, "render", lambda bot, chat, screen, msg=None: shown.append(screen.text))
    bot = FakeBot()
    store.update(plan=plan.id, name="tg-1")
    # no code exists → straight to the invoice, no question
    SB._after_draft(bot, 1, u, 777)
    assert "#" in shown[-1] and "کد تخفیف دارید" not in shown[-1]
    Order.objects.all().delete()
    code()
    store.clear(); store.update(plan=plan.id, name="tg-2")
    SB._after_draft(bot, 1, u, 777)
    assert "کد تخفیف دارید" in shown[-1]

    class Msg:
        def __init__(self, text):
            self.text, self.from_user, self.chat, self.message_id = text, type("F", (), {"id": 777}), type("C", (), {"id": 1}), 5
    store["awaiting"] = "dcode"
    SB._typed(bot, Msg("nope"), u, "dcode")
    assert "کد تخفیف معتبر نیست" in shown[-1]
    SB._typed(bot, Msg("off20"), u, "dcode")
    assert "OFF20" in shown[-1] and "160,000" in shown[-1] and store["dcode"] == "OFF20"
    SB._place_order(bot, 1, u, 777)
    o = Order.objects.get(requested_account_name="tg-2")
    assert o.discount_amount == Decimal(40000) and o.source == "bot"
    assert "تخفیف (OFF20)" in shown[-1] and f"{int(o.amount_unique):,}" in shown[-1]
