"""Agency module safety: sync/enforcement OFF by default, resellers never become
customer users, RBAC permissions, and the PAMP dump importer (1:1, verified)."""
import datetime as dt
import gzip

import pytest
import responses
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User
from apps.agency import tasks
from apps.agency.models import AdminGroup, AdminLimit, PanelAdmin, SyncLog, UserTrafficSnapshot
from apps.agency.pamp_import import DumpError, import_dump, parse_dump
from apps.panel.models import Panel
from apps.settings_app.models import ValueType
from apps.settings_app.utils import get_setting, set_setting

pytestmark = pytest.mark.django_db
BASE = "https://sigma.test"


@pytest.fixture
def panel():
    return Panel.objects.create(name="sigma", base_url=BASE, admin_username="u", admin_password_enc="p", is_active=True)


def test_sync_and_enforcement_are_off_by_default_and_touch_nothing(panel):
    call_command("seed", verbosity=0)
    assert get_setting("agency_sync_enabled") is False and get_setting("agency_enforcement_enabled") is False
    with responses.RequestsMock() as rsps:            # any HTTP call would fail the test
        res = tasks.sync_panel_admins.apply(throw=False)
        assert len(rsps.calls) == 0
    assert res.result == "disabled" and not SyncLog.objects.exists() and not PanelAdmin.objects.exists()


def test_seed_adds_permissions_and_the_gated_periodic_task():
    from django_celery_beat.models import PeriodicTask

    from apps.accounts.models import Permission, Role

    call_command("seed", verbosity=0)
    from apps.accounts.models import GM_PERMS

    assert set(Permission.objects.filter(code__startswith="agency.").values_list("code", flat=True)) == {
        "agency.view", "agency.manage", "agency.accounting", "agency.group_manager", *GM_PERMS}
    assert Role.objects.get(name="Super Admin").permissions.filter(code="agency.manage").exists()
    # v1.25: the group-manager code restricts — only the "Group manager" role holds it
    assert not Role.objects.get(name="Super Admin").permissions.filter(code="agency.group_manager").exists()
    assert set(Role.objects.get(name="Group manager").permissions.values_list("code", flat=True)) == {"agency.group_manager", *GM_PERMS}
    t = PeriodicTask.objects.get(name="agency: sync panel admins (PAMP)")
    assert t.task == "apps.agency.tasks.sync_panel_admins" and t.interval.every == 15


@responses.activate
def test_resellers_never_become_caspintunel_users(panel):
    set_setting("agency_sync_enabled", True, ValueType.BOOL)
    responses.add("POST", f"{BASE}/api/admin/token", json={"access_token": "t"})
    responses.add("GET", f"{BASE}/api/admins", json={"admins": [{"username": "reseller1", "data_limit": None,
                                                                    "used_traffic": 5, "total_users": 1}]})
    responses.add("GET", f"{BASE}/api/users", json={"users": [{"username": "x", "used_traffic": 5, "data_limit": 10}]})
    users_before = User.objects.count()
    tasks.sync_panel_admins.apply(throw=False)
    assert PanelAdmin.objects.filter(username="reseller1").exists()
    assert User.objects.count() == users_before and not User.objects.filter(username="reseller1").exists()


def test_enforcement_stays_off_when_only_sync_is_enabled(panel):
    set_setting("agency_sync_enabled", True, ValueType.BOOL)
    with responses.RequestsMock() as rsps:
        rsps.add("POST", f"{BASE}/api/admin/token", json={"access_token": "t"})
        rsps.add("GET", f"{BASE}/api/admins", json={"admins": [{"username": "over", "data_limit": 10,
                                                                   "used_traffic": 99, "total_users": 0}]})
        rsps.add("GET", f"{BASE}/api/users", json={"users": []})
        tasks.sync_panel_admins.apply(throw=False)
        assert not [c for c in rsps.calls if c.request.method == "PUT"]          # no disable call
    assert PanelAdmin.objects.get(username="over").pamp_blocked is False


# --- importer ---------------------------------------------------------------------
DUMP = r"""-- MySQL dump 10.13
CREATE TABLE `admins_paneladmin` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `username` varchar(255) NOT NULL,
  `is_sudo` tinyint(1) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `total_user_limit` bigint NOT NULL,
  `total_user_used` bigint NOT NULL,
  `admin_remaining` bigint NOT NULL,
  `user_count` int NOT NULL,
  `active_user_count` int NOT NULL,
  `raw_data` json NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `last_synced_at` datetime(6) DEFAULT NULL,
  `status` varchar(50) NOT NULL,
  `admin_limit_bytes` bigint NOT NULL,
  `has_data_limit` tinyint(1) NOT NULL,
  `disabled_users` int NOT NULL,
  `expired_users` int NOT NULL,
  `limited_users` int NOT NULL,
  `on_hold_users` int NOT NULL,
  `pamp_blocked` tinyint(1) NOT NULL,
  `pamp_blocked_at` datetime(6) DEFAULT NULL,
  `deleted_traffic_reset_at` datetime(6) DEFAULT NULL,
  `deleted_users_used_bytes` bigint NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;
INSERT INTO `admins_paneladmin` VALUES (7,'ali\'s \\ shop',0,1,107374182400,53687091200,42949672960,3,2,'{\"note\": \"x\\ny\", \"n\": 1}','2026-09-01 10:00:00.123456','2026-10-16 13:00:00.000000',NULL,'active',107374182400,1,0,0,0,1,0,NULL,NULL,9223372036854775806),(9,'رضا',1,0,0,0,0,0,0,'{}','2026-09-02 00:00:00.000000','2026-09-02 00:00:00.000000','2026-10-16 13:40:01.500000','disabled',0,0,0,0,0,0,1,'2026-10-01 01:02:03.000000',NULL,0);
CREATE TABLE `admins_adminlimit` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `limit_bytes` bigint NOT NULL,
  `warning_sent_80` tinyint(1) NOT NULL,
  `is_blocked` tinyint(1) NOT NULL,
  `blocked_at` datetime(6) DEFAULT NULL,
  `telegram_username` varchar(100) NOT NULL,
  `support_telegram` varchar(100) NOT NULL,
  `panel_admin_id` bigint NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;
INSERT INTO `admins_adminlimit` VALUES (3,0,1,0,NULL,'','@support',7);
CREATE TABLE `admins_usertrafficsnapshot` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_username` varchar(255) NOT NULL,
  `used_traffic_bytes` bigint NOT NULL,
  `last_seen` datetime(6) NOT NULL,
  `panel_admin_id` bigint NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;
INSERT INTO `admins_usertrafficsnapshot` VALUES (100,'u1',1234567890123,'2026-10-16 13:40:00.000000',7),(101,'u''2',0,'2026-10-16 13:40:00.000000',7);
CREATE TABLE `admins_synclog` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `status` varchar(20) NOT NULL,
  `admins_synced` int NOT NULL,
  `error_message` longtext NOT NULL,
  `duration_seconds` double NOT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;
INSERT INTO `admins_synclog` VALUES (55,'partial',78,'a: failed\nb: \"quoted\"',3.1415926535,'2026-10-16 13:40:00.000000');
CREATE TABLE `admins_admingroup` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `owner_username` varchar(150) NOT NULL,
  `member_usernames` longtext NOT NULL,
  `note` varchar(200) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;
INSERT INTO `admins_admingroup` VALUES (2,'رضا','ali\'s \\ shop,رضا','',  '2026-09-03 00:00:00.000000');
CREATE TABLE `admins_syncsettings` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `interval_minutes` int NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;
INSERT INTO `admins_syncsettings` VALUES (1,10,'2026-09-01 00:00:00.000000');
CREATE TABLE `admins_panelconfig` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `base_url` varchar(255) NOT NULL,
  `username` varchar(150) NOT NULL,
  `password` varchar(255) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB;
INSERT INTO `admins_panelconfig` VALUES (1,'https://sigma.test','admin','secret-not-imported','2026-09-01 00:00:00.000000');
-- Dump completed on 2026-10-16 13:42:30
"""


@pytest.fixture
def dump_file(tmp_path):
    p = tmp_path / "pamp.sql.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write(DUMP)
    return str(p)


def test_parser_handles_escapes_nulls_json_and_unicode():
    rows = parse_dump(DUMP, {"admins_paneladmin", "admins_usertrafficsnapshot"})
    a = rows["admins_paneladmin"][0]
    assert a["username"] == ("s", "ali's \\ shop") and a["last_synced_at"] == ("null", None)
    assert rows["admins_paneladmin"][1]["username"] == ("s", "رضا")
    assert rows["admins_usertrafficsnapshot"][1]["user_username"] == ("s", "u'2")


def test_import_copies_every_value_1_to_1(dump_file, panel):
    report = import_dump(dump_file)
    assert report["verified"] is True and report["warnings"] == []
    assert report["tables"] == {"admins_paneladmin": 2, "admins_adminlimit": 1, "admins_usertrafficsnapshot": 2,
                                "admins_synclog": 1, "admins_admingroup": 1}
    a = PanelAdmin.objects.get(pk=7)
    assert a.username == "ali's \\ shop" and a.deleted_users_used_bytes == 9223372036854775806
    assert a.raw_data == {"note": "x\ny", "n": 1}
    assert a.created_at == dt.datetime(2026, 9, 1, 10, 0, 0, 123456, tzinfo=dt.timezone.utc)   # not "now"
    assert a.updated_at == dt.datetime(2026, 10, 16, 13, 0, tzinfo=dt.timezone.utc)
    b = PanelAdmin.objects.get(pk=9)
    assert b.pamp_blocked is True and b.is_sudo is True and b.last_synced_at.microsecond == 500000
    assert AdminLimit.objects.get(pk=3).panel_admin_id == 7
    assert UserTrafficSnapshot.objects.get(pk=100).used_traffic_bytes == 1234567890123
    log = SyncLog.objects.get(pk=55)
    assert log.duration_seconds == 3.1415926535 and log.error_message == 'a: failed\nb: "quoted"'
    assert AdminGroup.objects.get(pk=2).get_all_usernames() == ["رضا", "ali's \\ shop"]
    assert get_setting("agency_sync_interval_minutes") == 10
    assert not User.objects.filter(username__in=["admin", "ali's \\ shop"]).exists()


def test_import_refuses_to_overwrite_without_replace(dump_file, panel):
    import_dump(dump_file)
    with pytest.raises(DumpError):
        import_dump(dump_file)
    assert import_dump(dump_file, replace=True)["verified"] is True


def test_import_refuses_while_sync_is_enabled_and_detects_truncated_dumps(dump_file, tmp_path, panel):
    set_setting("agency_sync_enabled", True, ValueType.BOOL)
    with pytest.raises(CommandError):
        call_command("import_pamp_dump", dump_file)
    cut = tmp_path / "cut.sql"
    cut.write_text(DUMP.replace("-- Dump completed on 2026-10-16 13:42:30", ""), encoding="utf-8")
    with pytest.raises(DumpError):
        import_dump(str(cut), dry_run=True)


def test_panel_host_mismatch_is_reported(dump_file):
    Panel.objects.create(name="other", base_url="https://other.panel", admin_username="u",
                         admin_password_enc="p", is_active=True)
    assert import_dump(dump_file, dry_run=True)["warnings"] == ["PAMP syncs sigma.test, the agency module would sync other.panel"]
