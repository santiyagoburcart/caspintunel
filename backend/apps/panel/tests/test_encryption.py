import pytest
from django.db import connection

from apps.panel.models import Panel

pytestmark = pytest.mark.django_db


def test_panel_password_encrypted_at_rest():
    p = Panel.objects.create(
        name="Pasargad",
        base_url="https://pas.hunaex.shop",
        admin_username="santiyago",
        admin_password_enc="super-secret-pw",
    )
    # plaintext in Python
    p.refresh_from_db()
    assert p.admin_password_enc == "super-secret-pw"

    # ciphertext in the actual column
    with connection.cursor() as cur:
        cur.execute("SELECT admin_password_enc FROM panel WHERE id = %s", [p.id])
        raw = cur.fetchone()[0]
    assert raw.startswith("enc:v1:")
    assert "super-secret-pw" not in raw
