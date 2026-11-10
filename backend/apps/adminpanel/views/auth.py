import jwt
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import GROUP_MANAGER_PERM, Staff
from apps.common.auth_reset import FreshAuthMixin

from ..permissions import StaffJWTAuthentication
from ..tokens import decode, issue_tokens, revoke_refresh, staff_for_payload


class StaffLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class StaffLoginView(FreshAuthMixin, APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(request=StaffLoginSerializer, responses=dict, summary="Panel operator login")
    def post(self, request):
        ser = StaffLoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        staff = Staff.objects.filter(username=ser.validated_data["username"]).first()
        from ..tokens import store_staff_here

        if staff is not None and not store_staff_here(staff):
            staff = None                # v1.52: a store's staff sign in on that store's domain only (same answer as unknown)
        if not staff or not staff.check_password(ser.validated_data["password"]):
            return Response(
                {"detail": "invalid credentials", "code": "invalid_credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not staff.is_active:
            # only revealed once the password already matched, so a guess can't
            # be used to probe which usernames exist
            return Response(
                {"detail": "account is disabled", "code": "account_disabled"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        staff.touch_login()
        return Response({**issue_tokens(staff), "staff": _staff_payload(staff)})


class StaffRefreshView(FreshAuthMixin, APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(request=RefreshSerializer, responses=dict,
                   summary="Exchange a refresh token for a new access token")
    def post(self, request):
        try:
            payload = decode(request.data.get("refresh", ""), "staff_refresh")
        except jwt.ExpiredSignatureError:
            return Response({"detail": "refresh token expired", "code": "token_expired"}, status=401)
        except jwt.InvalidTokenError:
            return Response({"detail": "invalid refresh token", "code": "token_invalid"}, status=401)
        staff = staff_for_payload(payload)
        if not staff:
            return Response(
                {"detail": "session ended or staff account disabled — log in again", "code": "token_revoked"},
                status=401,
            )
        # rotation — the presented refresh token is now spent (single use)
        if not revoke_refresh(payload):
            return Response({"detail": "invalid refresh token", "code": "token_invalid"}, status=401)
        return Response(issue_tokens(staff))


class StaffLogoutView(FreshAuthMixin, APIView):
    """Revoke the panel's refresh token (v1.30.2: logout used to only forget it in the
    browser, leaving it valid for its 7 days). Always 200 — an unknown, expired or
    already-spent token has nothing left to revoke."""

    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(request=RefreshSerializer, responses=dict, summary="Panel operator logout")
    def post(self, request):
        try:
            payload = decode(request.data.get("refresh", ""), "staff_refresh")
        except jwt.InvalidTokenError:          # includes expired / already revoked
            payload = None
        if payload:
            revoke_refresh(payload)
        return Response({"ok": True})


class StaffMeView(APIView):
    authentication_classes = [StaffJWTAuthentication]

    def get_permissions(self):
        from rest_framework.permissions import IsAuthenticated

        return [IsAuthenticated()]

    @extend_schema(responses=dict, summary="Current operator's profile + permissions")
    def get(self, request):
        return Response(_staff_payload(request.user))


def _staff_payload(staff: Staff) -> dict:
    gm = staff.group_manager_row if staff.is_group_manager else None
    if staff.tenant_id:
        # v1.52 (Phase 8): a store's staff — its role's codes within the store's ceiling (never "*")
        from apps.tenancy.staff import ceiling

        cap = ceiling(staff.tenant_id)
        perms = [c for c in staff.role.permissions.values_list("code", flat=True) if c in cap] if staff.role_id else []
    elif staff.is_superadmin:
        perms = ["*"]
    elif gm is not None:
        perms = [GROUP_MANAGER_PERM, *staff.gm_permissions()]   # v1.27: + its agency.gm.* abilities (Staff.has_perm)
    elif staff.role_id:
        perms = list(staff.role.permissions.values_list("code", flat=True))
    else:
        perms = []
    return {
        "id": staff.id,
        "username": staff.username,
        "role": staff.role.name if staff.role_id else None,
        "role_fa": (staff.role.name_fa or "") if staff.role_id else "",
        "is_superadmin": staff.is_superadmin and not staff.tenant_id,
        "store_staff": bool(staff.tenant_id),           # v1.52: a reseller store's own staff (not ours)
        "permissions": perms,
        "last_login": staff.last_login,
        # v1.33: panel sound preferences (views/push.py)
        "notify_prefs": _prefs(staff),
        # v1.25: the panel shows a group manager only its own menu (Agency pages scoped to its groups)
        "group_manager": ({"id": gm.id, "username": gm.username, "display_name": gm.display_name}
                          if gm is not None else None),
        # v1.43: the panel runs in store mode on a reseller store's domain (store menu, store data only)
        "store": _store(),
    }


def _store():
    from apps.settings_app.branding import current_tenant, is_store

    if not is_store():
        return None
    t = current_tenant()
    return {"id": t.id, "slug": t.slug, "name": t.name, "status": t.status, "reseller": t.reseller_username} if t else None


def _prefs(staff) -> dict:
    from .push import staff_prefs

    return staff_prefs(staff)
