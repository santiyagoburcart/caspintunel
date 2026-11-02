"""v1.34 agency invoices + agency payments for staff (apps/agency/billing.py).

GET  agency/invoices/?admin=&status=&group=          agency.accounting
GET  agency/invoices/settlement/?admin=              quote of «تسویه مانده قبلی»   (agency.accounting)
POST agency/invoices/settlement/ {admin}             issue it (once per admin)
POST agency/invoices/<id>/void/ {reason}             unpaid only, voids its charge too
GET  agency/payments/?status=review|all|<status>     «واریزهای نمایندگان»            (agency.payments)
GET  agency/payments/badge/                          waiting for review (agency.view)
POST agency/payments/<id>/approve/ · reject/ {reason}
GET  agency/payments/<id>/receipt/                   the receipt image (private)
Kept apart from customer payments: never in Transactions, Accounting revenue or Analytics.
"""
from __future__ import annotations

import mimetypes

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from rest_framework.response import Response

from apps.agency import billing as B
from apps.agency.models import AgencyInvoice, AgencyPayment

from .base import AdminAPIView

ACCOUNTING, PAYMENTS, VIEW = ["agency.accounting"], ["agency.payments"], ["agency.view"]


def _err(exc: B.BillingError) -> Response:
    return Response(exc.payload(), status=exc.status)


class _B(AdminAPIView):
    def handle_exception(self, exc):
        if isinstance(exc, B.BillingError):
            return _err(exc)
        return super().handle_exception(exc)


class AgencyInvoicesView(_B):
    perms_map = {"GET": ACCOUNTING}

    def get(self, request):
        q = request.query_params
        qs = AgencyInvoice.objects.all()
        if q.get("admin"):
            qs = qs.filter(admin_username=q["admin"])
        if q.get("group"):
            qs = qs.filter(group_id=q["group"])
        names = list(qs.values_list("admin_username", flat=True).distinct()) if not q.get("admin") else [q["admin"]]
        data = B.invoices_payload(names, q.get("status"))
        if q.get("group"):
            data["results"] = [r for r in data["results"] if str(r["group_id"]) == str(q["group"])]
        if q.get("admin"):
            data["settlement"] = B.settlement_quote(q["admin"])
        return Response(data)


class AgencySettlementView(_B):
    perms_map = {"GET": ACCOUNTING, "POST": ACCOUNTING}

    def get(self, request):
        return Response(B.settlement_quote(request.query_params.get("admin", "")))

    def post(self, request):
        from apps.common.models import write_audit

        inv = B.issue_settlement(str((request.data or {}).get("admin") or ""), by=request.user.username)
        write_audit(action="agency.invoice.settlement", staff=request.user, target=inv,
                    detail={"admin": inv.admin_username, "amount": str(inv.amount), "invoice": inv.number})
        return Response({**B.invoice_row(inv), "message": f"Invoice {inv.number} issued",
                         "message_fa": f"فاکتور {inv.number} صادر شد"}, status=201)


class AgencyInvoiceVoidView(_B):
    perms_map = {"POST": ACCOUNTING}

    def post(self, request, pk):
        from apps.common.models import write_audit

        inv = B.void_invoice(pk, reason=(request.data or {}).get("reason", ""), by=request.user.username)
        write_audit(action="agency.invoice.voided", staff=request.user, target=inv,
                    detail={"invoice": inv.number, "reason": inv.void_reason})
        return Response(B.invoice_row(inv))


class AgencyPaymentsView(_B):
    perms_map = {"GET": PAYMENTS}

    def get(self, request):
        st = request.query_params.get("status") or "review"
        qs = AgencyPayment.objects.select_related("confirmed_by_staff").prefetch_related("items__invoice")
        if st == "review":
            qs = qs.filter(status=AgencyPayment.PENDING_REVIEW)
        elif st == "open":
            qs = qs.filter(status__in=AgencyPayment.ACTIVE)
        elif st != "all":
            qs = qs.filter(status=st)
        q = (request.query_params.get("search") or "").strip()
        if q:
            qs = qs.filter(payer_username__icontains=q) | qs.filter(items__invoice__admin_username__icontains=q)
            qs = qs.distinct()
        counts = {s: AgencyPayment.objects.filter(status=s).count() for s, _ in AgencyPayment.STATUSES}
        return Response({"results": [B.payment_row(p, staff=True) for p in qs[:300]], "counts": counts,
                         "review": counts[AgencyPayment.PENDING_REVIEW]})


class AgencyPaymentsBadgeView(_B):
    perms_map = {"GET": VIEW}

    def get(self, request):
        return Response({"review": B.badge()})


class AgencyPaymentActionView(_B):
    perms_map = {"POST": PAYMENTS}

    def post(self, request, pk, action):
        d = request.data or {}
        if action == "approve":
            p = B.approve_payment(pk, staff=request.user, source="manual")
            return Response({**B.payment_row(p, staff=True), "message": f"Payment {p.number} approved",
                             "message_fa": f"واریز {p.number} تأیید شد"})
        if action == "reject":
            p = B.reject_payment(pk, staff=request.user, reason=d.get("reason", ""))
            return Response({**B.payment_row(p, staff=True), "message": f"Payment {p.number} rejected",
                             "message_fa": f"واریز {p.number} رد شد"})
        raise Http404


def serve_receipt(p: AgencyPayment):
    if not p.receipt_image:
        raise Http404
    name = p.receipt_image.name
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if getattr(settings, "SERVE_MEDIA_VIA_XACCEL", False):
        resp = HttpResponse(content_type=ctype)
        resp["X-Accel-Redirect"] = f"/_protected_media/{name}"
        resp["Content-Disposition"] = "inline"
        return resp
    try:
        fh = p.receipt_image.open("rb")
    except FileNotFoundError as exc:
        raise Http404 from exc
    resp = FileResponse(fh, content_type=ctype)
    resp["Cache-Control"] = "private, max-age=0, no-store"
    return resp


class AgencyPaymentReceiptView(_B):
    perms_map = {"GET": PAYMENTS}

    def get(self, request, pk):
        p = AgencyPayment.objects.filter(pk=pk).first()
        if p is None:
            raise Http404
        return serve_receipt(p)
