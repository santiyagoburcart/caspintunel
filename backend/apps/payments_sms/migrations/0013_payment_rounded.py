from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments_sms", "0012_blu_service_check"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="auto_rule",
            field=models.CharField(blank=True, db_default="", db_index=True, default="", max_length=16),
        ),
        migrations.AddField(
            model_name="payment",
            name="auto_reason",
            field=models.JSONField(blank=True, default=dict, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="shortfall",
            field=models.DecimalField(blank=True, decimal_places=0, max_digits=12, null=True),
        ),
    ]
