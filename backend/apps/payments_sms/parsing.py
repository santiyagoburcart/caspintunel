"""
Extract candidate payment amounts from a bank deposit SMS.

Iranian bank SMS often quote **rials** while our invoices are in **tomans**
(1 toman = 10 rials), and use Persian/Arabic digits with a variety of
thousands separators — so for every number found we offer both the raw value
and value/10 as candidates, and let the matcher decide.
"""
from __future__ import annotations

import re
from decimal import Decimal

# Persian (U+06F0..) and Arabic-Indic (U+0660..) digits -> ASCII
_DIGIT_TRANS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)

# digits, optionally grouped by comma / Arabic comma / Arabic thousands mark / dot
_NUMBER_RE = re.compile(r"\d[\d.,٬،]*\d|\d")

_MIN_DIGITS = 4   # >= 1,000  (ignore card suffixes, dates, small counts)
_MAX_DIGITS = 12


def normalize_digits(text: str) -> str:
    return (text or "").translate(_DIGIT_TRANS)


def extract_numbers(text: str) -> list[int]:
    text = normalize_digits(text)
    values: list[int] = []
    for match in _NUMBER_RE.finditer(text):
        token = match.group(0)
        # drop a trailing decimal part like ".00" (rare in IRR/IRT SMS)
        token = re.sub(r"\.\d{1,2}$", "", token)
        digits = re.sub(r"\D", "", token)
        if _MIN_DIGITS <= len(digits) <= _MAX_DIGITS:
            values.append(int(digits))
    return values


def candidate_amounts(text: str) -> set[Decimal]:
    """Every plausible toman amount the SMS could be referring to."""
    out: set[Decimal] = set()
    for n in extract_numbers(text):
        out.add(Decimal(n))
        if n % 10 == 0:
            out.add(Decimal(n // 10))  # rial -> toman
    return out
