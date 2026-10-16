"""/api/v1/agency/portal/ — the reseller portal API (reseller sessions only).

POST login/ {username, password} → {token, expires_at}      (throttle "auth", per-username lockout)
POST logout/
GET  me/                         → PAMP portal numbers (single, group or not_found) + balances
GET  statement/?admin=<name>     → that account's ledger (only accounts the reseller may see)
"""
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import ledger, portal


def _ip(request):
    return request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR", "")


class _Portal(APIView):
    authentication_classes = [portal.ResellerTokenAuthentication]
    permission_classes = [portal.IsReseller]


class PortalLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        if not portal.portal_enabled():
            return Response({"detail": "The reseller portal is not open yet.", "code": "portal_closed"},
                            status=status.HTTP_403_FORBIDDEN)
        token = portal.login(request.data.get("username", ""), request.data.get("password", ""), _ip(request))
        if not token:
            return Response({"detail": "Wrong username or password."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"token": token, "expires_at": timezone.now() + portal.SESSION_AGE})


class PortalLogoutView(_Portal):
    def post(self, request):
        request.auth.revoked = True
        request.auth.save(update_fields=["revoked"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PortalMeView(_Portal):
    def get(self, request):
        if not portal.portal_enabled():
            return Response({"detail": "The reseller portal is not open yet.", "code": "portal_closed"},
                            status=status.HTTP_403_FORBIDDEN)
        return Response(portal.portal_payload(request.user.username))


class PortalStatementView(_Portal):
    def get(self, request):
        if not portal.portal_enabled():
            return Response({"detail": "The reseller portal is not open yet.", "code": "portal_closed"},
                            status=status.HTTP_403_FORBIDDEN)
        name = request.query_params.get("admin") or request.user.username
        _, allowed = portal.visible_usernames(request.user.username)
        if name not in allowed:
            return Response({"detail": "Not your account."}, status=status.HTTP_403_FORBIDDEN)
        st = ledger.statement(name)
        for e in st["entries"]:          # internal fields stay internal
            e.pop("created_by", None)
        st["prices"] = []
        return Response(st)
