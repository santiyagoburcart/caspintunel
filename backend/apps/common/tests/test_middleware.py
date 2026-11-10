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


def test_sync_is_cached_per_process(settings, django_assert_num_queries):
    mw = DynamicAllowedHostsMiddleware(lambda r: r)
    mw._sync()                                              # first request of this process: reads the DB
    with django_assert_num_queries(0):
        mw._sync()                                          # same token, < 60 s: nothing read again


def test_every_worker_learns_a_new_store_domain(settings):
    """v1.53.1 (pilot rehearsal): the marker is shared in Redis but ALLOWED_HOSTS lives in each gunicorn worker — a worker
    that did not do the refresh itself must still pick the new store domain up (it used to answer 400 DisallowedHost)."""
    from apps.tenancy.models import Tenant, TenantDomain

    settings.ALLOWED_HOSTS = ["localhost"]
    cfg = SiteConfig.load()
    cfg.site_domain = "ours.example"
    cfg.save()
    cache.delete("dynamic_allowed_hosts")
    worker_a = DynamicAllowedHostsMiddleware(lambda r: r)
    worker_b = DynamicAllowedHostsMiddleware(lambda r: r)
    worker_a._sync()
    worker_b._sync()
    t = Tenant.objects.create(slug="mw", name="MW", status="active", reseller_username="mw")
    TenantDomain.objects.create(tenant=t, host="shop-mw.example", state="active")
    cache.delete("dynamic_allowed_hosts")                   # what tenancy.domains does when a domain goes active
    worker_a._sync()                                        # A refreshes first and sets the new token …
    settings.ALLOWED_HOSTS = ["localhost", "ours.example"]  # … B's process still has its old list
    worker_b._sync()
    assert "shop-mw.example" in settings.ALLOWED_HOSTS and "www.shop-mw.example" in settings.ALLOWED_HOSTS
