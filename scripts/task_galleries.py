"""The README's per-task galleries: a few saved designs that pass and a few that fail, each labelled with its model,
its trial and, for a failure, the check it failed. No model calls.

    uv run python scripts/task_galleries.py

Picks, for each task, up to four passing and four failing `can_ask` designs from different models (first print, the
design as handed in), in a fixed order so a rerun draws the same ones. A failure whose code didn't build has nothing
to draw and is skipped. A failure is drawn from below, with a failing roof or ledge in red; a failed knob
is cut through instead, with the nut drawn in: across the pocket for a fit, down the middle for a roof.
Writes docs/media/tasks/<task>-gallery.png with the walkthrough's renderer.
"""
import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import failure_figures  # noqa: E402  the cut across a nut pocket, with the nut drawn in
import task_figures  # noqa: E402  the same part picking and rendering as the reference pictures
import walkthrough_figures as walk  # noqa: E402
import scorecard  # noqa: E402  its short model names

import matplotlib.pyplot as plt  # noqa: E402

from pbe.graders import bridges  # noqa: E402
from pbe.runner import tasks  # noqa: E402
from pbe.runner.trial_record import TrialRecord  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs"
OUT = ROOT / "docs/media/tasks"
TASKS = {"tripod-plate": ["pilot-tripod"], "bearing-wheel": ["pilot-wheel"],
         "nut-knob": ["pilot-nut-knob-2", "pilot-nut-knob"]}
PER_ROW = 4
GENERIC = {"bridges": "a roof or ledge printed over air", "connected_bodies": "a part in pieces",
           "bed_fit": "too big for the bed", "builds": "code didn't run"}


def short_model(model: str) -> str:
    return scorecard.SHORT.get(model, model.split("/")[-1])


def failed_reason(record: TrialRecord) -> str:
    """The first counted check that failed: "Failed:" and what went wrong for a general check, "Not met:" and the
    requirement for a task's own, since a requirement says what the part should do, not what went wrong."""
    texts = {req.id: req.text for req in tasks.load(record.task).requirements}
    for finding in record.counted_findings:
        if finding.ok is False:
            if finding.check in GENERIC:
                return "Failed: " + GENERIC[finding.check]
            text = texts.get(finding.check, finding.check)
            return "Not met: " + text[0].lower() + text[1:]
    return ""


def picks(task: str) -> tuple[list, list]:
    """Up to PER_ROW passes and PER_ROW drawable failures, one per model, in a fixed order."""
    passes, fails, seen_pass, seen_fail = [], [], set(), set()
    for run in TASKS[task]:
        for folder, record in sorted(TrialRecord.all_in(RUNS / run), key=lambda pair: (pair[1].model, pair[1].trial)):
            if record.condition != "can_ask" or not (folder / "submission.yaml").exists():
                continue
            if record.verdict == "pass" and record.model not in seen_pass and len(passes) < PER_ROW:
                passes.append((folder, record)); seen_pass.add(record.model)
            elif (record.verdict == "fail" and record.model not in seen_fail and len(fails) < PER_ROW
                  and "builds" not in record.failed_checks):
                fails.append((folder, record)); seen_fail.add(record.model)
    return passes, fails


def failure_view(mesh):
    """The first roof or ledge the bridge check fails, if any, to draw in red. The part is drawn from below, as it
    comes off the bed, since that's where a roof printed over air sags."""
    return next((found for found in bridges.overhangs(mesh) if not found.ok and not found.narrow), None)


def knob_cut(folder: Path, record: TrialRecord, scratch: Path) -> Path:
    """A failed knob cut through, the nut drawn where it has to go (scripts/failure_figures.py): straight across the
    pocket where it's tightest, with both widths, when the nut's fit failed (R4); down the middle otherwise, where a
    roof over the pocket or a pocket that can't be reached shows. Drawn into scratch."""
    nut = f"ISO 4032 {record.task.split('/')[1]}"
    trial = folder.relative_to(RUNS).as_posix()
    across = "R4" in record.failed_checks and "bridges" not in record.failed_checks
    figure = (failure_figures.Figure("gallery-knob", trial, "", "across", nut=nut, dimensions=True) if across
              else failure_figures.Figure("gallery-knob", trial, "", "side", nut=nut))
    was, failure_figures.OUT = failure_figures.OUT, scratch
    try:
        return failure_figures.draw(figure)
    except AttributeError:  # no pocket the nut checker can read: cut it down the middle
        figure.view, figure.dimensions = "side", False
        return failure_figures.draw(figure)
    finally:
        failure_figures.OUT = was


def gallery(task: str, png: Path) -> None:
    passes, fails = picks(task)
    rows = [("Pass", passes, "#2f7a4f"), ("Fail", fails, "#b0392b")]
    fig, axes = plt.subplots(2, PER_ROW, figsize=(PER_ROW * 2.6, 2 * 2.7), dpi=150)
    with tempfile.TemporaryDirectory() as scratch:
        for row, (label, trials, colour) in enumerate(rows):
            for col in range(PER_ROW):
                ax = axes[row][col]
                ax.set_axis_off()
                if col >= len(trials):
                    continue
                folder, record = trials[col]
                picture = Path(scratch) / f"{row}-{col}.png"
                if label == "Fail" and task == "nut-knob":
                    picture = knob_cut(folder, record, Path(scratch))  # cut through, the nut drawn in
                    ax.imshow(plt.imread(picture))
                else:
                    mesh = task_figures.main_part(folder / "submission.yaml", Path(scratch) / f"parts-{row}-{col}")
                    if label == "Fail":  # from below, the failing roof in red
                        walk.render(mesh, picture, azim=-55, failed=failure_view(mesh), elev=-40)
                    else:
                        walk.render(mesh, picture, azim=-55)
                    image = plt.imread(picture)
                    rows_, cols_ = (image[..., 3] > 0).any(axis=1).nonzero()[0], (image[..., 3] > 0).any(axis=0).nonzero()[0]
                    ax.imshow(image[rows_[0]:rows_[-1] + 1, cols_[0]:cols_[-1] + 1])  # trimmed to the part
                title = f"{label}: {short_model(record.model)}, trial {record.trial}"
                if record.task.count("/"):
                    title += f" ({record.task.split('/')[1]})"
                ax.set_title(title, fontsize=8.5, color=colour, fontweight="bold")
                if label == "Fail":
                    ax.text(0.5, -0.04, "\n".join(_wrap(failed_reason(record), 34)), transform=ax.transAxes,
                            ha="center", va="top", fontsize=7.5, color="#3b4440")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.93, bottom=0.12, wspace=0.05, hspace=0.45)
    fig.savefig(png, facecolor="white")
    plt.close(fig)


def _wrap(text: str, width: int) -> list[str]:
    return textwrap.wrap(text, width, max_lines=3, placeholder=" …")


def main():
    for task in TASKS:
        gallery(task, OUT / f"{task}-gallery.png")
        print(f"wrote {task}-gallery.png")


if __name__ == "__main__":
    main()
