"""Multi-tenant Phase 8 (v1.52): a reseller store's own staff (docs/multi-tenant.md §11).

* Store staff sign in — and their tokens work — only on their own store's domains (never ours, never another store's).
* The ceiling (Tenant.permission_ceiling ⊆ STORE_CODES) bounds every store staff; lowering it strips the store's roles; a
  store's staff are never Super Admin.
* Roles / staff are listed and edited only inside their own store; store roles hold codes ⊆ ceiling ∩ the actor's own.
* Our staff create the owner login / reset its password on «فروشگاه» (shown once, never audited); the owner role = ceiling.
* Store staff link Telegram to THEIR store's bot and get ticket DMs through it.
* Release gates: STORE_CODES covers every code a store-safe view asks for and no platform-only code; signed in as the store
  owner, no admin endpoint shows our data.
"""
import json

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Permission, Role, Staff, User
from apps.adminpanel.tokens import issue_tokens
from apps.common.models import AuditLog
from apps.tenancy import context
from apps.tenancy import staff as S
from apps.tenancy.models import Tenant, TenantDomain
from apps.tenancy.tests.test_isolation import _list_urls

pytestmark = pytest.mark.django_db
HOST, HOST2 = "shop-p8.example", "other-p8.example"
OURS = "ZZOURMARK8"
ADMIN = "/api/v1/admin/agency/panel-admins/p8admin/store/"


@pytest.fixture
def codes(_default_tenant):
    for c in sorted(S.STORE_CODES | {"agency.manage", "accounting.view", "settings.email", "users.purge", "crm.view"}):
        Permission.objects.get_or_create(code=c, defaults={"name": c})


@pytest.fixture
def store(codes):
    t = Tenant.objects.create(slug="s8", name="Store Eight", status="active", reseller_username="p8admin",
                              permission_ceiling=list(S.DEFAULT_CEILING))
    TenantDomain.objects.create(tenant=t, host=HOST, state="active")
    return t


@pytest.fixture
def other(codes):
    t = Tenant.objects.create(slug="s8b", name="Other", status="active", reseller_username="p8other",
                              permission_ceiling=list(S.DEFAULT_CEILING))
    TenantDomain.objects.create(tenant=t, host=HOST2, state="active")
    return t


def _client(staff, host=None):
    c = APIClient(HTTP_HOST=host) if host else APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(staff)['access']}")
    return c


def _boss():
    from apps.payments_sms.tests.test_blu import staff_client

    return staff_client("super", "p8-boss")


def _owner(store):
    owner, password = S.ensure_owner(store, "p8owner")
    return owner, password


# ------------------------------------------------------------------ sign-in only on the own store
def test_store_staff_sign_in_and_tokens_only_on_their_store(store, other):
    owner, password = _owner(store)
    login = {"username": "p8owner", "password": password}
    r = APIClient(HTTP_HOST=HOST).post("/api/v1/admin/auth/login/", login, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["staff"]["store_staff"] is True and r.json()["staff"]["is_superadmin"] is False
    for host in (None, HOST2):                                              # ours, another store
        c = APIClient(HTTP_HOST=host) if host else APIClient()
        assert c.post("/api/v1/admin/auth/login/", login, format="json").status_code == 401
    access = r.json()["access"]
    on_store = APIClient(HTTP_HOST=HOST); on_store.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    assert on_store.get("/api/v1/admin/auth/me/").status_code == 200
    for host in (None, HOST2):
        c = APIClient(HTTP_HOST=host) if host else APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        assert c.get("/api/v1/admin/auth/me/").status_code in (401, 403)
    # our staff keep working on a store's panel (support), as before
    assert _client(Staff.objects.create(username="our-p8", is_superadmin=True), HOST).get("/api/v1/admin/auth/me/").status_code == 200


# ------------------------------------------------------------------ the ceiling
def test_the_ceiling_bounds_store_staff_and_lowering_it_strips_roles(store):
    owner, _ = _owner(store)
    role = Role.objects.create(tenant=store, name="support")
    role.permissions.set(Permission.objects.filter(code__in=["tickets.view", "tickets.reply", "payment.view"]))
    clerk = Staff.objects.create(username="p8clerk", tenant=store, role=role, is_superadmin=True)   # flag ignored
    assert clerk.has_perm("tickets.reply") and not clerk.has_perm("agency.manage") and not clerk.has_perm("crm.view")
    assert set(owner.role.permissions.values_list("code", flat=True)) == set(S.DEFAULT_CEILING)
    with pytest.raises(S.StaffError):
        S.set_ceiling(store, ["tickets.view", "agency.manage"])              # never a platform code
    S.set_ceiling(store, ["tickets.view", "tickets.reply", "roles.manage"])
    clerk.refresh_from_db(); store.refresh_from_db()
    assert not clerk.has_perm("payment.view") and clerk.has_perm("tickets.reply")
    assert set(role.permissions.values_list("code", flat=True)) == {"tickets.view", "tickets.reply"}
    assert set(S.owner_role(store).permissions.values_list("code", flat=True)) == {"tickets.view", "tickets.reply", "roles.manage"}
    log = AuditLog.objects.filter(action="store.ceiling").latest("id")
    assert log.detail["stripped"] == {"support": ["payment.view"]}


# ------------------------------------------------------------------ roles + staff stay in their store
def test_roles_and_staff_are_listed_and_edited_only_in_their_store(store):
    owner, _ = _owner(store)
    our_role = Role.objects.create(name="support")
    our = Staff.objects.create(username="our-clerk", role=our_role)
    boss = _boss()
    assert "p8owner" not in json.dumps(boss.get("/api/v1/admin/staff/?limit=200").json())     # our panel: ours only
    assert S.OWNER_ROLE not in json.dumps(boss.get("/api/v1/admin/roles/?limit=200").json())
    c = _client(owner, HOST)
    staff_rows = c.get("/api/v1/admin/staff/?limit=200").json()
    staff_rows = staff_rows.get("results", staff_rows)
    assert [r["username"] for r in staff_rows] == ["p8owner"]
    # a store role may reuse our role's name, never a code outside its ceiling ∩ the owner's own
    r = c.post("/api/v1/admin/roles/", {"name": "support", "permission_codes": ["tickets.view", "agency.manage"]}, format="json")
    assert r.status_code == 403
    r = c.post("/api/v1/admin/roles/", {"name": "support", "permission_codes": ["tickets.view", "tickets.reply"]}, format="json")
    assert r.status_code == 201, r.content
    store_role = Role.objects.get(pk=r.json()["id"])
    assert store_role.tenant_id == store.pk
    assert c.post("/api/v1/admin/roles/", {"name": "support", "permission_codes": []}, format="json").status_code == 400
    perms = c.get("/api/v1/admin/permissions/?limit=200").json()
    perms = perms.get("results", perms)
    assert {p["code"] for p in perms} <= S.STORE_CODES and "agency.manage" not in {p["code"] for p in perms}
    # staff: created in the store, never Super Admin, never with our role or the owner role
    base = {"username": "p8new", "password": "Str0ngPass!1", "is_active": True}
    assert c.post("/api/v1/admin/staff/", {**base, "role": our_role.pk}, format="json").status_code == 400
    assert c.post("/api/v1/admin/staff/", {**base, "role": store_role.pk, "is_superadmin": True}, format="json").status_code == 403
    assert c.post("/api/v1/admin/staff/", {**base, "role": S.owner_role(store).pk}, format="json").status_code == 403
    r = c.post("/api/v1/admin/staff/", {**base, "role": store_role.pk}, format="json")
    assert r.status_code == 201, r.content
    assert Staff.objects.get(username="p8new").tenant_id == store.pk
    assert c.delete(f"/api/v1/admin/staff/{owner.pk}/").status_code == 403          # the owner is ours to manage
    assert c.patch(f"/api/v1/admin/staff/{our.pk}/", {"is_active": False}, format="json").status_code == 404
    assert c.delete(f"/api/v1/admin/roles/{S.owner_role(store).pk}/").status_code == 403
    assert c.get("/api/v1/admin/staff/group-manager-options/").status_code == 404     # agency data is ours


# ------------------------------------------------------------------ owner + ceiling from «فروشگاه»
def test_our_staff_create_the_owner_and_set_the_ceiling(store):
    boss = _boss()
    r = boss.post(ADMIN + "owner/", {"username": "p8owner"}, format="json")
    assert r.status_code == 200, r.content
    pw = r.json()["password"]
    assert r.json()["store"]["owner"]["username"] == "p8owner" and len(pw) >= 12
    assert pw not in json.dumps(list(AuditLog.objects.values_list("detail", flat=True)), default=str)
    owner = Staff.objects.get(username="p8owner")
    old_tv = owner.token_version
    r2 = boss.post(ADMIN + "owner/", {}, format="json")                              # reset: a new password, sessions end
    owner.refresh_from_db()
    assert r2.json()["password"] != pw and owner.token_version == old_tv + 1
    assert boss.put(ADMIN + "ceiling/", {"codes": ["tickets.view", "agency.view"]}, format="json").status_code == 400
    r = boss.put(ADMIN + "ceiling/", {"codes": ["tickets.view", "tickets.reply"]}, format="json")
    assert r.status_code == 200 and r.json()["store"]["ceiling"] == ["tickets.reply", "tickets.view"]
    boss.defaults["HTTP_HOST"] = HOST                                                 # never from a store's own panel
    assert boss.put(ADMIN + "ceiling/", {"codes": list(S.STORE_CODES)}, format="json").status_code in (403, 404)


# ------------------------------------------------------------------ Telegram through the store's bot
def test_store_staff_link_and_get_ticket_dms_through_the_store_bot(store, monkeypatch):
    from apps.tickets import staff_link
    from apps.tickets.bot import staff_for

    owner, _ = _owner(store)
    with context.tenant_context(store.pk):
        code = staff_link.new_code(owner)
    assert staff_link.redeem(code, 8181) == "invalid"                    # in OUR bot: not ours to link
    with context.tenant_context(store.pk):
        code = staff_link.new_code(owner)
        assert staff_link.redeem(code, 8181) == "linked"
        assert staff_for(8181) == owner
    assert staff_for(8181) is None                                       # never in our bot
    sent = []
    monkeypatch.setattr("apps.telegram.config.sales_client",
                        lambda: type("B", (), {"send_message": lambda self, chat, text, **kw: sent.append(("store", chat))})())
    monkeypatch.setattr("apps.telegram.config.our_sales_client",
                        lambda: type("B", (), {"send_message": lambda self, chat, text, **kw: sent.append(("ours", chat))})())
    from apps.tickets.notify import _bot

    owner.refresh_from_db()
    with context.tenant_context(store.pk):
        from apps.tickets.models import Ticket, TicketTopic

        u = User.objects.create_user("p8cust", "Str0ngPass!")
        ticket = Ticket.objects.create(user=u, topic=TicketTopic.objects.create(name_fa="t", name_en="t"), subject="s")
        _bot(owner, ticket, "t", "b")
    assert sent and sent[-1] == ("store", 8181)


# ------------------------------------------------------------------ release gates
def test_store_codes_match_the_store_safe_views_and_hold_no_platform_code():
    from django.urls import URLPattern, URLResolver, get_resolver

    used = set()

    def walk(patterns):
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns)
            elif isinstance(p, URLPattern):
                cls = getattr(p.callback, "cls", None) or getattr(p.callback, "view_class", None)
                if cls is None or not getattr(cls, "store_ok", False):
                    continue
                for src in (getattr(cls, "perms_map", {}) or {}, getattr(cls, "action_perms", {}) or {}):
                    for v in src.values():
                        used.update(c for c in (v if isinstance(v, (list, tuple)) else [v]) if isinstance(c, str))

    walk(get_resolver().url_patterns)
    assert used <= S.STORE_CODES, f"a store page asks for a code a store can never hold: {sorted(used - S.STORE_CODES)}"
    platform = {"agency.manage", "agency.view", "agency.accounting", "agency.payments", "accounting.view", "settings.email",
                "users.purge", "bots.manage", "services.manage", "services.delete", "audit.view", "broadcast.send",
                "payments.manual_invoice"}          # v1.59: crm.* are store codes now (opt-in per store, OPT_IN_CODES)
    assert not (S.STORE_CODES & platform)
    assert not any(c.startswith("agency.") for c in S.STORE_CODES)


def test_signed_in_as_the_store_owner_no_endpoint_shows_our_data(store):
    User.objects.create_user(f"{OURS.lower()}user", "Str0ngPass!", name=f"{OURS} customer")
    Staff.objects.create(username=f"{OURS.lower()}staff", is_superadmin=True)
    Role.objects.create(name=f"{OURS}role")
    owner, _ = _owner(store)
    c = _client(owner, HOST)
    leaks, errors = [], []
    for url in _list_urls("/api/v1/admin/"):
        r = c.get(url)
        if r.status_code == 500:                     # 503 = an outside service (agency panel) not configured in tests
            errors.append((url, r.status_code))
        if r.status_code == 200 and (OURS.encode() in r.content or OURS.lower().encode() in r.content):
            leaks.append(url)
    assert not leaks, f"our data visible to a store owner: {leaks}"
    assert not errors, errors
