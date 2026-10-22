from django.db import migrations
from django.utils import timezone

RULES = [
    ("data", 80, "مصرف {service} به 80% رسید", "{service} has used 80% of its data",
     "سلام {name}، از حجم سرویس {service} فقط {remaining_gb} گیگ مانده است. برای قطع نشدن، همین حالا تمدید کنید:\n{renew}",
     "Hi {name}, only {remaining_gb} GB is left on {service}. Renew now to stay connected:\n{renew}"),
    ("data", 95, "حجم {service} تقریباً تمام شد", "{service} is almost out of data",
     "سلام {name}، فقط {remaining_gb} گیگ از سرویس {service} مانده است. با یک کلیک تمدید کنید:\n{renew}",
     "Hi {name}, just {remaining_gb} GB left on {service}. Renew in one click:\n{renew}"),
    ("time", 3, "{service} تا {remaining_days} روز دیگر منقضی می‌شود", "{service} expires in {remaining_days} days",
     "سلام {name}، سرویس {service} تا {remaining_days} روز دیگر منقضی می‌شود. برای ادامه، تمدید کنید:\n{renew}",
     "Hi {name}, {service} expires in {remaining_days} days. Renew to keep using it:\n{renew}"),
    ("time", 1, "{service} فردا منقضی می‌شود", "{service} expires tomorrow",
     "سلام {name}، سرویس {service} کمتر از یک روز دیگر منقضی می‌شود. همین حالا تمدید کنید:\n{renew}",
     "Hi {name}, {service} expires within a day. Renew now:\n{renew}"),
]
WINBACK_REASONS = [
    ("قیمت", "Price"), ("سرویس دیگری گرفته", "Switched to another provider"), ("فعلاً نیازی ندارد", "No need right now"),
    ("کیفیت / سرعت", "Quality / speed"), ("مشکل پرداخت", "Payment problem"), ("سایر", "Other"),
]
WB_FA = ("سلام {name} 👋\nسرویس {service} شما تمام شده و جایتان خالی است! برای برگشتن کافی است تمدید کنید:\n{renew}\n"
         "کد تخفیف ویژهٔ شما: {code} ({percent}٪ تا {code_expires})")
WB_EN = ("Hi {name} 👋\nYour service {service} has ended — we'd love to have you back. Renew here:\n{renew}\n"
         "Your personal discount code: {code} ({percent}% until {code_expires})")


def _period(s):
    exp = s.expire_at.strftime("%Y%m%d%H") if s.expire_at else "noexp"
    return f"{exp}:{int(s.data_limit or 0)}"


def seed(apps, schema_editor):
    WarningRule = apps.get_model("crm", "WarningRule")
    CaseReason = apps.get_model("crm", "CaseReason")
    MessageTemplate = apps.get_model("crm", "MessageTemplate")
    ServiceWarning = apps.get_model("crm", "ServiceWarning")
    Service = apps.get_model("panel", "Service")
    if not WarningRule.objects.exists():
        for kind, thr, tfa, ten, bfa, ben in RULES:
            WarningRule.objects.create(kind=kind, threshold=thr, title_fa=tfa, title_en=ten, body_fa=bfa, body_en=ben)
    if not CaseReason.objects.filter(category="winback").exists():
        for i, (fa, en) in enumerate(WINBACK_REASONS):
            CaseReason.objects.create(category="winback", name_fa=fa, name_en=en, sort_order=(i + 1) * 10)
    if not MessageTemplate.objects.filter(category="winback").exists():
        MessageTemplate.objects.create(category="winback", title="بازگشت مشتری / Win-back", body_fa=WB_FA, body_en=WB_EN, sort_order=10)
    # services the old fixed alert (80 % / 3 days) already warned this period: record it, so they
    # are not warned for the same threshold again by the new system
    now = timezone.now()
    for s in Service.objects.filter(status="active").filter(alert_vol_sent=True) | Service.objects.filter(status="active", alert_exp_sent=True):
        for flag, kind, thr in (("alert_vol_sent", "data", 80), ("alert_exp_sent", "time", 3)):
            if getattr(s, flag):
                ServiceWarning.objects.get_or_create(
                    service=s, kind=kind, threshold=thr, period_key=_period(s),
                    defaults={"site_sent_at": now, "bot_sent_at": now, "email_sent_at": now,
                              "bot_error": "skipped: sent by the old alert", "email_error": "skipped: sent by the old alert"})


class Migration(migrations.Migration):
    dependencies = [("crm", "0003_casereason_category_followupcase_ended_at_and_more"), ("panel", "0004_service_panel_username_per_panel")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
