from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments_sms", "0013_payment_rounded"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="pending_alerted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="pending_resolved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
