"""Subscription QR on a designed background: the code stays pixel-exact and
scannable on every built-in background, the admin picks one (or uploads one),
and the bot photo / site QR use the active background."""
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import Staff, User
from apps.adminpanel.tokens import issue_tokens
from apps.common import qrcard
from apps.settings_app.models import SiteConfig

URL = "https://sub.aicaspin.ir/sub/dGVzdC11c2VyLTE3MjgzOTQ4NTc0MzI4NzQ2Mzg3MjY0MzI4NzY0"


def assert_modules_exact(img, layout, data):
    """Every module (quiet zone included) is pure black or pure white, as in the matrix."""
    m = qrcard.matrix(data)
    assert layout.n == len(m)
    px = img.convert("RGB").load()
    for r, row in enumerate(m):
        for c, dark in enumerate(row):
            x0, y0 = layout.x + c * layout.box, layout.y + r * layout.box
            want = (0, 0, 0) if dark else (255, 255, 255)
            for dx, dy in ((0, 0), (layout.box - 1, 0), (0, layout.box - 1), (layout.box - 1, layout.box - 1)):
                assert px[x0 + dx, y0 + dy] == want, (r, c)


@pytest.mark.parametrize("key", list(qrcard.BUILT_IN))
def test_code_is_untouched_on_every_builtin_background(key):
    img, layout = qrcard.compose(URL, qrcard.background_image(key))
    assert img.size == (qrcard.SIZE, qrcard.SIZE)
    assert_modules_exact(img, layout, URL)
    # centred, with the quiet zone inside the white card
    side = layout.n * layout.box
    assert abs((layout.x + side / 2) - qrcard.SIZE / 2) <= 1 and layout.box >= 3


@pytest.mark.parametrize("key", list(qrcard.BUILT_IN) + [qrcard.PLAIN])
def test_composed_qr_decodes(key):
    zxingcpp = pytest.importorskip("zxingcpp")
    img = Image.open(io.BytesIO(qrcard.to_png(qrcard.compose(URL, qrcard.background_image(key))[0])))
    found = zxingcpp.read_barcodes(img.convert("RGB"))
    assert [b.text for b in found] == [URL]


def test_plain_is_the_bare_code():
    img, layout = qrcard.compose(URL, None)
    assert (layout.x, layout.y) == (0, 0) and img.size[0] == layout.n * layout.box
    assert_modules_exact(img, layout, URL)


def _jpeg(w=800, h=600, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.django_db
def test_custom_background_is_cover_cropped_and_qr_stays_exact():
    cfg = SiteConfig.load()
    cfg.qr_background = qrcard.CUSTOM
    cfg.qr_background_custom.save("bg.jpg", SimpleUploadedFile("bg.jpg", _jpeg()), save=True)
    img, layout = qrcard.compose(URL, qrcard.active_background())
    assert_modules_exact(img, layout, URL)
    r, g, b = img.getpixel((5, 5))
    assert r > 150 and g < 80          # the uploaded red is the background


@pytest.mark.django_db
def test_broken_custom_file_falls_back_to_default():
    bg = qrcard.background_image(qrcard.CUSTOM, None)
    assert bg.size == (qrcard.SIZE, qrcard.SIZE)


# --- admin -----------------------------------------------------------------------
@pytest.fixture
def boss():
    s = Staff(username="boss", is_superadmin=True); s.set_password("x-Str0ng!"); s.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(s)['access']}")
    return c


@pytest.mark.django_db
def test_admin_lists_backgrounds_and_picks_one(boss):
    data = boss.get("/api/v1/admin/branding/").json()
    keys = [b["key"] for b in data["qr_backgrounds"]]
    assert keys[0] == qrcard.PLAIN and set(qrcard.BUILT_IN) <= set(keys) and len(qrcard.BUILT_IN) >= 5
    assert data["qr_background"] == qrcard.DEFAULT
    assert boss.patch("/api/v1/admin/branding/", {"qr_background": "network"}, format="json").status_code == 200
    assert SiteConfig.load().qr_background == "network"
    assert boss.patch("/api/v1/admin/branding/", {"qr_background": "nope"}, format="json").status_code == 400
    # custom needs a file
    assert boss.patch("/api/v1/admin/branding/", {"qr_background": "custom"}, format="json").status_code == 400


@pytest.mark.django_db
def test_admin_custom_upload_is_validated(boss):
    small = SimpleUploadedFile("s.jpg", _jpeg(200, 200), content_type="image/jpeg")
    r = boss.patch("/api/v1/admin/branding/", {"qr_background_custom": small}, format="multipart")
    assert r.status_code == 400 and "qr_background_custom" in r.json()
    fake = SimpleUploadedFile("x.png", b"not an image at all", content_type="image/png")
    assert boss.patch("/api/v1/admin/branding/", {"qr_background_custom": fake}, format="multipart").status_code == 400
    big = SimpleUploadedFile("b.jpg", b"0" * (qrcard.MAX_UPLOAD + 1), content_type="image/jpeg")
    assert boss.patch("/api/v1/admin/branding/", {"qr_background_custom": big}, format="multipart").status_code == 400
    ok = SimpleUploadedFile("ok.jpg", _jpeg(), content_type="image/jpeg")
    r = boss.patch("/api/v1/admin/branding/", {"qr_background_custom": ok, "qr_background": "custom"}, format="multipart")
    assert r.status_code == 200 and r.json()["qr_background_custom"].startswith("/media/branding/qr/")


@pytest.mark.django_db
def test_admin_preview_png(boss):
    r = boss.get("/api/v1/admin/branding/qr-preview/?bg=aurora&size=240")
    assert r.status_code == 200 and r["Content-Type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).size == (240, 240)
    nobody = Staff(username="n"); nobody.set_password("x-Str0ng!"); nobody.save()
    c = APIClient(); c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(nobody)['access']}")
    assert c.get("/api/v1/admin/branding/qr-preview/").status_code == 403


# --- customer-facing ------------------------------------------------------------------
@pytest.mark.django_db
def test_site_and_bot_qr_use_the_active_background():
    from apps.panel.models import Panel, Service
    from apps.telegram.shop import qr_png

    cfg = SiteConfig.load(); cfg.qr_background = "caspian-dark"; cfg.save()
    user = User.objects.create_user("q", "Str0ngPass!")
    panel = Panel.objects.create(name="p", base_url="https://panel.example", admin_username="a", admin_password_enc="b", is_active=True)
    svc = Service.objects.create(user=user, panel=panel, panel_username="q1", status="active", subscription_url=URL)
    c = APIClient(); c.force_authenticate(user)
    r = c.get(f"/api/v1/services/{svc.id}/qr/")
    assert r.status_code == 200 and r["Content-Type"] == "image/png"
    site = Image.open(io.BytesIO(r.content)).convert("RGB")
    assert site.size == (qrcard.SIZE, qrcard.SIZE) and sum(site.getpixel((5, 5))) < 300   # dark corner, not the light default
    bot = Image.open(io.BytesIO(qr_png(URL)))
    assert bot.size == site.size
    img, layout = qrcard.compose(URL, qrcard.active_background())
    assert_modules_exact(site, layout, URL)
