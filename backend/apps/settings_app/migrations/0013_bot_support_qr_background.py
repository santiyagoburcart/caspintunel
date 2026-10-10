from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("settings_app", "0012_email_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="bot_support_telegram",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="bot_support_text_fa",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="bot_support_text_en",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="qr_background",
            field=models.CharField(default="caspian-light", max_length=32),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="qr_background_custom",
            field=models.FileField(blank=True, null=True, upload_to="branding/qr/"),
        ),
    ]
