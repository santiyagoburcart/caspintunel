"""Starter ticket topics (v1.52.1). A new reseller store gets a copy of OUR active topics when it is opened
(`tenancy.stores.enable`), so its customers can open tickets from day one; the reseller edits / deletes its copies.
`TOPICS` is the fallback when we have no active topic (same list as migration 0002_seed_topics, which keeps its own copy)."""
from __future__ import annotations

TOPICS = [
    # name_fa, name_en, description_fa, description_en, requires_active_service
    ("سوالات قبل از خرید", "Pre-purchase questions", "پلن‌ها، قیمت‌ها و نحوهٔ خرید",
     "Plans, prices and how to buy", False),
    ("مشکل پرداخت", "Payment problem", "پرداخت انجام شده ولی تأیید نشده، رسید، مبلغ",
     "Paid but not confirmed, receipts, amounts", True),
    ("مشکل اتصال", "Connection problem", "وصل نمی‌شود، کندی، قطعی", "Cannot connect, slow, disconnects", True),
    ("تمدید و ارتقا", "Renewal & upgrade", "تمدید سرویس، حجم اضافه، تغییر پلن",
     "Renew a service, add volume, change plan", True),
    ("سایر", "Other", "موارد دیگر", "Anything else", True),
]
FIELDS = ("name_fa", "name_en", "description_fa", "description_en", "requires_active_service", "sort_order")


def starter_topics() -> list[dict]:
    """Our active topics as plain dicts (call inside OUR tenant context) — never the staff scopes."""
    from .models import TicketTopic

    rows = list(TicketTopic.objects.filter(is_active=True).order_by("sort_order", "id").values(*FIELDS))
    if rows:
        return rows
    return [dict(zip(FIELDS, (fa, en, dfa, den, needs, (i + 1) * 10)))
            for i, (fa, en, dfa, den, needs) in enumerate(TOPICS)]
