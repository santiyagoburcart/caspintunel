"""Admin Documentation page: docs/*.md read-only, secrets masked, nothing else served."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Staff
from apps.adminpanel.tokens import issue_tokens
from apps.adminpanel.views.docs import mask_secrets

pytestmark = pytest.mark.django_db


@pytest.fixture
def docs(tmp_path, settings):
    (tmp_path / "README.md").write_text("# Index\n\nsee install", encoding="utf-8")
    (tmp_path / "install.md").write_text("# Install\n\nSMTP_RELAY_PASSWORD=hunter2-real\nEMAIL_PASSWORD=xxxx\n", encoding="utf-8")
    (tmp_path / "security-review.md").write_text("# Review", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not markdown", encoding="utf-8")
    (tmp_path.parent / "outside.md").write_text("# secret outside", encoding="utf-8")
    settings.DOCS_DIR = str(tmp_path)
    return tmp_path


def _client(**kw):
    s = Staff(username="s", **kw); s.set_password("x-Str0ng!"); s.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


def test_lists_markdown_readme_first_hides_review(docs):
    rows = _client(is_superadmin=True).get("/api/v1/admin/docs/").json()
    assert rows == [{"slug": "readme", "title": "Index"}, {"slug": "install", "title": "Install"}]


def test_page_masks_real_secret_values_only(docs):
    c = _client(is_superadmin=True)
    md = c.get("/api/v1/admin/docs/install/").json()["markdown"]
    assert "hunter2" not in md and "SMTP_RELAY_PASSWORD=••••••••" in md and "EMAIL_PASSWORD=xxxx" in md


@pytest.mark.parametrize("slug", ["security-review", "notes", "..%2Foutside", "outside", "README.md"])
def test_nothing_else_is_served(docs, slug):
    assert _client(is_superadmin=True).get(f"/api/v1/admin/docs/{slug}/").status_code == 404


def test_needs_settings_manage(docs):
    assert _client().get("/api/v1/admin/docs/").status_code == 403


def test_mask_keeps_prose_and_placeholders():
    assert mask_secrets("FIELD_ENCRYPTION_KEY=<generated>") == "FIELD_ENCRYPTION_KEY=<generated>"
    assert mask_secrets("the password is set in the panel") == "the password is set in the panel"
    assert mask_secrets("  export BOT_TOKEN: 123:abc") == "  export BOT_TOKEN: ••••••••"
