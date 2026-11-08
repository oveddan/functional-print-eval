"""The README's not-graded examples: for each reason a check couldn't be graded, a small render of one saved design
that hit it. No model calls.

    uv run python scripts/not_graded_figures.py

Picks, for each reason in failure_tables.NOT_GRADED, the first `can_ask` trial (by run, model and trial number) whose
design built and that was not graded for that reason, preferring one with no other reason, so the picture shows that
one thing. Draws the failure figures' cross-sections: a nut pocket cut straight across with the nut drawn in, a wheel cut down
the middle with its bearings and bolt, a tripod plate cut across; a roof ledge from below, the ungraded ledge in red. Writes docs/media/not-graded/<slug>.png and docs/media/not-graded/examples.json (which trial each is), which
scripts/failure_tables.py reads to put the pictures in its not-graded table.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import failure_figures  # noqa: E402  the cross-sections with hardware drawn in
import failure_tables  # noqa: E402  the reasons and their words
import results_page  # noqa: E402  the diagnosis of each trial's findings
import scorecard  # noqa: E402  short model names
import task_figures  # noqa: E402  building a saved design's main part
import walkthrough_figures as walk  # noqa: E402

from pbe.graders import bridges  # noqa: E402
from pbe.runner.trial_record import TrialRecord  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs"
OUT = ROOT / "docs/media/not-graded"
EXAMPLES = OUT / "examples.json"
POCKET_CLOSE_UP_MM = 10.0  # around the part's centre, so a nut pocket fills the picture


def slug(reason: str) -> str:
    words = failure_tables.NOT_GRADED[reason][0].lower()
    return re.sub(r"[^a-z0-9]+", "-", words).strip("-")


def candidates():
    """(reason, run, folder, record, other reasons) for every not-graded reason a can_ask trial with a design hit."""
    audit = json.loads(results_page.AUDIT.read_text())
    for run_dir in sorted(path for path in RUNS.iterdir() if path.is_dir() and path.name not in failure_tables.SMOKE_RUNS):
        trials = sorted(TrialRecord.all_in(run_dir), key=lambda pair: (pair[1].model, pair[1].task, pair[1].trial))
        for folder, record in trials:
            if record.condition != "can_ask" or not (folder / "submission.yaml").exists():
                continue
            issues = results_page.issues_of(run_dir.name, record, audit.get(failure_tables.trial_key(run_dir.name, record)), set())
            reasons = {issue["family"] for issue in issues if issue["family"] in failure_tables.NOT_GRADED}
            for reason in reasons:
                yield reason, run_dir.name, folder, record, reasons - {reason}


def picks() -> dict:
    """One trial per reason: the first with no other reason, else the first."""
    chosen = {}
    for reason, run, folder, record, others in candidates():
        if reason not in chosen or (chosen[reason][3] and not others):
            chosen[reason] = (run, folder, record, others)
    return chosen


def figure_for(reason: str, folder: Path, record) -> "failure_figures.Figure":
    """The failure figures' cross-section that shows the reason: a nut pocket cut straight across where it's tightest
    with the nut drawn in, so ribs, clips and a pocket too tight show; a wheel cut down the middle with its bearings
    and bolt; a tripod plate cut across."""
    trial = folder.relative_to(RUNS).as_posix()
    if record.task.startswith("nut-knob"):
        return failure_figures.Figure(slug(reason), trial, "", "across", nut=f"ISO 4032 {record.task.split('/')[1]}")
    if record.task == "bearing-wheel":
        return failure_figures.Figure(slug(reason), trial, "", "side", bearings=True)
    return failure_figures.Figure(slug(reason), trial, "", "side")


def draw(reason: str, folder: Path, record, png: Path) -> None:
    if "roof ledge" in reason:  # from below, the ungraded ledge in red
        with tempfile.TemporaryDirectory() as scratch:
            mesh = task_figures.main_part(folder / "submission.yaml", Path(scratch))
        ledge = next((found for found in bridges.overhangs(mesh) if found.narrow and not found.ok), None)
        walk.render(mesh, png, azim=-55, failed=ledge, elev=-40)
        return
    figure = figure_for(reason, folder, record)
    try:
        drawn = failure_figures.draw(figure)
    except AttributeError:  # no pocket the nut checker can read (that's the reason): cut it down the middle instead
        figure.view = "side"
        drawn = failure_figures.draw(figure)
    png.write_bytes(drawn.read_bytes())
    if drawn != png:
        drawn.unlink()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    examples = {}
    for reason, (run, folder, record, _) in sorted(picks().items()):
        png = OUT / f"{slug(reason)}.png"
        draw(reason, folder, record, png)
        examples[reason] = {"image": png.name, "model": scorecard.SHORT.get(record.model, record.model),
                            "task": record.task, "trial": record.trial, "run": run}
        print(f"{png.relative_to(ROOT)}: {examples[reason]['model']}, {record.task} t{record.trial}")
    EXAMPLES.write_text(json.dumps(examples, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
