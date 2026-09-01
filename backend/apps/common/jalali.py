"""
Jalali (Shamsi) helpers for the presentation layer.

Rule: store UTC everywhere, convert to Jalali only when displaying.
"""
from __future__ import annotations

from datetime import date, datetime

import jdatetime
from django.utils import timezone

TEHRAN_TZ = "Asia/Tehran"


def to_jalali_str(value: datetime | date | None, fmt: str = "%Y/%m/%d %H:%M") -> str:
    """Format an aware/naive datetime (or date) as a Jalali string."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value, timezone.get_fixed_timezone(0))
        jd = jdatetime.datetime.fromgregorian(datetime=value)
    else:
        jd = jdatetime.date.fromgregorian(date=value)
    return jd.strftime(fmt)


def jalali_now(fmt: str = "%Y/%m/%d %H:%M") -> str:
    return to_jalali_str(timezone.now(), fmt)
