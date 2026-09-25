"""The one place phone numbers are normalized and validated.

Every entry point — site registration, profile edit, admin user create/edit,
the Telegram contact share, the legacy importer — goes through here, so a
number is always stored the same way and "same phone" lookups (uniqueness,
bot ↔ site account merge) compare like with like:

    +98 910 732 3128 / 00989107323128 / 989107323128 / 9107323128 /
    ۰۹۱۰۷۳۲۳۱۲۸ / 0910-732-3128   ->   "09107323128"
"""
from __future__ import annotations

import re

# Persian (U+06F0..) and Arabic-Indic (U+0660..) digits -> ASCII
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
# separators people type or paste: spaces (incl. NBSP / ZWNJ), dashes, dots, parens
_SEPARATORS = re.compile(r"[\s ‌‏‎\-‐‑–—.()/]")
_IR_MOBILE = re.compile(r"^09\d{9}$")

IR_PHONE_ERROR_FA = "شماره موبایل باید ایرانی و با ۰۹ شروع شود (مثال: 09121234567)"
IR_PHONE_ERROR_EN = "The mobile number must be Iranian and start with 09 (e.g. 09121234567)"
IR_PHONE_ERROR = f"{IR_PHONE_ERROR_FA} / {IR_PHONE_ERROR_EN}"

PHONE_REQUIRED_ERROR = "شماره موبایل الزامی است / A mobile number is required"
PHONE_TAKEN_ERROR = "این شماره موبایل قبلاً ثبت شده است / This mobile number is already registered"
PHONE_TAKEN_BY_BOT_ERROR = (
    "این شماره قبلاً در ربات ثبت شده است؛ برای اتصال حساب‌ها، شماره را از داخل ربات ارسال کنید. / "
    "This number is already registered in the Telegram bot — to link the accounts, share the number from inside the bot."
)


def _clean(raw) -> str:
    return _SEPARATORS.sub("", str(raw or "").translate(_DIGITS))


def normalize_ir_phone(raw) -> str | None:
    """Canonical "09xxxxxxxxx" for a valid Iranian mobile number, else None."""
    s = _clean(raw)
    if not s:
        return None
    if s.startswith("+"):
        s = s[1:]
        if not s.startswith("98"):
            return None          # an explicit non-Iranian country code
    elif s.startswith("00"):
        s = s[2:]
        if not s.startswith("98"):
            return None
    if not s.isdigit():
        return None
    if s.startswith("98") and len(s) in (12, 13):
        rest = s[2:]                      # "+98 0912…" (redundant trunk zero) also seen
        s = rest if rest.startswith("0") else "0" + rest
    elif s.startswith("9") and len(s) == 10:
        s = "0" + s
    return s if _IR_MOBILE.match(s) else None


def normalize_phone(raw) -> str | None:
    """Storage form of any phone: the Iranian canonical form when it is one,
    otherwise "+<country><number>" for plausible international numbers.
    None when it isn't a phone number at all."""
    ir = normalize_ir_phone(raw)
    if ir:
        return ir
    s = _clean(raw)
    if s.startswith("00"):
        s = "+" + s[2:]
    digits = s[1:] if s.startswith("+") else s
    if not digits.isdigit() or not 8 <= len(digits) <= 15:
        return None
    return "+" + digits


def is_iranian(raw) -> bool:
    return normalize_ir_phone(raw) is not None


def iran_phone_only() -> bool:
    from apps.settings_app.utils import get_setting

    return bool(get_setting("iran_phone_only", True))


class PhoneError(ValueError):
    """Invalid / missing / taken phone. `code` is stable for API clients."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def phone_owner(phone: str, *, exclude_pk=None):
    """Another account already using this (normalized) phone, if any."""
    from django.contrib.auth import get_user_model

    qs = get_user_model().objects.filter(phone=phone)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.order_by("id").first()


def clean_site_phone(raw, *, required: bool | None = None, exclude_pk=None) -> str:
    """Validate + normalize a phone typed on the website (registration,
    profile) or by an admin. Returns the value to store ("" = none).

    - `iran_phone_only` on: must be a valid Iranian mobile; required on the
      site unless `required=False` is passed explicitly (admin forms).
    - Unique across accounts. A number already held by a Telegram-linked
      account is never merged from the site side (the site number is not
      verified) — the user is told to share it from inside the bot instead.
    """
    iran_only = iran_phone_only()
    if required is None:
        required = iran_only
    if not str(raw or "").strip():
        if required:
            raise PhoneError(PHONE_REQUIRED_ERROR, "phone_required")
        return ""
    value = normalize_ir_phone(raw) if iran_only else normalize_phone(raw)
    if not value:
        raise PhoneError(IR_PHONE_ERROR if iran_only else "شماره تلفن نامعتبر است / Invalid phone number",
                         "phone_invalid")
    owner = phone_owner(value, exclude_pk=exclude_pk)
    if owner is not None:
        if owner.telegram_id:
            raise PhoneError(PHONE_TAKEN_BY_BOT_ERROR, "phone_in_bot")
        raise PhoneError(PHONE_TAKEN_ERROR, "phone_taken")
    return value
