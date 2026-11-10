"""Multi-tenant Phase 7 Release A (v1.50): store-owned features never leak to our staff / channels / brand.

* Account emails (verify / reset) link to the customer's own store and carry its name; mail sent for a store goes out under
  the store's name (our address).
* `notify_user` always delivers in the customer's store (its bot), whatever context calls it.
* Ticket staff, the ticket staff picker and the CRM staff list are the current store's staff only.
* Periodic jobs on customer data run for every store (CRM, retention / expiry warnings, ticket auto-close, channel counts,
  the pending-payment alert).
* A store's admin links point at its own panel.
"""
import pytest
from django.core import mail
from django.core.mail import EmailMessage

from apps.accounts.models import Staff, User
from apps.tenancy import context
from apps.tenancy.models import Tenant, TenantBot, TenantDomain

pytestmark = pytest.mark.django_db
HOST = "shop-p7.example"
STORE_TOKEN = "555000777:" + "S" * 35


@pytest.fixture
def store(_default_tenant):
    t = Tenant.objects.create(slug="s7", name="Store Seven", status="active", reseller_username="p7admin")
    TenantDomain.objects.create(tenant=t, host=HOST, state="active")
    from apps.settings_app.models import TenantBranding

    with context.tenant_context(t.pk):
        TenantBranding.objects.create(site_name_fa="فروشگاه هفت", site_name_en="Store Seven")
    return t


def _in(t):
    return context.tenant_context(t.pk)


# ------------------------------------------------------------------ email
def test_account_emails_link_to_the_store_and_carry_its_name(store, monkeypatch):
    from apps.accounts import emails

    monkeypatch.setattr(emails, "smtp_configured", lambda: True)
    with _in(store):
        u = User.objects.create_user("p7cust", "Str0ngPass!", email="c@example.org")
        assert emails.send_password_reset_email(u, "TOKEN1") and emails.send_verification_email(u, "TOKEN2")
    reset, verify = mail.outbox[-2:]
    assert f"https://{HOST}/reset-password?token=TOKEN1" in reset.body and reset.subject.startswith("Store Seven")
    assert f"https://{HOST}/verify-email?token=TOKEN2" in verify.body and "caspin" not in (reset.body + verify.body).lower()


def test_mail_for_a_store_goes_out_under_its_name_ours_unchanged(store, settings):
    from apps.common.mail import _store_sender

    settings.DEFAULT_FROM_EMAIL = "noreply@caspin.example"
    ours = [EmailMessage("s", "b", "noreply@caspin.example", ["a@b.c"])]
    _store_sender(ours)
    assert ours[0].from_email == "noreply@caspin.example"
    with _in(store):
        theirs = [EmailMessage("s", "b", "noreply@caspin.example", ["a@b.c"])]
        _store_sender(theirs)
    assert theirs[0].from_email.endswith("<noreply@caspin.example>") and "Caspin" not in theirs[0].from_email


# ------------------------------------------------------------------ notifications
def test_notify_user_uses_the_customers_store_whatever_the_caller(store, monkeypatch):
    from apps.notifications.dispatch import notify_user
    from apps.telegram.client import TelegramClient
    from apps.telegram.models import BotType, TelegramConfig

    TelegramConfig.objects.create(bot_type=BotType.SALES, token="111222333:" + "B" * 35, is_active=True)
    TenantBot.objects.create(tenant=store, token=STORE_TOKEN, bot_id=555000777, username="seven_bot")
    sent = []
    monkeypatch.setattr(TelegramClient, "_call", lambda self, m, **p: sent.append((self._base, m)) or {"message_id": 1})
    with _in(store):
        u = User.objects.create_user("p7tg", "Str0ngPass!", telegram_id=9077)
    notify_user(u, title="t", body="b", via_bot=True)                # called from OUR context
    assert sent and all(base.endswith(STORE_TOKEN) for base, _ in sent)


# ------------------------------------------------------------------ staff of the store only
def test_ticket_and_crm_staff_are_the_current_stores_only(store):
    from apps.tickets.rules import ticket_staff

    ours = Staff.objects.create(username="our-t7", is_superadmin=True)
    theirs = Staff.objects.create(username="their-t7", is_superadmin=True, tenant=store)
    assert ours in ticket_staff(1) and theirs not in ticket_staff(1)
    with _in(store):
        assert ticket_staff(1) == [theirs]


def test_store_admin_links_point_at_the_store_panel(store):
    from apps.common.links import admin_link

    assert HOST not in admin_link("payments")
    with _in(store):
        assert admin_link("payments").startswith(f"https://{HOST}/") and admin_link("payments").endswith("/payments")


# ------------------------------------------------------------------ periodic jobs run for every store
@pytest.mark.parametrize("task, target", [
    ("apps.payments_sms.tasks.pending_payment_alert_task", "apps.payments_sms.pending_alert.run"),
    ("apps.tickets.tasks.auto_close_tickets_task", "apps.tickets.services.auto_close_stale"),
    ("apps.crm.tasks.crm_detect_task", "apps.crm.services.detect_inactivity"),
    ("apps.ops.tasks.service_alerts_task", "apps.crm.retention.run_warnings"),
    ("apps.telegram.tasks.sync_required_channels_task", "apps.telegram.config.sales_client"),
])
def test_customer_jobs_run_once_per_store(store, monkeypatch, task, target):
    import importlib

    seen = []

    def spy(*a, **k):
        seen.append(context.store_id())
        return {} if not target.endswith("auto_close_stale") else 0

    monkeypatch.setattr(target, spy)
    if task.endswith("crm_detect_task"):
        monkeypatch.setattr("apps.crm.retention.run_winback", lambda: 0)
        monkeypatch.setattr("apps.crm.services.refresh_all_stages", lambda: 0)
    if task.endswith("service_alerts_task"):
        monkeypatch.setattr("apps.crm.retention.setting", lambda key: True)
    if task.endswith("sync_required_channels_task"):
        monkeypatch.setattr("apps.telegram.config.sales_client", lambda: seen.append(context.store_id()))
    mod, fn = task.rsplit(".", 1)
    getattr(importlib.import_module(mod), fn)()
    assert None in seen and store.pk in seen                       # ours AND the store, each in its own context
