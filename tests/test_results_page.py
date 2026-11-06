"""The results page's diagnosis: which record a not-graded check is missing, and what follows from another failure."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]


def page():
    spec = importlib.util.spec_from_file_location("results_page", ROOT / "scripts/results_page.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_not_graded_check_names_the_record_it_is_missing():
    results_page = page()
    family, kind, help_key = results_page.missing_record(
        "nut-knob", "R4", "pocket 7.50 across flats at its tightest, with ribs, clips, a lip or relief: no print has measured those")
    assert "ribs" in family and kind == "gap" and help_key == "prints"
    family, _, _ = results_page.missing_record("nut-knob", "R4", "pocket 7.85 across flats, -0.15 over the 8.0 nut: prints say not measured")
    assert "tighter than any printed" in family
    family, _, _ = results_page.missing_record("bearing-wheel", "R4", "8.30 mm clear at its tightest: no print has measured that")
    assert "8.0 and 8.4" in family
    family, _, help_key = results_page.missing_record("nut-knob", "R3", "slits split the walls into fingers, so there's no closed pocket")
    assert help_key == "reader"
    # coupon B printed 5.5 to 5.8 for M3: 5.55 sits between two printed sizes, not below them
    family, _, _ = results_page.missing_record("nut-knob", "R4", "pocket 5.55 across flats, +0.05 over the 5.5 nut: prints say not measured")
    assert "between printed sizes" in family
    family, _, _ = results_page.missing_record(
        "nut-knob", "R4", "pocket 5.42 across flats, -0.08 over the 5.5 nut: prints say won't go in; test coupon coupon has 4 pocket(s), "
        "and no print has settled whether any of them holds")
    assert "test coupon" in family and "have ribs" not in family


def test_every_saved_trial_gets_a_diagnosis_for_each_counted_check_that_did_not_pass():
    results_page = page()
    from pbe.runner.trial_record import TrialRecord
    for run in results_page.RUNS:
        for _, record in TrialRecord.all_in(ROOT / "results/runs" / run):
            issues = results_page.issues_of(run, record, None, frozenset())
            if record.declined:
                assert [issue["kind"] for issue in issues] == ["declined"]
            elif record.verdict == "pass":
                assert issues == []
            else:
                assert all(issue["help"] in results_page.HELP and issue["kind"] in results_page.KIND for issue in issues)
                failed = [f for f in record.counted_findings if f.ok is False]
                assert len([issue for issue in issues if issue["kind"] != "gap"]) >= (1 if failed else 0)


def _finding(check, part, ok, detail=""):
    return SimpleNamespace(check=check, part=part, ok=ok, detail=detail)


def _block_with_pocket(hole_d, pocket=(20, 10)):
    """A 10 mm block with a 5 mm deep pocket open at the bed, and optionally a hole up through its roof."""
    l, w = pocket
    body = cq.Workplane("XY").box(l + 20, w + 20, 10, centered=(True, True, False))
    body = body.cut(cq.Workplane("XY").workplane(offset=-1).rect(l, w).extrude(6))
    if hole_d:
        body = body.cut(cq.Workplane("XY").workplane(offset=-1).circle(hole_d / 2).extrude(12))
    return body


def test_only_a_failed_roof_with_a_hole_through_it_is_called_a_holed_roof(tmp_path):
    """A failed bridge check is a holed roof only when the part's mesh shows one (DeepSeek V4 Pro's
    can_run_code tripod t2 fails on a roof and ledges with no hole)."""
    results_page = page()
    (tmp_path / "parts").mkdir()
    cq.exporters.export(_block_with_pocket(5), str(tmp_path / "parts/holed.stl"), tolerance=0.01, angularTolerance=0.1)
    cq.exporters.export(_block_with_pocket(0, (70, 60)), str(tmp_path / "parts/wide.stl"), tolerance=0.01, angularTolerance=0.1)
    record = SimpleNamespace(task="tripod-plate", model="m", trial=1, declined=False, counted_findings=[
        _finding("bridges", "holed", False), _finding("bridges", "wide", False)])
    holed = results_page.holed_roof_parts(tmp_path, record)
    assert holed == {"holed"}
    families = {issue["part"]: (issue["family"], issue["kind"]) for issue in results_page.issues_of("run", record, None, holed)}
    assert families["holed"] == ("A roof with the bolt's hole cut through it", "decided")
    assert families["wide"] == ("A roof or ledge too wide to bridge, with no hole through it", "real")
