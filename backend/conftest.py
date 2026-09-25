"""Test-suite shims.

Multi-panel (MP-Phase 1) made ``Plan.panel`` a required FK. Dozens of existing
fixtures build a ``Plan`` without one and don't care which panel it is on. Rather
than thread a panel through every fixture, fill it in at save time during tests:
if a Plan is saved without a panel, attach it to the first Panel (creating a
throw-away one on the common test base URL if none exists yet).

Tests that DO care about the panel pass ``panel=`` explicitly and are untouched.
"""
import pytest


@pytest.fixture(autouse=True)
def _plan_gets_a_panel(db):
    from django.db.models.signals import pre_save

    from apps.panel.models import Panel
    from apps.plans.models import Plan

    def _fill(sender, instance, **kwargs):
        if instance.panel_id is None:
            panel = Panel.objects.order_by("id").first()
            if panel is None:
                panel = Panel.objects.create(
                    name="Test Panel", base_url="https://panel.test",
                    admin_username="a", admin_password_enc="p",
                )
            instance.panel = panel

    pre_save.connect(_fill, sender=Plan, dispatch_uid="test_plan_default_panel")
    yield
    pre_save.disconnect(sender=Plan, dispatch_uid="test_plan_default_panel")


@pytest.fixture(autouse=True)
def _fresh_cache():
    """Public endpoints are cached (apps.common.public_cache) and DB rollbacks
    between tests don't bump its version — start every test with an empty cache."""
    from django.conf import settings
    from django.core.cache import cache

    # only ever wipe the test suite's own in-process cache — never a shared
    # Redis (e.g. if the suite is started with the wrong settings module)
    if settings.CACHES["default"]["BACKEND"].endswith("LocMemCache"):
        cache.clear()
    yield
