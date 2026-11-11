# v1.55: plan type ساب / فقط وایرگارد / هر دو — existing plans stay «ساب»

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('plans', '0009_plan_renewable_when_inactive'),
    ]

    operations = [
        migrations.AddField(
            model_name='plan',
            name='vpn_type',
            field=models.CharField(choices=[('sub', 'Subscription (V2Ray)'), ('wireguard', 'WireGuard only'), ('both', 'Both')], default='sub', max_length=10),
        ),
    ]
