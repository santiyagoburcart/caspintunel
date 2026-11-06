"""Account names (= PasarGuard usernames) — ONE rule for every form: site + Mini App checkout, the bot, renaming a paid
order, manual invoices, staff "new service", the provisioning retry, agency "create admin".

PasarGuard v5.6 (`app/models/validators.py::UserValidator.validate_username`): 3–128 characters, only `a-z A-Z 0-9 - _ @ .`,
and no two of `- _ @ .` next to each other. Our columns hold 64, so 3–64 here. Incident 2026-11-06: the bot accepted
"sahar 1364" (a space), PasarGuard answered 422 after the customer had paid and the service was never created.

The frontends carry the same rule (`lib/accountName.js` in both SPAs — keep the three copies in step).
"""
from __future__ import annotations

import re

MIN_LEN, MAX_LEN = 3, 64
_ALLOWED = re.compile(r"^[A-Za-z0-9_.@-]+$")
_SPECIAL = "_.@-"
_CONSECUTIVE = re.compile(r"[-_@.]{2,}")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

MESSAGES = {
    "required": ("نام اکانت را وارد کنید.", "Enter an account name."),
    "short": (f"نام اکانت باید حداقل {MIN_LEN} حرف باشد.", f"The account name needs at least {MIN_LEN} characters."),
    "long": (f"نام اکانت حداکثر {MAX_LEN} حرف است.", f"The account name can have at most {MAX_LEN} characters."),
    "space": ("نام اکانت نمی‌تواند فاصله داشته باشد؛ به جای فاصله _ بگذارید.",
              "The account name can't contain spaces — use _ instead."),
    "chars": ("نام اکانت فقط می‌تواند حروف انگلیسی، عدد و _ - . @ داشته باشد.",
              "Use only English letters, digits and _ - . @ in the account name."),
    "consecutive": ("دو علامت از _ - . @ نباید پشت سر هم بیایند.",
                    "Two of _ - . @ can't be next to each other."),
}


def problem(name: str | None) -> str | None:
    """The first rule `name` breaks (a MESSAGES key), or None when PasarGuard accepts it."""
    name = (name or "").strip()
    if not name:
        return "required"
    if any(ch.isspace() for ch in name):
        return "space"
    if not _ALLOWED.match(name):
        return "chars"
    if _CONSECUTIVE.search(name):
        return "consecutive"
    if len(name) < MIN_LEN:
        return "short"
    if len(name) > MAX_LEN:
        return "long"
    return None


def suggest(name: str | None) -> str | None:
    """A fixed version of `name` (spaces → _, Persian digits → Latin, other characters dropped, repeated symbols
    collapsed), or None when nothing usable is left or the name was already fine."""
    if problem(name) is None:
        return None
    raw = (name or "").strip().translate(_DIGITS)
    s = re.sub(r"\s+", "_", raw)
    s = "".join(ch for ch in s if ch.isascii() and (ch.isalnum() or ch in _SPECIAL))
    s = re.sub(r"[-_@.]{2,}", lambda m: m.group(0)[0], s)
    s = s.strip(_SPECIAL)[:MAX_LEN].strip(_SPECIAL)
    if not s or s == (name or "").strip() or problem(s) is not None:
        return None
    return s


class AccountNameInvalid(ValueError):
    def __init__(self, code: str, name: str = ""):
        self.code, self.name = code, name
        self.suggestion = suggest(name)
        super().__init__(MESSAGES[code][1])

    def message(self, lang: str = "fa", *, with_suggestion: bool = False) -> str:
        fa, en = MESSAGES[self.code]
        text = en if lang == "en" else fa
        if with_suggestion and self.suggestion:
            text += (f" Suggested: {self.suggestion}" if lang == "en" else f" پیشنهاد: {self.suggestion}")
        return text

    def as_dict(self, lang: str = "fa") -> dict:
        return {"detail": self.message(lang), "code": f"account_name_{self.code}", "suggestion": self.suggestion}


def validate(name: str | None) -> str:
    """The stripped name, or AccountNameInvalid."""
    clean = (name or "").strip()
    code = problem(clean)
    if code:
        raise AccountNameInvalid(code, clean)
    return clean
