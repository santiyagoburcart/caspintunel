"""v1.38 «فاکتور دستی» for staff (apps/orders/manual.py).

GET  users/<id>/manual-invoices/            the customer's manual invoices          payment.view
GET  users/<id>/manual-invoices/options/    plans, the customer's services, cards  payments.manual_invoice
POST users/<id>/manual-invoices/            mode=paid (multipart: receipt_image) | mode=issued
POST manual-invoices/<id>/cancel/ {reason}  an open issued invoice                  payments.manual_invoice
"""
from __future__ import annotations

from django.http import Http404
from rest_framework.response import Response

from apps.accounts.models import User
from apps.orders import manual as MIs
from apps.orders.models import ManualInvoice

from .base import AdminAPIView

PERM = ["payments.manual_invoice"]


def _err(exc: MIs.ManualInvoiceError) -> Response:
    return Response({"detail": str(exc), "detail_fa": exc.fa, "field": exc.field,
                     **({exc.field: [exc.fa]} if exc.field else {})}, status=400)


def _user(pk) -> User:
    u = User.objects.filter(pk=pk, deleted_at__isnull=True).first()
    if u is None:
        raise Http404
    return u


class UserManualInvoicesView(AdminAPIView):
    store_ok = True        # v1.60: a store's own customers; money goes to the store's cards / pool (tenant-scoped)
    perms_map = {"GET": ["payment.view"], "POST": PERM}

    def get(self, request, user_id):
        u = _user(user_id)
        lang = "en" if request.query_params.get("lang") == "en" else "fa"
        qs = ManualInvoice.objects.filter(user=u).select_related("plan", "service", "created_by")[:200]
        return Response({"results": [MIs.row(i, lang, staff=True) for i in qs]})

    def post(self, request, user_id):
        u = _user(user_id)
        d = request.data
        mode = d.get("mode")
        try:
            if mode == ManualInvoice.MODE_PAID:
                inv, p, warns = MIs.create_paid(u, request.user, d, receipt_image=request.FILES.get("receipt_image"))
                return Response({**MIs.row(inv, staff=True), "payment_id": p.id, "tx_number": p.tx_number, "warnings": warns,
                                 "message": f"Manual invoice {inv.number} recorded as paid ({p.tx_number})",
                                 "message_fa": f"فاکتور دستی {inv.number} به‌عنوان پرداخت‌شده ثبت شد ({p.tx_number})"}, status=201)
            if mode == ManualInvoice.MODE_ISSUED:
                inv = MIs.issue(u, request.user, d)
                return Response({**MIs.row(inv, staff=True),
                                 "message": f"Invoice {inv.number} issued — the customer was notified",
                                 "message_fa": f"فاکتور {inv.number} صادر شد و به مشتری اطلاع داده شد"}, status=201)
        except MIs.ManualInvoiceError as exc:
            return _err(exc)
        return Response({"detail": "mode must be paid or issued", "field": "mode"}, status=400)


class UserManualInvoiceOptionsView(AdminAPIView):
    store_ok = True        # v1.60: a store's own customers; money goes to the store's cards / pool (tenant-scoped)
    perms_map = {"GET": PERM}

    def get(self, request, user_id):
        from apps.panel.models import Service
        from apps.payments_sms.models import BankCard
        from apps.plans.models import Plan

        u = _user(user_id)
        plans = Plan.objects.filter(is_active=True).select_related("panel")
        return Response({
            "plans": [{"id": p.id, "name": p.name_fa, "name_en": p.name_en, "type": p.type, "price": p.final_price,
                       "data_limit_gb": round((p.data_limit or 0) / 1024 ** 3, 2) if p.data_limit else None,
                       "duration_days": p.duration_days, "panel": p.panel_id} for p in plans],
            "services": [{"id": s.id, "name": s.panel_username, "panel": s.panel_id, "status": s.status,
                          "plan": s.current_plan_id} for s in Service.objects.filter(user=u).order_by("-created_at")],
            "cards": [{"id": c.id, "card_number": c.card_number, "holder_name": c.holder_name, "bank_name": c.bank_name,
                       "is_active": c.is_active} for c in BankCard.objects.order_by("-is_active", "sort_order", "id")],
        })


class ManualInvoiceCancelView(AdminAPIView):
    store_ok = True        # v1.60: a store's own customers; money goes to the store's cards / pool (tenant-scoped)
    perms_map = {"POST": PERM}

    def post(self, request, pk):
        try:
            inv = MIs.cancel(pk, request.user, str((request.data or {}).get("reason") or ""))
        except ManualInvoice.DoesNotExist:
            raise Http404
        except MIs.ManualInvoiceError as exc:
            return _err(exc)
        return Response({**MIs.row(inv, staff=True), "message": f"Invoice {inv.number} cancelled",
                         "message_fa": f"فاکتور {inv.number} لغو شد"})
