"""Runtime access to the `setting` key-value table with safe fallbacks."""
from __future__ import annotations

from typing import Any

from .models import Setting


def get_setting(key: str, default: Any = None) -> Any:
    try:
        from .branding import store_setting

        found, value = store_setting(key)              # v1.43: a reseller store's own value (TENANT_KEYS only)
        if found:
            return value
    except Exception:  # noqa: BLE001
        pass
    try:
        return Setting.objects.get(key=key).typed
    except Setting.DoesNotExist:
        return default
    except Exception:  # noqa: BLE001 - never let config reads crash a request
        return default


class StoreSettingRefused(PermissionError):
    """v1.51: code running for a reseller store tried to change one of OUR global settings."""


def set_setting(key: str, value: Any, value_type: str = "str") -> Setting:
    """Our global setting — or, inside a reseller store (v1.51, multi-tenant Phase 7), that STORE's own value for a key in
    `branding.TENANT_KEYS`. Any other key from a store context is refused: a store can never change our settings."""
    from .branding import TENANT_KEYS, is_store, set_store_setting

    if is_store():
        if key not in TENANT_KEYS:
            raise StoreSettingRefused(f"{key} is not a store setting")
        return set_store_setting(key, value, value_type)
    obj, _ = Setting.objects.update_or_create(
        key=key, defaults={"value": str(value), "value_type": value_type}
    )
    return obj
