"""The results page's diagnosis: which record a not-graded check is missing, and what follows from another failure."""
import importlib.util
from pathlib import Path

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
    family, kind, _ = results_page.missing_record(
        "nut-knob", "R4", "pocket 5.60 across flats, +0.10 over the 5.5 nut: prints say struggles to go in; no test coupon in the manual would catch it")
    assert "struggles" in family and kind == "open"
    family, _, _ = results_page.missing_record(
        "nut-knob", "R4", "pocket 5.42 across flats, -0.08 over the 5.5 nut: prints say won't go in; test coupon coupon has 4 pocket(s), "
        "and no print has settled whether any of them holds")
    assert "test coupon" in family and "have ribs" not in family


def test_every_saved_trial_gets_a_diagnosis_for_each_counted_check_that_did_not_pass():
    results_page = page()
    from pbe.runner.trial_record import TrialRecord
    for run in results_page.RUNS:
        for _, record in TrialRecord.all_in(ROOT / "results/runs" / run):
            issues = results_page.issues_of(run, record, None)
            if record.declined:
                assert [issue["kind"] for issue in issues] == ["declined"]
            elif record.verdict == "pass":
                assert issues == []
            else:
                assert all(issue["help"] in results_page.HELP and issue["kind"] in results_page.KIND for issue in issues)
                failed = [f for f in record.counted_findings if f.ok is False]
                assert len([issue for issue in issues if issue["kind"] != "gap"]) >= (1 if failed else 0)
