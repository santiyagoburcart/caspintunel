"""v1.38.1 group-manager UI fixes — source checks (the browser checks run separately, against built SPAs).

- one receipt picker (components/ReceiptDrop.jsx, identical in both apps) everywhere a receipt is uploaded,
  and its size limit stays under what Django / nginx accept;
- the group manager's avatar only links to Settings (no dropdown) and «خروج» always asks first.
"""
import re
from pathlib import Path

import pytest
from django.conf import settings

ADMIN = Path("/app/frontend_admin_src")
USER = Path("/app/frontend_user_src")
pytestmark = pytest.mark.skipif(not (ADMIN.is_dir() and USER.is_dir()), reason="frontend source not mounted")


def _r(root, rel):
    return (root / rel).read_text(encoding="utf-8")


def test_one_receipt_picker_everywhere():
    assert _r(ADMIN, "components/ReceiptDrop.jsx") == _r(USER, "components/ReceiptDrop.jsx")
    uses = [(ADMIN, "components/AgencyBilling.jsx"), (USER, "components/AgencyBilling.jsx"),
            (ADMIN, "components/ManualInvoice.jsx"), (USER, "pages/Checkout.jsx")]
    for root, rel in uses:
        src = _r(root, rel)
        assert "<ReceiptDrop" in src, rel
        assert 'type="file"' not in src, f"{rel} still has a native file input"
    mb = int(re.search(r"RECEIPT_MAX_MB = (\d+)", _r(USER, "components/ReceiptDrop.jsx")).group(1))
    assert mb * 1024 * 1024 < min(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, settings.FILE_UPLOAD_MAX_MEMORY_SIZE)


def test_gm_avatar_opens_settings_and_logout_confirms():
    lay = _r(ADMIN, "components/Layout.jsx")
    assert "AvatarMenu" not in lay and "avm-pop" not in lay
    assert lay.count('<AvatarLink to="/my-groups/settings"') == 2          # phone + desktop top bar
    assert "gmLogout={gm}" in lay                                          # bottom of the GM sidebar
    btn = _r(ADMIN, "components/LogoutButton.jsx")
    assert "useConfirm" in btn and "tone: 'danger'" in btn
    gm = _r(ADMIN, "pages/GroupManager.jsx")
    assert "<LogoutButton" in gm and "set_logout_hint" not in gm


def test_gm_card_keeps_details_out_of_the_card():
    gm = _r(ADMIN, "pages/GroupManager.jsx")
    card = gm[gm.index("function AdminCard("):gm.index("function Pager(")]
    assert "StatGrid" not in card and "<MoreMenu" in card
