from django.db import migrations, models


class Migration(migrations.Migration):
    """Additive: staff email + linked Telegram account (ticket notifications)."""

    dependencies = [("accounts", "0010_revoke_all_staff_sessions")]

    operations = [
        migrations.AddField(model_name="staff", name="email",
                            field=models.EmailField(blank=True, default="", max_length=254)),
        migrations.AddField(model_name="staff", name="telegram_id",
                            field=models.BigIntegerField(blank=True, null=True, unique=True)),
        migrations.AddField(model_name="staff", name="telegram_linked_at",
                            field=models.DateTimeField(blank=True, null=True)),
    ]
