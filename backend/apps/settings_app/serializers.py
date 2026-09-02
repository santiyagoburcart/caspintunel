from rest_framework import serializers

from .models import Page, SiteConfig, Theme


class PublicSiteConfigSerializer(serializers.ModelSerializer):
    product_display_mode = serializers.SerializerMethodField()

    class Meta:
        model = SiteConfig
        fields = ("site_name_fa", "site_name_en", "site_domain", "logo", "favicon",
                  "bot_description_fa", "bot_description_en", "support_telegram", "meta_description",
                  "product_display_mode")

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
