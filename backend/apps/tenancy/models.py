"""Multi-tenant reseller storefronts (docs/multi-tenant.md). Phase 1 Release A: the tenant tables and a nullable
`tenant` on every tenant table, filled with the default tenant. Nothing reads them yet (Release B adds the middleware
and scoped managers)."""
import secrets

from django.db import models

from apps.common.fields import EncryptedTextField
from apps.common.models import TimeStampedModel

from .fields import tenant_fk


def _verify_token() -> str:
    return secrets.token_urlsafe(24)


class Tenant(TimeStampedModel):
    DRAFT, ACTIVE, SUSPENDED, CLOSED = "draft", "active", "suspended", "closed"
    STATUSES = [(DRAFT, "Draft"), (ACTIVE, "Active"), (SUSPENDED, "Suspended"), (CLOSED, "Closed")]

    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    # the reseller (agency PanelAdmin username) who owns the store; empty = the default tenant (our own store)
    reseller_username = models.CharField(max_length=255, blank=True, default="", db_index=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=DRAFT)
    is_default = models.BooleanField(default=False)
    export_allowed = models.BooleanField(default=False, help_text="the reseller may download a tenant export (set by us)")
    limits = models.JSONField(default=dict, blank=True, help_text="orders/min, staff count, … (set by us)")
    # v1.46 (Phase 4, tenancy/quota.py): the reseller quota warning last sent — 0 none, 20 / 10 = % remaining
    quota_alert_level = models.PositiveSmallIntegerField(default=0)
    # v1.52 (Phase 8, tenancy/staff.py): the permission codes the store's staff may hold and grant (⊆ STORE_CODES, set by us)
    permission_ceiling = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "tenant"
        ordering = ("-is_default", "name")

    def save(self, *args, **kwargs):
        # exactly one default tenant (MySQL has no partial unique index, so it is checked here)
        if self.is_default and Tenant.objects.filter(is_default=True).exclude(pk=self.pk).exists():
            raise ValueError("there is already a default tenant")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.slug


class TenantDomain(TimeStampedModel):
    SITE, ADMIN, BOTH = "site", "admin", "both"
    DIRECT, TUNNEL, CLOUDFLARE = "direct", "tunnel", "cloudflare"
    PENDING_DNS, VERIFIED, CERT_PENDING, ACTIVE, FAILED, REMOVED = (
        "pending_dns", "verified", "cert_pending", "active", "failed", "removed")
    STATES = [(PENDING_DNS, "Waiting for DNS"), (VERIFIED, "Verified"), (CERT_PENDING, "Certificate pending"),
              (ACTIVE, "Active"), (FAILED, "Failed"), (REMOVED, "Removed")]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="domains")
    host = models.CharField(max_length=253, unique=True, help_text="lowercase, IDNA (punycode)")
    role = models.CharField(max_length=5, choices=[(SITE, "Site"), (ADMIN, "Admin"), (BOTH, "Site + admin")], default=BOTH)
    mode = models.CharField(max_length=10, choices=[(DIRECT, "Direct (Finland IP)"), (TUNNEL, "Iran tunnel"),
                                                    (CLOUDFLARE, "Reseller's Cloudflare proxy")], default=DIRECT)
    verify_token = models.CharField(max_length=64, default=_verify_token)
    state = models.CharField(max_length=12, choices=STATES, default=PENDING_DNS)
    cert_expires_at = models.DateTimeField(null=True, blank=True)
    last_check_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True, default="")
    # v1.45 (Phase 3, apps/tenancy/domains.py): www + the reseller's Cloudflare proxy (detected), what the checks saw
    include_www = models.BooleanField(default=True)
    proxied = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    cert_issued_at = models.DateTimeField(null=True, blank=True)
    dns = models.JSONField(default=dict, blank=True)              # last DNS / reachability check
    health = models.JSONField(default=dict, blank=True)           # last health check
    unhealthy_since = models.DateTimeField(null=True, blank=True)
    cert_failures = models.PositiveSmallIntegerField(default=0)
    retry_token = models.PositiveIntegerField(default=0)          # bumped by «تلاش دوباره» → the host watcher retries now

    class Meta:
        db_table = "tenant_domain"
        ordering = ("host",)

    def __str__(self) -> str:
        return self.host



def _webhook_secret() -> str:
    return secrets.token_urlsafe(32)        # Telegram allows A-Z a-z 0-9 _ - (1–256 chars)


class TenantBot(TimeStampedModel):
    """v1.49 (Phase 6, tenancy/bots.py): a store's own Telegram bot — webhook mode, set ONLY by our staff (D5).
    Telegram posts its updates to /api/v1/telegram/hook/<tenant id>/ on OUR host with `webhook_secret` in the
    X-Telegram-Bot-Api-Secret-Token header. The reseller sees the username and state, never the token."""

    OK, ERROR = "ok", "error"
    STATES = [(OK, "Webhook OK"), (ERROR, "Error")]

    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="bot")
    token = EncryptedTextField(help_text="stored encrypted at rest; never returned by the API")
    webhook_secret = EncryptedTextField(default=_webhook_secret)
    bot_id = models.BigIntegerField(unique=True, help_text="Telegram id of the bot (getMe) — one store per bot")
    username = models.CharField(max_length=64)
    state = models.CharField(max_length=8, choices=STATES, default=OK)
    last_error = models.CharField(max_length=500, blank=True, default="")
    webhook_set_at = models.DateTimeField(null=True, blank=True)
    last_check_at = models.DateTimeField(null=True, blank=True)
    last_update_at = models.DateTimeField(null=True, blank=True, help_text="last update Telegram delivered")
    alerted_at = models.DateTimeField(null=True, blank=True, help_text="the one 'bot broken' alert to us")

    class Meta:
        db_table = "tenant_bot"

    def __str__(self) -> str:
        return f"@{self.username}"



class TenantExport(TimeStampedModel):
    """v1.53 (Phase 10, tenancy/export.py): a backup of ONE store's own data (zip of JSON + CSV), built in Celery.

    TENANT table (scoped to the store). Asked for in the store's panel (needs `Tenant.export_allowed` + `store.export`) or by
    our staff on «فروشگاه». The file lives under media/exports/ (nginx 404s it) and is served only through a one-time link
    (`link_hash` = sha256 of the token; every link works once) until `expires_at` (24 h after it is ready), then deleted."""

    QUEUED, RUNNING, READY, FAILED, EXPIRED = "queued", "running", "ready", "failed", "expired"
    STATES = [(QUEUED, "Queued"), (RUNNING, "Running"), (READY, "Ready"), (FAILED, "Failed"), (EXPIRED, "Expired")]

    tenant = tenant_fk()
    requested_by = models.CharField(max_length=150, blank=True, default="")
    by_platform = models.BooleanField(default=False, help_text="asked for by our staff on «فروشگاه»")
    state = models.CharField(max_length=8, choices=STATES, default=QUEUED, db_index=True)
    progress = models.PositiveSmallIntegerField(default=0)          # 0–100
    step = models.CharField(max_length=40, blank=True, default="")  # the dataset being written
    file = models.CharField(max_length=255, blank=True, default="")  # media-relative path (exports/<tenant>/<random>.zip)
    size = models.BigIntegerField(default=0)
    counts = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=500, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    link_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    link_scope = models.CharField(max_length=8, blank=True, default="")   # store | platform: the host the link works on
    link_expires_at = models.DateTimeField(null=True, blank=True)
    downloads = models.PositiveIntegerField(default=0)
    last_download_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tenant_export"
        ordering = ("-created_at", "-id")


class TenantFee(TimeStampedModel):
    """v1.53 (Phase 12, tenancy/fees.py): the monthly store fee — OFF by default, set by our staff on «فروشگاه».
    When on, an agency invoice (kind store_fee) is issued to the reseller on `next_due` every Jalali month, a reminder
    follows `remind_after_days` later and — only when `suspend_enabled` — the store is suspended `suspend_after_days`
    after the due date while the invoice is still unpaid (and made active again once it is paid)."""

    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="fee")
    enabled = models.BooleanField(default=False)
    amount = models.DecimalField(max_digits=14, decimal_places=0, default=0, help_text="tomans per month")
    next_due = models.DateField(null=True, blank=True, help_text="Tehran day the next invoice is issued")
    remind_after_days = models.PositiveSmallIntegerField(default=3, help_text="0 = no reminder")
    suspend_enabled = models.BooleanField(default=False)
    suspend_after_days = models.PositiveSmallIntegerField(default=10)
    updated_by = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        db_table = "tenant_fee"


class TenantFeeInvoice(models.Model):
    """One month's store fee: the agency invoice it became, and what the fee job did about it."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="fee_invoices")
    period = models.CharField(max_length=7, help_text="Jalali year-month, e.g. 1405-09")
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=0)
    invoice = models.ForeignKey("agency.AgencyInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    reminded_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    resumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tenant_fee_invoice"
        ordering = ("-due_date", "-id")
        constraints = [models.UniqueConstraint(fields=["tenant", "period"], name="tenant_fee_invoice_once_per_month")]


class StoreImport(TimeStampedModel):
    """v1.56 (tenancy/importers, docs/store-import.md): customers / services / balances / paid history brought into ONE store
    from another bot's database dump. TENANT table. Made only by our staff on «فروشگاه».

    uploaded → scanning (Celery: parse + read-only PasarGuard scan) → ready (the preview) → running → done | failed; a done
    import can be undone (→ undone). The dump lives under media/imports/ (nginx 404s it, 0600) until the import finishes or
    24 h after upload, then it is deleted; `report` keeps what the CSV needs (no tokens, no cards)."""

    UPLOADED, SCANNING, READY, RUNNING, DONE, FAILED, UNDONE, DISCARDED = (
        "uploaded", "scanning", "ready", "running", "done", "failed", "undone", "discarded")
    STATES = [(s, s.title()) for s in (UPLOADED, SCANNING, READY, RUNNING, DONE, FAILED, UNDONE, DISCARDED)]

    tenant = tenant_fk()
    source = models.CharField(max_length=20, blank=True, default="")       # adapter name (mirza)
    state = models.CharField(max_length=10, choices=STATES, default=UPLOADED, db_index=True)
    file = models.CharField(max_length=255, blank=True, default="")        # media-relative (imports/<tenant>/<random>.sql)
    file_name = models.CharField(max_length=150, blank=True, default="")
    size = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    reseller = models.CharField(max_length=255, blank=True, default="", help_text="the PasarGuard admin whose accounts are linked")
    preview = models.JSONField(default=dict, blank=True)                   # counts + masked rows (the page)
    report = models.JSONField(default=list, blank=True)                    # per service / customer outcome (the CSV)
    options = models.JSONField(default=dict, blank=True)                   # plan map, confirmed credits, checklist
    result = models.JSONField(default=dict, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=500, blank=True, default="")
    created_by = models.CharField(max_length=150, blank=True, default="")
    run_by = models.CharField(max_length=150, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    undone_at = models.DateTimeField(null=True, blank=True)
    file_expires_at = models.DateTimeField(null=True, blank=True)
    backup_log_id = models.IntegerField(null=True, blank=True, help_text="the DB backup taken right before the import")

    class Meta:
        db_table = "tenant_store_import"
        ordering = ("-created_at", "-id")


class ImportRecord(models.Model):
    """One thing a StoreImport created or touched (TENANT): the key for re-runs (never twice) and for «بازگردانی» (undo
    removes only rows with `created` and nothing done since). kind=history rows ARE the read-only payment history of
    the old bot (shown on Customer 360, never revenue)."""

    USER, SERVICE, CREDIT, HISTORY, REFERRAL = "user", "service", "credit", "history", "referral"
    KINDS = [(k, k) for k in (USER, SERVICE, CREDIT, HISTORY, REFERRAL)]

    tenant = tenant_fk()
    batch = models.ForeignKey(StoreImport, on_delete=models.CASCADE, related_name="records")
    kind = models.CharField(max_length=10, choices=KINDS)
    source_key = models.CharField(max_length=100)
    user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.CASCADE, related_name="import_records")
    object_id = models.BigIntegerField(null=True, blank=True)
    created = models.BooleanField(default=True, help_text="false = an existing row was only linked / updated")
    data = models.JSONField(default=dict, blank=True)
    at = models.DateTimeField(null=True, blank=True, help_text="history: when it happened in the old bot")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenant_import_record"
        ordering = ("-at", "-id")
        constraints = [models.UniqueConstraint(fields=["tenant", "kind", "source_key"], name="tenant_import_record_once")]
        indexes = [models.Index(fields=["batch", "kind"])]
