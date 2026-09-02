"""
Admin-panel screens for the external integrations the operator must configure
after install: the Pasargad panel connection and the two Telegram bots.

Secrets (panel password, bot tokens) are write-only — a GET never returns them,
only a boolean saying whether one is stored.
"""
from django.conf import settings
from django.core.mail import get_connection, send_mail
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from apps.common.models import write_audit
from apps.panel.exceptions import PanelError
from apps.panel.models import Panel
from apps.panel.services import client_for, get_active_panel
from apps.telegram.models import BotType, TelegramConfig

from ..serializers import PanelConfigSerializer, TelegramConfigSerializer
from .base import AdminAPIView

_BOTS = (BotType.SALES, BotType.BACKUP)


def _panel_row():
    return get_active_panel() or Panel.objects.order_by("id").first()


class PanelConfigView(AdminAPIView):
    """GET / PUT the Pasargad panel connection (base URL + admin credentials)."""

    perms_map = {"GET": ["settings.manage"], "PUT": ["settings.manage"],
                 "PATCH": ["settings.manage"]}

    @extend_schema(responses=PanelConfigSerializer,
                   summary="Pasargad panel connection settings")
    def get(self, request):
        panel = _panel_row()
        if not panel:
            return Response({
                "id": None, "name": "Pasargad", "base_url": "", "admin_username": "",
                "admin_password_set": False, "subscription_base_url": "",
                "verify_ssl": True, "default_group_ids": [], "is_active": True,
                "updated_at": None,
            })
        return Response(PanelConfigSerializer(panel).data)

    def put(self, request):
        return self._save(request, partial=False)

    def patch(self, request):
        return self._save(request, partial=True)

    def _save(self, request, *, partial):
        panel = _panel_row()
        if panel is None:
            ser = PanelConfigSerializer(data=request.data)
        else:
            ser = PanelConfigSerializer(panel, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        obj = ser.save()
        # base URL / credentials may have changed -> drop the cached API token
        Panel.objects.filter(pk=obj.pk).update(token_cache=None, token_expires_at=None)
        write_audit(action="panel.config_updated", target=obj, staff=request.user,
                    detail={"fields": list(request.data.keys())})
        return Response(PanelConfigSerializer(obj).data)


class PanelTestView(AdminAPIView):
    """POST — probe the configured panel with the stored credentials."""

    perms_map = {"POST": ["settings.manage"]}

    @extend_schema(request=None, responses=dict, summary="Test the panel connection")
    def post(self, request):
        panel = _panel_row()
        if not panel or not panel.base_url or not panel.admin_password_enc:
            return Response(
                {"ok": False, "detail": "پنل هنوز کامل پیکربندی نشده است."}, status=400)
        try:
            client_for(panel).check()
        except PanelError as exc:
            return Response({"ok": False, "detail": str(exc)})
        except Exception as exc:  # noqa: BLE001 - never 500 on a probe
            return Response({"ok": False, "detail": str(exc)})
        write_audit(action="panel.tested", target=panel, staff=request.user)
        return Response({"ok": True, "detail": "اتصال با پنل برقرار است."})


class PanelGroupsView(AdminAPIView):
    """GET — the groups a panel exposes (id + name), live.

    `?panel=<id>` targets a specific panel (multi-panel: the plan form fetches
    groups for the plan's own panel); without it, the active/first panel.
    """

    perms_map = {"GET": ["settings.manage"]}

    @extend_schema(request=None, responses=dict,
                   summary="List a panel's groups (live, from GET /api/groups)")
    def get(self, request):
        panel_id = request.query_params.get("panel")
        if panel_id:
            panel = Panel.objects.filter(pk=panel_id).first()
        else:
            panel = _panel_row()
        if not panel or not panel.base_url or not panel.admin_password_enc:
            return Response({"detail": "پنل هنوز کامل پیکربندی نشده است."}, status=400)
        try:
            raw = client_for(panel).list_groups()
        except PanelError as exc:
            return Response({"detail": str(exc)}, status=502)
        except Exception as exc:  # noqa: BLE001
            return Response({"detail": str(exc)}, status=502)
        groups = [
            {"id": g["id"], "name": g.get("name") or g.get("title") or f"group {g['id']}"}
            for g in raw if isinstance(g, dict) and g.get("id") is not None
        ]
        return Response({"groups": groups})


class TelegramConfigView(AdminAPIView):
    """GET / PUT both bot rows at once, keyed by bot type."""

    perms_map = {"GET": ["bots.manage"], "PUT": ["bots.manage"],
                 "PATCH": ["bots.manage"]}
    serializer_class = TelegramConfigSerializer  # schema hint only

    @extend_schema(responses=dict, summary="Both Telegram bot configs (sales + backup)")
    def get(self, request):
        return Response({bt: self._row(bt) for bt in _BOTS})

    @transaction.atomic
    def put(self, request):
        touched = []
        for bt in _BOTS:
            payload = request.data.get(bt)
            if payload is None:
                continue
            cfg, _ = TelegramConfig.objects.get_or_create(bot_type=bt)
            ser = TelegramConfigSerializer(cfg, data=payload, partial=True)
            ser.is_valid(raise_exception=True)
            data = dict(ser.validated_data)
            token = data.pop("token", None)
            for key, value in data.items():
                setattr(cfg, key, value)
            if token:  # blank / omitted -> keep the stored token
                cfg.token = token
            cfg.save()
            touched.append(bt)
        if touched:
            write_audit(action="telegram.config_updated", staff=request.user,
                        detail={"bots": touched})
        return Response({bt: self._row(bt) for bt in _BOTS})

    patch = put

    @staticmethod
    def _row(bot_type):
        cfg = TelegramConfig.objects.filter(bot_type=bot_type).first()
        if not cfg:
            return {"bot_type": bot_type, "token_set": False, "proxy_url": "",
                    "backup_chat_id": None, "is_active": False, "updated_at": None}
        return TelegramConfigSerializer(cfg).data


class _EmailTestSerializer(serializers.Serializer):
    to = serializers.EmailField()


class EmailStatusView(AdminAPIView):
    """Read-only view of the outbound-mail configuration + a 'send test' action.

    Relay credentials themselves live in `.env` (SMTP_RELAY_*) because they are
    consumed by the mailserver container at start-up, not by Django — this screen
    only reports the resulting state and lets the operator send a probe."""

    perms_map = {"GET": ["settings.manage"], "POST": ["settings.manage"]}
    serializer_class = _EmailTestSerializer

    @extend_schema(responses=dict, summary="Outbound email configuration status")
    def get(self, request):
        host = settings.EMAIL_HOST or ""
        backend = settings.EMAIL_BACKEND
        inert = ("dummy" in backend) or ("console" in backend)
        via_local_mailserver = host in ("mailserver", "mail", "localhost", "127.0.0.1")
        relay = bool(getattr(settings, "SMTP_RELAY_HOST", ""))
        return Response({
            "configured": bool(host) and not inert,
            "backend": backend.rsplit(".", 2)[-2] if "." in backend else backend,
            "host": host,
            "port": settings.EMAIL_PORT,
            "use_tls": settings.EMAIL_USE_TLS,
            "from_address": settings.DEFAULT_FROM_EMAIL,
            "via_local_mailserver": via_local_mailserver,
            "relay_configured": relay,
            "relay_host": getattr(settings, "SMTP_RELAY_HOST", "") or "",
            # external delivery needs EITHER a direct provider host OR a relay
            "external_delivery_ready": bool(host) and not inert and (relay or not via_local_mailserver),
            "verification_required": _verification_required(),
        })

    @extend_schema(request=_EmailTestSerializer, responses=dict,
                   summary="Send a test email to the given address")
    def post(self, request):
        ser = _EmailTestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        to = ser.validated_data["to"]
        if not settings.EMAIL_HOST:
            return Response({"ok": False, "detail": "EMAIL_HOST پیکربندی نشده است."}, status=400)
        try:
            sent = send_mail(
                subject=f"{settings.PROJECT_NAME} — test email",
                message="This is a test message from your caspintunel admin panel.\n",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to],
                connection=get_connection(fail_silently=False),
                fail_silently=False,
            )
        except Exception as exc:  # noqa: BLE001 - report the SMTP error verbatim
            return Response({"ok": False, "detail": str(exc)})
        write_audit(action="email.test_sent", staff=request.user, detail={"to": to})
        if not sent:
            return Response({"ok": False, "detail": "ارسال انجام نشد (۰ پیام)."})
        return Response({
            "ok": True,
            "detail": "به میل‌سرور تحویل شد. اگر به صندوق ورودی نرسید، لاگ mailserver را بررسی کنید.",
        })


def _verification_required() -> bool:
    from apps.settings_app.utils import get_setting

    return bool(get_setting("email_verification_required", False))
