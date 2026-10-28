from django.db import migrations

# copied from apps.accounts.models.GM_PERMS at the time of writing (migrations must not import live code)
GM_PERMS = {
    "agency.gm.view_admins": ("Group manager: view group admins", "مدیر گروه: دیدن ادمین‌های گروه"),
    "agency.gm.create_admin": ("Group manager: create admin (incl. profile title, support link)",
                               "مدیر گروه: ساخت ادمین (با عنوان پروفایل و لینک پشتیبانی)"),
    "agency.gm.add_volume": ("Group manager: add volume", "مدیر گروه: افزودن حجم"),
    "agency.gm.toggle_admin": ("Group manager: enable / disable admin", "مدیر گروه: فعال / غیرفعال‌کردن ادمین"),
    "agency.gm.admin_password": ("Group manager: change admin password", "مدیر گروه: تغییر رمز ادمین"),
    "agency.gm.admin_role": ("Group manager: change admin role", "مدیر گروه: تغییر نقش ادمین"),
    "agency.gm.view_users": ("Group manager: view admins' users", "مدیر گروه: دیدن کاربران ادمین‌ها"),
    "agency.gm.accounting": ("Group manager: view accounting / group statement", "مدیر گروه: دیدن حسابداری و صورت‌حساب گروه"),
    "agency.gm.activity": ("Group manager: view activity", "مدیر گروه: دیدن فعالیت"),
}


def grant(apps, schema_editor):
    """v1.27: every group-manager ability becomes its own permission. Roles that are
    group-manager roles today (they hold agency.group_manager) get all of them once, so
    nothing a manager can do changes with this release; the operator narrows them later."""
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    perms = [Permission.objects.update_or_create(code=c, defaults={"name": en, "name_fa": fa})[0]
             for c, (en, fa) in GM_PERMS.items()]
    for role in Role.objects.filter(permissions__code="agency.group_manager").distinct():
        role.permissions.add(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("agency", "0008_link_group_manager_staff"),
        ("accounts", "0013_role_permission_fa"),
    ]

    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
