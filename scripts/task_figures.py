"""The README's per-task pictures: each task's reference solution (a hand-written design that passes every check) and a
passing trial where the failure figures don't already show one. No model calls.

    uv run python scripts/task_figures.py

Writes docs/media/tasks/<name>.png with the walkthrough's renderer (scripts/walkthrough_figures.py): every face, lit
from above left, faces turned away from the camera left out. Parts are built from the saved designs into a
temporary folder, since parts/ isn't committed.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import walkthrough_figures as walk  # noqa: E402

from pbe.parts import submission  # noqa: E402
from pbe.parts.build import build_parts  # noqa: E402
from pbe.runner import tasks  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/media/tasks"
RUNS = ROOT / "results/runs"
FIGURES = {  # name: the design to draw
    "tripod-plate-reference": ROOT / "tasks/tripod-plate/reference.yaml",
    "bearing-wheel-reference": ROOT / "tasks/bearing-wheel/reference.yaml",
    "nut-knob-reference": "nut-knob/M3",  # a task family: its reference, filled in for the M3 variant
    "estoa-light-reference": ROOT / "tasks/estoa-light/reference.yaml",
    "tripod-plate-pass": RUNS / "pilot-tripod/tripod-plate/can_ask/anthropic__claude-opus-5.5/t5/submission.yaml",
    "nut-knob-pass": RUNS / "test-first/nut-knob/M3/can_test/anthropic__claude-sonnet-5.5/t2/submission.yaml",
    "nut-knob-ribs": RUNS / "pilot-nut-knob/nut-knob/M5/can_ask/anthropic__claude-opus-5.5/t2/submission.yaml",
}
VIEWS = {"nut-knob-ribs": {"azim": -60, "elev": 62}}  # from above, into the pocket, so the ribs show
CLOSE_UP = {"nut-knob-ribs": 9.0}  # mm around the part's centre, so the pocket fills the picture


def load(design):
    """A saved design, or a task family's reference filled in for one variant (pbe.runner.tasks)."""
    if isinstance(design, Path):
        return submission.load(design)
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
        handle.write(tasks.load(design).reference)
    return submission.load(Path(handle.name))


def main_part(design, out: Path):
    """The design's largest final part, built."""
    sub = load(design)
    finals = [part for part in sub.parts if part.role == "final"] or sub.parts
    built = build_parts(sub.model_copy(update={"parts": finals}), out)
    meshes = [built[part.id].mesh for part in finals if built[part.id].ok]
    return max(meshes, key=lambda mesh: abs(mesh.volume))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, design in FIGURES.items():
        with tempfile.TemporaryDirectory() as out:
            mesh = main_part(design, Path(out))
            if name in CLOSE_UP:
                centre = mesh.bounds.mean(axis=0)
                mesh = walk.around(mesh, (centre[0], centre[1]), CLOSE_UP[name])
            walk.render(mesh, OUT / f"{name}.png", **VIEWS.get(name, {"azim": -55}))
    print(f"wrote {len(FIGURES)} pictures to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
