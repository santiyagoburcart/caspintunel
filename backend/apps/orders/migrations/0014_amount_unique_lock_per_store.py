from django.db import migrations, models


class Migration(migrations.Migration):
    """v1.47 multi-tenant Phase 5: the unique-amount lock is unique per store. The composite constraint is added FIRST, then
    the old global unique index is dropped — never a moment without a constraint, and the old release (still serving during
    the rolling update) keeps working: today only our store has orders, so both rules are the same."""

    dependencies = [("orders", "0013_order_provision_error_order_provision_failed_at_and_more")]

    operations = [
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(fields=["tenant", "amount_unique_lock"], name="order_tenant_amount_lock"),
        ),
        migrations.AlterField(
            model_name="order",
            name="amount_unique_lock",
            field=models.DecimalField(blank=True, decimal_places=0, editable=False, max_digits=12, null=True),
        ),
    ]
