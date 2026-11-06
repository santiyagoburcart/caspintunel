"""v1.42.1: a service without a plan gets the plan of its last paid order (so «تمدید» offers it in one tap).
Idempotent: only services whose current_plan is NULL are touched; services without any paid order stay as they are
(the customer then picks from the plan list). Production on 2026-11-06: 0 services without a plan."""
from django.db import migrations


def forward(apps, schema_editor):
    Service = apps.get_model("panel", "Service")
    Order = apps.get_model("orders", "Order")
    for svc in Service.objects.filter(current_plan__isnull=True).iterator():
        o = (Order.objects.filter(service_id=svc.pk, status__in=("paid", "completed"), plan__isnull=False)
             .exclude(type="addon_volume").order_by("-id").first())
        if o is not None:
            Service.objects.filter(pk=svc.pk, current_plan__isnull=True).update(current_plan_id=o.plan_id)


class Migration(migrations.Migration):
    dependencies = [
        ("panel", "0006_alter_service_tenant"),
        ("orders", "0013_order_provision_error_order_provision_failed_at_and_more"),
    ]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
