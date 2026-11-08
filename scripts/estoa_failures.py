"""Example Estoa failures for the README: a keyhole whose slot runs down, and a perfboard with no wall on one side.
No model calls.

    uv run python scripts/estoa_failures.py

Each is a cut through the finished box, read the way the checks read it (pbe/graders/enclosure.py): the back at the
keyholes' depth, and the box at 2 mm above the perfboard, in the board's own frame. Writes docs/media/failures/
estoa-keyhole-down.png and estoa-perfboard-open.png. Parts are built from the saved designs (parts/ isn't committed).
"""
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Rectangle  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import failure_figures  # noqa: E402  the part colour, edge and drawing helpers

from pbe.graders import enclosure, placed  # noqa: E402
from pbe.parts import submission  # noqa: E402
from pbe.parts.build import build_parts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/media/failures"
RUNS = ROOT / "results/runs/test-first/estoa-light/can_test"
KEYHOLE_DOWN = RUNS / "anthropic__claude-opus-5.5/t2"
PERFBOARD_OPEN = RUNS / "openai__gpt-6.1-sol/t3"
FAIL = "#b0392b"
BOARD = "#3d6fb4"


def piece_of(folder: Path, scratch: Path):
    sub = submission.load(folder / "submission.yaml")
    piece, why = placed.piece(sub, build_parts(sub, scratch))
    if piece is None:
        raise SystemExit(f"{folder}: {why}")
    return piece


def draw_plastic(ax, polygons):
    for polygon in polygons:
        ax.add_patch(failure_figures._patch(polygon, facecolor=failure_figures.PART, edgecolor=failure_figures.EDGE, lw=0.8))


def keyhole_down(png: Path) -> None:
    """The back at the keyholes' depth, each slot's direction as a red arrow beside a grey one pointing up."""
    with tempfile.TemporaryDirectory() as scratch:
        piece = piece_of(KEYHOLE_DOWN, Path(scratch))
    back = placed.section(piece.meshes, piece.wall_z + 0.3)
    fig, ax = plt.subplots(figsize=(4.2, 4.2), dpi=200)
    draw_plastic(ax, back)
    for polygon in back:
        for ring in polygon.interiors:
            found = enclosure._keyhole(failure_figures.Polygon(ring))
            if found is None:
                continue
            origin, entry, _, direction, travel = found
            tip = origin + direction * (travel + 6)
            ax.add_patch(FancyArrowPatch(tuple(origin), tuple(tip), arrowstyle="-|>", mutation_scale=12, color=FAIL, lw=1.6))
            ax.add_patch(FancyArrowPatch(tuple(origin), (origin[0], origin[1] + travel + 6), arrowstyle="-|>",
                                         mutation_scale=12, color="#8a949b", lw=1.2, ls="--"))
    ax.text(0.5, -0.02, "red: the way the slot runs; grey dashed: up, the way it has to run", transform=ax.transAxes,
            fontsize=7, ha="center", va="top", color="#2c3431")
    ax.set_aspect("equal")
    ax.autoscale_view()
    ax.set_axis_off()
    fig.savefig(png, bbox_inches="tight", facecolor="white", metadata={"Software": None})
    plt.close(fig)


def perfboard_open(png: Path) -> None:
    """The box cut 2 mm above the perfboard, in the board's frame, with the board drawn in and its open side marked."""
    with tempfile.TemporaryDirectory() as scratch:
        piece = piece_of(PERFBOARD_OPEN, Path(scratch))
    board = enclosure._placed_once(piece, "own:perfboard")
    cut = placed.section(placed.into(piece.meshes, board), 2.0)
    fig, ax = plt.subplots(figsize=(4.2, 4.2), dpi=200)
    draw_plastic(ax, cut)
    width, length = 46, 66  # the perfboard (tasks/estoa-light/requirements.yaml, R5's slab)
    ax.add_patch(Rectangle((-width / 2, -length / 2), width, length, facecolor=BOARD, alpha=0.35, edgecolor=BOARD, lw=1.2))
    ax.text(0, 0, "perfboard", ha="center", va="center", fontsize=8, color=BOARD)
    ax.annotate("no wall on this side", xy=(0, -length / 2 - 2), xytext=(0, -length / 2 - 16), ha="center", fontsize=8,
                color=FAIL, arrowprops={"arrowstyle": "-|>", "color": FAIL})
    ax.set_aspect("equal")
    ax.autoscale_view()
    low = min(polygon.bounds[1] for polygon in cut) if cut else -length / 2
    ax.set_ylim(min(low, -length / 2 - 22), None)
    ax.set_axis_off()
    fig.savefig(png, bbox_inches="tight", facecolor="white", metadata={"Software": None})
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    keyhole_down(OUT / "estoa-keyhole-down.png")
    perfboard_open(OUT / "estoa-perfboard-open.png")
    print("wrote estoa-keyhole-down.png and estoa-perfboard-open.png to", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
