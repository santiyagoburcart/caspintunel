"""v1.35.1: bring every admin's invoices in line with its ledger (apps/agency/allocation.py).

Default = PREVIEW (read-only, nothing is written): per admin the ledger balance, the open invoice
total and the allocations the invariant would make (which payment / adjustment settles which invoice).
--apply writes exactly that plan (audit-logged). --admin limits it to one admin.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.agency import allocation
from apps.agency.models import AgencyInvoice

LABEL = {"manual": "manual payment", "adjustment": "adjustment", "balance": "covered by the balance"}


def _src(step) -> str:
    e = step.entry
    if e is None:
        return "ledger balance (no single entry)"
    return f"ledger #{e.id} {e.kind} {e.amount:,} ({e.created_at:%Y-%m-%d %H:%M})"


class Command(BaseCommand):
    help = "Reconcile agency invoices with the ledger (preview unless --apply)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="write the allocations (default: preview only)")
        parser.add_argument("--admin", default="", help="only this admin")

    def handle(self, *args, **opts):
        names = sorted(set(AgencyInvoice.objects.values_list("admin_username", flat=True)))
        if opts["admin"]:
            names = [n for n in names if n == opts["admin"]]
        changed = 0
        for n in names:
            p = allocation.plan(n)
            state = "MISMATCH" if p["excess"] > 0 else "ok"
            self.stdout.write(f"{n}: balance {p['balance']:,} · open invoices {p['open']:,} · {state}")
            for s in p["steps"]:
                part = "" if s.amount >= allocation.remaining(s.invoice) else f" (partial, {allocation.remaining(s.invoice) - s.amount:,} left)"
                self.stdout.write(f"   {s.invoice.number} {s.invoice.amount:,} ← {s.amount:,} {LABEL[s.kind]} · {_src(s)}{part}")
            if p["left"] > 0:
                self.stdout.write(f"   ! {p['left']:,} cannot be allocated (invoices under review)")
            if p["steps"]:
                changed += 1
                if opts["apply"]:
                    self._apply(n, p)
        verb = "applied" if opts["apply"] else "would change (preview — run with --apply to write)"
        self.stdout.write(f"{changed} admin(s) {verb}; {len(names)} checked.")

    @transaction.atomic
    def _apply(self, username, p):
        from apps.common.models import write_audit

        steps = allocation.enforce(username, by="reconcile v1.35.1")
        write_audit(action="agency.invoice.reconciled", staff="system", target=None,
                    detail={"admin": username, "balance": str(p["balance"]), "open": str(p["open"]),
                            "allocations": [f"{s.invoice.number}<-{s.amount}:{s.kind}:{s.entry.id if s.entry else '-'}"
                                            for s in steps]})
