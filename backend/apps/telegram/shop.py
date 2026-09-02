"""Bot-side buy / renew / status helpers (thin wrappers over apps.orders)."""
from __future__ import annotations

from django.core.files.base import ContentFile

from apps.common.jalali import to_jalali_str
from apps.orders.models import Order, OrderStatus, OrderType
from apps.orders.services import create_order
from apps.payments_sms.models import BankCard
from apps.payments_sms.services import submit_receipt
from apps.plans.models import Plan, PlanType

_GB = 1024**3


def active_plans():
    return Plan.objects.filter(is_active=True).order_by("sort_order", "id")


def user_services(user):
    return user.services.select_related("current_plan", "panel").order_by("-created_at")


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
def plan_label(plan) -> str:
    if plan.type == PlanType.CUSTOM_VOLUME:
        return f"{plan.name_fa} (حجمی)"
    vol = "نامحدود" if not plan.data_limit else f"{plan.data_limit // _GB} گیگ"
    days = "بدون انقضا" if not plan.duration_days else f"{plan.duration_days} روزه"
    return f"{plan.name_fa} — {vol} / {days} — {int(plan.final_price):,} تومان"


def service_summary(svc) -> str:
    used = svc.data_used // _GB
    total = "∞" if not svc.data_limit else f"{svc.data_limit // _GB}"
    exp = to_jalali_str(svc.expire_at, "%Y/%m/%d") if svc.expire_at else "بدون انقضا"
    status_fa = {
        "active": "فعال", "on_hold": "در انتظار اولین اتصال", "expired": "منقضی",
        "limited": "اتمام حجم", "disabled": "غیرفعال", "pending": "در حال ساخت",
    }.get(svc.status, svc.status)
    return (
        f"<b>{svc.panel_username}</b>\n"
        f"وضعیت: {status_fa}\n"
        f"مصرف: {used} از {total} گیگ\n"
        f"انقضا: {exp}"
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


def submit_bot_receipt(user, order, image_bytes: bytes, *, filename="receipt.jpg"):
    """Attach a photo sent to the bot as the order's card-to-card receipt —
    the exact same `submit_receipt` path the website uses (creates the pending
    Payment that lands in the admin approval queue)."""
    return submit_receipt(
        order=order,
        image=ContentFile(image_bytes, name=filename),
        bank_card=None,
        user=user,
    )


def delivery_message(service) -> str:
    return (
        "سرویس شما آماده است 🎉\n\n"
        f"لینک اشتراک:\n<code>{service.subscription_url}</code>\n\n"
        "برای دریافت QR دکمهٔ زیر را بزنید."
    )
