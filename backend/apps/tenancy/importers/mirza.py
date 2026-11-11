"""Mirza-family Telegram VPN-sales bots (PHP + MySQL, "marzban_panel" table) → a neutral `Source` (v1.56, store import).

Read from the dump (never executed, `dump.py`):

* ``user``            — customers: ``id`` = Telegram id, ``username`` = Telegram @username, ``number`` = phone ("none" = no
                        phone), ``Balance`` = wallet (tomans), ``User_Status`` (Active / block), ``agent`` (f = customer,
                        n / others = the bot's own agents), ``affiliates`` = the referrer's Telegram id ("0" = none),
                        ``register`` (unix time), ``lang``.
* ``invoice``         — one row per sold service: ``username`` = the panel account name, ``id_user``, ``name_product``,
                        ``Volume`` (GB), ``Service_time`` (days), ``time_sell`` (unix), ``Status`` (active / send_on_hold /
                        disabled / disabledn = was sold; unpaid / Unsuccessful / removebyuser = never delivered),
                        ``Service_location`` = the bot's panel name.
* ``product``         — plans: name, ``Volume_constraint`` (GB), ``Service_time`` (days), ``price_product`` (tomans),
                        ``Location`` (the bot's panel), ``agent`` (f = for customers).
* ``Payment_report``  — card-to-card payments: ``price`` (tomans), ``payment_Status`` (paid / reject / expire / waiting /
                        Unpaid), ``time`` ("YYYY/MM/DD HH:MM:SS", Tehran), ``id_invoice`` = "<purpose>|<what>"
                        (getconfigafterpay = a purchase, getextenduser = a renewal, 0 = a wallet top-up).
* ``marzban_panel``   — the bot's panels: only ``name_panel`` / ``type`` are read (never URLs or credentials).

Nothing else is read (cards, tokens, settings, texts stay in the file).
"""
from __future__ import annotations

from datetime import datetime, timezone as dt_tz
from zoneinfo import ZoneInfo

from .source import Customer, Payment, Product, Service, Source

NAME = "mirza"
LABEL = "Mirza bot (PHP · MySQL)"
TEHRAN = ZoneInfo("Asia/Tehran")
SOLD = {"active", "send_on_hold", "disabled", "disabledn"}
LIVE = {"active", "send_on_hold"}
NEVER_DELIVERED = {"unpaid", "unsuccessful", "removebyuser"}
REQUIRED = ("user", "invoice", "product", "marzban_panel", "Payment_report")


def detect(tables: dict) -> bool:
    return all(t in tables for t in REQUIRED)


def _s(v) -> str:
    v = (v or "").strip()
    return "" if v.lower() in ("none", "null") else v       # the bot writes the word "none" for an empty field


def _int(v, default=0) -> int:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return default


def _ts(v):
    n = _int(v, 0)
    return datetime.fromtimestamp(n, tz=dt_tz.utc) if n > 1_000_000_000 else None


def _pay_time(v):
    try:
        return datetime.strptime((v or "").strip()[:19], "%Y/%m/%d %H:%M:%S").replace(tzinfo=TEHRAN)
    except ValueError:
        return None


def parse(tables: dict) -> Source:
    src = Source(system=NAME, label=LABEL)
    src.panels = [{"name": _s(p.get("name_panel")), "type": _s(p.get("type"))} for p in tables.get("marzban_panel", [])]
    for r in tables.get("user", []):
        tg = _int(r.get("id"))
        if tg <= 0:
            continue
        ref = _int(r.get("affiliates"))
        src.customers.append(Customer(
            key=str(tg), telegram_id=tg, telegram_username=_s(r.get("username")).lstrip("@")[:64],
            phone=_s(r.get("number")), balance=max(0, _int(r.get("Balance"))),
            blocked=_s(r.get("User_Status")).lower() == "block", agent=_s(r.get("agent")).lower() not in ("", "f"),
            referrer_key=str(ref) if ref > 0 and ref != tg else "", joined_at=_ts(r.get("register")),
            language="en" if _s(r.get("lang")).lower() == "en" else "fa"))
    for r in tables.get("product", []):
        src.products.append(Product(
            key=_s(r.get("code_product")) or _s(r.get("name_product")), name=_s(r.get("name_product")),
            volume_gb=_int(r.get("Volume_constraint")), days=_int(r.get("Service_time")), price=_int(r.get("price_product")),
            location=_s(r.get("Location")), for_agents=_s(r.get("agent")).lower() not in ("", "f")))
    for r in tables.get("invoice", []):
        status = _s(r.get("Status")).lower()
        src.services.append(Service(
            key=_s(r.get("id_invoice")), customer_key=str(_int(r.get("id_user"))), panel_username=_s(r.get("username")),
            product_name=_s(r.get("name_product")), volume_gb=_int(r.get("Volume")), days=_int(r.get("Service_time")),
            price=_int(r.get("price_product")), sold_at=_ts(r.get("time_sell")), location=_s(r.get("Service_location")),
            status=status, sold=status in SOLD, live=status in LIVE))
    for r in tables.get("Payment_report", []):
        purpose, _, what = (r.get("id_invoice") or "").partition("|")
        kind = {"getconfigafterpay": "buy", "getextenduser": "renew", "0": "wallet"}.get(purpose.strip(), "other")
        src.payments.append(Payment(
            key=_s(r.get("id")), customer_key=str(_int(r.get("id_user"))), amount=_int(r.get("price")),
            status=_s(r.get("payment_Status")).lower(), paid=_s(r.get("payment_Status")).lower() == "paid",
            method=_s(r.get("Payment_Method")), at=_pay_time(r.get("time")), kind=kind, ref=what.strip()[:64]))
    return src
