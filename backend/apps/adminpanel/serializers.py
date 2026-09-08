from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.accounts.models import Permission, Role, Staff
from apps.notifications.models import Notification
from apps.ops.models import BackupLog, HealthCheck, ResourceStat
from apps.panel.models import Panel, Service
from apps.payments_sms.models import BankCard, Payment
from apps.plans.models import Plan
from apps.plans.serializers import PlanPanelDefaultMixin
from apps.settings_app.models import Page, SiteConfig, Theme
from apps.telegram.models import RequiredChannel, TelegramConfig

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


# --- integrations: pasargad panel + telegram bots ----------------
class PanelConfigSerializer(serializers.ModelSerializer):
    """Panel connection settings. The admin password is write-only; reads only
    report whether one is stored."""

    name = serializers.CharField(required=False)
    admin_password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, trim_whitespace=False,
        style={"input_type": "password"},
        help_text="leave blank to keep the stored password unchanged",
    )
    admin_password_set = serializers.SerializerMethodField()

    class Meta:
        model = Panel
        fields = ("id", "name", "base_url", "admin_username", "admin_password",
                  "admin_password_set", "subscription_base_url", "verify_ssl",
                  "default_group_ids", "is_active", "updated_at")
        read_only_fields = ("id", "updated_at")

    def get_admin_password_set(self, obj) -> bool:
        return bool(getattr(obj, "pk", None) and obj.admin_password_enc)

    def _apply(self, instance, validated):
        pw = validated.pop("admin_password", None)
        for key, value in validated.items():
            setattr(instance, key, value)
        if pw:  # blank / omitted -> keep whatever is stored
            instance.admin_password_enc = pw
        if not instance.name:
            instance.name = "Pasargad"
        instance.save()
        return instance

    def create(self, validated_data):
        return self._apply(Panel(), validated_data)

    def update(self, instance, validated_data):
        return self._apply(instance, validated_data)


class PanelAdminSerializer(serializers.ModelSerializer):
    """One panel in the multi-panel manager. Password write-only; reads report
    only whether one is stored, plus how many plans / services depend on it."""

    admin_password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, trim_whitespace=False,
        style={"input_type": "password"},
        help_text="leave blank to keep the stored password unchanged",
    )
    admin_password_set = serializers.SerializerMethodField()
    plan_count = serializers.SerializerMethodField()
    service_count = serializers.SerializerMethodField()

    class Meta:
        model = Panel
        fields = ("id", "name", "base_url", "admin_username", "admin_password",
                  "admin_password_set", "subscription_base_url", "verify_ssl",
                  "default_group_ids", "is_active", "plan_count", "service_count",
                  "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def get_admin_password_set(self, obj) -> bool:
        return bool(getattr(obj, "pk", None) and obj.admin_password_enc)

    def get_plan_count(self, obj) -> int:
        return obj.plans.count() if obj.pk else 0

    def get_service_count(self, obj) -> int:
        return obj.services.count() if obj.pk else 0

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("name is required")
        return value

    def _apply(self, instance, validated):
        pw = validated.pop("admin_password", None)
        for key, value in validated.items():
            setattr(instance, key, value)
        if pw:  # blank / omitted -> keep whatever is stored
            instance.admin_password_enc = pw
        instance.save()
        return instance

    def create(self, validated_data):
        if not validated_data.get("admin_password"):
            raise serializers.ValidationError(
                {"admin_password": "a password is required for a new panel"})
        return self._apply(Panel(), validated_data)

    def update(self, instance, validated_data):
        return self._apply(instance, validated_data)


class TelegramConfigSerializer(serializers.ModelSerializer):
    """One bot's settings. The token is write-only; reads only report whether
    one is stored."""

    token = serializers.CharField(
        write_only=True, required=False, allow_blank=True, trim_whitespace=False,
        help_text="leave blank to keep the stored token unchanged",
    )
    token_set = serializers.SerializerMethodField()

    class Meta:
        model = TelegramConfig
        fields = ("bot_type", "token", "token_set", "proxy_url", "backup_chat_id",
                  "is_active", "updated_at")
        read_only_fields = ("bot_type", "updated_at")

    def get_token_set(self, obj) -> bool:
        return bool(getattr(obj, "token", ""))


class AdminRequiredChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequiredChannel
        fields = ("id", "channel_id", "title", "invite_link", "member_count",
                  "last_synced_at", "is_active")
        read_only_fields = ("id", "member_count", "last_synced_at")

    def validate_channel_id(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("channel username or id is required")
        # normalise: bare name -> @name ; leave -100... ids and @names as-is
        if not value.startswith("@") and not value.lstrip("-").isdigit():
            value = "@" + value.lstrip("@")
        return value


# --- plans / cards / pages / themes -------------------------------
class AdminPlanSerializer(PlanPanelDefaultMixin, serializers.ModelSerializer):
    panel_name = serializers.CharField(source="panel.name", read_only=True)
    panel_default_group_ids = serializers.JSONField(
        source="panel.default_group_ids", read_only=True
    )

    class Meta:
        model = Plan
        fields = "__all__"
        extra_kwargs = {"panel": {"required": False}}


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
    user_name = serializers.CharField(source="order.user.name", read_only=True, default="")
    user_telegram = serializers.CharField(
        source="order.user.telegram_username", read_only=True, default=""
    )
    plan_name = serializers.CharField(source="order.plan.name_fa", read_only=True, default=None)
    plan_name_en = serializers.CharField(source="order.plan.name_en", read_only=True, default="")
    account_name = serializers.CharField(
        source="order.requested_account_name", read_only=True, default=""
    )
    order_source = serializers.CharField(source="order.source", read_only=True)
    order_type = serializers.CharField(source="order.type", read_only=True)
    order_status = serializers.CharField(source="order.status", read_only=True)
    amount_unique = serializers.DecimalField(
        source="order.amount_unique", max_digits=12, decimal_places=0, read_only=True, default=None
    )
    card = serializers.CharField(source="bank_card.card_number", read_only=True, default=None)
    card_holder = serializers.CharField(source="bank_card.holder_name", read_only=True, default=None)
    card_bank = serializers.CharField(source="bank_card.bank_name", read_only=True, default=None)
    gateway_ref = serializers.CharField(read_only=True, default=None)
    confirmer = serializers.SerializerMethodField()
    reject_reason = serializers.CharField(read_only=True)
    receipt_url = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            "id", "order_id", "user", "user_name", "user_telegram", "plan_name", "plan_name_en",
            "account_name", "amount", "amount_unique", "method", "status",
            "card", "card_holder", "card_bank", "gateway_ref",
            "confirmed_by", "confirmer", "confirmed_at", "reject_reason",
            "receipt_url", "order_source", "order_type", "order_status",
            "created_at", "updated_at",
        )

    def get_receipt_url(self, obj) -> str | None:
        return f"/api/v1/payments/{obj.id}/receipt/" if obj.receipt_image else None

    def get_confirmer(self, obj) -> str | None:
        if obj.confirmed_by == "system":
            return "SMS system"
        if obj.confirmed_by_staff_id:
            return obj.confirmed_by_staff.username
        if obj.confirmed_by == "admin":
            return "admin"
        return None


class AdminPendingPaymentSerializer(serializers.ModelSerializer):
    """One row in the approval queue."""

    order_id = serializers.IntegerField(source="order.id", read_only=True)
    user = serializers.CharField(source="order.user.username", read_only=True)
    user_telegram = serializers.CharField(source="order.user.telegram_username", read_only=True, default="")
    plan_name = serializers.CharField(source="order.plan.name_fa", read_only=True, default=None)
    order_type = serializers.CharField(source="order.type", read_only=True)
    order_source = serializers.CharField(source="order.source", read_only=True)
    account_name = serializers.CharField(source="order.requested_account_name", read_only=True, default="")
    receipt_url = serializers.SerializerMethodField()
    bank_card = serializers.PrimaryKeyRelatedField(read_only=True)
    bank_card_number = serializers.CharField(source="bank_card.card_number", read_only=True, default=None)

    class Meta:
        model = Payment
        fields = ("id", "order_id", "user", "user_telegram", "plan_name", "order_type",
                  "order_source", "account_name", "method", "amount", "status",
                  "receipt_url", "reject_reason", "created_at",
                  "bank_card", "bank_card_number")

    def get_receipt_url(self, obj) -> str | None:
        # authenticated endpoint (ReceiptFileView), never a public media path
        return f"/api/v1/payments/{obj.id}/receipt/" if obj.receipt_image else None


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

    def to_representation(self, obj):
        from apps.settings_app.serializers import rel_media

        data = super().to_representation(obj)
        # root-relative URLs — reachable from whatever origin the panel runs on
        data["logo"] = rel_media(obj.logo)
        data["favicon"] = rel_media(obj.favicon)
        return data


# --- service lists -------------------------------------------
class HealthCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthCheck
        fields = ("target", "is_up", "latency_ms", "detail", "checked_at")


class ResourceStatSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceStat
        fields = ("cpu_percent", "ram_percent", "swap_percent", "disk_percent", "net_in", "net_out",
                  "bandwidth_used", "sampled_at")


class BackupLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupLog
        fields = ("id", "filename", "size", "status", "sent_to_telegram", "error", "created_at")


class AdminServiceSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source="user.username", read_only=True)
    user_name = serializers.CharField(source="user.name", read_only=True, default="")
    plan = serializers.CharField(source="current_plan.name_fa", read_only=True, default=None)
    plan_en = serializers.CharField(source="current_plan.name_en", read_only=True, default=None)
    is_online = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = ("id", "panel_username", "user", "user_name", "plan", "plan_en", "status",
                  "expire_strategy", "data_limit", "data_used", "expire_at", "online_at",
                  "is_online", "last_synced_at", "subscription_url", "created_at")

    def get_is_online(self, obj) -> bool:
        if not obj.online_at:
            return False
        from django.utils import timezone
        return obj.online_at >= timezone.now() - timezone.timedelta(minutes=5)
