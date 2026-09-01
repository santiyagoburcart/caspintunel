import pytest
import responses

from apps.ops.cloudflare import Cloudflare

API = "https://api.cloudflare.com/client/v4"
ZONE = "zone123"


def _ok(result):
    return {"success": True, "result": result, "errors": []}


@responses.activate
def test_upsert_creates_when_absent():
    responses.add(responses.GET, f"{API}/zones/{ZONE}/dns_records", json=_ok([]))
    responses.add(responses.POST, f"{API}/zones/{ZONE}/dns_records", json=_ok({"id": "r1"}))
    res = Cloudflare("t").upsert(ZONE, type="A", name="www.x", content="1.2.3.4", proxied=True)
    assert res["action"] == "created"


@responses.activate
def test_upsert_is_noop_when_identical():
    responses.add(responses.GET, f"{API}/zones/{ZONE}/dns_records",
                  json=_ok([{"id": "r1", "content": "1.2.3.4", "proxied": True}]))
    res = Cloudflare("t").upsert(ZONE, type="A", name="www.x", content="1.2.3.4", proxied=True)
    assert res["action"] == "unchanged"


@responses.activate
def test_upsert_updates_when_changed():
    responses.add(responses.GET, f"{API}/zones/{ZONE}/dns_records",
                  json=_ok([{"id": "r1", "content": "9.9.9.9", "proxied": False}]))
    responses.add(responses.PUT, f"{API}/zones/{ZONE}/dns_records/r1", json=_ok({"id": "r1"}))
    res = Cloudflare("t").upsert(ZONE, type="A", name="x", content="1.2.3.4", proxied=True)
    assert res["action"] == "updated"


@responses.activate
def test_txt_match_prefix_ignores_unrelated_records():
    responses.add(responses.GET, f"{API}/zones/{ZONE}/dns_records",
                  json=_ok([{"id": "g", "content": '"google-site-verification=abc"'}]))
    responses.add(responses.POST, f"{API}/zones/{ZONE}/dns_records", json=_ok({"id": "spf"}))
    res = Cloudflare("t").upsert(ZONE, type="TXT", name="x", content="v=spf1 mx ~all",
                                 match_prefix="v=spf1")
    assert res["action"] == "created"   # didn't touch the google TXT


@responses.activate
def test_configure_dns_dry_run(capsys, settings):
    from django.core.management import call_command

    settings.CLOUDFLARE_API_TOKEN = "test-token"
    responses.add(responses.GET, f"{API}/zones", json=_ok([{"id": ZONE, "name": "aicaspin.ir"}]))
    call_command("configure_dns", "--server-ip", "1.2.3.4", "--domain", "aicaspin.ir")
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "mail.aicaspin.ir" in out
    assert "_dmarc.aicaspin.ir" in out
