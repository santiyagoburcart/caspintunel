"""Add the "Caspian" theme (inactive) for existing installs.

`seed` also creates it, but seed only re-runs on container start / update, so
this makes it available immediately after a plain `migrate`. Never touches
`is_active` — the active theme stays whatever the admin chose.
"""
from django.db import migrations

CASPIAN = {
    "style": "caspian",
    "light": {
        "background": "#F8FAFC", "surface": "#FFFFFF", "primary": "#0284C7",
        "secondary": "#0EA5E9", "success": "#10B981", "danger": "#F43F5E", "warning": "#F59E0B",
        "text": "#0F172A", "text_muted": "#64748B", "border": "#E2E8F0",
    },
    "dark": {
        "background": "#080B14", "surface": "#0D111F", "primary": "#8B5CF6",
        "secondary": "#06B6D4", "success": "#10B981", "danger": "#EF4444", "warning": "#F59E0B",
        "text": "#E0E2EF", "text_muted": "#94A3B8", "border": "#1E2640",
    },
    "vars": {
        "--csp-font-ui-light": "'Inter'", "--csp-font-ui-dark": "'Plus Jakarta Sans'",
        "--csp-font-display-light": "'Space Grotesk'", "--csp-font-display-dark": "'Plus Jakarta Sans'",
        "--csp-well-light": "#F8FAFC", "--csp-well-dark": "#060910",
        "--csp-muted-bg-light": "#F1F5F9", "--csp-muted-bg-dark": "#181B25",
        "--csp-text2-light": "#1E293B", "--csp-text2-dark": "#CBC3D7",
        "--csp-text3-light": "#334155", "--csp-text3-dark": "#94A3B8",
        "--csp-border-strong-light": "#CBD5E1", "--csp-border-strong-dark": "#494454",
        "--csp-signal-light": "#38BDF8", "--csp-signal-dark": "#06B6D4",
        "--csp-vibrant-light": "#0369A1", "--csp-vibrant-dark": "#7C3AED",
        "--csp-gauge-from-light": "#38BDF8", "--csp-gauge-from-dark": "#06B6D4",
        "--csp-gauge-to-light": "#0284C7", "--csp-gauge-to-dark": "#8B5CF6",
        "--csp-glow-light": "rgba(2,132,199,0.28)", "--csp-glow-dark": "rgba(139,92,246,0.45)",
        "--csp-radius-card-light": "0.75rem", "--csp-radius-card-dark": "1rem",
    },
}


def add_caspian(apps, schema_editor):
    Theme = apps.get_model("settings_app", "Theme")
    if not Theme.objects.filter(name="Caspian").exists():
        Theme.objects.create(name="Caspian", palette=CASPIAN, is_active=False)


def remove_caspian(apps, schema_editor):
    Theme = apps.get_model("settings_app", "Theme")
    Theme.objects.filter(name="Caspian", is_active=False).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("settings_app", "0003_royal_frost_theme"),
    ]

    operations = [
        migrations.RunPython(add_caspian, remove_caspian),
    ]
