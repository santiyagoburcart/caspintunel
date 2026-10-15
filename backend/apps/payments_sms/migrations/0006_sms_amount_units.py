from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments_sms", "0005_smsmessage_sender_note"),
    ]

    operations = [
        migrations.AddField(
            model_name="smssource",
            name="amount_unit",
            field=models.CharField(choices=[("rial", "Rial"), ("toman", "Toman")], db_default="rial", default="rial", max_length=5),
        ),
        migrations.AddField(
            model_name="smsmessage",
            name="parsed_raw",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="smsmessage",
            name="parsed_unit",
            field=models.CharField(blank=True, db_default="", default="", max_length=5),
        ),
    ]
