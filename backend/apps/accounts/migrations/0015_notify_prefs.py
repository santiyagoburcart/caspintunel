from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0014_user_purge"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="notify_sound",
            field=models.BooleanField(db_default=True, default=True),
        ),
        migrations.AddField(
            model_name="staff",
            name="notify_prefs",
            field=models.JSONField(blank=True, default=dict, null=True),
        ),
    ]
