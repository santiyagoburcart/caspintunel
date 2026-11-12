"""v1.33: the operator's own sound preferences and browser (Web Push) subscriptions.
Any signed-in staff member, for themselves only."""
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications import webpush

from ..permissions import StaffJWTAuthentication

DEFAULT_PREFS = {"sound": True, "volume": 60, "nav_open": None}   # v1.57 nav_open: {menu section key: open?}


def staff_prefs(staff) -> dict:
    p = dict(DEFAULT_PREFS)
    p.update({k: v for k, v in (staff.notify_prefs or {}).items() if k in DEFAULT_PREFS})
    return p


class NotGroupManager(BasePermission):
    """Signed-in staff, but never a group manager (their panel is default-deny)."""

    def has_permission(self, request, view):
        u = request.user
        return bool(u and getattr(u, "is_authenticated", False) and not getattr(u, "is_group_manager", False))


class _Me(APIView):
    authentication_classes = [StaffJWTAuthentication]
    permission_classes = [NotGroupManager]


class StaffPrefsView(_Me):
    @extend_schema(responses=dict, summary="My panel sound preferences")
    def get(self, request):
        return Response(staff_prefs(request.user))

    @extend_schema(request=dict, responses=dict, summary="Change my panel sound preferences")
    def patch(self, request):
        d = request.data or {}
        p = staff_prefs(request.user)
        if "sound" in d:
            p["sound"] = d["sound"] is True or str(d["sound"]).lower() in ("1", "true", "on")
        if "volume" in d:
            try:
                p["volume"] = max(0, min(100, int(d["volume"])))
            except (TypeError, ValueError):
                return Response({"detail": "volume must be 0–100", "field": "volume"}, status=400)
        if "nav_open" in d:                           # v1.57 desktop sidebar accordion, remembered per staff member
            v = d["nav_open"]
            if v is not None and (not isinstance(v, dict) or len(v) > 30
                                  or any(not isinstance(k, str) or len(k) > 40 or not isinstance(x, bool) for k, x in v.items())):
                return Response({"detail": "nav_open: {section: true|false}", "field": "nav_open"}, status=400)
            p["nav_open"] = v
        request.user.notify_prefs = p
        request.user.save(update_fields=["notify_prefs"])
        return Response(p)

    put = patch


class StaffPushView(_Me):
    @extend_schema(responses=dict, summary="Web Push: is it available, and how many of my browsers are subscribed")
    def get(self, request):
        return Response({"enabled": webpush.enabled(), "public_key": webpush.public_key(),
                         "subscriptions": request.user.push_subscriptions.count()})

    @extend_schema(request=dict, responses=dict, summary="Web Push: subscribe / unsubscribe / test this browser")
    def post(self, request, action=None):
        if not webpush.enabled():
            return Response({"detail": "browser push is not configured on the server (VAPID keys)", "code": "disabled"},
                            status=503)
        d = request.data or {}
        if action == "subscribe":
            try:
                webpush.save_subscription(d.get("subscription") or d, staff=request.user,
                                          user_agent=request.META.get("HTTP_USER_AGENT", ""))
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=400)
            return Response({"ok": True, "message": "Browser notifications are on",
                             "message_fa": "اعلان مرورگر روشن شد"})
        if action == "unsubscribe":
            webpush.delete_subscription(d.get("endpoint", ""), staff=request.user)
            return Response({"ok": True, "message": "Browser notifications are off for this browser",
                             "message_fa": "اعلان مرورگر برای این مرورگر خاموش شد"})
        if action == "test":
            n = webpush.push_to_staff(None, "🔔 تست اعلان · Test notification", "caspintunel", url="/",
                                      tag="test", staff_ids=[request.user.id])
            return Response({"ok": bool(n), "sent": n, "message": f"Test sent to {n} browser(s)",
                             "message_fa": f"اعلان آزمایشی به {n} مرورگر فرستاده شد"})
        return Response({"detail": "not found"}, status=404)
