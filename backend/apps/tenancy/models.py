"""Multi-tenant reseller storefronts (docs/multi-tenant.md). Phase 1 Release A: the tenant tables and a nullable
`tenant` on every tenant table, filled with the default tenant. Nothing reads them yet (Release B adds the middleware
and scoped managers)."""
import secrets

from django.db import models

from apps.common.models import TimeStampedModel


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


from .fields import tenant_fk  # noqa: E402,F401 — re-export
