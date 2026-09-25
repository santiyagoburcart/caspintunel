"""
Idempotent initial seed: permissions, roles, default theme, site config,
settings defaults, CMS pages, telegram bot rows, and the panel row from env.

Safe to run repeatedly (get_or_create / update_or_create).
    python manage.py seed
"""
import json as _json
import os

from django.conf import settings as dj_settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Permission, Role
from apps.settings_app.models import Page, Setting, SiteConfig, Theme, ValueType
from apps.telegram.models import BotType, TelegramConfig

PERMISSIONS = [
    ("users.view", "View users"),
    ("users.manage", "Create / edit / disable users"),
    ("plans.manage", "Manage plans"),
    ("payment.view", "View payments"),
    ("payment.approve", "Approve / reject payments"),
    ("accounting.view", "View accounting reports"),
    ("broadcast.send", "Send broadcasts"),
    ("sms.manage", "Manage SMS numbers & devices"),
    ("roles.manage", "Manage roles & permissions"),
    ("settings.manage", "Manage settings & branding"),
    ("settings.email", "Manage outgoing email (SMTP relay)"),
    ("bots.manage", "Manage bots & channels"),
    ("pages.manage", "Manage content pages"),
    ("monitoring.view", "View monitoring & resources"),
    ("audit.view", "View audit log"),
    ("themes.manage", "Manage themes"),
    ("services.manage", "Manage sold services (status, reset, revoke, create)"),
    ("services.delete", "Delete sold services"),
    ("users.delete", "Delete / restore users"),
]

SUPPORT_PERMS = {"users.view", "payment.view", "payment.approve", "accounting.view", "monitoring.view"}

MIDNIGHT_AURORA = {
    "dark": {
        "background": "#0B0E14", "surface": "rgba(255,255,255,0.06)", "primary": "#7C5CFF",
        "secondary": "#22D3EE", "success": "#34D399", "danger": "#F87171", "warning": "#FBBF24",
        "text": "#E6E8EC", "text_muted": "#9AA3B2", "border": "rgba(255,255,255,0.1)",
    },
    "light": {
        "background": "#F5F7FA", "surface": "rgba(255,255,255,0.7)", "primary": "#6D48F0",
        "secondary": "#0EA5B7", "success": "#059669", "danger": "#DC2626", "warning": "#D97706",
        "text": "#111827", "text_muted": "#6B7280", "border": "rgba(0,0,0,0.08)",
    },
}

# A theme now carries more than colours: `base` locks the site to light/dark
# (omit / "auto" to keep the user's dark-mode toggle, as Midnight Aurora does)
# and `style` selects the component look (`aurora` = existing default,
# `frost` = the new glass/light look). `vars` are extra raw CSS custom
# properties applied alongside the 10 semantic colour tokens.
ROYAL_FROST = {
    "base": "light",
    "style": "frost",
    "light": {
        "background": "#EEF3FB", "surface": "rgba(255,255,255,0.55)", "primary": "#2E56C8",
        "secondary": "#5B8DEF", "success": "#16A34A", "danger": "#DC2626", "warning": "#D97706",
        "text": "#1F2F55", "text_muted": "#6B7A9C", "border": "rgba(46,86,200,0.14)",
    },
    # frost is light-only (base="light" locks it) — kept identical to `light`
    # so a stray dark-mode read (e.g. a cached ct_mode) never breaks
    "dark": {
        "background": "#EEF3FB", "surface": "rgba(255,255,255,0.55)", "primary": "#2E56C8",
        "secondary": "#5B8DEF", "success": "#16A34A", "danger": "#DC2626", "warning": "#D97706",
        "text": "#1F2F55", "text_muted": "#6B7A9C", "border": "rgba(46,86,200,0.14)",
    },
    "vars": {
        "--c-primary-2": "#3B6FE0", "--c-ink": "#1E3A8A", "--c-glass-border": "rgba(255,255,255,0.85)",
    },
}

# Third theme: "Caspian" — two user-switchable variants (dark "Caspian
# Tunnel" / light "Azure Telemetry") sharing style="caspian". No `base` is
# set, so it behaves like Midnight Aurora: the user's own dark-mode toggle
# picks the variant. `light`/`dark` carry the 10 semantic tokens (auto
# picked by mode); `vars` carries the extra Caspian-only tokens, each
# suffixed -light/-dark and picked apart in CSS by [data-theme-style=
# "caspian"] vs. [data-theme-style="caspian"].dark (see index.css).
# Fixed Caspian brand colours: primary blue #1464BA (single-source primary),
# success green #11AB53 (every success / "up" / active-state green). #4C90D6 is
# a lighter tint of the blue — the supporting/secondary accent (and the
# readable-on-black tone in the dark variant).
CASPIAN = {
    "style": "caspian",
    "light": {
        "background": "#F8FAFC", "surface": "#FFFFFF", "primary": "#1464BA",
        "secondary": "#4C90D6", "success": "#11AB53", "danger": "#F43F5E", "warning": "#F59E0B",
        "text": "#0F172A", "text_muted": "#64748B", "border": "#E2E8F0",
    },
    "dark": {
        "background": "#080B14", "surface": "#0D111F", "primary": "#1464BA",
        "secondary": "#4C90D6", "success": "#11AB53", "danger": "#EF4444", "warning": "#F59E0B",
        "text": "#E0E2EF", "text_muted": "#94A3B8", "border": "#1E2640",
    },
    "vars": {
        "--csp-font-ui-light": "'Inter'", "--csp-font-ui-dark": "'Plus Jakarta Sans'",
        "--csp-font-display-light": "'Space Grotesk'", "--csp-font-display-dark": "'Plus Jakarta Sans'",
        "--csp-well-light": "#F8FAFC", "--csp-well-dark": "#060910",
        "--csp-muted-bg-light": "#F1F5F9", "--csp-muted-bg-dark": "#181B25",
        "--csp-text2-light": "#1E293B", "--csp-text2-dark": "#CBC3D7",
        "--csp-text3-light": "#334155", "--csp-text3-dark": "#94A3B8",
        "--csp-border-strong-light": "#CBD5E1", "--csp-border-strong-dark": "#494454",
        "--csp-signal-light": "#4C90D6", "--csp-signal-dark": "#4C90D6",
        "--csp-vibrant-light": "#0F4E92", "--csp-vibrant-dark": "#0F4E92",
        "--csp-gauge-from-light": "#4C90D6", "--csp-gauge-from-dark": "#4C90D6",
        "--csp-gauge-to-light": "#1464BA", "--csp-gauge-to-dark": "#1464BA",
        "--csp-glow-light": "rgba(20,100,186,0.28)", "--csp-glow-dark": "rgba(76,144,214,0.45)",
        "--csp-radius-card-light": "0.75rem", "--csp-radius-card-dark": "1rem",
    },
}

SETTINGS_DEFAULTS = [
    ("email_verification_required", "false", ValueType.BOOL),
    ("force_channel_join", "false", ValueType.BOOL),
    ("force_share_phone", "false", ValueType.BOOL),
    ("iran_phone_only", "true", ValueType.BOOL),
    ("unique_amount_min", "200", ValueType.INT),
    ("unique_amount_max", "1500", ValueType.INT),
    ("unique_amount_reservation_minutes", "30", ValueType.INT),
    ("backup_interval_minutes", "1440", ValueType.INT),
    ("default_language", "fa", ValueType.STR),
    ("alert_volume_percent", "80", ValueType.INT),
    ("alert_expire_days", "3", ValueType.INT),
]

PAGES = [
    ("rules", "قوانین", "Rules"),
    ("tutorial", "آموزش اتصال", "Tutorial"),
    ("faq", "سوالات متداول", "FAQ"),
]


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _seed_bot(bot_type, token, proxy, backup_chat_id=None):
    defaults = {"is_active": bool(token)}
    if token:
        defaults["token"] = token
    if proxy:
        defaults["proxy_url"] = proxy
    if backup_chat_id is not None:
        defaults["backup_chat_id"] = backup_chat_id
    obj, created = TelegramConfig.objects.get_or_create(bot_type=bot_type, defaults=defaults)
    if not created and token and not obj.token:
        obj.token = token
        obj.is_active = True
        if proxy and not obj.proxy_url:
            obj.proxy_url = proxy
        if backup_chat_id is not None and not obj.backup_chat_id:
            obj.backup_chat_id = backup_chat_id
        obj.save()
    return obj


class Command(BaseCommand):
    help = "Seed initial data (idempotent)."

    @transaction.atomic
    def handle(self, *args, **opts):
        # --- permissions & roles ---
        perms = {}
        for code, name in PERMISSIONS:
            p, _ = Permission.objects.update_or_create(code=code, defaults={"name": name})
            perms[code] = p

        super_role, _ = Role.objects.get_or_create(
            name="Super Admin", defaults={"description": "Full access"}
        )
        super_role.permissions.set(perms.values())

        # bootstrap a Staff account from the Django superuser env (panel login)
        su_name = os.environ.get("DJANGO_SUPERUSER_USERNAME", "")
        su_pass = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        if su_name and su_pass:
            from apps.accounts.models import Staff

            staff, created = Staff.objects.get_or_create(
                username=su_name,
                defaults={"role": super_role, "is_superadmin": True, "is_active": True},
            )
            if created:
                staff.set_password(su_pass)
                staff.save()
                self.stdout.write(self.style.SUCCESS(f"staff '{su_name}' created (Super Admin)"))

        support_role, _ = Role.objects.get_or_create(
            name="Support", defaults={"description": "Payments & user support"}
        )
        support_role.permissions.set([perms[c] for c in SUPPORT_PERMS])

        # --- themes ---
        # `seed` re-runs on every container start / update, so `is_active` must
        # only be set when a theme row is first created — otherwise re-running
        # it would silently undo an admin's choice to activate another theme.
        mid, created = Theme.objects.get_or_create(
            name="Midnight Aurora", defaults={"palette": MIDNIGHT_AURORA, "is_active": True}
        )
        if not created:
            Theme.objects.filter(pk=mid.pk).update(palette=MIDNIGHT_AURORA)

        frost, created = Theme.objects.get_or_create(
            name="Royal Frost", defaults={"palette": ROYAL_FROST, "is_active": False}
        )
        if not created:
            Theme.objects.filter(pk=frost.pk).update(palette=ROYAL_FROST)

        caspian, created = Theme.objects.get_or_create(
            name="Caspian", defaults={"palette": CASPIAN, "is_active": False}
        )
        if not created:
            Theme.objects.filter(pk=caspian.pk).update(palette=CASPIAN)

        # --- site config (singleton) — keep the domain in step with DOMAIN ---
        site = SiteConfig.load()
        domain = getattr(dj_settings, "DOMAIN", "") or ""
        if domain and site.site_domain != domain:
            site.site_domain = domain
            site.save(update_fields=["site_domain", "updated_at"])
            self.stdout.write(f"site_domain -> {domain}")

        # --- settings ---
        for key, value, vtype in SETTINGS_DEFAULTS:
            Setting.objects.get_or_create(key=key, defaults={"value": value, "value_type": vtype})
        active_theme = Theme.objects.filter(is_active=True).first()
        if active_theme:
            Setting.objects.update_or_create(
                key="active_theme_id",
                defaults={"value": str(active_theme.id), "value_type": ValueType.INT},
            )

        # --- CMS pages ---
        for slug, fa, en in PAGES:
            Page.objects.get_or_create(slug=slug, defaults={"title_fa": fa, "title_en": en})

        # --- telegram bot rows (tokens from env on first run; edit later in admin) ---
        proxy = getattr(dj_settings, "TELEGRAM_PROXY_URL", "") or ""
        _seed_bot(BotType.SALES, os.environ.get("BOT_SALES_TOKEN", ""), proxy)
        _seed_bot(
            BotType.BACKUP, os.environ.get("BOT_BACKUP_TOKEN", ""), proxy,
            backup_chat_id=_int_or_none(os.environ.get("BOT_BACKUP_CHAT_ID")),
        )

        # --- periodic tasks (celery beat / DatabaseScheduler) ---
        self._seed_periodic_tasks()

        # --- panel row: one-time bootstrap from env (fresh install only) ---
        # Panels are managed in the admin panel (Panel link page). This only runs
        # when no panel exists yet, so an update can never overwrite or duplicate
        # a panel configured there.
        from apps.panel.models import Panel

        base_url = getattr(dj_settings, "PANEL_BASE_URL", "")
        pw = getattr(dj_settings, "PANEL_ADMIN_PASSWORD", "")
        if Panel.objects.exists():
            self.stdout.write("panel(s) already configured in the admin panel — env panel settings ignored")
        elif base_url and pw:
            Panel.objects.update_or_create(
                name="Pasargad",
                defaults={
                    "base_url": base_url,
                    "admin_username": getattr(dj_settings, "PANEL_ADMIN_USERNAME", ""),
                    "admin_password_enc": pw,
                    "is_active": True,
                },
            )
            self.stdout.write(self.style.SUCCESS("panel row upserted from env"))
        else:
            self.stdout.write("panel env not set — skipping panel row")

        self.stdout.write(self.style.SUCCESS("seed complete"))

    def _seed_periodic_tasks(self):
        from django_celery_beat.models import IntervalSchedule, PeriodicTask

        # the sync interval is the admin setting service_sync_interval_minutes
        # (Settings page) — never reset it from .env on an update
        from apps.ops.schedule import reconcile_sync_schedule

        reconcile_sync_schedule()

        every_5, _ = IntervalSchedule.objects.get_or_create(
            every=5, period=IntervalSchedule.MINUTES
        )
        PeriodicTask.objects.update_or_create(
            name="orders: expire stale reservations",
            defaults={
                "task": "apps.orders.tasks.expire_stale_reservations_task",
                "interval": every_5,
                "kwargs": _json.dumps({}),
                "enabled": True,
            },
        )
        PeriodicTask.objects.update_or_create(
            name="panel: apply due scheduled renewals",
            defaults={
                "task": "apps.panel.tasks.apply_due_scheduled_renewals",
                "interval": every_5,
                "kwargs": _json.dumps({}),
                "enabled": True,
            },
        )
        every_10, _ = IntervalSchedule.objects.get_or_create(
            every=10, period=IntervalSchedule.MINUTES
        )
        PeriodicTask.objects.update_or_create(
            name="orders: retry unfulfilled (paid but not provisioned)",
            defaults={
                "task": "apps.orders.tasks.retry_unfulfilled_orders",
                "interval": every_10,
                "kwargs": _json.dumps({}),
                "enabled": True,
            },
        )

        from apps.settings_app.models import Setting

        backup_minutes = 1440
        s = Setting.objects.filter(key="backup_interval_minutes").first()
        if s:
            backup_minutes = int(s.typed or 1440)
        backup_sched, _ = IntervalSchedule.objects.get_or_create(
            every=backup_minutes, period=IntervalSchedule.MINUTES
        )
        PeriodicTask.objects.update_or_create(
            name="ops: database backup",
            defaults={
                "task": "apps.telegram.tasks.run_backup_task",
                "interval": backup_sched,
                "kwargs": _json.dumps({}),
                "enabled": True,
            },
        )

        hourly, _ = IntervalSchedule.objects.get_or_create(
            every=60, period=IntervalSchedule.MINUTES
        )
        PeriodicTask.objects.update_or_create(
            name="telegram: sync required-channel member counts",
            defaults={
                "task": "apps.telegram.tasks.sync_required_channels_task",
                "interval": hourly,
                "kwargs": _json.dumps({}),
                "enabled": True,
            },
        )

        # --- monitoring (phase 9) ---
        monitoring = [
            ("ops: health checks", "apps.ops.tasks.health_check_task", 2),
            ("ops: resource sample", "apps.ops.tasks.resource_sample_task", 5),
            ("ops: service alerts", "apps.ops.tasks.service_alerts_task", 30),
            ("ops: prune old backups", "apps.ops.tasks.prune_backups_task", 1440),
        ]
        for name, task_path, every in monitoring:
            sched, _ = IntervalSchedule.objects.get_or_create(
                every=every, period=IntervalSchedule.MINUTES
            )
            PeriodicTask.objects.update_or_create(
                name=name,
                defaults={"task": task_path, "interval": sched,
                          "kwargs": _json.dumps({}), "enabled": True},
            )

        from apps.ops.schedule import reconcile_backup_schedule

        reconcile_backup_schedule()

        # seed rewrites theme palettes with queryset.update (no signals)
        from apps.common.public_cache import bump_public_cache

        transaction.on_commit(bump_public_cache)
