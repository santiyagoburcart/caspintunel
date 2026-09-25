"""The UI shows Latin digits (0-9) everywhere. Rewrite Persian/Arabic digits
already typed into operator-written display text (plan names, pages, site
config) — digits only, nothing else changes. Not reversible (and needn't be)."""
from django.db import migrations

_TBL = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٪", "01234567890123456789%")

_FIELDS = {
    ("plans", "Plan"): ("name_fa", "name_en", "desc_fa", "desc_en", "category_fa", "category_en"),
    ("settings_app", "Page"): ("title_fa", "title_en", "body_fa", "body_en"),
    ("settings_app", "SiteConfig"): ("site_name_fa", "site_name_en", "bot_description_fa",
                                     "bot_description_en", "meta_description"),
}


def forwards(apps, schema_editor):
    for (app, model), fields in _FIELDS.items():
        M = apps.get_model(app, model)
        for obj in M.objects.all():
            changed = []
            for f in fields:
                v = getattr(obj, f)
                if v and v.translate(_TBL) != v:
                    setattr(obj, f, v.translate(_TBL))
                    changed.append(f)
            if changed:
                obj.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [
        ("settings_app", "0010_app_release"),
        ("plans", "0006_plan_carry_over_data_plan_renewal_mode"),
    ]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
