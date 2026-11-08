"""v1.42.2: Persian for the Blu tab's match notes. The note is stored in English (logs, audit, tests); the tab shows
`note_fa(note)` in Persian. Digits stay Latin (CLAUDE.md). An unknown note is returned unchanged."""
from __future__ import annotations

import re

_HOW = [
    (r"^auto-confirmed$", "خودکار تأیید شد"),
    (r"^attached by (?P<u>\S+), short (?P<s>[\d,]+) T$", r"توسط \g<u> وصل شد، کسری \g<s> تومان"),
    (r"^attached by (?P<u>\S+)$", r"توسط \g<u> وصل شد"),
    (r"^by (?P<u>\S+)$", r"توسط \g<u>"),
    (r"^auto: same_reference$", "خودکار: شمارهٔ پیگیری/مرجع یکسان"),
    (r"^auto: same_amount_time_name$", "خودکار: مبلغ، زمان و نام واریزکننده یکسان"),
    (r"^auto: same_amount_time$", "خودکار: مبلغ و زمان یکسان"),
]

_WHY = {"2+ orders fit": "بیش از یک سفارش مناسب بود", "no receipt and an unknown card": "بدون رسید و کارت ناشناس"}


def _rounded(text: str) -> str:
    """rounded.note_text(): "rounded amount — auto-approved: 1 order(s) fit, short 1,195 T ≤ 5,000 T, receipt uploaded" """
    m = re.match(r"^(rounded amount — auto-approved|rounded rule not applied \((?P<why>[^)]*)\)): (?P<bits>.*)$", text)
    if not m:
        return ""
    head = "مبلغ گرد شده — خودکار تأیید شد" if text.startswith("rounded amount") else (
        "قانون مبلغ گرد شده اعمال نشد" + (f" ({_why(m.group('why'))})" if m.group("why") else ""))
    bits = []
    for b in (m.group("bits") or "").split(", "):
        b = b.strip()
        if mm := re.match(r"^(\d+) order\(s\) fit$", b):
            bits.append(f"{mm.group(1)} سفارش مناسب")
        elif mm := re.match(r"^short ([\d,]+) T ≤ ([\d,]+) T$", b):
            bits.append(f"کمتر {mm.group(1)} تومان ≤ {mm.group(2)} تومان")
        elif mm := re.match(r"^over ([\d,]+) T ≤ ([\d,]+) T$", b):
            bits.append(f"بیشتر {mm.group(1)} تومان ≤ {mm.group(2)} تومان")
        elif b == "receipt uploaded":
            bits.append("رسید آپلود شده")
        elif mm := re.match(r"^known card \*+(\d+)$", b):
            bits.append(f"کارت آشنا ****{mm.group(1)}")
        elif b:
            bits.append(b)
    return f"{head}: " + "، ".join(bits)


def _why(w: str) -> str:
    if m := re.match(r"^deposit already approved order #(\d+)$", w):
        return f"این واریز قبلاً سفارش #{m.group(1)} را تأیید کرده"
    return _WHY.get(w, w)


def _how(how: str) -> str:
    how = how.strip()
    r = _rounded(how)
    if r:
        return r
    for pat, rep in _HOW:
        if re.match(pat, how):
            return re.sub(pat, rep, how)
    return how


_RULES: list[tuple[str, object]] = [
    (r"^no pending order of exactly (?P<a>[\d,]+) T at the deposit time$",
     r"در زمان واریز سفارش در انتظاری با مبلغ دقیق \g<a> تومان وجود نداشت"),
    (r"^amount not a whole toman \((?P<a>[\d,]+) Rial\)$", r"مبلغ تومان کامل نیست (\g<a> ریال)"),
    (r"^order #(?P<o>\d+) has this amount but the deposit is outside its window \(created (?P<c>[^,]+), reservation until "
     r"(?P<u>[^)]+) UTC\) — reused amount, not matched$",
     r"سفارش #\g<o> همین مبلغ را دارد ولی واریز خارج از بازهٔ آن است (ساخت \g<c>، رزرو تا \g<u> UTC) — مبلغ تکراری، وصل نشد"),
    (r"^amount equals order #(?P<o>\d+) AND agency payment (?P<ap>\S+) — not approved, review both$",
     r"مبلغ با سفارش #\g<o> و پرداخت نمایندگی \g<ap> برابر است — تأیید نشد، هر دو را بررسی کنید"),
    (r"^order #(?P<o>\d+) is already paid \(payment (?P<t>[^)]+)\) — duplicate$",
     r"سفارش #\g<o> قبلاً پرداخت شده (پرداخت \g<t>) — تکراری"),
    (r"^agency payment (?P<ap>\S+) was already paid — duplicate, not approved again$",
     r"پرداخت نمایندگی \g<ap> قبلاً پرداخت شده — تکراری، دوباره تأیید نشد"),
    (r"^order #(?P<o>\d+) was already paid \(SMS / receipt\) — duplicate, not approved again$",
     r"سفارش #\g<o> قبلاً (پیامک / رسید) پرداخت شده — تکراری، دوباره تأیید نشد"),
    (r"^amount mismatch — (?P<w>LESS|MORE) than invoice, NOT approved, review by hand: deposit (?P<d>[\d,]+) T, "
     r"order #(?P<o>\d+) expects (?P<i>[\d,]+) T$",
     lambda m: (f"مبلغ نامطابق — {'کمتر' if m['w'] == 'LESS' else 'بیشتر'} از فاکتور، تأیید نشد، دستی بررسی کنید: "
                f"واریز {m['d']} تومان، سفارش #{m['o']} مبلغ {m['i']} تومان")),
    (r"^amount mismatch — agency payment (?P<ap>\S+) expects (?P<i>[\d,]+) T, deposit (?P<d>[\d,]+) T — NOT approved, "
     r"review in «واریزهای نمایندگان»$",
     r"مبلغ نامطابق — پرداخت نمایندگی \g<ap> مبلغ \g<i> تومان است، واریز \g<d> تومان — تأیید نشد، در «واریزهای نمایندگان» بررسی کنید"),
    (r"^matched order #(?P<o>\d+) \((?P<a>[\d,]+) T\) — (?P<how>.+)$",
     lambda m: f"به سفارش #{m['o']} ({m['a']} تومان) وصل شد — {_how(m['how'])}"),
    (r"^linked to existing payment (?P<t>\S*) · order #(?P<o>\d+) \((?P<how>.+)\)$",
     lambda m: f"به پرداخت موجود {m['t']} · سفارش #{m['o']} متصل شد ({_how(m['how'])})"),
    (r"^linked to existing agency payment (?P<ap>\S+) \((?P<how>.+)\)$",
     lambda m: f"به پرداخت موجود نمایندگی {m['ap']} متصل شد ({_how(m['how'])})"),
    (r"^unlinked by (?P<u>\S+) — review by hand$", r"توسط \g<u> جدا شد — دستی بررسی کنید"),
    (r"^approved by staff in the payment queue \(order #(?P<o>\d+)\)$", r"در صف پرداخت توسط پشتیبان تأیید شد (سفارش #\g<o>)"),
    (r"^rounded auto-approval undone by (?P<u>.+) — review by hand$",
     r"تأیید خودکار مبلغ گرد شده توسط \g<u> لغو شد — دستی بررسی کنید"),
    (r"^rounded auto-approval restored \((?P<t>[^)]+)\)$", r"تأیید خودکار مبلغ گرد شده برگردانده شد (\g<t>)"),
    (r"^agency payment (?P<ap>\S+) \((?P<p>[^)]+)\) — rounded amount, auto-approved$",
     r"پرداخت نمایندگی \g<ap> (\g<p>) — مبلغ گرد شده، خودکار تأیید شد"),
    (r"^agency payment (?P<ap>\S+) \((?P<p>[^)]+)\) — auto-approved$", r"پرداخت نمایندگی \g<ap> (\g<p>) — خودکار تأیید شد"),
    (r"^agency payment (?P<ap>\S+) — attached by (?P<u>\S+)$", r"پرداخت نمایندگی \g<ap> — توسط \g<u> وصل شد"),
    (r"^not a deposit \(direction (?P<d>[^)]+)\)$", r"واریز نیست (جهت \g<d>)"),
    (r"^amount is not positive$", "مبلغ مثبت نیست"),
]


def _one(text: str) -> str | None:
    text = text.strip()
    r = _rounded(text)
    if r:
        return r
    for pat, rep in _RULES:
        m = re.match(pat, text)
        if m:
            return rep(m) if callable(rep) else m.expand(rep)
    return None


def note_fa(note: str) -> str:
    """The Persian text of a Blu match note: the whole note, else each « · »-joined part separately."""
    if not note:
        return ""
    whole = _one(note)
    if whole is not None:
        return whole
    return " · ".join(_one(part) or part.strip() for part in note.split(" · "))
