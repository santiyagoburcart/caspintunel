from django.db import migrations

# Runs once; afterwards reasons and templates belong to the admin panel.
REASONS = [
    ("اپلیکیشن نصب نشده", "App not installed"),
    ("مشکل در تنظیم / کانفیگ", "Config / setup problem"),
    ("فیلترینگ / اینترنت (ISP)", "Filtering / ISP"),
    ("مشکل دستگاه", "Device issue"),
    ("فعلاً نیازی ندارد", "No need right now"),
    ("قیمت", "Price"),
    ("سایر", "Other"),
]
HELP_FA = ("سلام {name} 👋\nدیدیم چند روزی است به سرویس {service} وصل نشده‌اید. اگر در اتصال مشکلی دارید، "
           "راهنمای اتصال اینجاست: {guide}\nاگر باز هم وصل نشد، همین‌جا یا از بخش پشتیبانی سایت پیام بدهید تا کمکتان کنیم.")
HELP_EN = ("Hi {name} 👋\nWe noticed you haven't connected to {service} for a few days. If something is not working, "
           "here is the connection guide: {guide}\nStill stuck? Message us here or open a support ticket on the website.")


def seed(apps, schema_editor):
    CaseReason = apps.get_model("crm", "CaseReason")
    MessageTemplate = apps.get_model("crm", "MessageTemplate")
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    if not CaseReason.objects.exists():
        for i, (fa, en) in enumerate(REASONS):
            CaseReason.objects.create(name_fa=fa, name_en=en, sort_order=(i + 1) * 10)
    if not MessageTemplate.objects.exists():
        MessageTemplate.objects.create(title="کمک برای اتصال / Help connecting", body_fa=HELP_FA, body_en=HELP_EN, sort_order=10)
    view, _ = Permission.objects.get_or_create(code="crm.view", defaults={"name": "CRM: customer 360, follow-up queue, leads, reports"})
    Permission.objects.get_or_create(code="crm.manage", defaults={"name": "CRM: cases, messages, notes, owners, stages, settings"})
    for role in Role.objects.filter(name="Ticketing"):
        role.permissions.add(view)


class Migration(migrations.Migration):
    dependencies = [("crm", "0001_initial"), ("accounts", "0012_staff_display_name")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
