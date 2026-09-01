import pytest
from django.conf import settings
from django.core.cache import cache

from apps.common.middleware import DynamicAllowedHostsMiddleware
from apps.settings_app.models import SiteConfig

pytestmark = pytest.mark.django_db


def test_db_domain_is_added_to_allowed_hosts(settings):
    settings.ALLOWED_HOSTS = ["localhost"]
    settings.CSRF_TRUSTED_ORIGINS = []
    cache.delete("dynamic_allowed_hosts")

    cfg = SiteConfig.load()
    cfg.site_domain = "newdomain.example"
    cfg.save()

    mw = DynamicAllowedHostsMiddleware(lambda r: r)
    mw._sync()

    assert "newdomain.example" in settings.ALLOWED_HOSTS
    assert "www.newdomain.example" in settings.ALLOWED_HOSTS
    assert "localhost" in settings.ALLOWED_HOSTS            # baseline kept
    assert "https://newdomain.example" in settings.CSRF_TRUSTED_ORIGINS


def test_sync_is_cached(settings):
    cache.set("dynamic_allowed_hosts", "x", 60)
    before = list(settings.ALLOWED_HOSTS)
    DynamicAllowedHostsMiddleware(lambda r: r)._sync()
    assert settings.ALLOWED_HOSTS == before
