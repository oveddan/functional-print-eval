"""The results site's data says what the scorecard says: the same passes and trials per model and task, for the first
print, the second print after feedback and test-first; every saved trial appears exactly once; and a trial that's not
graded is never counted as a pass. No builds and no transcripts read, so it's fast."""
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import results_site  # noqa: E402
import scorecard  # noqa: E402

RUNS = ROOT / "results/runs"


@pytest.fixture(scope="module")
def listed():
    return scorecard.rows()


@pytest.fixture(scope="module")
def index(listed):
    return results_site.index_of(results_site.collect(), listed, scorecard.slice_rows())


def site_tally(index: dict, group: str, passed) -> dict[tuple[str, str], tuple[int, int]]:
    """(model, task) -> (passes, trials) over the counted entries of one group."""
    found = defaultdict(lambda: [0, 0])
    for row in index["trials"]:
        if row["group"] == group and row["counted"]:
            found[row["model"], row["task"]][0] += passed(row)
            found[row["model"], row["task"]][1] += 1
    return {key: tuple(value) for key, value in found.items()}


def scorecard_tally(listed, trials_of, after=False) -> dict[tuple[str, str], tuple[int, int]]:
    return {(row.model, task): (sum(t.passed(after) for t in trials), len(trials))
            for row in listed for task, trials in trials_of(row).items() if trials}


def test_first_prints_match_the_scorecard(index, listed):
    site = site_tally(index, "first", lambda row: row["verdict"] == "pass")
    site = {key: value for key, value in site.items() if key[1] in scorecard.TASKS}
    assert site == scorecard_tally(listed, lambda row: row.by_task)


def test_second_prints_after_feedback_match_the_scorecard(index, listed):
    """Filtering first-print rows on after_feedback.counted lists exactly the trials behind each "after feedback" cell."""
    found = defaultdict(lambda: [0, 0])
    for row in index["trials"]:
        cell = row.get("after_feedback")
        if cell and cell["counted"] and row["task"] in scorecard.TASKS:
            found[row["model"], row["task"]][0] += cell["verdict"] == "pass"
            found[row["model"], row["task"]][1] += 1
            assert cell["via"] == ("second" if cell["second_print"] and row["verdict"] != "pass" else "first")
            assert (cell["second_slug"] is None) == (cell["second_print"] is None)
    assert {key: tuple(value) for key, value in found.items()} == scorecard_tally(listed, lambda row: row.by_task, after=True)
    block = {row["model"]: row for row in index["scorecard"]["models"]}
    for row in listed:
        for task in scorecard.TASKS:
            cell = block[row.model]["after_feedback"]["by_task"][task]
            assert cell["passes"] == sum(t.passed(True) for t in row.by_task[task])
            assert cell["passed_first"] + cell["passed_after_feedback"] == cell["passes"]


def test_test_first_matches_the_scorecard(index, listed):
    site = site_tally(index, "test_first", lambda row: row["verdict"] == "pass")
    assert site == scorecard_tally(listed, lambda row: row.tested)


def test_the_scorecard_block_is_the_scorecards_own(index, listed):
    block = {row["model"]: row for row in index["scorecard"]["models"]}
    assert list(block) == [row.model for row in listed]
    for row in listed:
        assert block[row.model]["first"]["passes"] == row.passes()
        assert block[row.model]["after_feedback"]["passes"] == row.passes(True)
        if row.tested_trials():
            assert block[row.model]["test_first"]["passes"] == sum(t.passed() for t in row.tested_trials())


def test_the_chart_s_bars_and_cost_per_passing_design_are_the_scorecards_own(index, listed):
    """The scorecard chart draws each model's after-feedback block: its four pieces add up to the counted designs, and
    the cost per passing design is the API cost of every print counted, over the passes. No pass, no value."""
    block = {row["model"]: row["after_feedback"] for row in index["scorecard"]["models"]}
    for row in listed:
        cell = block[row.model]
        rest = cell["trials"] - cell["passes"] - cell["not_graded"]
        assert rest >= 0 and cell["passed_first"] + cell["passed_after_feedback"] + cell["not_graded"] + rest == len(row.all_trials())
        assert cell["passed_first"] == row.passes() and cell["not_graded"] == row.not_graded(True)
        assert cell["cost_usd"] == pytest.approx(row.cost(True))
        if row.passes(True):
            assert cell["cost_per_pass"] == pytest.approx(row.cost(True) / row.passes(True))
        else:
            assert cell["cost_per_pass"] is None
    # the chart's headline row adds up the headline's models: the README's 105 and 151 of 281 when this was written
    pooled = index["scorecard"]["pooled"]
    cells = [block[model] for model in pooled["model_ids"]]
    assert sum(cell["passed_first"] for cell in cells) == pooled["first"]["passes"]
    assert sum(cell["passes"] for cell in cells) == pooled["after_feedback"]["passes"]
    assert sum(cell["trials"] for cell in cells) == pooled["after_feedback"]["trials"] == pooled["first"]["trials"]


def test_the_chart_s_cost_is_the_saved_cost_of_the_prints_it_counts(index):
    """Added up from the trials the page lists: each counted first print, plus its second print when that one counts."""
    by_slug = {row["slug"]: row for row in index["trials"]}
    spend = defaultdict(float)
    for row in index["trials"]:
        cell = row.get("after_feedback")
        if row["group"] == "first" and cell and cell["counted"] and row["task"] in scorecard.TASKS:
            spend[row["model"]] += row["cost_usd"] + (by_slug[cell["second_slug"]]["cost_usd"] if cell["via"] == "second" else 0.0)
    for row in index["scorecard"]["models"]:
        assert spend[row["model"]] == pytest.approx(row["after_feedback"]["cost_usd"], abs=1e-4)


def test_every_saved_trial_appears_exactly_once(index):
    ids = Counter(row["id"] for row in index["trials"])
    assert max(ids.values()) == 1
    saved = {path.parent.relative_to(RUNS).as_posix() for path in RUNS.rglob("grades.json")}
    saved |= {path.parent.relative_to(RUNS).as_posix() for path in RUNS.rglob("loop.json") if path.parent.name != "baseline"}
    saved |= {path.parent.relative_to(RUNS).as_posix() for path in RUNS.rglob("replay.json")}
    assert set(ids) == saved
    assert len({row["slug"] for row in index["trials"]}) == len(ids)


def test_not_graded_is_never_a_pass(index):
    for row in index["trials"]:
        if row["verdict"] == "not graded":
            assert "after_feedback" not in row or row["after_feedback"]["verdict"] != "not graded" or not row["after_feedback"]["passed"]
        if row.get("after_feedback", {}).get("passed"):
            assert row["after_feedback"]["verdict"] == "pass"
        assert row["verdict"] != "pass" or not row["not_graded_checks"] and not row["failed_checks"]


def test_excluded_trials_say_why(index):
    for row in index["trials"]:
        assert row["counted"] or row["excluded_reason"]
    errors = [row for row in index["trials"] if row["verdict"] == "error"]
    assert errors and all(not row["counted"] for row in errors)


def test_a_trial_detail_has_no_home_paths():
    entries = {entry.id: entry for entry in results_site.collect()}
    sample = [entries[key] for key in ("test-first/nut-knob/M3/can_test/anthropic__claude-opus-5.5/t1",
                                       "loop-all/pilot-tripod/tripod-plate/can_ask/anthropic__claude-opus-5.5/t1/feedback")]
    sliced, prompts = scorecard.slice_rows(), {}
    for entry in sample:
        found = results_site.detail(entry, sliced, entries, prompts)
        text = str(found)
        assert "/Users/" not in text and "/home/" not in text
        assert found["transcript"]["url"].endswith(f"results/runs/{entry.id}/transcript.json")
        assert found["findings"]


def test_not_graded_reasons_match_the_failure_tables(index):
    """The site's per-trial reasons, counted once per trial as scripts/failure_tables.py counts them, give the README's
    not-graded table and docs/reference.md's what-went-wrong tables."""
    import failure_tables
    trials, wrong, not_graded, _ = failure_tables.tally(from_meshes=False)
    site_not_graded, site_wrong, site_trials = Counter(), defaultdict(Counter), Counter()
    for row in index["trials"]:
        family = row["task"].split("/")[0]
        if row["kind"] != "trial" or row["run"] in failure_tables.SMOKE_RUNS or family not in failure_tables.FAMILIES:
            continue
        site_trials[family] += 1
        site_not_graded.update({issue["reason_key"] for issue in row["issues"] if issue["kind"] == "not graded"
                                and issue["reason_key"] in failure_tables.NOT_GRADED})
        site_wrong[family].update({failure_tables.NO_DESIGN if issue["kind"] == "error" else issue["reason"]
                                   for issue in row["issues"] if issue["reason_key"] not in failure_tables.NOT_GRADED})
    assert site_trials == trials
    assert site_not_graded == not_graded
    assert {family: Counter(dict(counts)) for family, counts in site_wrong.items() if counts} == \
        {family: Counter({results_site.reader_words(label.replace("`", "")): n for label, n in counts.items()})
         for family, counts in wrong.items() if counts}


def test_the_picture_is_the_failing_part_or_the_largest_final_part(index):
    media = results_site.media()
    for row in index["trials"]:
        design = media.get(row["id"])
        rendered = [part for part in (design or {}).get("parts") or [] if part.get("thumb")]
        if not rendered:
            assert row["thumb"] is None and row["thumb_none_reason"]
            continue
        chosen = next(part for part in rendered if part["id"] == row["thumb_part"])
        assert row["thumb"] == chosen["thumb"]
        assert row["thumb_role"] == ("test print" if chosen["role"] == "coupon" else "final")
        finals = [part for part in rendered if part["role"] == "final"]
        failing = [check for check in row["issues"] if check["kind"] == "failed" and check["part"]
                   and any(results_site.same_part(check["part"], part["id"]) for part in rendered)]
        if not failing and finals:
            assert chosen["role"] == "final"
            assert results_site.volume(chosen) == max(results_site.volume(part) for part in finals)
    declined_test_prints_only = [row for row in index["trials"] if row["verdict"] == "declined" and row["thumb_role"]
                                 and not any(p["role"] == "final" for p in media[row["id"]]["parts"] if p.get("thumb"))]
    assert all(row["thumb_role"] == "test print" for row in declined_test_prints_only)


def test_not_reached_is_apart_from_not_graded_without_changing_verdicts(index):
    reached = 0
    for row in index["trials"]:
        reached += len(row["not_reached_checks"])
        if row["verdict"] == "not graded":
            assert row["not_graded_checks"] or row["not_reached_checks"]
    assert reached
    entries = {entry.id: entry for entry in results_site.collect()}
    entry = entries["crash-replay/pilot-nut-knob/nut-knob/M5/can_ask/qwen__qwen3.8-flash/t1"]
    states = {f.check: results_site.check_state(f) for f in entry.record.findings if f.ok is None}
    assert states == {"R2": "not reached", "R3": "not reached", "R4": "not reached", "R5": "not reached"}
    assert entry.verdict == "fail"


def test_excluded_and_cant_tell_follow_the_scorecard(index, listed):
    block = {row["model"]: row for row in index["scorecard"]["models"]}
    for row in listed:
        saved = [r for r in index["trials"] if r["group"] == "test_first" and r["model"] == row.model]
        tested = block[row.model]["test_first"]
        if not tested:
            continue
        assert tested["excluded"]["count"] + sum(len(row.tested.get(t, [])) for t in results_site.HEADLINE_TASKS) == len(saved)
        assert tested["cant_tell"]["trials"] == sum(t.told_cant_tell for t in row.tested_trials())
        assert tested["cant_tell"]["passes"] == sum(t.passed() and t.told_cant_tell for t in row.tested_trials())
    argon = block["google/gemini-4-argon"]["test_first"]["excluded"]
    assert argon["count"] == 12 and argon["by_task"] == {"bearing-wheel": 2, "nut-knob/M3": 5, "nut-knob/M5": 5}
    pooled = index["scorecard"]["pooled"]
    tested_rows = [row for row in listed if row.tested_trials()]
    assert pooled["after_feedback"]["passes"] == sum(row.passes(True) for row in tested_rows)
    assert pooled["first"]["trials"] == pooled["after_feedback"]["trials"] == sum(len(row.all_trials()) for row in tested_rows)


def test_matched_trial_numbers_use_only_trials_both_conditions_have(index):
    rows = [r for r in index["trials"] if r["counted"] and r["task"] in scorecard.TASKS]
    first = {(r["model"], r["task"], r["trial"]) for r in rows if r["group"] == "first"}
    tested = {(r["model"], r["task"], r["trial"]) for r in rows if r["group"] == "test_first"}
    block = index["scorecard"]["matched_trial_numbers"]
    models = set(index["scorecard"]["test_first_order"])
    assert block["first"]["trials"] == block["test_first"]["trials"] == len({k for k in first & tested if k[0] in models})


@pytest.fixture(scope="module")
def drawn_views():
    if not results_site.VIEWS.exists():
        pytest.skip("scripts/results_site_views.json isn't written here")
    return results_site.views()


def test_every_counted_failure_has_a_view_or_says_why(index, drawn_views):
    """Each counted failed check carries a drawn view's URL or a reason there is none, and the index row's counts agree."""
    entries = {entry.id: entry for entry in results_site.collect()}
    rows = {row["id"]: row for row in index["trials"]}
    for entry_id, entry in entries.items():
        failed = [finding for finding in results_site.counted_of(entry) if finding.ok is False]
        found = [results_site.view_of(entry, finding) for finding in failed]
        for finding, view in zip(failed, found):
            assert view["view"] or view["no_view_reason"], (entry_id, finding.check, finding.part)
            if view["view"]:
                assert view["view"]["url"].startswith("https://") and view["view"]["state"] == "fail"
        drawn = sum(bool(view["view"]) for view in found)
        assert (rows[entry_id]["views"], rows[entry_id]["views_missing"]) == (drawn, len(failed) - drawn)


def test_view_counts_match_the_views_manifest(index, drawn_views):
    """Per design, the drawn views the site attaches to counted failures are the manifest's counted failures with a view."""
    rows = {row["id"]: row for row in index["trials"]}
    for design, entries in drawn_views.items():
        if design not in rows:
            continue
        in_manifest = sum(1 for view in entries if view["state"] == "fail" and not view["test_print"] and view["view"])
        assert rows[design]["views"] == in_manifest, design
    assert sum(row["views"] for row in index["trials"]) > 500


def test_a_failed_check_in_a_trial_detail_carries_its_view(drawn_views):
    entries = {entry.id: entry for entry in results_site.collect()}
    entry = entries["pilot-estoa/estoa-light/can_ask/anthropic__claude-opus-5.5/t4"]
    rows = results_site.finding_rows(entry, entry.record.findings, getattr(entry.record, "declined", None))
    bridges = next(row for row in rows if row["check"] == "bridges" and row["part"] == "back_box")
    assert bridges["view"]["kind"] == "bridge-layer" and bridges["view"]["url"].endswith(".webp")
    assert bridges["view"]["width"] == 900 and bridges["view"]["height"] > 200  # the page reserves this shape
    assert next(row for row in rows if row["check"] == "R1").get("view", "absent") == "absent"  # a pass has no view keys


def test_view_audit_attaches_only_to_existing_views(drawn_views):
    """Each audit entry names a drawn view in the manifest, p is a probability, and view_of carries it as view.audit."""
    audit = results_site.view_audit()
    if not audit:
        pytest.skip("scripts/results_site_view_audit.json isn't written here")
    urls = {view["view"] for entries in drawn_views.values() for view in entries if view["view"]}
    assert set(audit) <= urls
    for answer in audit.values():
        assert 0.0 <= answer["p"] <= 1.0 and isinstance(answer["shows_failure"], bool) and answer["model"]
    entries = {entry.id: entry for entry in results_site.collect()}
    attached = 0
    for entry in entries.values():
        for finding in entry.record.findings:
            view = results_site.view_of(entry, finding).get("view")
            if view and "audit" in view:
                assert view["audit"] == audit[view["url"]]
                attached += 1
    assert attached > 0


def test_view_audit_is_optional(monkeypatch, tmp_path):
    monkeypatch.setattr(results_site, "VIEW_AUDIT", tmp_path / "absent.json")
    results_site.view_audit.cache_clear()
    try:
        assert results_site.view_audit() == {}
    finally:
        results_site.view_audit.cache_clear()
