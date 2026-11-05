"""The README's pictures of what went wrong: cross-sections of saved designs with the hardware drawn in
where it would sit, and the bridge check's strand picture for a holed roof. No model calls.

    uv run python scripts/failure_figures.py

Writes docs/media/failures/. A part whose mesh isn't on this machine (parts/ isn't committed) is built
again from the saved design first. The hardware is drawn at catalog sizes, where the design puts it:
a nut at the bottom of its pocket, a bearing in each seat, a bolt down the middle.
"""
import math
import sys
from dataclasses import dataclass, field
from functools import reduce
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from matplotlib.patches import PathPatch, Rectangle  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402
from shapely import affinity  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402
from shapely.geometry.polygon import orient  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import results_page  # noqa: E402  its part rebuilding, so both pages read the same meshes

from pbe.graders import bridges, nuts  # noqa: E402
from pbe.parts import catalog, submission  # noqa: E402
from pbe.parts.build import build_parts  # noqa: E402
from pbe.runner import tasks  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/media/failures"
PART = "#c9d3dc"
EDGE = "#3b4a57"
HARDWARE = "#d9822b"
BEARING = dict(od=22.0, bore=8.0, width=7.0)  # 608, as in catalog/hardware.yaml


@dataclass
class Figure:
    name: str
    trial: str  # run/task/condition/model/tN under results/runs, or reference/<task> for the task's reference
    part: str
    view: str  # "strands", "across" (a cut straight across at the pocket), "side" (a vertical cut), "side-y"
    nut: str = ""  # draw this nut in its pocket
    bearings: bool = False  # draw a 608 in each seat and an M8 down the middle
    notes: list = field(default_factory=list)


FIGURES = [
    Figure("tripod-holed-roof", "pilot-tripod/tripod-plate/can_ask/openai__gpt-6-luna/t1", "camera_plate", "strands"),
    Figure("tripod-reference", "reference/tripod-plate", "plate", "side"),
    Figure("tripod-dovetail-upside-down", "pilot-tripod/tripod-plate/can_ask/anthropic__claude-sonnet-5.5/t1", "", "side"),
    Figure("tripod-straight-sides", "pilot-tripod/tripod-plate/can_ask/anthropic__claude-haiku-5.5/t2", "", "side"),
    Figure("wheel-flat-roof", "pilot-wheel/bearing-wheel/can_ask/anthropic__claude-sonnet-5.5/t1", "wheel", "side", bearings=True),
    Figure("wheel-narrow-ledge", "pilot-wheel/bearing-wheel/can_ask/anthropic__claude-sonnet-5.5/t3", "wheel", "side", bearings=True),
    Figure("wheel-cone", "pilot-wheel/bearing-wheel/can_ask/anthropic__claude-opus-5.5/t1", "wheel", "side", bearings=True),
    Figure("knob-snap-lip", "pilot-nut-knob-2/nut-knob/M3/can_ask/anthropic__claude-haiku-5.5/t1", "knob", "side", nut="ISO 4032 M3"),
    Figure("knob-no-clearance", "pilot-nut-knob-2/nut-knob/M3/can_ask/anthropic__claude-sonnet-5.5/t1", "knob", "across", nut="ISO 4032 M3"),
    Figure("knob-ribs-opus", "pilot-nut-knob/nut-knob/M5/can_ask/anthropic__claude-opus-5.5/t2", "knob", "across", nut="ISO 4032 M5"),
    Figure("knob-ribs-sol", "pilot-nut-knob/nut-knob/M5/can_ask/openai__gpt-6.1-sol/t1", "", "across", nut="ISO 4032 M5"),
]


# ---- the mesh, sitting on the bed and centred ----

def _design(fig):
    """(folder, submission) with the design's parts built into folder/parts."""
    if fig.trial.startswith("reference/"):
        task_id = fig.trial.removeprefix("reference/")
        folder = ROOT / "results/local/reference" / task_id
        sub = submission.parse(tasks.load(task_id).reference)
        if not (folder / "parts").exists():
            build_parts(sub, folder / "parts")
        return folder, sub
    folder = ROOT / "results/runs" / fig.trial
    sub = submission.load(folder / "submission.yaml")
    results_page.ensure_parts(folder, sub)
    return folder, sub


def load_part(fig):
    folder, sub = _design(fig)
    finals = [part.id for part in sub.parts if part.role == "final"]
    part_id = fig.part or max(finals, key=lambda id_: (folder / "parts" / f"{id_}.stl").stat().st_size)
    mesh = trimesh.load(folder / "parts" / f"{part_id}.stl", force="mesh")
    low, high = mesh.bounds
    mesh.apply_translation([-(low[0] + high[0]) / 2, -(low[1] + high[1]) / 2, -low[2]])
    return mesh


# ---- cuts ----

def _even_odd(loops):
    loops = [loop for loop in loops if loop is not None and loop.is_valid]
    return reduce(lambda so_far, loop: so_far.symmetric_difference(loop), loops) if loops else None


def cut_across(mesh, z):
    """The layer at height z, seen from above."""
    return bridges._layer_at(mesh, z)


def cut_side(mesh, along="x", at=0.0):
    """A vertical cut through the part, seen from the side: along x shows x against z."""
    normal, to_2d = ([0, 1, 0], [[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, at], [0, 0, 0, 1]]) if along == "x" else \
                    ([1, 0, 0], [[0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, -at], [0, 0, 0, 1]])
    origin = [0, at, 0] if along == "x" else [at, 0, 0]
    section = mesh.section(plane_origin=origin, plane_normal=normal)
    planar, _ = section.to_2D(to_2D=np.array(to_2d, dtype=float), check=False)
    return _even_odd(planar.polygons_closed)


# ---- drawing ----

def _patch(geom, **style):
    polys = geom.geoms if hasattr(geom, "geoms") else [geom]
    verts, codes = [], []
    for poly in polys:
        if poly.geom_type != "Polygon" or poly.is_empty:
            continue
        poly = orient(poly)
        for ring in [poly.exterior, *poly.interiors]:
            xy = list(ring.coords)
            verts += xy
            codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(xy) - 2) + [MplPath.CLOSEPOLY]
    return PathPatch(MplPath(verts, codes), **style)


def _scale_bar(ax, length=5.0):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    x, y = x1 - length - (x1 - x0) * 0.04, y0 + (y1 - y0) * 0.05
    ax.plot([x, x + length], [y, y], color=EDGE, lw=2)
    ax.text(x + length / 2, y + (y1 - y0) * 0.02, f"{length:g} mm", ha="center", va="bottom", fontsize=8, color=EDGE)


def _frame(ax, geom, pad=3.0):
    minx, miny, maxx, maxy = geom.bounds
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad - (maxy - miny) * 0.12, maxy + pad)
    ax.set_aspect("equal")
    ax.set_axis_off()


def hexagon(across, centre=(0.0, 0.0), degrees=0.0):
    r = across / math.sqrt(3)
    points = [(r * math.cos(math.radians(60 * i)), r * math.sin(math.radians(60 * i))) for i in range(6)]
    return affinity.translate(affinity.rotate(Polygon(points), degrees, origin=(0, 0)), *centre)


def _best_turn(hole, across, centre):
    """The nut's turn that lines up best with the pocket."""
    return max(range(0, 60, 2), key=lambda deg: hexagon(across, centre, deg).intersection(hole).area)


def _pocket(mesh, nut):
    found = nuts.find_pockets(mesh, catalog.resolve(nut)["af"])
    return min(found, key=lambda pocket: pocket.centre.distance(Polygon([(0, 0), (0, 0.01), (0.01, 0)]))) if found else None


def _hole_at(layer, centre):
    holes = [Polygon(ring) for poly in (layer.geoms if hasattr(layer, "geoms") else [layer]) for ring in poly.interiors]
    near = affinity.translate(Polygon([(0, 0), (0, .01), (.01, 0)]), *centre)
    return min(holes, key=lambda hole: hole.distance(near)) if holes else None


def _tightest_layer(mesh, pocket, across, centre):
    """(z, layer, hole) where the nut overlaps the most plastic: the layer with ribs, clips or a lip."""
    best = None
    for z in np.arange(pocket.z[0] + 0.1, pocket.z[1], 0.2):
        layer = cut_across(mesh, z)
        hole = _hole_at(layer, centre) if layer is not None else None
        if hole is None:
            continue
        nut_shape = hexagon(across, centre, _best_turn(hole, across, centre))
        overlap = nut_shape.difference(hole).area
        if best is None or overlap > best[0]:
            best = (overlap, z, layer, hole)
    return best[1:]


def draw_across(ax, mesh, nut):
    """The pocket cut across where it's tightest, with the nut drawn where it has to go."""
    spec = catalog.resolve(nut)
    pocket = _pocket(mesh, nut)
    centre = (pocket.centre.x, pocket.centre.y)
    z, layer, hole = _tightest_layer(mesh, pocket, spec["af"], centre)
    nut_shape = hexagon(spec["af"], centre, _best_turn(hole, spec["af"], centre))
    ax.add_patch(_patch(layer, facecolor=PART, edgecolor=EDGE, lw=0.8))
    ax.add_patch(_patch(nut_shape, facecolor="none", edgecolor=HARDWARE, lw=1.6, ls="--"))
    overlap = nut_shape.difference(hole) if hole is not None else None
    if overlap is not None and overlap.area > 0.01:  # where the nut has to push plastic out of the way
        ax.add_patch(_patch(overlap, facecolor=HARDWARE, edgecolor="none", alpha=0.75))
    view = nut_shape.buffer(spec["af"] * 0.9)
    _frame(ax, view, pad=0.5)


def draw_side(ax, mesh, fig):
    extents = mesh.extents
    along = "x" if extents[0] >= extents[1] or fig.bearings or fig.nut else "y"
    if fig.name.startswith("tripod"):  # cut across the plate's length, to show the profile the clamp grips
        along = "y" if extents[0] >= extents[1] else "x"
    section = cut_side(mesh, along)
    ax.add_patch(_patch(section, facecolor=PART, edgecolor=EDGE, lw=0.8))
    if fig.bearings:
        height = mesh.bounds[1][2]
        for z in (0.0, height - BEARING["width"]):
            for side in (-1, 1):
                x = side * BEARING["bore"] / 2 if side > 0 else -BEARING["od"] / 2
                ax.add_patch(Rectangle((x, z), (BEARING["od"] - BEARING["bore"]) / 2, BEARING["width"],
                                       facecolor=HARDWARE, alpha=0.55, edgecolor=HARDWARE, lw=1))
        ax.add_patch(Rectangle((-4, -1), 8, height + 2, facecolor="none", edgecolor=HARDWARE, lw=1, ls=":"))
    if fig.nut:
        spec = catalog.resolve(fig.nut)
        pocket = _pocket(mesh, fig.nut)
        x = pocket.centre.x if pocket and along == "x" else (pocket.centre.y if pocket else 0.0)
        top = mesh.bounds[1][2]
        z = pocket.z[0] if pocket else top - spec["h"]
        ax.add_patch(Rectangle((x - spec["af"] / 2, z), spec["af"], spec["h"], facecolor=HARDWARE, alpha=0.55,
                               edgecolor=HARDWARE, lw=1))
    _frame(ax, section)


def draw_strands(path, mesh):
    found = [overhang for overhang in bridges.overhangs(mesh) if not overhang.ok and not overhang.narrow]
    path.with_suffix(".svg").write_text(bridges.svg(found[0]))
    return path.with_suffix(".svg")


def draw(fig):
    mesh = load_part(fig)
    path = OUT / fig.name
    if fig.view == "strands":
        return draw_strands(path, mesh)
    figure, ax = plt.subplots(figsize=(3.4, 2.8), dpi=130)
    if fig.view == "across":
        draw_across(ax, mesh, fig.nut)
    else:
        draw_side(ax, mesh, fig)
    _scale_bar(ax)
    figure.savefig(path.with_suffix(".png"), bbox_inches="tight", facecolor="white", metadata={"Software": None})
    plt.close(figure)
    return path.with_suffix(".png")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for fig in FIGURES:
        print(draw(fig).relative_to(ROOT))


if __name__ == "__main__":
    main()
