"""watch_payments (v1.48) — follow the next N real payments of OUR store and alert staff when one does not match.

    python manage.py watch_payments [--count 3] [--grace 180] [--receipt-wait 1800] [--timeout 86400]

Read-only except for the alerts. Starts from "now" and follows three kinds of payment:

  SMS deposit  — an SmsMessage with a deposit amount. OK once it matched an order (matched_order) or an agency payment;
                 after --grace seconds without a match it FAILED (the SMS log note says why).
  Blu deposit  — a BluTransaction deposit. OK when matched / linked / duplicate (an already paid order); still
                 «unmatched» after --grace seconds = FAILED. «ignored» rows are not payments.
  Receipt      — a customer receipt upload (audit `payment.receipt_uploaded`). OK when its payment is approved;
                 rejected by staff = counted, no alert; still pending after --receipt-wait seconds = FAILED.

One payment = one order: a receipt and the SMS / Blu deposit that confirmed it count once.
Each failure → `alert_staff(perm="payment.view")` (staff DMs with a linked Telegram id, else the backup chat; deduped);
a short silent summary at the end. Only the default tenant: a store's payment data never reaches our staff.
Exit code 0 = all matched, 2 = at least one failed, 1 = timed out.
"""
from __future__ import annotations

import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection
from django.utils import timezone

POLL_SECONDS = 15


class Command(BaseCommand):
    help = "Follow the next N real payments (SMS, Blu, receipt) of our store and alert staff if one does not match."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=3, help="payments to follow (default 3)")
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
        deadline = self.start + timedelta(seconds=opt["timeout"])
        self.done: dict[str, tuple[bool, str]] = {}      # key → (ok, line)
        self.orders: set[int] = set()                     # orders already counted
        self._say(f"watching the next {self.count} payment(s) of our store from {self._t(self.start)}")
        while len(self.done) < self.count:
            if timezone.now() > deadline:
                self._finish(timed_out=True)
                raise SystemExit(1)
            if not connection.in_atomic_block:         # long run: drop a stale MySQL connection between polls
                close_old_connections()
            self._sms()
            self._blu()
            self._receipts()
            if len(self.done) < self.count:
                time.sleep(POLL_SECONDS)
        failed = self._finish()
        if failed:
            raise SystemExit(2)

    def _record(self, key: str, ok: bool, line: str, order_id: int | None = None) -> None:
        if key in self.done or len(self.done) >= self.count:
            return
        if order_id and order_id in self.orders:
            return
        if order_id:
            self.orders.add(order_id)
        self.done[key] = (ok, line)
        n = len(self.done)
        self._say(f"[{n}/{self.count}] {'OK  ' if ok else 'FAIL'} {line}", ok=ok)
        if not ok:
            from apps.common.staff_alert import alert_staff

            alert_staff(f"⚠️ پرداخت تطبیق داده نشد ({n}/{self.count})\n{line}", perm="payment.view",
                        dedupe_key=f"watch_payments:{key}", ttl=86400)

    # ------------------------------------------------------------------ sources
    def _sms(self):
        from apps.agency.models import AgencyPayment
        from apps.payments_sms.models import SmsMessage

        cutoff = timezone.now() - timedelta(seconds=self.grace)
        for m in SmsMessage.objects.filter(uploaded_at__gte=self.start, parsed_amount__isnull=False).order_by("id"):
            key = f"sms:{m.pk}"
            if key in self.done:
                continue
            what = f"SMS #{m.pk} · {m.parsed_amount:,.0f} T · {self._t(m.received_at)}"
            if m.matched_order_id:
                self._record(key, True, f"{what} → order #{m.matched_order_id}", m.matched_order_id)
            elif AgencyPayment.objects.filter(sms_message=m).exists():
                self._record(key, True, f"{what} → agency payment")
            elif m.uploaded_at <= cutoff:
                self._record(key, False, f"{what} → no match: {m.note or '—'}")

    def _blu(self):
        from apps.payments_sms.models import BluStatus, BluTransaction

        cutoff = timezone.now() - timedelta(seconds=self.grace)
        rows = (BluTransaction.objects.filter(received_at__gte=self.start, amount_toman__isnull=False)
                .exclude(status=BluStatus.IGNORED).order_by("id"))          # ignored = not a deposit
        for tx in rows:
            key = f"blu:{tx.pk}"
            if key in self.done:
                continue
            what = f"Blu #{tx.pk} · {tx.amount_toman:,.0f} T · {self._t(tx.occurred_at)}"
            if tx.status in (BluStatus.MATCHED, BluStatus.LINKED, BluStatus.DUPLICATE):
                target = f"order #{tx.matched_order_id}" if tx.matched_order_id else "agency payment"
                self._record(key, True, f"{what} → {tx.status} {target}", tx.matched_order_id)
            elif tx.received_at <= cutoff:
                self._record(key, False, f"{what} → still unmatched: {tx.match_note or '—'}")

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
                self._record(key, True, f"{what} → approved ({p.method})", p.order_id)
            elif p.status == PaymentStatus.REJECTED:
                self._record(key, True, f"{what} → rejected by staff: {p.reject_reason or '—'}", p.order_id)
            elif at <= cutoff:
                self._record(key, False, f"{what} → still unconfirmed after {self.receipt_wait // 60} min",
                             p.order_id)

    # ------------------------------------------------------------------ output
    def _finish(self, *, timed_out: bool = False) -> int:
        from apps.common.staff_alert import alert_staff

        failed = sum(1 for ok, _ in self.done.values() if not ok)
        head = (f"watch_payments: timed out — {len(self.done)}/{self.count} seen" if timed_out
                else f"watch_payments: {self.count} payment(s) — {self.count - failed} matched, {failed} failed")
        self._say(head, ok=not failed and not timed_out)
        lines = "\n".join(("✅ " if ok else "❌ ") + line for ok, line in self.done.values())
        alert_staff(f"پایش پرداخت‌ها تمام شد\n{head}\n{lines}".strip(), perm="payment.view", silent=not failed)
        return failed

    def _t(self, dt) -> str:
        from apps.common.jalali import TZ

        return timezone.localtime(dt, TZ).strftime("%H:%M:%S") if dt else "—"

    def _say(self, text: str, ok: bool = True) -> None:
        stamp = self._t(timezone.now())
        self.stdout.write((self.style.SUCCESS if ok else self.style.ERROR)(f"{stamp} {text}"))
        self.stdout.flush()
