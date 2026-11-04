"""
Jalali (Shamsi) helpers for the presentation layer.

Rule: store UTC everywhere, convert to Jalali only when displaying.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import jdatetime
from django.utils import timezone

TEHRAN_TZ = "Asia/Tehran"
TZ = ZoneInfo(TEHRAN_TZ)


# ---- v1.38.3 day boundaries: a "day" in reports and filters is a TEHRAN calendar day (the server runs in UTC)
def tehran_day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=TZ)


def tehran_day_end(d: date) -> datetime:
    """Last microsecond of that Tehran day (for __lte filters)."""
    return tehran_day_start(d + timedelta(days=1)) - timedelta(microseconds=1)


def tehran_today() -> date:
    return timezone.now().astimezone(TZ).date()


def parse_day(value) -> date | None:
    """A Jalali (1405/08/13) or ISO (2026-11-04) date string → that calendar date (Gregorian)."""
    if not value:
        return None
    value = str(value).strip()
    try:
        if "/" in value:
            y, m, d = (int(x) for x in value.split("/"))
            return jdatetime.date(y, m, d).togregorian()
        y, m, d = (int(x) for x in value[:10].split("-"))
        return date(y, m, d)
    except (ValueError, TypeError):
        return None


def today_bounds() -> tuple[datetime, datetime]:
    d = tehran_today()
    return tehran_day_start(d), tehran_day_end(d)


def jalali_month_bounds(day: date | None = None) -> tuple[datetime, datetime]:
    """The Jalali month containing `day` (default: today in Tehran), as Tehran day boundaries."""
    jd = jdatetime.date.fromgregorian(date=day or tehran_today())
    first = jdatetime.date(jd.year, jd.month, 1)
    nxt = jdatetime.date(jd.year + (jd.month == 12), jd.month % 12 + 1, 1)
    return tehran_day_start(first.togregorian()), tehran_day_end(nxt.togregorian() - timedelta(days=1))


def jalali_day(value: date | datetime) -> str:
    """1405/08/13 for a date, or for an aware datetime in Tehran time."""
    if isinstance(value, datetime):
        value = value.astimezone(TZ).date() if timezone.is_aware(value) else value.date()
    return jdatetime.date.fromgregorian(date=value).strftime("%Y/%m/%d")


def to_jalali_str(value: datetime | date | None, fmt: str = "%Y/%m/%d %H:%M") -> str:
    """Format an aware/naive datetime (or date) as a Jalali string."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        if timezone.is_aware(value):            # v1.38.3: Tehran time (was UTC — 3½ h off)
            value = value.astimezone(TZ).replace(tzinfo=None)
        jd = jdatetime.datetime.fromgregorian(datetime=value)
    else:
        jd = jdatetime.date.fromgregorian(date=value)
    return jd.strftime(fmt)


def jalali_now(fmt: str = "%Y/%m/%d %H:%M") -> str:
    return to_jalali_str(timezone.now(), fmt)
