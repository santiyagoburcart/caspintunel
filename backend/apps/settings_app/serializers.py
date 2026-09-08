from rest_framework import serializers

from .models import Page, SiteConfig, Theme


def rel_media(fieldfile) -> str | None:
    """Root-relative media URL (`/media/...`) — resolves against whatever origin
    the browser is on, so it works behind nginx, the dev proxy, or a custom domain
    without the backend ever guessing its own host."""
    if not fieldfile:
        return None
    url = fieldfile.url
    if url.startswith("http"):
        return url
    return url if url.startswith("/") else "/" + url


class PublicSiteConfigSerializer(serializers.ModelSerializer):
    product_display_mode = serializers.SerializerMethodField()
    logo = serializers.SerializerMethodField()
    favicon = serializers.SerializerMethodField()

    class Meta:
        model = SiteConfig
        fields = ("site_name_fa", "site_name_en", "site_domain", "logo", "favicon",
                  "bot_description_fa", "bot_description_en", "support_telegram", "meta_description",
                  "product_display_mode")

    def get_logo(self, obj) -> str | None:
        return rel_media(obj.logo)

    def get_favicon(self, obj) -> str | None:
        return rel_media(obj.favicon)

    def get_product_display_mode(self, obj) -> str:
        from apps.settings_app.utils import get_setting

        mode = get_setting("product_display_mode", "grouped")
        return mode if mode in ("grouped", "flat") else "grouped"


class PublicThemeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Theme
        fields = ("id", "name", "palette")


class PublicPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = ("slug", "title_fa", "title_en", "body_fa", "body_en", "updated_at")
