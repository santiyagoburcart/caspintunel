"""Every model change ships with its migration (a missing one would break update.sh)."""
from io import StringIO

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_no_missing_migrations():
    out = StringIO()
    try:
        call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
    except SystemExit as exc:                     # exit 1 = changes without a migration
        if exc.code:
            pytest.fail(f"missing migrations:\n{out.getvalue()}")
