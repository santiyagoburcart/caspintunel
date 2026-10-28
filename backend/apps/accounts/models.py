from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel

from .managers import UserManager, generate_referral_code

# the only permission a group-manager staff holds (apps/agency/managers.py, v1.25)
GROUP_MANAGER_PERM = "agency.group_manager"
GROUP_MANAGER_ROLE = "Group manager"
# v1.27: what a group manager may do, one permission each (Roles page → "Agency – group manager").
# code → (English name, Persian name). The "Group manager" role gets all of them when created.
GM_PERMS = {
    "agency.gm.view_admins": ("Group manager: view group admins", "مدیر گروه: دیدن ادمین‌های گروه"),
    "agency.gm.create_admin": ("Group manager: create admin (incl. profile title, support link)",
                               "مدیر گروه: ساخت ادمین (با عنوان پروفایل و لینک پشتیبانی)"),
    "agency.gm.add_volume": ("Group manager: add volume", "مدیر گروه: افزودن حجم"),
    "agency.gm.toggle_admin": ("Group manager: enable / disable admin", "مدیر گروه: فعال / غیرفعال‌کردن ادمین"),
    "agency.gm.admin_password": ("Group manager: change admin password", "مدیر گروه: تغییر رمز ادمین"),
    "agency.gm.admin_role": ("Group manager: change admin role", "مدیر گروه: تغییر نقش ادمین"),
    "agency.gm.view_users": ("Group manager: view admins' users", "مدیر گروه: دیدن کاربران ادمین‌ها"),
    "agency.gm.accounting": ("Group manager: view accounting / group statement", "مدیر گروه: دیدن حسابداری و صورت‌حساب گروه"),
    "agency.gm.activity": ("Group manager: view activity", "مدیر گروه: دیدن فعالیت"),
}


class Source(models.TextChoices):
    SITE = "site", "Site"
    BOT = "bot", "Bot"


class Language(models.TextChoices):
    FA = "fa", "فارسی"
    EN = "en", "English"


class User(AbstractBaseUser, PermissionsMixin):
    """Customer account (data-model.md · Module 1 · `user`)."""

    username = models.CharField(max_length=64, unique=True)
    email = models.EmailField(max_length=255, null=True, blank=True)
    email_verified = models.BooleanField(default=False)
    name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=20, blank=True, help_text="= Telegram phone")
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True)
    telegram_username = models.CharField(max_length=64, null=True, blank=True)
    bank_card_number = models.CharField(
        max_length=20, null=True, blank=True, help_text="user's own card, shown in bot"
    )
    referral_code = models.CharField(max_length=6, unique=True, editable=False)
    referred_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals"
    )
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.SITE)
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.FA)
    is_legacy = models.BooleanField(default=False)
    admin_note = models.TextField(blank=True, default="", help_text="Internal staff-only note; never shown to the user")
    terms_accepted_at = models.DateTimeField(
        null=True, blank=True, help_text="when the user accepted the terms of service (at sign-up)"
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="Django admin access")

    # soft delete (admin "delete user"): the row stays so orders / payments keep
    # their owner and accounting never changes; see apps.accounts.deletion
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_by = models.ForeignKey(
        "accounts.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="deleted_users"
    )
    delete_reason = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "user"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.username

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = self._unique_referral_code()
        super().save(*args, **kwargs)

    @staticmethod
    def _unique_referral_code() -> str:
        for _ in range(20):
            code = generate_referral_code()
            if not User.objects.filter(referral_code=code).exists():
                return code
        raise RuntimeError("could not allocate a unique referral_code")

    @property
    def referral_count(self) -> int:
        return self.referrals.count()

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


# ---------------------------------------------------------------------------
# Independent RBAC for panel operators (architecture.md — "our own system")
# ---------------------------------------------------------------------------
class Permission(models.Model):
    """Fine-grained action code, e.g. `payment.approve` (data-model · `permission`)."""

    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=150)
    # v1.25.2: Persian label (seeded); the panel shows it when its language is fa
    name_fa = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        db_table = "permission"
        ordering = ("code",)

    def __str__(self) -> str:
        return self.code


class Role(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    # v1.25.2: Persian name / description (seeded for built-in roles, editable); blank = use `name`
    name_fa = models.CharField(max_length=100, blank=True, default="")
    description_fa = models.CharField(max_length=255, blank=True, default="")
    permissions = models.ManyToManyField(
        Permission, related_name="roles", blank=True, db_table="role_permission"
    )

    class Meta:
        db_table = "role"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Staff(TimeStampedModel):
    """Panel operator / admin (data-model · `staff`). Separate from `User`."""

    username = models.CharField(max_length=64, unique=True)
    password_hash = models.CharField(max_length=255)
    role = models.ForeignKey(
        Role, null=True, blank=True, on_delete=models.SET_NULL, related_name="staff"
    )
    is_active = models.BooleanField(default=True)
    is_superadmin = models.BooleanField(
        default=False, help_text="bypasses permission checks"
    )
    last_login = models.DateTimeField(null=True, blank=True)
    # Every staff JWT carries this as "tv"; a token whose tv differs is dead.
    # Bumped on password change and by `manage.py revoke_staff_sessions`.
    token_version = models.PositiveIntegerField(default=1)
    # ticketing notifications (apps/tickets): optional email, and the Telegram
    # account linked from the panel with a one-time code sent to the sales bot
    email = models.EmailField(blank=True, default="")
    # shown to customers on ticket replies when the setting tickets_show_staff_name is on
    display_name = models.CharField(max_length=60, blank=True, default="")
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True)
    telegram_linked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "staff"
        ordering = ("username",)
        verbose_name_plural = "staff"

    # user-like shims so DRF (IsAuthenticated etc.) accepts a Staff on request.user
    is_authenticated = True
    is_anonymous = False

    def __str__(self) -> str:
        return self.username

    def set_password(self, raw: str) -> None:
        """Also ends every session of this account (tokens carry token_version);
        the caller saves."""
        self.password_hash = make_password(raw)
        self.token_version = (self.token_version or 0) + 1

    def check_password(self, raw: str) -> bool:
        return check_password(raw, self.password_hash)

    def touch_login(self) -> None:
        self.last_login = timezone.now()
        self.save(update_fields=["last_login"])

    @property
    def group_manager_row(self):
        """The agency GroupManager this staff signs in as (v1.25), or None."""
        try:
            return self.group_manager
        except ObjectDoesNotExist:
            return None

    @property
    def is_group_manager(self) -> bool:
        """A staff linked to a group manager is restricted to its own groups: every
        admin API refuses it unless the view opts in (StaffPermission)."""
        return not self.is_superadmin and self.group_manager_row is not None

    def gm_permissions(self) -> list[str]:
        """The agency.gm.* abilities of a group-manager staff (sorted)."""
        if not self.role_id:
            return []
        return sorted(self.role.permissions.filter(code__in=list(GM_PERMS)).values_list("code", flat=True))

    def has_perm(self, code: str) -> bool:
        if self.is_superadmin:
            return True
        if self.is_group_manager:
            # restricted: only the group-manager marker + the agency.gm.* abilities its role holds
            if code == GROUP_MANAGER_PERM:
                return True
            if code in GM_PERMS and self.role_id:
                return self.role.permissions.filter(code=code).exists()
            return False
        if not self.role_id:
            return False
        return self.role.permissions.filter(code=code).exists()


class StaffRevokedToken(models.Model):
    """Spent / revoked staff refresh tokens (by jti), kept until the token
    would have expired anyway. Durable on purpose: it used to live only in the
    Redis cache, where a flush silently re-enabled used tokens."""

    jti = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "staff_revoked_token"


class DeletedUserArchive(models.Model):
    """Full snapshot of a user taken right before an admin soft-deleted them
    (profile, orders + payments, services, notification count, admin note).
    The live row's unique fields are freed afterwards; the originals live here
    and are what a restore puts back."""

    user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="deletion_archives"
    )
    original_username = models.CharField(max_length=64, db_index=True)
    original_name = models.CharField(max_length=120, blank=True)
    original_phone = models.CharField(max_length=20, blank=True, db_index=True)
    original_email = models.CharField(max_length=255, blank=True)
    original_telegram_id = models.BigIntegerField(null=True, blank=True)
    original_telegram_username = models.CharField(max_length=64, blank=True)

    deleted_at = models.DateTimeField(default=timezone.now, db_index=True)
    deleted_by = models.ForeignKey(
        Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    deleted_by_label = models.CharField(max_length=150, blank=True)
    reason = models.TextField()

    orders_count = models.IntegerField(default=0)
    total_paid = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    snapshot = models.JSONField(default=dict)

    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey(
        Staff, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    restored_by_label = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = "deleted_user_archive"
        ordering = ("-deleted_at", "-id")

    def __str__(self) -> str:
        return f"archive#{self.pk} {self.original_username}"
