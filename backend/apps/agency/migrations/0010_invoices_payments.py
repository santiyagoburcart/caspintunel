import django.db.models.deletion
from django.db import migrations, models

# copied at the time of writing (migrations must not import live code)
GM_INVOICES = ("agency.gm.invoices", "Group manager: view and pay the group's invoices",
               "مدیر گروه: دیدن و پرداخت فاکتورهای گروه")
STAFF_PAY = ("agency.payments", "Agency panel: review / approve agency payments", "نمایندگی: بررسی و تأیید واریزهای نمایندگان")


def grant(apps, schema_editor):
    """v1.34: the new permissions exist with their Persian names; every group-manager role
    gets "view / pay group invoices" once (the operator narrows it later on the Roles page)."""
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    gm, _ = Permission.objects.update_or_create(code=GM_INVOICES[0], defaults={"name": GM_INVOICES[1], "name_fa": GM_INVOICES[2]})
    Permission.objects.update_or_create(code=STAFF_PAY[0], defaults={"name": STAFF_PAY[1], "name_fa": STAFF_PAY[2]})
    for role in Role.objects.filter(permissions__code="agency.group_manager").distinct():
        role.permissions.add(gm)


class Migration(migrations.Migration):

    dependencies = [
        ("agency", "0009_gm_permissions"),
        ("accounts", "0015_notify_prefs"),
        ("payments_sms", "0015_blu_poll_liveness"),
    ]

    operations = [
        migrations.AlterField(
            model_name="volumerequest", name="kind",
            field=models.CharField(choices=[("create", "New admin"), ("add", "Added volume"), ("request", "Admin request")],
                                   max_length=8),
        ),
        migrations.AddField(model_name="volumerequest", name="requested_by",
                            field=models.CharField(blank=True, db_default="", default="", max_length=255)),
        migrations.AddField(model_name="volumerequest", name="note",
                            field=models.CharField(blank=True, db_default="", default="", max_length=255)),
        migrations.CreateModel(
            name="AgencyInvoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("admin_username", models.CharField(db_index=True, max_length=255)),
                ("group_name", models.CharField(blank=True, default="", max_length=150)),
                ("kind", models.CharField(choices=[("quota_charge", "Volume (staff)"), ("manual_charge", "Manual charge"),
                                                   ("request", "Volume request / group manager"),
                                                   ("settlement", "Previous balance")], max_length=16)),
                ("gb", models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True)),
                ("price_per_gb", models.DecimalField(blank=True, decimal_places=0, max_digits=12, null=True)),
                ("amount", models.DecimalField(decimal_places=0, max_digits=14)),
                ("status", models.CharField(choices=[("unpaid", "Unpaid"), ("pending", "Pending review"), ("paid", "Paid"),
                                                     ("voided", "Voided")], db_index=True, default="unpaid", max_length=8)),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("created_by", models.CharField(blank=True, default="", max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("voided_at", models.DateTimeField(blank=True, null=True)),
                ("void_reason", models.CharField(blank=True, default="", max_length=255)),
                ("group", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                            related_name="+", to="agency.admingroup")),
                ("ledger_entry", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                   related_name="invoices", to="agency.ledgerentry")),
                ("volume_request", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                     related_name="invoices", to="agency.volumerequest")),
            ],
            options={"db_table": "agency_invoice", "ordering": ("-created_at", "-id")},
        ),
        migrations.CreateModel(
            name="AgencyPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("payer_kind", models.CharField(choices=[("admin", "Agency admin"), ("manager", "Group manager")], max_length=8)),
                ("payer_username", models.CharField(db_index=True, max_length=255)),
                ("amount", models.DecimalField(decimal_places=0, help_text="the invoices' total", max_digits=14)),
                ("amount_unique", models.DecimalField(decimal_places=0, max_digits=14)),
                ("amount_unique_lock", models.DecimalField(blank=True, decimal_places=0, editable=False, max_digits=14,
                                                           null=True, unique=True)),
                ("unique_expire_at", models.DateTimeField()),
                ("status", models.CharField(choices=[("pending_payment", "Waiting for the transfer"),
                                                     ("pending_review", "Waiting for review"), ("approved", "Approved"),
                                                     ("rejected", "Rejected"), ("expired", "Expired"),
                                                     ("cancelled", "Cancelled")], db_index=True, default="pending_payment",
                                            max_length=16)),
                ("receipt_image", models.ImageField(blank=True, null=True, upload_to="receipts/agency/%Y/%m/")),
                ("receipt_sha256", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("receipt_ref", models.CharField(blank=True, db_index=True, default="", max_length=40)),
                ("receipt_uploaded_at", models.DateTimeField(blank=True, null=True)),
                ("method", models.CharField(blank=True, default="", max_length=12)),
                ("mismatch_kind", models.CharField(blank=True, default="", max_length=4)),
                ("mismatch_amount", models.DecimalField(blank=True, decimal_places=0, max_digits=14, null=True)),
                ("paid_amount", models.DecimalField(blank=True, decimal_places=0, max_digits=14, null=True)),
                ("auto_rule", models.CharField(blank=True, default="", max_length=16)),
                ("auto_reason", models.JSONField(blank=True, default=dict, null=True)),
                ("shortfall", models.DecimalField(blank=True, decimal_places=0, max_digits=14, null=True)),
                ("confirmed_by", models.CharField(blank=True, default="", max_length=8)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("reject_reason", models.CharField(blank=True, default="", max_length=255)),
                ("pending_alerted_at", models.DateTimeField(blank=True, null=True)),
                ("pending_resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("bank_card", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                related_name="+", to="payments_sms.bankcard")),
                ("blu_transaction", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                      related_name="agency_payments", to="payments_sms.blutransaction")),
                ("confirmed_by_staff", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                         related_name="+", to="accounts.staff")),
                ("manager", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                              related_name="payments", to="agency.groupmanager")),
                ("sms_message", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                  related_name="agency_payments", to="payments_sms.smsmessage")),
            ],
            options={"db_table": "agency_payment", "ordering": ("-created_at", "-id")},
        ),
        migrations.CreateModel(
            name="AgencyPaymentItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=0, max_digits=14)),
                ("invoice", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payment_items",
                                              to="agency.agencyinvoice")),
                ("payment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items",
                                              to="agency.agencypayment")),
            ],
            options={"db_table": "agency_payment_item", "unique_together": {("payment", "invoice")}},
        ),
        migrations.CreateModel(
            name="AgencyNotice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("admin_username", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("kind", models.CharField(blank=True, default="", max_length=24)),
                ("title", models.CharField(max_length=200)),
                ("title_en", models.CharField(blank=True, default="", max_length=200)),
                ("body", models.TextField(blank=True, default="")),
                ("body_en", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("manager", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                              related_name="notices", to="agency.groupmanager")),
            ],
            options={"db_table": "agency_notice", "ordering": ("-created_at", "-id")},
        ),
        migrations.RunPython(grant, migrations.RunPython.noop),
    ]
