"""
Extract the deposit amount from a bank SMS.

Iranian bank SMS quote **rials** or **tomans** (our invoices are tomans,
1 toman = 10 rials), use Persian / Arabic / Latin digits with several
thousands separators, and carry other numbers too: the account balance
(مانده / موجودی), account and card numbers, dates, times and reference
codes. So:

1. digits are normalized to ASCII and Arabic ي/ك to Persian ی/ک;
2. numbers that are clearly not an amount are dropped: account numbers
   (`10.1234567.1`), card numbers (16+ digits), dates/times (next to `/` or `:`),
   and anything on a balance / account / card / date / reference line;
3. numbers on a **deposit** line (واریز, بستانکار, انتقال به, دریافت, `+…`,
   مبلغ, …ریال/تومان) are preferred; an SMS that only reports a withdrawal
   (برداشت, خرید, `-…`) yields nothing;
4. every remaining number is offered both as-is and /10 (rial → toman).

Formats covered by tests: Bank Resalat (multi-line and one-line), Blu (Saman),
generic «واریز … ریال» lines.
"""
from __future__ import annotations

import re
from decimal import Decimal

# Persian (U+06F0..) and Arabic-Indic (U+0660..) digits -> ASCII; Arabic yeh/kaf -> Persian
_DIGIT_TRANS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك",
    "01234567890123456789یک",
)

# digits, optionally grouped by comma / Arabic comma / Arabic thousands mark / dot
_NUMBER_RE = re.compile(r"\d[\d.,٬،]*\d|\d")

_MIN_DIGITS = 4   # >= 1,000  (ignore card suffixes, dates, small counts)
_MAX_DIGITS = 12

# a deposit is announced by one of these (or a line starting with "+")
_DEPOSIT_STRONG = ("واریز", "بستانکار", "انتقال به", "دریافت", "افزایش", "deposit", "credit")
# amount hints: a number on such a line is likely the amount
_AMOUNT_HINT = ("مبلغ", "ریال", "تومان", "rial", "irr", "amount")
_WITHDRAW = ("برداشت", "خرید", "انتقال از", "کسر", "withdraw", "debit")
_BALANCE = ("مانده", "موجودی", "balance")                       # never the deposit amount
_META = ("شماره", "حساب", "کارت", "تاریخ", "ساعت", "پیگیری", "مرجع", "کد", "account", "card", "date", "ref")


def normalize_digits(text: str) -> str:
    return (text or "").translate(_DIGIT_TRANS)


def _numbers(line: str) -> list[int]:
    out = []
    for m in _NUMBER_RE.finditer(line):
        token = m.group(0)
        before = line[m.start() - 1] if m.start() else ""
        after = line[m.end()] if m.end() < len(line) else ""
        if (before and before in "/:") or (after and after in "/:"):
            continue                       # dates 1405/07/18, times 18:05
        if token.count(".") >= 2:
            continue                       # account numbers 10.1234567.1
        token = re.sub(r"\.\d{1,2}$", "", token)   # trailing decimals like .00
        digits = re.sub(r"\D", "", token)
        if len(digits) >= 16:
            continue                       # card numbers
        if _MIN_DIGITS <= len(digits) <= _MAX_DIGITS:
            out.append(int(digits))
    return out


_CARD_RE = re.compile(r"\d{4}[\s-]?[\d*]{4}[\s-]?[\d*]{4}[\s-]?\d{4}")


def _lines(text: str) -> list[str]:
    text = _CARD_RE.sub(" ", normalize_digits(text))      # card numbers, full or masked
    return [ln.strip() for ln in re.split(r"[\n\r;|]+", text) if ln.strip()]


def _has(line: str, words) -> bool:
    low = line.lower()
    return any(w in low for w in words)


def _before_balance(line: str) -> str:
    """Text before the first balance word (one-line SMS put the balance last)."""
    low, cut = line.lower(), len(line)
    for w in _BALANCE:
        i = low.find(w)
        if i != -1:
            cut = min(cut, i)
    return line[:cut]


def deposit_amounts(text: str) -> list[int]:
    """Raw numbers (as written in the SMS) that are plausibly the deposited amount,
    best first. Empty for a withdrawal-only SMS."""
    lines = _lines(text)
    is_deposit = any(_has(ln, _DEPOSIT_STRONG) or ln.startswith("+") for ln in lines)
    is_withdraw = any(_has(ln, _WITHDRAW) or re.match(r"^-\s*\d", ln) for ln in lines)
    if is_withdraw and not is_deposit:
        return []
    primary, other = [], []
    for ln in lines:
        part = _before_balance(ln)
        nums = _numbers(part)
        if not nums:
            continue
        dep = _has(part, _DEPOSIT_STRONG) or part.startswith("+")
        hint = _has(part, _AMOUNT_HINT)
        if (_has(part, _WITHDRAW) or re.match(r"^-\s*\d", part)) and not dep:
            continue                                   # a withdrawal amount
        if _has(part, _META) and not (dep or hint):
            continue                                   # account / card / date / ref lines
        (primary if (dep or hint) else other).extend(nums)
    seen, out = set(), []
    # a clear deposit-line amount wins; other numbers are only a fallback
    for n in (primary or other):
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def extract_numbers(text: str) -> list[int]:
    """Kept for callers/tests: every amount-like number (deposit lines first)."""
    return deposit_amounts(text)


def candidate_amounts(text: str) -> set[Decimal]:
    """Every plausible toman amount the SMS could be referring to."""
    out: set[Decimal] = set()
    for n in deposit_amounts(text):
        out.add(Decimal(n))
        if n % 10 == 0:
            out.add(Decimal(n // 10))  # rial -> toman
    return out


def primary_amount_toman(text: str) -> Decimal | None:
    """The single most likely deposit amount, in tomans (for the SMS log)."""
    nums = deposit_amounts(text)
    if not nums:
        return None
    n = nums[0]
    norm = normalize_digits(text)
    rial = "ریال" in norm or "rial" in norm.lower() or "irr" in norm.lower()
    toman = "تومان" in norm
    if rial and not toman and n % 10 == 0:
        return Decimal(n // 10)
    return Decimal(n)
