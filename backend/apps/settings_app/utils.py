"""Runtime access to the `setting` key-value table with safe fallbacks."""
from __future__ import annotations

from typing import Any

from .models import Setting


def get_setting(key: str, default: Any = None) -> Any:
    try:
        return Setting.objects.get(key=key).typed
    except Setting.DoesNotExist:
        return default
    except Exception:  # noqa: BLE001 - never let config reads crash a request
        return default


def set_setting(key: str, value: Any, value_type: str = "str") -> Setting:
    obj, _ = Setting.objects.update_or_create(
        key=key, defaults={"value": str(value), "value_type": value_type}
    )
    return obj
