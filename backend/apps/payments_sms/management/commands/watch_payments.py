"""watch_payments (v1.48, v1.49.1) — follow the next real payments of OUR store; alert staff when one is not matched
automatically.

    python manage.py watch_payments [--count 3] [--want-order] [--max-count N] [--grace 180] [--receipt-wait 1800]
                                    [--timeout 86400]

Read-only except for the alerts. Starts from "now". Every payment ends in one of three outcomes:

  AUTO    matched automatically — an SMS / Blu deposit approved an order (sms_auto / blu_auto, incl. the rounded rule) or
          an agency payment; a Blu deposit for an order that was already paid (duplicate / linked); a receipt whose
          payment was approved.
  REVIEW  not matched automatically — the deposit is held for a person (an `sms_mismatch` / `blu_mismatch` payment:
          amount differs, rounded rule without evidence, ambiguous…), alerted at once, whether or not staff approve it
          later. (v1.49.1: before, a review approved by staff within the grace time was counted as matched.)
  FAIL    no match at all after --grace seconds (the SMS log / Blu note says why), or a receipt still pending after
          --receipt-wait seconds. A receipt rejected by staff is counted with no alert.

One payment = one order: a receipt and the deposit that confirmed it count once.
--want-order: after --count payments, keep watching (up to --max-count) until one CUSTOMER order matched automatically.
REVIEW / FAIL → `alert_staff(perm="payment.view")` (staff DMs with a linked Telegram id, else the backup chat; deduped);
a short summary at the end (silent when all AUTO). Only the default tenant: a store's payment data never reaches our staff.
Exit code 0 = all AUTO, 2 = at least one REVIEW / FAIL, 1 = timed out.
"""
from __future__ import annotations

import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection
from django.utils import timezone

POLL_SECONDS = 15
AUTO, REVIEW, FAIL = "AUTO", "REVIEW", "FAIL"


class Command(BaseCommand):
    help = "Follow the next real payments (SMS, Blu, receipt) of our store; alert staff when one is not matched automatically."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=3, help="payments to follow (default 3)")
        parser.add_argument("--want-order", action="store_true",
                            help="also wait (up to --max-count) for one customer order matched automatically")
        parser.add_argument("--max-count", type=int, default=0, help="with --want-order: stop after this many (default count+2)")
        parser.add_argument("--grace", type=int, default=180, help="seconds a deposit may take to match (default 180)")
        parser.add_argument("--receipt-wait", type=int, default=1800,
                            help="seconds a receipt may stay unconfirmed (default 1800)")
        parser.add_argument("--timeout", type=int, default=86400, help="give up after this many seconds (default 1 day)")

    def handle(self, *args, **opt):
        from apps.tenancy import context

        with context.tenant_context(context.default_tenant_id()):
            return self._run(opt)

    # ------------------------------------------------------------------ loop
    def _run(self, opt):
        self.start = timezone.now()
        self.count, self.grace, self.receipt_wait = opt["count"], opt["grace"], opt["receipt_wait"]
        self.want_order = opt["want_order"]
        self.limit = max(self.count, opt["max_count"] or self.count + 2) if self.want_order else self.count
        deadline = self.start + timedelta(seconds=opt["timeout"])
        self.done: dict[str, tuple[str, str, bool]] = {}   # key → (outcome, line, customer order auto-matched)
        self.orders: set[int] = set()                       # orders already counted
        extra = f", until a customer order matches automatically (at most {self.limit})" if self.want_order else ""
        self._say(f"watching the next {self.count} payment(s) of our store{extra} from {self._t(self.start)}")
        while not self._enough():
            if timezone.now() > deadline:
                self._finish(timed_out=True)
                raise SystemExit(1)
            if not connection.in_atomic_block:           # long run: drop a stale MySQL connection between polls
                close_old_connections()
            self._sms()
            self._blu()
            self._receipts()
            if not self._enough():
                time.sleep(POLL_SECONDS)
        if self._finish():
            raise SystemExit(2)

    def _enough(self) -> bool:
        n = len(self.done)
        if n >= self.limit:
            return True
        if n < self.count:
            return False
        return not self.want_order or any(c for _, _, c in self.done.values())

    def _record(self, key: str, outcome: str, line: str, order_id: int | None = None, *, customer: bool = False) -> None:
        if key in self.done or self._enough():
            return
        if order_id and order_id in self.orders:
            return
        if order_id:
            self.orders.add(order_id)
        self.done[key] = (outcome, line, outcome == AUTO and customer)
        n = len(self.done)
        self._say(f"[{n}] {outcome:<6} {line}", ok=outcome == AUTO)
        if outcome != AUTO:
            from apps.common.staff_alert import alert_staff

            head = "⚠️ پرداخت خودکار تطبیق نشد — بررسی دستی" if outcome == REVIEW else "⚠️ پرداخت تطبیق داده نشد"
            alert_staff(f"{head} ({n})\n{line}", perm="payment.view", dedupe_key=f"watch_payments:{key}", ttl=86400)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _review_line(p) -> str:
        """A mismatch payment: why it was held, and whether staff already approved it."""
        why = (p.auto_reason or {}).get("why_not") or (p.auto_reason or {}).get("rule") or "amount mismatch"
        state = {"approved": "approved by staff", "rejected": "rejected by staff"}.get(p.status, "waiting in the queue")
        return f"held for review ({why}, invoice {p.order.amount_unique:,.0f} T) · {state}"

    def _order_outcome(self, key: str, what: str, order_id: int, mismatch_method: str) -> bool:
        """A deposit linked to a customer order. Returns True when it was recorded."""
        from apps.payments_sms.models import Payment

        p = Payment.objects.select_related("order").filter(order_id=order_id).first()
        if p is not None and p.method == mismatch_method:
            self._record(key, REVIEW, f"{what} → order #{order_id} {self._review_line(p)}", order_id)
        else:
            self._record(key, AUTO, f"{what} → order #{order_id} ({getattr(p, 'method', '?')})", order_id, customer=True)
        return True

    # ------------------------------------------------------------------ sources
    def _sms(self):
        from apps.agency.models import AgencyPayment
        from apps.payments_sms.models import Payment, PaymentMethod, SmsMessage

        cutoff = timezone.now() - timedelta(seconds=self.grace)
        for m in SmsMessage.objects.filter(uploaded_at__gte=self.start, parsed_amount__isnull=False).order_by("id"):
            key = f"sms:{m.pk}"
            if key in self.done:
                continue
            what = f"SMS #{m.pk} · {m.parsed_amount:,.0f} T · {self._t(m.received_at)}"
            held = Payment.objects.select_related("order").filter(sms_message=m, method=PaymentMethod.SMS_MISMATCH).first()
            if held is not None:
                self._record(key, REVIEW, f"{what} → order #{held.order_id} {self._review_line(held)}", held.order_id)
            elif m.matched_order_id:
                self._order_outcome(key, what, m.matched_order_id, PaymentMethod.SMS_MISMATCH)
            elif AgencyPayment.objects.filter(sms_message=m).exists():
                self._record(key, AUTO, f"{what} → agency payment")
            elif m.uploaded_at <= cutoff:
                self._record(key, FAIL, f"{what} → no match: {m.note or '—'}")

    def _blu(self):
        from apps.payments_sms.models import BluStatus, BluTransaction, Payment, PaymentMethod

        cutoff = timezone.now() - timedelta(seconds=self.grace)
        rows = (BluTransaction.objects.filter(received_at__gte=self.start, amount_toman__isnull=False)
                .exclude(status=BluStatus.IGNORED).order_by("id"))          # ignored = not a deposit
        for tx in rows:
            key = f"blu:{tx.pk}"
            if key in self.done:
                continue
            what = f"Blu #{tx.pk} · {tx.amount_toman:,.0f} T · {self._t(tx.occurred_at)}"
            held = Payment.objects.select_related("order").filter(blu_transaction=tx, method=PaymentMethod.BLU_MISMATCH).first()
            if held is not None:
                self._record(key, REVIEW, f"{what} → order #{held.order_id} {self._review_line(held)}", held.order_id)
            elif tx.status in (BluStatus.LINKED, BluStatus.DUPLICATE):
                target = f"order #{tx.matched_order_id}" if tx.matched_order_id else "an agency payment"
                self._record(key, AUTO, f"{what} → {tx.status} ({target} already paid)", tx.matched_order_id)
            elif tx.status == BluStatus.MATCHED and tx.matched_order_id:
                self._order_outcome(key, what, tx.matched_order_id, PaymentMethod.BLU_MISMATCH)
            elif tx.status == BluStatus.MATCHED:
                self._record(key, AUTO, f"{what} → agency payment ({tx.match_note[:80] or 'matched'})")
            elif tx.received_at <= cutoff:
                self._record(key, FAIL, f"{what} → still unmatched: {tx.match_note or '—'}")

    def _receipts(self):
        from apps.common.models import AuditLog
        from apps.payments_sms.models import Payment, PaymentStatus

        ids = (AuditLog.objects.filter(action="payment.receipt_uploaded", target_type="Payment",
                                       created_at__gte=self.start).values_list("target_id", "created_at"))
        cutoff = timezone.now() - timedelta(seconds=self.receipt_wait)
        for pid, at in ids:
            key = f"receipt:{pid}"
            if key in self.done or not pid:
                continue
            p = Payment.objects.filter(pk=pid).first()       # tenant-scoped: a store's receipt is not ours
            if p is None:
                continue
            what = f"receipt {p.tx_number} · order #{p.order_id} · {p.amount:,.0f} T"
            if p.status == PaymentStatus.APPROVED:
                self._record(key, AUTO, f"{what} → approved ({p.method})", p.order_id, customer=True)
            elif p.status == PaymentStatus.REJECTED:
                self._record(key, AUTO, f"{what} → rejected by staff: {p.reject_reason or '—'}", p.order_id)
            elif at <= cutoff:
                self._record(key, FAIL, f"{what} → still unconfirmed after {self.receipt_wait // 60} min", p.order_id)

    # ------------------------------------------------------------------ output
    def _finish(self, *, timed_out: bool = False) -> int:
        from apps.common.staff_alert import alert_staff

        n = len(self.done)
        counts = {k: sum(1 for o, _, _ in self.done.values() if o == k) for k in (AUTO, REVIEW, FAIL)}
        bad = counts[REVIEW] + counts[FAIL]
        orders = sum(1 for _, _, c in self.done.values() if c)
        head = (f"watch_payments: timed out — {n} seen" if timed_out
                else f"watch_payments: {n} payment(s) — {counts[AUTO]} automatic, {counts[REVIEW]} needed review, "
                     f"{counts[FAIL]} not matched; customer orders matched automatically: {orders}")
        self._say(head, ok=not bad and not timed_out)
        mark = {AUTO: "✅ ", REVIEW: "🟡 ", FAIL: "❌ "}
        lines = "\n".join(mark[o] + line for o, line, _ in self.done.values())
        alert_staff(f"پایش پرداخت‌ها تمام شد\n{head}\n{lines}".strip(), perm="payment.view", silent=not bad)
        return bad

    def _t(self, dt) -> str:
        from apps.common.jalali import TZ

        return timezone.localtime(dt, TZ).strftime("%H:%M:%S") if dt else "—"

    def _say(self, text: str, ok: bool = True) -> None:
        stamp = self._t(timezone.now())
        self.stdout.write((self.style.SUCCESS if ok else self.style.ERROR)(f"{stamp} {text}"))
        self.stdout.flush()
