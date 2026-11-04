"""The README's results are what the saved runs say, so a typed number can't drift from main."""
import sys
from pathlib import Path

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
    for replay in ("crash-replay", "loop-sample", "loop-sample-2"):  # their own summaries, not trials
        assert not list((results_table.RUNS / replay).glob("**/grades.json"))
