# v1.53: invoice kind store_fee (choices only, no schema change)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agency', '0013_gm_full_stats'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agencyinvoice',
            name='kind',
            field=models.CharField(choices=[('quota_charge', 'Volume (staff)'), ('manual_charge', 'Manual charge'), ('request', 'Volume request / group manager'), ('settlement', 'Previous balance'), ('store_fee', 'Store monthly fee')], max_length=16),
        ),
    ]
