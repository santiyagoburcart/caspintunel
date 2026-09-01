from datetime import datetime, timezone

from apps.common.jalali import to_jalali_str


def test_known_gregorian_to_jalali():
    # 2024-03-20 is 1403-01-01 (Nowruz)
    dt = datetime(2024, 3, 20, 6, 0, tzinfo=timezone.utc)
    assert to_jalali_str(dt, "%Y/%m/%d").startswith("1403/01/01")


def test_none_is_empty_string():
    assert to_jalali_str(None) == ""
