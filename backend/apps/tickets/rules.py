"""Ticket settings, staff topic scopes and attachment validation."""
from __future__ import annotations

import os
import uuid

from apps.settings_app.utils import get_setting

# key, default, min, max — edited on the ticket settings endpoint (tickets.manage_topics)
SETTINGS = [
    ("tickets_max_open_per_user", 3, 1, 50),      # tickets not closed yet, per user
    ("tickets_auto_close_days", 7, 1, 90),        # awaiting_user this long → closed by the system
    ("tickets_reopen_days", 7, 0, 90),            # a user may reopen a closed ticket within N days (0 = never)
]
_SPEC = {k: (d, lo, hi) for k, d, lo, hi in SETTINGS}


def setting(key: str) -> int:
    default, lo, hi = _SPEC[key]
    try:
        return max(lo, min(hi, int(get_setting(key, default))))
    except (TypeError, ValueError):
        return default


def all_settings() -> dict:
    return {k: setting(k) for k, *_ in SETTINGS}


# --- who has an "active service" (gate for topics with requires_active_service) ---
def has_active_service(user) -> bool:
    from apps.panel.models import Service, ServiceStatus

    return Service.objects.filter(user=user, status__in=(ServiceStatus.ACTIVE, ServiceStatus.ON_HOLD)).exists()


def topics_for_user(user):
    """Active topics this user may open a ticket in."""
    from .models import TicketTopic

    qs = TicketTopic.objects.filter(is_active=True)
    if not has_active_service(user):
        qs = qs.filter(requires_active_service=False)
    return qs


# --- staff scopes ------------------------------------------------------------
def visible_topic_ids(staff) -> set[int] | None:
    """None = every topic (superadmin, or a staff member with no topic scope)."""
    if staff.is_superadmin:
        return None
    ids = set(staff.ticket_topics.values_list("id", flat=True))
    return ids or None


def staff_queryset(staff):
    from .models import Ticket

    qs = Ticket.objects.all()
    ids = visible_topic_ids(staff)
    return qs if ids is None else qs.filter(topic_id__in=ids)


def staff_covers(staff, topic_id: int) -> bool:
    ids = visible_topic_ids(staff)
    return ids is None or topic_id in ids


def ticket_staff(topic_id: int):
    """Active staff who may see tickets of this topic (permission + scope)."""
    from apps.accounts.models import Staff

    out = []
    for s in Staff.objects.filter(is_active=True).select_related("role").prefetch_related("ticket_topics"):
        if not (s.is_superadmin or s.has_perm("tickets.view")):
            continue
        if staff_covers(s, topic_id):
            out.append(s)
    return out


# --- attachments -------------------------------------------------------------
MAX_ATTACHMENTS = 3
MAX_BYTES = 5 * 1024 * 1024
MAX_BODY = 4000

# content sniffed from the first bytes — the file name / browser type are not trusted
_SIGNATURES = [
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
    (b"%PDF-", "application/pdf", ".pdf"),
]


class AttachmentError(ValueError):
    pass


def sniff(head: bytes) -> tuple[str, str] | None:
    for sig, ctype, ext in _SIGNATURES:
        if head.startswith(sig):
            return ctype, ext
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def check_attachments(files) -> list[tuple]:
    """Validate uploaded files → [(file, content_type, ext, original_name)].
    Images must also decode (Pillow), PDFs must carry the PDF header."""
    files = list(files or [])
    if len(files) > MAX_ATTACHMENTS:
        raise AttachmentError(f"at most {MAX_ATTACHMENTS} attachments per message")
    out = []
    for f in files:
        if f.size > MAX_BYTES:
            raise AttachmentError(f"{f.name}: larger than {MAX_BYTES // (1024 * 1024)} MB")
        if f.size == 0:
            raise AttachmentError(f"{f.name}: empty file")
        f.seek(0)
        kind = sniff(f.read(16))
        f.seek(0)
        if kind is None:
            raise AttachmentError(f"{f.name}: only JPEG, PNG, GIF, WebP images and PDF files are allowed")
        ctype, ext = kind
        if ctype.startswith("image/"):
            from PIL import Image

            try:
                with Image.open(f) as im:
                    im.verify()
            except Exception as exc:  # noqa: BLE001
                raise AttachmentError(f"{f.name}: not a valid image") from exc
            f.seek(0)
        name = os.path.basename(f.name or "file")[:120] or "file"
        out.append((f, ctype, ext, name))
    return out


def stored_name(ext: str) -> str:
    """Random file name: the original name is kept in the DB only."""
    return f"{uuid.uuid4().hex}{ext}"
