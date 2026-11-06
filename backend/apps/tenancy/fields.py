"""The `tenant` column of tenant tables — kept free of project imports so any app's models.py can use it."""
from django.db import models


def tenant_fk(null: bool = False, **extra):
    """NOT NULL since Release C (v1.42.0): every row of a tenant table belongs to one store (filled from the current
    tenant on save). `null=True` only for the models in registry.NULLABLE (NULL = platform: our staff, roles, audit,
    staff push, built-in themes). PROTECT: a tenant with data can't be deleted by accident. `blank=True` + not editable:
    forms and full_clean never ask for it — pre_save / bulk_create fill it."""
    return models.ForeignKey("tenancy.Tenant", null=null, blank=True, on_delete=models.PROTECT, related_name="+",
                             editable=False, **extra)
