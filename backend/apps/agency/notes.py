"""Persian versions of the notes the server writes into the ledger, limit history and
price list (v1.25.5). Notes are stored in English (exports, audit); the panel shows
`note_fa` when it is in Persian. A note may join several parts with " · " — each
part is translated on its own; anything not recognised (e.g. a note a person typed)
is kept as it is."""
from __future__ import annotations

import re

_RULES: list[tuple[re.Pattern, str]] = [(re.compile(p), r) for p, r in [
    (r"^no price per GB set for this date — add an adjustment$",
     "برای این تاریخ قیمت هر گیگ ثبت نشده بود — با اصلاحیه درست کنید"),
    (r"^approved request #(\d+) — group manager (.+)$", r"درخواست #\1 تأیید شد — مدیر گروه \2"),
    (r"^created by group manager (.+) — pending approval$", r"ساخته‌شده توسط مدیر گروه \1 — در انتظار تأیید"),
    (r"^group manager (.+): \+(\S+) GB — pending approval #(\d+)$", r"مدیر گروه \1: ‎+\2 گیگ — در انتظار تأیید #\3"),
    (r"^set when approving request #(\d+)$", r"ثبت‌شده هنگام تأیید درخواست #\1"),
    (r"^rejected request #(\d+) \((.+?)\): (.+)$", r"درخواست #\1 رد شد (\2): \3"),
    (r"^set on creation$", "ثبت‌شده هنگام ساخت"),
    (r"^detected by the sync — changed directly on PasarGuard$", "در همگام‌سازی دیده شد — مستقیم روی پاسارگارد تغییر کرده"),
    (r"^admin created$", "ساخت ادمین"),
    (r"^limit when the history started \((.+)\)$", r"سقف در شروع تاریخچه (\1)"),
    (r"^was already unlimited$", "از قبل نامحدود بود"),
    (r"^removed (.+)$", r"حذف \1"),
    (r"^add (\S+) GB — was unlimited; based on the last limit (.+)$", r"افزودن \1 گیگ — نامحدود بود؛ بر پایهٔ آخرین سقف \2"),
    (r"^add (\S+) GB$", r"افزودن \1 گیگ"),
    (r"^reduce (\S+) GB$", r"کاهش \1 گیگ"),
    (r"^set (\S+) GB — was unlimited; based on the last limit (.+)$", r"تنظیم \1 گیگ — نامحدود بود؛ بر پایهٔ آخرین سقف \2"),
    (r"^set (\S+) GB$", r"تنظیم \1 گیگ"),
]]


def _part(p: str) -> str:
    s = p.strip()
    for rx, rep in _RULES:
        if rx.match(s):
            return rx.sub(rep, s)
    return p


def to_fa(note: str | None) -> str:
    if not note:
        return note or ""
    return " · ".join(_part(p) for p in note.split(" · "))


def localized(note: str | None, lang: str) -> str:
    return to_fa(note) if lang == "fa" else (note or "")
