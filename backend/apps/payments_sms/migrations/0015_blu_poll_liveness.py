from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments_sms", "0014_payment_pending_alert"),
    ]

    operations = [
        migrations.AddField(
            model_name="blucollector",
            name="last_poll_ok_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="blucollector",
            name="poll_error_count",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
