from rest_framework import serializers

from apps.plans.models import Plan

from .models import Order, OrderType
from .services import AccountNameRefused, DiscountCodeRefused, OrderError, RenewalWaiting, SaleUnavailable, create_order


def manual_info(order) -> dict | None:
    """v1.38 the «دستی» tag: the staff invoice behind an order (None = a normal order)."""
    inv = getattr(order, "manual_invoice", None) if getattr(order, "manual_invoice_id", None) else None
    if inv is None:
        return None
    return {"id": inv.id, "number": inv.number, "mode": inv.mode, "title": inv.title, "service_action": inv.service_action,
            "paid_at": inv.paid_at, "created_by": inv.created_by.username if inv.created_by_id else None}


class OrderSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source="plan.name_fa", read_only=True)
    plan_name_en = serializers.CharField(source="plan.name_en", read_only=True, default="")
    payment_status = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()
    receipt_url = serializers.SerializerMethodField()
    reject_reason = serializers.SerializerMethodField()
    tx_number = serializers.SerializerMethodField()
    manual = serializers.SerializerMethodField()
    # v1.42.1: paid but the panel refused the account — the customer only sees «در حال آماده‌سازی» (never the error)
    preparing = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id", "type", "status", "plan", "plan_name", "plan_name_en", "service",
            "requested_account_name", "custom_volume_gb",
            "amount", "discount_amount", "original_amount", "discount_code_text", "amount_unique", "unique_expire_at",
            "payment_status", "payment_method", "receipt_url",
            "reject_reason", "source", "created_at", "needs_new_name", "tx_number", "manual",
            "preparing",
        )
        read_only_fields = fields

    def get_preparing(self, obj) -> bool:
        return obj.status == "paid" and obj.provision_failed_at is not None

    def get_manual(self, obj) -> dict | None:
        m = manual_info(obj)
        return {k: m[k] for k in ("number", "title", "paid_at")} if m else None

    def get_payment_status(self, obj) -> str | None:
        pay = getattr(obj, "payment", None)
        return pay.status if pay else None

    def get_payment_method(self, obj) -> str | None:
        pay = getattr(obj, "payment", None)
        return pay.method if pay else None

    def get_receipt_url(self, obj) -> str | None:
        # owner-checked endpoint (ReceiptFileView), never a public media path
        pay = getattr(obj, "payment", None)
        return f"/api/v1/payments/{pay.id}/receipt/" if pay and pay.receipt_image else None

    def get_tx_number(self, obj) -> str | None:
        pay = getattr(obj, "payment", None)
        return pay.tx_number if pay else None

    def get_reject_reason(self, obj) -> str:
        pay = getattr(obj, "payment", None)
        return pay.reject_reason if pay and pay.status == "rejected" else ""


class OrderCreateSerializer(serializers.Serializer):
    # active plans; a renewal may also use the service's own retired plan when staff marked it renewable
    # (create_order / plan_renews decide)
    plan = serializers.PrimaryKeyRelatedField(queryset=Plan.objects.all())
    type = serializers.ChoiceField(choices=OrderType.choices, default=OrderType.NEW)
    requested_account_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    custom_volume_gb = serializers.IntegerField(required=False, min_value=1)
    service = serializers.IntegerField(required=False)
    discount_code = serializers.CharField(required=False, allow_blank=True, max_length=40)
    lang = serializers.ChoiceField(choices=("fa", "en"), required=False, default="fa")
    # accepted once at sign-up (User.terms_accepted_at); kept only so older
    # clients that still send it don't break
    terms_accepted = serializers.BooleanField(write_only=True, required=False)

    def validate(self, attrs):
        """PasarGuard's username rule (apps/panel/account_names.py) for a new service — the reason in the customer's
        language + a fixed suggestion; then "taken" in our DB (the panel itself is asked in create_order)."""
        from apps.panel.account_names import AccountNameInvalid, validate
        from apps.panel.models import Service

        if attrs.get("type", OrderType.NEW) == OrderType.NEW:
            lang = attrs.get("lang", "fa")
            try:
                name = validate(attrs.get("requested_account_name"))
            except AccountNameInvalid as exc:
                raise serializers.ValidationError({"requested_account_name": [exc.message(lang)],
                                                   "suggestion": exc.suggestion or ""})
            if Service.objects.filter(panel_username__iexact=name).exists():
                raise serializers.ValidationError({"requested_account_name": [
                    "This account name is taken — pick another." if lang == "en" else "این نام اکانت گرفته شده است؛ نام دیگری انتخاب کنید."]})
            attrs["requested_account_name"] = name
        elif not attrs["plan"].is_active and attrs.get("type") != OrderType.RENEW:
            raise serializers.ValidationError({"plan": ["plan not found or inactive"]})
        return attrs

    def create(self, validated):
        request = self.context["request"]
        try:
            return create_order(
                user=request.user,
                plan_id=validated["plan"].id,
                order_type=validated["type"],
                requested_account_name=validated.get("requested_account_name"),
                custom_volume_gb=validated.get("custom_volume_gb"),
                service_id=validated.get("service"),
                source=self.context.get("source", "site"),
                discount_code=validated.get("discount_code") or None,
            )
        except DiscountCodeRefused as exc:
            # v1.26: the reason in the customer's language + a code the client can map
            raise serializers.ValidationError({"discount_code": [exc.message(validated.get("lang", "fa"))],
                                               "discount_error": exc.code})
        except RenewalWaiting as exc:
            # a paid renewal of this service still waits — one at a time
            raise serializers.ValidationError({"detail": exc.message(validated.get("lang", "fa")), "code": exc.code})
        except AccountNameRefused as exc:
            raise serializers.ValidationError({"requested_account_name": [exc.message(validated.get("lang", "fa"))],
                                               "suggestion": exc.suggestion or ""})
        except SaleUnavailable as exc:
            raise serializers.ValidationError({"detail": exc.message(validated.get("lang", "fa")), "code": exc.code})
        except OrderError as exc:
            raise serializers.ValidationError(str(exc))
