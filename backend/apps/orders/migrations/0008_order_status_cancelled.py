from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0007_order_needs_new_name"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(choices=[("pending_payment", "Pending payment"), ("paid", "Paid"),
                                            ("completed", "Completed"), ("rejected", "Rejected"), ("failed", "Failed"),
                                            ("expired", "Reservation expired"), ("cancelled", "Cancelled")],
                                   db_index=True, default="pending_payment", max_length=16),
        ),
    ]
