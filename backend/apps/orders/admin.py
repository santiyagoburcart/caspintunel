from django.contrib import admin

from .models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "type", "plan", "amount", "amount_unique", "status", "source", "created_at")
    list_filter = ("status", "type", "source")
    search_fields = ("user__username", "requested_account_name")
    raw_id_fields = ("user", "service", "plan")
    readonly_fields = ("amount_unique_lock", "created_at", "updated_at")
