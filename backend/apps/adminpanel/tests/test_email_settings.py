"""Outgoing email from the admin panel: backend selection + fallback, write-only
encrypted password, test-email endpoint (mocked SMTP), permissions, audit."""
import smtplib
import socket

import pytest
from django.core import mail
from django.db import connection

from .conftest import make_staff
from apps.common import mail as m
from apps.common.models import AuditLog
from apps.settings_app.models import EmailSettings

pytestmark = pytest.mark.django_db

DYN = "apps.common.mail.DynamicEmailBackend"
URL = "/api/v1/admin/email/"


class FakeSMTP:
    """Stands in for smtplib.SMTP inside Django's SMTP backend."""
    calls: list = []
    fail_on: str = ""          # "connect" | "login" | "sender"
    exc: BaseException | None = None

    def __init__(self, host, port, **kw):
        FakeSMTP.calls.append(("connect", host, port))
        if FakeSMTP.fail_on == "connect":
            raise FakeSMTP.exc

    def ehlo(self, *a, **k): pass
    def starttls(self, *a, **k): FakeSMTP.calls.append(("starttls",))
    def login(self, u, p):
        FakeSMTP.calls.append(("login", u, p))
        if FakeSMTP.fail_on == "login":
            raise FakeSMTP.exc

    def sendmail(self, frm, to, msg):
        if FakeSMTP.fail_on == "sender":
            raise FakeSMTP.exc
        FakeSMTP.calls.append(("sendmail", frm, tuple(to)))
        return {}

    def quit(self): pass
    def close(self): pass


@pytest.fixture
def smtp(monkeypatch, settings):
    settings.EMAIL_BACKEND = DYN
    FakeSMTP.calls, FakeSMTP.fail_on, FakeSMTP.exc = [], "", None
    monkeypatch.setattr("django.core.mail.backends.smtp.smtplib.SMTP", FakeSMTP)
    m.bump_email_settings_version()
    return FakeSMTP


def relay(**kw):
    obj = EmailSettings.load()
    for k, v in {"enabled": True, "host": "smtp-relay.brevo.com", "port": 587, "security": "starttls",
                 "username": "me@x.test", "password": "s3cret-pass", "from_email": "noreply@aicaspin.ir",
                 "from_name": "Caspin Tunnel", **kw}.items():
        setattr(obj, k, v)
    obj.save()
    return obj


# ------------------------------------------------------------- selection
def test_production_settings_use_the_dynamic_backend():
    from config.settings import base

    assert base.EMAIL_BACKEND == DYN


def test_fallback_order(settings):
    settings.EMAIL_HOST, settings.EMAIL_PORT = "", 25
    m.bump_email_settings_version()
    assert m.resolve_mail_config().source == "none"

    settings.EMAIL_HOST = "mailserver"
    m.bump_email_settings_version()
    assert m.resolve_mail_config().source == "local"

    settings.EMAIL_HOST, settings.EMAIL_PORT = "smtp.env-provider.test", 587
    m.bump_email_settings_version()
    assert m.resolve_mail_config().source == "env"

    relay()  # enabled DB relay wins
    cfg = m.resolve_mail_config()
    assert (cfg.source, cfg.host, cfg.port, cfg.use_tls) == ("db", "smtp-relay.brevo.com", 587, True)
    assert cfg.from_email == "Caspin Tunnel <noreply@aicaspin.ir>"

    relay(enabled=False)  # off again → back to .env
    assert m.resolve_mail_config().source == "env"


def test_ssl_security_maps_to_implicit_tls():
    relay(security="ssl", port=465)
    cfg = m.resolve_mail_config()
    assert cfg.use_ssl and not cfg.use_tls


def test_save_invalidates_the_process_cache():
    relay(host="first.test")
    assert m.resolve_mail_config().host == "first.test"
    relay(host="second.test")      # post_save bumps the version
    assert m.resolve_mail_config().host == "second.test"


def test_app_emails_go_through_the_relay_and_record_status(smtp):
    from apps.accounts.emails import send_password_reset_email
    from apps.accounts.models import User

    relay()
    assert send_password_reset_email(User(username="u", email="user@example.com"), "tok") is True
    assert ("connect", "smtp-relay.brevo.com", 587) in smtp.calls
    assert ("login", "me@x.test", "s3cret-pass") in smtp.calls
    assert ("sendmail", "Caspin Tunnel <noreply@aicaspin.ir>", ("user@example.com",)) in smtp.calls
    row = EmailSettings.load()
    assert row.last_success_at and row.last_source == "db"


def test_failed_app_email_records_the_error(smtp):
    relay()
    smtp.fail_on, smtp.exc = "login", smtplib.SMTPAuthenticationError(535, b"bad credentials")
    from apps.accounts.emails import _safe_send

    assert _safe_send("s", "b", "user@example.com") is False       # never raises for app mail
    row = EmailSettings.load()
    assert row.last_error.startswith("[auth_failed]") and row.last_error_at


def test_notification_email_channel_uses_the_backend(smtp):
    from apps.accounts.models import User
    from apps.notifications.dispatch import _deliver_email

    relay()
    status, err = _deliver_email(User(username="n", email="n@example.com"), "t", "b")
    assert status == "sent" and err == ""
    assert any(c[0] == "sendmail" for c in smtp.calls)


# ------------------------------------------------------------- password
def test_password_encrypted_at_rest_and_never_serialized(boss):
    r = boss.put(URL, {"enabled": True, "host": "smtp.mailgun.org", "port": 587, "security": "starttls",
                       "username": "postmaster@mg.x", "password": "Pl41n-S3cret"}, format="json")
    assert r.status_code == 200, r.data
    assert "password" not in r.data and r.data["password_set"] is True
    assert "Pl41n-S3cret" not in str(r.data)
    assert "Pl41n-S3cret" not in str(boss.get(URL).data)

    with connection.cursor() as c:
        c.execute("SELECT password FROM email_settings WHERE id = 1")
        stored = c.fetchone()[0]
    assert stored.startswith("enc:v1:") and "Pl41n-S3cret" not in stored
    assert EmailSettings.load().password == "Pl41n-S3cret"

    # blank keeps it, clear_password removes it
    boss.put(URL, {"host": "smtp.mailgun.org", "password": ""}, format="json")
    assert EmailSettings.load().password == "Pl41n-S3cret"
    r = boss.put(URL, {"clear_password": True}, format="json")
    assert r.data["password_set"] is False and EmailSettings.load().password == ""


def test_changes_are_audited_without_the_password(boss):
    boss.put(URL, {"enabled": True, "host": "smtp.sendgrid.net", "username": "apikey",
                   "password": "SG.very-secret"}, format="json")
    log = AuditLog.objects.filter(action="email.settings_updated").latest("id")
    assert log.detail["host"]["to"] == "smtp.sendgrid.net"
    assert log.detail["password"] == "set"
    assert "SG.very-secret" not in str(log.detail)


def test_validation(boss):
    assert boss.put(URL, {"enabled": True, "host": ""}, format="json").status_code == 400
    assert boss.put(URL, {"enabled": True, "host": "mailserver"}, format="json").status_code == 400
    assert boss.put(URL, {"host": "https://smtp.x.test:587"}, format="json").status_code == 400
    assert boss.put(URL, {"port": 70000}, format="json").status_code == 400


# ------------------------------------------------------------- test endpoint
def test_test_email_success(boss, smtp):
    relay()
    r = boss.post(URL + "test/", {"to": "probe@example.com"}, format="json")
    assert r.data["ok"] is True and r.data["source"] == "db" and r.data["code"] == "sent"
    assert ("sendmail", "Caspin Tunnel <noreply@aicaspin.ir>", ("probe@example.com",)) in smtp.calls


def test_test_email_auth_error_is_readable(boss, smtp):
    relay()
    smtp.fail_on, smtp.exc = "login", smtplib.SMTPAuthenticationError(535, b"5.7.8 Authentication failed")
    r = boss.post(URL + "test/", {"to": "probe@example.com"}, format="json")
    assert r.data["ok"] is False and r.data["code"] == "auth_failed"
    assert "Authentication failed" in r.data["en"] and "احراز هویت" in r.data["fa"]
    assert "535" in r.data["raw"]


def test_test_email_timeout_is_readable(boss, smtp):
    relay(host="smtp.blocked.test", port=25, security="none")
    smtp.fail_on, smtp.exc = "connect", socket.timeout("timed out")
    r = boss.post(URL + "test/", {"to": "probe@example.com"}, format="json")
    assert r.data["ok"] is False and r.data["code"] == "timeout"
    assert "587" in r.data["en"]


def test_test_email_sender_not_verified(boss, smtp):
    relay()
    smtp.fail_on, smtp.exc = "sender", smtplib.SMTPSenderRefused(550, b"Sender not verified", "noreply@aicaspin.ir")
    r = boss.post(URL + "test/", {"to": "probe@example.com"}, format="json")
    assert r.data["code"] == "sender_refused" and "verified" in r.data["en"]


def test_test_email_nothing_configured(boss, settings):
    settings.EMAIL_BACKEND, settings.EMAIL_HOST = DYN, ""
    m.bump_email_settings_version()
    r = boss.post(URL + "test/", {"to": "probe@example.com"}, format="json")
    assert r.data["ok"] is False and r.data["code"] == "not_configured"


def test_health_probe_reports_auth_failure(smtp):
    from apps.ops.health import _check_mail

    relay()
    assert _check_mail()[0] is True
    smtp.fail_on, smtp.exc = "login", smtplib.SMTPAuthenticationError(535, b"nope")
    ok, detail = _check_mail()
    assert ok is False and "Authentication failed" in detail


# ------------------------------------------------------------- permissions
def test_permissions(staff_client, perms, api):
    only_settings = staff_client(make_staff("s", ["settings.manage"], perms))
    assert only_settings.get(URL).status_code == 403
    assert only_settings.put(URL, {"host": "x.test"}, format="json").status_code == 403
    assert only_settings.post(URL + "test/", {"to": "a@example.com"}, format="json").status_code == 403

    mailer = staff_client(make_staff("e", ["settings.email"], perms))
    assert mailer.get(URL).status_code == 200
    assert mailer.put(URL, {"host": "smtp.x.test"}, format="json").status_code == 200

    assert api.get(URL).status_code in (401, 403)


def test_seed_creates_the_permission():
    from django.core.management import call_command

    from apps.accounts.models import Permission, Role

    call_command("seed")
    assert Permission.objects.filter(code="settings.email").exists()
    assert Role.objects.get(name="Super Admin").permissions.filter(code="settings.email").exists()


@pytest.fixture
def boss(superadmin, staff_client):
    return staff_client(superadmin)


@pytest.fixture(autouse=True)
def _outbox_isolation():
    mail.outbox = []
    yield
