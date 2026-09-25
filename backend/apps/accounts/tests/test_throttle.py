from unittest import mock

import pytest
from django.core.cache import cache
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.test import APIClient

from apps.accounts.views import RegisterView

pytestmark = pytest.mark.django_db


def test_auth_scope_is_rate_limited():
    """The `auth` throttle scope blocks a burst of requests."""
    cache.clear()
    client = APIClient()
    with mock.patch.object(RegisterView, "throttle_classes", [ScopedRateThrottle]), \
         mock.patch.object(ScopedRateThrottle, "THROTTLE_RATES", {"auth": "3/min"}):
        codes = [
            client.post(
                "/api/v1/auth/register/",
                {"username": f"user{i}", "password": "Str0ngPass!", "phone": f"0912000000{i}"},
                format="json",
            ).status_code
            for i in range(6)
        ]
    assert codes.count(429) >= 1, codes
    assert codes[0] == 201
