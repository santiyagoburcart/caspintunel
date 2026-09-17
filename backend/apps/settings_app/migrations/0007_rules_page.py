"""Seed/update the "rules" CMS page (Terms of Service) with the real policy
text. Runs once per database on `migrate`, like any migration; update_or_create
by slug just means it works the same whether the page row already exists
(legacy seed data) or not (fresh install).
"""
from django.db import migrations

TITLE_FA = "قوانین و شرایط استفاده"
TITLE_EN = "Terms of Service"

BODY_FA = """۱. حریم خصوصی: ما هیچ اطلاعاتی درباره ترافیک، محتوا یا فعالیت‌های آنلاین کاربران ذخیره نمی‌کنیم. تنها اطلاعات نگهداری‌شده، سوابق خرید برای امور حسابداری است.
۲. هدف سرویس: خدمات ما صرفاً برای دور زدن محدودیت‌های اینترنتی و تحریم‌ها طراحی شده است.
۳. استفاده مجاز: هرگونه استفاده غیراخلاقی، غیرقانونی یا مغایر با قوانین جمهوری اسلامی ایران ممنوع است.
۴. تعلیق سرویس: در صورت مشاهده استفاده غیرمجاز، سرویس کاربر بدون اطلاع قبلی مسدود خواهد شد.
۵. مسئولیت: کاربر مسئول تمام فعالیت‌های انجام‌شده از طریق سرویس خود است."""

BODY_EN = """1. Privacy: We do not store any information about users' traffic, content, or online activities. Only purchase history is retained for accounting purposes.
2. Purpose: Our service is designed solely for bypassing internet restrictions and sanctions.
3. Permitted Use: Any unethical, illegal, or unlawful use is strictly prohibited.
4. Service Suspension: In case of unauthorized use, the user's service will be suspended without prior notice.
5. Responsibility: The user is solely responsible for all activities conducted through their service."""


def forward(apps, schema_editor):
    Page = apps.get_model("settings_app", "Page")
    Page.objects.update_or_create(
        slug="rules",
        defaults={
            "title_fa": TITLE_FA,
            "title_en": TITLE_EN,
            "body_fa": BODY_FA,
            "body_en": BODY_EN,
            "is_active": True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("settings_app", "0006_caspian_brand_green"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
