"""Repair `deleted_user_archive` on databases where an earlier, unmerged draft
of 0006_user_soft_delete was applied under the same migration name (it
created `order_count` + `service_count` and 64-char *_by_label columns).

Idempotent: introspects the live table and only fixes what differs from the
0006 that is in the repo, so on a correctly built database it is a no-op.
"""
from django.db import migrations

TABLE = "deleted_user_archive"


def repair(apps, schema_editor):
    conn = schema_editor.connection
    with conn.cursor() as cur:
        desc = {c.name: c for c in conn.introspection.get_table_description(cur, TABLE)}
    qn = schema_editor.quote_name
    if "order_count" in desc and "orders_count" not in desc:
        schema_editor.execute(f"ALTER TABLE {qn(TABLE)} RENAME COLUMN {qn('order_count')} TO {qn('orders_count')}")
    if "service_count" in desc:
        schema_editor.execute(f"ALTER TABLE {qn(TABLE)} DROP COLUMN {qn('service_count')}")
    if conn.vendor == "mysql":
        for col in ("deleted_by_label", "restored_by_label"):
            if col in desc and (desc[col].internal_size or 0) < 150:
                schema_editor.execute(f"ALTER TABLE {qn(TABLE)} MODIFY {qn(col)} varchar(150) NOT NULL")


class Migration(migrations.Migration):
    atomic = False   # MySQL: DDL cannot run inside a transaction

    dependencies = [("accounts", "0007_user_terms_accepted_at")]

    operations = [migrations.RunPython(repair, migrations.RunPython.noop)]
