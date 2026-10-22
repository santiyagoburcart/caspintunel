"""Customer ticket API (`/api/v1/tickets/`) + the attachment file view.
Staff endpoints live in `admin_views.py` (`/api/v1/admin/tickets/`)."""
import mimetypes

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.authentication import JWTAuthentication
from apps.accounts.models import Staff
from apps.adminpanel.permissions import StaffJWTAuthentication

from . import rules, services
from .models import Ticket, TicketAttachment
from .serializers import TopicSerializer, UserTicketDetailSerializer, UserTicketSerializer


def error(exc: services.TicketError | rules.AttachmentError) -> Response:
    if isinstance(exc, rules.AttachmentError):
        return Response({"detail": str(exc), "code": "attachment"}, status=400)
    return Response({"detail": str(exc), "code": exc.code}, status=exc.status)


def _files(request):
    return request.FILES.getlist("attachments")


class _UserView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # a staff token must not act as a customer here
        if isinstance(request.user, Staff):
            self.permission_denied(request, message="customer endpoint")

    def ticket(self, request, pk) -> Ticket:
        return get_object_or_404(Ticket.objects.select_related("topic"), pk=pk, user=request.user)


class TopicsView(_UserView):
    @extend_schema(summary="Topics I can open a ticket in")
    def get(self, request):
        return Response({"has_active_service": rules.has_active_service(request.user),
                         "topics": TopicSerializer(rules.topics_for_user(request.user), many=True).data})


class TicketListView(_UserView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_scope = "ticket"

    def get_throttles(self):
        # the "ticket" scope limits creating tickets, not reading the list
        throttles = super().get_throttles()
        if self.request.method != "POST":
            throttles = [t for t in throttles if not isinstance(t, ScopedRateThrottle)]
        return throttles

    @extend_schema(summary="My tickets")
    def get(self, request):
        qs = Ticket.objects.filter(user=request.user).select_related("topic")
        if request.query_params.get("status") == "open":
            qs = qs.exclude(status="closed")
        elif request.query_params.get("status") == "closed":
            qs = qs.filter(status="closed")
        return Response({"results": UserTicketSerializer(qs[:200], many=True).data,
                         "max_open": rules.setting("tickets_max_open_per_user")})

    @extend_schema(summary="Open a ticket (multipart: topic, subject, body, attachments[], service?, order?)")
    def post(self, request):
        d = request.data
        try:
            t = services.open_ticket(request.user, topic_id=d.get("topic"), subject=d.get("subject"),
                                     body=d.get("body"), files=_files(request), service_id=d.get("service") or None,
                                     order_id=d.get("order") or None, channel="site")
        except (services.TicketError, rules.AttachmentError) as exc:
            return error(exc)
        return Response(UserTicketDetailSerializer(t).data, status=201)


class TicketDetailView(_UserView):
    @extend_schema(summary="One of my tickets with its messages (marks support replies read)")
    def get(self, request, pk):
        t = self.ticket(request, pk)
        services.mark_read(t, by_user=True)
        return Response(UserTicketDetailSerializer(t).data)


class TicketReplyView(_UserView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_scope = "ticket"

    @extend_schema(summary="Reply (multipart: body, attachments[])")
    def post(self, request, pk):
        t = self.ticket(request, pk)
        try:
            services.user_reply(t, request.user, body=request.data.get("body"), files=_files(request), channel="site")
        except (services.TicketError, rules.AttachmentError) as exc:
            return error(exc)
        t.refresh_from_db()
        return Response(UserTicketDetailSerializer(t).data, status=201)


class TicketCloseView(_UserView):
    @extend_schema(request=None, summary="Close my ticket")
    def post(self, request, pk):
        t = services.user_close(self.ticket(request, pk), request.user)
        return Response(UserTicketSerializer(t).data)


class TicketReopenView(_UserView):
    @extend_schema(request=None, summary="Reopen my closed ticket (within tickets_reopen_days)")
    def post(self, request, pk):
        try:
            t = services.user_reopen(self.ticket(request, pk), request.user)
        except services.TicketError as exc:
            return error(exc)
        return Response(UserTicketSerializer(t).data)


class AttachmentFileView(APIView):
    """A ticket attachment for the ticket's owner (never on internal notes) or for
    staff with `tickets.view` whose topic scope covers the ticket. Prod hands off
    to nginx (`/_protected_media/`); `/media/tickets/` itself is 404 in nginx."""

    authentication_classes = [StaffJWTAuthentication, JWTAuthentication, SessionAuthentication]
    permission_classes = [permissions.AllowAny]      # checked below

    def get(self, request, pk):
        att = get_object_or_404(TicketAttachment.objects.select_related("message__ticket"), pk=pk)
        ticket = att.message.ticket
        user = request.user
        if isinstance(user, Staff):
            allowed = (user.is_superadmin or user.has_perm("tickets.view")) and rules.staff_covers(user, ticket.topic_id)
        elif getattr(user, "is_authenticated", False):
            allowed = ticket.user_id == user.id and not att.message.is_internal
        else:
            return Response({"detail": "authentication required"}, status=401)
        if not allowed:
            raise Http404
        ctype = att.content_type or mimetypes.guess_type(att.file.name)[0] or "application/octet-stream"
        disposition = "inline" if ctype.startswith("image/") else f'attachment; filename="attachment-{att.id}.pdf"'
        if getattr(settings, "SERVE_MEDIA_VIA_XACCEL", False):
            resp = HttpResponse(content_type=ctype)
            resp["X-Accel-Redirect"] = f"/_protected_media/{att.file.name}"
        else:
            try:
                resp = FileResponse(att.file.open("rb"), content_type=ctype)
            except FileNotFoundError as exc:
                raise Http404 from exc
            resp["Cache-Control"] = "private, max-age=0, no-store"
        resp["Content-Disposition"] = disposition
        resp["X-Content-Type-Options"] = "nosniff"
        return resp
