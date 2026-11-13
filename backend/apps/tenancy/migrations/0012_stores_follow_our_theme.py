"""v1.60: stores no longer manage themes — `themes.manage` leaves every store's ceiling and roles, and every store goes back
to following our active theme (TenantBranding.theme = NULL; only our staff set an override on «فروشگاه» from now on).
Prints what it changed (shown by update.sh)."""
from django.db import migrations


def forwards(apps, schema_editor):
    Tenant = apps.get_model("tenancy", "Tenant")
    Role = apps.get_model("accounts", "Role")
    TenantBranding = apps.get_model("settings_app", "TenantBranding")
    ceilings, roles, themes = [], [], []
    for t in Tenant.objects.filter(is_default=False):
        codes = list(t.permission_ceiling or [])
        if "themes.manage" in codes:
            t.permission_ceiling = sorted(c for c in codes if c != "themes.manage")
            t.save(update_fields=["permission_ceiling"])
            ceilings.append(t.slug)
    for r in Role.objects.filter(tenant__isnull=False, tenant__is_default=False, permissions__code="themes.manage").distinct():
        r.permissions.remove(*r.permissions.filter(code="themes.manage"))
        roles.append(f"{r.tenant_id}:{r.name}")
    # _base_manager: the plain manager — the scoped one would only see the default tenant here
    for b in TenantBranding._base_manager.filter(tenant__is_default=False, theme__isnull=False):
        themes.append(f"{b.tenant_id}:{b.theme_id}")
        b.theme = None
        b.save(update_fields=["theme"])
    print(f"\n  stores: themes.manage removed from ceilings {ceilings or 'none'} · roles {roles or 'none'}"
          f" · now following our theme (was tenant:theme) {themes or 'none'}")


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0011_tenantdomain_stage"),
        ("accounts", "0019_role_name_per_store"),
        ("settings_app", "0020_tenantbranding_support_email"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
