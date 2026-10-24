import json

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.fields import EncryptedTextField


class ValueType(models.TextChoices):
    STR = "str", "String"
    INT = "int", "Integer"
    BOOL = "bool", "Boolean"
    JSON = "json", "JSON"


class Setting(models.Model):
    """Typed key-value config (data-model · Module 8 · `setting`)."""

    key = models.CharField(max_length=100, unique=True)
    value = models.TextField(blank=True)
    value_type = models.CharField(max_length=4, choices=ValueType.choices, default=ValueType.STR)

    class Meta:
        db_table = "setting"
        ordering = ("key",)

    def __str__(self) -> str:
        return self.key

    @property
    def typed(self):
        if self.value_type == ValueType.INT:
            return int(self.value or 0)
        if self.value_type == ValueType.BOOL:
            return str(self.value).strip().lower() in ("1", "true", "yes", "on")
        if self.value_type == ValueType.JSON:
            return json.loads(self.value or "null")
        return self.value

    def clean(self):
        if self.value_type == ValueType.JSON and self.value:
            try:
                json.loads(self.value)
            except ValueError as exc:
                raise ValidationError({"value": f"invalid JSON: {exc}"})


class SiteConfig(models.Model):
    """Single-row dynamic branding (data-model · Module 8 · `site_config`)."""

    site_name_fa = models.CharField(max_length=120, default="کسپین تانل")
    site_name_en = models.CharField(max_length=120, default="caspintunel")
    site_domain = models.CharField(max_length=120, default="aicaspin.ir")
    logo = models.FileField(upload_to="branding/", null=True, blank=True)
    favicon = models.FileField(upload_to="branding/", null=True, blank=True)
    bot_description_fa = models.TextField(blank=True)
    bot_description_en = models.TextField(blank=True)
    support_telegram = models.CharField(max_length=64, blank=True)
    # sales-bot 💬 Support screen: its own contacts (comma/space separated
    # @ids or t.me links; empty → support_telegram) and an optional message
    bot_support_telegram = models.CharField(max_length=255, blank=True, default="")
    bot_support_text_fa = models.TextField(blank=True, default="")
    bot_support_text_en = models.TextField(blank=True, default="")
    # subscription QR background (apps/common/qrcard.py): "plain", a built-in key or "custom"
    qr_background = models.CharField(max_length=32, default="caspian-light")
    qr_background_custom = models.FileField(upload_to="branding/qr/", null=True, blank=True)
    meta_description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "site_config"
        verbose_name = verbose_name_plural = "site config"

    def __str__(self) -> str:
        return self.site_name_en

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "SiteConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Theme(models.Model):
    """data-model · Module 8 · `theme`."""

    name = models.CharField(max_length=80, unique=True)
    palette = models.JSONField(default=dict)
    is_active = models.BooleanField(default=False)

    class Meta:
        db_table = "theme"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            Theme.objects.exclude(pk=self.pk).filter(is_active=True).update(is_active=False)


class Page(models.Model):
    """CMS page — rules / tutorial / faq (data-model · Module 8 · `page`)."""

    slug = models.SlugField(max_length=50, unique=True)
    title_fa = models.CharField(max_length=200)
    title_en = models.CharField(max_length=200, blank=True)
    body_fa = models.TextField(blank=True)
    body_en = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "page"
        ordering = ("slug",)

    def __str__(self) -> str:
        return self.slug


class AppPlatform(models.TextChoices):
    ANDROID = "android", "Android SMS bridge app"
    IOS = "ios", "iPhone shortcut"


class AppRelease(models.Model):
    """The operator tools an admin hands to the phone that receives the bank
    SMS: the Android "SMS Bridge" APK and the iPhone Shortcut. Files live in
    private media (never a public URL) and are downloaded from our own server
    through the admin API — works on an offline / Iran-only server. The
    Android row falls back to the APK bundled in the repo
    (mobile_sms/release, mounted at APP_RELEASES_DIR) when nothing was uploaded."""

    platform = models.CharField(max_length=10, choices=AppPlatform.choices, unique=True)
    file = models.FileField(upload_to="apps/", blank=True)
    version = models.CharField(max_length=40, blank=True)
    link = models.URLField(blank=True, help_text="optional external link (e.g. the iCloud shortcut link)")
    notes = models.TextField(blank=True, help_text="release notes / extra instructions shown to admins")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = "app_release"
        ordering = ("platform",)

    def __str__(self) -> str:
        return f"{self.platform} {self.version}".strip()


class EmailSecurity(models.TextChoices):
    STARTTLS = "starttls", "STARTTLS"
    SSL = "ssl", "SSL/TLS"
    NONE = "none", "None"


class EmailSettings(models.Model):
    """Outgoing-mail relay, edited in the admin panel (single row).

    Django talks to the relay DIRECTLY (apps.common.mail.DynamicEmailBackend),
    so a change applies on the next send — no container restart, and the web
    app never touches the mailserver container. Fallback when `enabled` is off:
    .env SMTP settings → local mailserver (see CLAUDE.md)."""

    enabled = models.BooleanField(default=False)
    host = models.CharField(max_length=255, blank=True)
    port = models.PositiveIntegerField(default=587)
    security = models.CharField(max_length=10, choices=EmailSecurity.choices, default=EmailSecurity.STARTTLS)
    username = models.CharField(max_length=255, blank=True)
    password = EncryptedTextField(blank=True, help_text="stored encrypted at rest; never returned by the API")
    from_email = models.EmailField(blank=True)
    from_name = models.CharField(max_length=120, blank=True)
    # delivery status, written by the backend on every app email
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_source = models.CharField(max_length=10, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "email_settings"
        verbose_name_plural = "email settings"

    def __str__(self) -> str:
        return f"email relay {'on' if self.enabled else 'off'} ({self.host or '-'})"

    @classmethod
    def load(cls) -> "EmailSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class DomainConfig(models.Model):
    """Settings → Domain & Cloudflare (single row). The Cloudflare token is
    write-only: stored encrypted, never returned by the API (.env
    CLOUDFLARE_API_TOKEN stays the fallback)."""

    cloudflare_token = EncryptedTextField(blank=True, help_text="stored encrypted at rest; never returned by the API")
    token_updated_at = models.DateTimeField(null=True, blank=True)
    token_updated_by = models.CharField(max_length=150, blank=True)
    last_test = models.JSONField(default=dict, blank=True)   # last "Test" result (no secrets)
    transition_days = models.PositiveSmallIntegerField(default=14)
    # access mode (docs/access-mode.md): how visitors reach the site under the same domain.
    # Nothing about the tunnel is hard-coded — IPs, sources and PROXY ports are edited here.
    access_mode = models.CharField(max_length=10, default="direct")      # direct | cloudflare | tunnel
    iran_ips = models.JSONField(default=list, blank=True)                 # tunnel entry IP(s) → the A record
    tunnel_sources = models.JSONField(default=list, blank=True)           # IPs / CIDRs the tunnel arrives from
    proxy_protocol = models.JSONField(default=dict, blank=True)           # {"80": false, "443": false}
    cf_ranges = models.JSONField(default=dict, blank=True)                # {"v4": [...], "v6": [...], "at": iso}
    access_state = models.JSONField(default=dict, blank=True)             # last / running switch (steps, records)
    dns01 = models.JSONField(default=dict, blank=True)                    # certificate renewal via DNS-01 (host result)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "domain_config"
        verbose_name = verbose_name_plural = "domain config"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "DomainConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class DomainChange(models.Model):
    """One run of the domain-change wizard (docs/domain.md). `steps` holds a
    status per step: {key: {state, message, at, detail}}."""

    class Status(models.TextChoices):
        DRAFT = "draft", "draft"              # entered, DNS / TLS in progress
        APPLYING = "applying", "applying"     # host is switching
        TRANSITION = "transition", "transition"   # live on the new domain, old one redirects
        DONE = "done", "done"                 # old domain removed
        FAILED = "failed", "failed"           # apply failed (rolled back by the host)
        ROLLED_BACK = "rolled_back", "rolled back"
        CANCELLED = "cancelled", "cancelled"

    old_domain = models.CharField(max_length=253)
    new_domain = models.CharField(max_length=253)
    include_www = models.BooleanField(default=True)
    mode = models.CharField(max_length=12, default="cloudflare")   # cloudflare | manual
    zone_id = models.CharField(max_length=64, blank=True)
    zone_name = models.CharField(max_length=253, blank=True)
    server_ip = models.CharField(max_length=45, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    steps = models.JSONField(default=dict, blank=True)
    checklist = models.JSONField(default=dict, blank=True)
    transition_days = models.PositiveSmallIntegerField(default=14)
    old_until = models.DateTimeField(null=True, blank=True)
    created_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "domain_change"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.old_domain} → {self.new_domain} ({self.status})"
