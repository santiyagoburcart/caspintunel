from django.contrib import admin

from .models import Notification, NotificationDelivery


class DeliveryInline(admin.TabularInline):
    model = NotificationDelivery
    extra = 0
    readonly_fields = ("user", "channel", "status", "error", "sent_at")
    can_delete = False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "title", "target_user", "via_site", "via_bot", "via_email", "created_at")
    list_filter = ("type", "via_site", "via_bot", "via_email")
    search_fields = ("title", "body")
    raw_id_fields = ("target_user",)
    inlines = [DeliveryInline]


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = ("id", "notification", "user", "channel", "status", "sent_at")
    list_filter = ("channel", "status")
    search_fields = ("user__username",)
