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
from matplotlib.patches import Ellipse, Patch, PathPatch, Rectangle  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402
from shapely import affinity  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402
from shapely.geometry.polygon import orient  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import results_page  # noqa: E402  its part rebuilding, so both pages read the same meshes

from pbe.graders import bridges, nuts  # noqa: E402
from pbe.parts import catalog, submission  # noqa: E402
from pbe.parts.build import build_parts  # noqa: E402
from pbe.runner import tasks  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/media/failures"
PART = "#c9d3dc"
BEYOND = "#e6ebef"  # the part behind a side cut, seen through it
BEYOND_EDGE = "#a3afba"
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
    dimensions: bool = False  # label the pocket's width and draw the nut beside it with its own
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
    Figure("knob-no-clearance", "pilot-nut-knob-2/nut-knob/M3/can_ask/anthropic__claude-sonnet-5.5/t1", "knob", "across", nut="ISO 4032 M3",
           dimensions=True),
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


def beyond_cut(mesh, along="x", at=0.0):
    """The half of the part behind a side cut, as seen through the cut: what a drafter draws faintly behind a section,
    so the material that joins the two cut faces around a bore or hole shows in the gap between them."""
    normal = [0, 1, 0] if along == "x" else [1, 0, 0]
    origin = [0, at, 0] if along == "x" else [at, 0, 0]
    half = trimesh.intersections.slice_mesh_plane(mesh, plane_normal=normal, plane_origin=origin, cap=False)
    seen = half.triangles[:, :, [0, 2]] if along == "x" else half.triangles[:, :, [1, 2]]
    faces = [Polygon(tri) for tri in seen]
    return unary_union([face.buffer(0.01) for face in faces if face.area > 1e-6]).buffer(-0.01)


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


def draw_across(ax, mesh, nut, dimensions=False):
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
    if dimensions:
        view = view.union(_dimensions(ax, pocket, spec, centre, layer.bounds[2]))
    _frame(ax, view, pad=0.5)


def _width_line(ax, x0, x1, y, text, colour):
    """A dimension line from x0 to x1 at height y, with its label above."""
    ax.annotate("", xy=(x0, y), xytext=(x1, y), arrowprops={"arrowstyle": "<->", "color": colour, "lw": 1.0})
    ax.text((x0 + x1) / 2, y + 0.35, text, ha="center", va="bottom", fontsize=7.5, color=colour)


def _dimensions(ax, pocket, spec, centre, knob_right):
    """The pocket's measured width across flats over it, and the nut drawn to its right with its own width, so the
    two numbers sit side by side. Returns the area the labels take, for framing."""
    cx, cy = centre
    half = pocket.across / 2
    top = cy + spec["af"] / math.sqrt(3) + 0.6
    _width_line(ax, cx - half, cx + half, top, f"pocket {pocket.across:.2f} mm", EDGE)
    nut_x = knob_right + spec["af"] * 0.9  # clear of the knob, so it reads as a separate part
    nut = hexagon(spec["af"], (nut_x, cy), 30)
    ax.add_patch(_patch(nut, facecolor=HARDWARE, edgecolor=HARDWARE, alpha=0.85))
    ax.add_patch(_patch(nut.buffer(-spec["af"] * 0.28), facecolor="white", edgecolor="none"))
    _width_line(ax, nut_x - spec["af"] / 2, nut_x + spec["af"] / 2, top, f"nut {spec['af']:.1f} mm", HARDWARE)
    return Polygon([(cx - half, cy), (nut_x + spec["af"], cy), (nut_x + spec["af"], top + 1.6), (cx - half, top + 1.6)])


def _gap_center(section):
    """The middle of the gap a center cut leaves between the part's sides (a bore or hole): the gap in the
    pieces' x spans nearest x = 0. None if the cut came out in one piece."""
    polys = section.geoms if hasattr(section, "geoms") else [section]
    spans = sorted((poly.bounds[0], poly.bounds[2]) for poly in polys)
    gaps, reach = [], spans[0][1]
    for low, high in spans[1:]:
        if low > reach:
            gaps.append((reach + low) / 2)
        reach = max(reach, high)
    return min(gaps, key=abs) if gaps else None


def _mark_axis(ax, section, height, hole_words, rim):
    """Show that a center cut's separate-looking sides are one part: a dash-dot center line through the gap and a note
    saying they join around it; for a round part also the rim it turns around, as a dashed ellipse over the top."""
    x = _gap_center(section)
    if x is None:
        return 0.0
    minx, _, maxx, _ = section.bounds
    lift = min(4.0, (maxx - minx) * 0.15) if rim else 0.0
    ax.plot([x, x], [-2.0, height + lift / 2 + 1.0], color=EDGE, lw=0.8, ls=(0, (8, 2, 1.5, 2)), zorder=6)
    ax.text(x, -2.3, "axis" if rim else "center line", ha="center", va="top", fontsize=7, color=EDGE)
    if rim:
        ax.add_patch(Ellipse((x, height), maxx - minx, lift, fill=False, edgecolor=EDGE, lw=0.7, ls=(0, (3, 2)),
                             alpha=0.8, zorder=5))
    ax.text(x, height + lift / 2 + 1.2, f"one piece: the light gray behind the cut joins both sides around {hole_words}", ha="center", va="bottom",
            fontsize=6.5, color=EDGE)
    return lift / 2 + 3.5


def draw_side(ax, mesh, fig):
    extents = mesh.extents
    along = "x" if extents[0] >= extents[1] or fig.bearings or fig.nut else "y"
    if fig.name.startswith("tripod"):  # cut across the plate's length, to show the profile the clamp grips
        along = "y" if extents[0] >= extents[1] else "x"
    section = cut_side(mesh, along)
    ax.add_patch(_patch(beyond_cut(mesh, along), facecolor=BEYOND, edgecolor=BEYOND_EDGE, lw=0.6))
    ax.add_patch(_patch(section, facecolor=PART, edgecolor=EDGE, lw=0.8, hatch="////"))
    round_part = fig.bearings or bool(fig.nut)
    room = _mark_axis(ax, section, mesh.bounds[1][2], "the axis" if round_part else "the hole", rim=round_part)
    ax.set_title("Section: cut through the center", fontsize=8, color=EDGE, loc="left")
    if fig.bearings:
        height = mesh.bounds[1][2]
        for z in (0.0, height - BEARING["width"]):
            for side in (-1, 1):
                x = side * BEARING["bore"] / 2 if side > 0 else -BEARING["od"] / 2
                ax.add_patch(Rectangle((x, z), (BEARING["od"] - BEARING["bore"]) / 2, BEARING["width"],
                                       facecolor=HARDWARE, alpha=0.55, edgecolor=HARDWARE, lw=1))
        ax.add_patch(Rectangle((-4, -1), 8, height + 2, facecolor="none", edgecolor=HARDWARE, lw=1, ls=":"))
        ax.legend(handles=[Patch(facecolor=PART, edgecolor=EDGE, label="Wheel, cut face"),
                           Patch(facecolor=BEYOND, edgecolor=BEYOND_EDGE, label="Wheel behind the cut"),
                           Patch(facecolor=HARDWARE, alpha=0.55, edgecolor=HARDWARE, label="Bearings"),
                           Patch(facecolor="none", edgecolor=HARDWARE, ls=":", label="Bolt")],
                  loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=2, frameon=False, fontsize=7.5,
                  handlelength=1.2, columnspacing=1.0)
    if fig.nut:
        spec = catalog.resolve(fig.nut)
        pocket = _pocket(mesh, fig.nut)
        x = pocket.centre.x if pocket and along == "x" else (pocket.centre.y if pocket else 0.0)
        top = mesh.bounds[1][2]
        z = pocket.z[0] if pocket else top - spec["h"]
        ax.add_patch(Rectangle((x - spec["af"] / 2, z), spec["af"], spec["h"], facecolor=HARDWARE, alpha=0.55,
                               edgecolor=HARDWARE, lw=1))
    _frame(ax, section)
    if room:  # space over the part for the note
        y0, y1 = ax.get_ylim()
        ax.set_ylim(y0, y1 + room)


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
        draw_across(ax, mesh, fig.nut, fig.dimensions)
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
