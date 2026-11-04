"""The `tenant` column of tenant tables — kept free of project imports so any app's models.py can use it."""
from django.db import models


def tenant_fk(**extra):
    """Nullable during Phase 1 Release A/B (backfilled with the default tenant); NOT NULL from Release C except the
    models in registry.NULLABLE (where NULL = platform). PROTECT: a tenant with data can't be deleted by accident."""
    return models.ForeignKey("tenancy.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                             editable=False, **extra)
