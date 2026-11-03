"""v1.34 invoices / volume requests / payments for agency admins (/api/v1/agency/portal/…) and
group managers (/api/v1/agency/manager/…). Rules live in billing.py; these views only scope:
an admin sees the accounts the portal shows them (themselves, or their group as its owner) and
requests volume only for themselves; a manager sees its own groups' admins and needs the
permission agency.gm.invoices. Anything else → 403 / 404.

portal/invoices/                 GET  list + total unpaid
portal/requests/                 GET  my requests · POST {gb, note}
portal/requests/quote/?gb=       GET  price × GB (or the missing-price error)
portal/payments/                 GET  my payments · POST {invoice_id}   (one invoice, full amount)
portal/payments/<id>/            GET  checkout (card, unique amount, timer)
portal/payments/<id>/receipt/    POST multipart receipt_image [+ receipt_ref]
portal/payments/<id>/cancel/     POST
portal/notices/                  GET latest · ?page= (20 each) · POST {read: true} all, or {id} one
portal/debt/                     GET  v1.38.2 «کل بدهی» (open invoices + old balance) + open payment
portal/payments/all/             POST {expected_total} — «پرداخت کل بدهی» (one payment, 409 total_changed)
portal/invoices/settlement/      POST — issue my «تسویه مانده قبلی» invoice («پرداخت انتخابی»)
portal/push/[subscribe|unsubscribe|test]   GET status · POST — Web Push for this reseller
manager/debt/ · manager/payments/all/ (POST {expected_total}) · manager/invoices/ · manager/payments/ (POST {invoice_ids}) · manager/payments/<id>/… · manager/notices/
"""
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response

from . import billing as B
from . import managers as M
from . import portal
from .models import AgencyNotice, AgencyPayment, VolumeRequest
from .portal_views import _Portal
from .manager_views import _Mgr


class ReceiptSerializer(serializers.Serializer):
    receipt_image = serializers.ImageField()
    receipt_ref = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")


def _berr(exc: B.BillingError) -> Response:
    return Response(exc.payload(), status=exc.status)


def _notice(n) -> dict:
    return {"id": n.id, "kind": n.kind, "title": n.title, "title_en": n.title_en, "body": n.body,
            "body_en": n.body_en, "created_at": n.created_at, "read": n.read_at is not None}


def notice_rows(qs) -> dict:
    return {"results": [_notice(n) for n in qs[:50]], "unread": qs.filter(read_at__isnull=True).count()}


def request_row(r: VolumeRequest) -> dict:
    q = B.quote(r.admin_username, r.gb) if r.status == "pending" else None
    inv = next(iter(r.invoices.all()), None)
    return {"id": r.id, "gb": r.gb, "note": r.note, "status": r.status, "reason": r.reason,
            "created_at": r.created_at, "decided_at": r.decided_at, "group": r.group_name,
            "amount": inv.amount if inv else (q["amount"] if q else None),
            "invoice": inv.number if inv else None}


# ------------------------------------------------------------------ portal (agency admins)
class _PortalB(_Portal):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not portal.portal_enabled():
            raise B.BillingError("The reseller portal is not open yet.", "forbidden", fa="پرتال نمایندگان هنوز فعال نشده است.")
        if not isinstance(self, (PortalNoticesView, PortalPushView)):
            self.initial2()

    def handle_exception(self, exc):
        if isinstance(exc, B.BillingError):
            return _berr(exc)
        return super().handle_exception(exc)

    def initial2(self):
        if portal.check_access(self.request.user.username)["mode"] != "full":
            raise B.BillingError("your account is with your group manager — invoices and requests are there", "forbidden",
                                 fa="حساب شما با مدیر گروه است — فاکتورها و درخواست شارژ از طریق مدیر گروه انجام می‌شود")

    @property
    def allowed(self) -> list[str]:
        return portal.billing_usernames(self.request.user.username)

    def mine(self, p: AgencyPayment) -> bool:
        return p.payer_kind == "admin" and p.payer_username == self.request.user.username


class PortalInvoicesView(_PortalB):
    def get(self, request):
        return Response(B.invoices_payload(self.allowed, request.query_params.get("status")))


class PortalRequestQuoteView(_PortalB):
    def get(self, request):
        return Response(B.quote(request.user.username, request.query_params.get("gb")))


class PortalRequestsView(_PortalB):
    def get(self, request):
        qs = VolumeRequest.objects.filter(kind="request", requested_by=request.user.username).prefetch_related("invoices")
        return Response({"results": [request_row(r) for r in qs[:100]]})

    def post(self, request):
        d = request.data or {}
        r = B.create_request(request.user.username, d.get("gb"), d.get("note", ""))
        return Response({**request_row(r), "message": "Request sent — staff will review it",
                         "message_fa": "درخواست ثبت شد — پس از بررسی نتیجه را همین‌جا می‌بینید"}, status=201)


class PortalPaymentsView(_PortalB):
    def get(self, request):
        qs = AgencyPayment.objects.filter(payer_kind="admin", payer_username=request.user.username)
        return Response({"results": [B.payment_row(p) for p in qs[:50]]})

    def post(self, request):
        d = request.data or {}
        ids = d.get("invoice_ids") or ([d["invoice_id"]] if d.get("invoice_id") else [])   # v1.38.2: several at once
        p = B.create_payment(ids if isinstance(ids, list) else [ids], payer_kind="admin", payer_username=request.user.username,
                             allowed_admins=self.allowed)
        return Response(B.payment_row(p), status=201)


class PortalDebtView(_PortalB):
    """v1.38.2 «کل بدهی» for the portal (same numbers as the group manager's page, direct accounts only)."""

    def get(self, request):
        d = B.debt_breakdown(self.allowed)
        open_p = AgencyPayment.objects.filter(payer_kind="admin", payer_username=request.user.username,
                                              status=AgencyPayment.PENDING_PAYMENT).order_by("-id").first()
        d["open_payment"] = B.payment_row(open_p) if open_p else None
        return Response(d)


class PortalPayAllView(_PortalB):
    def post(self, request):
        p = B.pay_all(None, self.allowed, (request.data or {}).get("expected_total"), admin=request.user.username)
        return Response(B.payment_row(p), status=status.HTTP_201_CREATED)


class PortalSettlementView(_PortalB):
    """«پرداخت انتخابی» of an old balance: issues that account's «تسویه مانده قبلی» invoice (once)."""

    def post(self, request):
        admin = str((request.data or {}).get("admin") or request.user.username)
        if admin not in self.allowed:
            raise B.BillingError("not your account", "forbidden", fa="این حساب متعلق به شما نیست")
        inv = B.issue_settlement(admin, by=f"admin:{request.user.username}")
        return Response({**B.invoice_row(inv), "message": f"Invoice {inv.number} issued",
                         "message_fa": f"فاکتور {inv.number} صادر شد"}, status=201)


class PortalPaymentView(_PortalB):
    def _get(self, pk):
        p = AgencyPayment.objects.filter(pk=pk).first()
        if p is None or not self.mine(p):
            raise B.BillingError("payment not found", "not_found")
        return p

    def get(self, request, pk):
        return Response(B.payment_row(self._get(pk)))

    def post(self, request, pk, action):
        if action == "cancel":
            return Response(B.payment_row(B.cancel_payment(pk, payer_check=self.mine)))
        if action == "receipt":
            ser = ReceiptSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            p = B.submit_receipt(pk, image=ser.validated_data["receipt_image"],
                                 receipt_ref=ser.validated_data.get("receipt_ref", ""), payer_check=self.mine)
            return Response({**B.payment_row(p), "message": "Receipt received — waiting for review",
                             "message_fa": "رسید دریافت شد — در انتظار بررسی"})
        return Response({"detail": "not found"}, status=404)


def paged_notices(qs, page_param) -> dict:
    """The bell (latest 50) or the notifications page (?page=, 20 each)."""
    if not page_param:
        return notice_rows(qs)
    size = 20
    count = qs.count()
    pages = max(1, -(-count // size))
    try:
        page = min(max(1, int(page_param)), pages)
    except ValueError:
        page = 1
    rows = [_notice(n) for n in qs[(page - 1) * size: page * size]]
    return {"results": rows, "unread": qs.filter(read_at__isnull=True).count(), "count": count, "page": page, "pages": pages}


class PortalNoticesView(_PortalB):
    """Read-only sub-admins see their notices too (no initial2 check)."""

    def _qs(self, request):
        return AgencyNotice.objects.filter(admin_username=request.user.username, manager__isnull=True)

    def get(self, request):
        return Response(paged_notices(self._qs(request), request.query_params.get("page")))

    def post(self, request):
        qs = self._qs(request).filter(read_at__isnull=True)
        nid = (request.data or {}).get("id")
        if nid:
            qs = qs.filter(pk=nid)
        qs.update(read_at=timezone.now())
        return Response({"ok": True, "unread": self._qs(request).filter(read_at__isnull=True).count()})


class PortalPushView(_PortalB):
    """v1.38.2 Web Push for this reseller's browsers (notices arrive while the portal is closed)."""

    def get(self, request):
        from apps.notifications import webpush
        from apps.notifications.models import PushSubscription

        return Response({"enabled": webpush.enabled(), "public_key": webpush.public_key(),
                         "subscriptions": PushSubscription.objects.filter(reseller=request.user.username).count()})

    def post(self, request, action=None):
        from apps.notifications import webpush

        if not webpush.enabled():
            return Response({"detail": "browser push is not configured on the server", "code": "disabled",
                             "detail_fa": "اعلان مرورگر روی سرور فعال نیست"}, status=503)
        d = request.data or {}
        if action == "subscribe":
            try:
                webpush.save_subscription(d.get("subscription") or d, reseller=request.user.username,
                                          user_agent=request.META.get("HTTP_USER_AGENT", ""))
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=400)
            return Response({"ok": True, "message": "Browser notifications are on", "message_fa": "اعلان مرورگر روشن شد"})
        if action == "unsubscribe":
            webpush.delete_subscription(d.get("endpoint", ""), reseller=request.user.username)
            return Response({"ok": True, "message": "Browser notifications are off for this browser",
                             "message_fa": "اعلان مرورگر برای این مرورگر خاموش شد"})
        if action == "test":
            n = webpush.push_to_reseller(request.user.username, "🔔 تست اعلان · Test notification", "caspintunel",
                                         url=portal.PORTAL_NOTICES_URL(), tag="test")
            return Response({"ok": bool(n), "sent": n, "message": f"Test sent to {n} browser(s)",
                             "message_fa": f"اعلان آزمایشی به {n} مرورگر فرستاده شد"})
        return Response({"detail": "not found"}, status=404)


# ------------------------------------------------------------------ group managers (staff JWT)
class _MgrB(_Mgr):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.need("agency.gm.invoices")

    def handle_exception(self, exc):
        if isinstance(exc, B.BillingError):
            return _berr(exc)
        return super().handle_exception(exc)

    def mine(self, p: AgencyPayment) -> bool:
        return p.payer_kind == "manager" and p.manager_id == self.m.id


class ManagerInvoicesView(_MgrB):
    def get(self, request):
        names = M.visible_usernames(self.m)
        data = B.invoices_payload(names, request.query_params.get("status"))
        # v1.35: every admin's balance + the old balance not invoiced yet (payable from here)
        data["admins"] = B.admin_balances(names)
        data["groups"] = [{"id": a.group_id, "name": M.group_title(a.group)} for a in M.assignments(self.m)]
        return Response(data)


class ManagerDebtView(_MgrB):
    """v1.35.2 «کل بدهی گروه» + «ریز بدهی» (live from the ledger)."""

    def get(self, request):
        d = B.debt_breakdown(M.visible_usernames(self.m))
        d["groups"] = [{"id": a.group_id, "name": M.group_title(a.group)} for a in M.assignments(self.m)]
        open_p = AgencyPayment.objects.filter(payer_kind="manager", manager=self.m,
                                              status=AgencyPayment.PENDING_PAYMENT).order_by("-id").first()
        d["open_payment"] = B.payment_row(open_p) if open_p else None
        return Response(d)


class ManagerPayAllView(_MgrB):
    """v1.35.2 «پرداخت کل بدهی»: POST {expected_total} → one payment for exactly the current total."""

    def post(self, request):
        p = B.pay_all(self.m, M.visible_usernames(self.m), (request.data or {}).get("expected_total"))
        return Response(B.payment_row(p), status=status.HTTP_201_CREATED)


class ManagerSettlementView(_MgrB):
    """v1.35: pay an admin's old balance — issues its «تسویه مانده قبلی» invoice (once), then the manager pays it."""

    def post(self, request):
        admin = str((request.data or {}).get("admin") or "")
        if admin not in M.visible_usernames(self.m):
            raise B.BillingError("not an admin of your groups", "forbidden", fa="این ادمین در گروه‌های شما نیست")
        inv = B.issue_settlement(admin, by=f"manager:{self.m.username}")
        return Response({**B.invoice_row(inv), "message": f"Invoice {inv.number} issued",
                         "message_fa": f"فاکتور {inv.number} صادر شد"}, status=status.HTTP_201_CREATED)


class ManagerRequestsView(_Mgr):
    """v1.35: ask staff for volume for an admin of the group (same approval as admin requests)."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.need("agency.gm.request_volume")

    def handle_exception(self, exc):
        if isinstance(exc, B.BillingError):
            return _berr(exc)
        return super().handle_exception(exc)

    def get(self, request):
        q = request.query_params
        if q.get("quote"):
            admin = q.get("admin") or ""
            if admin not in M.visible_usernames(self.m):
                raise B.BillingError("not an admin of your groups", "forbidden", fa="این ادمین در گروه‌های شما نیست")
            return Response(B.quote(admin, q.get("gb")))
        qs = VolumeRequest.objects.filter(kind="request", manager=self.m).prefetch_related("invoices")
        return Response({"results": [{**request_row(r), "admin": r.admin_username} for r in qs[:100]]})

    def post(self, request):
        d = request.data or {}
        admin = str(d.get("admin") or "")
        if admin not in M.visible_usernames(self.m):
            raise B.BillingError("not an admin of your groups", "forbidden", fa="این ادمین در گروه‌های شما نیست")
        r = B.create_request(admin, d.get("gb"), d.get("note", ""), manager=self.m)
        return Response({**request_row(r), "admin": admin, "message": "Request sent — staff will review it",
                         "message_fa": "درخواست ثبت شد — پس از تأیید، فاکتور برای این ادمین صادر می‌شود"},
                        status=status.HTTP_201_CREATED)


class ManagerPaymentsView(_MgrB):
    def get(self, request):
        qs = AgencyPayment.objects.filter(payer_kind="manager", manager=self.m)
        return Response({"results": [B.payment_row(p) for p in qs[:50]]})

    def post(self, request):
        ids = (request.data or {}).get("invoice_ids") or []
        if not isinstance(ids, list):
            ids = [ids]
        p = B.create_payment(ids, payer_kind="manager", payer_username=self.m.username, manager=self.m,
                             allowed_admins=M.visible_usernames(self.m))
        return Response(B.payment_row(p), status=status.HTTP_201_CREATED)


class ManagerPaymentView(_MgrB):
    def _get(self, pk):
        p = AgencyPayment.objects.filter(pk=pk).first()
        if p is None or not self.mine(p):
            raise B.BillingError("payment not found", "not_found")
        return p

    def get(self, request, pk):
        return Response(B.payment_row(self._get(pk)))

    def post(self, request, pk, action):
        if action == "cancel":
            return Response(B.payment_row(B.cancel_payment(pk, payer_check=self.mine)))
        if action == "receipt":
            ser = ReceiptSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            p = B.submit_receipt(pk, image=ser.validated_data["receipt_image"],
                                 receipt_ref=ser.validated_data.get("receipt_ref", ""), payer_check=self.mine)
            return Response({**B.payment_row(p), "message": "Receipt received — waiting for review",
                             "message_fa": "رسید دریافت شد — در انتظار بررسی"})
        return Response({"detail": "not found"}, status=404)


class ManagerNoticesView(_Mgr):
    """GET latest (bell) or ?page= (notifications page, 20 each) · POST {read: true} all, or {id} one."""

    def get(self, request):
        qs = AgencyNotice.objects.filter(manager=self.m)
        if not request.query_params.get("page"):
            return Response(notice_rows(qs))
        size = 20
        count = qs.count()
        pages = max(1, -(-count // size))
        try:
            page = min(max(1, int(request.query_params.get("page"))), pages)
        except ValueError:
            page = 1
        rows = [{"id": n.id, "kind": n.kind, "title": n.title, "title_en": n.title_en, "body": n.body, "body_en": n.body_en,
                 "created_at": n.created_at, "read": n.read_at is not None} for n in qs[(page - 1) * size: page * size]]
        return Response({"results": rows, "unread": qs.filter(read_at__isnull=True).count(), "count": count,
                         "page": page, "pages": pages})

    def post(self, request):
        qs = AgencyNotice.objects.filter(manager=self.m, read_at__isnull=True)
        nid = (request.data or {}).get("id")
        if nid:
            qs = qs.filter(pk=nid)
        qs.update(read_at=timezone.now())
        return Response({"ok": True, "unread": AgencyNotice.objects.filter(manager=self.m, read_at__isnull=True).count()})
