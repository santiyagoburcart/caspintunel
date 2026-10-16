"""Agency panel models — PAMP v1.5.3 `admins/models.py`, ported 1:1.

Fields, defaults, formulas (properties) and 1024-based formatting are copied
VERBATIM from PAMP (tag v1.5.3, sha256 9a6a8316…53a9); only `db_table` was
added. Not ported: PanelConfig (the panel connection is caspintunel's
`panel.Panel`), SyncSettings (→ setting `agency_sync_interval_minutes`),
UISettings and TelegramConfig (caspintunel has its own UI and backups).
Do not edit the formulas: `tests/test_golden.py` compares them with the
original PAMP code.
"""
from django.db import models
from django.utils import timezone


def _fmt_bytes(b):
    b = b or 0
    if b == 0:
        return "0 B"
    b_abs = abs(b)
    sign = "-" if b < 0 else ""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if b_abs < 1024.0:
            return f"{sign}{b_abs:.2f} {unit}"
        b_abs /= 1024.0
    return f"{sign}{b_abs:.2f} PB"


class PanelAdmin(models.Model):
    username = models.CharField(max_length=255, unique=True, db_index=True)
    is_sudo = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=50, default='active')

    # Admin's own traffic quota from panel (bytes). False = unlimited.
    has_data_limit = models.BooleanField(default=False)
    admin_limit_bytes = models.BigIntegerField(default=0)
    admin_remaining = models.BigIntegerField(default=0)

    # Traffic aggregated across all this admin's users (bytes)
    total_user_limit = models.BigIntegerField(default=0)
    total_user_used = models.BigIntegerField(default=0)

    # User counts by status
    user_count = models.IntegerField(default=0)
    active_user_count = models.IntegerField(default=0)
    limited_users = models.IntegerField(default=0)
    disabled_users = models.IntegerField(default=0)
    expired_users = models.IntegerField(default=0)
    on_hold_users = models.IntegerField(default=0)

    # PAMP enforcement fields
    pamp_blocked = models.BooleanField(default=False)
    pamp_blocked_at = models.DateTimeField(null=True, blank=True)

    raw_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    # Cumulative used-traffic of users deleted from the panel.
    # Added ONLY into total_user_limit (sold volume) so Sold Limit stays correct.
    deleted_users_used_bytes = models.BigIntegerField(default=0)
    deleted_traffic_reset_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agency_panel_admin"
        verbose_name = "Panel Admin"
        verbose_name_plural = "Panel Admins"
        ordering = ['username']

    def __str__(self):
        return self.username

    # ── effective status (panel status + PAMP enforcement) ────────────────
    @property
    def effective_status(self):
        """Return (code, label, color) for the admin's true current state."""
        if self.status == 'disabled':
            return ('panel_disabled', 'Disabled', '#ef4444')
        if self.pamp_blocked:
            return ('pamp_limited', 'Limited', '#f59e0b')
        return ('active', 'Active', '#10b981')

    @property
    def status_code(self):
        return self.effective_status[0]

    @property
    def status_label(self):
        return self.effective_status[1]

    @property
    def status_color(self):
        return self.effective_status[2]

    # ── compatibility aliases ──────────────────────────────────────────────
    @property
    def users_count(self):
        return self.user_count

    @property
    def active_users(self):
        return self.active_user_count

    @property
    def admin_used_bytes(self):
        return self.total_user_used

    # ── traffic calculations ───────────────────────────────────────────────
    @property
    def is_unlimited(self):
        """Admin has no traffic limit on the panel (unlimited)."""
        return not self.admin_limit_bytes or self.admin_limit_bytes <= 0

    @property
    def sold_limit_bytes(self):
        """Sold Limit = remaining − total_user_limit + total_user_used. Zero if unlimited."""
        if self.is_unlimited:
            return 0
        return self.admin_remaining - self.total_user_limit + self.total_user_used

    @property
    def hidden_traffic(self):
        # Clamped to 0: goes negative when admins have many unlimited users whose traffic
        # isn't captured in total_user_limit (which only sums limited users' data caps).
        return max(0, self.total_user_limit - self.total_user_used - self.admin_remaining)

    @property
    def hidden_traffic_bytes(self):
        return self.hidden_traffic

    @property
    def usage_percent(self):
        # Use admin_limit_bytes (the admin's actual quota from Pasargad) as denominator.
        # total_user_limit is the sum of per-user data caps and excludes unlimited users,
        # so it can be smaller than total_user_used → would give >100% incorrectly.
        if not self.has_data_limit or not self.admin_limit_bytes:
            return 0
        return round((self.total_user_used / self.admin_limit_bytes) * 100, 1)

    # ── formatted display strings ──────────────────────────────────────────
    @property
    def admin_limit_fmt(self):
        return "Unlimited" if not self.has_data_limit else _fmt_bytes(self.admin_limit_bytes)

    @property
    def admin_remaining_fmt(self):
        return "Unlimited" if not self.has_data_limit else _fmt_bytes(self.admin_remaining)

    @property
    def admin_used_fmt(self):
        return _fmt_bytes(self.total_user_used)

    @property
    def total_user_limit_fmt(self):
        return _fmt_bytes(self.total_user_limit)

    @property
    def total_user_used_fmt(self):
        return _fmt_bytes(self.total_user_used)

    @property
    def hidden_traffic_fmt(self):
        return _fmt_bytes(self.hidden_traffic)

    # ── GB helpers ─────────────────────────────────────────────────────────
    def _to_gb(self, val):
        return round((val or 0) / (1024 ** 3), 2)

    @property
    def total_user_limit_gb(self):
        return self._to_gb(self.total_user_limit)

    @property
    def total_user_used_gb(self):
        return self._to_gb(self.total_user_used)

    @property
    def admin_remaining_gb(self):
        return self._to_gb(self.admin_remaining)

    @property
    def hidden_traffic_gb(self):
        return self._to_gb(self.hidden_traffic)

    @property
    def admin_limit_gb(self):
        return self._to_gb(self.admin_limit_bytes)


class AdminLimit(models.Model):
    panel_admin = models.OneToOneField(
        PanelAdmin, on_delete=models.CASCADE, related_name='limit_config'
    )
    limit_bytes = models.BigIntegerField(default=0)
    warning_sent_80 = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)
    blocked_at = models.DateTimeField(null=True, blank=True)
    telegram_username = models.CharField(max_length=100, blank=True)
    support_telegram = models.CharField(max_length=100, blank=True, default='@support')

    class Meta:
        db_table = "agency_admin_limit"
        verbose_name = "Admin Limit Config"
        verbose_name_plural = "Admin Limit Configs"

    @property
    def limit_gb(self):
        return self.limit_bytes / (1024 ** 3) if self.limit_bytes else 0

    def __str__(self):
        return f"{self.panel_admin.username} — {self.limit_gb:.1f} GB"


class SyncLog(models.Model):
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_PARTIAL = 'partial'

    STATUS_CHOICES = [
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_PARTIAL, 'Partial'),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    admins_synced = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    duration_seconds = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agency_sync_log"
        verbose_name = "Sync Log"
        verbose_name_plural = "Sync Logs"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.status.upper()}] {self.created_at.strftime('%Y-%m-%d %H:%M')} — {self.admins_synced} admins"


class UserTrafficSnapshot(models.Model):
    """Last-known used_traffic per user — used to detect deletions on the next sync."""
    panel_admin = models.ForeignKey(PanelAdmin, on_delete=models.CASCADE, related_name='user_snapshots')
    user_username = models.CharField(max_length=255)
    used_traffic_bytes = models.BigIntegerField(default=0)
    last_seen = models.DateTimeField(auto_now=True)


    class Meta:
        db_table = "agency_user_traffic_snapshot"
        unique_together = ('panel_admin', 'user_username')
        indexes = [models.Index(fields=['panel_admin', 'user_username'])]

    def __str__(self):
        return f"{self.panel_admin.username}/{self.user_username}"


class AdminGroup(models.Model):
    """Groups multiple PanelAdmin accounts under one owner admin.
    When the owner logs in, they see all member accounts in My Panel."""
    owner_username = models.CharField(max_length=150, unique=True,
        help_text="The admin username who logs in and sees all member accounts")
    member_usernames = models.TextField(blank=True,
        help_text="Comma-separated list of admin usernames in this group")
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agency_admin_group"
        verbose_name = 'Account Group'

    def __str__(self):
        return f"{self.owner_username} (+{len(self.get_members())})"

    def get_members(self):
        if not self.member_usernames:
            return []
        return [u.strip() for u in self.member_usernames.split(',') if u.strip()]

    def get_all_usernames(self):
        members = self.get_members()
        result = [self.owner_username]
        for m in members:
            if m != self.owner_username:
                result.append(m)
        return result

    @classmethod
    def get_group_for_owner(cls, username):
        return cls.objects.filter(owner_username=username).first()


