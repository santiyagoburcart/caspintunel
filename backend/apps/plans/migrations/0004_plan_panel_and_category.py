"""Multi-panel MP-Phase 1: every Plan belongs to exactly one Panel + optional
bilingual category label.

Existing plans are attached to the first (lowest-id) Panel so nothing breaks.
"""
from django.db import migrations, models
import django.db.models.deletion


def attach_existing_plans_to_first_panel(apps, schema_editor):
    Plan = apps.get_model("plans", "Plan")
    Panel = apps.get_model("panel", "Panel")

    if not Plan.objects.filter(panel__isnull=True).exists():
        return
    panel = Panel.objects.order_by("id").first()
    if panel is None:
        raise RuntimeError(
            "cannot migrate: plans exist but no Panel row is configured. "
            "Create a Panel first, then re-run migrate."
        )
    Plan.objects.filter(panel__isnull=True).update(panel=panel)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("plans", "0003_plan_group_ids_default_empty"),
        ("panel", "0003_alter_panel_default_group_ids"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="category_fa",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="plan",
            name="category_en",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="plan",
            name="panel",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="plans",
                to="panel.panel",
                help_text="the panel this plan's services are created / renewed on",
            ),
        ),
        migrations.RunPython(attach_existing_plans_to_first_panel, noop),
        migrations.AlterField(
            model_name="plan",
            name="panel",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="plans",
                to="panel.panel",
                help_text="the panel this plan's services are created / renewed on",
            ),
        ),
    ]
