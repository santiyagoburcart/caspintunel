import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0015_notify_prefs"),
        ("notifications", "0003_notification_link_alter_notification_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="PushSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("endpoint", models.TextField()),
                ("endpoint_hash", models.CharField(max_length=64, unique=True)),
                ("p256dh", models.CharField(max_length=255)),
                ("auth", models.CharField(max_length=255)),
                ("user_agent", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_ok_at", models.DateTimeField(blank=True, null=True)),
                ("failures", models.PositiveIntegerField(default=0)),
                ("staff", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                            related_name="push_subscriptions", to="accounts.staff")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                           related_name="push_subscriptions", to="accounts.user")),
            ],
            options={"db_table": "push_subscription"},
        ),
    ]
