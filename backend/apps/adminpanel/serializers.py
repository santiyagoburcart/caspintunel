from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.accounts.models import Permission, Role, Staff
from apps.notifications.models import Notification
from apps.ops.models import BackupLog, HealthCheck, ResourceStat
from apps.panel.models import Service
from apps.payments_sms.models import BankCard, Payment
from apps.plans.models import Plan
from apps.settings_app.models import Page, SiteConfig, Theme

User = get_user_model()


# --- users ---------------------------------------------------------
class AdminUserSerializer(serializers.ModelSerializer):
    referral_count = serializers.IntegerField(read_only=True)
    service_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "email_verified", "name", "phone",
            "telegram_id", "telegram_username", "referral_code", "referred_by",
            "referral_count", "service_count", "source", "language",
            "is_legacy", "is_active", "is_staff", "created_at",
        )
        read_only_fields = ("id", "referral_code", "referral_count", "service_count", "created_at")


class AdminUserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "username", "password", "email", "name", "phone", "language", "is_active")

    def create(self, validated):
        pwd = validated.pop("password")
        user = User(**validated)
        user.set_password(pwd)
        user.save()
        return user


class SetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(min_length=8, trim_whitespace=False)


# --- plans / cards / pages / themes -------------------------------
class AdminPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = "__all__"


class AdminBankCardSerializer(serializers.ModelSerializer):
    deposit_total = serializers.SerializerMethodField()
    deposit_count = serializers.SerializerMethodField()

    class Meta:
        model = BankCard
        fields = ("id", "card_number", "holder_name", "bank_name", "sort_order",
                  "is_active", "deposit_total", "deposit_count", "created_at")

    def get_deposit_total(self, obj) -> int | None:
        return getattr(obj, "deposit_total", None)

    def get_deposit_count(self, obj) -> int | None:
        return getattr(obj, "deposit_count", None)


class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = ("id", "slug", "title_fa", "title_en", "body_fa", "body_en", "is_active", "updated_at")


class ThemeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Theme
        fields = ("id", "name", "palette", "is_active")


# --- rbac ---------------------------------------------------------
class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ("id", "code", "name")


class RoleSerializer(serializers.ModelSerializer):
    permission_codes = serializers.SlugRelatedField(
        source="permissions", slug_field="code", many=True, queryset=Permission.objects.all()
    )

    class Meta:
        model = Role
        fields = ("id", "name", "description", "permission_codes")


class StaffSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = Staff
        fields = ("id", "username", "password", "role", "role_name",
                  "is_active", "is_superadmin", "last_login", "created_at")
        read_only_fields = ("last_login", "created_at")

    def validate(self, attrs):
        if not self.instance and not attrs.get("password"):
            raise serializers.ValidationError({"password": "required when creating a staff account"})
        return attrs

    def create(self, validated):
        pwd = validated.pop("password")
        staff = Staff(**validated)
        staff.set_password(pwd)
        staff.save()
        return staff

    def update(self, instance, validated):
        pwd = validated.pop("password", None)
        for k, v in validated.items():
            setattr(instance, k, v)
        if pwd:
            instance.set_password(pwd)
        instance.save()
        return instance


# --- payments / transactions ------------------------------------
class TransactionSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source="order.id", read_only=True)
    user = serializers.CharField(source="order.user.username", read_only=True)
    order_source = serializers.CharField(source="order.source", read_only=True)
    order_type = serializers.CharField(source="order.type", read_only=True)
    card = serializers.CharField(source="bank_card.card_number", read_only=True, default=None)
    confirmer = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            "id", "order_id", "user", "amount", "method", "status",
            "card", "confirmed_by", "confirmer", "confirmed_at",
            "order_source", "order_type", "created_at",
        )

    def get_confirmer(self, obj) -> str | None:
        if obj.confirmed_by == "system":
            return "SMS system"
        if obj.confirmed_by_staff_id:
            return obj.confirmed_by_staff.username
        if obj.confirmed_by == "admin":
            return "admin"
        return None


# --- notifications ---------------------------------------------
class BroadcastSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    body = serializers.CharField()
    target_user = serializers.IntegerField(required=False, allow_null=True)
    via_site = serializers.BooleanField(default=True)
    via_bot = serializers.BooleanField(default=False)
    via_email = serializers.BooleanField(default=False)


class NotificationSerializer(serializers.ModelSerializer):
    delivery_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Notification
        fields = ("id", "type", "title", "body", "target_user", "via_site",
                  "via_bot", "via_email", "delivery_count", "created_at")


# --- branding -------------------------------------------------
class SiteConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteConfig
        fields = ("site_name_fa", "site_name_en", "site_domain", "logo", "favicon",
                  "bot_description_fa", "bot_description_en", "support_telegram",
                  "meta_description", "updated_at")
        read_only_fields = ("updated_at",)


# --- service lists -------------------------------------------
class HealthCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthCheck
        fields = ("target", "is_up", "latency_ms", "detail", "checked_at")


class ResourceStatSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceStat
        fields = ("cpu_percent", "ram_percent", "disk_percent", "net_in", "net_out",
                  "bandwidth_used", "sampled_at")


class BackupLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupLog
        fields = ("id", "filename", "size", "status", "sent_to_telegram", "error", "created_at")


class AdminServiceSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source="user.username", read_only=True)
    plan = serializers.CharField(source="current_plan.name_fa", read_only=True, default=None)

    class Meta:
        model = Service
        fields = ("id", "panel_username", "user", "plan", "status", "expire_strategy",
                  "data_limit", "data_used", "expire_at", "online_at", "last_synced_at",
                  "subscription_url", "created_at")
