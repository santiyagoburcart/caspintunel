from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework import authentication, exceptions, permissions

from .models import SmsAppDevice


class SmsDeviceAuthentication(authentication.BaseAuthentication):
    """
    Authenticates the Android SMS app by its per-device token (never the admin
    password). Token goes in `X-Device-Token` or `Authorization: Device <token>`.

    On success `request.user` and `request.auth` are both the `SmsAppDevice`.
    """

    def authenticate(self, request):
        token = request.META.get("HTTP_X_DEVICE_TOKEN", "").strip()
        if not token:
            header = authentication.get_authorization_header(request).split()
            if len(header) == 2 and header[0].lower() == b"device":
                token = header[1].decode()
        if not token:
            return None

        try:
            device = SmsAppDevice.objects.get(api_token=token, is_active=True)
        except SmsAppDevice.DoesNotExist:
            raise exceptions.AuthenticationFailed("invalid or disabled device token")

        SmsAppDevice.objects.filter(pk=device.pk).update(last_seen_at=timezone.now())
        # keep request.user a real (anonymous) user; the device is on request.auth
        return (AnonymousUser(), device)

    def authenticate_header(self, request):
        return "Device"


class IsSmsDevice(permissions.BasePermission):
    message = "a valid SMS-app device token is required"

    def has_permission(self, request, view):
        return isinstance(request.auth, SmsAppDevice)


try:  # document the scheme for drf-spectacular (optional dependency at import time)
    from drf_spectacular.extensions import OpenApiAuthenticationExtension

    class SmsDeviceAuthScheme(OpenApiAuthenticationExtension):
        target_class = "apps.payments_sms.authentication.SmsDeviceAuthentication"
        name = "SmsDeviceToken"

        def get_security_definition(self, auto_schema):
            return {"type": "apiKey", "in": "header", "name": "X-Device-Token"}
except ImportError:  # pragma: no cover
    pass
