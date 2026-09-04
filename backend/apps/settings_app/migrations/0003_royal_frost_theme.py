"""Add the "Royal Frost" theme (inactive) for existing installs.

`seed` also creates it, but seed only re-runs on container start / update, so
this makes it available immediately after a plain `migrate`. Never touches
`is_active` — Midnight Aurora stays the active theme unless the admin switches.
"""
from django.db import migrations

ROYAL_FROST = {
    "base": "light",
    "style": "frost",
    "light": {
        "background": "#EEF3FB", "surface": "rgba(255,255,255,0.55)", "primary": "#2E56C8",
        "secondary": "#5B8DEF", "success": "#16A34A", "danger": "#DC2626", "warning": "#D97706",
        "text": "#1F2F55", "text_muted": "#6B7A9C", "border": "rgba(46,86,200,0.14)",
    },
    "dark": {
        "background": "#EEF3FB", "surface": "rgba(255,255,255,0.55)", "primary": "#2E56C8",
        "secondary": "#5B8DEF", "success": "#16A34A", "danger": "#DC2626", "warning": "#D97706",
        "text": "#1F2F55", "text_muted": "#6B7A9C", "border": "rgba(46,86,200,0.14)",
    },
    "vars": {
        "--c-primary-2": "#3B6FE0", "--c-ink": "#1E3A8A", "--c-glass-border": "rgba(255,255,255,0.85)",
    },
}


def add_royal_frost(apps, schema_editor):
    Theme = apps.get_model("settings_app", "Theme")
    if not Theme.objects.filter(name="Royal Frost").exists():
        Theme.objects.create(name="Royal Frost", palette=ROYAL_FROST, is_active=False)


def remove_royal_frost(apps, schema_editor):
    Theme = apps.get_model("settings_app", "Theme")
    Theme.objects.filter(name="Royal Frost", is_active=False).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("settings_app", "0002_alter_siteconfig_site_domain"),
    ]

    operations = [
        migrations.RunPython(add_royal_frost, remove_royal_frost),
    ]
