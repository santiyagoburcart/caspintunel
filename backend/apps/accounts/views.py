import logging

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
    UserSerializer,
)

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
        return Response({"detail": "password updated"})


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
