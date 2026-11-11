# v1.54: admins + group managers are archived, never deleted (agency/archive.py); first-seen users for «تاریخچه» — additive only

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agency', '0014_invoice_kind_store_fee'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupmanager',
            name='archived_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='paneladmin',
            name='archived_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='paneladmin',
            name='archived_by',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.AddField(
            model_name='paneladmin',
            name='archived_reason',
            field=models.CharField(blank=True, default='', max_length=16),
        ),
        migrations.CreateModel(
            name='AgencyUserSeen',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('admin_username', models.CharField(db_index=True, max_length=255)),
                ('user_username', models.CharField(max_length=255)),
                ('first_seen_at', models.DateTimeField(db_index=True)),
            ],
            options={
                'db_table': 'agency_user_seen',
                'constraints': [models.UniqueConstraint(fields=('admin_username', 'user_username'), name='agency_user_seen_once')],
            },
        ),
    ]
