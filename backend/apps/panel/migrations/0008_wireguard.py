# v1.55 WireGuard: Service.wireguard (mirrored by the sync) + «مکان‌های وایرگارد» pre-filled with today's five locations

from django.db import migrations, models


LOCATIONS = [  # host remark codes on PasarGuard 5.6 (2026-11-11): Ita / tu / de / nl / IR
    ("Ita", "ایتالیا", "Italy", "\U0001F1EE\U0001F1F9", "italy", 1),
    ("tu", "ترکیه", "Türkiye", "\U0001F1F9\U0001F1F7", "turkiye", 2),
    ("de", "آلمان", "Germany", "\U0001F1E9\U0001F1EA", "germany", 3),
    ("nl", "هلند", "Netherlands", "\U0001F1F3\U0001F1F1", "netherlands", 4),
    ("IR", "ایران", "Iran", "\U0001F1EE\U0001F1F7", "iran", 5),
]


def prefill(apps, schema_editor):
    WL = apps.get_model("panel", "WireguardLocation")
    for code, fa, en, flag, slug, order in LOCATIONS:
        WL.objects.get_or_create(code=code, defaults={"name_fa": fa, "name_en": en, "flag": flag, "slug": slug,
                                                       "sort_order": order})


class Migration(migrations.Migration):

    dependencies = [
        ('panel', '0007_backfill_service_plan'),
    ]

    operations = [
        migrations.CreateModel(
            name='WireguardLocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(help_text="the host remark's code, e.g. Ita, de, IR (case-insensitive)", max_length=40, unique=True)),
                ('name_fa', models.CharField(max_length=60)),
                ('name_en', models.CharField(max_length=60)),
                ('flag', models.CharField(blank=True, default='', max_length=16)),
                ('slug', models.CharField(blank=True, default='', help_text='file name part, e.g. germany', max_length=24)),
                ('sort_order', models.IntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'wireguard_location',
                'ordering': ('sort_order', 'name_en'),
            },
        ),
        migrations.AddField(
            model_name='service',
            name='wireguard',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(prefill, migrations.RunPython.noop),
    ]
