import jwt
from rest_framework import authentication, exceptions, permissions

from apps.accounts.models import Staff

from .tokens import decode


class StaffJWTAuthentication(authentication.BaseAuthentication):
    """`Authorization: Bearer <staff access token>` -> request.user = Staff."""

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if len(header) != 2 or header[0].lower() != b"bearer":
            return None
        try:
            payload = decode(header[1].decode(), "staff_access")
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("token expired")
        except jwt.InvalidTokenError:
            return None  # not a staff token — let other authenticators try
        staff = Staff.objects.filter(pk=payload["staff_id"], is_active=True).select_related("role").first()
        if not staff:
            raise exceptions.AuthenticationFailed("staff account not found or disabled")
        return (staff, payload)

    def authenticate_header(self, request):
        return "Bearer"


class StaffPermission(permissions.BasePermission):
    """
    Grants access to an authenticated `Staff` holding the permission codes the
    view declares (superadmins bypass). A Django superuser authenticated by the
    normal customer JWT / session is also allowed — a bootstrap "break-glass".

    A view declares needs via `perms_map = {"GET": [...], "POST": [...]}` or a
    flat `required_perms = [...]`.
    """

    def has_permission(self, request, view):
        user = request.user
        if isinstance(user, Staff):
            if user.is_superadmin:
                return True
            return all(user.has_perm(code) for code in self._needed(request, view))
        return bool(getattr(user, "is_superuser", False) and getattr(user, "is_authenticated", False))

    @staticmethod
    def _needed(request, view):
        mapping = getattr(view, "perms_map", None)
        if mapping:
            return mapping.get(request.method, mapping.get("*", []))
        return getattr(view, "required_perms", [])


try:
    from drf_spectacular.extensions import OpenApiAuthenticationExtension

    class StaffJWTScheme(OpenApiAuthenticationExtension):
        target_class = "apps.adminpanel.permissions.StaffJWTAuthentication"
        name = "StaffJWT"

        def get_security_definition(self, auto_schema):
            return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
except ImportError:  # pragma: no cover
    pass
