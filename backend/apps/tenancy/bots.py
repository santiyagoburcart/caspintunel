"""A store's own Telegram bot (v1.49, multi-tenant Phase 6 — docs/multi-tenant.md §8).

* Webhook mode only (no process per bot): Telegram posts to `/api/v1/telegram/hook/<tenant id>/` on OUR site host with the
  store's `webhook_secret` (apps/telegram/webhook.py); the update runs in Celery inside the store's tenant context through
  the same handlers as our sales bot (apps/telegram/bot/store_bots.py).
* Only our staff set / replace / remove the token (D5, «فروشگاه» → ربات): `getMe` check, never our own bots, one store per
  bot, stored encrypted, then `apply` = setWebhook (+ secret) · menu button → the store's Mini App (its site domain) ·
  description from the store's branding. The token is never returned by any API, logged or audited.
* `check` (Celery, every 10 min + «بررسی») reads getWebhookInfo, puts a wrong webhook back, and alerts US once when the bot
  is broken (`alert_staff(platform=True)`), once more when it works again.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Tenant, TenantBot

log = logging.getLogger("caspintunel")

TOKEN_RE = re.compile(r"^(\d{5,15}):[A-Za-z0-9_-]{30,64}$")
ALLOWED_UPDATES = ["message", "callback_query"]
MENU_TEXT = "🌐 اپ"
HOOK_PATH = "/api/v1/telegram/hook/{id}/"


class BotError(Exception):
    def __init__(self, key: str, fa: str, en: str, status: int = 400):
        super().__init__(en)
        self.key, self.fa, self.en, self.status = key, fa, en, status


def _client(token: str):
    from apps.telegram.client import TelegramClient

    return TelegramClient(token, proxy_url=getattr(settings, "TELEGRAM_PROXY_URL", "") or None)


def hook_ip() -> str:
    """v1.60.1: the address Telegram must post to — OUR server (SERVER_IP), never what our domain resolves to. In access mode
    *tunnel* caspintunel.com resolves to the Iran IP, which Telegram cannot reach («Connection refused», no update was ever
    delivered to a store bot). Same URL and certificate, only the connection goes straight to us (setWebhook ip_address)."""
    return (getattr(settings, "SERVER_IP", "") or "").strip()


def hook_url(tenant_id: int) -> str:
    """On OUR host (never the store's domain), so a store domain problem never stops its bot."""
    from apps.settings_app.models import SiteConfig

    domain = (SiteConfig.load().site_domain or "").strip().strip("/")
    base = f"https://{domain}" if domain else settings.PUBLIC_BASE_URL.rstrip("/")
    return base + HOOK_PATH.format(id=tenant_id)


def _our_bot_ids() -> set[str]:
    from apps.telegram.models import TelegramConfig

    return {(c.token or "").split(":", 1)[0] for c in TelegramConfig.objects.all() if c.token}


def row(t: Tenant | None, *, staff_view: bool = True) -> dict | None:
    b = getattr(t, "bot", None) if t is not None else None
    if b is None:
        return None
    out = {"username": b.username, "state": b.state, "last_error": b.last_error,
           "webhook_set_at": b.webhook_set_at, "last_update_at": b.last_update_at, "last_check_at": b.last_check_at}
    if not staff_view:            # the reseller: which bot and whether it works
        out.pop("last_check_at")
    return out


def _audit(action: str, t: Tenant, staff, **detail) -> None:
    from apps.common.models import write_audit

    write_audit(action=action, staff=staff, target=t, detail={"tenant": t.pk, **detail})


# ------------------------------------------------------------------ set / remove
def set_token(t: Tenant, raw: str, *, staff=None) -> TenantBot:
    from apps.telegram.client import TelegramError

    token = (raw or "").strip()
    m = TOKEN_RE.match(token)
    if not m:
        raise BotError("format", "توکن ربات معتبر نیست (شکل درست: 123456789:AA…، از BotFather).",
                       "That is not a bot token (format 123456789:AA…, from BotFather).")
    if m.group(1) in _our_bot_ids():
        raise BotError("ours", "این توکنِ ربات خودمان است — برای فروشگاه یک ربات جدا در BotFather بسازید.",
                       "That is one of our own bots — create a separate bot for the store in BotFather.")
    try:
        me = _client(token).get_me()
    except TelegramError as exc:
        raise BotError("rejected", f"تلگرام این توکن را نپذیرفت: {exc}", f"Telegram refused the token: {exc}") from exc
    if not me.get("is_bot"):
        raise BotError("rejected", "این توکن مال یک ربات نیست.", "That token is not a bot's.")
    taken = TenantBot.objects.filter(bot_id=me["id"]).exclude(tenant=t).select_related("tenant").first()
    if taken is not None:
        raise BotError("taken", f"این ربات به فروشگاه «{taken.tenant.name}» وصل است.",
                       f"That bot already belongs to the store {taken.tenant.name}.", status=409)
    with transaction.atomic():
        b = TenantBot.objects.select_for_update().filter(tenant=t).first()
        old_token = b.token if b is not None and b.bot_id != me["id"] else None
        if b is None:
            b = TenantBot(tenant=t)
        from .models import _webhook_secret

        b.token, b.bot_id, b.username = token, me["id"], me.get("username") or ""
        b.webhook_secret = _webhook_secret()          # a new secret with every token
        b.state, b.last_error, b.alerted_at = TenantBot.OK, "", None
        b.save()
    if old_token:                                      # the previous bot stops calling us
        _delete_webhook(old_token)
    _audit("store.bot_set", t, staff, username=b.username, bot_id=b.bot_id)
    apply(b)
    return b


def remove(t: Tenant, *, staff=None) -> None:
    b = TenantBot.objects.filter(tenant=t).first()
    if b is None:
        return
    _delete_webhook(b.token)
    username = b.username
    b.delete()
    forget(t.pk)
    _audit("store.bot_removed", t, staff, username=username)


def _delete_webhook(token: str) -> None:
    try:
        _client(token)._call("deleteWebhook", drop_pending_updates="true")
    except Exception as exc:  # noqa: BLE001 — a revoked token: nothing left to stop
        log.info("store bot: deleteWebhook failed: %s", exc)


def forget(tenant_id: int) -> None:
    """Drop the cached bot object in this process (token / username changed or removed)."""
    from apps.telegram.bot import store_bots

    store_bots.forget(tenant_id)


# ------------------------------------------------------------------ apply / check
def apply(b: TenantBot) -> TenantBot:
    """setWebhook + menu button + description. Errors are kept on the row (state=error), never raised."""
    from apps.settings_app.branding import branding, public_base
    from apps.telegram.client import TelegramError

    from .context import tenant_context

    c = _client(b.token)
    try:
        extra = {"ip_address": hook_ip()} if hook_ip() else {}
        c._call("setWebhook", url=hook_url(b.tenant_id), secret_token=b.webhook_secret, max_connections=10,
                allowed_updates=json.dumps(ALLOWED_UPDATES), **extra)
        with tenant_context(b.tenant_id):
            base, brand = public_base(), branding()
            desc_fa = (brand.bot_description_fa or "").strip()
        if base:
            c.set_chat_menu_button(text=MENU_TEXT, url=base + "/")
        if desc_fa:
            c._call("setMyDescription", description=desc_fa[:512])
        b.state, b.last_error, b.webhook_set_at = TenantBot.OK, "", timezone.now()
    except TelegramError as exc:
        b.state, b.last_error = TenantBot.ERROR, str(exc)[:500]
    b.last_check_at = timezone.now()
    b.save(update_fields=["state", "last_error", "webhook_set_at", "last_check_at", "updated_at"])
    forget(b.tenant_id)
    return b


def check(b: TenantBot) -> TenantBot:
    """getWebhookInfo: our URL? recent delivery errors? A wrong / missing webhook is set again."""
    from apps.telegram.client import TelegramError

    was = b.state
    try:
        info = _client(b.token)._call("getWebhookInfo")
        if info.get("url") != hook_url(b.tenant_id) or (hook_ip() and info.get("ip_address") != hook_ip()):
            return _after_check(apply(b), was)        # wrong URL, or Telegram still resolving our domain (v1.60.1)
        err_at = info.get("last_error_date") or 0
        recent = err_at and timezone.now().timestamp() - err_at < 3600
        if recent and (info.get("pending_update_count") or 0) > 0:
            b.state, b.last_error = TenantBot.ERROR, str(info.get("last_error_message") or "delivery failed")[:500]
        else:
            b.state, b.last_error = TenantBot.OK, ""
    except TelegramError as exc:
        b.state, b.last_error = TenantBot.ERROR, str(exc)[:500]
    b.last_check_at = timezone.now()
    b.save(update_fields=["state", "last_error", "last_check_at", "updated_at"])
    return _after_check(b, was)


def _after_check(b: TenantBot, was: str) -> TenantBot:
    """One alert to US when a store bot breaks, one (silent) when it works again."""
    from apps.common.staff_alert import alert_staff

    name = b.tenant.name
    if b.state == TenantBot.ERROR and b.alerted_at is None:
        alert_staff(f"⚠️ ربات فروشگاه «{name}» (@{b.username}) کار نمی‌کند:\n{b.last_error}", perm="agency.manage",
                    platform=True)
        TenantBot.objects.filter(pk=b.pk).update(alerted_at=timezone.now())
    elif b.state == TenantBot.OK and b.alerted_at is not None:
        alert_staff(f"✅ ربات فروشگاه «{name}» (@{b.username}) دوباره کار می‌کند.", perm="agency.manage",
                    platform=True, silent=True)
        TenantBot.objects.filter(pk=b.pk).update(alerted_at=None)
    return b


def check_all() -> int:
    n = 0
    for b in TenantBot.objects.select_related("tenant").filter(tenant__status=Tenant.ACTIVE):
        try:
            check(b)
            n += 1
        except Exception as exc:  # noqa: BLE001 — one store never stops the others
            log.warning("store bot %s check failed: %s", b.pk, exc)
    return n


def mark_update(tenant_id: int) -> None:
    """Seen an update from Telegram (at most one write a minute per store)."""
    cutoff = timezone.now() - timedelta(minutes=1)
    TenantBot.objects.filter(tenant_id=tenant_id).exclude(last_update_at__gte=cutoff).update(last_update_at=timezone.now())
