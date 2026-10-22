"""Staff ticket API under `/api/v1/admin/tickets/` (staff JWT + StaffPermission).

Every ticket endpoint is limited to the staff member's topic scope
(`rules.staff_queryset`): a ticket outside it answers 404."""
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.models import Staff
from apps.adminpanel.views.base import AdminAPIView
from apps.common.models import write_audit
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting

from . import notify, rules, services, staff_link
from .models import Ticket, TicketStatus, TicketTopic
from .serializers import StaffTicketDetailSerializer, StaffTicketSerializer, TopicAdminSerializer
from .views import error

PAGE = 50


class _StaffView(AdminAPIView):
    """Ticket scopes, assignment and Telegram links belong to a `Staff` account —
    the Django-superuser break-glass login of StaffPermission is not enough here."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not isinstance(request.user, Staff):
            self.permission_denied(request, message="log in with a staff account")


class _TicketView(_StaffView):
    def ticket(self, request, pk) -> Ticket:
        qs = rules.staff_queryset(request.user).select_related("topic", "user", "assigned_to", "closed_by")
        return get_object_or_404(qs, pk=pk)


class InboxView(_TicketView):
    perms_map = {"GET": ["tickets.view"]}

    @extend_schema(summary="Ticket inbox (?status=&topic=&priority=&assigned=me|none|<id>&q=&source=&offset=)")
    def get(self, request):
        p = request.query_params
        qs = rules.staff_queryset(request.user).select_related("topic", "user", "assigned_to", "closed_by")
        scope_qs = qs
        status = p.get("status", "")
        if status == "active":
            qs = qs.exclude(status=TicketStatus.CLOSED)
        elif status:
            qs = qs.filter(status__in=status.split(","))
        if p.get("topic"):
            qs = qs.filter(topic_id=p["topic"])
        if p.get("priority"):
            qs = qs.filter(priority=p["priority"])
        if p.get("source"):
            qs = qs.filter(source=p["source"])
        assigned = p.get("assigned", "")
        if assigned == "me":
            qs = qs.filter(assigned_to=request.user)
        elif assigned == "none":
            qs = qs.filter(assigned_to__isnull=True)
        elif assigned.isdigit():
            qs = qs.filter(assigned_to_id=int(assigned))
        q = (p.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(number=q.lstrip("#")) | Q(subject__icontains=q) | Q(user__username__icontains=q)
                           | Q(user__phone__icontains=q) | Q(user__telegram_username__icontains=q))
        try:
            offset = max(0, int(p.get("offset", 0)))
        except ValueError:
            offset = 0
        total = qs.count()
        counts = dict(scope_qs.values_list("status").annotate(n=Count("id")).values_list("status", "n"))
        rows = qs.order_by("-last_activity_at")[offset:offset + PAGE]
        return Response({
            "count": total, "next": offset + PAGE if offset + PAGE < total else None,
            "status_counts": {s: counts.get(s, 0) for s in TicketStatus.values},
            "badge": notify.badge_count(request.user),
            "results": StaffTicketSerializer(rows, many=True).data,
        })


class BadgeView(_StaffView):
    perms_map = {"GET": ["tickets.view"]}

    @extend_schema(summary="Tickets waiting for me (badge count)")
    def get(self, request):
        return Response({"badge": notify.badge_count(request.user)})


class TicketDetailView(_TicketView):
    perms_map = {"GET": ["tickets.view"]}

    @extend_schema(summary="Ticket with messages (incl. internal notes) and full history; marks user messages read")
    def get(self, request, pk):
        t = self.ticket(request, pk)
        services.mark_read(t, by_user=False)
        return Response(StaffTicketDetailSerializer(t).data)


class ReplyView(_TicketView):
    perms_map = {"POST": ["tickets.reply"]}
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(summary="Reply to the user, or add an internal note (multipart: body, attachments[], internal)")
    def post(self, request, pk):
        t = self.ticket(request, pk)
        internal = str(request.data.get("internal", "")).lower() in ("1", "true", "yes", "on")
        try:
            services.staff_reply(t, request.user, body=request.data.get("body"),
                                 files=request.FILES.getlist("attachments"), internal=internal)
        except (services.TicketError, rules.AttachmentError) as exc:
            return error(exc)
        return Response(StaffTicketDetailSerializer(self.ticket(request, pk)).data, status=201)


class AssignView(_TicketView):
    perms_map = {"POST": ["tickets.assign"]}

    @extend_schema(summary="Assign to a staff member ({staff: id | null})")
    def post(self, request, pk):
        t = self.ticket(request, pk)
        sid = request.data.get("staff")
        assignee = get_object_or_404(Staff, pk=sid) if sid not in (None, "", "null") else None
        try:
            services.assign(t, request.user, assignee)
        except services.TicketError as exc:
            return error(exc)
        return Response(StaffTicketDetailSerializer(self.ticket(request, pk)).data)


class StatusView(_TicketView):
    perms_map = {"POST": ["tickets.reply"]}

    @extend_schema(summary="Change status ({status}); closing or reopening needs tickets.close")
    def post(self, request, pk):
        t = self.ticket(request, pk)
        status = request.data.get("status")
        if (status == TicketStatus.CLOSED or t.is_closed) and not request.user.has_perm("tickets.close"):
            return Response({"detail": "closing / reopening needs tickets.close", "code": "forbidden"}, status=403)
        try:
            services.set_status(t, request.user, status)
        except services.TicketError as exc:
            return error(exc)
        return Response(StaffTicketDetailSerializer(self.ticket(request, pk)).data)


class PriorityView(_TicketView):
    perms_map = {"POST": ["tickets.reply"]}

    @extend_schema(summary="Change priority ({priority}: low | normal | high | urgent)")
    def post(self, request, pk):
        t = self.ticket(request, pk)
        try:
            services.set_priority(t, request.user, request.data.get("priority"))
        except services.TicketError as exc:
            return error(exc)
        return Response(StaffTicketDetailSerializer(self.ticket(request, pk)).data)


class AssignableStaffView(_TicketView):
    perms_map = {"GET": ["tickets.assign"]}

    @extend_schema(summary="Staff this ticket can be assigned to (permission + topic scope)")
    def get(self, request, pk):
        t = self.ticket(request, pk)
        return Response([{"id": s.id, "username": s.username} for s in rules.ticket_staff(t.topic_id)])


# --- topics, settings, scopes (tickets.manage_topics) ---------------------------
def _topic_data(data, partial=False):
    fields = {}
    for k in ("name_fa", "name_en", "description_fa", "description_en"):
        if k in data:
            fields[k] = str(data.get(k) or "").strip()
    for k in ("requires_active_service", "is_active"):
        if k in data:
            fields[k] = str(data.get(k)).lower() in ("1", "true", "yes", "on")
    if "sort_order" in data:
        try:
            fields["sort_order"] = int(data.get("sort_order"))
        except (TypeError, ValueError):
            pass
    if not partial and not (fields.get("name_fa") and fields.get("name_en")):
        raise services.TicketError("name_fa and name_en are required", "name")
    if partial and ("name_fa" in fields and not fields["name_fa"] or "name_en" in fields and not fields["name_en"]):
        raise services.TicketError("names cannot be empty", "name")
    return fields


class TopicsView(_StaffView):
    perms_map = {"GET": ["tickets.view"], "POST": ["tickets.manage_topics"]}

    @extend_schema(summary="All topics (incl. inactive)")
    def get(self, request):
        return Response(TopicAdminSerializer(TicketTopic.objects.prefetch_related("staff"), many=True).data)

    @extend_schema(summary="Create a topic")
    def post(self, request):
        try:
            topic = TicketTopic.objects.create(**_topic_data(request.data))
        except services.TicketError as exc:
            return error(exc)
        write_audit(action="ticket.topic_created", staff=request.user, target=topic)
        return Response(TopicAdminSerializer(topic).data, status=201)


class TopicDetailView(_StaffView):
    perms_map = {"PATCH": ["tickets.manage_topics"], "PUT": ["tickets.manage_topics"],
                 "DELETE": ["tickets.manage_topics"]}

    @extend_schema(summary="Edit a topic")
    def patch(self, request, pk):
        topic = get_object_or_404(TicketTopic, pk=pk)
        try:
            fields = _topic_data(request.data, partial=True)
        except services.TicketError as exc:
            return error(exc)
        for k, v in fields.items():
            setattr(topic, k, v)
        topic.save()
        write_audit(action="ticket.topic_updated", staff=request.user, target=topic, detail=fields)
        return Response(TopicAdminSerializer(topic).data)

    put = patch

    @extend_schema(summary="Delete a topic without tickets (otherwise deactivate it)")
    def delete(self, request, pk):
        topic = get_object_or_404(TicketTopic, pk=pk)
        if topic.tickets.exists():
            return Response({"detail": "this topic has tickets — deactivate it instead", "code": "in_use"},
                            status=409)
        write_audit(action="ticket.topic_deleted", staff=request.user, target=topic,
                    detail={"name": topic.name_en})
        topic.delete()
        return Response(status=204)


class SettingsView(_StaffView):
    perms_map = {"GET": ["tickets.view"], "PATCH": ["tickets.manage_topics"], "PUT": ["tickets.manage_topics"]}

    @extend_schema(summary="Ticket settings")
    def get(self, request):
        return Response({"settings": rules.all_settings(),
                         "limits": {k: [lo, hi] for k, _d, lo, hi in rules.SETTINGS}})

    @extend_schema(summary="Update ticket settings")
    def patch(self, request):
        changed = {}
        for key, _default, lo, hi in rules.SETTINGS:
            if key in request.data:
                try:
                    val = max(lo, min(hi, int(request.data[key])))
                except (TypeError, ValueError):
                    return Response({"detail": f"{key} must be a number", "code": "invalid"}, status=400)
                set_setting(key, val, ValueType.INT)
                changed[key] = val
        if changed:
            write_audit(action="ticket.settings", staff=request.user, detail=changed)
        return Response({"settings": rules.all_settings()})

    put = patch


class StaffScopesView(_StaffView):
    perms_map = {"GET": ["tickets.manage_topics"]}

    @extend_schema(summary="Staff who can see tickets, with their topic scope ([] = all topics)")
    def get(self, request):
        out = []
        for s in Staff.objects.filter(is_active=True).select_related("role").prefetch_related("ticket_topics"):
            if s.is_superadmin or s.has_perm("tickets.view"):
                out.append({"id": s.id, "username": s.username, "is_superadmin": s.is_superadmin,
                            "topic_ids": sorted(t.id for t in s.ticket_topics.all()),
                            "telegram_linked": s.telegram_id is not None, "email": s.email})
        return Response(out)


class StaffScopeDetailView(_StaffView):
    perms_map = {"PUT": ["tickets.manage_topics"]}

    @extend_schema(summary="Limit a staff member to these topics ({topic_ids: [...]}, [] = all topics)")
    def put(self, request, pk):
        staff = get_object_or_404(Staff, pk=pk)
        ids = request.data.get("topic_ids") or []
        if not isinstance(ids, list):
            return Response({"detail": "topic_ids must be a list", "code": "invalid"}, status=400)
        topics = list(TicketTopic.objects.filter(pk__in=ids))
        if len(topics) != len(set(ids)):
            return Response({"detail": "unknown topic", "code": "topic"}, status=400)
        staff.ticket_topics.set(topics)
        write_audit(action="ticket.staff_scope", staff=request.user, target=staff,
                    detail={"topics": sorted(t.id for t in topics)})
        return Response({"id": staff.id, "topic_ids": sorted(t.id for t in topics)})


# --- my Telegram link (any logged-in staff member, for themselves) --------------
class TelegramLinkView(_StaffView):
    perms_map = {"GET": [], "POST": [], "DELETE": []}

    @extend_schema(summary="Is my Telegram linked?")
    def get(self, request):
        s = request.user
        return Response({"linked": s.telegram_id is not None, "linked_at": s.telegram_linked_at})

    @extend_schema(request=None, summary="One-time code to link my Telegram (open the deep link or send /start staff-CODE)")
    def post(self, request):
        code = staff_link.new_code(request.user)
        return Response({"code": code, "command": f"/start {staff_link.PREFIX}{code}",
                         "deep_link": staff_link.deep_link(code), "expires_in": staff_link.TTL}, status=201)

    @extend_schema(summary="Unlink my Telegram")
    def delete(self, request):
        s = request.user
        if s.telegram_id is not None:
            s.telegram_id = None
            s.telegram_linked_at = None
            s.save(update_fields=["telegram_id", "telegram_linked_at"])
            write_audit(action="staff.telegram_unlinked", staff=s, target=s)
        return Response({"linked": False})

