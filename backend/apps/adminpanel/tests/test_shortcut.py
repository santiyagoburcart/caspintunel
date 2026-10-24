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
    assert acts[shortcut.ENDPOINT_UUID]["WFWorkflowActionParameters"]["WFTextActionText"].endswith(shortcut.SMS_PATH)
    assert {q["ActionIndex"] for q in wf["WFWorkflowImportQuestions"]} == {0, 1, 2}     # server, token, sender
    for dev in SmsAppDevice.objects.all():
        assert dev.api_token not in raw
    assert "X-Device-Token" in raw
    assert (Path(settings.SHORTCUT_SOURCE_DIR) / "VERSION").read_text().strip() == "1.1.0"


def _flow():
    wf = _template()["WFWorkflowActions"]
    return wf, [a["WFWorkflowActionIdentifier"].removeprefix("is.workflow.actions.") for a in wf]


def test_saves_the_sms_before_any_network_call():
    """v1.1: {text, sender, received_at} → JSON → appended to the queue file first; then the whole
    queue is POSTed. A manual run (no input) only flushes, without an alert."""
    wf, names = _flow()
    assert names.index("file.append") < names.index("downloadurl")
    assert "alert" not in names
    first_if = wf[names.index("conditional")]["WFWorkflowActionParameters"]
    assert first_if["WFCondition"] == 100 and first_if["WFInput"]["Variable"]["Value"] == {"Type": "ExtensionInput"}
    group = first_if["GroupingIdentifier"]
    end = next(i for i, a in enumerate(wf) if a["WFWorkflowActionParameters"].get("GroupingIdentifier") == group
               and a["WFWorkflowActionParameters"]["WFControlFlowMode"] == 2)
    assert names.index("file.append") < end < names.index("downloadurl")         # save inside, send outside
    d = wf[names.index("dictionary")]["WFWorkflowActionParameters"]["WFItems"]["Value"]["WFDictionaryFieldValueItems"]
    body = {i["WFKey"]["Value"]["string"]: i["WFValue"]["Value"]["attachmentsByRange"]["{0, 1}"] for i in d}
    assert set(body) == {"text", "sender", "received_at"} and body["text"] == {"Type": "ExtensionInput"}
    fmt = wf[names.index("format.date")]["WFWorkflowActionParameters"]
    assert fmt["WFDateFormatStyle"] == "ISO 8601" and fmt["WFISO8601IncludeTime"] is True
    assert body["received_at"]["OutputUUID"] == fmt["UUID"]
    append = wf[names.index("file.append")]["WFWorkflowActionParameters"]
    assert append["WFFilePath"]["Value"]["string"] == "CaspinSMS-queue.txt" and append["WFAppendFileWriteMode"] == "Append"


def test_queue_is_posted_and_cleared_only_when_stored():
    wf, names = _flow()
    p = wf[names.index("downloadurl")]["WFWorkflowActionParameters"]
    assert p["WFHTTPMethod"] == "POST" and p["WFHTTPBodyType"] == "File"
    assert p["WFURL"]["Value"]["attachmentsByRange"]["{0, 1}"]["OutputUUID"] == shortcut.ENDPOINT_UUID
    hdr = {i["WFKey"]["Value"]["string"]: i for i in p["WFHTTPHeaders"]["Value"]["WFDictionaryFieldValueItems"]}
    assert hdr["X-Device-Token"]["WFValue"]["Value"]["attachmentsByRange"]["{0, 1}"]["OutputUUID"] == shortcut.TOKEN_UUID
    key = wf[names.index("getvalueforkey")]["WFWorkflowActionParameters"]
    assert key["WFDictionaryKey"] == "result"
    stored_if = next(a["WFWorkflowActionParameters"] for a in wf if a["WFWorkflowActionParameters"].get("WFConditionalActionString"))
    assert stored_if["WFCondition"] == 4 and stored_if["WFConditionalActionString"] == "stored"
    assert names.index("getvalueforkey") < names.index("text.replace") < names.index("file.delete")
    assert names.index("documentpicker.save") < names.index("file.delete")
    assert wf[names.index("file.delete")]["WFWorkflowActionParameters"]["WFDeleteFileConfirmDeletion"] is False
    # every If has its End If
    modes = {}
    for a in wf:
        if a["WFWorkflowActionIdentifier"].endswith("conditional"):
            modes.setdefault(a["WFWorkflowActionParameters"]["GroupingIdentifier"], []).append(a["WFWorkflowActionParameters"]["WFControlFlowMode"])
    assert all(m[0] == 0 and m[-1] == 2 for m in modes.values()) and len(modes) == 5


def test_download_injects_domain_but_never_writes_back(staff_client, superadmin):
    cfg = SiteConfig.load(); cfg.site_domain = "pay.example.ir"; cfg.save()
    before = shortcut.template_path().read_bytes()
    r = staff_client(superadmin).get("/api/v1/admin/apps/ios/download/")
    assert r.status_code == 200 and 'filename="CaspinSMS.shortcut"' in r["Content-Disposition"]
    wf = plistlib.loads(r.content)
    acts = _actions(wf)
    assert acts[shortcut.ENDPOINT_UUID]["WFWorkflowActionParameters"]["WFTextActionText"] == \
        "https://pay.example.ir/api/v1/payments/sms/inbound-batch/"
    assert acts[shortcut.TOKEN_UUID]["WFWorkflowActionParameters"]["WFTextActionText"] == ""
    assert [q["ActionIndex"] for q in wf["WFWorkflowImportQuestions"]] == [1, 2]       # token + sender still asked
    assert shortcut.template_path().read_bytes() == before


def test_download_with_device_injects_its_token(staff_client, superadmin):
    dev = SmsAppDevice.objects.create(name="iPhone 13")
    r = staff_client(superadmin).get(f"/api/v1/admin/apps/ios/download/?device={dev.id}")
    wf = plistlib.loads(r.content)
    assert _actions(wf)[shortcut.TOKEN_UUID]["WFWorkflowActionParameters"]["WFTextActionText"] == dev.api_token
    assert [q["ActionIndex"] for q in wf["WFWorkflowImportQuestions"]] == [2]          # only the optional sender
    assert dev.api_token not in shortcut.template_path().read_text()


def test_device_token_needs_sms_manage(staff_client, perms):
    dev = SmsAppDevice.objects.create(name="iPhone")
    only_settings = staff_client(make_staff("s", ["settings.manage"], perms))
    assert only_settings.get("/api/v1/admin/apps/ios/download/").status_code == 200
    assert only_settings.get(f"/api/v1/admin/apps/ios/download/?device={dev.id}").status_code == 403
    both = staff_client(make_staff("b", ["settings.manage", "sms.manage"], perms))
    assert both.get(f"/api/v1/admin/apps/ios/download/?device={dev.id}").status_code == 200
    assert both.get("/api/v1/admin/apps/ios/download/?device=99999").status_code == 404
