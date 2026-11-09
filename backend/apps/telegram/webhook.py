"""POST /api/v1/telegram/hook/<tenant id>/ — Telegram → a store's bot (v1.49, multi-tenant Phase 6, docs/multi-tenant.md §6.4).

Only on OUR hosts (blocked on store domains, tenancy/middleware.py). The `X-Telegram-Bot-Api-Secret-Token` header must equal
that store's `TenantBot.webhook_secret` (constant time) — else 403 and nothing is read. A store that is not active, or has
no bot, gets 200 and the update is dropped (Telegram would only retry). `update_id` is accepted once (24 h). The update
itself runs in Celery inside the store's tenant context (`store_bot_update_task`) so Telegram gets its answer at once.
"""
from __future__ import annotations

import hmac
import json
import logging

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

log = logging.getLogger("caspintunel")
MAX_BODY = 256 * 1024
DEDUPE_TTL = 24 * 3600


@csrf_exempt
@require_POST
def store_bot_hook(request, tenant_id: int):
    from apps.tenancy.models import Tenant, TenantBot

    b = TenantBot.objects.select_related("tenant").filter(tenant_id=tenant_id).first()
    given = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if b is None or not given or not hmac.compare_digest(given.encode(), (b.webhook_secret or "").encode()):
        return JsonResponse({"ok": False}, status=403)
    if b.tenant.status != Tenant.ACTIVE:
        return HttpResponse(status=200)                      # suspended / closed: drop, never serve
    if len(request.body) > MAX_BODY:
        return HttpResponse(status=200)
    try:
        update = json.loads(request.body or b"{}")
        update_id = int(update["update_id"])
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"ok": False}, status=400)
    if not cache.add(f"tghook:{tenant_id}:{update_id}", 1, DEDUPE_TTL):
        return HttpResponse(status=200)                      # Telegram retried one we already have
    from apps.tenancy import bots
    from apps.tenancy.context import tenant_context

    from .tasks import store_bot_update_task

    with tenant_context(tenant_id):                          # the task runs in the store (header caspin_tenant)
        store_bot_update_task.delay(tenant_id, update)
    bots.mark_update(tenant_id)
    return HttpResponse(status=200)
