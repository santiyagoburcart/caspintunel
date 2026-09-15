"""Service usage / expiry alerts (flowchart 1.9)."""
from __future__ import annotations

import logging

from django.utils import timezone

from apps.common.jalali import to_jalali_str
from apps.notifications.dispatch import notify_user
from apps.notifications.models import NotificationType
from apps.panel.models import Service, ServiceStatus
from apps.settings_app.utils import get_setting

log = logging.getLogger("caspintunel")

_WATCHED = (ServiceStatus.ACTIVE, ServiceStatus.ON_HOLD, ServiceStatus.LIMITED)


def run_service_alerts() -> dict:
    vol_pct = int(get_setting("alert_volume_percent", 80))
    exp_days = int(get_setting("alert_expire_days", 3))
    now = timezone.now()
    vol_sent = exp_sent = 0

    qs = Service.objects.filter(status__in=_WATCHED).select_related("user")
    for svc in qs.iterator():
        updates = []

        if svc.data_limit and not svc.alert_vol_sent:
            used_pct = svc.data_used / svc.data_limit * 100
            if used_pct >= vol_pct:
                _send_volume_alert(svc, used_pct)
                svc.alert_vol_sent = True
                updates.append("alert_vol_sent")
                vol_sent += 1

        if svc.expire_at and not svc.alert_exp_sent:
            days_left = (svc.expire_at - now).days
            if days_left <= exp_days:
                _send_expiry_alert(svc, max(days_left, 0))
                svc.alert_exp_sent = True
                updates.append("alert_exp_sent")
                exp_sent += 1

        if updates:
            updates.append("updated_at")
            svc.save(update_fields=updates)

    return {"volume_alerts": vol_sent, "expiry_alerts": exp_sent}


def _send_volume_alert(svc, used_pct):
    gb = svc.data_limit / 1024**3
    notify_user(
        svc.user,
        title="هشدار اتمام حجم سرویس",
        body=(f"سرویس «{svc.panel_username}» حدود {used_pct:.0f}٪ از {gb:.0f} گیگابایت حجم را "
              "مصرف کرده است. برای جلوگیری از قطعی، سرویس را تمدید کنید."),
        title_en="Service volume warning",
        body_en=(f"Service \"{svc.panel_username}\" has used about {used_pct:.0f}% of its {gb:.0f}GB "
                 "quota. Renew it to avoid an interruption."),
        ntype=NotificationType.VOLUME_WARNING,
        via_site=True, via_bot=True, via_email=True,
    )


def _send_expiry_alert(svc, days_left):
    when = to_jalali_str(svc.expire_at, "%Y/%m/%d")
    notify_user(
        svc.user,
        title="هشدار انقضای سرویس",
        body=(f"سرویس «{svc.panel_username}» تا {days_left} روز دیگر (‌{when}‌) منقضی می‌شود. "
              "برای ادامهٔ استفاده آن را تمدید کنید."),
        title_en="Service expiry warning",
        body_en=(f"Service \"{svc.panel_username}\" expires in {days_left} day(s) ({when}). "
                 "Renew it to keep using it."),
        ntype=NotificationType.EXPIRY_WARNING,
        via_site=True, via_bot=True, via_email=True,
    )
