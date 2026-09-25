"""One-time: end every staff/admin session issued before token versioning
(v1.6.2). Needed because the Redis-only refresh-token blacklist was flushed
once, re-enabling already-rotated staff refresh tokens. Customers are not
affected (separate SimpleJWT tokens)."""
from django.db import migrations
from django.db.models import F


def forwards(apps, schema_editor):
    apps.get_model("accounts", "Staff").objects.update(token_version=F("token_version") + 1)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0009_staff_token_version_and_revoked_tokens")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
