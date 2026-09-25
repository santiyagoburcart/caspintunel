"""
Admin "delete user" (soft delete) and restore.

Deleting never removes rows: orders, payments and transactions stay linked to
the (now soft-deleted) user so accounting is unchanged. What happens:

1. every service of the user is DISABLED on its PasarGuard panel (never
   deleted) and our Service rows are marked disabled;
2. a full JSON snapshot is stored in `DeletedUserArchive`;
3. the user is soft-deleted (deleted_at / deleted_by / delete_reason,
   is_active=False), every login session is revoked and the Telegram id is
   unlinked so the bot treats that person as a new user;
4. username / phone / email are freed by prefixing them with
   "deleted_<id>_" so the same person can sign up again — the originals stay
   in the archive, and a restore puts them back if they are still free.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from apps.common.models import write_audit

from .models import DeletedUserArchive, Staff, User

log = logging.getLogger("caspintunel")


class UserDeletionError(Exception):
    """The delete could not be completed (nothing was soft-deleted)."""

    def __init__(self, message: str, *, failed: list[dict] | None = None):
        super().__init__(message)
        self.failed = failed or []


class RestoreConflict(Exception):
    """A restore is blocked because original identifiers are taken again."""

    def __init__(self, conflicts: dict[str, dict]):
        self.conflicts = conflicts
        super().__init__("original " + ", ".join(conflicts) + " already in use")


def _iso(dt):
    return dt.isoformat() if dt else None


def _staff_label(staff) -> str:
    return getattr(staff, "username", "") or (str(staff) if staff else "")


def _confirmer(payment) -> str | None:
    if payment.confirmed_by == "system":
        return "SMS system"
    if payment.confirmed_by_staff_id:
        return payment.confirmed_by_staff.username
    return payment.confirmed_by or None


def freed_value(prefix: str, value: str, max_length: int) -> str:
    """"deleted_<id>_<value>", cut to the column width (the id keeps it unique)."""
    return f"{prefix}{value}"[:max_length]


def build_snapshot(user: User, *, service_panel_results: dict[int, str] | None = None,
                   services_before: dict[int, str] | None = None) -> dict:
    """Everything worth keeping about a user, as plain JSON."""
    from apps.notifications.models import Notification, NotificationDelivery
    from apps.orders.models import Order
    from apps.panel.models import Service

    service_panel_results = service_panel_results or {}
    services_before = services_before or {}

    orders = []
    qs = (Order.objects.filter(user=user)
          .select_related("plan", "payment", "payment__bank_card", "payment__confirmed_by_staff")
          .order_by("created_at"))
    for o in qs:
        pay = getattr(o, "payment", None)
        orders.append({
            "id": o.id, "type": o.type, "status": o.status, "source": o.source,
            "plan": ({"id": o.plan_id, "name_fa": o.plan.name_fa, "name_en": o.plan.name_en}
                     if o.plan_id else None),
            "amount": int(o.amount), "amount_unique": int(o.amount_unique),
            "requested_account_name": o.requested_account_name or "",
            "custom_volume_gb": o.custom_volume_gb, "service_id": o.service_id,
            "created_at": _iso(o.created_at),
            "payment": None if pay is None else {
                "id": pay.id, "method": pay.method, "amount": int(pay.amount), "status": pay.status,
                "card": ({"number": pay.bank_card.card_number, "holder": pay.bank_card.holder_name,
                          "bank": pay.bank_card.bank_name} if pay.bank_card_id else None),
                "gateway_ref": pay.gateway_ref or "", "confirmed_by": pay.confirmed_by or "",
                "confirmer": _confirmer(pay), "confirmed_at": _iso(pay.confirmed_at),
                "reject_reason": pay.reject_reason or "", "has_receipt": bool(pay.receipt_image),
                "created_at": _iso(pay.created_at),
            },
        })

    services = []
    for s in (Service.objects.filter(user=user).select_related("panel", "current_plan").order_by("created_at")):
        services.append({
            "id": s.id, "panel": {"id": s.panel_id, "name": s.panel.name},
            "panel_username": s.panel_username,
            "plan": ({"id": s.current_plan_id, "name_fa": s.current_plan.name_fa,
                      "name_en": s.current_plan.name_en} if s.current_plan_id else None),
            "status_before": services_before.get(s.id, s.status), "status": s.status,
            "panel_result": service_panel_results.get(s.id, ""),
            "data_limit": s.data_limit, "data_used": s.data_used,
            "expire_strategy": s.expire_strategy, "expire_at": _iso(s.expire_at),
            "on_hold_duration": s.on_hold_duration, "device_limit": s.device_limit,
            "subscription_url": s.subscription_url, "online_at": _iso(s.online_at),
            "source": s.source, "created_at": _iso(s.created_at),
        })

    approved = [o["payment"]["amount"] for o in orders
                if o["payment"] and o["payment"]["status"] == "approved"]
    return {
        "profile": {
            "id": user.id, "username": user.username, "name": user.name, "phone": user.phone,
            "email": user.email or "", "email_verified": user.email_verified,
            "telegram_id": user.telegram_id, "telegram_username": user.telegram_username or "",
            "bank_card_number": user.bank_card_number or "",
            "referral_code": user.referral_code,
            "referred_by": ({"id": user.referred_by_id, "username": user.referred_by.username}
                            if user.referred_by_id else None),
            "referral_count": user.referrals.count(),
            "source": user.source, "language": user.language, "is_legacy": user.is_legacy,
            "was_active": user.is_active, "created_at": _iso(user.created_at),
            "admin_note": user.admin_note or "",
        },
        "orders": orders,
        "services": services,
        "notifications": {
            "targeted": Notification.objects.filter(target_user=user).count(),
            "deliveries": NotificationDelivery.objects.filter(user=user).count(),
        },
        "totals": {"orders": len(orders), "payments_approved": len(approved), "total_paid": sum(approved)},
    }


def _revoke_sessions(user) -> int:
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    n = 0
    for tok in OutstandingToken.objects.filter(user=user):
        _, created = BlacklistedToken.objects.get_or_create(token=tok)
        n += int(created)
    return n


def delete_user(user: User, *, staff, reason: str) -> DeletedUserArchive:
    """Soft-delete `user` (see module docstring). Raises UserDeletionError if
    any service could not be disabled on its panel — in that case the user is
    left untouched (services already disabled stay disabled) so the admin can
    retry once the panel is reachable."""
    from apps.panel.exceptions import PanelError
    from apps.panel.models import Service, ServiceStatus
    from apps.panel.services import disable_service_on_panel

    reason = (reason or "").strip()
    if not reason:
        raise UserDeletionError("a reason is required")
    if user.deleted_at is not None:
        raise UserDeletionError("user is already deleted")

    # 1) panels first — outside our transaction; each call is idempotent
    before, results, failed = {}, {}, []
    for svc in Service.objects.filter(user=user).select_related("panel"):
        before[svc.id] = svc.status
        try:
            results[svc.id] = disable_service_on_panel(svc)
        except PanelError as exc:
            log.warning("delete user %s: could not disable service %s: %s", user.id, svc.id, exc)
            failed.append({"service_id": svc.id, "panel_username": svc.panel_username,
                           "panel": svc.panel.name, "error": str(exc)})
    if failed:
        raise UserDeletionError(
            "could not disable %d service(s) on the panel — the user was not deleted" % len(failed),
            failed=failed,
        )

    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user.pk)
        # 2) snapshot, before anything is freed
        snap = build_snapshot(user, service_panel_results=results, services_before=before)
        snap["services_disabled"] = sum(1 for r in results.values() if r == "disabled")
        archive = DeletedUserArchive.objects.create(
            user=user,
            original_username=user.username, original_name=user.name or "",
            original_phone=user.phone or "", original_email=user.email or "",
            original_telegram_id=user.telegram_id,
            original_telegram_username=user.telegram_username or "",
            deleted_by=staff if isinstance(staff, Staff) else None,
            deleted_by_label=_staff_label(staff), reason=reason,
            orders_count=snap["totals"]["orders"], total_paid=snap["totals"]["total_paid"],
            snapshot=snap,
        )
        # our rows mirror the panel: everything disabled
        Service.objects.filter(user=user).exclude(status=ServiceStatus.DISABLED).update(
            status=ServiceStatus.DISABLED, updated_at=timezone.now())

        # 3) soft delete + 4) free unique identifiers
        prefix = f"deleted_{user.pk}_"
        user.username = freed_value(prefix, user.username, User._meta.get_field("username").max_length)
        if user.phone:
            user.phone = freed_value(prefix, user.phone, User._meta.get_field("phone").max_length)
        if user.email:
            user.email = freed_value(prefix, user.email, User._meta.get_field("email").max_length)
        user.telegram_id = None
        user.is_active = False
        user.deleted_at = archive.deleted_at
        user.deleted_by = archive.deleted_by
        user.delete_reason = reason
        stamp = timezone.localtime(archive.deleted_at).strftime("%Y-%m-%d %H:%M")
        note = f"[{stamp}] Deleted by {archive.deleted_by_label or 'admin'}: {reason} (archive #{archive.pk})"
        user.admin_note = (user.admin_note + "\n" if user.admin_note else "") + note
        user.save()
        revoked = _revoke_sessions(user)

        write_audit(action="user.deleted", staff=staff, target=user, detail={
            "archive": archive.pk, "username": archive.original_username, "reason": reason,
            "services": results, "sessions_revoked": revoked,
            "orders": archive.orders_count, "total_paid": int(archive.total_paid),
        })
    return archive


def restore_conflicts(archive: DeletedUserArchive) -> dict[str, dict]:
    """Which original identifiers are taken by another account now."""
    others = User.objects.exclude(pk=archive.user_id)
    out: dict[str, dict] = {}
    checks = [("username", "username__iexact", archive.original_username),
              ("phone", "phone", archive.original_phone),
              ("email", "email__iexact", archive.original_email)]
    for key, lookup, value in checks:
        if not value:
            continue
        hit = others.filter(**{lookup: value}).only("id", "username").first()
        if hit:
            out[key] = {"value": value, "user_id": hit.id, "username": hit.username}
    return out


@dataclass
class RestoreResult:
    user: User
    telegram_restored: bool
    warnings: list[str] = field(default_factory=list)


def restore_user(archive: DeletedUserArchive, *, staff) -> RestoreResult:
    """Undo a soft delete from its archive. Blocked (RestoreConflict) when the
    original username / phone / email now belong to someone else. Services
    stay disabled — an admin re-enables them one by one."""
    if archive.restored_at is not None:
        raise UserDeletionError("this archive was already restored")
    if archive.user_id is None:
        raise UserDeletionError("the user row no longer exists")

    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=archive.user_id)
        if user.deleted_at is None:
            raise UserDeletionError("user is not deleted")
        latest = user.deletion_archives.order_by("-deleted_at", "-id").first()
        if latest is None or latest.pk != archive.pk:
            raise UserDeletionError("only the most recent deletion of this user can be restored")
        conflicts = restore_conflicts(archive)
        if conflicts:
            raise RestoreConflict(conflicts)

        warnings = []
        tg = archive.original_telegram_id
        tg_ok = bool(tg) and not User.objects.exclude(pk=user.pk).filter(telegram_id=tg).exists()
        if tg and not tg_ok:
            warnings.append("telegram_id_in_use")

        user.username = archive.original_username
        user.phone = archive.original_phone
        user.email = archive.original_email or None
        user.telegram_id = tg if tg_ok else None
        if tg_ok and archive.original_telegram_username:
            user.telegram_username = archive.original_telegram_username
        user.is_active = True
        user.deleted_at = None
        user.deleted_by = None
        user.delete_reason = ""
        now = timezone.now()
        label = _staff_label(staff)
        note = (f"[{timezone.localtime(now):%Y-%m-%d %H:%M}] Restored by {label or 'admin'} "
                f"from archive #{archive.pk}" + ("" if tg_ok or not tg else " (Telegram id was in use — not relinked)"))
        user.admin_note = (user.admin_note + "\n" if user.admin_note else "") + note
        user.save()

        archive.restored_at = now
        archive.restored_by = staff if isinstance(staff, Staff) else None
        archive.restored_by_label = label
        archive.save(update_fields=["restored_at", "restored_by", "restored_by_label"])

        write_audit(action="user.restored", staff=staff, target=user, detail={
            "archive": archive.pk, "username": user.username, "telegram_relinked": tg_ok,
            "warnings": warnings,
        })
    return RestoreResult(user=user, telegram_restored=tg_ok, warnings=warnings)

