"""Import a PAMP MySQL dump (mysqldump output, plain or .gz) into the agency tables.

Every value is copied 1:1 — primary keys (so snapshots/limits keep pointing to
the same admin), byte counters, deleted-users accumulators, snapshots, logs and
the original created/updated timestamps — and the result is re-read and
compared field by field with the dump before the transaction commits.

PAMP table              → agency table
  admins_paneladmin        agency_panel_admin
  admins_adminlimit        agency_admin_limit
  admins_usertrafficsnapshot agency_user_traffic_snapshot
  admins_synclog           agency_sync_log
  admins_admingroup        agency_admin_group
  admins_syncsettings      setting agency_sync_interval_minutes
  admins_panelconfig       not imported (only its host is compared with ours;
                           the password stays in the dump)
Not imported: auth_user (resellers are not caspintunel customers), sessions,
Telegram config, UI settings, celery beat/results tables.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import re
from contextlib import contextmanager
from decimal import Decimal

from django.db import models, transaction

from .models import AdminGroup, AdminLimit, PanelAdmin, SyncLog, UserTrafficSnapshot

TABLES = [  # import order (FK parents first)
    ("admins_paneladmin", PanelAdmin),
    ("admins_adminlimit", AdminLimit),
    ("admins_usertrafficsnapshot", UserTrafficSnapshot),
    ("admins_synclog", SyncLog),
    ("admins_admingroup", AdminGroup),
]


class DumpError(Exception):
    pass


# ---------------------------------------------------------------- dump parsing
_CREATE_RE = re.compile(r"^CREATE TABLE `([^`]+)` \($", re.M)
_COL_RE = re.compile(r"^\s+`([^`]+)` ")
_INSERT_RE = re.compile(r"^INSERT INTO `([^`]+)`(?: \(([^)]*)\))? VALUES ", re.M)
_ESC = {"0": "\0", "'": "'", '"': '"', "b": "\b", "n": "\n", "r": "\r", "t": "\t", "Z": "\x1a", "\\": "\\"}
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def read_dump(path: str) -> str:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        return f.read()


def _columns(sql: str) -> dict[str, list[str]]:
    out = {}
    for m in _CREATE_RE.finditer(sql):
        cols = []
        for line in sql[m.end():].splitlines()[1:]:
            c = _COL_RE.match(line)
            if not c:
                break
            cols.append(c.group(1))
        out[m.group(1)] = cols
    return out


def _parse_values(sql: str, i: int):
    """Yield one tuple per `(...)` group of an extended INSERT starting at i;
    returns the index after the closing `;` via StopIteration.value."""
    n = len(sql)
    while True:
        while sql[i] in " \n\r\t,":
            i += 1
        if sql[i] == ";":
            return i + 1
        if sql[i] != "(":
            raise DumpError(f"unexpected {sql[i:i + 20]!r} in INSERT")
        i += 1
        row = []
        while True:
            while sql[i] == " ":
                i += 1
            ch = sql[i]
            if ch == "'" or sql.startswith("_binary '", i):
                if ch != "'":
                    i += len("_binary ")
                i += 1
                buf = []
                while True:
                    c = sql[i]
                    if c == "\\":
                        buf.append(_ESC.get(sql[i + 1], sql[i + 1]))
                        i += 2
                    elif c == "'":
                        if i + 1 < n and sql[i + 1] == "'":   # '' inside a string
                            buf.append("'"); i += 2
                        else:
                            i += 1
                            break
                    else:
                        buf.append(c); i += 1
                row.append(("s", "".join(buf)))
            elif sql.startswith("NULL", i):
                row.append(("null", None)); i += 4
            elif sql.startswith("0x", i):
                m = re.match(r"0x([0-9A-Fa-f]*)", sql[i:])
                row.append(("s", bytes.fromhex(m.group(1)).decode("utf-8"))); i += m.end()
            else:
                m = _NUM_RE.match(sql, i)
                if not m:
                    raise DumpError(f"cannot parse value at {sql[i:i + 30]!r}")
                row.append(("n", m.group(0))); i = m.end()
            while sql[i] == " ":
                i += 1
            if sql[i] == ",":
                i += 1
                continue
            if sql[i] == ")":
                i += 1
                break
            raise DumpError(f"unexpected {sql[i:i + 20]!r} after a value")
        yield row


def parse_dump(sql: str, wanted: set[str]) -> dict[str, list[dict]]:
    cols = _columns(sql)
    rows: dict[str, list[dict]] = {t: [] for t in wanted}
    for m in _INSERT_RE.finditer(sql):
        table = m.group(1)
        if table not in wanted:
            continue
        names = [c.strip().strip("`") for c in m.group(2).split(",")] if m.group(2) else cols.get(table)
        if not names:
            raise DumpError(f"no column list for {table} (CREATE TABLE missing from the dump?)")
        gen = _parse_values(sql, m.end())
        for values in gen:
            if len(values) != len(names):
                raise DumpError(f"{table}: {len(values)} values for {len(names)} columns")
            rows[table].append(dict(zip(names, values)))
    return rows


# ---------------------------------------------------------------- conversion
def _to_python(field: models.Field, token):
    kind, raw = token
    if kind == "null":
        return None
    if isinstance(field, models.BooleanField):
        return bool(int(raw))
    if isinstance(field, (models.BigIntegerField, models.IntegerField, models.AutoField, models.ForeignKey,
                          models.PositiveIntegerField)):
        return int(raw)
    if isinstance(field, models.FloatField):
        return float(raw)
    if isinstance(field, models.DecimalField):
        return Decimal(raw)
    if isinstance(field, models.DateTimeField):
        # Django on MySQL stores naive UTC (USE_TZ=True) — keep the exact instant
        value = dt.datetime.fromisoformat(raw)
        return value.replace(tzinfo=dt.timezone.utc)
    if isinstance(field, models.JSONField):
        return json.loads(raw)
    return raw


def _field_map(model):
    return {f.column: f for f in model._meta.concrete_fields}


@contextmanager
def _keep_timestamps(*model_classes):
    """Turn auto_now/auto_now_add off while importing so the dump's values stay."""
    saved = []
    for m in model_classes:
        for f in m._meta.concrete_fields:
            if isinstance(f, models.DateTimeField) and (f.auto_now or f.auto_now_add):
                saved.append((f, f.auto_now, f.auto_now_add))
                f.auto_now = f.auto_now_add = False
    try:
        yield
    finally:
        for f, a, b in saved:
            f.auto_now, f.auto_now_add = a, b


# ---------------------------------------------------------------- import
def import_dump(path: str, *, replace: bool = False, dry_run: bool = False) -> dict:
    sql = read_dump(path)
    if "-- Dump completed" not in sql[-500:]:
        raise DumpError("the dump is incomplete (no '-- Dump completed' footer)")
    wanted = {t for t, _ in TABLES} | {"admins_syncsettings", "admins_panelconfig"}
    parsed = parse_dump(sql, wanted)

    report = {"tables": {}, "warnings": []}
    objects = {}
    for table, model in TABLES:
        fmap = _field_map(model)
        unknown = set().union(*(r.keys() for r in parsed[table])) - set(fmap) if parsed[table] else set()
        if unknown:
            raise DumpError(f"{table}: columns not in the agency model: {sorted(unknown)} — newer PAMP schema?")
        objs = []
        for r in parsed[table]:
            objs.append(model(**{fmap[c].attname: _to_python(fmap[c], tok) for c, tok in r.items()}))
        objects[model] = objs
        report["tables"][table] = len(objs)

    # settings / panel host (informational)
    interval = None
    if parsed["admins_syncsettings"]:
        tok = parsed["admins_syncsettings"][0].get("interval_minutes")
        interval = int(tok[1]) if tok and tok[0] == "n" else None
    report["sync_interval_minutes"] = interval
    pamp_host = None
    if parsed["admins_panelconfig"]:
        tok = parsed["admins_panelconfig"][0].get("base_url")
        pamp_host = re.sub(r"^https?://", "", (tok[1] if tok and tok[0] == "s" else "") or "").split("/")[0] or None
    report["pamp_panel_host"] = pamp_host
    try:
        from .panel_api import agency_panel

        ours = re.sub(r"^https?://", "", agency_panel().base_url).split("/")[0]
    except Exception:  # noqa: BLE001
        ours = None
    report["agency_panel_host"] = ours
    if pamp_host and ours and pamp_host != ours:
        report["warnings"].append(f"PAMP syncs {pamp_host}, the agency module would sync {ours}")

    pa = objects[PanelAdmin]
    report["totals"] = {
        "admins": len(pa),
        "deleted_users_used_bytes": sum(a.deleted_users_used_bytes or 0 for a in pa),
        "total_user_limit": sum(a.total_user_limit or 0 for a in pa),
        "total_user_used": sum(a.total_user_used or 0 for a in pa),
        "admin_remaining": sum(a.admin_remaining or 0 for a in pa),
        "snapshot_used_bytes": sum(s.used_traffic_bytes or 0 for s in objects[UserTrafficSnapshot]),
    }
    if dry_run:
        report["dry_run"] = True
        return report

    with transaction.atomic():
        existing = PanelAdmin.objects.exists() or SyncLog.objects.exists() or AdminGroup.objects.exists()
        if existing and not replace:
            raise DumpError("the agency tables already hold data — use --replace to overwrite them")
        for _, model in reversed(TABLES):
            model.objects.all().delete()
        with _keep_timestamps(*(m for _, m in TABLES)):
            for _, model in TABLES:
                model.objects.bulk_create(objects[model], batch_size=1000)
        if interval:
            from apps.settings_app.models import ValueType
            from apps.settings_app.utils import set_setting

            set_setting("agency_sync_interval_minutes", interval, ValueType.INT)
        mismatches = verify(parsed)
        if mismatches:
            raise DumpError("re-read differs from the dump: " + "; ".join(mismatches[:10]))
    report["verified"] = True
    return report


def verify(parsed: dict[str, list[dict]]) -> list[str]:
    """Every row and every column of the dump equals what is now in the DB."""
    out = []
    for table, model in TABLES:
        fmap = _field_map(model)
        db_rows = {o.pk: o for o in model.objects.all()}
        if len(db_rows) != len(parsed[table]):
            out.append(f"{table}: {len(db_rows)} rows in DB, {len(parsed[table])} in the dump")
            continue
        for r in parsed[table]:
            pk = int(r["id"][1])
            obj = db_rows.get(pk)
            if obj is None:
                out.append(f"{table} #{pk} missing")
                continue
            for col, tok in r.items():
                f = fmap[col]
                want, got = _to_python(f, tok), getattr(obj, f.attname)
                if isinstance(got, dt.datetime) and isinstance(want, dt.datetime):
                    got = got.astimezone(dt.timezone.utc)
                if want != got:
                    out.append(f"{table} #{pk}.{col}: dump {want!r} db {got!r}")
    return out
