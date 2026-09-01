"""
Probe the active panel: authenticate, hit /api/system, list nodes.

    python manage.py panel_check
"""
from django.core.management.base import BaseCommand, CommandError

from apps.panel.exceptions import PanelError
from apps.panel.services import client_for, get_active_panel


class Command(BaseCommand):
    help = "Check connectivity and auth against the active panel."

    def handle(self, *args, **opts):
        panel = get_active_panel()
        if not panel:
            raise CommandError("no active panel row — run `manage.py seed` with PANEL_* env set")

        self.stdout.write(f"panel: {panel.name} @ {panel.base_url}")
        client = client_for(panel)
        try:
            stats = client.system_stats()
            self.stdout.write(self.style.SUCCESS("auth OK"))
            self.stdout.write(f"system stats: {stats}")
            try:
                nodes = client.list_nodes()
                self.stdout.write(f"nodes: {len(nodes)}")
                for n in nodes:
                    if isinstance(n, dict):
                        self.stdout.write(f"  - {n.get('name')}: {n.get('status')} {n.get('message') or ''}".rstrip())
            except PanelError as exc:
                self.stdout.write(self.style.WARNING(f"nodes unavailable: {exc}"))
            try:
                groups = client.list_groups()
                self.stdout.write(f"groups (use ids in Panel.default_group_ids):")
                for g in groups:
                    if isinstance(g, dict):
                        self.stdout.write(f"  - id={g.get('id')}  {g.get('name')}")
            except PanelError as exc:
                self.stdout.write(self.style.WARNING(f"groups unavailable: {exc}"))
        except PanelError as exc:
            raise CommandError(f"panel check failed: {exc}")
