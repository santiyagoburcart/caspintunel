"""Only branding media (logo / favicon) is public; receipts and operator apps
stay private even on the DEBUG=False dev-compose server."""
import pytest
from django.test import Client


@pytest.fixture
def media(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    (tmp_path / "branding").mkdir()
    (tmp_path / "branding" / "logo.png").write_bytes(b"\x89PNGlogo")
    (tmp_path / "receipts").mkdir()
    (tmp_path / "receipts" / "r.jpg").write_bytes(b"secret")
    (tmp_path / "apps").mkdir()
    (tmp_path / "apps" / "ios.shortcut").write_bytes(b"app")
    return tmp_path


def test_branding_is_served(media):
    r = Client().get("/media/branding/logo.png")
    assert r.status_code == 200 and b"".join(r.streaming_content) == b"\x89PNGlogo"


@pytest.mark.parametrize("path", [
    "/media/receipts/r.jpg", "/media/apps/ios.shortcut",
    "/media/branding/../receipts/r.jpg", "/media/branding/..%2Freceipts%2Fr.jpg",
])
def test_private_media_is_not_served(media, path):
    assert Client().get(path).status_code == 404
