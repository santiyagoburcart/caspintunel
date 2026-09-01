import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_api_root_is_public():
    resp = APIClient().get("/api/v1/")
    assert resp.status_code == 200
    assert resp.data["api"] == "v1"
    assert "version" in resp.data


def test_health_reports_checks():
    resp = APIClient().get("/api/v1/health/")
    assert resp.status_code in (200, 503)
    assert "database" in resp.data["checks"]
    assert "redis" in resp.data["checks"]


def test_openapi_schema_available():
    resp = APIClient().get("/api/schema/")
    assert resp.status_code == 200
