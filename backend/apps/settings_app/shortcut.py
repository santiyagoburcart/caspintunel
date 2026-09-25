"""iPhone SMS Shortcut — built from the repo's single source of truth.

`mobile_shortcut/CaspinSMS.shortcut` (XML plist, no secrets) is the template.
The panel's download fills in, at download time only:
  - the server's SMS endpoint (this deployment's domain), and
  - optionally one SMS device's token (then that import question is dropped).
Nothing injected is ever written back to disk. Output is a binary plist; iOS
still requires it to be signed (`shortcuts sign --mode anyone`) or shared via
an iCloud link before it can be imported — see mobile_shortcut/README.md.
"""
from __future__ import annotations

import plistlib
from pathlib import Path

from django.conf import settings

TEMPLATE_NAME = "CaspinSMS.shortcut"
# fixed action UUIDs in the template (see mobile_shortcut/README.md)
ENDPOINT_UUID = "6F1C4C2E-7A43-4F4B-9D6B-5A1E0C3B7E01"
TOKEN_UUID = "0B9A3D51-2C8E-4E3B-8F77-2D4C6A9E1F02"
SMS_PATH = "/api/v1/payments/sms/inbound/"


def source_dir() -> Path:
    return Path(settings.SHORTCUT_SOURCE_DIR)


def template_path() -> Path:
    return source_dir() / TEMPLATE_NAME


def version() -> str:
    try:
        return (source_dir() / "VERSION").read_text().strip()
    except OSError:
        return ""


def endpoint_url() -> str:
    from apps.settings_app.models import SiteConfig

    domain = (SiteConfig.load().site_domain or "").strip().strip("/")
    base = f"https://{domain}" if domain else settings.PUBLIC_BASE_URL.rstrip("/")
    return base.rstrip("/") + SMS_PATH


def build(*, endpoint: str, token: str | None = None) -> bytes:
    with template_path().open("rb") as f:
        wf = plistlib.load(f)
    actions = wf["WFWorkflowActions"]
    index = {a["WFWorkflowActionParameters"].get("UUID"): i for i, a in enumerate(actions)}
    fill = {index[ENDPOINT_UUID]: endpoint}
    if token:
        fill[index[TOKEN_UUID]] = token
    for i, value in fill.items():
        actions[i]["WFWorkflowActionParameters"]["WFTextActionText"] = value
    # anything we filled in is no longer asked on import
    wf["WFWorkflowImportQuestions"] = [
        q for q in wf.get("WFWorkflowImportQuestions", []) if q.get("ActionIndex") not in fill
    ]
    return plistlib.dumps(wf, fmt=plistlib.FMT_BINARY)
