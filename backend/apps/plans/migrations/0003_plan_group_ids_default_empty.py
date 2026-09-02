"""Plan.group_ids: default changes from "all panel groups" to empty (inherit).

The old callable default baked every panel group id onto every new plan, so
`resolve_group_ids()` always returned the plan's own full list and the panel's
`default_group_ids` was never consulted — unchecking a group at the panel level
had no effect on provisioning.

New default is an empty list = "inherit the panel default". Existing plans whose
group_ids still equal the old hard-coded full set (i.e. never deliberately
customised) are reset to empty so they start honouring the panel default.
"""
from django.db import migrations, models


OLD_DEFAULT = [5, 6, 8, 10]  # apps.panel.constants.ALL_PANEL_GROUP_IDS at the time


def reset_inherited(apps, schema_editor):
    Plan = apps.get_model("plans", "Plan")
    for plan in Plan.objects.all():
        if sorted(plan.group_ids or []) == sorted(OLD_DEFAULT):
            plan.group_ids = []
            plan.save(update_fields=["group_ids"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("plans", "0002_plan_group_ids"),
    ]

    operations = [
        migrations.AlterField(
            model_name="plan",
            name="group_ids",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="panel group ids for this plan; empty = use the panel's default set",
            ),
        ),
        migrations.RunPython(reset_inherited, noop),
    ]
