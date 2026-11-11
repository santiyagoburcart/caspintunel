"""Store plans (multi-tenant Phase 4, docs/multi-tenant.md §5 `plans`). A reseller sets their own plans and prices in their
store panel; what a store plan may use is bounded by the reseller's PasarGuard admin:

  * panel  = the agency panel (where the reseller's admin lives and `set_owner` points to) — never another one;
  * groups = what the reseller's admin ROLE allows (`RoleAccess.allowed_group_ids`; null = every group), read live and
             cached 5 minutes;
  * volume = an unlimited plan only when the reseller itself is unlimited (its volume cannot be reserved otherwise).

Our own store (the default tenant) is unchanged.
"""
from __future__ import annotations

import logging

from django.core.cache import cache

from . import context

log = logging.getLogger("caspintunel")
TTL = 300


class CatalogError(Exception):
    def __init__(self, en: str, fa: str, field: str | None = None):
        super().__init__(en)
        self.en, self.fa, self.field = en, fa, field


def current_store():
    from .models import Tenant

    tid = context.current_tenant_id()
    t = Tenant.objects.filter(pk=tid).first() if tid else None
    return None if t is None or t.is_default else t


def store_panel():
    from apps.agency.panel_api import agency_panel

    return agency_panel()


def allowed_groups(tenant) -> dict:
    """{'all': bool, 'groups': [{id, name}]} for the reseller's admin role (live, cached 5 min)."""
    key = f"tenancy:catalog:groups:{tenant.pk}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    from apps.agency import admin_crud

    panel = store_panel()
    opts = admin_crud.options(panel)
    admin = admin_crud.get_admin(panel, tenant.reseller_username)
    role_id = (admin.get("role") or {}).get("id")
    role = next((r for r in opts["roles"] if r["id"] == role_id), None)
    names = {g["id"]: g["name"] for g in opts["groups"]}
    if role is None or role["all_groups"]:
        out = {"all": True, "groups": opts["groups"]}
    else:
        allowed = {n for n in role["groups"]}
        out = {"all": False, "groups": [{"id": i, "name": n} for i, n in names.items() if n in allowed]}
    cache.set(key, out, TTL)
    return out


def options() -> dict:
    """What the store panel's plan form may use (GET /admin/plans/store-options/)."""
    from . import quota

    t = current_store()
    if t is None:
        raise CatalogError("only on a store's domain", "فقط در پنل فروشگاه")
    panel = store_panel()
    try:
        g = allowed_groups(t)
    except Exception as exc:  # noqa: BLE001 — the panel is down: the form still opens, groups unknown
        log.warning("store plan options: groups of %s unavailable: %s", t.reseller_username, exc)
        g = {"all": False, "groups": [], "error": str(exc)[:200]}
    pa = quota.reseller_of(t)
    try:                                       # v1.55: which of the reseller's groups are WireGuard groups
        from apps.panel.wireguard import group_kinds

        kinds = group_kinds(panel)
        g["groups"] = [{**x, "wireguard": bool(kinds.get(int(x["id"]), {}).get("wireguard"))} for x in g["groups"]]
    except Exception:  # noqa: BLE001
        pass
    return {"panel": {"id": panel.id, "name": panel.name}, "groups": g["groups"], "all_groups": g["all"],
            "groups_error": g.get("error", ""), "unlimited_ok": not quota.limited(pa)}


def validate_plan(attrs: dict, instance=None) -> dict:
    """Store plan create / update: force the agency panel, check groups and volume. Returns attrs (panel set)."""
    from apps.plans.models import PlanType

    from . import quota

    t = current_store()
    if t is None:
        return attrs
    panel = store_panel()
    want_panel = attrs.get("panel") or (instance.panel if instance else None)
    if want_panel is not None and want_panel.pk != panel.pk:
        raise CatalogError("a store plan uses the agency panel only", "پلن فروشگاه فقط روی پنل نمایندگی است", "panel")
    attrs["panel"] = panel
    groups = attrs.get("group_ids", instance.group_ids if instance else [])
    if groups:
        try:
            g = allowed_groups(t)
        except Exception as exc:  # noqa: BLE001
            raise CatalogError(f"the reseller's allowed groups could not be read: {exc}",
                               "گروه‌های مجاز نماینده خوانده نشد — کمی بعد دوباره امتحان کنید", "group_ids") from exc
        if not g["all"]:
            ok = {x["id"] for x in g["groups"]}
            bad = [i for i in groups if int(i) not in ok]
            if bad:
                raise CatalogError(f"groups {bad} are not allowed for this reseller",
                                   "این گروه‌ها برای نقش این نماینده مجاز نیست", "group_ids")
    ptype = attrs.get("type", instance.type if instance else PlanType.FIXED)
    limit = attrs.get("data_limit", instance.data_limit if instance else None)
    if ptype != PlanType.CUSTOM_VOLUME and not limit and quota.limited(quota.reseller_of(t)):
        raise CatalogError("an unlimited plan needs an unlimited reseller", "پلن حجم نامحدود برای این فروشگاه مجاز نیست",
                           "data_limit")
    return attrs
