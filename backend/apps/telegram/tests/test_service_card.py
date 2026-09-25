"""Bot service card: QR photo + subscription link as tap-to-copy <code>."""
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.orders.models import Order, OrderStatus
from apps.orders.tasks import _notify_delivered
from apps.panel.models import Panel, Service
from apps.plans.models import Plan
from apps.telegram.shop import qr_png, service_caption

pytestmark = pytest.mark.django_db


@pytest.fixture
def svc():
    panel = Panel.objects.create(name="P", base_url="https://p.test", admin_username="a", admin_password_enc="p")
    user = User.objects.create_user("tgu", "Str0ngPass!", telegram_id=4242)
    return Service.objects.create(user=user, panel=panel, panel_username="ali_1",
                                  subscription_url="https://sub.test/sub/abc?x=1&y=2")


def test_caption_has_monospace_escaped_link(svc):
    cap = service_caption(svc, title="ready", summary="<b>ali_1</b>")
    assert "<code>https://sub.test/sub/abc?x=1&amp;y=2</code>" in cap
    assert cap.startswith("<b>ready</b>") and len(cap) <= 1024
    assert qr_png(svc.subscription_url).startswith(b"\x89PNG")


def test_delivery_sends_qr_photo_to_bot(svc):
    plan = Plan.objects.create(panel=svc.panel, name_fa="p", price=Decimal("1"), duration_days=30)
    order = Order(user=svc.user, plan=plan, service=svc, amount=1, amount_unique=1,
                  unique_expire_at=timezone.now(), status=OrderStatus.COMPLETED)
    order.sync_unique_lock()
    order.save()
    client = mock.Mock()
    with mock.patch("apps.telegram.config.sales_client", return_value=client):
        _notify_delivered(order)
    client.send_photo.assert_called_once()
    args, kw = client.send_photo.call_args
    assert args[0] == 4242 and args[1].startswith(b"\x89PNG")
    assert kw["parse_mode"] == "HTML" and "<code>https://sub.test/sub/abc?x=1&amp;y=2</code>" in kw["caption"]
    client.send_message.assert_not_called()          # no duplicate plain-text bot message
