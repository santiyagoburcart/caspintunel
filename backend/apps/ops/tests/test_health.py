import pytest
import responses
from django.core.cache import cache

from apps.ops.health import bot_heartbeat, run_health_checks
from apps.ops.models import HealthCheck, HealthTarget

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fast_worker_ping(monkeypatch):
    from config.celery import app

    monkeypatch.setattr(app.control, "ping", lambda timeout=1: [{"celery@test": {"ok": "pong"}}])


@responses.activate
def test_run_health_checks_writes_a_row_per_target(settings):
    settings.HEALTHCHECK_SITE_URL = "http://web:8000/api/v1/health/"
    responses.add(responses.GET, settings.HEALTHCHECK_SITE_URL, json={"status": "ok"}, status=200)
    cache.clear()
    bot_heartbeat(HealthTarget.BOT_SALES)  # pretend the sales bot is alive

    results = run_health_checks()
    assert {r["target"] for r in results} == set(HealthTarget.values)
    assert HealthCheck.objects.count() == len(HealthTarget.values)

    by_target = {r["target"]: r for r in results}
    assert by_target[HealthTarget.MYSQL]["is_up"] is True
    assert by_target[HealthTarget.REDIS]["is_up"] is True
    assert by_target[HealthTarget.SITE]["is_up"] is True
    assert by_target[HealthTarget.CELERY_WORKER]["is_up"] is True
    assert by_target[HealthTarget.BOT_SALES]["is_up"] is True
    assert by_target[HealthTarget.BOT_BACKUP]["is_up"] is False   # no heartbeat
    assert by_target[HealthTarget.MAIL]["is_up"] is False          # SMTP not configured
    assert by_target[HealthTarget.PANEL]["is_up"] is False         # no active panel


@responses.activate
def test_site_down_is_recorded(settings):
    settings.HEALTHCHECK_SITE_URL = "http://web:8000/api/v1/health/"
    responses.add(responses.GET, settings.HEALTHCHECK_SITE_URL, status=503)
    run_health_checks()
    assert HealthCheck.objects.filter(target=HealthTarget.SITE, is_up=False).exists()
