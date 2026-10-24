"""iPhone SMS Shortcut — built from the repo's single source of truth.

`mobile_shortcut/CaspinSMS.shortcut` (XML plist, no secrets) is the template.
The panel's download fills in, at download time only:
  - the server's SMS endpoint (this deployment's domain), and
  - optionally one SMS device's token (then that import question is dropped).
Nothing injected is ever written back to disk. Output is an UNSIGNED binary
plist: iOS 15+ refuses to import unsigned shortcuts ("Importing unsigned
shortcut files is not supported") and signing needs macOS/iCloud, so this file
is only the "advanced" path (`shortcuts sign --mode anyone` on a Mac).

The OFFICIAL distribution is an iCloud link (setting `ios_shortcut_icloud_url`,
edited on the panel's Apps page): the operator imports the shortcut on an
iPhone once, shares it as an iCloud link and pastes that link in the panel.
Installing from the link asks for the server address + device token (the
template's import questions). A token is never part of that link.
"""
from __future__ import annotations

import plistlib
import re
from pathlib import Path

from django.conf import settings

TEMPLATE_NAME = "CaspinSMS.shortcut"
# fixed action UUIDs in the template (see mobile_shortcut/README.md)
ENDPOINT_UUID = "6F1C4C2E-7A43-4F4B-9D6B-5A1E0C3B7E01"
TOKEN_UUID = "0B9A3D51-2C8E-4E3B-8F77-2D4C6A9E1F02"
SMS_PATH = "/api/v1/payments/sms/inbound-batch/"   # v1.1+: offline queue, uploaded as a batch

ICLOUD_SETTING = "ios_shortcut_icloud_url"
ICLOUD_PREFIX = "https://www.icloud.com/shortcuts/"
# exactly an iCloud shortcut share link: no query, fragment or extra path
_ICLOUD_RE = re.compile(r"^https://www\.icloud\.com/shortcuts/[A-Za-z0-9]{8,64}/?$")


def clean_icloud_url(raw) -> str:
    """Validated iCloud share link ('' clears it). Raises ValueError with a
    message for the operator. A device token must never travel in this link."""
    from apps.payments_sms.models import SmsAppDevice

    url = str(raw or "").strip()
    if not url:
        return ""
    if not url.startswith(ICLOUD_PREFIX):
        raise ValueError(f"the iCloud link must start with {ICLOUD_PREFIX}")
    if not _ICLOUD_RE.match(url):
        raise ValueError("not an iCloud shortcut link — copy it from Share → Copy iCloud Link "
                         "(https://www.icloud.com/shortcuts/<id>, nothing after the id)")
    tokens = SmsAppDevice.objects.values_list("api_token", flat=True)
    if any(t and t in url for t in tokens):
        raise ValueError("the link must not contain a device token")
    return url


def icloud_url() -> str:
    """The configured share link, or '' (an invalid stored value is ignored)."""
    from apps.settings_app.utils import get_setting

    try:
        return clean_icloud_url(get_setting(ICLOUD_SETTING, ""))
    except ValueError:
        return ""


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
