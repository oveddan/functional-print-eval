"""The results site's data says what the scorecard says: the same passes and trials per model and task, for the first
print, the second print after feedback and test-first; every saved trial appears exactly once; and a trial that's not
graded is never counted as a pass. No builds and no transcripts read, so it's fast."""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import results_site  # noqa: E402
import results_site_timeline  # noqa: E402
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
    # the chart's headline row adds up the headline's models whose failed first prints were sent back, and only those
    after = index["scorecard"]["pooled"]["after_feedback"]
    cells = [block[model] for model in after["model_ids"]]
    assert sum(cell["passed_first"] for cell in cells) == after["first"]["passes"]
    assert sum(cell["passes"] for cell in cells) == after["passes"]
    assert sum(cell["trials"] for cell in cells) == after["trials"] == after["first"]["trials"]


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
    assert all(not row["counted"] for row in errors)  # none saved since the 2026-11-17 reruns, but never counted


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
    # the 12 trials out-of-credit stopped were run again on 2026-11-17 (changes/2026-11-17-finish-credit-trials.md)
    assert argon["count"] == 0 and argon["by_task"] == {}
    pooled = index["scorecard"]["pooled"]
    tested_rows = [row for row in listed if row.tested_trials()]
    sent_back = [row for row in tested_rows if row.replayed()]
    assert pooled["first"]["trials"] == sum(len(row.all_trials()) for row in tested_rows)
    assert pooled["after_feedback"]["passes"] == sum(row.passes(True) for row in sent_back)
    assert pooled["after_feedback"]["trials"] == sum(len(row.all_trials()) for row in sent_back)


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


def test_every_check_title_has_a_failed_wording():
    """A failed check is shown by what went wrong, never by its success phrase beside a red X."""
    for family, titles in results_site.CHECK_TITLES.items():
        failed = results_site.CHECK_FAILED_TITLES.get(family, {})
        assert set(failed) == set(titles), family
        assert all(failed[check] != titles[check] for check in titles), family


def test_a_failed_finding_is_titled_by_its_failure_and_a_pass_by_the_check():
    entries = {entry.id: entry for entry in results_site.collect()}
    entry = entries["pilot-estoa/estoa-light/can_ask/anthropic__claude-opus-5.5/t4"]
    rows = results_site.finding_rows(entry, entry.record.findings, getattr(entry.record, "declined", None))
    bridges = next(row for row in rows if row["check"] == "bridges" and row["part"] == "back_box")
    assert bridges["title"] == "An overhang can't be bridged" and bridges["check_title"] == "Overhangs can be bridged"
    passed = next(row for row in rows if row["ok"] is True)
    assert passed["title"] == passed["check_title"]
    for row in rows:
        if row["ok"] is None:  # not graded keeps the check's own title
            assert row["title"] == row["check_title"]
    assert results_site.check_title("nut-knob/M3", "R3", False, "grader error: GEOSException: …") == results_site.CRASHED


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


# Photos kept for a reason no saved design has now, each with why, so a misspelled key can't hide here.
PARKED_REASON_PHOTOS = {
    "insert-posts-thinner-than-any-printed",  # Estoa R4 passes for now (Dan, 2026-11-13); back when R4 is tightened
}


def test_reference_photos_belong_to_real_reasons_and_cite_a_record(index):
    """Each recorded photo is keyed like a reason group, says what kind of print it is and names the file its caption
    comes from. One whose reason no design has now (a check relaxed in a regrade) is kept but not shown."""
    photos = results_site.references()
    active = results_site.active_references()
    assert active and set(active) <= set(index["reason_groups"])
    assert set(photos) - set(active) <= PARKED_REASON_PHOTOS, "a photo for a reason no design has: misspelled, or park it here"
    for key, photo in photos.items():
        assert photo["kind"] in ("test print", "Dan's own build"), key
        assert photo["url"].startswith("https://media.danoved.xyz/") and photo["thumb"].startswith("https://media.danoved.xyz/"), key
        assert photo["caption"] and photo["source"] and photo["width"] and photo["height"], key
        assert "coupon" not in photo["caption"].lower(), key


def test_reason_pictures_are_a_recorded_photo_or_a_drawing_of_a_counted_design(index):
    by_slug = {row["slug"]: row for row in index["trials"]}
    pictures = index["reason_pictures"]
    assert set(results_site.active_references()) <= set(pictures)
    for key, picture in pictures.items():
        assert key in index["reason_groups"], key
        if picture["kind"] == "drawing":
            row = by_slug[picture["trial"]]
            assert row["counted"] and any(issue["reason_group"] == key for issue in row["issues"]), key
            assert "wasn't printed" in picture["caption"], key
        else:
            assert picture["url"] == results_site.references()[key]["url"], key


def test_a_check_gets_a_reference_photo_only_for_its_own_reason():
    entries = results_site.collect()
    photos = results_site.references()
    seen = 0
    for entry in entries[:400]:
        groups = {(issue["check"], issue["part"] or "-"): issue["reason_group"] for issue in results_site.issue_rows(entry)}
        for finding in results_site.counted_of(entry):
            photo = results_site.reference_of(entry, finding)
            if photo:
                seen += 1
                assert photos[groups[(finding.check, finding.part or "-")]] == photo
            if finding.ok is True:
                assert (finding.check, finding.part or "-") not in groups
    assert seen


def test_the_page_has_an_introduction_and_share_metadata():
    page = (ROOT / "scripts/results_site/index.html").read_text()
    for needed in ('<h1 class="title">', 'property="og:image"', 'property="og:title"', 'property="og:description"',
                   'name="twitter:card" content="summary_large_image"', 'rel="canonical"'):
        assert needed in page, needed
    assert page.count("<h1") == 1
    assert "coupon" not in page.lower()


def test_a_shared_link_states_the_finding_from_the_scorecard(index):
    pooled = index["scorecard"]["pooled"]
    words = results_site.share_text(pooled)
    first = round(100 * pooled["first"]["passes"] / pooled["first"]["trials"])
    after = round(100 * pooled["after_feedback"]["passes"] / pooled["after_feedback"]["trials"])
    before = round(100 * pooled["after_feedback"]["first"]["passes"] / pooled["after_feedback"]["first"]["trials"])
    assert f"{first}%" in words["share_title"]
    assert f"{first}%" in words["share_description"]
    assert f"{before}% rises to {after}%" in words["share_description"]  # like for like: the same models, before and after
    page = results_site.with_share_text((ROOT / "scripts/results_site/index.html").read_text(), pooled)
    assert "{{" not in page and words["share_title"] in page



def test_after_feedback_counts_only_models_whose_failed_prints_were_sent_back(index, listed):
    """The site once pooled every headline model into "after one round of feedback", so a model whose first prints
    were never sent back (the README's table says "not run") was counted with its first-print result, and the
    caption said each failure had been sent back. The rate is the replayed models', beside their own first prints."""
    pooled = index["scorecard"]["pooled"]
    after = pooled["after_feedback"]
    replayed = {row.model: row for row in listed if row.replayed()}
    assert after["model_ids"] and set(after["model_ids"]) <= set(replayed) and set(after["model_ids"]) <= set(pooled["model_ids"])
    left_out = [model for model in pooled["model_ids"] if model not in after["model_ids"]]
    assert all(model not in replayed for model in left_out)
    assert len(after["not_sent_back"]) == len(left_out) and after["models"] == len(after["model_ids"])
    assert after["first"]["trials"] == after["trials"] and after["first"]["passes"] <= after["passes"]
    # the page offers the set as a filter, so the number opens exactly its designs, and says who is left out
    app = (ROOT / "scripts/results_site/app.js").read_text()
    assert 'const FED_SLUG = "sent-back";' in app and "after.not_sent_back" in app
    # Codex on PR 34: the set is offered wherever it narrows the list, and always while chosen, not only where the
    # larger pooled set also narrows it (under "test prints first" every listed model is a headline model)
    assert "fedHere || state.model === FED" in app and "!fedModels().includes(model)" in app
    assert "each one that didn't pass was sent back once\"" not in app  # the old caption, false for a model not replayed


def test_the_stl_download_is_offered_only_for_a_passing_designs_final_part():
    detail = (ROOT / "scripts/results_site/detail.js").read_text()
    assert 'row.verdict !== "pass" || !part.mesh || part.role !== "final"' in detail
    assert "It hasn't been printed." in detail
    assert (ROOT / "scripts/results_site/stl.js").exists()


def test_the_small_bars_draw_pass_rate_too():
    """The second design review: the table's and the by-part panels' small bars still drew every design at full width.
    They are the chart's rule at a smaller size: filled length is the share that pass, nothing else is drawn."""
    page = (ROOT / "scripts/results_site/app.js").read_text()
    small = page[page.index("function bar(cell"):page.index("function stoppedNote(")]
    assert "width:${(100 * n / cell.trials)" in small
    assert "flex-grow" not in small and "bar-ng" not in small and "bar-rest" not in small
    assert 'h("span", { class: "cell-ng" }, `${cell.not_graded} not graded`)' in page  # said in words instead


def test_a_step_from_the_other_trial_says_whose_title_and_verdict_are_shown():
    """A link with phase=second on a failed first print showed the passing second print under a bare "Fail". The
    header now says the step is saved as another trial, with that trial's verdict, whenever such a step is shown."""
    detail = (ROOT / "scripts/results_site/detail.js").read_text()
    note = detail[detail.index("function otherStepNote("):detail.index("function lowerSections(")]
    assert "phase.slug !== detail.slug" in note and "badge(phase.verdict" in note
    assert "otherStepNote(content.parentElement, phase, detail, context)" in detail


def test_the_trial_dialog_arrives_solid():
    style = (ROOT / "scripts/results_site/style.css").read_text()
    assert "@keyframes rise { from { transform: translateY(6px); } }" in style


def test_every_three_js_file_the_site_loads_is_pinned_by_hash():
    """The 3D library comes from a CDN. Each file the page's scripts import, and the one file GLTFLoader imports in
    turn, has an integrity hash in the import map, so a changed file is refused instead of run."""
    import json
    import re

    frontend = ROOT / "scripts/results_site"
    block = re.search(r'<script type="importmap">\s*(\{.*?\})\s*</script>', (frontend / "index.html").read_text(), re.S)
    importmap = json.loads(block.group(1))
    three, addons = importmap["imports"]["three"], importmap["imports"]["three/addons/"]
    assert re.search(r"/three@\d+\.\d+\.\d+/", three), "the version is exact, not a range"
    wanted = {addons + "utils/BufferGeometryUtils.js"}  # GLTFLoader's own import
    for script in frontend.glob("*.js"):
        for name in re.findall(r'import\("(three[^"]*)"\)', script.read_text()):
            wanted.add(three if name == "three" else addons + name.removeprefix("three/addons/"))
    assert len(wanted) >= 5
    for url in wanted:
        assert importmap["integrity"].get(url, "").startswith("sha384-"), url


def test_a_3d_view_that_finishes_loading_late_is_thrown_away():
    """Security review, 2026-11-14: the stage is reused by every view of a trial, so a mount that finished after the
    reader switched tabs landed in the wrong view. Each mount now knows its turn."""
    detail = (ROOT / "scripts/results_site/detail.js").read_text()
    teardown = detail[detail.index("export function teardown()"):detail.index("export function teardown()") + 120]
    assert "mountSeq += 1" in teardown
    assert "const mine = ++mountSeq;" in detail
    assert "if (mine !== mountSeq || !stage.isConnected) { mounted.dispose(); return; }" in detail


def test_only_the_deploy_job_can_publish():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/site.yml").read_text())
    assert workflow["permissions"] == {"contents": "read"}
    assert "permissions" not in workflow["jobs"]["build"]
    assert workflow["jobs"]["deploy"]["permissions"] == {"pages": "write", "id-token": "write"}


def test_an_unrecognised_url_value_is_repeated_only_in_part():
    app = (ROOT / "scripts/results_site/app.js").read_text()
    assert "const ECHO_MAX = 40;" in app and "value.slice(0, ECHO_MAX)" in app


def test_the_home_page_keeps_its_review_fixes():
    """Two design reviews, 2026-11-13: each mark in the one-line view is one trial, a reason link shows what the
    failure looks like, the long tables fold on a phone."""
    app = (ROOT / "scripts/results_site/app.js").read_text()
    assert 'class: "marks"' in app and "one mark each" in app            # a list of marks, not one link per line
    assert "function reasonHeader()" in app and "function phoneFold(" in app
    assert 'class: "row-reason", "aria-pressed"' in app                   # a reason under a model's name is a button
    assert "Show the table" not in app                                     # a label that is wrong once it is open


def test_reader_words_changes_the_word_and_leaves_a_models_part_ids_alone(index):
    """The site says "test print" where saved text says "coupon", but a model's own part id is its own: the old
    helper turned nut_fit_coupon into "nut_fit_test print" (131 strings on the built site) and the grader's
    "test coupon coupon would find a size", about a part a model named coupon, into "test print test print"."""
    said = results_site.reader_words
    assert said("test coupon coupon would find a size that holds") == "test print “coupon” would find a size that holds"
    assert said("test coupon fit_coupon would find a size") == "test print “fit_coupon” would find a size"
    assert said("test coupon coupon has 5 pocket(s), with 5.58 holding") == "test print “coupon” has 5 pocket(s), with 5.58 holding"
    assert said("declined: no final part: only coupons (unloaded_plate_coupon)") == "declined: no final part: only test prints (unloaded_plate_coupon)"
    assert said("only coupons (coupon)") == "only test prints (coupon)"
    assert said("Its test coupon's pockets are ribbed") == "Its test print's pockets are ribbed"
    assert said("Coupon loop: the coupons came back") == "Test-print loop: the test prints came back"
    assert said("nut_fit_coupon and dovetail-coupon stay") == "nut_fit_coupon and dovetail-coupon stay"
    # Codex on PR 35: the drawing script protects part ids with its own \x00N\x00 tokens before calling this helper;
    # they are not this helper's to restore, and used to raise IndexError
    assert said("test print \x000\x00 has 4 pocket(s)") == "test print \x000\x00 has 4 pocket(s)"
    garbled = re.compile(r"_test print|test print test print|test test print")
    for row in index["trials"]:
        assert not garbled.search(row["summary"] or ""), (row["id"], row["summary"])
    util = (ROOT / "scripts/results_site/util.js").read_text()
    assert "est coupon (\\S+) (would|has)" in util and "[^\\w-]" in util  # the page's reader() follows the same two rules


# ---- "How the checks work" (checks.html): the hand-written explanations must still describe real code and designs ----

@pytest.fixture(scope="module")
def explained_checks():
    return results_site.explained()["checks"]


@pytest.fixture(scope="module")
def entries_by_id():
    return {entry.id: entry for entry in results_site.collect()}


def test_every_explained_check_is_a_real_check_and_names_real_functions(explained_checks):
    """Each entry names a check the task really has, and each grader function it points at still exists, so a renamed
    or deleted grader breaks this page loudly instead of leaving it describing code that's gone."""
    assert 8 <= len(explained_checks) <= 14
    for entry in explained_checks:
        family = entry["task"]
        if family == results_site.EVERY_PART:
            known = set(results_site.GENERIC_CHECKS)
        else:
            task = next(task for task in results_site.TASK_NAMES if task.split("/")[0] == family)
            known = {requirement.id for requirement in results_site.task_files.load(task).requirements}
        assert entry["check"] in known, entry
        assert entry["code"], entry["check"]
        for code in entry["code"]:
            assert results_site.code_line(code["file"], code["function"]), f"{code['file']} has no {code['function']}"
        for field in ("tests", "record", "not_graded"):
            assert entry[field].strip(), (entry["check"], field)
        assert entry["how"], entry["check"]
        if entry.get("photo"):
            assert entry["photo"] in results_site.references(), entry["photo"]


def _walk(value, path):
    for key in path:
        if isinstance(value, (list, tuple)):
            value = value[int(key)]
        elif isinstance(value, dict):
            value = value[key]
        else:
            value = getattr(value, key)
    return value


def _where_the_code_keeps_it(constant):
    """The value a `constants` entry of scripts/results_site_checks.yaml points at, read from the code, the catalog,
    the task's requirements or the recorded prints."""
    import importlib
    import inspect

    if "code" in constant:
        parts = constant["code"].split(".")
        for cut in range(len(parts) - 1, 0, -1):
            try:
                return _walk(importlib.import_module(".".join(parts[:cut])), parts[cut:])
            except ModuleNotFoundError:
                continue
        raise AssertionError(constant)
    if "printer" in constant:
        return _walk(yaml.safe_load((ROOT / "catalog/printer.yaml").read_text()), constant["printer"].split("."))
    if "default" in constant:
        name, argument = constant["default"].split()
        module, function = name.rsplit(".", 1)
        return inspect.signature(getattr(importlib.import_module(module), function)).parameters[argument].default
    if "requirement" in constant:
        family, check, path = constant["requirement"].split()
        task = next(task for task in results_site.TASK_NAMES if task.split("/")[0] == family)
        requirement = next(found for found in results_site.task_files.load(task).requirements if found.id == check)
        return _walk(requirement.args, path.split("."))
    if "nut_records" in constant:
        from pbe.graders import nuts

        nut, shape = constant["nut_records"].split()
        return [list(row) for row in nuts._measured()[(nut, shape)]]
    if "bolt_holes" in constant:
        from pbe.graders import bolt_fits

        return [list(row) for row in bolt_fits.printed_holes(constant["bolt_holes"])]
    raise AssertionError(f"a constant with no known source: {constant}")


def test_every_threshold_the_checks_page_states_is_the_code_s(explained_checks):
    """The page's prose is hand-written. Each threshold it states is listed under `constants` with where the code
    keeps it; a grader, catalog or requirements change that moves one fails here until the prose is re-read."""
    compared = 0
    for entry in explained_checks:
        prose = " ".join(str(entry.get(field, "")) for field in ("tests", "how", "record", "not_graded", "weak", "inference"))
        for constant in entry.get("constants", []):
            assert _where_the_code_keeps_it(constant) == pytest.approx(constant["value"]) if not isinstance(constant["value"], list) \
                else _where_the_code_keeps_it(constant) == constant["value"], (entry["check"], constant)
            if not isinstance(constant["value"], list):
                shown = constant.get("shown", f"{constant['value']:g}")
                assert shown in prose, f"{entry['task']} {entry['check']}: the prose doesn't state {shown} ({constant})"
            compared += 1
    assert compared >= 50


def test_explained_prose_says_test_print_not_coupon(explained_checks):
    source = results_site.explained()
    texts = [*source["intro"], *source["states"].values(), source["nearest_print"]]
    for entry in explained_checks:
        texts += [entry["tests"], entry["record"], entry["not_graded"], entry.get("weak") or "", *entry["how"]]
        texts += [example.get("note") or "" for example in entry.get("examples") or []]
    for text in texts:
        assert "coupon" not in text.replace("-coupons.yaml", ""), text


def test_every_example_exists_with_the_outcome_it_is_shown_for(explained_checks, entries_by_id):
    """A regrade or a grader change that moves an example's result fails here, not silently on the page."""
    for entry in explained_checks:
        outcomes = [example["outcome"] for example in entry["examples"]]
        assert "fail" in outcomes or "not graded" in outcomes, entry["check"]
        for example in entry["examples"]:
            assert example["trial"] in entries_by_id, example["trial"]
            design = entries_by_id[example["trial"]]
            assert design.group == "first" and design.counted, example["trial"]
            assert results_site.check_applies(entry["task"], design.task), example["trial"]
            part = example.get("part", "-")
            found = [f for f in results_site.counted_of(design) if f.check == entry["check"] and (f.part or "-") == part]
            assert len(found) == 1, (example["trial"], entry["check"], part)
            assert results_site.check_state(found[0]) == example["outcome"], (example["trial"], entry["check"], found[0].detail)


def test_every_example_has_its_drawing(explained_checks, entries_by_id):
    """Every example shows the drawing scripts/results_site_check_views.py made of it from today's code, in the state
    the example is shown for (a grader change means a redraw). Code that didn't run has no shape to draw."""
    if not results_site.CHECK_VIEWS.exists():
        pytest.skip("the check views manifest isn't here")
    for entry in explained_checks:
        for example in entry["examples"]:
            shown = results_site.example_of(example, entry["task"], entry["check"], entries_by_id)
            if entry["check"] == "builds":
                assert shown["view"] is None and shown["no_view_reason"]
                continue
            assert shown["view"] and shown["view"]["url"].startswith("https://"), (example["trial"], entry["check"], shown["no_view_reason"])
            # a pass that rests on a test print or template rescue is never shown as a plain pass
            assert not shown["via_test_print"] or (example.get("label") and example.get("note")), example["trial"]
            word = {"pass": ": passes.", "fail": ": fails.", "not graded": ": not graded."}[example["outcome"]]
            assert word in shown["view"]["caption"], (example["trial"], entry["check"])


def test_the_checks_page_data_and_its_links(index, entries_by_id):
    page = results_site.checks_page(list(entries_by_id.values()), index["trials"])
    anchors = {section["anchor"] for section in page["checks"]}
    assert len(anchors) == len(page["checks"])
    for section in page["checks"]:
        counts = section["counts"]
        assert counts["first_prints"] > 0
        # every design in the denominator is accounted for once, declined and no design included
        parts = ("failed", "not_graded", "passed", "not_reached", "no_part_built", "declined", "no_design")
        assert sum(counts[key] for key in parts) == counts["first_prints"], section["anchor"]
        assert section["counts"]["failed"] + section["counts"]["not_graded"] > 0, section["anchor"]
        assert all(reason["key"] in index["reason_groups"] for reason in section["counts"]["reasons"])
        assert all(code["url"].startswith(results_site.REPO) and "#L" in code["url"] for code in section["code"])
    # a check in a trial's detail links to its own section, and only an explained check links at all
    entry = entries_by_id["pilot-tripod/tripod-plate/can_ask/anthropic__claude-haiku-5.5/t10"]
    links = {row["check"]: row["explained"] for row in results_site.finding_rows(entry, entry.record.findings, None)}
    assert links["bridges"] == "checks.html#bridges" and links["R3"] == "checks.html#tripod-plate-R3"
    assert links["R5"] is None and links["bed_fit"] is None
    assert {link.split("#")[1] for link in links.values() if link} <= anchors
    text = json.dumps(page)
    assert "/Users/" not in text and "/home/" not in text


def test_the_check_views_manifest_has_no_local_paths():
    if not results_site.CHECK_VIEWS.exists():
        pytest.skip("no check views manifest")
    text = results_site.CHECK_VIEWS.read_text()
    assert "/Users/" not in text and "results/local" not in text
    for view in json.loads(text)["views"]:
        assert view["state"] in ("pass", "fail", "not graded") and view["view"].startswith("https://media.danoved.xyz/print-build-eval/site/")


def test_the_checks_page_is_linked_from_the_home_page_and_shares_its_styles():
    home = (ROOT / "scripts/results_site/index.html").read_text()
    assert home.count('href="checks.html"') == 2  # the header and "How to read a result"
    page = (ROOT / "scripts/results_site/checks.html").read_text()
    assert 'href="style.css"' in page and 'src="checks.js"' in page
    assert 'from "./util.js"' in (ROOT / "scripts/results_site/checks.js").read_text()


# ---- the assembled views of the wheel, the tripod plate and the knob (scripts/hardware_scene.py) ----

HARDWARE_TASKS = ("bearing-wheel", "tripod-plate", "nut-knob")
SAVED_FINDINGS = ("grades.json", "loop.json", "replay.json")


def saved_record(design_id):
    for name in SAVED_FINDINGS:
        path = RUNS / design_id / name
        if path.exists():
            return json.loads(path.read_text())
    return None


def test_a_fit_outcome_comes_only_from_the_saved_words():
    import hardware_scene
    said = lambda check, ok, detail: SimpleNamespace(check=check, ok=ok, detail=detail)  # noqa: E731
    assert hardware_scene.wheel_outcome(said("R3", True, "22.14 mm: it presses in and holds upside down")) == (22.14, "seats")
    assert hardware_scene.wheel_outcome(said("R3", True, "21.98 mm: a 22.05 mm seat wouldn't take the bearing; test coupon c "
                                                         "would find a size that holds, and d moves the seat")) == (21.98, "stops")
    assert hardware_scene.wheel_outcome(said("R3", False, "22.39 mm: from 22.4 mm the bearing was too loose and fell out"))[1] == "falls"
    assert hardware_scene.wheel_outcome(said("R3", None, "22.07 mm: between 22.05, too tight, and 22.1, which held")) == (None, None)
    assert hardware_scene.wheel_outcome(said("R3", None, "no seat to read")) == (None, None)
    assert hardware_scene.nut_outcome(said("R4", True, "pocket 8.00 across flats, +0.00 over the 8.0 nut: prints say holds")) == "seats"
    assert hardware_scene.nut_outcome(said("R4", False, "pocket 5.40 across flats, -0.10 over the 5.5 nut: prints say won't go in; x")) == "stops"
    assert hardware_scene.nut_outcome(said("R4", False, "pocket 8.30 across flats, +0.30 over the 8.0 nut: prints say falls out")) == "falls"
    assert hardware_scene.nut_outcome(said("R4", None, "pocket 8.20 across flats, +0.20 over the 8.0 nut: prints say loose")) is None
    assert hardware_scene.nut_outcome(said("R4", None, "pocket with ribs: round 3's prints of that shape say not measured")) is None
    through = said("R3", True, "6.60 mm clear at its tightest: the bolt goes through by hand (round 3)")
    assert hardware_scene.tripod_outcome(through, said("R4", True, "recess 15.2 mm across and 5.0 mm deep"))[0] == "seats"
    assert hardware_scene.tripod_outcome(through, said("R4", False, "recess 13.00 mm across: the 13 mm one was too tight for this head"))[:2] == ("stops", "head")
    assert hardware_scene.tripod_outcome(said("R3", False, "6.20 mm clear at its tightest: a 6.35 mm bolt won't pass"), None)[:2] == ("stops", "tip")
    assert hardware_scene.tripod_outcome(said("R3", False, "6.35 mm clear at its tightest: round 3's 1/4-20 only screwed through"), None)[0] is None


def test_assembled_scenes_draw_the_hardware_where_the_saved_findings_say():
    """Every built wheel, plate and knob design has an assembled view or a stated reason. A view's printed part has a
    matrix, its hardware has its own colors, and a fit is played only with the outcome the saved finding's words give,
    the same outcome on every piece, along a unit axis, stopping short of seated only when it stops."""
    import hardware_scene
    media = results_site.media()
    outcome_of = {"bearing-wheel": lambda f: hardware_scene.wheel_outcome(f)[1], "nut-knob": hardware_scene.nut_outcome}
    scenes = 0
    for design_id, design in media.items():
        record = saved_record(design_id)
        family = (record or {}).get("task", "").split("/")[0]
        if family not in HARDWARE_TASKS or not design["built"]:
            continue
        scene = design["scene"]
        assert scene or design.get("scene_none"), design_id
        if not scene:
            continue
        scenes += 1
        layers = {layer["key"]: layer for layer in scene["layers"]}
        assert layers["printed"]["parts"][0]["part"] and len(layers["printed"]["parts"][0]["matrix"]) == 16
        assert len({layer["color"] for layer in scene["layers"]}) == len(scene["layers"])
        assert {"bolt"} <= set(layers) <= {"printed", "bearings", "bolt", "nut"}
        fits = [part["fit"] for layer in scene["layers"] for part in layer["parts"] if part.get("fit")]
        assert bool(fits) == bool(scene.get("fit")), design_id
        assert scene.get("fit") or scene.get("fit_note"), design_id
        if not fits:
            continue
        saved = {f["check"]: f for f in (record.get("findings") or []) if not f.get("test_print")}
        named = saved[scene["fit"]["check"]]
        assert scene["fit"]["detail"] == named["detail"]
        if family in outcome_of:
            assert outcome_of[family](SimpleNamespace(**named)) == scene["fit"]["outcome"]
        else:
            r4 = SimpleNamespace(**saved["R4"]) if "R4" in saved else None
            assert hardware_scene.tripod_outcome(SimpleNamespace(**saved["R3"]), r4)[0] == scene["fit"]["outcome"]
        assert named["ok"] is not None, f"{design_id}: a fit plays on a check that isn't graded"
        assert scene["fit"]["assumed"] == ("assumed from the" in named["detail"].split(";")[0])
        for fit in fits:
            assert fit["outcome"] == scene["fit"]["outcome"]
            assert abs(sum(v * v for v in fit["axis"]) - 1) < 1e-4 and fit["start"] > 0
            assert fit["rest"] == ("stopped" if fit["outcome"] == "stops" else "seated"), design_id
    if scenes == 0:
        pytest.skip("the media manifest here has no wheel, plate or knob scenes")


def test_a_not_graded_check_never_plays_and_a_rescued_pass_says_so():
    import hardware_scene
    said = lambda check, ok, detail: SimpleNamespace(check=check, ok=ok, detail=detail)  # noqa: E731
    unsettled = said("R4", None, "pocket 5.25 across flats, -0.25 over the 5.5 nut: prints say won't go in; test coupon "
                                 "fit-coupon has 3 pocket(s), and no print has settled whether any of them holds")
    assert hardware_scene.nut_outcome(unsettled) is None
    rescued = said("R4", True, "pocket 7.85 across flats, -0.15 over the 8.0 nut: prints say won't go in; test coupon "
                               "press_coupon has 4 pocket(s), with 7.95 holding, and the pocket follows param pocket_af")
    assert hardware_scene.nut_outcome(rescued) == "stops" and "set from that test print" in hardware_scene.rescued(rescued)
    assert hardware_scene.rescued(said("R3", True, "21.98 mm: a 22.05 mm seat wouldn't take the bearing; test coupon c "
                                                   "would find a size that holds, and d moves the seat"))
    assert hardware_scene.rescued(said("R4", True, "pocket 8.00 across flats, +0.00 over the 8.0 nut: prints say holds")) is None
    through = said("R3", True, "6.60 mm clear at its tightest: the bolt goes through by hand (round 3)")
    head_unknown = said("R4", None, "recess 14.68 mm across: between 13, too tight, and 15, which fit")
    assert hardware_scene.tripod_outcome(through, head_unknown)[0] is None  # the head's motion follows R4
    assumed = said("R4", True, "pocket 5.30 across flats, -0.20 over the 5.5 nut: prints say holds (assumed from the -0.2 mm "
                               "clearance print, within the 0.2 mm assumption tolerance)")
    assert hardware_scene.saying(assumed, "seats")["assumed"] is True


@pytest.mark.parametrize("size", ["M3", "M5", "M8"])
def test_the_nut_is_drawn_at_the_catalog_size(size):
    """Across its flats the drawn nut is the catalog's af, whichever way it's turned; only its corners are chamfered."""
    import math

    import hardware_scene
    from shapely.affinity import rotate
    from shapely.geometry import Point

    from pbe.parts import catalog
    af = catalog.resolve(f"ISO 4032 {size}")["af"]
    for degrees in (0, 17, 45):
        outline = hardware_scene.nut_outline(Point(0, 0), af, degrees)
        widths = []
        for turn in range(0, 180, 1):
            minx, _, maxx, _ = rotate(outline, turn, origin=(0, 0)).bounds
            widths.append(maxx - minx)
        assert min(widths) == pytest.approx(af, abs=0.01)
        assert max(widths) < af / math.cos(math.radians(30))  # corners chamfered, not sharp


def test_a_piece_that_stops_rests_where_it_stops():
    """The still view never shows a fit the record says can't happen: a "stops" piece is stored at the opening."""
    import hardware_scene
    import numpy as np
    import trimesh
    scene = hardware_scene.Scene(np.eye(4), "knob")
    scene.add("nut", trimesh.creation.box(extents=(1, 1, 1)), (np.array([0.0, 0.0, -1.0]), 10.0, "stops", 3.0))
    scene.add("bolt", trimesh.creation.box(extents=(1, 1, 1)), (np.array([0.0, 0.0, -1.0]), 10.0, "seats", None))
    stopped, seated = scene.layers["nut"][0], scene.layers["bolt"][0]
    assert stopped["mesh_obj"].bounds[0][2] == pytest.approx(-0.5 + 7.0)  # moved back out along the way in
    assert stopped["fit"] == {"axis": [0.0, 0.0, -1.0], "start": 3.0, "outcome": "stops", "rest": "stopped"}
    assert seated["mesh_obj"].bounds[0][2] == pytest.approx(-0.5) and seated["fit"]["start"] == 10.0


def test_a_pass_that_rests_on_its_test_print_is_flagged_for_the_stl():
    entries = {entry.id: entry for entry in results_site.collect()}
    for design_id in ("pilot-nut-knob/nut-knob/M5/can_ask/deepseek__deepseek-v4.1-flash/t2",
                      "pilot-wheel/bearing-wheel/can_ask/openai__gpt-6.1-sol/t8"):
        entry = entries[design_id]
        flagged = results_site.rests_on_test_print(results_site.counted_of(entry))
        assert entry.verdict == "pass" and flagged, design_id
        for found in flagged:  # a model's own part id ("fit_coupon") is left as it is, in quotes
            words = re.sub(r"“[^”]*”", "", found["as_drawn"] + " " + found["rescue"])
            assert not re.search(r"(?<![\w-])coupons?(?![\w-])", words)
    plain = entries["pilot-nut-knob/nut-knob/M5/can_ask/anthropic__claude-opus-5.5/t1"]
    assert results_site.rests_on_test_print(results_site.counted_of(plain)) == []


def test_estoa_scenes_show_the_led_disk_and_the_plug_only_where_r3_passed():
    media = results_site.media()
    estoa = 0
    for design_id, design in media.items():
        record = saved_record(design_id)
        if not design.get("scene") or (record or {}).get("task") != "estoa-light":
            continue
        estoa += 1
        keys = {layer["key"] for layer in design["scene"]["layers"]}
        sub = yaml.safe_load((RUNS / design_id / "submission.yaml").read_text())
        disks = {item["id"] for item in sub.get("hardware") or [] if item.get("ref") == "own:led-disk"}
        placed_disk = any(item.get("item") in disks for item in (sub.get("assembly") or {}).get("items") or [])
        assert ("disk" in keys) == placed_disk, design_id
        counted = [] if record.get("declined") else [f for f in record.get("findings") or [] if not f.get("test_print")]
        if "plug" in keys:
            assert any(f["check"] == "R3" and f["ok"] is True for f in counted), design_id
    if estoa == 0:
        pytest.skip("the media manifest here has no Estoa scenes")


def test_a_scene_says_marked_in_red_only_when_it_has_a_red_layer():
    """Codex on PR 26: the hardware views list failed checks but draw no red, so the caption mustn't point at red."""
    detail = (ROOT / "scripts/results_site/detail.js").read_text()
    assert 'layer.key === "problem" && layer.parts.some((part) => part.mesh)' in detail
    assert "not marked in this view" in detail


# ---- the timeline on a trial's page ----

@pytest.fixture(scope="module")
def timelines():
    entries = {entry.id: entry for entry in results_site.collect()}
    reasons = lambda entry: [row["reason"] for row in results_site.issue_rows(entry)]  # noqa: E731
    return entries, {key: results_site_timeline.timeline(entry, entries, reasons) for key, entry in entries.items()}


def test_a_timeline_accounts_for_what_the_trial_asked_and_states_each_saved_verdict(timelines):
    entries, found = timelines
    by_slug = {entry.slug: entry for entry in entries.values()}
    for key, phases in found.items():
        entry = entries[key]
        assert len({phase["key"] for phase in phases}) == len(phases), key
        own = [phase for phase in phases if phase["slug"] == entry.slug]
        assert sum(phase["count"] for phase in own if phase["kind"] == "asked") == len(getattr(entry.record, "measures", None) or []), key
        rounds = [phase for phase in own if phase["kind"] == "round"]
        assert [phase["round"] for phase in rounds] == list(range(1, len(getattr(entry.record, "test_prints", None) or []) + 1)), key
        for phase in rounds:
            assert phase["pieces"] == len(entry.record.test_prints[phase["round"] - 1]["parts"]), key
        assert [phase["verdict"] for phase in own if phase["kind"] == "design"] == [entry.verdict], key
        for phase in phases:
            # the page's own words say "test print"; a model's question, quoted as it asked it, keeps its words
            assert "coupon" not in (phase["label"] + re.sub(r"“[^”]*”", "", phase["line"])).lower(), (key, phase)
            if phase["kind"] == "design":
                # the label says the saved verdict of the trial it points at, so "not graded" never reads as a pass
                assert phase["label"].endswith(f": {by_slug[phase['slug']].verdict}"), (key, phase)
                assert ("passes" in phase["line"]) == (phase["verdict"] == "pass"), (key, phase)


def test_a_first_print_and_its_second_print_share_one_timeline(timelines):
    entries, found = timelines
    paired = [entry for entry in entries.values() if entry.kind == "trial" and entry.second_print]
    assert paired
    for first in paired:
        phases = found[first.id]
        assert phases == found[first.second_print], first.id
        assert [phase["key"] for phase in phases if phase["kind"] != "asked"] == ["design", "told", "second"], first.id
        assert phases[-1]["slug"] == results_site.slug_of(first.second_print) and phases[-1]["label"].startswith("Second print: ")
        assert next(phase for phase in phases if phase["key"] == "design")["label"].startswith("First print: ")


def test_a_trial_that_only_handed_in_a_design_has_one_phase(timelines):
    entries, found = timelines
    for key, phases in found.items():
        entry = entries[key]
        alone = entry.kind == "trial" and not entry.second_print and not entry.record.measures and not entry.record.test_prints
        assert (len(phases) == 1) == alone, key


def test_a_timeline_follows_the_transcript_s_order():
    entries = {entry.id: entry for entry in results_site.collect()}
    # this trial asked for test prints first and a measurement after them
    entry = entries["test-first/nut-knob/M5/can_test/openai__gpt-6.1-sol/t10"]
    phases = results_site_timeline.timeline(entry, entries, lambda e: [])
    assert [phase["kind"] for phase in phases] == ["round", "asked", "design"]
    assert phases[-1]["label"] == f"Final design: {entry.verdict}"


def test_a_test_print_round_s_renders_are_of_the_pieces_that_round_asked_for():
    drawn = results_site_timeline.round_media()
    if not drawn:
        pytest.skip("the renders of the asked-for test prints aren't here")
    entries = {entry.id: entry for entry in results_site.collect()}
    assert set(drawn) <= set(entries)
    for key in drawn:
        for round_ in results_site.test_prints_of(entries[key]):
            asked = {part["id"] for part in round_["parts"]}
            if round_["media"]:
                assert {part["id"] for part in round_["media"]["parts"]} | set(round_["not_built"]) == asked, key
                assert all(part["role"] == "coupon" and part["role_label"] == "test print" for part in round_["media"]["parts"])
            else:
                assert round_["media_none"], key
    assert "/Users/" not in results_site_timeline.ROUNDS_MEDIA.read_text()


def test_the_page_draws_no_timeline_for_a_single_phase_and_checks_its_numbers():
    detail = (ROOT / "scripts/results_site/detail.js").read_text()
    assert "if (phases.length > 1) return renderWithTimeline(" in detail
    assert "timelineProblems(detail)" in (ROOT / "scripts/results_site/app.js").read_text()
    # Codex on PR 30: a phase that loads after its trial was closed or replaced mustn't draw or tear down the next view
    assert "() => turn === shown && control.panel.isConnected" in detail


def test_a_view_is_never_redrawn_from_missing_part_files_and_saved_as_current():
    """Codex on PR 26: the scene-only redraw read each part's mesh from folder/parts, which isn't committed, without
    building it again if it had gone, then saved the design under a current key with no view, so no later run retried.
    It builds the parts first, and a redraw that fails redoes the design in full instead of saving."""
    import inspect

    import results_site_media as media
    redraw = inspect.getsource(media.redraw_scene)
    assert "ensure_built(folder, sub)" in redraw and "except" not in redraw
    work = inspect.getsource(media.work)
    assert "record = None" in work and "if record is not None:" in work
