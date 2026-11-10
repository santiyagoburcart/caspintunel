from django.db import migrations, models


class Migration(migrations.Migration):
    """v1.52 multi-tenant Phase 8: role names unique per store (two stores may each have «پشتیبانی»). Dropping the global
    unique index first is backward compatible; the old release only ever creates platform roles with unique names."""

    dependencies = [("accounts", "0018_alter_deleteduserarchive_tenant_and_more")]

    operations = [
        migrations.AlterField("role", "name", models.CharField(max_length=100)),
        migrations.AddConstraint("role", models.UniqueConstraint(fields=("tenant", "name"), name="role_tenant_name")),
    ]
