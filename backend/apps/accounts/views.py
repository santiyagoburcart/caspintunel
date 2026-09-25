import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.common.models import write_audit

from . import services
from .phone import PhoneError, clean_site_phone
from .serializers import (
    ChangePasswordSerializer,
    EmailVerifyConfirmSerializer,
    EmptySerializer,
    LegacyImportSerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    TelegramMiniAppSerializer,
    UserSerializer,
)
from .telegram_auth import InitDataError, sales_bot_token, validate_init_data

log = logging.getLogger("caspintunel")
User = get_user_model()


class RegisterView(GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer
    throttle_scope = "auth"

    @extend_schema(summary="Register a new user (flowchart 1.1)")
    def post(self, request):
        ser = self.get_serializer(data=request.data, context={"source": "site"})
        ser.is_valid(raise_exception=True)
        user = ser.save()
        email_status = services.dispatch_verification(user)
        write_audit(action="user.registered", target=user, detail={"email_status": email_status})

        refresh = RefreshToken.for_user(user)
        messages = {
            "not_sent": "Account created. The verification email could not be sent right now; "
                        "you can continue and verify later.",
            "skipped": "Account created.",
            "sent": "Account created. Check your inbox to verify your email.",
            "no_email": "Account created. Add an email later to enable email features.",
        }
        return Response(
            {
                "user": UserSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "email_status": email_status,
                "detail": messages.get(email_status, "Account created."),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_scope = "auth"


class TelegramMiniAppLoginView(GenericAPIView):
    """
    Exchange a validated Telegram Mini App `initData` for a normal user JWT.

    initData's HMAC is verified against the sales-bot token server-side
    (`telegram_auth.validate_init_data`); only then is the Telegram user linked
    to a site account (existing `telegram_id`, else created exactly like the
    first-time bot user — random `tg_*` username, `source=bot`). The token that
    comes back is an ordinary SimpleJWT pair: a Mini App session has the same
    permissions as any other logged-in customer, nothing more.
    """

    permission_classes = [permissions.AllowAny]
    serializer_class = TelegramMiniAppSerializer
    throttle_scope = "auth"

    @extend_schema(summary="Start a session from Telegram Mini App initData")
    def post(self, request):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)

        token = sales_bot_token()
        if not token:
            return Response(
                {"detail": "the Telegram mini app is not configured yet "
                           "(set the sales bot token in the admin panel)"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            parsed = validate_init_data(
                ser.validated_data["init_data"],
                bot_token=token,
                max_age_seconds=settings.MINIAPP_INITDATA_MAX_AGE,
                debug=settings.DEBUG,
            )
        except InitDataError as exc:
            log.warning("mini app initData rejected: %s", exc)
            return Response(
                {"detail": f"invalid Telegram session ({exc})"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        tg = parsed["user"]
        from apps.telegram.accounts import ensure_bot_user

        user, created, _pw = ensure_bot_user(
            int(tg["id"]),
            telegram_username=tg.get("username") or "",
            name=" ".join(filter(None, [tg.get("first_name"), tg.get("last_name")])) or None,
        )
        if not user.is_active:
            return Response({"detail": "this account is disabled"},
                            status=status.HTTP_403_FORBIDDEN)

        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        refresh = RefreshToken.for_user(user)
        write_audit(action="user.miniapp_session", target=user,
                    detail={"telegram_id": int(tg["id"]), "created": created})
        return Response({
            "user": UserSerializer(user).data,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "created": created,
        })


class LogoutView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LogoutSerializer

    @extend_schema(summary="Blacklist the given refresh token")
    def post(self, request):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            RefreshToken(ser.validated_data["refresh"]).blacklist()
        except TokenError:
            return Response({"detail": "invalid or already-expired token"}, status=400)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get(self, request):
        return Response(self.get_serializer(request.user).data)

    @extend_schema(summary="Update own profile (name, phone, email, language, cards)")
    def patch(self, request):
        user = request.user
        editable = {"name", "phone", "email", "language", "bank_card_number", "telegram_username"}
        data = {k: v for k, v in request.data.items() if k in editable}
        new_email = data.get("email")
        if new_email and new_email != user.email:
            if User.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
                return Response({"email": ["email already registered"]}, status=400)
            user.email = new_email
            user.email_verified = False
        if "phone" in data:
            try:
                data["phone"] = clean_site_phone(data["phone"], exclude_pk=user.pk)
            except PhoneError as exc:
                return Response({"phone": [str(exc)], "code": exc.code}, status=400)
        for k in editable - {"email"}:
            if k in data:
                setattr(user, k, data[k])
        user.save()
        resent = None
        if new_email and new_email != "":
            resent = services.dispatch_verification(user)
        return Response({"user": self.get_serializer(user).data, "email_status": resent})


class ChangePasswordView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        ser = self.get_serializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        request.user.set_password(ser.validated_data["new_password"])
        request.user.save(update_fields=["password", "updated_at"])
        write_audit(action="password.changed", target=request.user)
        # a new password revokes every existing token (CHECK_REVOKE_TOKEN) —
        # hand this session fresh ones so only the *other* sessions end
        refresh = RefreshToken.for_user(request.user)
        return Response({"detail": "password updated",
                         "access": str(refresh.access_token), "refresh": str(refresh)})


class EmailVerifyResendView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EmptySerializer
    throttle_scope = "auth"

    @extend_schema(summary="Resend the verification email", request=None)
    def post(self, request):
        if request.user.email_verified:
            return Response({"detail": "already verified"})
        result = services.dispatch_verification(request.user)
        return Response({"email_status": result})


class EmailVerifyConfirmView(GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = EmailVerifyConfirmSerializer
    throttle_scope = "auth"

    def post(self, request):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            user = services.confirm_email(ser.validated_data["token"])
        except signing.SignatureExpired:
            return Response({"detail": "verification link expired"}, status=400)
        except (signing.BadSignature, User.DoesNotExist):
            return Response({"detail": "invalid verification link"}, status=400)
        return Response({"detail": "email verified", "user": UserSerializer(user).data})


class PasswordResetRequestView(GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetRequestSerializer
    throttle_scope = "auth"

    @extend_schema(summary="Request a password reset — email path (flowchart 1.6)")
    def post(self, request):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = services.start_password_reset(ser.validated_data["identifier"])
        detail = (
            "If the account exists, a reset link has been emailed."
            if result["email_sent"]
            else "Email reset is unavailable. Use the Telegram bot or contact an admin."
        )
        return Response({**result, "detail": detail})


class PasswordResetConfirmView(GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetConfirmSerializer
    throttle_scope = "auth"

    def post(self, request):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            services.confirm_password_reset(
                ser.validated_data["token"], ser.validated_data["new_password"]
            )
        except signing.SignatureExpired:
            return Response({"detail": "reset link expired"}, status=400)
        except (signing.BadSignature, User.DoesNotExist):
            return Response({"detail": "invalid reset link"}, status=400)
        return Response({"detail": "password has been reset"})


class LegacyImportView(GenericAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = LegacyImportSerializer

    @extend_schema(summary="Bulk-import legacy users (admin only)")
    def post(self, request):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        summary = services.import_legacy_users(
            ser.validated_data["users"],
            overwrite=ser.validated_data["overwrite"],
            staff=request.user,
        )
        return Response(summary, status=status.HTTP_201_CREATED)
