"""v1.38.2 /agency/ portal UI — source checks (browser checks run separately against built SPAs): one bell / notifications
page and one stats-tooltip file shared with the group-manager panel, no notices block in the page, «پرداخت کل بدهی»,
the shared receipt picker, and «خروج» behind a confirm."""
from pathlib import Path

import pytest

ADMIN = Path("/app/frontend_admin_src")
USER = Path("/app/frontend_user_src")
pytestmark = pytest.mark.skipif(not (ADMIN.is_dir() and USER.is_dir()), reason="frontend source not mounted")


def _r(root, rel):
    return (root / rel).read_text(encoding="utf-8")


def test_shared_components_are_identical():
    for rel in ("components/AgencyBell.jsx", "components/AgencyStats.jsx", "components/ReceiptDrop.jsx"):
        assert _r(ADMIN, rel) == _r(USER, rel), rel
    assert "AgencyBell" in _r(ADMIN, "components/GmBell.jsx")


def test_portal_sections_bell_and_pay_all():
    page = _r(USER, "pages/AgencyPortal.jsx")
    for part in ("<AgencyBell", "<AgencyNotificationsPage", "useNewBuild", "useConfirm", "'Sold Limit'"):
        assert (part in page) is (part != "'Sold Limit'"), part
    bill = _r(USER, "components/AgencyBilling.jsx")
    assert "function Notices" not in bill and "PortalBilling" not in bill
    assert "'/payments/all/'" in bill and "<details className=\"ap-card ab-adv\"" in bill and "<ReceiptDrop" in bill
    assert "'درخواست / مدیر گروه'" not in bill and "src_admin_request" in bill
