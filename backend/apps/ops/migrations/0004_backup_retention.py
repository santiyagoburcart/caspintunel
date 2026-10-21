import re

from django.db import migrations, models

_TOKEN_IN_URL = re.compile(r"/bot\d+:[A-Za-z0-9_-]+")


def redact_tokens(apps, schema_editor):
    # older send errors carried the full Bot API URL (= the backup bot token)
    BackupLog = apps.get_model("ops", "BackupLog")
    for row in BackupLog.objects.filter(error__contains="/bot").only("id", "error"):
        clean = _TOKEN_IN_URL.sub("/bot<token>", row.error)
        if clean != row.error:
            BackupLog.objects.filter(pk=row.pk).update(error=clean)


class Migration(migrations.Migration):

    dependencies = [
        ("ops", "0003_resourcestat_swap_percent"),
    ]

    operations = [
        migrations.AddField(
            model_name="backuplog",
            name="local_deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="CleanupRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ran_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("freed_bytes", models.BigIntegerField(default=0)),
                ("deleted", models.JSONField(default=dict)),
                ("warnings", models.JSONField(default=list)),
                ("alerted", models.BooleanField(default=False)),
            ],
            options={"db_table": "cleanup_run", "ordering": ("-ran_at",)},
        ),
        migrations.RunPython(redact_tokens, migrations.RunPython.noop),
    ]
