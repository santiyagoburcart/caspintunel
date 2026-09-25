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


@pytest.mark.django_db
def test_latin_digits_migration_rewrites_only_digits():
    import importlib

    from django.apps import apps as real_apps

    from apps.plans.models import Plan
    from apps.settings_app.models import Page

    mig = importlib.import_module("apps.settings_app.migrations.0011_latin_digits_in_content")
    plan = Plan.objects.create(name_fa="بسته ۵۰ گیگ ٪۱۰", data_limit=1, duration_days=30, price=1000)
    page = Page.objects.create(slug="d1", title_fa="قوانین", body_fa="۱. حریم خصوصی ۲۴ ساعته")
    mig.forwards(real_apps, None)
    plan.refresh_from_db(); page.refresh_from_db()
    assert plan.name_fa == "بسته 50 گیگ %10"
    assert page.body_fa == "1. حریم خصوصی 24 ساعته" and page.title_fa == "قوانین"
