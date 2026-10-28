"""Panel → Discount codes (v1.26). One list for the codes made here and the win-back
codes of the retention module (apps.crm) — the same model, the same rules
(apps/crm/discounts.py). Codes are never deleted (orders keep pointing at them):
"disable" switches them off. Every create / edit / disable is in the audit log.

GET    discounts/                 list (+ uses, customers, discount, revenue per code) ?kind ?status ?search
POST   discounts/                 create
GET    discounts/<id>/            one code
PATCH  discounts/<id>/            edit (win-back codes: on/off, end, name, note only)
GET    discounts/<id>/report/     its orders
GET    discounts/summary/         totals for the page header
GET    discounts/customers/?q=    customer search (username / name / phone / Telegram)
GET    discounts/options/         plans to pick from
"""
from __future__ import annotations

import re
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import User
from apps.common.models import write_audit
from apps.crm import discounts as D
from apps.crm.models import DiscountCode
from apps.plans.models import Plan

from .base import AdminViewSet

CODE_RE = re.compile(r"^[A-Z0-9_-]{3,32}$")
WINBACK_EDITABLE = {"is_active", "expires_at", "name", "note"}
AUDIT_FIELDS = ("code", "name", "is_active", "starts_at", "expires_at", "discount_type", "percent", "max_discount",
                "amount_off", "audience", "first_purchase_only", "applies_to", "max_uses", "max_uses_per_customer",
                "min_order_amount", "note")


def _s(v):
    return str(v) if isinstance(v, Decimal) else v


def _sd(d: dict) -> dict:
    return {k: _s(v) for k, v in d.items()}


def status_of(dc: DiscountCode, held: int | None = None) -> str:
    now = timezone.now()
    if not dc.is_active:
        return "disabled"
    if dc.expires_at and dc.expires_at <= now:
        return "expired"
    if dc.kind == "winback" and dc.used_at:
        return "used_up"
    if dc.starts_at and dc.starts_at > now:
        return "scheduled"
    if dc.max_uses is not None and (held if held is not None else D.held_orders(dc).count()) >= dc.max_uses:
        return "used_up"
    return "active"


def _user_row(u) -> dict:
    return {"id": u.id, "username": u.username, "name": u.name, "phone": u.phone,
            "telegram_username": u.telegram_username or ""}


class DiscountCodeSerializer(serializers.ModelSerializer):
    customer_ids = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    plan_ids = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    code = serializers.CharField(required=False, allow_blank=True, max_length=40)

    class Meta:
        model = DiscountCode
        fields = ("id", "code", "kind", "name", "is_active", "starts_at", "expires_at", "discount_type", "percent",
                  "max_discount", "amount_off", "audience", "first_purchase_only", "applies_to", "max_uses",
                  "max_uses_per_customer", "min_order_amount", "note", "created_by", "created_at", "updated_at",
                  "customer_ids", "plan_ids", "used_at")
        read_only_fields = ("kind", "created_by", "created_at", "updated_at", "used_at")

    def to_representation(self, dc):
        data = super().to_representation(dc)
        st = D.stats(dc)
        data.update({
            "customers": [_user_row(u) for u in dc.customers.all()[:200]],
            "plans": [{"id": p.id, "name_fa": p.name_fa, "name_en": p.name_en} for p in dc.plans.all()],
            "owner": _user_row(dc.user) if dc.user_id else None,
            "status": status_of(dc, st["held"]),
            "stats": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in st.items()},
        })
        return data

    def validate_code(self, v):
        v = D.normalize(v)
        if v and not CODE_RE.match(v):
            raise serializers.ValidationError("3–32 English letters, digits, _ or -")
        if v and DiscountCode.objects.filter(code=v).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("this code already exists")
        return v

    def validate(self, attrs):
        inst = self.instance
        if inst is not None and inst.kind == "winback":
            extra = set(attrs) - WINBACK_EDITABLE - {"customer_ids", "plan_ids"}
            if extra or "customer_ids" in attrs or "plan_ids" in attrs:
                raise serializers.ValidationError(
                    {"kind": "a win-back code can only be switched on/off, given another end date, name or note"})
        get = lambda k: attrs.get(k, getattr(inst, k, None) if inst else None)  # noqa: E731
        dtype = get("discount_type") or "percent"
        if dtype == "percent":
            p = get("percent") or 0
            if not 1 <= int(p) <= 100:
                raise serializers.ValidationError({"percent": "1–100"})
            if get("max_discount") is not None and Decimal(get("max_discount")) <= 0:
                raise serializers.ValidationError({"max_discount": "must be more than 0"})
        else:
            if not get("amount_off") or Decimal(get("amount_off")) <= 0:
                raise serializers.ValidationError({"amount_off": "a fixed discount needs an amount"})
        s, e = get("starts_at"), get("expires_at")
        if s and e and e <= s:
            raise serializers.ValidationError({"expires_at": "the end must be after the start"})
        for k in ("max_uses", "max_uses_per_customer"):
            if attrs.get(k) == 0:
                raise serializers.ValidationError({k: "at least 1 (empty = unlimited)"})
        if get("min_order_amount") is not None and Decimal(get("min_order_amount")) < 0:
            raise serializers.ValidationError({"min_order_amount": "cannot be negative"})
        audience = get("audience") or "all"
        if (inst is None or inst.kind != "winback") and audience == "selected":
            ids = attrs.get("customer_ids") if "customer_ids" in attrs else (list(inst.customers.values_list("id", flat=True)) if inst else [])
            if not ids:
                raise serializers.ValidationError({"customer_ids": "pick at least one customer"})
        if "customer_ids" in attrs:
            found = set(User.objects.filter(pk__in=attrs["customer_ids"]).values_list("id", flat=True))
            if found != set(attrs["customer_ids"]):
                raise serializers.ValidationError({"customer_ids": "unknown customer"})
        if "plan_ids" in attrs:
            found = set(Plan.objects.filter(pk__in=attrs["plan_ids"]).values_list("id", flat=True))
            if found != set(attrs["plan_ids"]):
                raise serializers.ValidationError({"plan_ids": "unknown plan"})
        return attrs

    def _m2m(self, dc, attrs):
        if "customer_ids" in attrs:
            dc.customers.set(attrs["customer_ids"] if dc.audience == "selected" else [])
        elif dc.audience != "selected":
            dc.customers.clear()
        if "plan_ids" in attrs:
            dc.plans.set(attrs["plan_ids"])

    @transaction.atomic
    def create(self, attrs):
        m2m = {k: attrs.pop(k) for k in ("customer_ids", "plan_ids") if k in attrs}
        if not attrs.get("code"):
            attrs["code"] = D.random_code()
        req = self.context["request"]
        dc = DiscountCode.objects.create(kind="campaign", created_by=getattr(req.user, "username", "")[:64], **attrs)
        self._m2m(dc, m2m)
        write_audit(action="discount.created", staff=req.user, target=dc,
                    detail={"code": dc.code, **{k: _j(getattr(dc, k)) for k in AUDIT_FIELDS},
                            "customers": list(dc.customers.values_list("id", flat=True)),
                            "plans": list(dc.plans.values_list("id", flat=True))})
        return dc

    @transaction.atomic
    def update(self, dc, attrs):
        m2m = {k: attrs.pop(k) for k in ("customer_ids", "plan_ids") if k in attrs}
        before = {k: _j(getattr(dc, k)) for k in AUDIT_FIELDS}
        before_c = sorted(dc.customers.values_list("id", flat=True))
        before_p = sorted(dc.plans.values_list("id", flat=True))
        if "code" in attrs and not attrs["code"]:
            attrs.pop("code")
        for k, v in attrs.items():
            setattr(dc, k, v)
        dc.save()
        self._m2m(dc, m2m)
        after = {k: _j(getattr(dc, k)) for k in AUDIT_FIELDS}
        changes = {k: [before[k], after[k]] for k in AUDIT_FIELDS if before[k] != after[k]}
        c, p = sorted(dc.customers.values_list("id", flat=True)), sorted(dc.plans.values_list("id", flat=True))
        if c != before_c:
            changes["customers"] = [before_c, c]
        if p != before_p:
            changes["plans"] = [before_p, p]
        if changes:
            act = ("discount.disabled" if changes.get("is_active") == [True, False] else
                   "discount.enabled" if changes.get("is_active") == [False, True] else "discount.updated")
            write_audit(action=act, staff=self.context["request"].user, target=dc,
                        detail={"code": dc.code, "changes": changes})
        return dc


def _j(v):
    if v is None or isinstance(v, (bool, int, str)):
        return v
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


class DiscountCodeViewSet(AdminViewSet):
    serializer_class = DiscountCodeSerializer
    perms_map = {"GET": ["discounts.view"], "*": ["discounts.manage"]}
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = DiscountCode.objects.select_related("user").prefetch_related("customers", "plans").order_by("-created_at", "-id")
        q = self.request.query_params
        if q.get("kind") in ("winback", "campaign"):
            qs = qs.filter(kind=q["kind"])
        if q.get("search"):
            s = q["search"].strip()
            qs = qs.filter(Q(code__icontains=s) | Q(name__icontains=s) | Q(user__username__icontains=s))
        st = q.get("status")
        if st:
            now = timezone.now()
            if st == "disabled":
                qs = qs.filter(is_active=False)
            elif st == "expired":
                qs = qs.filter(is_active=True, expires_at__lte=now)
            elif st == "scheduled":
                qs = qs.filter(is_active=True, starts_at__gt=now)
            elif st == "active":
                qs = qs.filter(is_active=True).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).filter(
                    Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        return qs

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        dc = self.get_object()
        from apps.orders.models import Order

        rows = []
        for o in Order.objects.filter(discount_code=dc).select_related("user", "plan", "payment").order_by("-created_at")[:300]:
            pay = getattr(o, "payment", None)
            rows.append({"id": o.id, "created_at": o.created_at, "status": o.status, "type": o.type,
                         "user": o.user.username, "user_id": o.user_id,
                         "plan": o.plan.name_fa if o.plan else "", "plan_en": o.plan.name_en if o.plan else "",
                         "original": _s(o.original_amount), "discount": _s(o.discount_amount), "final": _s(o.amount),
                         "to_pay": _s(o.amount_unique),
                         "paid": _s(pay.amount) if pay and pay.status == "approved" and not pay.voided_at else None,
                         "payment_status": pay.status if pay else None, "source": o.source})
        st = D.stats(dc)
        return Response({"code": DiscountCodeSerializer(dc, context={"request": request}).data, "orders": rows,
                         "stats": _sd(st)})

    @action(detail=False, methods=["get"])
    def summary(self, request):
        now = timezone.now()
        live = DiscountCode.objects.filter(is_active=True).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        t = D.totals(now - timezone.timedelta(days=36500), now + timezone.timedelta(days=1))
        return Response({"active": live.filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now)).count(),
                         "scheduled": live.filter(starts_at__gt=now).count(), "total": DiscountCode.objects.count(),
                         "uses": t["uses"], "discount": _s(t["discount"]), "revenue": _s(t["revenue"])})

    @action(detail=False, methods=["get"])
    def customers(self, request):
        q = (request.query_params.get("q") or "").strip().lstrip("@")
        if len(q) < 2:
            return Response({"results": []})
        qs = User.objects.filter(deleted_at__isnull=True).filter(
            Q(username__icontains=q) | Q(name__icontains=q) | Q(phone__icontains=q) | Q(telegram_username__icontains=q)
        ).order_by("username")[:20]
        return Response({"results": [_user_row(u) for u in qs]})

    @action(detail=False, methods=["get"])
    def options(self, request):
        plans = Plan.objects.select_related("panel").order_by("-is_active", "sort_order", "id")
        return Response({"plans": [{"id": p.id, "name_fa": p.name_fa, "name_en": p.name_en, "is_active": p.is_active,
                                    "panel": p.panel.name if p.panel_id else ""} for p in plans]})
