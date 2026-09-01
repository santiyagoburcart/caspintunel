from django.contrib import admin

from .models import BankCard, Payment, SmsAppDevice, SmsMessage, SmsSource


@admin.register(BankCard)
class BankCardAdmin(admin.ModelAdmin):
    list_display = ("card_number", "holder_name", "bank_name", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")


@admin.register(SmsSource)
class SmsSourceAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "description", "is_active")
    list_editable = ("is_active",)


@admin.register(SmsAppDevice)
class SmsAppDeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "last_seen_at", "created_at")
    readonly_fields = ("api_token", "last_seen_at", "created_at")
    actions = ("regenerate_token",)

    @admin.action(description="Regenerate API token (invalidates the old one)")
    def regenerate_token(self, request, queryset):
        from .models import generate_device_token

        for device in queryset:
            device.api_token = generate_device_token()
            device.save(update_fields=["api_token"])
        self.message_user(request, f"regenerated {queryset.count()} token(s)")


@admin.register(SmsMessage)
class SmsMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "sms_source", "device", "parsed_amount", "matched_order", "received_at")
    list_filter = ("device", "sms_source")
    search_fields = ("raw_text",)
    readonly_fields = ("received_at",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "method", "amount", "status", "bank_card", "confirmed_by", "confirmed_at")
    list_filter = ("status", "method", "confirmed_by", "bank_card")
    search_fields = ("order__user__username", "gateway_ref")
    raw_id_fields = ("order", "sms_message", "confirmed_by_staff")
    readonly_fields = ("created_at", "updated_at")
