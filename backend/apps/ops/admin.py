from django.contrib import admin

from .models import BackupLog, HealthCheck, ResourceStat


@admin.register(BackupLog)
class BackupLogAdmin(admin.ModelAdmin):
    list_display = ("filename", "size", "status", "sent_to_telegram", "created_at")
    list_filter = ("status", "sent_to_telegram")
    readonly_fields = ("created_at",)


@admin.register(HealthCheck)
class HealthCheckAdmin(admin.ModelAdmin):
    list_display = ("target", "is_up", "latency_ms", "checked_at")
    list_filter = ("target", "is_up")
    readonly_fields = ("checked_at",)


@admin.register(ResourceStat)
class ResourceStatAdmin(admin.ModelAdmin):
    list_display = ("sampled_at", "cpu_percent", "ram_percent", "disk_percent", "bandwidth_used")
    readonly_fields = ("sampled_at",)
