"""Pin the Caspian success colour to the brand green (#11AB53).

Only the "Caspian" theme row's `success` (light + dark) changes; everything
else in the palette is left as-is. `is_active` is never touched.
"""
from django.db import migrations

_OLD_GREEN = "#10B981"
_NEW_GREEN = "#11AB53"


def _swap(apps, old, new):
    Theme = apps.get_model("settings_app", "Theme")
    t = Theme.objects.filter(name="Caspian").first()
    if not t:
        return
    p = t.palette or {}
    for mode in ("light", "dark"):
        if isinstance(p.get(mode), dict) and p[mode].get("success") == old:
            p[mode]["success"] = new
    t.palette = p
    t.save(update_fields=["palette"])


def forward(apps, schema_editor):
    _swap(apps, _OLD_GREEN, _NEW_GREEN)


def backward(apps, schema_editor):
    _swap(apps, _NEW_GREEN, _OLD_GREEN)


class Migration(migrations.Migration):

    dependencies = [
        ("settings_app", "0005_caspian_brand_blue"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
