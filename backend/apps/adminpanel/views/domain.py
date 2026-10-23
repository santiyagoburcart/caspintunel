"""Settings → Domain & Cloudflare (docs/domain.md). Super admins only.

GET  domain/                         state: current domain, token status, wizard, history, host result
POST domain/token/        {token}    save the Cloudflare token (encrypted, write-only; "" clears it)
POST domain/token/test/   {token?}   verify a typed token, else the saved / .env one
POST domain/settings/     {transition_days}
POST domain/start/        {domain, include_www, mode: cloudflare|manual, zone_id}
POST domain/<id>/<step>/  dns | dns-check | tls | mail | mail-check | apply | retire | cancel | checklist {key, done}
POST domain/rollback/                back to the previous domain
"""
from rest_framework.response import Response

from apps.settings_app import domain as D
from apps.settings_app.models import DomainChange, DomainConfig

from .base import AdminAPIView


class _Super(AdminAPIView):
    perms_map = {"GET": ["settings.manage"], "POST": ["settings.manage"]}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        u = request.user
        if not (getattr(u, "is_superadmin", False) or getattr(u, "is_superuser", False)):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("only a super admin can change the domain")

    DONE = {"dns_apply": ("DNS records saved", "رکوردهای DNS ذخیره شد"), "dns_check": ("DNS checked", "DNS بررسی شد"),
            "mail_publish": ("Mail records saved", "رکوردهای ایمیل ذخیره شد"), "mail_check": ("Mail DNS checked", "DNS ایمیل بررسی شد"),
            "request_tls": ("Certificate requested — the server handles it within a minute", "درخواست گواهی ثبت شد — تا یک دقیقه انجام می‌شود"),
            "request_apply": ("Switch queued — the server applies it within a minute", "انتقال در صف است — تا یک دقیقه اعمال می‌شود"),
            "request_retire": ("Removal of the old domain queued", "حذف دامنهٔ قبلی در صف است"),
            "request_rollback": ("Rollback queued — the server applies it within a minute", "بازگشت در صف است — تا یک دقیقه اعمال می‌شود"),
            "start": ("Domain change started", "تغییر دامنه شروع شد"), "cancel": ("Cancelled", "لغو شد")}

    def run(self, fn, *args, **kwargs):
        D.sync()                      # fold in a host result first, so a step sees the latest state
        if args and isinstance(args[0], DomainChange):
            args[0].refresh_from_db()
        try:
            fn(*args, **kwargs)
        except D.DomainError as exc:
            return Response({"detail": str(exc), **D.state()}, status=400)
        msg = self.DONE.get(fn.__name__)
        return Response({**D.state(), **({"message": msg[0], "message_fa": msg[1]} if msg else {})})


class DomainView(_Super):
    def get(self, request):
        return Response(D.state())


class DomainTokenView(_Super):
    def post(self, request, test=False):
        token = (request.data.get("token") or "").strip()
        if test:
            return Response(D.test_token(token or None, request.user))
        if "token" not in request.data:
            return Response({"token": ["required (empty to remove)"]}, status=400)
        if token and (len(token) < 20 or len(token) > 200 or any(c.isspace() for c in token)):
            return Response({"token": ["does not look like a Cloudflare API token"]}, status=400)
        D.save_token(token, request.user)
        return Response(D.state())


class DomainSettingsView(_Super):
    def post(self, request):
        try:
            days = int(request.data.get("transition_days"))
        except (TypeError, ValueError):
            days = -1
        if not 0 <= days <= 90:
            return Response({"transition_days": ["0–90 days"]}, status=400)
        cfg = DomainConfig.load()
        cfg.transition_days = days
        cfg.save(update_fields=["transition_days", "updated_at"])
        D._audit("settings", request.user, transition_days=days)
        return Response(D.state())


class DomainStartView(_Super):
    def post(self, request):
        d = request.data
        return self.run(D.start, domain=d.get("domain", ""), include_www=d.get("include_www", True) not in (False, "false", 0),
                        mode=d.get("mode", "cloudflare"), zone_id=d.get("zone_id", "") or "", by=request.user)


class DomainRollbackView(_Super):
    def post(self, request):
        return self.run(D.request_rollback, request.user)


class DomainStepView(_Super):
    ACTIONS = {"dns": D.dns_apply, "dns-check": D.dns_check, "mail": D.mail_publish, "mail-check": D.mail_check, "tls": D.request_tls, "apply": D.request_apply,
               "retire": D.request_retire, "cancel": D.cancel}

    def post(self, request, pk, step):
        change = DomainChange.objects.filter(pk=pk).first()
        if not change:
            return Response({"detail": "not found"}, status=404)
        if step == "checklist":
            return self.run(D.set_checklist, change, request.data.get("key"), request.data.get("done"), request.user)
        fn = self.ACTIONS.get(step)
        if not fn:
            return Response({"detail": "unknown step"}, status=404)
        return self.run(fn, change, request.user)
