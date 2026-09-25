from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Source
from .phone import PhoneError, clean_site_phone

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    referral_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "email_verified", "name", "phone",
            "telegram_id", "telegram_username", "bank_card_number",
            "referral_code", "referral_count", "source", "language",
            "is_legacy", "is_active", "created_at",
        )
        read_only_fields = (
            "id", "email_verified", "referral_code", "referral_count",
            "source", "is_legacy", "is_active", "created_at", "telegram_id",
        )


class RegisterSerializer(serializers.Serializer):
    username = serializers.RegexField(r"^[A-Za-z0-9_.]{3,64}$")
    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    referral_code = serializers.CharField(max_length=6, required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("username already taken")
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("email already registered")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_phone(self, value):
        try:
            return clean_site_phone(value)
        except PhoneError as exc:
            raise serializers.ValidationError(str(exc), code=exc.code)

    def validate_referral_code(self, value):
        if not value:
            return value
        value = value.upper()
        if not User.objects.filter(referral_code=value).exists():
            raise serializers.ValidationError("invalid referral code")
        return value

    def validate(self, attrs):
        if "phone" not in attrs:
            # field omitted entirely — still enforce "required" under iran_phone_only
            try:
                attrs["phone"] = clean_site_phone("")
            except PhoneError as exc:
                raise serializers.ValidationError({"phone": [str(exc)]}, code=exc.code)
        if not attrs.get("referral_code"):
            from apps.settings_app.utils import get_setting

            if get_setting("referral_required", False):
                raise serializers.ValidationError(
                    {"referral_code": "a referral code is required to register"}
                )
        return attrs

    def create(self, validated):
        referrer = None
        code = validated.get("referral_code")
        if code:
            referrer = User.objects.filter(referral_code=code).first()
        user = User.objects.create_user(
            username=validated["username"],
            password=validated["password"],
            email=validated.get("email") or None,
            name=validated.get("name", ""),
            phone=validated.get("phone", ""),
            referred_by=referrer,
            source=self.context.get("source", Source.SITE),
        )
        return user


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("current password is incorrect")
        return value

    def validate_new_password(self, value):
        validate_password(value, self.context["request"].user)
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(help_text="username or email")


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)

    def validate_new_password(self, value):
        validate_password(value)
        return value


class EmailVerifyConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()


class LoginSerializer(TokenObtainPairSerializer):
    """JWT login that also returns the user profile."""

    def validate(self, attrs):
        try:
            data = super().validate(attrs)
        except AuthenticationFailed:
            # Django's ModelBackend already refuses an inactive user before we
            # get here, so a wrong password and a disabled account both land in
            # this except — check the password ourselves to tell them apart.
            username = attrs.get(self.username_field)
            candidate = User.objects.filter(**{self.username_field: username}).first()
            if candidate and not candidate.is_active and candidate.check_password(attrs.get("password", "")):
                raise AuthenticationFailed({"detail": "account is disabled", "code": "account_disabled"})
            raise AuthenticationFailed(
                {"detail": "invalid credentials", "code": "invalid_credentials"}
            )
        data["user"] = UserSerializer(self.user).data
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class TelegramMiniAppSerializer(serializers.Serializer):
    """The raw `Telegram.WebApp.initData` string, verified server-side."""

    init_data = serializers.CharField(trim_whitespace=False, max_length=8192)


class EmptySerializer(serializers.Serializer):
    """No input; used by action-only endpoints so the schema generator is happy."""


class LegacyUserSerializer(serializers.Serializer):
    username = serializers.RegexField(r"^[A-Za-z0-9_.]{3,64}$")
    email = serializers.EmailField(required=False, allow_blank=True)
    name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    telegram_id = serializers.IntegerField(required=False, allow_null=True)
    password = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    referral_code = serializers.CharField(max_length=6, required=False, allow_blank=True)


class LegacyImportSerializer(serializers.Serializer):
    users = LegacyUserSerializer(many=True)
    overwrite = serializers.BooleanField(default=False)
