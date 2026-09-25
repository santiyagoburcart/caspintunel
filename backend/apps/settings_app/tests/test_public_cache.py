"""Public read endpoints: 60s server cache, invalidated on admin edits, own
throttle scope; client IP for throttling can't be spoofed via X-Forwarded-For."""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.settings import api_settings
from rest_framework.test import APIClient

from apps.plans.models import Plan
from apps.settings_app.models import Page, SiteConfig

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.parametrize("url", ["/api/v1/config/", "/api/v1/theme/", "/api/v1/pages/", "/api/v1/plans/"])
def test_second_hit_is_served_from_cache(client, url):
    from django.core.management import call_command

    call_command("seed")
    Plan.objects.create(name_fa="پلن", name_en="Plan", data_limit=1, duration_days=30, price=1000)
    first = client.get(url)
    assert first.status_code == 200
    with CaptureQueriesContext(connection) as q:
        second = client.get(url)
    assert second.status_code == 200 and second.json() == first.json()
    assert len(q.captured_queries) == 0, [x["sql"] for x in q.captured_queries]


def test_admin_edit_shows_up_immediately(client):
    cfg = SiteConfig.load()
    cfg.site_name_en = "Before"
    cfg.save()
    assert client.get("/api/v1/config/").json()["site_name_en"] == "Before"
    cfg.site_name_en = "After"
    cfg.save()
    assert client.get("/api/v1/config/").json()["site_name_en"] == "After"

    page = Page.objects.create(slug="x1", title_fa="a", title_en="a", body_fa="b", body_en="b", is_active=True)
    assert any(p["slug"] == "x1" for p in client.get("/api/v1/pages/").json()["results"])
    page.delete()
    assert not any(p["slug"] == "x1" for p in client.get("/api/v1/pages/").json()["results"])

    plan = Plan.objects.create(name_fa="پ", name_en="P", data_limit=1, duration_days=30, price=1000)
    assert [p["id"] for p in client.get("/api/v1/plans/").json()["results"]] == [plan.id]
    plan.is_active = False
    plan.save()
    assert client.get("/api/v1/plans/").json()["results"] == []


def test_missing_page_is_not_cached_as_hit(client):
    assert client.get("/api/v1/pages/nope/").status_code == 404
    Page.objects.create(slug="nope", title_fa="a", title_en="a", body_fa="b", body_en="b", is_active=True)
    assert client.get("/api/v1/pages/nope/").status_code == 200


def test_public_reads_use_their_own_scope():
    from apps.plans.views import PlanViewSet
    from apps.settings_app.views import PublicSiteConfigView

    from config.settings import base

    assert PublicSiteConfigView.throttle_scope == "public_read"
    rates = base.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    assert rates["public_read"] == "600/min" and rates["anon"] == "180/min"
    assert rates["auth"] == "10/min" and rates["receipt"] == "20/hour"  # strict ones unchanged

    view = PlanViewSet()
    view.action = "list"
    view.request = type("R", (), {"user": type("U", (), {"is_authenticated": False, "is_staff": False})()})()
    assert [type(t).__name__ for t in view.get_throttles()] == ["ScopedRateThrottle"]
    assert view.throttle_scope == "public_read"


def test_spoofed_forwarded_for_does_not_pick_a_new_bucket():
    """nginx sends exactly one trusted address; with NUM_PROXIES=1 DRF keys on
    it, so junk prepended by the client is ignored."""
    from rest_framework.test import APIRequestFactory
    from rest_framework.throttling import AnonRateThrottle
    from rest_framework.views import APIView

    assert api_settings.NUM_PROXIES == 1
    rf = APIRequestFactory()
    t = AnonRateThrottle()
    idents = {
        t.get_ident(APIView().initialize_request(rf.get("/", HTTP_X_FORWARDED_FOR=f"10.0.0.{i}, 203.0.113.7", REMOTE_ADDR="172.18.0.5")))
        for i in range(5)
    }
    assert idents == {"203.0.113.7"}
