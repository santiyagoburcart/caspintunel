from datetime import timedelta

import jdatetime
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.jalali import to_jalali_str
from apps.common.models import write_audit
from apps.notifications.live import push_payments_event
from apps.payments_sms.models import BankCard, ConfirmedBy, Payment, PaymentStatus
from apps.payments_sms.services import PaymentError, approve_payment, reject_payment

from ..serializers import AdminPendingPaymentSerializer, TransactionSerializer
from .base import AdminAPIView, _AUTH
from ..permissions import StaffPermission


class TransactionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Transactions (= payments). ?search= (TX-000123 / number / user / account),
    ?deleted=1 (Super Admin: include deleted ones), ?export=csv (all filtered rows).
    Delete (void) / restore — Super Admin only (apps/payments_sms/voiding.py)."""

    authentication_classes = _AUTH
    permission_classes = [StaffPermission]
    perms_map = {"GET": ["payment.view"], "POST": ["payment.approve"]}
    queryset = Payment.objects.none()
    serializer_class = TransactionSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status", "method", "confirmed_by", "bank_card"]
    ordering_fields = ["created_at", "amount", "number"]
    ordering = ["-created_at"]

    def _superadmin(self) -> bool:
        return bool(getattr(self.request.user, "is_superadmin", False))

    def get_queryset(self):
        qs = Payment.objects.select_related(
            "order", "order__user", "order__plan", "bank_card", "confirmed_by_staff", "voided_by"
        )
        q = self.request.query_params
        if self.action == "list" or self.action is None:
            # deleted (voided) rows: hidden unless a Super Admin asks for them
            if not (self._superadmin() and q.get("deleted") in ("1", "true", "only")):
                qs = qs.live()
            elif q.get("deleted") == "only":
                qs = qs.filter(voided_at__isnull=False)
        elif not self._superadmin():
            qs = qs.live()
        src = q.get("source")
        if src:
            qs = qs.filter(order__source=src)
        frm = _parse_any_date(q.get("from"))
        to = _parse_any_date(q.get("to"), end_of_day=True)
        if frm:
            qs = qs.filter(created_at__gte=frm)
        if to:
            qs = qs.filter(created_at__lte=to)
        term = (q.get("search") or "").strip()
        if term:
            qs = qs.filter(_tx_search(term))
        return qs.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        if request.query_params.get("export") == "csv":
            rows = self.filter_queryset(self.get_queryset())
            return _transactions_csv(rows, "en" if request.query_params.get("lang") == "en" else "fa")
        return super().list(request, *args, **kwargs)

    # --- delete (void) / restore — Super Admin only ---------------------------------
    def _void_err(self, exc):
        return Response(exc.payload(), status=exc.status)

    @extend_schema(request=None, responses=dict, summary="What deleting this transaction affects (Super Admin)")
    @action(detail=True, methods=["get"], url_path="delete-preview")
    def delete_preview(self, request, pk=None):
        from apps.payments_sms.voiding import VoidError, preview, require_superadmin

        try:
            require_superadmin(request.user)
        except VoidError as exc:
            return self._void_err(exc)
        p = Payment.objects.select_related("order", "order__user", "order__service", "order__service__panel").filter(pk=pk).first()
        if p is None:
            return Response({"detail": "transaction not found"}, status=404)
        return Response(preview(p))

    @extend_schema(request=dict, responses=TransactionSerializer, summary="Delete (void) a transaction (Super Admin)")
    @action(detail=True, methods=["post"], url_path="delete")
    def void(self, request, pk=None):
        from apps.payments_sms.voiding import VoidError, void_payment

        try:
            # the option is passed through as sent — missing / unknown → 400, never a silent "keep"
            p = void_payment(pk, staff=request.user, reason=request.data.get("reason", ""),
                             service_action=request.data.get("service_action"))
        except VoidError as exc:
            return self._void_err(exc)
        data = dict(TransactionSerializer(Payment.objects.get(pk=p.pk)).data)
        data["service_result"] = p.service_result      # kept | no_service | disabled | deleted | missing_on_panel
        return Response(data)

    @extend_schema(request=dict, responses=TransactionSerializer,
                   summary="Undo a rounded-amount auto-approval (Super Admin) — voids it like a delete")
    @action(detail=True, methods=["post"], url_path="undo-rounded")
    def undo_rounded(self, request, pk=None):
        """«لغو تأیید»: {reason?, service_action? (default keep)} — rounded.undo."""
        from apps.payments_sms.rounded import undo
        from apps.payments_sms.voiding import VoidError

        try:
            p = undo(pk, staff=request.user, reason=request.data.get("reason", ""),
                     service_action=request.data.get("service_action") or "keep")
        except VoidError as exc:
            return self._void_err(exc)
        data = dict(TransactionSerializer(Payment.objects.get(pk=p.pk)).data)
        data["service_result"] = p.service_result
        data["message"] = f"Auto-approval undone ({p.tx_number}); the deposit is back for review"
        data["message_fa"] = f"تأیید خودکار لغو شد ({p.tx_number})؛ واریز برای بررسی دستی برگشت"
        return Response(data)

    @extend_schema(request=None, responses=TransactionSerializer, summary="Restore a deleted transaction (Super Admin)")
    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        from apps.payments_sms.voiding import VoidError, restore_payment

        try:
            p = restore_payment(pk, staff=request.user)
        except VoidError as exc:
            return self._void_err(exc)
        return Response(TransactionSerializer(Payment.objects.get(pk=p.pk)).data)

    @extend_schema(request=dict, responses=dict, summary="Delete (void) several transactions (Super Admin)")
    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_void(self, request):
        """{ids, reason, service_action} (required): the choice applies to each row that has a
        service; a row without one is deleted with "keep" and says so (service_result
        "no_service"). One result per id; a PasarGuard refusal leaves that row untouched."""
        from apps.payments_sms.voiding import VoidError, require_superadmin, void_payment

        try:
            require_superadmin(request.user)
        except VoidError as exc:
            return self._void_err(exc)
        ids = _ids(request.data.get("ids"))
        if not ids:
            return Response({"detail": "pick at least one transaction", "field": "ids"}, status=400)
        action_ = request.data.get("service_action")
        if action_ not in ("keep", "disable", "delete"):
            return Response({"detail": "choose what happens to the orders / services: keep, disable or delete",
                             "code": "invalid", "field": "service_action"}, status=400)
        out = []
        for pid in ids:
            try:
                has_service = Payment.objects.filter(pk=pid, order__service__isnull=False).exists()
                p = void_payment(pid, staff=request.user, reason=request.data.get("reason", ""),
                                 service_action=action_ if has_service else "keep")
                out.append({"id": pid, "ok": True, "tx_number": p.tx_number, "service_result": p.service_result})
            except VoidError as exc:
                if exc.field == "reason":
                    return self._void_err(exc)
                out.append({"id": pid, "ok": False, "detail": str(exc), "code": exc.code})
        return Response({"results": out, "ok": sum(1 for r in out if r["ok"]), "failed": sum(1 for r in out if not r["ok"])})

    @extend_schema(request=dict, responses=dict, summary="Restore several deleted transactions (Super Admin)")
    @action(detail=False, methods=["post"], url_path="bulk-restore")
    def bulk_restore(self, request):
        from apps.payments_sms.voiding import VoidError, require_superadmin, restore_payment

        try:
            require_superadmin(request.user)
        except VoidError as exc:
            return self._void_err(exc)
        out = []
        for pid in _ids(request.data.get("ids")):
            try:
                restore_payment(pid, staff=request.user)
                out.append({"id": pid, "ok": True})
            except VoidError as exc:
                out.append({"id": pid, "ok": False, "detail": str(exc), "code": exc.code})
        return Response({"results": out, "ok": sum(1 for r in out if r["ok"]), "failed": sum(1 for r in out if not r["ok"])})

    @extend_schema(request=dict, responses=TransactionSerializer,
                   summary="Manually set a payment's status (admin override)")
    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        payment = self.get_object()
        target = (request.data.get("status") or "").strip()
        reason = (request.data.get("reason") or "").strip()
        if target not in PaymentStatus.values:
            return Response({"detail": "invalid status"}, status=400)
        if target == payment.status:
            return Response(TransactionSerializer(payment).data)

        # ANY transition into approved runs the real flow (fulfilment, notification,
        # confirmer) — incl. rejected -> approved; into rejected likewise.
        try:
            if target == PaymentStatus.APPROVED:
                payment = approve_payment(payment.pk, actor=request.user)
            elif target == PaymentStatus.REJECTED and payment.status == PaymentStatus.PENDING:
                payment = reject_payment(payment.pk, reason=reason or "رد شد", actor=request.user)
            else:
                # any other transition = a manual override, no side effects
                payment.status = target
                if target == PaymentStatus.APPROVED:
                    payment.confirmed_by = ConfirmedBy.ADMIN
                    payment.confirmed_at = payment.confirmed_at or timezone.now()
                elif target == PaymentStatus.PENDING:
                    payment.confirmed_by = None
                    payment.confirmed_at = None
                    payment.reject_reason = ""
                elif target == PaymentStatus.REJECTED:
                    payment.reject_reason = reason or payment.reject_reason or "رد شد"
                payment.save(update_fields=["status", "confirmed_by", "confirmed_at",
                                            "reject_reason", "updated_at"])
                write_audit(action="payment.status_override", target=payment, staff=request.user,
                            detail={"to": target, "reason": reason})
                push_payments_event("payment_status_changed", order_id=payment.order_id,
                                    payment_id=payment.id, by=getattr(request.user, "username", None))
        except PaymentError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(TransactionSerializer(payment).data)


class PendingPaymentsView(AdminAPIView):
    """The card-to-card approval queue — pending receipts from site + bot."""

    perms_map = {"GET": ["payment.view"]}

    @extend_schema(responses=AdminPendingPaymentSerializer(many=True),
                   summary="Payments awaiting manual approval")
    def get(self, request):
        qs = (
            Payment.objects.live().filter(status=PaymentStatus.PENDING)
            .select_related("order", "order__user", "order__plan", "bank_card", "sms_message", "blu_transaction")
            .order_by("created_at")
        )
        data = AdminPendingPaymentSerializer(qs, many=True, context={"request": request}).data
        return Response({"results": data, "count": len(data)})


def _blu_row(tx) -> dict:
    from apps.payments_sms.blu import mask_card

    return {
        "id": tx.id, "amount_toman": tx.amount_toman, "amount_irr": tx.amount_irr,
        "occurred_at": tx.occurred_at, "occurred_jalali": to_jalali_str(tx.occurred_at),
        "type_label": tx.type_label, "payer_name": tx.payer_name,
        "payer_card": mask_card(tx.payer_card) if tx.payer_card else (f"******{tx.payer_last4}" if tx.payer_last4 else ""),
        "receipt": tx.receipt, "reference": tx.reference, "status": tx.status,
        "matched_order": tx.matched_order_id, "matched_payment": tx.matched_payment_id,
        "match_note": tx.match_note, "received_at": tx.received_at,
        # v1.32: approved by the rounded-amount rule (payments_sms/rounded.py)
        "rounded": bool(tx.matched_payment_id and tx.matched_payment.auto_rule == "rounded"),
        "shortfall": tx.matched_payment.shortfall if tx.matched_payment_id else None,
    }


class BluTransactionListView(AdminAPIView):
    """GET /admin/payments/blu-transactions/?status=&limit= — Blu deposits, newest first,
    plus the collector's health (last batch, connected / offline)."""

    perms_map = {"GET": ["payment.view"]}

    @extend_schema(responses=dict, summary="Blu Bank deposits + collector health")
    def get(self, request):
        from apps.payments_sms.blu import collector_health
        from apps.payments_sms.models import BluStatus, BluTransaction

        qs = BluTransaction.objects.select_related("matched_payment").order_by("-occurred_at", "-id")
        st = request.query_params.get("status")
        if st:
            if st not in BluStatus.values:
                return Response({"status": [f"one of {', '.join(BluStatus.values)}"]}, status=400)
            qs = qs.filter(status=st)
        try:
            limit = max(1, min(500, int(request.query_params.get("limit") or 100)))
        except ValueError:
            limit = 100
        counts = {k: 0 for k in BluStatus.values}
        for row in BluTransaction.objects.values("status").annotate(n=Count("id")):
            counts[row["status"]] = row["n"]
        rows = [_blu_row(tx) for tx in qs[:limit]]
        return Response({"collector": collector_health(), "counts": counts, "results": rows, "count": len(rows)})


class BluAttachView(AdminAPIView):
    """POST /admin/payments/blu-transactions/<id>/attach/ {order_id} — staff match an
    unmatched deposit to an order: approves it (confirmed_by admin) and fulfils it."""

    perms_map = {"POST": ["payment.approve"]}

    @extend_schema(request=dict, responses=dict, summary="Attach a Blu deposit to an order (approves it)")
    def post(self, request, pk):
        from django.db import transaction

        from apps.orders.models import Order, OrderStatus
        from apps.payments_sms.matching import confirm_blu
        from apps.payments_sms.models import BluStatus, BluTransaction
        from apps.payments_sms.services import _FULFILLABLE

        try:
            order_id = int(str(request.data.get("order_id") or "").strip().lstrip("#"))
        except ValueError:
            return Response({"detail": "enter the order number", "field": "order_id"}, status=400)
        with transaction.atomic():
            tx = BluTransaction.objects.select_for_update().filter(pk=pk).first()
            if tx is None:
                return Response({"detail": "deposit not found"}, status=404)
            if tx.status != BluStatus.UNMATCHED:
                return Response({"detail": f"this deposit is already {tx.status}", "code": "not_unmatched"}, status=409)
            order = Order.objects.select_for_update().filter(pk=order_id).first()
            if order is None:
                return Response({"detail": f"order #{order_id} not found", "field": "order_id"}, status=404)
            paid = Payment.objects.live().filter(order=order, status=PaymentStatus.APPROVED).first()
            if paid is not None or order.status in (OrderStatus.PAID, OrderStatus.COMPLETED):
                return Response({"detail": f"order #{order.id} is already paid", "code": "already_paid"}, status=409)
            if order.status not in _FULFILLABLE:
                return Response({"detail": f"order #{order.id} is {order.status}", "code": "order_state"}, status=409)
            payment = confirm_blu(order, tx, staff=request.user)
        return Response({"ok": True, "order_id": order.id, "payment_id": payment.id,
                         "message": f"Order #{order.id} approved with this Blu deposit",
                         "message_fa": f"سفارش #{order.id} با این واریز بلو تأیید شد",
                         "deposit": _blu_row(BluTransaction.objects.get(pk=pk))})


class PaymentReceiptInfoView(AdminAPIView):
    """POST /admin/payments/<id>/receipt-info/ — what the receipt says, typed by staff:
    `receipt_amount` + `unit` (rial | toman, explicit) and `receipt_ref` (bank document /
    tracking number). Only feeds the queue warnings; never approves or changes the order."""

    perms_map = {"POST": ["payment.approve"]}

    @extend_schema(request=dict, responses=AdminPendingPaymentSerializer,
                   summary="Record the receipt's amount and bank document number")
    def post(self, request, pk):
        from apps.payments_sms.checks import normalize_ref, parse_amount

        p = Payment.objects.select_related("order", "order__user").filter(pk=pk).first()
        if p is None:
            return Response({"detail": "payment not found"}, status=404)
        unit = request.data.get("unit") or "toman"
        if unit not in ("rial", "toman"):
            return Response({"unit": ["rial or toman"]}, status=400)
        changed = {}
        if "receipt_amount" in request.data:
            try:
                amount = parse_amount(request.data.get("receipt_amount"), unit)
            except ValueError as exc:
                return Response({"receipt_amount": [str(exc)]}, status=400)
            if amount != p.receipt_amount:
                changed["receipt_amount"] = [str(p.receipt_amount) if p.receipt_amount is not None else None,
                                             str(amount) if amount is not None else None]
                p.receipt_amount = amount
        if "receipt_ref" in request.data:
            ref = normalize_ref(request.data.get("receipt_ref"))
            if ref != p.receipt_ref:
                changed["receipt_ref"] = [p.receipt_ref, ref]
                p.receipt_ref = ref
        if changed:
            p.save(update_fields=["receipt_amount", "receipt_ref", "updated_at"])
            write_audit(action="payment.receipt_info", staff=request.user, target=p, detail=changed)
        return Response(AdminPendingPaymentSerializer(p, context={"request": request}).data)


class PaymentDecisionView(AdminAPIView):
    """POST /admin/payments/<id>/(approve|reject) — the manual decision."""

    perms_map = {"POST": ["payment.approve"]}

    @extend_schema(request=dict, responses=AdminPendingPaymentSerializer,
                   summary="Approve or reject a pending payment")
    def post(self, request, pk, action):
        try:
            if action == "approve":
                card = None
                raw = request.data.get("bank_card")
                if raw not in (None, "", 0, "0"):
                    card = BankCard.objects.filter(pk=raw).first()
                payment = approve_payment(pk, actor=request.user, bank_card=card)
            elif action == "reject":
                reason = (request.data.get("reason") or "").strip() or "رد شد"
                payment = reject_payment(pk, reason=reason, actor=request.user)
            else:
                return Response({"detail": "unknown action"}, status=400)
        except Payment.DoesNotExist:
            return Response({"detail": "payment not found"}, status=404)
        except PaymentError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(AdminPendingPaymentSerializer(payment, context={"request": request}).data)


class AccountingView(AdminAPIView):
    perms_map = {"GET": ["accounting.view"]}

    @extend_schema(
        summary="Revenue report — daily / weekly / monthly / custom range (Jalali)",
        responses=dict,
    )
    def get(self, request):
        period = request.query_params.get("period", "monthly")
        now = timezone.now()

        frm = request.query_params.get("from")
        to = request.query_params.get("to")
        if frm or to:
            start = _parse_any_date(frm) or (now - timedelta(days=30))
            end = _parse_any_date(to, end_of_day=True) or now
        elif period == "daily":
            start, end = now - timedelta(days=1), now
        elif period == "weekly":
            start, end = now - timedelta(days=7), now
        else:
            period, start, end = "monthly", now - timedelta(days=30), now

        # voided (deleted by a Super Admin) payments never count — apps/payments_sms/voiding.py
        approved = Payment.objects.live().filter(
            status=PaymentStatus.APPROVED, confirmed_at__gte=start, confirmed_at__lte=end
        )

        totals = approved.aggregate(revenue=Sum("amount"), count=Count("id"))
        by_method = list(
            approved.values("method").annotate(revenue=Sum("amount"), count=Count("id"))
        )
        by_source = list(
            approved.values("order__source").annotate(revenue=Sum("amount"), count=Count("id"))
        )
        by_card = list(
            approved.values("bank_card__card_number").annotate(revenue=Sum("amount"), count=Count("id"))
        )
        # multi-panel: revenue split by which panel each order's plan belongs to
        by_panel = [
            {
                "panel_id": row["order__plan__panel_id"],
                "panel": row["order__plan__panel__name"] or "—",
                "revenue": row["revenue"],
                "count": row["count"],
            }
            for row in approved.values("order__plan__panel_id", "order__plan__panel__name")
            .annotate(revenue=Sum("amount"), count=Count("id"))
            .order_by("-revenue")
        ]
        daily = [
            {
                "date": to_jalali_str(row["day"], "%Y/%m/%d"),
                "date_gregorian": row["day"].isoformat(),
                "revenue": row["revenue"],
                "count": row["count"],
            }
            for row in approved.annotate(day=TruncDate("confirmed_at"))
            .values("day")
            .annotate(revenue=Sum("amount"), count=Count("id"))
            .order_by("day")
        ]

        return Response({
            "period": period,
            "range": {
                "from": to_jalali_str(start, "%Y/%m/%d %H:%M"),
                "to": to_jalali_str(end, "%Y/%m/%d %H:%M"),
                "from_gregorian": start.isoformat(),
                "to_gregorian": end.isoformat(),
            },
            "revenue": totals["revenue"] or 0,
            "transactions": totals["count"] or 0,
            "by_method": by_method,
            "by_source": by_source,
            "by_card": by_card,
            "by_panel": by_panel,
            "daily": daily,
            # v1.26: discount codes on the approved payments of this range (apps/crm/discounts.py)
            "discounts": _discounts(start, end),
            # v1.32: rounded-amount auto-approvals — revenue above already counts what was PAID
            "rounded": _rounded(approved),
        })


def _rounded(approved) -> dict:
    agg = approved.filter(auto_rule="rounded").aggregate(count=Count("id"), shortfall=Sum("shortfall"),
                                                         paid=Sum("amount"))
    return {"count": agg["count"] or 0, "shortfall": str(agg["shortfall"] or 0), "paid": str(agg["paid"] or 0)}


def _discounts(start, end) -> dict:
    from apps.crm.discounts import totals

    t = totals(start, end)
    return {"uses": t["uses"], "discount": str(t["discount"]), "revenue": str(t["revenue"]),
            "by_code": [{**r, "discount": str(r["discount"]), "revenue": str(r["revenue"])} for r in t["by_code"]]}


def _parse_any_date(value, *, end_of_day=False):
    """Accept an ISO (YYYY-MM-DD) or Jalali (YYYY/MM/DD) date string."""
    if not value:
        return None
    value = value.strip()
    try:
        if "/" in value:  # Jalali YYYY/MM/DD
            y, m, d = (int(x) for x in value.split("/"))
            g = jdatetime.date(y, m, d).togregorian()
            y, m, d = g.year, g.month, g.day
        else:  # Gregorian YYYY-MM-DD
            y, m, d = (int(x) for x in value.split("-"))
        dt = timezone.datetime(y, m, d)
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59)
        return timezone.make_aware(dt)
    except (ValueError, TypeError):
        return None


class SmsLogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /admin/sms-log/ — every SMS the phones forwarded (newest first), with
    the sender, the parsed amount, the matched order or the reason it did not
    match. ?matched=1|0|mismatch filters."""

    authentication_classes = _AUTH
    permission_classes = [StaffPermission]
    perms_map = {"GET": ["payment.view"]}

    def get_serializer_class(self):
        from ..serializers import AdminSmsLogSerializer

        return AdminSmsLogSerializer

    def get_queryset(self):
        from apps.payments_sms.models import SmsMessage

        qs = (SmsMessage.objects.select_related("device", "sms_source", "matched_order", "mismatch_order")
              .order_by("-received_at", "-id"))
        m = self.request.query_params.get("matched")
        if m in ("1", "true"):
            qs = qs.filter(matched_order__isnull=False)
        elif m in ("0", "false"):
            qs = qs.filter(matched_order__isnull=True)
        elif m == "mismatch":                 # unit / amount mismatches waiting for a manual check
            from django.db.models import Q

            qs = qs.filter(Q(mismatch_order__isnull=False) | Q(note__startswith="amount mismatch"), matched_order__isnull=True)
        return qs



def _ids(raw) -> list[int]:
    out = []
    for x in (raw or [])[:500]:
        try:
            v = int(x)
        except (TypeError, ValueError):
            continue
        if v not in out:
            out.append(v)
    return out


def _tx_search(term: str):
    """TX-000123 / tx123 / #123 / 123 → that number (or id); anything else → user, name,
    phone, account name, gateway reference."""
    import re

    from django.db.models import Q

    t = term.strip()
    m = re.fullmatch(r"(?i)(?:tx-?|#)?\s*0*(\d{1,9})", t)
    q = Q()
    if m:
        n = int(m.group(1))
        q |= Q(number=n) | Q(pk=n) | Q(order_id=n)
        if t.lower().startswith("tx"):
            return Q(number=n)
    return (q | Q(order__user__username__icontains=t) | Q(order__user__name__icontains=t)
            | Q(order__user__phone__icontains=t) | Q(order__requested_account_name__icontains=t)
            | Q(order__service__panel_username__icontains=t)
            | Q(gateway_ref__icontains=t))


CSV_HEAD = {
    "fa": ["شماره تراکنش", "تاریخ", "مبلغ (تومان)", "وضعیت", "روش", "کاربر", "نام", "پلن", "نوع سفارش", "منبع",
           "کارت", "تأییدکننده", "تاریخ تأیید", "شماره سفارش", "دلیل رد", "حذف‌شده", "دلیل حذف"],
    "en": ["Transaction", "Date", "Amount (Toman)", "Status", "Method", "User", "Name", "Plan", "Order type", "Source",
           "Card", "Confirmed by", "Confirmed at", "Order", "Reject reason", "Deleted", "Delete reason"],
}


def _transactions_csv(qs, lang: str):
    import csv
    import io

    from django.http import HttpResponse

    buf = io.StringIO()
    buf.write("\ufeff")                        # Excel opens UTF-8 (Persian) correctly
    w = csv.writer(buf)
    w.writerow(CSV_HEAD[lang])
    for p in qs.iterator(chunk_size=500):
        o = p.order
        confirmer = (("Blu system" if p.method == "blu_auto" else "SMS system") if p.confirmed_by == "system" else
                     (p.confirmed_by_staff.username if p.confirmed_by_staff_id else (p.confirmed_by or "")))
        w.writerow([
            p.tx_number, to_jalali_str(p.created_at, "%Y/%m/%d %H:%M"), int(p.amount), p.status, p.method,
            o.user.username, o.user.name or "", (o.plan.name_en if lang == "en" else o.plan.name_fa) if o.plan_id else "",
            o.type, o.source, p.bank_card.card_number if p.bank_card_id else "", confirmer,
            to_jalali_str(p.confirmed_at, "%Y/%m/%d %H:%M") if p.confirmed_at else "", o.id, p.reject_reason or "",
            to_jalali_str(p.voided_at, "%Y/%m/%d %H:%M") if p.voided_at else "", p.void_reason or "",
        ])
    resp = HttpResponse(buf.getvalue().encode("utf-8"), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="transactions-{timezone.localdate().isoformat()}.csv"'
    return resp
