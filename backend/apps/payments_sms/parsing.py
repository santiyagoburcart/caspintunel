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
4. the UNIT is read from the SMS — ریال / تومان (also Rial, IRR, Toman, IRT) on
   the amount's line, else in the whole SMS if it names only one unit — and the
   amount is converted to tomans exactly once. If the SMS names no unit (or
   both), the unit configured on the bank number (SmsSource.amount_unit) is
   used. Never both units, never a guess: 175,662 Rial is 17,566.2 Toman and
   matches no invoice.

Formats covered by tests: Bank Resalat (multi-line and one-line), Blu (Saman),
generic «واریز … ریال» lines.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
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
        if token.count(".") >= 2 and not re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):
            continue                       # account numbers 10.1234567.1 (1.750.000 is an amount)
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


RIAL, TOMAN = "rial", "toman"
_RIAL_RE = re.compile(r"ریال|\b(?:rials?|irr)\b", re.I)
_TOMAN_RE = re.compile(r"تومان|تومن|\b(?:tomans?|irt)\b", re.I)


def unit_in(text: str) -> str | None:
    """RIAL / TOMAN when the text names exactly one unit, else None."""
    t = normalize_digits(text)
    r, m = bool(_RIAL_RE.search(t)), bool(_TOMAN_RE.search(t))
    return RIAL if r and not m else TOMAN if m and not r else None


@dataclass(frozen=True)
class SmsAmount:
    """The deposit of one SMS: the number as written, its unit, where the unit
    came from ("sms" or "source" = the bank number's setting) and the EXACT
    amount in tomans (fractional when a rial amount is not a multiple of 10)."""
    raw: int
    unit: str
    unit_from: str
    toman: Decimal

    @property
    def whole(self) -> bool:
        return self.toman == self.toman.to_integral_value()

    def describe(self) -> str:
        unit = "Rial" if self.unit == RIAL else "Toman"
        src = "" if self.unit_from == "sms" else " (unit from the bank-number setting)"
        if self.unit == RIAL:
            return f"{self.raw:,} {unit} = {self.toman.normalize():,f} T{src}"
        return f"{self.raw:,} {unit}{src}"


def _deposit_entries(text: str) -> list[tuple[int, str]]:
    """(number as written, the text of its line before any balance) for every
    plausible deposit amount, best first. Empty for a withdrawal-only SMS."""
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
        (primary if (dep or hint) else other).extend((n, part) for n in nums)
    seen, out = set(), []
    # a clear deposit-line amount wins; other numbers are only a fallback
    for n, part in (primary or other):
        if n not in seen:
            seen.add(n)
            out.append((n, part))
    return out


def deposit_amounts(text: str) -> list[int]:
    """Raw numbers (as written in the SMS) that are plausibly the deposited amount,
    best first. Empty for a withdrawal-only SMS."""
    return [n for n, _ in _deposit_entries(text)]


def extract_numbers(text: str) -> list[int]:
    """Kept for callers/tests: every amount-like number (deposit lines first)."""
    return deposit_amounts(text)


def deposit_amount(text: str, source_unit: str = RIAL) -> SmsAmount | None:
    """THE deposit of this SMS, converted to tomans with an explicit unit:
    the unit on the amount's line, else the only unit the SMS names, else
    `source_unit` (the bank number's setting). None when there is no deposit."""
    entries = _deposit_entries(text)
    if not entries:
        return None
    raw, line = entries[0]
    unit, origin = unit_in(line), "sms"
    if unit is None:
        unit = unit_in(text)
    if unit is None:
        unit, origin = (TOMAN if source_unit == TOMAN else RIAL), "source"
    toman = Decimal(raw) / 10 if unit == RIAL else Decimal(raw)
    return SmsAmount(raw=raw, unit=unit, unit_from=origin, toman=toman)
