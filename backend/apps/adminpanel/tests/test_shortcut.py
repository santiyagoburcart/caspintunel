"""iPhone SMS Shortcut: repo template is the single source; the panel injects
the endpoint (and optionally one device's token) at download time only."""
import plistlib
from pathlib import Path

import pytest
from django.conf import settings

from apps.adminpanel.tests.conftest import make_staff
from apps.payments_sms.models import SmsAppDevice
from apps.settings_app import shortcut
from apps.settings_app.models import SiteConfig

pytestmark = pytest.mark.django_db
OBJ = "￼"


def _actions(wf):
    return {a["WFWorkflowActionParameters"].get("UUID"): a for a in wf["WFWorkflowActions"]}


def _template():
    with shortcut.template_path().open("rb") as f:
        return plistlib.load(f)


def test_repo_template_has_no_secrets_and_asks_on_import():
    raw = shortcut.template_path().read_text()
    wf = _template()
    acts = _actions(wf)
    assert acts[shortcut.TOKEN_UUID]["WFWorkflowActionParameters"]["WFTextActionText"] == ""
    assert "YOUR-DOMAIN" in acts[shortcut.ENDPOINT_UUID]["WFWorkflowActionParameters"]["WFTextActionText"]
    assert {q["ActionIndex"] for q in wf["WFWorkflowImportQuestions"]} == {0, 1}
    # no real domain / token-looking strings in the committed file
    for dev in SmsAppDevice.objects.all():
        assert dev.api_token not in raw
    assert "aicaspin" not in raw and "X-Device-Token" in raw
    assert (Path(settings.SHORTCUT_SOURCE_DIR) / "VERSION").read_text().strip()


def test_json_body_binds_the_automation_input():
    """text = Shortcut Input (the received message), sender = its Sender
    property, header = the token Text action, URL = the endpoint action."""
    acts = _actions(_template())
    post = next(a for a in acts.values() if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.downloadurl")
    p = post["WFWorkflowActionParameters"]
    assert p["WFHTTPMethod"] == "POST" and p["WFHTTPBodyType"] == "JSON"
    body = {i["WFKey"]["Value"]["string"]: i["WFValue"]["Value"] for i in p["WFJSONValues"]["Value"]["WFDictionaryFieldValueItems"]}
    assert set(body) == {"text", "sender"}
    assert body["text"]["string"] == OBJ and body["text"]["attachmentsByRange"]["{0, 1}"] == {"Type": "ExtensionInput"}
    snd = body["sender"]["attachmentsByRange"]["{0, 1}"]
    assert snd["Type"] == "ExtensionInput" and snd["Aggrandizements"][0]["PropertyName"] == "Sender"
    hdr = p["WFHTTPHeaders"]["Value"]["WFDictionaryFieldValueItems"][0]
    assert hdr["WFKey"]["Value"]["string"] == "X-Device-Token"
    assert hdr["WFValue"]["Value"]["attachmentsByRange"]["{0, 1}"]["OutputUUID"] == shortcut.TOKEN_UUID
    assert p["WFURL"]["Value"]["attachmentsByRange"]["{0, 1}"]["OutputUUID"] == shortcut.ENDPOINT_UUID
    # the POST sits inside "if Shortcut Input has any value" (a manual run sends nothing)
    wf = _template()["WFWorkflowActions"]
    ifs = [a for a in wf if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.conditional"]
    order = [a["WFWorkflowActionIdentifier"].split(".")[-1] for a in wf]
    assert order == ["gettext", "gettext", "conditional", "downloadurl", "conditional", "alert", "conditional"]
    assert wf[2]["WFWorkflowActionParameters"]["WFCondition"] == 100
    assert [a["WFWorkflowActionParameters"]["WFControlFlowMode"] for a in ifs] == [0, 1, 2]
    assert len({a["WFWorkflowActionParameters"]["GroupingIdentifier"] for a in ifs}) == 1


def test_download_injects_domain_but_never_writes_back(staff_client, superadmin):
    cfg = SiteConfig.load(); cfg.site_domain = "pay.example.ir"; cfg.save()
    before = shortcut.template_path().read_bytes()
    r = staff_client(superadmin).get("/api/v1/admin/apps/ios/download/")
    assert r.status_code == 200 and 'filename="CaspinSMS.shortcut"' in r["Content-Disposition"]
    wf = plistlib.loads(r.content)
    acts = _actions(wf)
    assert acts[shortcut.ENDPOINT_UUID]["WFWorkflowActionParameters"]["WFTextActionText"] == \
        "https://pay.example.ir/api/v1/payments/sms/inbound/"
    assert acts[shortcut.TOKEN_UUID]["WFWorkflowActionParameters"]["WFTextActionText"] == ""
    assert [q["ActionIndex"] for q in wf["WFWorkflowImportQuestions"]] == [1]          # token still asked
    assert shortcut.template_path().read_bytes() == before


def test_download_with_device_injects_its_token(staff_client, superadmin):
    dev = SmsAppDevice.objects.create(name="iPhone 13")
    r = staff_client(superadmin).get(f"/api/v1/admin/apps/ios/download/?device={dev.id}")
    wf = plistlib.loads(r.content)
    assert _actions(wf)[shortcut.TOKEN_UUID]["WFWorkflowActionParameters"]["WFTextActionText"] == dev.api_token
    assert wf["WFWorkflowImportQuestions"] == []
    assert dev.api_token not in shortcut.template_path().read_text()


def test_device_token_needs_sms_manage(staff_client, perms):
    dev = SmsAppDevice.objects.create(name="iPhone")
    only_settings = staff_client(make_staff("s", ["settings.manage"], perms))
    assert only_settings.get("/api/v1/admin/apps/ios/download/").status_code == 200
    assert only_settings.get(f"/api/v1/admin/apps/ios/download/?device={dev.id}").status_code == 403
    both = staff_client(make_staff("b", ["settings.manage", "sms.manage"], perms))
    assert both.get(f"/api/v1/admin/apps/ios/download/?device={dev.id}").status_code == 200
    assert both.get("/api/v1/admin/apps/ios/download/?device=99999").status_code == 404
