"""Caspian light mode: the amber warning colour (#F59E0B) is only ~2:1 against
white, so warning text ("offline", "expired", "email not verified" …) was
barely readable. Darken it to #B45309 (~5:1) in the light palette only; the
dark palette keeps the bright amber."""
from django.db import migrations

_OLD = "#F59E0B"
_NEW = "#B45309"


def _swap(apps, old, new):
    Theme = apps.get_model("settings_app", "Theme")
    t = Theme.objects.filter(name="Caspian").first()
    if not t:
        return
    p = t.palette or {}
    light = p.get("light")
    if isinstance(light, dict) and str(light.get("warning", "")).upper() == old:
        light["warning"] = new
        t.palette = p
        t.save(update_fields=["palette"])


def forward(apps, schema_editor):
    _swap(apps, _OLD, _NEW)


def backward(apps, schema_editor):
    _swap(apps, _NEW, _OLD)


class Migration(migrations.Migration):

    dependencies = [
        ("settings_app", "0008_service_sync_setting"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
