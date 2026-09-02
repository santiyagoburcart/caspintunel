from django.contrib import admin

from .forms import PlanAdminForm
from .models import Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    form = PlanAdminForm
    list_display = (
        "__str__", "panel", "category_fa", "type", "data_limit", "duration_days", "price",
        "discount_percent", "group_ids", "is_active", "sort_order",
    )
    list_filter = ("panel", "type", "is_active", "category_fa")
    search_fields = ("name_fa", "name_en", "category_fa", "category_en")
    list_editable = ("sort_order", "is_active")
    fieldsets = (
        (None, {"fields": ("type", "name_fa", "name_en", "desc_fa", "desc_en",
                           "category_fa", "category_en", "is_active", "sort_order")}),
        ("Quota", {"fields": ("data_limit", "duration_days", "device_limit")}),
        ("Pricing", {"fields": ("price", "discount_percent")}),
        ("Custom volume", {"fields": ("min_gb", "max_gb", "price_per_gb")}),
        ("Panel", {"fields": ("panel", "group_ids"),
                   "description": "group_ids are from the selected panel; empty = that panel's default set"}),
    )
