"""The README's results are what the saved runs say, so a typed number can't drift from main."""
import sys
import tempfile
from pathlib import Path

import pytest
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import results_table  # noqa: E402


def test_the_readmes_results_match_the_saved_runs():
    text = results_table.README.read_text()
    assert results_table.readme_with(text, results_table.counted_records()) == text, \
        "run: uv run python scripts/results_table.py --write"


def test_counts_leave_out_the_smoke_tests_and_the_replays():
    saved = [path for path in results_table.RUNS.glob("*/**/grades.json")
             if path.relative_to(results_table.RUNS).parts[0] not in results_table.SMOKE_RUNS]
    assert len(results_table.counted_records()) == len(saved)
    for replay in ("crash-replay", "loop-sample", "loop-sample-2", "loop-tripod"):  # their own summaries, not trials
        assert not list((results_table.RUNS / replay).glob("**/grades.json"))



def bridges_alone_trials():
    """(folder, record) for every counted trial that fails on `bridges` alone."""
    from pbe.runner.trial_record import TrialRecord
    return [(folder, record) for run_dir in sorted(path for path in results_table.RUNS.iterdir()
                                                   if path.is_dir() and path.name not in results_table.SMOKE_RUNS)
            for folder, record in TrialRecord.all_in(run_dir) if results_table.fails_on_bridges_alone(record)]


BRIDGES_ALONE = bridges_alone_trials()


def test_every_listed_exception_is_a_trial_that_fails_on_bridges_alone():
    assert set(results_table.NOT_HOLED_ROOFS) <= {results_table.trial_key(record) for _, record in BRIDGES_ALONE}


@pytest.mark.parametrize("folder, record", BRIDGES_ALONE, ids=[str(folder.relative_to(results_table.RUNS)) for folder, _ in BRIDGES_ALONE])
def test_a_bridges_alone_trial_is_a_holed_roof_unless_listed(folder, record):
    """The assumption row counts only holed roofs, so NOT_HOLED_ROOFS has to be what the meshes say."""
    from pbe.graders.bridges import is_holed_roof, overhangs
    from pbe.parts import submission
    from pbe.parts.build import build_parts, require_sandbox
    try:
        require_sandbox()
    except RuntimeError as e:
        pytest.skip(f"parts can't be built here: {e}")
    failed = {finding.part for finding in record.counted_findings if finding.check == "bridges" and finding.ok is False}
    with tempfile.TemporaryDirectory() as out:
        built = build_parts(submission.load(folder / "submission.yaml"), out)
        holed = any(is_holed_roof(found) for part in failed for found in overhangs(trimesh.load(built[part].stl, force="mesh")))
    assert holed is (results_table.trial_key(record) not in results_table.NOT_HOLED_ROOFS)
