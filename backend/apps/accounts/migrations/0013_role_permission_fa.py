from django.db import migrations, models


class Migration(migrations.Migration):
    """v1.25.2: Persian labels for permissions and roles (seeded; shown when the panel is fa)."""

    dependencies = [("accounts", "0012_staff_display_name")]

    operations = [
        migrations.AddField(model_name="permission", name="name_fa",
                            field=models.CharField(blank=True, default="", max_length=150)),
        migrations.AddField(model_name="role", name="name_fa",
                            field=models.CharField(blank=True, default="", max_length=100)),
        migrations.AddField(model_name="role", name="description_fa",
                            field=models.CharField(blank=True, default="", max_length=255)),
    ]
