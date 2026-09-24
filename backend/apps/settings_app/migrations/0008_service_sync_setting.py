"""Bootstrap service_sync_interval_minutes (default 60) and make sure the
"panel: sync all services" beat task exists and matches it — this deploy may
never have run `manage.py seed` (SEED=0 by default), so the periodic task
can't be assumed to already exist.
"""
from django.db import migrations


def forward(apps, schema_editor):
    Setting = apps.get_model("settings_app", "Setting")
    Setting.objects.get_or_create(
        key="service_sync_interval_minutes",
        defaults={"value": "60", "value_type": "int"},
    )

    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    minutes = 60
    s = Setting.objects.filter(key="service_sync_interval_minutes").first()
    if s and s.value:
        try:
            minutes = max(int(s.value), 1)
        except ValueError:
            pass

    schedule, _ = IntervalSchedule.objects.get_or_create(every=minutes, period="minutes")
    PeriodicTask.objects.update_or_create(
        name="panel: sync all services",
        defaults={
            "task": "apps.panel.tasks.sync_all_services",
            "interval": schedule,
            "kwargs": "{}",
            "enabled": True,
        },
    )


def backward(apps, schema_editor):
    Setting = apps.get_model("settings_app", "Setting")
    Setting.objects.filter(key="service_sync_interval_minutes").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("settings_app", "0007_rules_page"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
