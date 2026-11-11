"""v1.56 — store import from another bot (apps/tenancy/importers, docs/store-import.md). SYNTHETIC dumps only.

Covered: the dump reader (zip / gz / sql, quoting, a decoy INSERT inside a value, size + shape checks); the scan is read-only
and its preview carries no Telegram ids / usernames (masked); services are linked ONLY when PasarGuard says the store's
reseller owns them (another admin's never, one already linked anywhere never); 1-day tests and never-paid rows skipped; the
«active in the old bot but missing on PasarGuard» list; the checklist is required; a DB backup comes first (a failed backup
writes nothing); balances become one-use credit codes and a big one only when confirmed; the 63-style paid history is
read-only (no Payment rows, no revenue); nothing on PasarGuard is written; no customer is messaged; re-runs never
duplicate; undo removes only unused rows; imported customers follow the store's own phone rule (both cases); the credit is
offered by the bot / checkout and is personal; our own store is untouched; API = our staff only, never on a store domain.
"""
import gzip
import io
import json
import zipfile
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.common.models import AuditLog
from apps.crm.models import DiscountCode
from apps.notifications.models import Notification
from apps.orders.models import Order
from apps.panel.models import Panel, Service
from apps.payments_sms.models import Payment
from apps.plans.models import Plan
from apps.tenancy import context
from apps.tenancy.importers import dump as D
from apps.tenancy.importers import engine as E
from apps.tenancy.models import ImportRecord, StoreImport
from apps.tenancy.tests.test_phase8 import _boss, _client
from apps.tenancy.tests.test_v153_export_fee import _store, codes  # noqa: F401 — fixture

pytestmark = pytest.mark.django_db
GB = 1024 ** 3
RESELLER = "imanx"
HOST = "shop-iman.example"
NOW = int(timezone.now().timestamp())
BASE_TG = 7_000_000_000


def _q(v):
    if v is None:
        return "NULL"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _table(name, cols, rows, *, col_list=False):
    create = f"CREATE TABLE `{name}` (\n" + ",\n".join(f"  `{c}` varchar(200) DEFAULT NULL" for c in cols) + "\n) ENGINE=InnoDB;\n"
    if not rows:
        return create
    head = f"INSERT INTO `{name}` ({', '.join(f'`{c}`' for c in cols)}) VALUES\n" if col_list else f"INSERT INTO `{name}` VALUES\n"
    return create + head + ",\n".join("(" + ", ".join(_q(r.get(c)) for c in cols) + ")" for r in rows) + ";\n"


U_COLS = ["id", "limit_usertest", "username", "number", "Balance", "User_Status", "agent", "affiliatescount", "affiliates",
          "namecustom", "register", "lang"]
I_COLS = ["id_invoice", "id_user", "username", "Service_location", "time_sell", "name_product", "price_product", "Volume",
          "Service_time", "Status"]
P_COLS = ["code_product", "name_product", "price_product", "Volume_constraint", "Location", "Service_time", "agent"]
PAY_COLS = ["id", "id_user", "id_order", "time", "price", "Payment_Method", "payment_Status", "id_invoice"]


def tg(i):
    return BASE_TG + i


def mirza_dump() -> str:
    users = [dict(id=tg(i), username=f"cust{i}", number="none", Balance=0, User_Status="Active", agent="f", affiliates="0",
                  namecustom="none", register=NOW - 86400 * 30, lang="fa") for i in range(1, 9)]
    users[1]["affiliates"] = str(tg(1))                     # cust2 was brought by cust1
    users[2]["Balance"] = 30000                              # small balance → credit
    users[3]["Balance"] = 8_500_000                          # the outlier → only when confirmed
    users[4]["User_Status"] = "block"
    users[5]["number"] = "09121112233"                       # a phone the old bot had
    users[6]["agent"] = "n"
    inv = [  # (key, user, account, status, days)
        ("i1", 1, "iman_a1", "active", 30), ("i2", 2, "iman_a2", "send_on_hold", 30), ("i3", 3, "iman_a3", "disabled", 30),
        ("i4", 1, "test_1", "active", 1),                     # 1-day test → skipped
        ("i5", 4, "never_paid", "unpaid", 30),                # never delivered → skipped
        ("i6", 5, "gone_live", "active", 30),                 # live in the bot, missing on PasarGuard → listed
        ("i7", 6, "gone_old", "disabled", 30),                # missing, not live
        ("i8", 7, "collide_9", "active", 30),                 # owned by ANOTHER PasarGuard admin → never
        ("i9", 8, "ours_linked", "active", 30),               # already linked in OUR store → never
        ("i10", 2, "iman_a2", "disabled", 30),                # an older duplicate row of iman_a2
    ]
    invoices = [dict(id_invoice=k, id_user=tg(u), username=a, Service_location="WireGuard", time_sell=NOW - (86400 if k != "i10" else 864000),
                     name_product="30GB", price_product=150000, Volume=30, Service_time=d, Status=st) for k, u, a, st, d in inv]
    products = [dict(code_product="9b19", name_product="30GB", price_product=150000, Volume_constraint=30, Location="WireGuard",
                     Service_time=30, agent="f")]
    pays = [dict(id=str(n), id_user=tg(u), id_order=f"o{n}", time="2026/10/01 12:30:00", price=p, Payment_Method="cart to cart",
                 payment_Status=st, id_invoice=inv_) for n, u, p, st, inv_ in [
        (1, 1, 150000, "paid", "getconfigafterpay|iman_a1"), (2, 2, 150000, "paid", "getextenduser|iman_a2"),
        (3, 3, 50000, "paid", "0|wallet"), (4, 1, 150000, "reject", "getconfigafterpay|x"), (5, 2, 99000, "expire", "0|w")]]
    setting = _table("setting", ["Bot_Status", "text"], [dict(Bot_Status="on", text="INSERT INTO `user` VALUES (1, 'fake');")])
    return ("-- MySQL dump (synthetic)\nSET NAMES utf8mb4;\n" + setting
            + _table("user", U_COLS, users) + _table("invoice", I_COLS, invoices, col_list=True) + _table("product", P_COLS, products)
            + _table("marzban_panel", ["code_panel", "name_panel", "type", "url_panel", "password_panel"],
                     [dict(code_panel="1b8a", name_panel="WireGuard", type="marzban", url_panel="https://secret.example", password_panel="S3CRET")])
            + _table("Payment_report", PAY_COLS, pays))


def as_zip(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("backup.sql", text)
    return buf.getvalue()


# ------------------------------------------------------------------ fake PasarGuard (records every call)
def pg_user(name, owner, status="active"):
    return {"username": name, "status": status, "admin": {"username": owner}, "subscription_url": f"/sub/{name}",
            "used_traffic": 0, "data_limit": 30 * GB, "expire": None}


class FakePG:
    def __init__(self):
        self.calls = []
        self.users = [pg_user("iman_a1", RESELLER), pg_user("iman_a2", RESELLER, "on_hold"), pg_user("iman_a3", "ImanX", "expired"),
                      pg_user("test_1", RESELLER), pg_user("collide_9", "otheradmin"), pg_user("ours_linked", RESELLER)]
        self.users += [pg_user(f"filler{i}", "someone") for i in range(7)]

    def list_users(self, *, search="", limit=20, offset=0):
        self.calls.append(("GET", "/api/users", offset))
        return self.users[offset:offset + 5], len(self.users)        # small pages: paging is exercised

    def get_user(self, name):
        self.calls.append(("GET", f"/api/user/{name}"))
        u = next((u for u in self.users if u["username"].lower() == name.lower()), None)
        if u is None:
            from apps.panel.exceptions import PanelNotFound
            raise PanelNotFound(name)
        return u

    def __getattr__(self, name):                                     # anything else would be a write: record + refuse
        def refuse(*a, **kw):
            self.calls.append(("WRITE", name))
            raise AssertionError(f"PasarGuard write attempted: {name}")
        return refuse


@pytest.fixture
def pg(monkeypatch):
    fake = FakePG()
    monkeypatch.setattr("apps.panel.services.client_for", lambda panel: fake)
    return fake


@pytest.fixture
def backup(monkeypatch):
    state = {"n": 0, "status": "ok"}

    def fake():
        state["n"] += 1
        return NS(pk=99, status=state["status"], error="disk full" if state["status"] != "ok" else "")
    monkeypatch.setattr("apps.telegram.backup.run_database_backup", fake)
    return state


@pytest.fixture
def world(codes, settings, tmp_path, pg, backup):  # noqa: F811
    settings.MEDIA_ROOT = tmp_path
    panel = Panel.objects.create(name="PG", base_url="https://pg.test", admin_username="caspin", admin_password_enc="p")
    store = _store("iman", HOST, RESELLER)
    ours_user = User.objects.create_user("our_customer", "Str0ngPass!", telegram_id=tg(8))   # same Telegram id as cust8, OUR store
    Service.objects.create(user=ours_user, panel=panel, panel_username="ours_linked", status="active")
    with context.tenant_context(store.pk):
        plan = Plan.objects.create(panel=panel, name_fa="۳۰ گیگ وایرگارد", price=Decimal(150000), data_limit=30 * GB,
                                   duration_days=30, vpn_type="wireguard")
    return NS(panel=panel, store=store, plan=plan, ours_user=ours_user, tmp=tmp_path)


def _uploaded(world, raw=None, name="backup.zip"):
    with context.tenant_context(world.store.pk):
        obj = E.upload(raw or as_zip(mirza_dump()), name)
        E.scan(obj.pk)
        obj.refresh_from_db()
    return obj


def _run(world, obj, **choice):
    with context.tenant_context(world.store.pk):
        E.start(obj.pk, {"old_bot_stopped": True, "plan_map": {"30GB": world.plan.pk}, **choice})
        E.run(obj.pk)
        obj.refresh_from_db()
    return obj


# ------------------------------------------------------------------ dump reader
def test_dump_reader_formats_quoting_and_decoys():
    text = mirza_dump()
    t = D.parse(D.read_upload(as_zip(text), "b.zip"))
    assert len(t["user"]) == 8 and len(t["invoice"]) == 10 and len(t["Payment_report"]) == 5
    assert t["setting"][0]["text"] == "INSERT INTO `user` VALUES (1, 'fake');"            # a value, never a statement
    assert t["invoice"][0]["Status"] == "active" and t["user"][0]["number"] == "none"     # no stray spaces
    assert D.parse(D.read_upload(gzip.compress(text.encode()), "b.sql.gz"))["user"] == t["user"]
    assert D.parse(D.read_upload(text.encode(), "b.sql"))["user"] == t["user"]
    q = D.parse("CREATE TABLE `x` (\n  `a` text,\n  `b` int\n) ;\nINSERT INTO `x` VALUES ('it''s \\'q\\' \\n', NULL),( 'x,y)' , 5 );")
    assert q["x"] == [{"a": "it's 'q' \n", "b": None}, {"a": "x,y)", "b": "5"}]
    two = io.BytesIO()
    with zipfile.ZipFile(two, "w") as z:
        z.writestr("a.sql", text)
        z.writestr("b.sql", text)
    for raw, name in ((two.getvalue(), "two.zip"), (b"hello", "x.sql"), (b"PK\x03\x04broken", "x.zip"),
                      (b"x" * (D.MAX_UPLOAD + 1), "big.sql")):
        with pytest.raises(D.DumpError):
            D.read_upload(raw, name)


# ------------------------------------------------------------------ scan = preview, read-only, masked
def test_scan_preview_buckets_masked_and_read_only(world, pg):
    obj = _uploaded(world)
    assert obj.state == StoreImport.READY and obj.source == "mirza"
    pv = obj.preview
    assert pv["services"]["link"] == 3                         # iman_a1, iman_a2 (newest row), iman_a3 (case-insensitive owner)
    assert pv["services"]["test"] == 1 and pv["services"]["not_sold"] == 1 and pv["services"]["duplicate"] == 1
    assert pv["services"]["missing"] == 2 and pv["services"]["other_admin"] == 1 and pv["services"]["linked_elsewhere"] == 1
    assert [m["panel_username"] for m in pv["missing_live"]] == ["gone_live"]   # live in the bot, not on PasarGuard
    assert pv["customers"] == {"total": 8, "new": 8, "existing": 0, "blocked": 1, "agents": 1, "with_phone": 1, "referred": 1}
    assert pv["credits"]["count"] == 1 and pv["credits"]["total"] == 30000
    assert pv["credits"]["review"][0]["amount"] == 8_500_000 and pv["credits"]["review"][0]["who"].startswith("cu")
    assert pv["history"] == {"paid": 3, "total": 350000, "by_kind": {"buy": 1, "renew": 1, "wallet": 1}}
    assert pv["plan_groups"][0]["name"] == "30GB" and pv["plan_groups"][0]["suggested_plan"] == world.plan.pk
    assert pv["store"]["reseller"] == RESELLER and pv["store"]["phone_required"] is False
    blob = json.dumps(pv)
    for secret in [str(tg(i)) for i in range(1, 9)] + ["cust4", "S3CRET", "secret.example"]:
        assert secret not in blob                              # the page never shows Telegram ids / names / panel secrets
    assert not any(c[0] == "WRITE" for c in pg.calls)
    with context.tenant_context(world.store.pk):
        assert User.objects.count() == 0 and Service.objects.count() == 0 and not ImportRecord.objects.exists()
    f = world.tmp / obj.file
    assert f.exists() and oct(f.stat().st_mode & 0o777) == "0o600" and oct(f.parent.stat().st_mode & 0o777) == "0o700"


# ------------------------------------------------------------------ run
def test_import_needs_checklist_and_a_store_plan(world, codes):  # noqa: F811
    obj = _uploaded(world)
    with context.tenant_context(world.store.pk):
        with pytest.raises(E.ImportFailure) as e:
            E.start(obj.pk, {"plan_map": {}})
        assert e.value.code == "old_bot"
    foreign = Plan.objects.create(panel=world.panel, name_fa="our plan", price=Decimal(1), data_limit=GB, duration_days=1)
    with context.tenant_context(world.store.pk):
        with pytest.raises(E.ImportFailure) as e:
            E.start(obj.pk, {"old_bot_stopped": True, "plan_map": {"30GB": foreign.pk}})   # our store's plan: refused
        assert e.value.code == "plan"
        obj.refresh_from_db()
        assert obj.state == StoreImport.READY


def test_failed_backup_writes_nothing(world, backup):
    backup["status"] = "failed"
    obj = _run(world, _uploaded(world))
    assert obj.state == StoreImport.FAILED and "backup" in obj.error
    with context.tenant_context(world.store.pk):
        assert User.objects.count() == 0 and not ImportRecord.objects.exists()


def test_import_links_only_the_resellers_accounts_and_writes_nothing_on_pasarguard(world, pg, backup):
    before_ours = (User.objects.count(), Service.objects.count(), DiscountCode.objects.count())
    obj = _run(world, _uploaded(world))
    assert obj.state == StoreImport.DONE, obj.error
    assert backup["n"] == 1 and obj.backup_log_id == 99
    assert not any(c[0] == "WRITE" for c in pg.calls)          # PasarGuard: reads only
    assert obj.file == "" and not any(world.tmp.rglob("*.sql"))   # the dump is deleted once imported
    r = obj.result
    assert r["customers_created"] == 8 and r["services_linked"] == 3 and r["referrals"] == 1
    assert r["credits"] == 1 and r["credits_held"] == 1 and r["history"] == 3
    with context.tenant_context(world.store.pk):
        assert User.objects.count() == 8
        names = set(Service.objects.values_list("panel_username", flat=True))
        assert names == {"iman_a1", "iman_a2", "iman_a3"}         # never collide_9 / ours_linked / test_1 / missing ones
        s1 = Service.objects.get(panel_username="iman_a1")
        assert s1.user.telegram_id == tg(1) and s1.current_plan_id == world.plan.pk and s1.source == "import"
        o = Order.objects.get(service=s1)
        assert o.type == "imported" and o.amount == 0 and o.status == "completed" and o.source == "import"
        assert not Payment.objects.exists()                      # history is never revenue
        assert not Notification.objects.exists()                 # nobody is messaged
        blocked = User.objects.get(telegram_id=tg(5))
        assert blocked.is_active is False and "blocked there" in blocked.admin_note
        assert User.objects.get(telegram_id=tg(6)).phone == "09121112233"
        assert User.objects.get(telegram_id=tg(2)).referred_by.telegram_id == tg(1)
        assert all(u.has_usable_password() for u in User.objects.all())   # usable (random) password: JWT accepts them
        dc = DiscountCode.objects.get()
        assert dc.kind == "credit" and dc.discount_type == "fixed" and dc.amount_off == 30000 and dc.user.telegram_id == tg(3)
        assert dc.max_uses == 1 and dc.expires_at > timezone.now()
        assert ImportRecord.objects.filter(kind="history").count() == 3
        assert {r.data["kind"] for r in ImportRecord.objects.filter(kind="history")} == {"buy", "renew", "wallet"}
        rep = {r["panel_username"]: r["outcome"] for r in StoreImport.objects.get(pk=obj.pk).report if r["type"] == "service"}
        assert rep["iman_a1"] == "linked" and rep["collide_9"] == "other_admin" and rep["gone_live"] == "missing"
    # our own store is untouched
    assert (User.objects.count(), Service.objects.count(), DiscountCode.objects.count()) == before_ours
    assert Service.objects.get(panel_username="ours_linked").user_id == world.ours_user.pk
    assert AuditLog.objects.filter(action="store.import_done").exists()


def test_rerun_never_duplicates_and_big_credit_only_when_confirmed(world):
    obj = _run(world, _uploaded(world))
    obj2 = _uploaded(world)                                       # the same dump again
    assert obj2.preview["services"].get("link", 0) == 0 and obj2.preview["services"]["already"] == 3
    key = obj2.preview["credits"]["review"][0]["key"]
    obj2 = _run(world, obj2, confirm_credits=[key, "not-a-key"])
    assert obj2.state == StoreImport.DONE
    with context.tenant_context(world.store.pk):
        assert User.objects.count() == 8 and Service.objects.count() == 3
        assert ImportRecord.objects.filter(kind="history").count() == 3
        assert sorted(DiscountCode.objects.values_list("amount_off", flat=True)) == [30000, 8_500_000]
    assert obj2.result["customers_existing"] == 8 and obj2.result.get("customers_created", 0) == 0
    assert obj.pk != obj2.pk


def test_undo_removes_only_unused_rows(world, pg):
    obj = _run(world, _uploaded(world))
    with context.tenant_context(world.store.pk):
        keep = User.objects.get(telegram_id=tg(4))
        Order.objects.create(user=keep, type="new", status="pending_payment", amount=Decimal(150000), amount_unique=Decimal(150321),
                             unique_expire_at=timezone.now())       # activity after the import
        used = DiscountCode.objects.get()
        used.used_at = timezone.now()
        used.save()
        out = E.undo(obj.pk)
        assert out["removed"]["services"] == 3 and out["removed"]["history"] == 3
        assert {k["kind"] for k in out["kept"]} == {"customer", "credit"}
        assert set(User.objects.values_list("telegram_id", flat=True)) == {tg(3), tg(4)}   # the credit's owner + the active one
        assert not Service.objects.exists() and not Order.objects.filter(type="imported").exists()
        assert DiscountCode.objects.filter(pk=used.pk).exists()
        obj.refresh_from_db()
        assert obj.state == StoreImport.UNDONE
        with pytest.raises(E.ImportFailure):
            E.undo(obj.pk)
    assert not any(c[0] == "WRITE" for c in pg.calls)
    assert Service.objects.filter(panel_username="ours_linked").exists()


# ------------------------------------------------------------------ the store's own sign-up rules
@pytest.mark.parametrize("phone_required", [True, False])
def test_imported_customers_follow_the_store_phone_rule(world, phone_required):
    from apps.settings_app.branding import set_store_setting
    from apps.telegram.accounts import handle_contact
    from apps.telegram.gate import needs_phone

    with context.tenant_context(world.store.pk):
        set_store_setting("force_share_phone", "true" if phone_required else "false", "bool")
    obj = _run(world, _uploaded(world))
    assert obj.preview["store"]["phone_required"] is phone_required
    with context.tenant_context(world.store.pk):
        u = User.objects.get(telegram_id=tg(1))
        assert u.phone == ""
        assert needs_phone(u) is phone_required                  # the bot / Mini App gate asks for it — or not
        res = handle_contact(tg(1), "+989120001122", contact_user_id=tg(1))
        assert res.status == "phone_saved" and res.user.pk == u.pk   # the same imported account, never a second one
        assert needs_phone(User.objects.get(pk=u.pk)) is False
        assert User.objects.filter(telegram_id=tg(1)).count() == 1
    assert needs_phone(User.objects.get(pk=world.ours_user.pk)) is False   # our store's rule is its own


# ------------------------------------------------------------------ the credit for the customer
def test_credit_is_personal_and_offered_by_bot_and_checkout(world):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    from apps.crm import discounts as Dc
    from apps.telegram.bot import screens as sc

    _run(world, _uploaded(world))
    with context.tenant_context(world.store.pk):
        owner = User.objects.get(telegram_id=tg(3))
        other = User.objects.get(telegram_id=tg(1))
        dc = DiscountCode.objects.get()
        assert [c.pk for c in Dc.credits_for(owner)] == [dc.pk] and Dc.credits_for(other) == []
        q = Dc.evaluate(dc.code, user=owner, plan=world.plan, order_type="new", amount=Decimal(150000))
        assert q.discount == Decimal(30000) and q.final == Decimal(120000)
        with pytest.raises(Dc.DiscountError) as e:
            Dc.evaluate(dc.code, user=other, plan=world.plan, order_type="new", amount=Decimal(150000))
        assert e.value.code == "invalid"
        assert Dc.any_usable_for(owner)
        screen = sc.discount_ask(owner, Dc.credits_for(owner))
        datas = [b.callback_data for row in screen.markup.keyboard for b in row]
        assert f"dc:cr:{dc.pk}" in datas and "30,000" in screen.markup.keyboard[0][0].text
        c = APIClient(HTTP_HOST=HOST)
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(owner).access_token}")
        r = c.get("/api/v1/orders/credits/")
        assert r.status_code == 200, r.content
        assert r.json()["results"] == [{"code": dc.code, "amount": "30000", "expires_at": r.json()["results"][0]["expires_at"]}]
        from apps.crm.views import _imported

        im = _imported(owner)
        assert im["credit"]["amount"] == 30000 and im["credit"]["used_at"] is None
        assert _imported(User.objects.get(telegram_id=tg(1)))["history_total"] == 150000


# ------------------------------------------------------------------ API: our staff only
def test_api_upload_preview_report_and_store_domain_blocked(world, django_capture_on_commit_callbacks):
    boss = _boss()
    url = f"/api/v1/admin/agency/panel-admins/{RESELLER}/store/imports/"
    from django.core.files.uploadedfile import SimpleUploadedFile

    with django_capture_on_commit_callbacks(execute=True):        # the scan task is queued on commit, inside the store
        r = boss.post(url, {"file": SimpleUploadedFile("backup.zip", as_zip(mirza_dump()), "application/zip")}, format="multipart")
    assert r.status_code == 202, r.content
    st = boss.get(url).json()                                    # scanned in Celery (eager in tests), inside the store
    cur = st["results"][0]
    assert cur["state"] == "ready", cur
    assert cur["preview"]["services"]["link"] == 3
    csv = boss.get(f"{url}{cur['id']}/report.csv")
    assert csv.status_code == 200 and csv["Content-Type"].startswith("text/csv")
    body = csv.content.decode("utf-8-sig")
    assert body.splitlines()[0].startswith("type,outcome,outcome_fa,panel_username")
    assert "gone_live,active,True" in body and "S3CRET" not in body
    assert boss.post(f"{url}{cur['id']}/run/", {"plan_map": {}}, format="json").json()["code"] == "old_bot"
    # a store's own staff / domain never reach it
    from apps.tenancy import staff as S

    owner, _ = S.ensure_owner(world.store, "imanowner")
    assert _client(owner, HOST).get(url).status_code in (403, 404)
    assert boss.get(f"/api/v1/admin/agency/panel-admins/nostore/store/imports/").status_code == 404
    # a second upload while one is waiting is fine only once it's done / discarded
    assert boss.delete(f"{url}{cur['id']}/").status_code == 200
    with context.tenant_context(world.store.pk):
        assert StoreImport.objects.get(pk=cur["id"]).state == "discarded" and not any(world.tmp.rglob("*.sql"))
