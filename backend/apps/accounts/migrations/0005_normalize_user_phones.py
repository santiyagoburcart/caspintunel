"""Normalize every stored User.phone to the canonical form
("+989107323128" -> "09107323128", Persian digits -> ASCII, separators
stripped). Values that aren't a phone at all are left untouched.

Uniqueness is enforced in the application (apps.accounts.phone), not by a DB
constraint, so pre-existing duplicates can't break this migration — they are
only reported here for an admin to resolve.
"""
from collections import defaultdict

from django.db import migrations


def normalize(apps, schema_editor):
    from apps.accounts.phone import normalize_ir_phone, normalize_phone

    User = apps.get_model("accounts", "User")
    changed = 0
    owners = defaultdict(list)
    for u in User.objects.exclude(phone="").only("id", "username", "phone").iterator():
        new = normalize_ir_phone(u.phone) or normalize_phone(u.phone) or u.phone.strip()
        if new != u.phone:
            User.objects.filter(pk=u.pk).update(phone=new)
            changed += 1
        owners[new].append(f"#{u.pk} {u.username}")

    dups = {p: us for p, us in owners.items() if len(us) > 1}
    print(f"\n  phones normalized: {changed}")
    if dups:
        print(f"  ⚠ {len(dups)} phone number(s) shared by several accounts (resolve in the admin panel):")
        for phone, users in sorted(dups.items()):
            print(f"    {phone}: {', '.join(users)}")


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_services_delete_permission")]

    operations = [migrations.RunPython(normalize, migrations.RunPython.noop)]
