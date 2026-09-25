"""Admin panel → Settings → Email: outgoing-mail relay (EmailSettings) + test send.

Django sends straight to the relay (apps.common.mail.DynamicEmailBackend); the
web app never reconfigures or restarts the mailserver container."""
from django.conf import settings
from django.core.mail import EmailMessage
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from apps.common.mail import LOCAL_HOSTS, describe_smtp_error, resolve_mail_config
from apps.common.models import write_audit
from apps.settings_app.models import EmailSecurity, EmailSettings

from .base import AdminAPIView

AUDITED = ("enabled", "host", "port", "security", "username", "from_email", "from_name")


class EmailSettingsSerializer(serializers.ModelSerializer):
    # write-only, never serialized back; blank = keep the stored one
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=False)
    clear_password = serializers.BooleanField(write_only=True, required=False, default=False)
    password_set = serializers.SerializerMethodField()

    class Meta:
        model = EmailSettings
        fields = ("enabled", "host", "port", "security", "username", "password", "clear_password",
                  "password_set", "from_email", "from_name",
                  "last_success_at", "last_error", "last_error_at", "last_source", "updated_at")
        read_only_fields = ("last_success_at", "last_error", "last_error_at", "last_source", "updated_at")

    def get_password_set(self, obj) -> bool:
        return bool(obj.password)

    def validate_host(self, v):
        v = (v or "").strip()
        if " " in v or "/" in v or ":" in v:
            raise serializers.ValidationError("host name only — no scheme, path or port")
        return v

    def validate_port(self, v):
        if not 1 <= v <= 65535:
            raise serializers.ValidationError("1–65535")
        return v

    def validate(self, attrs):
        inst = self.instance
        enabled = attrs.get("enabled", inst.enabled if inst else False)
        host = attrs.get("host", inst.host if inst else "")
        if enabled and not host:
            raise serializers.ValidationError({"host": "required to enable the relay"})
        if enabled and host in LOCAL_HOSTS:
            raise serializers.ValidationError({"host": "use the provider's SMTP host, not the local mailserver"})
        return attrs

    def update(self, instance, validated):
        pwd = validated.pop("password", "")
        clear = validated.pop("clear_password", False)
        for k, v in validated.items():
            setattr(instance, k, v)
        if pwd:
            instance.password = pwd
        elif clear:
            instance.password = ""
        instance.save()
        return instance


def _status(obj: EmailSettings) -> dict:
    cfg = resolve_mail_config()
    return {
        "effective_source": cfg.source,          # db | env | local | none
        "effective_host": cfg.host,
        "effective_port": cfg.port,
        "env_host": settings.EMAIL_HOST or "",
        "default_from": settings.DEFAULT_FROM_EMAIL,
        "securities": [c for c, _ in EmailSecurity.choices],
    }


class EmailSettingsView(AdminAPIView):
    perms_map = {"GET": ["settings.email"], "PUT": ["settings.email"], "PATCH": ["settings.email"]}
    serializer_class = EmailSettingsSerializer

    @extend_schema(responses=EmailSettingsSerializer, summary="Outgoing email (SMTP relay) settings")
    def get(self, request):
        obj = EmailSettings.load()
        return Response({**EmailSettingsSerializer(obj).data, **_status(obj)})

    @extend_schema(request=EmailSettingsSerializer, responses=EmailSettingsSerializer,
                   summary="Update the SMTP relay (password write-only)")
    def put(self, request):
        obj = EmailSettings.load()
        before = {k: getattr(obj, k) for k in AUDITED}
        ser = EmailSettingsSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        pwd_change = ("set" if request.data.get("password") else
                      "cleared" if ser.validated_data.get("clear_password") and obj.password else None)
        obj = ser.save()
        changed = {k: {"from": before[k], "to": getattr(obj, k)} for k in AUDITED if before[k] != getattr(obj, k)}
        if pwd_change:
            changed["password"] = pwd_change          # never the value
        if changed:
            write_audit(action="email.settings_updated", staff=request.user, target=obj, detail=changed)
        return Response({**EmailSettingsSerializer(obj).data, **_status(obj)})

    patch = put


class _TestSerializer(serializers.Serializer):
    to = serializers.EmailField()


class EmailTestView(AdminAPIView):
    """Send one message through the SAVED settings and report the real result."""

    perms_map = {"POST": ["settings.email"]}
    serializer_class = _TestSerializer

    @extend_schema(request=_TestSerializer, responses=dict, summary="Send a test email via the saved settings")
    def post(self, request):
        ser = _TestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        to = ser.validated_data["to"]
        cfg = resolve_mail_config()
        base = {"source": cfg.source, "host": cfg.host, "port": cfg.port}
        if not cfg.configured:
            return Response({**base, "ok": False, "code": "not_configured",
                             "fa": "هیچ سرور SMTP تنظیم نشده است.", "en": "No SMTP server is configured.",
                             "raw": ""})
        msg = EmailMessage(
            subject=f"{settings.PROJECT_NAME} — test email",
            body="This is a test message from the caspintunel admin panel (Settings → Email).\n",
            from_email=settings.DEFAULT_FROM_EMAIL, to=[to],
        )
        try:
            sent = msg.send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001 - the operator needs the real reason
            d = describe_smtp_error(exc)
            write_audit(action="email.test_failed", staff=request.user, detail={"to": to, "code": d["code"]})
            return Response({**base, "ok": False, **d})
        write_audit(action="email.test_sent", staff=request.user, detail={"to": to, "source": cfg.source})
        ok = bool(sent)
        return Response({
            **base, "ok": ok, "code": "sent" if ok else "not_sent", "raw": "",
            "fa": "ایمیل توسط سرور SMTP پذیرفته شد. صندوق ورودی (و پوشهٔ اسپم) را بررسی کنید." if ok else "ارسال انجام نشد.",
            "en": "Accepted by the SMTP server. Check the inbox (and spam folder)." if ok else "Not sent.",
        })
