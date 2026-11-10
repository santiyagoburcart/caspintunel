# v1.53 (multi-tenant Phases 10 + 12): store exports (TENANT) + the monthly store fee (PLATFORM) — new tables only

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agency', '0014_invoice_kind_store_fee'),
        ('tenancy', '0008_tenant_permission_ceiling'),
    ]

    operations = [
        migrations.CreateModel(
            name='TenantExport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('requested_by', models.CharField(blank=True, default='', max_length=150)),
                ('by_platform', models.BooleanField(default=False, help_text='asked for by our staff on «فروشگاه»')),
                ('state', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('ready', 'Ready'), ('failed', 'Failed'), ('expired', 'Expired')], db_index=True, default='queued', max_length=8)),
                ('progress', models.PositiveSmallIntegerField(default=0)),
                ('step', models.CharField(blank=True, default='', max_length=40)),
                ('file', models.CharField(blank=True, default='', max_length=255)),
                ('size', models.BigIntegerField(default=0)),
                ('counts', models.JSONField(blank=True, default=dict)),
                ('error', models.CharField(blank=True, default='', max_length=500)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('link_hash', models.CharField(blank=True, db_index=True, default='', max_length=64)),
                ('link_scope', models.CharField(blank=True, default='', max_length=8)),
                ('link_expires_at', models.DateTimeField(blank=True, null=True)),
                ('downloads', models.PositiveIntegerField(default=0)),
                ('last_download_at', models.DateTimeField(blank=True, null=True)),
                ('tenant', models.ForeignKey(blank=True, editable=False, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='tenancy.tenant')),
            ],
            options={
                'db_table': 'tenant_export',
                'ordering': ('-created_at', '-id'),
            },
        ),
        migrations.CreateModel(
            name='TenantFee',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('enabled', models.BooleanField(default=False)),
                ('amount', models.DecimalField(decimal_places=0, default=0, help_text='tomans per month', max_digits=14)),
                ('next_due', models.DateField(blank=True, help_text='Tehran day the next invoice is issued', null=True)),
                ('remind_after_days', models.PositiveSmallIntegerField(default=3, help_text='0 = no reminder')),
                ('suspend_enabled', models.BooleanField(default=False)),
                ('suspend_after_days', models.PositiveSmallIntegerField(default=10)),
                ('updated_by', models.CharField(blank=True, default='', max_length=150)),
                ('tenant', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='fee', to='tenancy.tenant')),
            ],
            options={
                'db_table': 'tenant_fee',
            },
        ),
        migrations.CreateModel(
            name='TenantFeeInvoice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period', models.CharField(help_text='Jalali year-month, e.g. 1405-09', max_length=7)),
                ('due_date', models.DateField()),
                ('amount', models.DecimalField(decimal_places=0, max_digits=14)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reminded_at', models.DateTimeField(blank=True, null=True)),
                ('suspended_at', models.DateTimeField(blank=True, null=True)),
                ('resumed_at', models.DateTimeField(blank=True, null=True)),
                ('invoice', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='agency.agencyinvoice')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fee_invoices', to='tenancy.tenant')),
            ],
            options={
                'db_table': 'tenant_fee_invoice',
                'ordering': ('-due_date', '-id'),
                'constraints': [models.UniqueConstraint(fields=('tenant', 'period'), name='tenant_fee_invoice_once_per_month')],
            },
        ),
    ]
