"""Panel navigation on phones (v1.30.4).

Phones have no ☰ / drawer: navigation = bottom tabs + the Settings tab, which lists every
sidebar page (components/adminNav.js → pages/Settings.jsx) filtered by permission. These
tests read the panel source (mounted read-only by docker-compose.test.yml) and check:
- every panel route is reachable from the menu (a page, or a sub-page of one);
- every menu permission exists, and the page's own API answers a staff member holding
  exactly that permission (tile shown ⇒ page opens) and refuses one without it (403);
- the phone top bar has no menu button and the rail is hidden on phones;
- a group manager reaches every page of its menu from its bottom bar.
"""
import re
from pathlib import Path

import pytest

from apps.accounts.models import Permission, Role, Staff
from apps.settings_app.management.commands.seed import PERMISSIONS

SRC = Path("/app/frontend_admin_src")
pytestmark = pytest.mark.skipif(not SRC.is_dir(), reason="panel source not mounted")
ITEM = re.compile(r"\['(/[^']*)',\s*'([a-z_]+)',\s*(null|'[a-z_.]+'|\[[^\]]*\])")


def _read(rel):
    return (SRC / rel).read_text(encoding="utf-8")


def _block(src, name):
    start = src.index(f"export const {name} = [")
    depth, i = 0, src.index("[", start)
    for j in range(i, len(src)):
        depth += {"[": 1, "]": -1}.get(src[j], 0)
        if depth == 0:
            return src[i:j + 1]
    raise AssertionError(name)


def _items(name):
    def perm(p):   # null → None, 'a' → 'a', ['a', 'b'] → ('a', 'b') = all of them
        return None if p == "null" else tuple(re.findall(r"'([a-z_.]+)'", p)) if p.startswith("[") else p.strip("'")
    return [(to, key, perm(p)) for to, key, p in ITEM.findall(_block(_read("components/adminNav.js"), name))]


def _staff_routes():
    app = _read("App.jsx")
    staff_part = app[app.index("  return (\n    <Routes>"):]
    return [p for p in re.findall(r'<Route path="([^"]+)"', staff_part) if p not in ("/login", "*", "/my-groups/*")]


# --- 1. every route is reachable --------------------------------------------------
def test_every_staff_route_is_reachable_from_the_menu():
    menu = {to for to, _, _ in _items("CASPIAN_GROUPS")} | {"/users/deleted"}   # + the hub's Users extra
    missing = []
    for route in _staff_routes():
        static = route.split("/:")[0] or "/"
        # a page in the menu, or a sub-page (detail / tab) of one — reached from that page
        parents = ["/" + "/".join(static.strip("/").split("/")[:n]) for n in range(1, static.count("/") + 1)]
        if static not in menu and not any(p in menu for p in parents):
            missing.append(route)
    assert not missing, f"routes with no menu entry on phones: {missing}"


def test_settings_tab_lists_every_menu_page_and_the_account_block():
    hub = _read("pages/Settings.jsx")
    assert "items.filter(([to]) => to !== SELF)" in hub and "const SELF = '/settings'" in hub
    assert "BOTTOM_TABS" not in hub                       # bottom-tab pages (e.g. Services) are listed too
    for needle in ('data-testid="hub-account"', "setLang", "toggle()", "logout()", "roleText(staff, lang)"):
        assert needle in hub, needle
    # every hub page has its fa + en text (a missing key would crash the tab)
    keys = {"panel_link": "panel", "email_settings": "email", "domain_cf": "domain"}
    for to, key, _ in _items("CASPIAN_GROUPS"):
        if to == "/settings":
            continue
        k = keys.get(key, key)
        assert hub.count(f"    {k}: {{ t: ") >= 2, f"Settings hub has no fa/en text for {to} ({k})"


# --- 2. permissions: tile shown ⇔ page opens ----------------------------------------
def test_every_menu_permission_exists():
    known = {code for code, _ in PERMISSIONS} | {None, "superadmin"}
    for name in ("CASPIAN_GROUPS", "CASPIAN_BOTNAV", "GM_GROUPS", "GM_BOTNAV"):
        for to, _, perm in _items(name):
            for code in (perm if isinstance(perm, tuple) else (perm,)):
                assert code in known, (name, to, code)


PAGE_API = {   # menu route → the API its page loads first (a tuple: every call the page makes)
    "/monitoring": "/api/v1/admin/monitoring/", "/panel-link": "/api/v1/admin/panels/",
    "/users": "/api/v1/admin/users/", "/agency": "/api/v1/admin/agency/settings/",
    "/tickets": "/api/v1/admin/tickets/", "/crm": "/api/v1/admin/crm/reasons/",
    "/services": "/api/v1/admin/services/", "/plans": "/api/v1/admin/plans/",
    "/payments": "/api/v1/admin/payments/pending/", "/transactions": "/api/v1/admin/transactions/",
    "/sms-log": "/api/v1/admin/sms-log/", "/accounting": "/api/v1/admin/accounting/",
    "/cards": "/api/v1/admin/cards/",
    "/discounts": "/api/v1/admin/discounts/", "/branding": "/api/v1/admin/branding/",
    "/settings": "/api/v1/admin/settings/", "/settings/email": "/api/v1/admin/email/",
    "/settings/paths": "/api/v1/admin/paths/", "/settings/domain": "/api/v1/admin/domain/",
    "/bots": "/api/v1/admin/integrations/telegram/", "/apps": "/api/v1/admin/apps/",
    "/notifications": "/api/v1/admin/notifications/", "/pages": "/api/v1/admin/pages/",
    "/themes": "/api/v1/admin/themes/", "/roles": "/api/v1/admin/roles/",
    "/tickets/topics": ("/api/v1/admin/tickets/topics/", "/api/v1/admin/tickets/settings/", "/api/v1/admin/tickets/canned/?all=1"),
    "/analytics": ("/api/v1/admin/crm/analytics/overview/",), "/docs": "/api/v1/admin/docs/",
}


def _staff_with(codes, name):
    role = Role.objects.create(name=f"nav-{name}")
    role.permissions.set([Permission.objects.get_or_create(code=c, defaults={"name": c})[0] for c in codes])
    s = Staff(username=f"nav_{name}"[:30], role=role)
    s.set_password("Str0ngPass!")
    s.save()
    return s


@pytest.mark.django_db
def test_each_menu_page_opens_with_exactly_its_permission_and_not_without(staff_client):
    items = [i for i in _items("CASPIAN_GROUPS") if i[0] != "/"]
    assert {to for to, _, _ in items} == set(PAGE_API), "a menu page has no API mapping in this test"
    nobody = staff_client(_staff_with([], "none"))
    clients = {}

    def holder(perm):                                       # one staff member per permission
        if perm not in clients:
            codes = [c for c, _ in PERMISSIONS] if perm == "superadmin" else list(perm) if isinstance(perm, tuple) else [perm]
            clients[perm] = staff_client(_staff_with(codes, "_".join(codes).replace(".", "_")[:40] if perm != "superadmin" else "all"))
        return clients[perm]

    for to, _, perm in items:
        urls = PAGE_API[to] if isinstance(PAGE_API[to], tuple) else (PAGE_API[to],)
        for url in urls:
            if perm == "superadmin":                        # no role grants it, not even every permission
                assert holder(perm).get(url).status_code == 403, to
                continue
            r = holder(perm).get(url)
            assert r.status_code != 403, f"{to}: tile shown with {perm} but {url} answers 403"
            assert nobody.get(url).status_code == 403, f"{to}: {url} opens without {perm}"
        if isinstance(perm, tuple):                         # all of them are needed: with one alone a call fails
            for code in perm:
                assert any(holder(code).get(u).status_code == 403 for u in urls), f"{to}: works with only {code}"


# --- 3. phone shell: no ☰, no drawer ----------------------------------------------------
def test_phone_top_bar_has_no_menu_button_and_no_drawer():
    lay = _read("components/Layout.jsx")
    mtop = lay[lay.index('<header className="csp-mtop">'):lay.index("</header>", lay.index('<header className="csp-mtop">'))]
    assert "MenuButton" not in mtop and "☰" not in mtop
    assert 'data-testid="avatar"' in mtop and "!inner && (" not in mtop.split('data-testid="avatar"')[0][-200:]
    assert "@media (max-width: 767px) { .csp-rail, .csp-backdrop { display: none !important; } }" in lay


def test_group_manager_reaches_every_menu_page_from_the_bottom_bar():
    menu = {to for to, _, _ in _items("GM_GROUPS")}
    bottom = {to for to, _, _ in _items("GM_BOTNAV")}
    assert menu <= bottom and "/my-groups/settings" in bottom
