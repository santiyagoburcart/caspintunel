"""v1.60: stores follow OUR theme (docs/multi-tenant.md §5).

A store never manages themes: `themes.manage` is not a store code and the theme API is not `store_ok`. What a store's
customers see = `store_theme()`: the override our staff set on «فروشگاه» (`TenantBranding.theme`, only one of OUR themes —
built-in or ours, never a store's own), else the theme active on our platform right now — so when we switch ours every
store follows (the public cache version is bumped by the theme save signal).
"""
from __future__ import annotations

from django.db.models import Q


def _ours_q():
    from apps.tenancy.context import default_tenant_id

    return Q(tenant__isnull=True) | Q(tenant_id=default_tenant_id())


def our_themes():
    from .models import Theme

    return Theme.objects.filter(_ours_q()).order_by("name")


def platform_theme():
    """The theme active on our own store (caspintunel.com)."""
    from .models import Theme

    return (Theme.objects.filter(_ours_q(), is_active=True).first()
            or Theme.objects.filter(_ours_q()).order_by("id").first())


def store_override():
    """The current store's override (one of our themes) or None = follow ours."""
    from .branding import store_branding

    b = store_branding()
    if b.theme_id and our_themes().filter(pk=b.theme_id).exists():
        return b.theme
    return None


def store_theme():
    return store_override() or platform_theme()


class ThemeRefused(Exception):
    def __init__(self, en: str, fa: str):
        super().__init__(en)
        self.en, self.fa = en, fa


def store_row(tenant) -> dict:
    """«پوسته» on «فروشگاه» (our staff): follow ours, or the chosen override."""
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant.pk):
        o = store_override()
    p = platform_theme()
    return {"override": o.id if o else None, "follows": o is None,
            "platform": {"id": p.id, "name": p.name} if p else None,
            "options": [{"id": t.id, "name": t.name} for t in our_themes()]}


def set_store_override(tenant, theme_id, *, staff=None) -> dict:
    """Our staff only. None / '' = follow our theme again."""
    from apps.common.models import write_audit
    from apps.tenancy.context import tenant_context

    from .branding import store_branding

    theme = None
    if theme_id not in (None, "", 0, "0"):
        theme = our_themes().filter(pk=theme_id).first()
        if theme is None:
            raise ThemeRefused("only one of our own themes can be set for a store",
                               "فقط یکی از پوسته‌های پلتفرم ما را می‌توان برای فروشگاه انتخاب کرد")
    with tenant_context(tenant.pk):
        b = store_branding()
        before = b.theme_id
        b.theme = theme
        b.save(update_fields=["theme", "updated_at"])
    write_audit(action="store.theme", staff=staff, target=tenant,
                detail={"tenant": tenant.pk, "before": before, "after": theme.id if theme else None, "follows": theme is None})
    return store_row(tenant)
