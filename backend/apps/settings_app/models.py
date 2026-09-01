import json

from django.core.exceptions import ValidationError
from django.db import models


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
