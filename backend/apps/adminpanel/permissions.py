import jwt
from rest_framework import authentication, exceptions, permissions

from apps.accounts.models import Staff

from .tokens import decode, staff_for_payload


class StaffJWTAuthentication(authentication.BaseAuthentication):
    """`Authorization: Bearer <staff access token>` -> request.user = Staff."""

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if len(header) != 2 or header[0].lower() != b"bearer":
            return None
        try:
            payload = decode(header[1].decode(), "staff_access")
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed({"detail": "token expired", "code": "token_expired"})
        except jwt.InvalidTokenError:
            return None  # not a staff token — let other authenticators try
        staff = staff_for_payload(payload)
        if not staff:
            raise exceptions.AuthenticationFailed(
                {"detail": "session ended or staff account disabled — log in again", "code": "token_revoked"}
            )
        return (staff, payload)

    def authenticate_header(self, request):
        return "Bearer"


class RefuseManagerToken(authentication.BaseAuthentication):
    """A group-manager token (`Authorization: Manager …`, apps/agency/managers.py) on the
    staff API is answered 403 — managers never get into the site panel."""

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if header and header[0].lower() == b"manager":
            raise exceptions.PermissionDenied({"detail": "group managers cannot use the site panel", "code": "forbidden"})
        return None


class StaffPermission(permissions.BasePermission):
    """
    Grants access to an authenticated `Staff` holding the permission codes the
    view declares (superadmins bypass). A Django superuser authenticated by the
    normal customer JWT / session is also allowed — a bootstrap "break-glass".

    A view declares needs via `perms_map = {"GET": [...], "POST": [...]}` or a
    flat `required_perms = [...]`; a viewset may override single actions with
    `action_perms = {"<action>": [...]}`.

    A staff linked to a group manager (role "Group manager", v1.25) is refused on
    every view unless the view sets `group_manager_ok = True` — those views scope
    their data to the manager's groups themselves.
    """

    def has_permission(self, request, view):
        user = request.user
        if isinstance(user, Staff):
            if user.is_superadmin:
                return True
            if user.is_group_manager:
                # default-deny: a group manager reaches only views that opt in
                return bool(getattr(view, "group_manager_ok", False))
            return all(user.has_perm(code) for code in self._needed(request, view))
        return bool(getattr(user, "is_superuser", False) and getattr(user, "is_authenticated", False))

    @staticmethod
    def _needed(request, view):
        # per-action override for viewset actions, e.g. {"destroy_user": ["users.delete"]}
        by_action = getattr(view, "action_perms", None)
        if by_action and getattr(view, "action", None) in by_action:
            return by_action[view.action]
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


class IsGroupManagerStaff(permissions.BasePermission):
    """Staff signed in as a group manager (active, linked GroupManager row, active
    manager). Superadmins and other staff are refused: this API is the manager's own."""

    message = "group managers only"

    def has_permission(self, request, view):
        user = request.user
        if not isinstance(user, Staff) or not user.is_active or not user.is_group_manager:
            return False
        return bool(user.group_manager_row.is_active)
