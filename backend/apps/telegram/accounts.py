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
class ContactResult:
    """Outcome of a Telegram contact share (`handle_contact`).

    status:
      "created"     no account had this Telegram id or phone -> new account (`password` set, send it once)
      "linked"      an existing site account had the phone -> Telegram attached to it (no bot account existed)
      "merged"      a bot account existed AND a site account had the phone -> bot account folded into it
      "phone_saved" the Telegram account had no (or another) phone -> phone stored on it
      "already"     same phone as before
      "conflict"    the phone belongs to an account linked to a DIFFERENT Telegram id (staff notified)
      "not_own"     the contact card is not the sender's own number
      "not_iranian" / "invalid"  rejected number
    In "linked" / "merged" the site account keeps its username and password.
    """
    status: str
    user: object = None
    phone: str = ""
    password: str | None = None
    moved: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in ("created", "linked", "merged", "phone_saved", "already")


def _clean_contact_phone(raw_phone: str):
    """(phone, None) or (None, "not_iranian" | "invalid")."""
    phone = normalize_ir_phone(raw_phone)
    if phone:
        return phone, None
    if iran_phone_only():
        return None, "not_iranian"
    phone = normalize_phone(raw_phone)
    return (phone, None) if phone else (None, "invalid")


@transaction.atomic
def handle_contact(telegram_id: int, raw_phone: str, *, contact_user_id=None,
                   telegram_username: str = "", name: str = "") -> ContactResult:
    """The one place a shared Telegram contact is turned into an account.

    The phone comes from Telegram (verified), so it is the key: an existing
    account with that phone is reused — never a second account. A site
    account's username and password are never changed by this."""
    telegram_id = int(telegram_id)
    if contact_user_id is None or int(contact_user_id) != telegram_id:
        log.warning("tg %s shared a contact that is not their own (contact user %s)", telegram_id, contact_user_id)
        return ContactResult("not_own")
    phone, bad = _clean_contact_phone(raw_phone)
    if bad:
        return ContactResult(bad)

    current = User.objects.select_for_update().filter(telegram_id=telegram_id).first()
    owner_qs = User.objects.select_for_update().filter(phone=phone)
    if current is not None:
        owner_qs = owner_qs.exclude(pk=current.pk)
    owner = owner_qs.order_by("id").first()

    if owner is not None and owner.telegram_id:
        # the number is someone else's Telegram-linked account: never merge, a human decides
        log.warning("tg %s shared %s, which belongs to user %s linked to tg %s",
                    telegram_id, phone, owner.pk, owner.telegram_id)
        write_audit(action="user.telegram_link_conflict", target=owner, staff="telegram-bot", detail={
            "telegram_id": telegram_id, "phone": phone, "owner": owner.pk,
            "owner_telegram_id": owner.telegram_id, "bot_user": current.pk if current else None,
        })
        transaction.on_commit(lambda: notify_staff_conflict(telegram_id, telegram_username, phone, owner.pk))
        return ContactResult("conflict", current, phone)

    if current is not None:
        if owner is None:
            if current.phone == phone:
                return ContactResult("already", current, phone)
            old = current.phone
            # Telegram verified this number, so it wins over an older (unverified) value
            current.phone = phone
            current.save(update_fields=["phone", "updated_at"])
            write_audit(action="user.phone_from_telegram", target=current, staff="telegram-bot",
                        detail={"telegram_id": telegram_id, "phone": phone, "old_phone": old})
            return ContactResult("phone_saved", current, phone)
        merged, moved = merge_bot_account_into_site(bot_user=current, site_user=owner, phone=phone)
        return ContactResult("merged", merged, phone, moved=moved)

    if owner is not None:
        return ContactResult("linked", link_telegram_to_account(owner, telegram_id, telegram_username, name), phone)

    user, created, password = ensure_bot_user(telegram_id, telegram_username=telegram_username,
                                              phone=phone, name=name)
    return ContactResult("created" if created else "already", user, phone, password=password)


def link_telegram_to_account(user, telegram_id: int, telegram_username: str = "", name: str = ""):
    """Attach a Telegram id to an existing (site) account. Username, password
    and sessions stay as they are."""
    user = User.objects.select_for_update().get(pk=user.pk)
    user.telegram_id = telegram_id
    fields = ["telegram_id", "updated_at"]
    if telegram_username and user.telegram_username != telegram_username:
        user.telegram_username = telegram_username
        fields.append("telegram_username")
    if name and not user.name:
        user.name = name
        fields.append("name")
    stamp = timezone.now().strftime("%Y-%m-%d %H:%M")
    user.admin_note = ((user.admin_note + "\n") if user.admin_note else "") + (
        f"[{stamp}] Telegram {telegram_id} linked via bot contact {user.phone} "
        "(username and password unchanged).")
    fields.append("admin_note")
    user.save(update_fields=fields)
    write_audit(action="user.linked_telegram", target=user, staff="telegram-bot",
                detail={"telegram_id": telegram_id, "phone": user.phone, "username": user.username})
    log.info("linked tg %s to existing user %s", telegram_id, user.pk)
    return user


def notify_staff_conflict(telegram_id: int, telegram_username: str, phone: str, owner_id: int) -> int:
    """Tell staff (linked staff with users.manage, else the backup chat) that a
    Telegram user shared a number that belongs to another Telegram-linked
    account. Best effort, at most once an hour per (Telegram id, phone)."""
    from apps.common.staff_alert import alert_staff

    owner = User.objects.filter(pk=owner_id).first()
    who = f"@{telegram_username}" if telegram_username else "-"
    text = ("⚠️ تداخل حساب تلگرام / Telegram account conflict\n"
            f"Telegram {telegram_id} ({who}) shared {phone}.\n"
            f"That number belongs to user #{owner_id} ({owner.username if owner else '?'}), "
            f"already linked to Telegram {owner.telegram_id if owner else '?'}.\n"
            "Nothing was merged — check it in Users.")
    return alert_staff(text, perm="users.manage", dedupe_key=f"tgconflict:{telegram_id}:{phone}")


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

    The site account keeps its username, password and sessions (the phone is
    verified by Telegram, so this is the same person). The bot account's
    generated credentials stop working. Returns (site_user, moved-counts)."""
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

    stamp = timezone.now().strftime("%Y-%m-%d %H:%M")
    summary = ", ".join(f"{_FRIENDLY.get(k, k)}: {v}" for k, v in moved.items()) or "nothing"
    note = (f"[{stamp}] Telegram account merged via bot contact {phone}: bot user "
            f"'{bot_username}' (#{bot_user.pk}, tg {tg_id}) -> this account. Moved: {summary}. "
            "Username and password unchanged.")
    site_user.admin_note = (site_user.admin_note + "\n" if site_user.admin_note else "") + note
    site_user.save()

    write_audit(action="user.merged_telegram", target=site_user, staff="telegram-bot", detail={
        "site_user": site_user.pk, "bot_user": bot_user.pk, "bot_username": bot_username,
        "telegram_id": tg_id, "phone": phone, "moved": moved, "password_kept": True,
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
