"""GOLDEN TEST — the agency port computes exactly what PAMP v1.5.3 computes.

`golden/expected_pamp_v153.json` was produced by running the ORIGINAL PAMP
v1.5.3 code (its own image, Django 4.2, MySQL) on `golden/scenario.json`
(scripts/agency-golden.sh synthetic). Here the agency app runs the same
scenario with the same mocked panel responses; every stored value, formula,
view number, snapshot, SyncLog row and HTTP call (= enforcement decision)
must be identical.

The same comparison on REAL data (the Finland dump + recorded sigma
responses) runs when backend/.golden_local/real/ exists (local only, never
committed): scripts/agency-golden.sh real DUMP RESPONSES, then ./scripts/test.sh.
"""
import json
from pathlib import Path

import pytest

from apps.agency import enrich, models, tasks
from apps.agency.golden import golden_lib
from apps.panel.models import Panel
from apps.settings_app.models import ValueType
from apps.settings_app.utils import set_setting

GOLDEN = Path(__file__).resolve().parent.parent / "golden"
REAL = Path("/app/.golden_local/real")

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def mock_panel_enabled():
    Panel.objects.create(name="golden", base_url=golden_lib.BASE, admin_username="golden",
                         admin_password_enc="golden", is_active=True)
    set_setting("agency_sync_enabled", True, ValueType.BOOL)
    set_setting("agency_enforcement_enabled", True, ValueType.BOOL)


def portal_fn(a):
    if models.AdminGroup.get_group_for_owner(a.username):
        return None
    return enrich.portal_state(a)


def _without_ids(result):
    for state in [result["initial"], *result["rounds"]]:
        for row in state["admins"].values():
            row.pop("id", None)
    return result


def run_ours(scenario, **kw):
    return golden_lib.run(models, tasks.sync_panel_admins, enrich._enrich, portal_fn, enrich.dashboard_numbers,
                          scenario, **kw)


def test_synthetic_scenario_is_identical_to_pamp_v153():
    scenario = json.loads((GOLDEN / "scenario.json").read_text())
    expected = json.loads((GOLDEN / "expected_pamp_v153.json").read_text())
    assert expected["source"]["pamp_version"] == "1.5.3"
    expected.pop("source")
    ours = json.loads(json.dumps(run_ours(scenario)))   # same JSON round-trip as the PAMP side
    # synthetic rows get auto-increment ids (test-order dependent) — compare everything else;
    # the real-data test below keeps the ids (the import must preserve PAMP's ids)
    expected, ours = _without_ids(expected), _without_ids(ours)
    problems = golden_lib.diff(expected, ours)
    assert problems == [], "\n".join(problems[:40])
    # the scenario really exercised the risky paths
    calls = [c for r in expected["rounds"] for c in r["calls"] if c["method"] == "PUT"]
    assert {"status": "disabled"} in [c["body"] for c in calls] and {"status": "active"} in [c["body"] for c in calls]
    assert any("skipped this run" in log["error_message"] for r in expected["rounds"] for log in r["sync_logs"])


@pytest.mark.skipif(not (REAL / "expected.json").exists(), reason="no local real-data golden files")
def test_real_finland_data_is_identical_to_pamp_v153():
    from apps.agency.pamp_import import import_dump

    report = import_dump(str(REAL / "pamp.sql.gz"))
    assert report["verified"] is True
    expected = json.loads((REAL / "expected.json").read_text())
    expected.pop("source")
    rounds = json.loads((REAL / "responses.json").read_text())["rounds"]
    ours = json.loads(json.dumps(run_ours({"rounds": rounds}, start_from_initial=False)))
    (REAL / "agency.json").write_text(json.dumps(ours, indent=1, sort_keys=True))
    problems = golden_lib.diff(expected, ours)
    assert problems == [], "\n".join(problems[:40])
