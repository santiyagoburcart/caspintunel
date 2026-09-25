"""Link a Telegram user to a site `User` (architecture: website account == bot account)."""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.accounts.models import Source
from apps.accounts.phone import iran_phone_only, normalize_ir_phone, normalize_phone
from apps.common.models import write_audit

User = get_user_model()
log = logging.getLogger("caspintunel")


def _unique_username() -> str:
    for _ in range(20):
        candidate = f"tg_{secrets.token_hex(4)}"
        if not User.objects.filter(username=candidate).exists():
            return candidate
    raise RuntimeError("could not allocate a bot username")


@transaction.atomic
def ensure_bot_user(telegram_id: int, *, telegram_username: str | None = None,
                    phone: str | None = None, name: str | None = None):
    """
    Returns (user, created, generated_password | None).

    First-time bot users get a random username + password for website login
    (architecture §2). Existing users are synced with any newly-known fields.
    """
    phone = (normalize_ir_phone(phone) or normalize_phone(phone)) if phone else None
    user = User.objects.filter(telegram_id=telegram_id).first()
    if user:
        fields = []
        if telegram_username and user.telegram_username != telegram_username:
            user.telegram_username = telegram_username
            fields.append("telegram_username")
        if phone and not user.phone:
            user.phone = phone
            fields.append("phone")
        if name and not user.name:
            user.name = name
            fields.append("name")
        if fields:
            fields.append("updated_at")
            user.save(update_fields=fields)
        return user, False, None

    password = secrets.token_urlsafe(9)
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=_unique_username(),
                password=password,
                telegram_id=telegram_id,
                telegram_username=telegram_username or "",
                phone=phone or "",
                name=name or "",
                source=Source.BOT,
            )
    except IntegrityError:
        # a concurrent first-contact (two Mini App launches / bot + app at once)
        # already created the row — adopt it instead of failing.
        user = User.objects.filter(telegram_id=telegram_id).first()
        if user is None:
            raise
        return user, False, None
    write_audit(action="user.created_via_bot", target=user, detail={"telegram_id": telegram_id})
    return user, True, password


@dataclass
class PhoneLinkResult:
    """Outcome of a Telegram contact share.

    status: "linked" (phone saved), "already" (same phone as before),
    "merged" (joined an existing site account — `user` is now that account),
    "not_iranian" (rejected by iran_phone_only), "invalid", or "conflict"
    (the number belongs to a different Telegram-linked account).
    """
    status: str
    user: object
    phone: str = ""
    moved: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in ("linked", "already", "merged")


@transaction.atomic
def link_telegram_phone(user, raw_phone: str) -> PhoneLinkResult:
    """Store the phone a Telegram user shared (Telegram-verified, e.g.
    "+989107323128" -> "09107323128") and, if it matches a SITE account that
    has no Telegram link yet, merge this bot account into it."""
    phone = normalize_ir_phone(raw_phone)
    if phone is None:
        if iran_phone_only():
            return PhoneLinkResult("not_iranian", user)
        phone = normalize_phone(raw_phone)
        if phone is None:
            return PhoneLinkResult("invalid", user)

    owner = (User.objects.select_for_update().filter(phone=phone)
             .exclude(pk=user.pk).order_by("id").first())
    if owner is None:
        if user.phone == phone:
            return PhoneLinkResult("already", user, phone)
        # the Telegram number is verified by Telegram, so it wins over
        # whatever (unverified) value the account had before
        user.phone = phone
        user.save(update_fields=["phone", "updated_at"])
        return PhoneLinkResult("linked", user, phone)
    if owner.telegram_id:
        log.warning("bot contact %s for tg %s matches user %s already linked to tg %s",
                    phone, user.telegram_id, owner.pk, owner.telegram_id)
        return PhoneLinkResult("conflict", user, phone)
    merged, moved = merge_bot_account_into_site(bot_user=user, site_user=owner, phone=phone)
    return PhoneLinkResult("merged", merged, phone, moved)


def link_phone(user, phone: str) -> None:
    """Back-compat wrapper (kept for callers that only need the side effect)."""
    link_telegram_phone(user, phone)


def _revoke_sessions(user) -> int:
    """Blacklist every refresh token; access tokens die through the
    password-hash claim (accounts.authentication) once the password changes."""
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    n = 0
    for tok in OutstandingToken.objects.filter(user=user):
        _, created = BlacklistedToken.objects.get_or_create(token=tok)
        n += int(created)
    return n


# admin-note wording for the relations a merge moves (audit detail keeps the raw labels)
_FRIENDLY = {
    "orders.Order.user": "orders (with their payments)",
    "panel.Service.user": "services",
    "accounts.User.referred_by": "referrals",
    "notifications.Notification.target_user": "notifications",
    "notifications.NotificationDelivery.user": "notification deliveries",
    "token_blacklist.OutstandingToken.user": "login sessions",
    "admin.LogEntry.user": "django-admin log entries",
}


@transaction.atomic
def merge_bot_account_into_site(*, bot_user, site_user, phone: str):
    """Move everything the bot-only account owns into the site account, link
    the Telegram id to the site account and retire the bot account.

    The site account's phone was never verified (anyone could have typed it),
    while the Telegram phone is — so the site password is invalidated and
    every existing site session revoked; the owner sets a new password from
    the bot. Returns (site_user, moved-counts)."""
    site_user = User.objects.select_for_update().get(pk=site_user.pk)
    bot_user = User.objects.select_for_update().get(pk=bot_user.pk)
    tg_id = bot_user.telegram_id

    moved: dict[str, int] = {}
    for rel in User._meta.related_objects:
        if rel.many_to_many:
            continue
        model, fname = rel.related_model, rel.field.name
        qs = model._default_manager.filter(**{fname: bot_user})
        if model is User:
            qs = qs.exclude(pk=site_user.pk)       # never make the site user refer itself
        if rel.one_to_one and model._default_manager.filter(**{fname: site_user}).exists():
            continue
        count = qs.update(**{fname: site_user})
        if count:
            moved[f"{model._meta.label}.{fname}"] = count

    # profile fields the site account doesn't have yet
    for f in ("telegram_username", "name", "bank_card_number"):
        if not getattr(site_user, f) and getattr(bot_user, f):
            setattr(site_user, f, getattr(bot_user, f))
    if (site_user.referred_by_id is None and bot_user.referred_by_id
            and bot_user.referred_by_id != site_user.pk):
        site_user.referred_by_id = bot_user.referred_by_id

    # free the unique telegram_id before handing it to the site account
    bot_username = bot_user.username
    bot_user.telegram_id = None
    bot_user.phone = ""
    bot_user.is_active = False
    bot_user.save(update_fields=["telegram_id", "phone", "is_active", "updated_at"])

    site_user.telegram_id = tg_id
    site_user.phone = phone
    site_user.set_unusable_password()
    revoked = _revoke_sessions(site_user)

    stamp = timezone.now().strftime("%Y-%m-%d %H:%M")
    summary = ", ".join(f"{_FRIENDLY.get(k, k)}: {v}" for k, v in moved.items()) or "nothing"
    note = (f"[{stamp}] Telegram account merged via bot contact {phone}: bot user "
            f"'{bot_username}' (#{bot_user.pk}, tg {tg_id}) -> this account. Moved: {summary}. "
            f"Site password invalidated, {revoked} session(s) revoked.")
    site_user.admin_note = (site_user.admin_note + "\n" if site_user.admin_note else "") + note
    site_user.save()

    write_audit(action="user.merged_telegram", target=site_user, staff="telegram-bot", detail={
        "site_user": site_user.pk, "bot_user": bot_user.pk, "bot_username": bot_username,
        "telegram_id": tg_id, "phone": phone, "moved": moved, "sessions_revoked": revoked,
    })
    log.info("merged bot user %s (tg %s) into site user %s: %s", bot_user.pk, tg_id, site_user.pk, moved)

    # the bot account is now empty — drop it (kept, deactivated, if anything still protects it)
    try:
        with transaction.atomic():
            bot_user.delete()
    except ProtectedError:
        pass
    return site_user, moved


def change_password_via_bot(user, new_password: str) -> None:
    """Set a new password from the sales bot.

    Unlike the website's change-password flow, this does not ask for the
    current password: the user's identity is already proven by chatting
    from their own linked Telegram account (the same trust level the
    website's "forgot password" email link relies on), so it mirrors that
    reset path rather than the in-session change-password one.
    Raises django.core.exceptions.ValidationError if the password is weak.
    """
    validate_password(new_password, user)
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    write_audit(action="password.changed_via_bot", target=user)
