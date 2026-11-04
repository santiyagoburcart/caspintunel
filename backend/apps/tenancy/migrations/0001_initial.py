import django.db.models.deletion
from django.db import migrations, models

import apps.tenancy.models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Tenant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("slug", models.SlugField(unique=True)),
                ("name", models.CharField(max_length=150)),
                ("reseller_username", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("active", "Active"), ("suspended", "Suspended"), ("closed", "Closed")], default="draft", max_length=10)),
                ("is_default", models.BooleanField(default=False)),
                ("export_allowed", models.BooleanField(default=False, help_text="the reseller may download a tenant export (set by us)")),
                ("limits", models.JSONField(blank=True, default=dict, help_text="orders/min, staff count, … (set by us)")),
            ],
            options={"db_table": "tenant", "ordering": ("-is_default", "name")},
        ),
        migrations.CreateModel(
            name="TenantDomain",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("host", models.CharField(help_text="lowercase, IDNA (punycode)", max_length=253, unique=True)),
                ("role", models.CharField(choices=[("site", "Site"), ("admin", "Admin"), ("both", "Site + admin")], default="both", max_length=5)),
                ("mode", models.CharField(choices=[("direct", "Direct (Finland IP)"), ("tunnel", "Iran tunnel"), ("cloudflare", "Reseller's Cloudflare proxy")], default="direct", max_length=10)),
                ("verify_token", models.CharField(default=apps.tenancy.models._verify_token, max_length=64)),
                ("state", models.CharField(choices=[("pending_dns", "Waiting for DNS"), ("verified", "Verified"), ("cert_pending", "Certificate pending"), ("active", "Active"), ("failed", "Failed"), ("removed", "Removed")], default="pending_dns", max_length=12)),
                ("cert_expires_at", models.DateTimeField(blank=True, null=True)),
                ("last_check_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, default="", max_length=500)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="domains", to="tenancy.tenant")),
            ],
            options={"db_table": "tenant_domain", "ordering": ("host",)},
        ),
    ]
