"""Sign-in backend for customers (Release C, v1.42.0): usernames are unique per store, not globally.

Django's ModelBackend looks the user up with `User._default_manager.get_by_natural_key(username)`; that manager is
tenant-scoped (apps/tenancy/scoping.py), so the lookup only sees the current store's customers and the per-store unique
constraint `user_tenant_username` keeps it to one row. Nothing else changes — this subclass exists so Django accepts a
non-unique USERNAME_FIELD (auth.E003 → the silenced auth.W004).
"""
from django.contrib.auth.backends import ModelBackend


class TenantModelBackend(ModelBackend):
    pass
