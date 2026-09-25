"""Admin payments queue live feed: events fire on every queue change and only
staff with payment.view can subscribe."""
from decimal import Decimal

import pytest
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Permission, Role, Staff, User
from apps.adminpanel.tokens import issue_tokens
from apps.notifications import live
from apps.orders.services import create_order
from apps.payments_sms.services import approve_payment, reject_payment, submit_receipt
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db(transaction=True)

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f"
       b"\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


@pytest.fixture
def events(monkeypatch):
    sent = []
    monkeypatch.setattr(live, "_send", lambda event, data: sent.append((event, data)))
    return sent


@pytest.fixture
def order():
    user = User.objects.create_user("cust", "Str0ngPass!")
    plan = Plan.objects.create(name_fa="p", price=Decimal("50000"), data_limit=1, duration_days=30)
    return create_order(user=user, plan_id=plan.id, requested_account_name="acc")


def test_queue_changes_push_events(events, order, monkeypatch):
    from apps.orders import tasks

    monkeypatch.setattr(tasks.fulfill_order, "delay", lambda *a, **k: None)  # no panel in tests
    assert ("order_created", {"order_id": order.id}) in events

    pay = submit_receipt(order=order, image=SimpleUploadedFile("r.png", PNG, "image/png"), user=order.user)
    assert events[-1][0] == "receipt_uploaded" and events[-1][1]["payment_id"] == pay.id

    reject_payment(pay.id, reason="x")
    assert events[-1][0] == "payment_rejected"

    pay = submit_receipt(order=order, image=SimpleUploadedFile("r.png", PNG, "image/png"), user=order.user)
    approve_payment(pay.id)
    assert events[-1][0] == "payment_approved"


def test_reused_order_does_not_push_again(events, order):
    n = len(events)
    again = create_order(user=order.user, plan_id=order.plan_id, requested_account_name="acc")
    assert again.id == order.id and len(events) == n


def _staff(perm_codes):
    role = Role.objects.create(name="r-" + "-".join(perm_codes or ["none"]))
    role.permissions.set([Permission.objects.get_or_create(code=c, defaults={"name": c})[0] for c in perm_codes])
    s = Staff(username="s-" + str(Role.objects.count()), role=role)
    s.set_password("Str0ngPass!")
    s.save()
    return s


async def _connect(token):
    from config.asgi import application

    comm = WebsocketCommunicator(application, f"/ws/admin/payments/?token={token}")
    connected, _ = await comm.connect()
    return comm, connected


def test_ws_requires_payment_view(settings):
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    ok_token = issue_tokens(_staff(["payment.view"]))["access"]
    no_token = issue_tokens(_staff(["users.view"]))["access"]

    async def run():
        comm, connected = await _connect(no_token)
        assert not connected
        comm, connected = await _connect("garbage")
        assert not connected

        comm, connected = await _connect(ok_token)
        assert connected
        from channels.layers import get_channel_layer

        await get_channel_layer().group_send(
            live.STAFF_PAYMENTS_GROUP,
            {"type": "payments.event", "payload": {"event": "receipt_uploaded", "pending_count": 1}},
        )
        msg = await comm.receive_json_from(timeout=2)
        assert msg == {"event": "receipt_uploaded", "pending_count": 1}
        await comm.disconnect()

    async_to_sync(run)()
