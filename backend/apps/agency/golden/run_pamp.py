"""Runs the ORIGINAL PAMP v1.5.3 code on a golden scenario (scripts/agency-golden.sh).

Executed inside PAMP's own image (python 3.11, Django 4.2, PAMP's requirements)
with PAMP's real settings module against a throw-away MySQL — PAMP source is
mounted read-only and never modified. `render` in admins.views is captured so
the dashboard / portal numbers come from PAMP's real view functions.

  python run_pamp.py scenario.json out.json            synthetic start state
  python run_pamp.py --from-db responses.json out.json  start from the DB as loaded (real dump)
"""
import json
import os
import sys

sys.path.insert(0, "/pamp")                 # PAMP v1.5.3 (read-only)
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pamp.settings")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402

import golden_lib  # noqa: E402

from_db = sys.argv[1] == "--from-db"
src, out_path = (sys.argv[2], sys.argv[3]) if from_db else (sys.argv[1], sys.argv[2])
scenario = json.load(open(src))

call_command("migrate", verbosity=0, interactive=False)

from admins import models, tasks, views  # noqa: E402

# PAMP reads its panel connection from PanelConfig — point it at the mock panel
cfg = models.PanelConfig.get_config()
cfg.base_url, cfg.username, cfg.password = golden_lib.BASE, "golden", "golden"
cfg.save()


class _User:
    is_authenticated = True
    is_superuser = True
    is_staff = True

    def __init__(self, username):
        self.username = username


class _Req:
    def __init__(self, username):
        self.user = _User(username)
        self.method = "GET"
        self.session = {}
        self.META = {}
        self.path = "/"

    def get_full_path(self):
        return "/"

    def build_absolute_uri(self, *a):
        return "/"


_captured = {}


def _render(request, template, context=None, *a, **k):
    _captured["ctx"] = context or {}
    return None


views.render = _render       # capture what PAMP's views would render


def portal_fn(a):
    if models.AdminGroup.get_group_for_owner(a.username):
        return None           # group owners get the grouped page (per-account _enrich)
    getattr(views.portal_v2, "__wrapped__", views.portal_v2)(_Req(a.username))
    return _captured["ctx"]


def dashboard_fn():
    fn = getattr(views.dashboard_v2, "__wrapped__", views.dashboard_v2)
    fn(_Req("golden-admin"))
    return _captured["ctx"]


result = golden_lib.run(models, tasks.sync_panel_admins, views._enrich, portal_fn, dashboard_fn,
                        scenario, start_from_initial=not from_db)
result["source"] = {"pamp_version": open("/pamp/VERSION").read().strip(), "django": django.get_version()}
json.dump(result, open(out_path, "w"), indent=1, sort_keys=True)
print("PAMP rounds:", len(result["rounds"]), "admins:", len(result["initial"]["admins"]), "->", out_path)
