from rest_framework import serializers

from .models import Ticket, TicketAttachment, TicketEvent, TicketMessage, TicketTopic


class TopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketTopic
        fields = ("id", "name_fa", "name_en", "description_fa", "description_en", "requires_active_service")


class TopicAdminSerializer(serializers.ModelSerializer):
    staff_ids = serializers.SerializerMethodField()
    ticket_count = serializers.SerializerMethodField()

    class Meta:
        model = TicketTopic
        fields = ("id", "name_fa", "name_en", "description_fa", "description_en", "requires_active_service",
                  "is_active", "sort_order", "staff_ids", "ticket_count")

    def get_staff_ids(self, obj) -> list[int]:
        return sorted(s.id for s in obj.staff.all())

    def get_ticket_count(self, obj) -> int:
        return obj.tickets.count()


def _attachment_url(att) -> str:
    return f"/api/v1/tickets/attachments/{att.id}/"


class AttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = TicketAttachment
        fields = ("id", "original_name", "content_type", "size", "url")

    def get_url(self, obj) -> str:
        return _attachment_url(obj)


class UserMessageSerializer(serializers.ModelSerializer):
    """Customer view: staff are "support" — or their display name when the setting
    tickets_show_staff_name is on (never the login username unless no display name)."""
    author = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()
    attachments = AttachmentSerializer(many=True, read_only=True)
    read = serializers.SerializerMethodField()

    class Meta:
        model = TicketMessage
        fields = ("id", "author", "author_name", "body", "channel", "attachments", "read", "created_at")

    def get_author(self, obj) -> str:
        return "staff" if obj.from_staff else "user"

    def get_author_name(self, obj) -> str | None:
        if not obj.from_staff or not self.context.get("show_staff_name") or obj.author_staff is None:
            return None
        return obj.author_staff.display_name or obj.author_staff.username

    def get_read(self, obj) -> bool:
        # for the customer's own messages: has support read it yet?
        return bool(obj.read_by_staff_at) if not obj.from_staff else bool(obj.read_by_user_at)


class StaffMessageSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    staff = serializers.CharField(source="author_staff.username", default=None, read_only=True)
    staff_display = serializers.CharField(source="author_staff.display_name", default=None, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = TicketMessage
        fields = ("id", "author", "staff", "staff_display", "body", "is_internal", "channel", "attachments",
                  "read_by_user_at", "read_by_staff_at", "created_at")

    def get_author(self, obj) -> str:
        return "staff" if obj.from_staff else "user"


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketEvent
        fields = ("id", "kind", "actor_label", "old_value", "new_value", "message_id", "created_at")


class _TicketBase(serializers.ModelSerializer):
    topic = TopicSerializer(read_only=True)


def _preview(msg) -> dict | None:
    if msg is None:
        return None
    return {"author": "staff" if msg.from_staff else "user", "body": (msg.body or "")[:140],
            "attachments": msg.attachments.count(), "created_at": msg.created_at}


class UserTicketSerializer(_TicketBase):
    unread = serializers.SerializerMethodField()
    can_reopen = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = ("id", "number", "subject", "topic", "status", "priority", "source", "service", "order",
                  "created_at", "last_activity_at", "closed_at", "unread", "can_reopen", "last_message")

    def get_last_message(self, obj) -> dict | None:
        return _preview(obj.messages.filter(is_internal=False).order_by("-created_at", "-id").first())

    def get_unread(self, obj) -> int:
        return obj.messages.filter(author_staff__isnull=False, is_internal=False, read_by_user_at__isnull=True).count()

    def get_can_reopen(self, obj) -> bool:
        from datetime import timedelta

        from django.utils import timezone

        from . import rules

        days = rules.setting("tickets_reopen_days")
        return bool(obj.is_closed and days and obj.closed_at and timezone.now() - obj.closed_at <= timedelta(days=days))


class UserTicketDetailSerializer(UserTicketSerializer):
    messages = serializers.SerializerMethodField()

    class Meta(UserTicketSerializer.Meta):
        fields = UserTicketSerializer.Meta.fields + ("messages",)

    def get_messages(self, obj):
        from . import rules

        qs = obj.messages.filter(is_internal=False).select_related("author_staff").prefetch_related("attachments")
        return UserMessageSerializer(qs, many=True,
                                     context={"show_staff_name": rules.bool_setting("tickets_show_staff_name")}).data


class StaffTicketSerializer(_TicketBase):
    user = serializers.SerializerMethodField()
    assigned_to = serializers.SerializerMethodField()
    closed_by = serializers.CharField(source="closed_by.username", default=None, read_only=True)
    unread = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = ("id", "number", "subject", "topic", "status", "priority", "source", "user", "assigned_to",
                  "service", "order", "first_response_at", "last_activity_at", "created_at", "closed_at",
                  "closed_by", "closed_by_kind", "unread", "last_message")

    last_message = serializers.SerializerMethodField()

    def get_last_message(self, obj) -> dict | None:
        return _preview(obj.messages.order_by("-created_at", "-id").first())

    def get_user(self, obj) -> dict:
        u = obj.user
        return {"id": u.id, "username": u.username, "name": u.name, "telegram_username": u.telegram_username}

    def get_assigned_to(self, obj) -> dict | None:
        a = obj.assigned_to
        return {"id": a.id, "username": a.username} if a else None

    def get_unread(self, obj) -> int:
        return obj.messages.filter(author_user__isnull=False, read_by_staff_at__isnull=True).count()


class StaffTicketDetailSerializer(StaffTicketSerializer):
    messages = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()

    class Meta(StaffTicketSerializer.Meta):
        fields = StaffTicketSerializer.Meta.fields + ("messages", "events")

    def get_messages(self, obj):
        qs = obj.messages.select_related("author_staff").prefetch_related("attachments")
        return StaffMessageSerializer(qs, many=True).data

    def get_events(self, obj):
        return EventSerializer(obj.events.all(), many=True).data
