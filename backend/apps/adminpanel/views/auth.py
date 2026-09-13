import jwt
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Staff

from ..permissions import StaffJWTAuthentication
from ..tokens import decode, issue_tokens, revoke_refresh


class StaffLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class StaffLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(request=StaffLoginSerializer, responses=dict, summary="Panel operator login")
    def post(self, request):
        ser = StaffLoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        staff = Staff.objects.filter(username=ser.validated_data["username"]).first()
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


class StaffRefreshView(APIView):
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
        staff = Staff.objects.filter(pk=payload["staff_id"], is_active=True).first()
        if not staff:
            return Response(
                {"detail": "staff account not found or disabled", "code": "account_disabled"}, status=401
            )
        revoke_refresh(payload)  # rotation — the presented refresh token is now spent
        return Response(issue_tokens(staff))


class StaffMeView(APIView):
    authentication_classes = [StaffJWTAuthentication]

    def get_permissions(self):
        from rest_framework.permissions import IsAuthenticated

        return [IsAuthenticated()]

    @extend_schema(responses=dict, summary="Current operator's profile + permissions")
    def get(self, request):
        return Response(_staff_payload(request.user))


def _staff_payload(staff: Staff) -> dict:
    if staff.is_superadmin:
        perms = ["*"]
    elif staff.role_id:
        perms = list(staff.role.permissions.values_list("code", flat=True))
    else:
        perms = []
    return {
        "id": staff.id,
        "username": staff.username,
        "role": staff.role.name if staff.role_id else None,
        "is_superadmin": staff.is_superadmin,
        "permissions": perms,
        "last_login": staff.last_login,
    }
