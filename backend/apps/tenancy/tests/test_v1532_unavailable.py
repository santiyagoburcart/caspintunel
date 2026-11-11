"""v1.53.2 — a store that is not active shows its own «در دسترس نیست» page (503) instead of an empty site shell.

The host watcher parks its vhost (scripts/tenants_host.py, tested end to end in scripts/test-tenants.sh); here: the page
Django answers (store name + inlined logo, no data, never our brand, 404 for our / unknown hosts), the `parked` flag the
watcher reads, a status change rewriting the watcher's file at once, and the domain health check not alerting for a store
that is parked on purpose.
"""
import io
import json

import pytest
from django.core.files.base import ContentFile
from PIL import Image
from rest_framework.test import APIClient

from apps.settings_app.models import SiteConfig, TenantBranding
from apps.tenancy import context, domains, stores
from apps.tenancy.models import Tenant, TenantDomain

pytestmark = pytest.mark.django_db
HOST = "shop-park.example"
URL = "/api/v1/store-unavailable/"


@pytest.fixture
def store(_default_tenant, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    t = Tenant.objects.create(slug="park", name="Park Store", status="suspended", reseller_username="parkadmin")
    TenantDomain.objects.create(tenant=t, host=HOST, state="active", include_www=True, verified_at="2026-11-10T00:00:00Z")
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (20, 100, 186)).save(buf, "PNG")
    with context.tenant_context(t.pk):
        b = TenantBranding.objects.create(site_name_fa="فروشگاه <پارک>", site_name_en="Park <Shop>")
        b.logo.save("logo.png", ContentFile(buf.getvalue()), save=True)
    return t


def _get(host, method="get"):
    return getattr(APIClient(HTTP_HOST=host), method)(URL)


def test_a_suspended_store_shows_its_own_unavailable_page(store):
    cfg = SiteConfig.load()
    r = _get(HOST)
    assert r.status_code == 503 and r["Retry-After"] == "3600" and r["Cache-Control"] == "no-store"
    html = r.content.decode()
    assert "این فروشگاه در حال حاضر در دسترس نیست" in html and "This store is not available right now" in html
    assert "فروشگاه &lt;پارک&gt;" in html and "Park &lt;Shop&gt;" in html and "<پارک>" not in html     # escaped
    assert 'src="data:image/png;base64,' in html                       # the logo inlined (nothing else loads)
    assert "caspintunel" not in html.lower() and (not cfg.site_name_en or cfg.site_name_en not in html)
    assert 'name="robots" content="noindex"' in html and r["X-Robots-Tag"] == "noindex"
    assert _get(f"www.{HOST}").status_code == 503
    head = _get(HOST, "head")
    assert head.status_code == 503 and head.content == b""


def test_the_expected_503_is_not_logged_as_an_error(store):
    """v1.53.3: a parked store's page is expected — no django.request ERROR per visitor. (A handler on the logger
    itself: our LOGGING config does not let django.request reach the root logger, where caplog listens.)"""
    import logging

    seen = []

    class Keep(logging.Handler):
        def emit(self, record):
            seen.append(record)

    h, log = Keep(level=logging.WARNING), logging.getLogger("django.request")
    log.addHandler(h)
    try:
        assert _get(HOST).status_code == 503
    finally:
        log.removeHandler(h)
    assert not [r for r in seen if r.levelno >= logging.ERROR]         # without the fix: one ERROR per request


def test_without_a_logo_a_letter_is_shown_and_draft_stores_retry_sooner(store):
    Tenant.objects.filter(pk=store.pk).update(status="draft")
    with context.tenant_context(store.pk):
        TenantBranding.objects.update(logo="")
    r = _get(HOST)
    assert r.status_code == 503 and r["Retry-After"] == "60" and 'class="mark"' in r.content.decode()


def test_our_host_and_unknown_hosts_get_404(store):
    assert APIClient().get(URL).status_code == 404                     # our own site never shows it
    assert _get("nobody.example").status_code == 404


def test_the_watcher_parks_every_store_that_is_not_active(store):
    other = Tenant.objects.create(slug="live", name="Live", status="active", reseller_username="liveadmin")
    TenantDomain.objects.create(tenant=other, host="shop-live.example", state="active", verified_at="2026-11-10T00:00:00Z")
    parked = {h["host"]: h["parked"] for h in domains.desired()}
    assert parked == {HOST: True, "shop-live.example": False}


def test_a_status_change_rewrites_the_watcher_file_at_once(store, monkeypatch, tmp_path, django_capture_on_commit_callbacks):
    path = tmp_path / ".tenant-domains.json"
    monkeypatch.setattr(domains, "desired_file", lambda: path)
    with django_capture_on_commit_callbacks(execute=True):
        stores.update(store, {"status": "active"})
    assert json.loads(path.read_text())["hosts"][0]["parked"] is False
    with django_capture_on_commit_callbacks(execute=True):
        stores.update(store, {"status": "suspended"})
    assert json.loads(path.read_text())["hosts"][0]["parked"] is True


def test_health_does_not_call_the_api_of_a_parked_store(store, monkeypatch):
    from apps.settings_app import access

    calls = []

    def fake_probe(ip, host, path="/api/v1/health/"):
        calls.append(path)
        d = TenantDomain.objects.get(host=HOST)
        return {"ok": True, "data": d.verify_token, "status": 200} if path.startswith("/.well-known/") \
            else {"ok": False, "status": 503, "error": "503"}

    monkeypatch.setattr(access, "probe", fake_probe)
    d = TenantDomain.objects.select_related("tenant").get(host=HOST)
    h = domains.health(d)
    assert h["ok"] is True and calls == [f"{domains.PROBE_PATH}{d.verify_token}"]   # no /api/v1/health/ while parked
    Tenant.objects.filter(pk=store.pk).update(status="active")
    d = TenantDomain.objects.select_related("tenant").get(host=HOST)
    assert domains.health(d)["ok"] is False and calls[-1] == "/api/v1/health/"      # an active store is checked as before
