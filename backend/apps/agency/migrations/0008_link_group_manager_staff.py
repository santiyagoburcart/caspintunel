from django.db import migrations

GM_ROLE = "Group manager"
GM_PERM = "agency.group_manager"


def link(apps, schema_editor):
    """v1.25.2: a staff given the "Group manager" role on the Staff page (before this
    release nothing created its manager record, so no group could be assigned) gets a
    linked GroupManager — same username and password hash, inactive if the staff is,
    and NO groups: those are assigned by an operator."""
    Staff = apps.get_model("accounts", "Staff")
    GroupManager = apps.get_model("agency", "GroupManager")
    linked = set(GroupManager.objects.exclude(staff=None).values_list("staff_id", flat=True))
    for s in Staff.objects.filter(is_superadmin=False).exclude(role=None).select_related("role"):
        if s.pk in linked:
            continue
        if s.role.name != GM_ROLE and not s.role.permissions.filter(code=GM_PERM).exists():
            continue
        m = GroupManager.objects.filter(username__iexact=s.username).first()
        if m is not None and m.staff_id:
            continue                                   # name taken by another link — leave it
        if m is None:
            m = GroupManager(username=s.username, created_by="migration 0008")
        m.staff_id = s.pk
        m.password = s.password_hash
        m.is_active = s.is_active
        m.display_name = (s.display_name or m.display_name or "")[:100]
        m.save()


class Migration(migrations.Migration):
    dependencies = [
        ("agency", "0007_group_manager_staff"),
        ("accounts", "0013_role_permission_fa"),
    ]

    operations = [migrations.RunPython(link, migrations.RunPython.noop)]
