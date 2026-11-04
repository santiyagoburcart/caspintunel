"""Scoping of tenant tables (Phase 1 Release B), installed by TenancyConfig.ready() on every model in registry.TENANT:

- the default manager's class gets `TenantScopedMixin`: every queryset is filtered to the current tenant
  (`tenant_id = current`), `bulk_create` fills the tenant on new objects;
- a `pre_save` handler fills `tenant` on new rows from the current tenant (rows never land without one).

The model's own manager / queryset (e.g. `Payment.objects.live()`, `UserManager.create_user`) keeps working: the mixin
sits in front of the original class. Related managers (`user.orders`) are scoped too, which is harmless — a parent row
already belongs to the current tenant. NULLABLE models (staff, roles, audit, push, themes) are not scoped here.
"""
from __future__ import annotations

from django.db.models import ForeignKey, Lookup
from django.db.models.signals import pre_save

from . import context


@ForeignKey.register_lookup
class TenantScope(Lookup):
    """`tenant__tenant_scope=True`: the tenant is read when the SQL is COMPILED, not when the queryset is built. DRF views
    build `queryset = Model.objects.all()` once at import and clone it per request — a plain `filter(tenant_id=…)` would
    freeze the tenant of import time. Unscoped → `1 = 1` (every row, NULL tenants included)."""

    lookup_name = "tenant_scope"
    prepare_rhs = False
    can_use_none_as_rhs = True

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        tid = context.current_tenant_id()
        if tid is None:
            return "1 = 1", []
        return f"{lhs} = %s", [*lhs_params, tid]


class TenantScopedMixin:
    def get_queryset(self):
        return super().get_queryset().filter(tenant__tenant_scope=True)

    def bulk_create(self, objs, *args, **kwargs):
        tid = None if context.is_unscoped() else context.current_tenant_id()
        for o in objs:
            if getattr(o, "tenant_id", None) is None and tid is not None:
                o.tenant_id = tid
        return super().bulk_create(objs, *args, **kwargs)

    def __copy__(self):
        """Migration state (ModelState.from_model) copies managers: hand it the plain original, so the autodetector never
        sees a "managers changed" difference. The live managers (already in Options.managers) stay scoped."""
        orig = type(self)._tenancy_original
        plain = orig.__new__(orig)
        plain.__dict__ = self.__dict__.copy()
        return plain

    def deconstruct(self):
        """Migrations serialize managers with use_in_migrations (UserManager): describe the original class — the
        scoping is a runtime layer, not part of the schema."""
        orig = type(self)._tenancy_original
        plain = orig.__new__(orig)
        plain.__dict__ = self.__dict__.copy()
        return orig.deconstruct(plain)


def _fill_tenant(sender, instance, raw=False, **kwargs):
    if raw or getattr(instance, "tenant_id", None) is not None or context.is_unscoped():
        return
    tid = context.current_tenant_id()
    if tid is not None:
        instance.tenant_id = tid


_installed: set[str] = set()


def install(models) -> None:
    for model in models:
        label = model._meta.label
        if label in _installed:
            continue
        for mgr in {model._default_manager, *model._meta.managers}:
            cls = mgr.__class__
            if not issubclass(cls, TenantScopedMixin):
                mgr.__class__ = type(f"TenantScoped{cls.__name__}", (TenantScopedMixin, cls), {"_tenancy_original": cls})
        pre_save.connect(_fill_tenant, sender=model, dispatch_uid=f"tenancy_fill:{label}", weak=False)
        _installed.add(label)
