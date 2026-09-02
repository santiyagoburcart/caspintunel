"""Bot-side buy / renew / status helpers (thin wrappers over apps.orders)."""
from __future__ import annotations

from django.core.files.base import ContentFile
from django.utils import timezone

from apps.common.jalali import to_jalali_str
from apps.orders.models import Order, OrderStatus, OrderType
from apps.orders.services import create_order
from apps.payments_sms.models import BankCard
from apps.payments_sms.services import submit_receipt
from apps.plans.models import Plan, PlanType

_GB = 1024**3


def active_plans():
    return Plan.objects.filter(is_active=True).order_by("sort_order", "id")


# --- product display mode (grouped | flat) — shared with the site -----
_OTHER_FA = "سایر"


def product_display_mode() -> str:
    from apps.settings_app.utils import get_setting

    mode = get_setting("product_display_mode", "grouped")
    return mode if mode in ("grouped", "flat") else "grouped"


def plan_category_label(plan) -> str:
    """Bot is Persian-only: prefer category_fa, fall back to category_en."""
    return (plan.category_fa or plan.category_en or "").strip()


def grouped_plans(plans):
    """[(label, [plan, ...]), ...] in first-seen order; the no-category group
    ('سایر') always comes last. Never exposes the panel name."""
    groups: dict[str, list] = {}
    order: list[str] = []
    for p in plans:
        label = plan_category_label(p) or _OTHER_FA
        if label not in groups:
            groups[label] = []
            order.append(label)
        groups[label].append(p)
    order.sort(key=lambda lbl: 1 if lbl == _OTHER_FA else 0)
    return [(lbl, groups[lbl]) for lbl in order]


def user_services(user):
    """The user's services, with on_hold/pending ones freshly synced from the
    panel (so a just-connected service shows as active without any action)."""
    from apps.panel.services import refresh_watchable_services

    services = list(
        user.services.select_related("current_plan", "panel").order_by("-created_at")
    )
    if refresh_watchable_services(services):
        services = list(
            user.services.select_related("current_plan", "panel").order_by("-created_at")
        )
    return services


def buy_new(user, plan, *, account_name=None, custom_gb=None):
    return create_order(
        user=user, plan_id=plan.id, order_type=OrderType.NEW,
        requested_account_name=account_name, custom_volume_gb=custom_gb, source="bot",
    )


def renew(user, service, plan):
    return create_order(
        user=user, plan_id=plan.id, order_type=OrderType.RENEW,
        service_id=service.id, source="bot",
    )


# --- message formatting (Persian) ---------------------------------
def plan_label(plan, *, with_badge=False) -> str:
    if plan.type == PlanType.CUSTOM_VOLUME:
        base = f"{plan.name_fa} (حجمی)"
    else:
        vol = "نامحدود" if not plan.data_limit else f"{plan.data_limit // _GB} گیگ"
        days = "بدون انقضا" if not plan.duration_days else f"{plan.duration_days} روزه"
        base = f"{plan.name_fa} — {vol} / {days} — {int(plan.final_price):,} تومان"
    if with_badge:
        cat = plan_category_label(plan)
        if cat:
            base = f"[{cat}] {base}"
    return base


def service_summary(svc) -> str:
    from apps.panel.services import refresh_watchable_services

    if refresh_watchable_services([svc]):
        svc.refresh_from_db()
    used = svc.data_used // _GB
    total = "∞" if not svc.data_limit else f"{svc.data_limit // _GB}"
    status_fa = {
        "active": "فعال", "on_hold": "در انتظار اولین اتصال", "expired": "منقضی",
        "limited": "اتمام حجم", "disabled": "غیرفعال", "pending": "در حال ساخت",
    }.get(svc.status, svc.status)

    waiting = svc.status == "on_hold" and not svc.online_at
    if waiting:
        days = round((svc.on_hold_duration or 0) / 86400)
        time_line = (
            f"⏳ با اولین اتصال فعال می‌شود (اعتبار {days} روز)" if days
            else "⏳ با اولین اتصال فعال می‌شود"
        )
    elif svc.expire_at:
        left = max((svc.expire_at - timezone.now()).days, 0)
        time_line = f"انقضا: {to_jalali_str(svc.expire_at, '%Y/%m/%d')} ({left} روز مانده)"
    else:
        time_line = "بدون محدودیت زمان"

    return (
        f"<b>{svc.panel_username}</b>\n"
        f"وضعیت: {status_fa}\n"
        f"مصرف: {used} از {total} گیگ\n"
        f"{time_line}"
    )


def payment_instructions(order) -> str:
    cards = BankCard.objects.filter(is_active=True).order_by("sort_order", "id")
    lines = [
        "سفارش ثبت شد ✅",
        f"مبلغ دقیق قابل پرداخت: <b>{int(order.amount_unique):,} تومان</b>",
        "(لطفاً همین مبلغ دقیق را واریز کنید تا خودکار تأیید شود)",
        "",
    ]
    if cards:
        lines.append("کارت‌ها:")
        for c in cards:
            lines.append(f"• <code>{c.card_number}</code> — {c.holder_name}")
    else:
        lines.append("⚠️ کارتی برای واریز ثبت نشده — لطفاً با پشتیبانی تماس بگیرید.")
    if order.unique_expire_at:
        lines.append("")
        lines.append(f"مهلت پرداخت تا: {to_jalali_str(order.unique_expire_at, '%H:%M')}")
    lines.append("")
    lines.append("پس از واریز، <b>عکس رسید</b> را همین‌جا ارسال کنید 📸")
    return "\n".join(lines)


def order_awaiting_receipt(user):
    """The most recent order this bot user still needs to pay for."""
    return (
        Order.objects.filter(user=user, status=OrderStatus.PENDING_PAYMENT)
        .select_related("payment")
        .order_by("-created_at")
        .first()
    )


def submit_bot_receipt(user, order, image_bytes: bytes):
    """Attach a photo/document sent to the bot as the order's card-to-card
    receipt — the exact same `submit_receipt` path the website uses (creates the
    pending Payment that lands in the admin approval queue).

    The bot path bypasses DRF's ImageField validation, so we validate the bytes
    with Pillow here and pick the right extension from the real format."""
    from io import BytesIO

    from PIL import Image
    from apps.payments_sms.services import PaymentError

    if not image_bytes:
        raise PaymentError("empty file")
    try:
        img = Image.open(BytesIO(image_bytes))
        img.verify()
        fmt = (img.format or "JPEG").lower()
    except Exception as exc:  # noqa: BLE001
        raise PaymentError("that file is not a valid image") from exc

    ext = {"jpeg": "jpg", "png": "png", "webp": "webp"}.get(fmt, "jpg")
    return submit_receipt(
        order=order,
        image=ContentFile(image_bytes, name=f"receipt.{ext}"),
        bank_card=None,
        user=user,
    )


def delivery_message(service) -> str:
    return (
        "سرویس شما آماده است 🎉\n\n"
        f"لینک اشتراک:\n<code>{service.subscription_url}</code>\n\n"
        "برای دریافت QR دکمهٔ زیر را بزنید."
    )
