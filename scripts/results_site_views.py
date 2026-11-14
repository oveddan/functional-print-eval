"""A drawn view for each failing check on the results site: for every saved design and every counted check that
failed (and, after those, every check that couldn't be graded), one 2D figure of the region the check read, drawn
from the grader's own geometry and numbers, or an honest reason there is none. No model calls.

    uv run python scripts/results_site_views.py --no-upload             # draw everything, don't upload
    uv run python scripts/results_site_views.py --only pilot-estoa      # designs whose path contains this
    uv run python scripts/results_site_views.py --failed-only --limit 20

Designs are found as scripts/results_site_media.py finds them (any folder under results/runs with a submission.yaml),
with its findings, part owners and builds; parts already built under each design's parts/ are read, not rebuilt.
Each view calls the same grader functions the check ran (pbe/graders/), so it shows what the check looked at, never
a second grading. When today's grader no longer finds what a saved finding names, the view says so instead of
drawing something else.

Work is kept under results/local/site-views/ (git-ignored): one record per design in designs/, the figures in
objects/<sha256-8>/<name>.webp (content-addressed, like the media script's), slow overhang searches in cache/,
and views.json, the working manifest: {"version", "designs": {design path: [{check, part, state, test_print, kind,
caption, view, no_view_reason}]}}, where `view` is the media host URL once uploaded, else the local path. Once every
image is uploaded (with the media script's uploader, its own ledger, at most 6 at a time) the same manifest with URLs
only is written to scripts/results_site_views.json, committed, which scripts/results_site.py reads. A re-run only does
what's new; bump VERSION to redraw everything.
"""
import argparse
import hashlib
import io
import json
import math
import pickle
import re
import sys
import textwrap
import time
import traceback
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import cache, reduce
from itertools import groupby
from multiprocessing import Pool
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle, Patch, Rectangle  # noqa: E402
from shapely.geometry import LineString, MultiPoint, Point, Polygon  # noqa: E402
from shapely.ops import polylabel, unary_union  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import failure_figures as ff  # noqa: E402  the cross-section drawing helpers and hardware sizes
import results_page  # noqa: E402  CONSEQUENCE: the not-graded phrases that mean a check wasn't reached
import results_site  # noqa: E402  check titles and reader wording
import results_site_media as media  # noqa: E402  design discovery, findings, builds, part owners, upload

from pbe.graders import bolt_fits, bolted, bridges, enclosure, nuts, placed, sections, wheel  # noqa: E402
from pbe.graders.placed import NotReadable  # noqa: E402
from pbe.parts import catalog  # noqa: E402
from pbe.parts.build import Built  # noqa: E402
from pbe.parts.printer import printer  # noqa: E402
from pbe.parts.submission import Placement  # noqa: E402
from pbe.runner import tasks  # noqa: E402

ROOT = media.ROOT
WORK = ROOT / "results/local/site-views"
RECORDS = WORK / "designs"
OBJECTS = WORK / "objects"
CACHE = WORK / "cache"
LEDGER = WORK / "uploaded.txt"
MANIFEST = WORK / "views.json"  # the working manifest: local paths for anything not uploaded
COMMITTED = Path(__file__).with_suffix(".json")  # the committed one: URLs only, written once everything is uploaded
VERSION = 5
DEBUG_FIT = False

FIG_W_IN, DPI = 4.5, 200  # 900 px wide; text stays readable when a phone shows it at about 360 px
BG = "#fbfbf8"  # opaque and light, so a figure reads the same on a light or a dark page
BORDER = (197, 203, 209)
TEXT = "#1f2a33"
PART, EDGE, HARDWARE, BEARING = ff.PART, ff.EDGE, ff.HARDWARE, ff.BEARING
LIGHT = "#e9edf0"
FAIL = "#c0392b"
ROOF = "#f3c6c0"
OK = "#2e7d4f"
WARN = "#d9822b"
BOARD = "#3d6fb4"
DISK = "#a9c1e3"  # the disk's board: a solid light blue, so it reads at a glance
TONES = {"ok": OK, "bad": FAIL, "warn": WARN, "info": "#5b6b78"}
NICE_MM = (0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000)

plt.rcParams.update({"font.size": 8.5, "font.family": "DejaVu Sans", "axes.titlesize": 8, "axes.titlelocation": "left",
                     "axes.titlecolor": TEXT, "text.color": TEXT})


class NoView(Exception):
    """This finding can't be drawn honestly; the message says why, in a reader's words."""


@dataclass
class View:
    kind: str
    fig: object
    legend: list = field(default_factory=list)
    note: str = ""  # added to the caption: something the picture alone doesn't say


# ---- the design and what the checks read ----

@cache
def task_of(task_id):
    return tasks.load(task_id)


def requirement_args(task_id, check):
    return next((r.args or {} for r in task_of(task_id).requirements if r.id == check), {})


@dataclass
class Design:
    folder: Path
    task: str
    sub: object
    built: dict
    errors: dict
    _piece: tuple = None

    @property
    def family(self):
        return self.task.split("/")[0]

    def args(self, check):
        return requirement_args(self.task, check)

    def mesh(self, part_id):
        part = self.built.get(part_id)
        if part is None or not part.ok:
            raise NoView(f"part {part_id} didn't build, so there's no shape to draw")
        return part.mesh

    def piece(self):
        if self._piece is None:
            self._piece = placed.piece(self.sub, self.built)
        found, why = self._piece
        if found is None:
            raise NoView(f"the assembled box can't be put together: {why}")
        return found


def load_design(folder):
    sub = media.submission_to_build(folder)
    errors = media.ensure_built(folder, sub)
    built = {}
    for part in sub.parts:
        stl = folder / "parts" / f"{part.id}.stl"
        if errors.get(part.id) or not stl.exists():
            built[part.id] = Built(part_id=part.id, ok=False, error=errors.get(part.id) or "not built", role=part.role)
            continue
        built[part.id] = Built(part_id=part.id, ok=True, stl=stl, mesh=trimesh.load(stl, force="mesh"), role=part.role)
    return Design(folder, media.task_of(folder), sub, built, errors)


# ---- geometry helpers ----

def unit(vector):
    vector = np.asarray(vector, float)
    return vector / np.linalg.norm(vector)


def polygons_of(geom):
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    found = []
    for part in getattr(geom, "geoms", []):
        found += polygons_of(part)
    return found


def merged(geoms):
    found = [poly for geom in geoms for poly in polygons_of(geom)]
    return unary_union(found) if found else Polygon()


def plane_cut(meshes, point, u, v):
    """The meshes cut by the plane through `point` spanned by u (the drawing's x) and v (its y), with each mesh's holes
    nested by even-odd, in the plane's own coordinates measured from `point`."""
    point, u, v = np.asarray(point, float), unit(u), unit(v)
    normal = np.cross(u, v)
    found = []
    for mesh in meshes:
        section = mesh.section(plane_origin=point, plane_normal=normal)
        if section is None:
            continue
        loops = []
        for loop in section.discrete:
            if len(loop) < 3:
                continue
            relative = np.asarray(loop) - point
            if not np.isfinite(relative).all():
                continue
            try:
                ring = Polygon(np.c_[relative @ u, relative @ v]).buffer(0)
            except Exception:  # a degenerate loop in a broken mesh: leave it out of the drawing
                continue
            if not ring.is_empty:
                loops.append(ring)
        if loops:
            found.append(reduce(lambda so_far, loop: so_far.symmetric_difference(loop), loops))
    return merged(found)


def mesh_key(mesh):
    digest = hashlib.sha256(np.ascontiguousarray(mesh.vertices, np.float64).tobytes())
    digest.update(np.ascontiguousarray(mesh.faces, np.int64).tobytes())
    return digest.hexdigest()[:20]


def cached_overhangs(mesh):
    """pbe.graders.bridges.overhangs(mesh), cached on disk by mesh and printer settings: the grader's own search,
    minutes on a big box, done once."""
    key = hashlib.sha256((mesh_key(mesh) + json.dumps(bridges.settings(), sort_keys=True)).encode()).hexdigest()[:20]
    path = CACHE / "overhangs" / f"{key}.pkl"
    if path.exists():
        try:
            return pickle.loads(path.read_bytes())
        except Exception:
            pass
    found = bridges.overhangs(mesh)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{id(found)}.tmp")
    tmp.write_bytes(pickle.dumps(found))
    tmp.replace(path)
    return found


def numbers(text):
    return [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", text or "")]


# ---- drawing helpers ----

def new_figure(layout):
    """(figure, axes list) for one of the fixed layouts, 900 px wide."""
    if layout == "one":
        fig = plt.figure(figsize=(FIG_W_IN, 4.6), layout="constrained")
        return fig, [fig.add_subplot()]
    if layout == "two":
        fig = plt.figure(figsize=(FIG_W_IN, 3.6), layout="constrained")
        return fig, list(fig.subplots(1, 2))
    if layout == "two+strip":
        fig = plt.figure(figsize=(FIG_W_IN, 5.1), layout="constrained")
        grid = fig.add_gridspec(2, 2, height_ratios=[2.3, 1])
        return fig, [fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1]), fig.add_subplot(grid[1, :])]
    if layout == "one+ruler":
        fig = plt.figure(figsize=(FIG_W_IN, 5.0), layout="constrained")
        grid = fig.add_gridspec(2, 1, height_ratios=[4, 1])
        return fig, [fig.add_subplot(grid[0]), fig.add_subplot(grid[1])]
    if layout == "two+ruler":
        fig = plt.figure(figsize=(FIG_W_IN, 4.4), layout="constrained")
        grid = fig.add_gridspec(2, 2, height_ratios=[3, 1])
        return fig, [fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1]), fig.add_subplot(grid[1, :])]
    raise ValueError(layout)


def fill(ax, geom, z=1, **style):
    for poly in polygons_of(geom):
        ax.add_patch(ff._patch(poly, zorder=z, **style))


def silhouette(ax, mesh, axes, colour, z=1, alpha=1.0):
    """The mesh seen along the third axis, as its triangles filled flat."""
    triangles = np.asarray(mesh.triangles)[:, :, list(axes)]
    ax.add_collection(PolyCollection(triangles, facecolors=colour, edgecolors=colour, linewidths=0.15, zorder=z, alpha=alpha))


def frame(ax, bounds, pad=None, bottom_room=0.12):
    """Equal-aspect limits around (minx, miny, maxx, maxy), room at the bottom for the scale bar, no axes."""
    minx, miny, maxx, maxy = bounds
    span = max(maxx - minx, maxy - miny, 1e-3)
    pad = span * 0.06 if pad is None else pad
    ax.set_xlim(minx - pad, maxx + pad)
    ax.set_ylim(miny - pad - (maxy - miny + 2 * pad) * bottom_room, maxy + pad)
    ax.set_aspect("equal")
    ax.set_axis_off()


def scale_bar(ax):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    span = x1 - x0
    length = max([nice for nice in NICE_MM if nice <= span / 4] or [NICE_MM[0]])
    x, y = x1 - length - span * 0.03, y0 + (y1 - y0) * 0.035
    ax.plot([x, x + length], [y, y], color=TEXT, lw=2.4, solid_capstyle="butt", zorder=20)
    ax.text(x + length / 2, y + (y1 - y0) * 0.02, f"{length:g} mm", ha="center", va="bottom", fontsize=7.5, zorder=20)


def bounds_of(*geoms):
    found = [g for g in geoms if g is not None and not g.is_empty]
    if not found:
        return (-1.0, -1.0, 1.0, 1.0)
    return unary_union(found).bounds


def box_of(bounds):
    minx, miny, maxx, maxy = bounds
    return Polygon([(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)])


def ruler(ax, marks, value, value_text, title="Recorded prints", spans=()):
    """A number line of what the recorded prints did at each size, with this design's reading marked.
    marks: (size, words, tone); spans: (low, high, words, tone)."""
    sizes = [mark[0] for mark in marks] + [value] + [s for span in spans for s in span[:2]]
    low, high = min(sizes), max(sizes)
    pad = max((high - low) * 0.12, 0.05)
    ax.set_xlim(low - pad, high + pad)
    ax.set_ylim(-1.45, 1.1)
    ax.set_facecolor(BG)
    ax.axhline(0, color=EDGE, lw=1, zorder=1)
    for start, end, words, tone in spans:
        ax.plot([start, end], [0, 0], color=TONES[tone], lw=5, alpha=0.5, solid_capstyle="butt", zorder=2)
    for index, (size, words, tone) in enumerate(sorted(marks, key=lambda mark: mark[0])):
        ax.plot([size], [0], marker="|", ms=11, mew=2, color=TONES[tone], zorder=3)
        ax.text(size, -0.25 - 0.36 * (index % 3), words, ha="center", va="top", fontsize=6.8, color=TONES[tone])
    ax.plot([value], [0.12], marker="v", ms=8, color=TEXT, zorder=4)
    ax.text(value, 0.35, value_text, ha="center", va="bottom", fontsize=7.5, weight="bold")
    ax.set_title(title, fontsize=7.5)
    ax.set_yticks([])
    for side in ("left", "right", "top"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="x", labelsize=6.5, length=2)


def render(view, caption):
    """The finished figure as WebP bytes: caption on top, legend under, a thin border, 900 px wide."""
    from PIL import Image, ImageDraw
    fig = view.fig
    fig.suptitle(textwrap.fill(caption, 64), x=0.01, ha="left", fontsize=9, color=TEXT, linespacing=1.25)
    view.legend = drawn_entries(fig, view.legend)
    if view.legend:
        wide = max(len(handle.get_label()) for handle in view.legend) > 28
        fig.legend(handles=view.legend, loc="outside lower center", ncol=1 if wide or len(view.legend) == 1 else 2, frameon=False,
                   fontsize=7.4, handlelength=1.6, columnspacing=1.2)
    fit_text(fig)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=DPI, facecolor=BG, metadata={"Software": None})
    plt.close(fig)
    picture = collapse_blank_rows(Image.open(buffer).convert("RGB"))
    if picture.width != 900:
        picture = picture.resize((900, round(picture.height * 900 / picture.width)), Image.LANCZOS)
    ImageDraw.Draw(picture).rectangle([0, 0, picture.width - 1, picture.height - 1], outline=BORDER, width=2)
    out = io.BytesIO()
    picture.save(out, "WEBP", quality=82, method=6)
    return out.getvalue()


def _rgb(colour):
    from matplotlib.colors import to_rgba
    rgba = to_rgba(colour)
    return None if rgba[3] == 0 else tuple(round(c, 2) for c in rgba[:3])


def _visible_in(ax, extent):
    """Does a display-space box overlap the panel's drawing area, with some size to it?"""
    box = ax.get_window_extent()
    return (extent.width + extent.height > 1.5 and extent.x1 >= box.x0 and extent.x0 <= box.x1
            and extent.y1 >= box.y0 and extent.y0 <= box.y1)


def drawn_colours(fig):
    """({fill colours}, {line and edge colours}) of what is actually drawn inside the panels."""
    fig.canvas.draw()
    fills, lines = set(), set()
    for ax in fig.axes:
        for patch in ax.patches:
            if not patch.get_visible() or not _visible_in(ax, patch.get_window_extent()):
                continue
            if (face := _rgb(patch.get_facecolor())) is not None and patch.get_fill():
                fills.add(face)
            if patch.get_linewidth() > 0 and (edge := _rgb(patch.get_edgecolor())) is not None:
                lines.add(edge)
        for collection in ax.collections:
            if collection.get_visible() and len(collection.get_paths()):
                fills.update(filter(None, (_rgb(c) for c in collection.get_facecolors())))
        for line in ax.lines:
            if line.get_visible() and len(line.get_xdata()) and _visible_in(ax, line.get_window_extent()):
                lines.add(_rgb(line.get_color()))
                if line.get_marker() not in (None, "None", "", " "):
                    fills.add(_rgb(line.get_markerfacecolor()))
        for text in ax.texts:
            arrow = getattr(text, "arrow_patch", None)
            if arrow is not None and arrow.get_visible():
                lines.add(_rgb(arrow.get_edgecolor()))
    return fills, lines


def drawn_entries(fig, legend):
    """The legend entries whose mark is drawn in the figure: a filled swatch needs that fill somewhere, a line needs
    that line or edge colour, a marker needs that marker. An entry for something not drawn is dropped, so the legend
    never names a thing the picture doesn't show."""
    fills, lines = drawn_colours(fig)
    kept = []
    for handle in legend:
        if isinstance(handle, Line2D):
            if handle.get_linestyle() in ("None", "", " "):
                ok = _rgb(handle.get_markerfacecolor()) in fills
            else:
                ok = _rgb(handle.get_color()) in lines
        else:
            face = _rgb(handle.get_facecolor()) if handle.get_fill() else None
            ok = face in fills if face is not None else _rgb(handle.get_edgecolor()) in lines
        if ok:
            kept.append(handle)
    return kept


def require(geom, what):
    """The geometry a view is built on, or no view: an empty cut can't show anything."""
    if geom is None or geom.is_empty or geom.area < 1e-6:
        raise NoView(f"{what} comes back empty, so there's nothing to draw")
    return geom


def _limits(fig, text):
    """(left, right) in display px a text must stay within: its panel's grid cell for a panel title, the figure else."""
    width = fig.bbox.width
    for ax in fig.axes:
        if text in (ax.title, ax._left_title, ax._right_title):
            cell = ax.get_position(original=True)  # the box the layout gave the panel, before equal aspect shrinks it
            return max(cell.x0 * width - 12, 8), min(cell.x1 * width + 12, width - 10)
    return 8, width - 10


def fit_text(fig, rounds=8):
    """Wrap, then shrink, any text that runs past its panel or the figure's edge: at 900 px a long panel title or a
    number line's title would otherwise be cut off or run into the next panel."""
    from matplotlib.text import Text
    fig.set_dpi(DPI)  # measure at the resolution it's saved at
    for _ in range(rounds):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        changed = False
        for text in fig.findobj(Text):
            words = text.get_text()
            if not words or not text.get_visible():
                continue
            box = text.get_window_extent(renderer)
            left, right = _limits(fig, text)
            if box.x0 >= left - 1 and box.x1 <= right + 1:
                continue
            room = max(right - left, 40)
            longest = max(len(line) for line in words.split("\n"))
            fits = int(longest * room / max(box.width, 1) * 0.95)
            if fits >= 12 and longest > fits:
                text.set_text(textwrap.fill(" ".join(words.split()), fits))
            else:
                text.set_fontsize(text.get_fontsize() * min(0.95, max(0.6, room / max(box.width, 1) * 0.95)))
            changed = True
        if not changed:
            return
    print("fit_text: still over after", rounds, "rounds", file=sys.stderr) if DEBUG_FIT else None


def collapse_blank_rows(picture, keep=36):
    """Shrink every band of empty rows taller than `keep` px to `keep`: an equal-aspect drawing leaves blank bands in
    a fixed-size figure, and nothing is drawn in a row that's all background."""
    pixels = np.asarray(picture).astype(int)
    background = np.array([int(BG[i:i + 2], 16) for i in (1, 3, 5)])
    blank = (np.abs(pixels - background).max(axis=2) <= 6).all(axis=1)
    rows, run = [], 0
    for index, empty in enumerate(blank):
        run = run + 1 if empty else 0
        if not empty or run <= keep:
            rows.append(index)
    from PIL import Image
    return Image.fromarray(pixels[rows].astype(np.uint8))


def patch_key(colour, words, edge=None, ls="-"):
    return Patch(facecolor=colour, edgecolor=edge or colour, label=words, ls=ls)


def line_key(colour, words, ls="-", lw=1.6):
    return Line2D([], [], color=colour, ls=ls, lw=lw, label=words)


# ---- generic printability checks ----

def view_bridges(design, finding, part_id):
    mesh = design.mesh(part_id)
    found = cached_overhangs(mesh)
    failing = [overhang for overhang in found if not overhang.ok and not overhang.narrow]
    if finding["ok"] is None:
        failing = [overhang for overhang in found if not overhang.ok and overhang.narrow]
    if not failing:
        raise NoView("today's bridge check finds no such roof on this part, so there's nothing to draw "
                     "(the saved finding predates a change to the check)")
    named = numbers(finding["detail"].split("at z =")[-1])[:1] if "at z =" in finding["detail"] else []
    first = next((o for o in failing if named and abs(o.z - named[0]) < 0.05), failing[0])
    moved_note = (f"today's check finds this roof at z = {first.z:.1f} mm; the saved finding's roof at z = {named[0]:g} mm "
                  "now passes" if named and abs(first.z - named[0]) >= 0.05 else "")
    layer_h = printer().layer_mm
    shifted = mesh.copy()
    shifted.apply_translation([0, 0, -mesh.bounds[0][2]])
    this_layer = bridges._layer_at(shifted, first.z + layer_h / 2)
    same_z = [o for o in failing if abs(o.z - first.z) < 1e-6]
    fig, (whole, zoom, side) = new_figure("two+strip")
    for target in (whole, zoom):
        fill(target, this_layer, fc=LIGHT, ec=EDGE, lw=0.5)
        fill(target, first.support, z=2, fc=PART, ec=EDGE, lw=0.5)
        for overhang in same_z:
            fill(target, overhang.region, z=3, fc=ROOF, ec=FAIL, lw=0.9)
    for line, anchored in first.strands:
        xs, ys = line.xy
        zoom.plot(xs, ys, color=OK if anchored else FAIL, lw=0.6, zorder=4)
    x0, y0, x1, y1 = first.region.bounds
    pad = max(4.0, 0.35 * max(x1 - x0, y1 - y0))
    whole_bounds = bounds_of(this_layer, first.support)
    zoom_box = box_of((x0 - pad, y0 - pad, x1 + pad, y1 + pad))
    if zoom_box.area < 0.4 * box_of(whole_bounds).area:
        whole.add_patch(Rectangle((x0 - pad, y0 - pad), x1 - x0 + 2 * pad, y1 - y0 + 2 * pad, fill=False, ec=FAIL, lw=1.1, zorder=5))
    frame(whole, whole_bounds)
    frame(zoom, (x0 - pad, y0 - pad, x1 + pad, y1 + pad), pad=0)
    whole.set_title(f"Layer at z = {first.z:.1f} mm, from above")
    zoom.set_title(f"Zoomed: strands at {first.best_angle}°")
    # a side cut through the roof, to show where it is in the part
    probe = first.region.representative_point()
    across = _across_the_roof(first.region)  # cut across the roof's long side, so its overhang shows in profile
    cut = plane_cut([shifted], (probe.x, probe.y, 0), (across[0], across[1], 0), (0, 0, 1))
    fill(side, cut, fc=PART, ec=EDGE, lw=0.5)
    reach = max(x1 - x0, y1 - y0) + 2
    line = LineString([(probe.x - across[0] * reach, probe.y - across[1] * reach), (probe.x + across[0] * reach, probe.y + across[1] * reach)])
    span = first.region.intersection(line)
    for piece in getattr(span, "geoms", [span]):
        if piece.geom_type == "LineString" and not piece.is_empty:
            along = [(x - probe.x) * across[0] + (y - probe.y) * across[1] for x, y in piece.coords]
            side.plot(along, [first.z + layer_h] * len(along), color=FAIL, lw=3, solid_capstyle="butt", zorder=5)
    frame(side, bounds_of(cut, Point(0, first.z)), bottom_room=0.2)
    side.axhline(first.z + layer_h, color=FAIL, lw=0.6, ls=":", zorder=4)
    side.set_title("Side cut through the roof (red)")
    for target in (whole, zoom, side):
        scale_bar(target)
    others = len(failing) - 1
    note = "; ".join(filter(None, [moved_note, f"{others} more like it on this part, not drawn" if others else ""]))
    bridging = printer().bridging
    legend = [patch_key(PART, "Layer below: where strands can land", EDGE), patch_key(LIGHT, "This layer", EDGE),
              patch_key(ROOF, "Roof over air", FAIL), line_key(OK, "Strand landing on plastic at both ends"),
              line_key(FAIL, "Strand ending over air")]
    note += ("; " if note else "") + (f"prints that came out clean had {bridging.min_anchored:.0%} of strands anchored, "
                                      f"or strands no longer than {bridging.short_strand_mm:g} mm")
    return View("bridge-layer", fig, legend, note)


def _across_the_roof(region):
    """A unit vector across a roof's long side, from its smallest enclosing rectangle."""
    corners = np.asarray(region.minimum_rotated_rectangle.exterior.coords)[:3]
    edges = [corners[1] - corners[0], corners[2] - corners[1]]
    longest = max(edges, key=np.linalg.norm)
    if np.linalg.norm(longest) < 1e-9:
        return np.array([1.0, 0.0])
    along = longest / np.linalg.norm(longest)
    return np.array([-along[1], along[0]])


def view_connected(design, finding, part_id):
    mesh = design.mesh(part_id)
    pieces = [shell for shell in mesh.split(only_watertight=False) if shell.volume > 0]
    if not pieces:
        raise NoView("the exported mesh has no piece with positive volume (it's inside out or not closed), "
                     "so there are no bodies to tell apart")
    coupon = design.built[part_id].role == "coupon"
    bed = mesh.bounds[0][2]
    if coupon:
        loose = [piece for piece in pieces if piece.bounds[0][2] > bed + 0.01]
    else:
        largest = max(pieces, key=lambda piece: piece.volume)
        loose = [piece for piece in pieces if piece is not largest]
    if not loose:
        raise NoView("today's split of the mesh finds it in one piece, so there's no loose piece to draw")
    fig, (top, side) = new_figure("two")
    kept = [piece for piece in pieces if not any(piece is other for other in loose)]
    for target, axes in ((top, (0, 1)), (side, (0, 2))):
        for piece in kept:
            silhouette(target, piece, axes, PART, z=1)
        for piece in loose:
            silhouette(target, piece, axes, FAIL, z=3)
        low, high = mesh.bounds
        frame(target, (low[axes[0]], low[axes[1]], high[axes[0]], high[axes[1]]))
        span = max(high[axes[0]] - low[axes[0]], high[axes[1]] - low[axes[1]])
        for piece in loose:  # a sliver too small to see gets a ring round it
            plow, phigh = piece.bounds
            if max(phigh[axes[0]] - plow[axes[0]], phigh[axes[1]] - plow[axes[1]]) < 0.04 * span:
                centre = ((plow[axes[0]] + phigh[axes[0]]) / 2, (plow[axes[1]] + phigh[axes[1]]) / 2)
                target.add_patch(Circle(centre, 0.035 * span, fill=False, ec=FAIL, lw=1.4, zorder=5))
        scale_bar(target)
    side.axhline(bed, color=EDGE, lw=0.8, ls="--")
    top.set_title("From above")
    side.set_title("From the side (dashed: the bed)")
    loose_words = "Piece off the bed" if coupon else "Separate piece"
    legend = [patch_key(PART, "On the bed" if coupon else "Largest piece"), patch_key(FAIL, f"{loose_words} ({len(loose)})"),
              line_key(FAIL, "Ring round a piece too small to see")]
    return View("pieces", fig, legend, "red is drawn on top, so a piece inside another still shows")


def view_bed_fit(design, finding, part_id):
    mesh = design.mesh(part_id)
    bed = printer().bed_mm
    fig, (top, side) = new_figure("two")
    low, high = mesh.bounds
    centre = (low + high) / 2
    moved = mesh.copy()
    moved.apply_translation([bed[0] / 2 - centre[0], bed[1] / 2 - centre[1], -low[2]])
    for target, axes, size in ((top, (0, 1), (bed[0], bed[1])), (side, (0, 2), (bed[0], bed[2]))):
        target.add_patch(Rectangle((0, 0), size[0], size[1], fill=False, ec=BOARD, lw=1.2, ls="--", zorder=4))
        silhouette(target, moved, axes, PART, z=2)
        mlow, mhigh = moved.bounds
        target.add_patch(Rectangle((mlow[axes[0]], mlow[axes[1]]), mhigh[axes[0]] - mlow[axes[0]], mhigh[axes[1]] - mlow[axes[1]],
                                   fill=False, ec=FAIL, lw=1.4, zorder=3))
        frame(target, bounds_of(box_of((0, 0) + tuple(size)), box_of((mlow[axes[0]], mlow[axes[1]], mhigh[axes[0]], mhigh[axes[1]]))))
        scale_bar(target)
    top.set_title("From above")
    side.set_title("From the side")
    return View("bed", fig, [patch_key(PART, "The part, as it would print"), line_key(FAIL, "Its outline"),
                             line_key(BOARD, "The printer's build volume", "--")])


# ---- the hand knob ----

def _single_final(design):
    part, why = sections.single_final(design.sub, design.built)
    if part is None:
        raise NoView(why)
    return part.mesh


def _knob_pocket(design, mesh):
    nut = design.args("R3")["nut"]
    spec = catalog.resolve(nut)
    return spec, nuts._nuts_pocket(mesh, spec["af"])


def _nut_turned(hole, af, centre):
    return max(range(0, 60, 2), key=lambda degrees: nuts._hexagon(centre, af, degrees).intersection(hole).area)


def _draw_across(ax, mesh, spec, found):
    """The pocket cut across at its tightest layer, with a real nut (catalog size, chamfered corners) laid in it."""
    af = spec["af"]
    centre = (found.centre.x, found.centre.y)
    z, layer, hole = ff._tightest_layer(mesh, found, af, centre)
    nut_shape = nuts._hexagon(found.centre, af, _nut_turned(hole, af, found.centre))
    fill(ax, layer, fc=PART, ec=EDGE, lw=0.6)
    fill(ax, nut_shape, z=3, fc="none", ec=HARDWARE, lw=1.4, ls="--")
    overlap = nut_shape.difference(hole)
    if overlap.area > 0.005:
        fill(ax, overlap, z=4, fc=HARDWARE, ec="#9a4a0c", lw=1.2, alpha=0.9)
    ax.text(found.centre.x, found.centre.y, f"pocket {found.across:.2f}\nnut {af:g}", ha="center", va="center", fontsize=7.5, zorder=6)
    frame(ax, nut_shape.buffer(af * 0.55).bounds, pad=0)
    ax.set_title(f"Cut across at z = {z - mesh.bounds[0][2]:.1f} mm, where the nut meets most plastic")
    scale_bar(ax)
    return overlap.area


def _draw_knob_side(ax, mesh, spec, found, centre=None, along=(1, 0, 0)):
    """A vertical cut through the pocket (or the part's middle), with the nut drawn at catalog size where it seats."""
    bottom = mesh.bounds[0][2]
    cx, cy = (found.centre.x, found.centre.y) if found else (centre if centre else mesh.bounds[:, :2].mean(axis=0))
    cut = plane_cut([mesh], (cx, cy, bottom), along, (0, 0, 1))
    fill(ax, cut, fc=PART, ec=EDGE, lw=0.6)
    nut_box = None
    if found:
        z0, z1 = found.z[0] - bottom, found.z[1] - bottom
        start = z1 - spec["h"] if found.opens == ["bed"] else z0
        nut_box = box_of((-spec["af"] / 2, start, spec["af"] / 2, start + spec["h"]))
        fill(ax, nut_box, z=3, fc=HARDWARE, ec=HARDWARE, alpha=0.45, lw=1)
        overlap = nut_box.intersection(cut)
        if overlap.area > 0.01:
            fill(ax, overlap, z=4, fc=HARDWARE, ec="none", alpha=0.9)
        ax.plot([spec["af"] / 2 + 0.6] * 2, [z0, z1], color=BOARD, lw=2, zorder=5)
    frame(ax, bounds_of(cut, nut_box))
    scale_bar(ax)
    return cut


def view_knob_r1(design, finding):
    finals = [part for part in design.sub.parts if part.role == "final" and design.built[part.id].ok]
    if len(finals) < 2:
        raise NoView("only one final part built, so there's nothing beside it to show")
    fig, (ax,) = new_figure("one")
    wanted = design.args("R1").get("n", 1)
    x = 0.0
    for number, part in enumerate(finals, 1):
        mesh = design.built[part.id].mesh.copy()
        low, high = mesh.bounds
        mesh.apply_translation([x - low[0], -low[1], 0])
        silhouette(ax, mesh, (0, 1), PART)
        ax.text(x + (high[0] - low[0]) / 2, high[1] - low[1] + 1.5, f"{number} of {len(finals)}: {part.id}", ha="center",
                va="bottom", fontsize=8, color=FAIL)
        x += high[0] - low[0] + 6
    frame(ax, (0, 0, x - 6, max(design.built[p.id].mesh.extents[1] for p in finals) + 7))
    ax.set_title(f"{len(finals)} parts marked final (not test prints), from above; the request asks for {wanted}")
    scale_bar(ax)
    legend = [patch_key(PART, f"A part the design marks as final: {len(finals)} here, {wanted} wanted")]
    return View("final-parts", fig, legend)


def view_knob_r2(design, finding):
    mesh = _single_final(design)
    args = design.args("R2")
    fig, (ax,) = new_figure("one")
    silhouette(ax, mesh, (0, 1), PART)
    low, high = mesh.bounds
    centre = (low[:2] + high[:2]) / 2
    for diameter, style in ((args["d"], "-"), (args["d"] * (1 - args["tol_frac"]), "--"), (args["d"] * (1 + args["tol_frac"]), "--")):
        ax.add_patch(Circle(centre, diameter / 2, fill=False, ec=OK, lw=1.2, ls=style, zorder=3))
    width = float(max(mesh.extents[:2]))
    ax.annotate("", xy=(low[0], low[1] - 1.5), xytext=(high[0], low[1] - 1.5), arrowprops={"arrowstyle": "<->", "color": FAIL})
    ax.text(centre[0], low[1] - 2.2, f"{width:.1f} mm", ha="center", va="top", color=FAIL)
    reach = args["d"] * (1 + args["tol_frac"]) / 2
    frame(ax, (centre[0] - reach, centre[1] - reach - 4, centre[0] + reach, centre[1] + reach))
    ax.set_title("The knob from above")
    scale_bar(ax)
    return View("plan-width", fig, [patch_key(PART, "The knob"), line_key(OK, f"{args['d']} mm asked"),
                                    line_key(OK, f"{args['tol_frac']:.0%} either way", "--")])


def view_knob_r3(design, finding):
    if "grader error" in finding["detail"]:
        raise NoView("the grader crashed reading this shape, so there's no reading of the pocket to draw")
    mesh = _single_final(design)
    spec, found = _knob_pocket(design, mesh)
    if found is None:
        return _view_no_pocket(mesh, spec)
    fig, (across, side) = new_figure("two")
    _draw_across(across, mesh, spec, found)
    _draw_knob_side(side, mesh, spec, found)
    opens = " and ".join(found.opens) if found.opens else "neither face"
    side.set_title(f"Side cut: pocket opens to {opens}")
    legend = [patch_key(PART, "Printed knob, cut", EDGE), patch_key(HARDWARE, f"{spec['size']} nut at catalog size"),
              line_key(BOARD, "The hex pocket's height", lw=2.4)]
    return View("pocket-cut", fig, legend)


def _view_no_pocket(mesh, spec):
    """No hex pocket the nut's size along z: the part cut down its middle and across where its central hole is
    widest, with the nut drawn where a pocket would have to be."""
    bottom, top = mesh.bounds[0][2], mesh.bounds[1][2]
    centre = Point(*mesh.bounds[:, :2].mean(axis=0))
    best = None
    for z in np.linspace(bottom + 0.1, top - 0.1, 40):
        layer = ff.cut_across(mesh, z)
        if layer is None:
            continue
        holes = [Polygon(ring) for poly in polygons_of(layer) for ring in poly.interiors]
        here = [hole for hole in holes if hole.buffer(0.5).contains(centre)]
        score = -abs(sections.clear_width(here[0]) - spec["af"]) if here else -math.inf
        if best is None or score > best[0]:
            best = (score, z, layer, here[0] if here else None)
    if best is None:
        raise NoView("the part has no cross-section to cut")
    _, z, layer, hole = best
    nut_at = polylabel(hole, tolerance=0.01) if hole is not None else centre
    nut_shape = nuts._hexagon(nut_at, spec["af"], _nut_turned(hole, spec["af"], nut_at) if hole is not None else 0)
    fig, (across, side) = new_figure("two")
    fill(across, layer, fc=PART, ec=EDGE, lw=0.6)
    fill(across, nut_shape, z=3, fc="none", ec=HARDWARE, lw=1.4, ls="--")
    overlap = nut_shape.difference(hole) if hole is not None else nut_shape
    fill(across, overlap, z=4, fc=HARDWARE, ec="none", alpha=0.8)
    frame(across, nut_shape.buffer(spec["af"] * 0.7).bounds, pad=0)
    across.set_title(f"Cut across at z = {z - bottom:.1f} mm, the middle hole nearest the nut's size")
    scale_bar(across)
    _draw_knob_side(side, mesh, spec, None, (nut_at.x, nut_at.y))
    side.set_title("Side cut down the middle")
    legend = [patch_key(PART, "Printed knob, cut", EDGE), line_key(HARDWARE, f"{spec['size']} nut ({spec['af']} mm across flats)", "--"),
              patch_key(HARDWARE, "Where the nut overlaps plastic")]
    if hole is None:
        words = "no hole runs where the nut would go, so the nut is drawn over the part's middle"
    elif sections.clear_width(hole) >= spec["af"] - nuts.TOL:
        words = "the nut is drawn in the middle hole nearest its size: the hole isn't hex-shaped, so a nut there could turn"
    else:
        words = "the nut is drawn in the middle hole nearest its size, which is too small for it"
    return View("pocket-cut", fig, legend, words)


NUT_TONES = {"holds": "ok", "won't go in": "bad", "falls out": "bad", "loose": "warn", "goes in": "info"}


def view_knob_r4(design, finding):
    if "grader error" in finding["detail"]:
        raise NoView("the grader crashed reading this shape, so there's no reading of the pocket to draw")
    mesh = _single_final(design)
    spec, found = _knob_pocket(design, mesh)
    if found is None:
        raise NoView("today's grader finds no hex pocket to read, so there's no fit to draw")
    label = design.args("R4")["label"]
    clearance = round(found.across - spec["af"], 3) or 0.0
    fig, (across, side, line) = new_figure("two+ruler")
    _draw_across(across, mesh, spec, found)
    _draw_knob_side(side, mesh, spec, found)
    side.set_title("Side cut through the pocket")
    rows = nuts._measured().get((label, found.shape), [])
    shape_words = {"plain": "plain hex", "ribbed": "ribs or clips", "lip": "a lip"}[found.shape]
    if rows:
        marks = [(c, f"{c:+.2f} {outcome}", NUT_TONES.get(outcome, "info")) for c, outcome in rows]
        ruler(line, marks, clearance, f"this pocket {clearance:+.2f}",
              title=f"{label} nut in printed pockets with {shape_words}: clearance over the nut's {spec['af']} mm")
    else:
        line.set_axis_off()
        line.text(0.5, 0.5, f"No recorded print of an {label} pocket with {shape_words}", ha="center", va="center", transform=line.transAxes)
    legend = [patch_key(PART, "Printed knob, cut", EDGE), line_key(HARDWARE, f"{label} nut at catalog size", "--"),
              patch_key(HARDWARE, "Where the nut has to push plastic aside"), line_key(BOARD, "The hex pocket's height", lw=2.4)]
    return View("pocket-fit", fig, legend, f"pocket {found.across:.2f} mm across flats against the nut's {spec['af']} mm")


def view_knob_r5(design, finding):
    if "grader error" in finding["detail"]:
        raise NoView("the grader crashed reading this shape, so there's no bolt path to draw")
    mesh = _single_final(design)
    spec, found = _knob_pocket(design, mesh)
    if found is None:
        raise NoView("today's grader finds no hex pocket to line the bolt up with")
    d_min = design.args("R5")["d_min"]
    layer_h, cuts = sections.sections_by_layer(mesh, 2, nuts.LAYER)
    clears = [nuts._clear_around(sections.holes_in(polys), nuts._outline(polys), found.centre) for polys in cuts]
    blocked = [i for i, clear in enumerate(clears) if clear < d_min - nuts.TOL]
    if not blocked:
        raise NoView("today's check finds the bolt's path clear, so there's no blockage to draw")
    fig, (across, side) = new_figure("two")
    bottom = mesh.bounds[0][2]

    def blocked_area(along):  # the cut that shows the most of the blockage: a web across half the bore hides in the other
        cut = plane_cut([mesh], (found.centre.x, found.centre.y, bottom), along, (0, 0, 1))
        bands = [box_of((-d_min / 2, i * layer_h, d_min / 2, (i + 1) * layer_h)) for i in blocked]
        return merged(bands).intersection(cut).area
    along = max(((1, 0, 0), (0, 1, 0)), key=blocked_area)
    cut = _draw_knob_side(side, mesh, spec, found, along=along)
    height = mesh.extents[2]
    side.add_patch(Rectangle((-d_min / 2, 0), d_min, height, fill=False, ec=TEXT, lw=1, ls=":", zorder=6))
    for index in blocked:
        band = box_of((-d_min / 2, index * layer_h, d_min / 2, (index + 1) * layer_h)).intersection(cut)
        fill(side, band, z=7, fc=FAIL, ec=FAIL, lw=0.5)
    side.set_title("Side cut: bolt's path dotted")
    first = blocked[0]
    fill(across, merged(cuts[first]), fc=PART, ec=EDGE, lw=0.6)
    across.add_patch(Circle((found.centre.x, found.centre.y), d_min / 2, fill=False, ec=FAIL, lw=1.4, ls="--", zorder=5))
    if 0 < clears[first] < math.inf:
        across.add_patch(Circle((found.centre.x, found.centre.y), clears[first] / 2, fill=False, ec=OK, lw=1.2, zorder=5))
    frame(across, Point(found.centre.x, found.centre.y).buffer(spec["af"] * 1.1).bounds, pad=0)
    across.set_title(f"Cut across at z = {(first + 0.5) * layer_h:.1f} mm")
    scale_bar(across)
    legend = [patch_key(PART, "Printed knob, cut", EDGE), line_key(FAIL, f"The bolt needs {d_min} mm clear", "--"),
              patch_key(FAIL, "Plastic in the bolt's way"), patch_key(HARDWARE, f"{spec['size']} nut at catalog size")]
    note = ""
    if blocked_area(along) < 0.01:
        note = (f"no plastic shows in the bolt's path in a side cut: the check's slice at z = {(first + 0.5) * layer_h:.1f} mm "
                "reads that layer as closed, which a face lying at that height or an unclean mesh can cause")
    return View("bolt-path", fig, legend, note)


# ---- the closet door wheel ----

def _wheel_meshes(design, seat_range):
    finals = wheel._finals(design.sub, design.built)
    if not finals:
        raise NoView("no wheel to read: a final part didn't build")
    wheels = [mesh for mesh in finals if wheel._middle_side(mesh) >= seat_range[0]] or finals
    return wheels[:2]


@dataclass
class WheelCut:
    mesh: object
    axis: int
    cut: object  # the section, horizontal across the bore, vertical along the axis from its low face
    stack: list  # the bore's hole per layer, or None
    layer: float
    runs: list  # (first layer, end layer, Seat) for each seat-sized stretch


def _wheel_cut(mesh, seat_range, bearing_width=7.0, bearings=2):
    axis = int(mesh.extents.argmin())
    stack, layer = wheel._axle(mesh, axis, seat_range)
    in_plane = [other for other in range(3) if other != axis]
    point = mesh.bounds.mean(axis=0)
    if stack:
        centre = min(stack, key=sections.clear_width).centroid
        point[in_plane[0]], point[in_plane[1]] = centre.x, centre.y
    point[axis] = mesh.bounds[0][axis]
    u, v = np.eye(3)[in_plane[0]], np.eye(3)[axis]
    cut = plane_cut([mesh], point, u, v)
    runs = []
    if stack:
        tightest = min(sections.clear_width(hole) for hole in stack)
        for sized, group in groupby(enumerate(stack), key=lambda pair: wheel._sized(sections.clear_width(pair[1]), seat_range)):
            group = list(group)
            if sized:
                seat = wheel._read_seat([hole for _, hole in group], layer, tightest, bearing_width, bearings)
                runs.append((group[0][0], group[-1][0] + 1, seat))
    return WheelCut(mesh, axis, cut, stack, layer, runs)


def _bearing(start, width=BEARING["width"]):
    """A 608's cross-section in the cut: two rings' halves either side of the bore, from `start` along the axis."""
    inner, outer = BEARING["bore"] / 2, BEARING["od"] / 2
    return merged([box_of((-outer, start, -inner, start + width)), box_of((inner, start, outer, start + width))])


def _draw_bearings(ax, cut, wanted=2):
    """A bearing in each seat, as many as fit from the seat's open end, and any still needed at a face with no seat,
    where they'd have to go; orange where one overlaps plastic."""
    length = cut.layer * len(cut.stack) if cut.stack else float(cut.mesh.extents[cut.axis])
    width = BEARING["width"]
    starts, used_ends = [], set()
    for first, end, seat in cut.runs:
        for n in range(seat.bearings):
            if first == 0:
                starts.append(first * cut.layer + n * width)
                used_ends.add("low")
            elif cut.stack and end == len(cut.stack):
                starts.append(end * cut.layer - (n + 1) * width)
                used_ends.add("high")
            else:
                starts.append(first * cut.layer + n * width)
    extra = []
    for end in ("low", "high"):
        if len(starts) + len(extra) >= wanted:
            break
        if end not in used_ends:
            extra.append(0.0 if end == "low" else length - width)
    if len(extra) == 2 and length < 2 * width:  # too thin for two: stack them, so they show standing out of the wheel
        extra = [0.0, width]
    for start in starts:
        fill(ax, _bearing(start), z=3, fc=HARDWARE, ec=HARDWARE, alpha=0.45, lw=0.8)
    for start in extra:
        fill(ax, _bearing(start), z=3, fc="none", ec=HARDWARE, lw=1.2, ls="--")
    overlap = merged([_bearing(start) for start in starts + extra]).intersection(cut.cut)
    if overlap.area > 0.05:
        fill(ax, overlap, z=4, fc=HARDWARE, ec="none", alpha=0.9)
    return len(extra)


def _draw_seat_marks(ax, cut, seat_range):
    outer = BEARING["od"] / 2 + 1.5
    for first, end, seat in cut.runs:
        ax.plot([outer, outer], [first * cut.layer, end * cut.layer], color=BOARD, lw=2.4, zorder=5)
        ax.text(outer + 0.8, (first + end) / 2 * cut.layer, f"{seat.across:.2f}", fontsize=6.8, color=BOARD, va="center", zorder=5)


def _wheel_panel(ax, cut, title, bolt=None):
    if min(cut.mesh.extents) < 0.01:
        raise NoView(f"the wheel built as a flat sheet {min(cut.mesh.extents):.2f} mm thick, so there's no section to cut")
    require(cut.cut, "a cut down the wheel's axle")
    fill(ax, cut.cut, fc=PART, ec=EDGE, lw=0.6)
    length = float(cut.mesh.extents[cut.axis])
    if bolt:
        ax.add_patch(Rectangle((-bolt / 2, -1.5), bolt, length + 3, fill=False, ec=TEXT, lw=1, ls=":", zorder=6))
    frame(ax, bounds_of(cut.cut, box_of((-BEARING["od"] / 2 - 1, 0, BEARING["od"] / 2 + 5, length))))
    ax.set_title(title)
    scale_bar(ax)


def _wheel_layout(count, ruler_too=False):
    if count == 1:
        fig, axes = new_figure("one+ruler" if ruler_too else "one")
        return fig, axes[:1], (axes[1] if ruler_too else None)
    fig, axes = new_figure("two+ruler" if ruler_too else "two")
    return fig, axes[:2], (axes[2] if ruler_too else None)


WHEEL_LEGEND = [patch_key(PART, "Printed wheel, cut through the bore", EDGE), patch_key(HARDWARE, "608 bearing (22 x 8 x 7 mm), in its seat"),
                line_key(BOARD, "Seat-sized stretch, its width in mm", lw=2.4)]


def view_wheel_r2(design, finding):
    args = design.args("R2")
    cuts = [_wheel_cut(mesh, args["seat_range"], args["bearing_width"], args["bearings"]) for mesh in _wheel_meshes(design, args["seat_range"])]
    fig, axes, _ = _wheel_layout(len(cuts))
    missing = 0
    for ax, cut in zip(axes, cuts):
        _wheel_panel(ax, cut, "Cut down the axle" if len(cuts) == 1 else "One wheel part, cut down the axle")
        missing += _draw_bearings(ax, cut, args["bearings"] if len(cuts) == 1 else 1)
        _draw_seat_marks(ax, cut, args["seat_range"])
    legend = WHEEL_LEGEND + ([line_key(HARDWARE, "A bearing with no seat, where it would have to go", "--")] if missing else [])
    note = ("no hole runs all the way through the wheel, and the check reads seats only along a through bore"
            if all(cut.stack is None for cut in cuts) else "")
    return View("wheel-cut", fig, legend, note)


def view_wheel_r3(design, finding):
    args = design.args("R3")
    cuts = [_wheel_cut(mesh, args["seat_range"], args["bearing_width"], args["bearings"]) for mesh in _wheel_meshes(design, args["seat_range"])]
    if not any(cut.runs for cut in cuts):
        raise NoView("today's grader finds no seat to read")
    fig, axes, line = _wheel_layout(len(cuts), ruler_too=True)
    for ax, cut in zip(axes, cuts):
        _wheel_panel(ax, cut, "Cut down the axle")
        _draw_bearings(ax, cut, args["bearings"] if len(cuts) == 1 else 1)
        _draw_seat_marks(ax, cut, args["seat_range"])
    seats = [seat.across for cut in cuts for _, _, seat in cut.runs]
    measured = (numbers(finding["detail"]) or [min(seats)])[0]
    marks = [(args["too_tight"], f"{args['too_tight']} wouldn't take it", "bad"), (args["holds"][0], f"{args['holds'][0]} held", "ok"),
             (args["holds"][1], f"{args['holds'][1]} held", "ok"), (args["too_loose"], f"{args['too_loose']} fell out", "bad")]
    ruler(line, marks, measured, f"this seat {measured:.2f}", title="608 bearing in printed seats: seat width (mm)",
          spans=[(args["holds"][0], args["holds"][1], "held", "ok")])
    return View("wheel-seat-fit", fig, WHEEL_LEGEND, "the bearing is drawn at its catalog 22 mm; the difference is too small to see, so the line below carries it")


def view_wheel_r4(design, finding):
    args = design.args("R4")
    finals = wheel._finals(design.sub, design.built)
    if not finals:
        raise NoView("no wheel to read: a final part didn't build")
    # the wheel and, if another printed part on the bolt is tighter (a cap or sleeve), that one too
    wheels = [mesh for mesh in finals if wheel._middle_side(mesh) >= args["seat_range"][1]] or finals[:1]
    others = [mesh for mesh in finals if not any(mesh is w for w in wheels)]
    def tightest(mesh):
        found = wheel._tightest_bore(mesh, args["seat_range"])
        return math.inf if found is None else found
    drawn = wheels[:1] + sorted(others, key=tightest)[:1]
    cuts = [_wheel_cut(mesh, args["seat_range"]) for mesh in drawn]
    no_hole = all(cut.stack is None for cut in cuts) or not numbers(finding["detail"])
    fig, axes, line = _wheel_layout(len(cuts), ruler_too=not no_hole)
    bolt = args["bolt"]
    for ax, cut in zip(axes, cuts):
        _wheel_panel(ax, cut, "Cut down the axle", bolt=bolt)
        rod = box_of((-bolt / 2, -1.5, bolt / 2, float(cut.mesh.extents[cut.axis]) + 1.5))
        if cut.stack:
            widths = [sections.clear_width(hole) for hole in cut.stack]
            index = int(np.argmin(widths))
            ax.plot([-widths[index] / 2, widths[index] / 2], [(index + 0.5) * cut.layer] * 2, color=FAIL, lw=2.2, zorder=7)
            ax.text(widths[index] / 2 + 1, (index + 0.5) * cut.layer, f"{widths[index]:.2f} clear", color=FAIL, fontsize=7, va="center", zorder=7)
        blocked = rod.intersection(cut.cut)
        if blocked.area > 0.01:
            fill(ax, blocked, z=7, fc=FAIL, ec="none", alpha=0.85)
    legend = [patch_key(PART, "Printed wheel, cut through the bore", EDGE), line_key(TEXT, f"M8 bolt, {bolt} mm", ":"),
              patch_key(FAIL, "Plastic in the bolt's way")]
    if not no_hole:
        marks = [(d, f"{d:g} {how}", "warn" if how == "screws in" else "ok") for d, how in bolt_fits.printed_holes(args["thread"])]
        marks.append((args["fine"], f"{args['fine']} ISO fine", "info"))
        measured = numbers(finding["detail"])[0]
        ruler(line, marks, measured, f"tightest {measured:.2f}", title="M8 bolt through printed holes, by hand (mm)")
    return View("wheel-bolt", fig, legend)


def view_wheel_r1(design, finding):
    args = design.args("R1")
    finals = wheel._finals(design.sub, design.built)
    if not finals:
        raise NoView("no final part built")
    mesh = max(finals, key=lambda found: max(found.extents))
    cut = _wheel_cut(mesh, design.args("R2").get("seat_range", [20, 26]))
    fig, (ax,) = new_figure("one")
    fill(ax, cut.cut, fc=PART, ec=EDGE, lw=0.6)
    minx, miny, maxx, maxy = cut.cut.bounds
    ax.annotate("", xy=(minx, maxy + 2), xytext=(maxx, maxy + 2), arrowprops={"arrowstyle": "<->", "color": TEXT})
    ax.text((minx + maxx) / 2, maxy + 2.6, f"{maxx - minx:.1f} mm across (asked {args['across'][0]} to {args['across'][1]})", ha="center", fontsize=7.5)
    ax.annotate("", xy=(maxx + 2, miny), xytext=(maxx + 2, maxy), arrowprops={"arrowstyle": "<->", "color": FAIL})
    ax.text(maxx + 3, (miny + maxy) / 2, f"{maxy - miny:.1f} mm wide\n(old wheel {args['max_width']} at most)", color=FAIL, fontsize=7.5, va="center")
    pieces = [found for found in finals if wheel._middle_side(found) >= args["across"][0]]
    note = (f"{len(pieces)} wheel parts, whose widths add up; the widest is drawn" if len(pieces) > 1 else "")
    frame(ax, (minx, miny, maxx + 22, maxy + 5))
    ax.set_title("The wheel cut down its axle")
    scale_bar(ax)
    return View("wheel-size", fig, [patch_key(PART, "Printed wheel, cut", EDGE)], note)


# ---- the tripod plate ----

@dataclass
class PlateCut:
    mesh: object
    axis: int
    width_axis: int
    cut: object
    widths: list
    wide_end: object  # 0, -1 or None
    low: float  # the plate's low face along its thickness axis


def _plate(design):
    plate, axis = bolted._plate(design.sub, design.built)
    if plate is None:
        raise NoView("no plate built: a final part's code didn't run, so there's nothing to cut")
    return plate.mesh, axis


def _clamped_side(mesh, axis):
    """The plan axis across the side the clamp grips, as bolted._clamped_widths chooses it."""
    sides = bolted._edges_by_layer(mesh, axis)
    plan_axes = [other for other in range(3) if other != axis]
    shorter_first = sorted((0, 1), key=lambda side: mesh.extents[plan_axes[side]])
    side = max(shorter_first, key=lambda side: round(bolted._narrowing(sides[side]), 2))
    return side, plan_axes


def _plate_cut(mesh, axis, centre=None):
    side, plan_axes = _clamped_side(mesh, axis)
    point = mesh.bounds.mean(axis=0)
    if centre is not None:
        point[plan_axes[0]], point[plan_axes[1]] = centre
    point[axis] = mesh.bounds[0][axis]
    cut = plane_cut([mesh], point, np.eye(3)[plan_axes[side]], np.eye(3)[axis])
    widths, _ = bolted._clamped_widths(mesh, axis)
    return PlateCut(mesh, axis, plan_axes[side], cut, widths, bolted._wide_end(widths), float(mesh.bounds[0][axis]))


def _bore_holes(mesh, axis, bore):
    """The bore bolted._main_bore found, as its hole in each layer, followed as the check follows it: the stack whose
    widths match the bore's. None if it can't be found again."""
    fracs = bolted._layers(mesh, axis)
    layer_sets = [sections.holes(mesh, axis, frac) for frac in fracs]
    gap_sets = [bolted._gaps(unary_union(sections.section(mesh, axis, frac))) for frac in fracs]
    best = None
    for layers in (layer_sets, gap_sets):
        for start in layers[0]:
            stack, hole = [start], start
            for found in layers[1:]:
                hole = next((candidate for candidate in found if candidate.intersects(hole)), None)
                if hole is None:
                    break
                stack.append(hole)
            if len(stack) != len(bore.widths):
                continue
            error = sum(abs(sections.clear_width(h) - w) for h, w in zip(stack, bore.widths) if w is not None)
            if best is None or error < best[0]:
                best = (error, stack)
    return best[1] if best and best[0] < 0.05 * len(bore.widths) + 0.5 else None


def _plate_faces(ax, plate):
    """Name the plate's two faces in the cut: the wide one goes in the clamp."""
    minx, miny, maxx, maxy = plate.cut.bounds
    if plate.wide_end is None:
        return
    clamp_y, camera_y = (miny, maxy) if plate.wide_end == 0 else (maxy, miny)
    ax.text(maxx + 1, clamp_y, "clamp side\n(wide face)", fontsize=7, va="center", color=BOARD)
    ax.text(maxx + 1, camera_y, "camera side", fontsize=7, va="center", color=TEXT)


def _plate_panel(ax, plate, title, extra=None):
    require(plate.cut, "a cut through the plate")
    fill(ax, plate.cut, fc=PART, ec=EDGE, lw=0.6)
    minx, miny, maxx, maxy = plate.cut.bounds
    frame(ax, bounds_of(plate.cut, extra, box_of((minx, miny, maxx + 0.3 * (maxx - minx), maxy))))
    ax.set_title(title)
    _plate_faces(ax, plate)


def view_tripod_r1(design, finding):
    raise NoView("no final part built: the plate's code didn't produce a part, so there's no plate to draw")


def view_tripod_r2(design, finding):
    """The plate cut across the side the clamp grips, with the dovetail a clamp's lips can bear on dashed over it, and a
    zoom on one edge, where a fraction of a millimetre of taper shows."""
    mesh, axis = _plate(design)
    args = design.args("R2")
    plate = _plate_cut(mesh, axis)
    require(plate.cut, "a cut through the plate")
    fig, (ax, zoom) = new_figure("two")
    minx, miny, maxx, maxy = plate.cut.bounds
    narrow = args["narrows_by"]
    wide_low = plate.wide_end in (0, None) and plate.widths[0] >= plate.widths[-1]
    if wide_low:
        ghost = Polygon([(minx, miny), (maxx, miny), (maxx - narrow, maxy), (minx + narrow, maxy)])
    else:
        ghost = Polygon([(minx + narrow, miny), (maxx - narrow, miny), (maxx, maxy), (minx, maxy)])
    _plate_panel(ax, plate, "Cut across the side the clamp grips", ghost)
    fill(ax, ghost, z=4, fc="none", ec=OK, lw=1.3, ls="--")
    height = maxy - miny
    window = (minx - 0.6 * height * 0.3, miny - 0.5, minx + max(narrow * 3, height * 0.6), maxy + 0.5)
    ax.add_patch(Rectangle(window[:2], window[2] - window[0], window[3] - window[1], fill=False, ec=FAIL, lw=1, zorder=6))
    fill(zoom, plate.cut, fc=PART, ec=EDGE, lw=1.0)
    fill(zoom, ghost, z=4, fc="none", ec=OK, lw=1.8, ls="--")
    frame(zoom, window, pad=0)
    _, narrowing = bolted._clamped_widths(mesh, axis)
    zoom.set_title(f"One edge, zoomed: both edges move in by {narrowing:.2f} mm; {narrow} wanted")
    for target in (ax, zoom):
        scale_bar(target)
    legend = [patch_key(PART, "Printed plate, cut", EDGE), line_key(OK, f"A dovetail the clamp's lips can bear on: each edge in by {narrow} mm", "--")]
    return View("plate-profile", fig, legend, f"widths {plate.widths[0]:.2f} mm at the low face, {plate.widths[-1]:.2f} mm at the high face")


def view_tripod_bolt(design, finding):
    """R3, R4 and R5: the plate cut through the bolt's bore, across the clamped side, with the bolt drawn in."""
    check = finding["check"]
    mesh, axis = _plate(design)
    args = design.args(check)
    if bolted._other_fastener(design.sub, args["bolt"]):
        raise NoView("the failure is in the hardware the design lists, not in the plate's shape")
    told = nuts.sentence_saying_to_clear_it(design.sub)
    bolt_across = args.get("too_tight", args.get("bolt_across"))
    bore = bolted._main_bore(mesh, axis, bolt_across if check == "R3" else args["bolt_across"], told is not None)
    side, plan_axes = _clamped_side(mesh, axis)
    stack = _bore_holes(mesh, axis, bore) if bore else None
    centre = None
    if stack:
        tight = min(stack, key=sections.clear_width).centroid
        centre = (tight.x, tight.y)
    plate = _plate_cut(mesh, axis, centre)
    if plate.cut.is_empty:  # the bore's centre found off the plate (a gap read open at the side): cut the middle instead
        plate = _plate_cut(mesh, axis)
    if plate.cut.is_empty:
        raise NoView("a cut through the plate comes back empty (the mesh isn't clean there)")
    thickness = float(mesh.extents[axis])
    ruler_needed = check in ("R3", "R4") and bore is not None and "recess opens" not in finding["detail"]
    fig, axes = new_figure("one+ruler" if ruler_needed else "one")
    ax = axes[0]
    shank = 6.35
    minx, miny, maxx, maxy = plate.cut.bounds
    extra = None
    if bore is None:
        rod = box_of((-shank / 2, -2, shank / 2, thickness + 2))
        fill(ax, rod, z=5, fc="none", ec=TEXT, lw=1, ls=":")
        fill(ax, rod.intersection(plate.cut), z=6, fc=FAIL, ec="none", alpha=0.85)
        note = "no hole runs through the plate, so the bolt is drawn down its middle"
        if rod.intersection(plate.cut).area < 0.01:
            note = ("this cut down the middle shows an opening, but the check found no hole it could follow through "
                    "every layer of the plate, so it reads none")
    else:
        recess = bore.recess()
        layer_y = [(k + 0.5) * bore.layer for k in range(len(bore.widths))]
        offset = (thickness - bore.thickness) / 2  # a pad standing on a face isn't the plate's own layers
        tight_k = int(np.argmin(bore.widths))
        ax.plot([-bore.widths[tight_k] / 2, bore.widths[tight_k] / 2], [offset + layer_y[tight_k]] * 2, color=FAIL, lw=2, zorder=7)
        has_recess = recess.depth >= bolted.MIN_RECESS
        floor = (offset + recess.depth if recess.end == 0 else offset + bore.thickness - recess.depth) if has_recess else None
        if check == "R5":
            length = args["bolt_length"]
            start = floor if floor is not None else offset  # the head's underside
            direction = 1 if (not has_recess or recess.end == 0) else -1
            if not has_recess:
                start = offset if plate.wide_end in (0, None) else offset + bore.thickness
                direction = 1 if plate.wide_end in (0, None) else -1
            tip = start + direction * length
            rod = box_of((-shank / 2, min(start, tip), shank / 2, max(start, tip)))
            fill(ax, rod, z=5, fc=HARDWARE, ec=HARDWARE, alpha=0.5, lw=0.8)
            far = offset + bore.thickness if direction == 1 else offset
            camera = box_of((minx, far, maxx, far + direction * 8))
            fill(ax, camera, z=0, fc="#dfe7f2", ec=BOARD, lw=0.8, ls="--")
            want = far + direction * args["min_reach"]
            ax.plot([-shank, shank], [want, want], color=OK, lw=1.6, zorder=8)
            ax.text(shank + 0.6, want, f"{args['min_reach']} mm needed", color=OK, fontsize=7, va="center")
            into = (tip - far) * direction
            words = f"tip {into:.1f} mm in" if into > 0.05 else ("tip only reaches the camera" if into > -0.05 else "tip short of the camera")
            ax.text(-shank - 0.6, tip, words, color=FAIL, fontsize=7, va="center", ha="right", zorder=9)
            extra = camera
            note = f"an assumed {length} mm bolt, head on the recess floor"
        else:
            rod = box_of((-shank / 2, -2, shank / 2, thickness + 2))
            fill(ax, rod, z=5, fc="none", ec=TEXT, lw=1, ls=":")
            if has_recess:
                ax.annotate("head goes here", xy=(0, floor), xytext=(maxx * 0.55, floor + (2.5 if recess.end == 0 else -2.5)),
                            fontsize=7, color=HARDWARE, arrowprops={"arrowstyle": "-|>", "color": HARDWARE}, zorder=9)
                ax.plot([-recess.width / 2, recess.width / 2], [floor] * 2, color=HARDWARE, lw=2, zorder=8)
            note = f"tightest {bore.tightest:.2f} mm clear (red line)"
            if has_recess:
                note += f"; recess {recess.width:.2f} mm across, {recess.depth:.1f} mm deep"
    _plate_panel(ax, plate, "The plate cut through the bolt hole, across the clamped side", extra)
    scale_bar(ax)
    if ruler_needed:
        line = axes[1]
        if check == "R4":
            value = bore.recess().width
            ruler(line, [(args["too_tight"], f"{args['too_tight']} too tight", "bad"), (args["fits"], f"{args['fits']} fit", "ok")],
                  value, f"this recess {value:.2f}", title="The webcam bolt's head in printed recesses: recess width (mm)")
        elif bore.tightest > 10:
            ruler(line, [(args["head_stopped"], f"{args['head_stopped']} stops the head", "ok"),
                         (args["head_passes"], f"{args['head_passes']} head pulls through", "bad")],
                  bore.tightest, f"this hole {bore.tightest:.2f}", title="The webcam bolt's head over printed holes (mm)")
        else:
            marks = [(d, f"{d:g} {how}", "bad" if how == "screws in" else "ok") for d, how in bolt_fits.printed_holes(args["thread"])]
            ruler(line, marks, bore.tightest, f"this hole {bore.tightest:.2f}", title="1/4-20 bolt through printed holes, by hand (mm)")
    legend = [patch_key(PART, "Printed plate, cut", EDGE), line_key(TEXT, "The bolt's shank, 6.35 mm (1/4-20)", ":"),
              line_key(FAIL, "Tightest point of the hole", lw=2.2)]
    if check == "R5" and bore is not None:
        legend = [patch_key(PART, "Printed plate, cut", EDGE), patch_key(HARDWARE, "Assumed 10 mm bolt"),
                  patch_key("#dfe7f2", "The camera", BOARD, "--"), line_key(OK, "How far in it needs to go")]
    return View("plate-bolt-cut", fig, legend, note)


# ---- the Estoa light box ----

def _readable(draw):
    def run(design, finding):
        try:
            return draw(design, finding)
        except NotReadable:
            raise NoView(enclosure.UNREADABLE) from None
    run.__name__ = draw.__name__
    return run


def _hole_span_named(spans, detail):
    named = re.search(r"hole at ([+-]\d+(?:\.\d+)?) mm", detail or "")
    if named:
        at = float(named.group(1))
        return min(spans, key=lambda span: abs(span.coords[0][0] - at))
    return spans[0]


@_readable
def view_estoa_r1(design, finding):
    args = design.args("R1")
    piece = design.piece()
    board = enclosure._placed_once(piece, args["item"])
    if board is None:
        raise NoView(f"{args['item']} isn't placed once")
    meshes = placed.into(piece.meshes, board)
    spans = enclosure._hole_spans(args["holes_r"])
    behind = merged(placed.section(meshes, -0.3))
    disk = Point(0, 0).buffer(args["board_radius"], quad_segs=64)
    in_board = merged(placed.section(meshes, args["board_thickness"][0] / 2)).intersection(disk)
    fig, (whole, zoom) = new_figure("two")
    span = _hole_span_named(spans, finding["detail"])
    for ax in (whole, zoom):
        fill(ax, behind, fc=PART, ec=EDGE, lw=0.5)
        fill(ax, in_board, z=3, fc=FAIL, ec=FAIL, lw=0.4, alpha=0.75)
        ax.add_patch(Circle((0, 0), args["board_radius"], fill=False, ec=BOARD, lw=1, ls="--", zorder=4))
        for each in spans:
            xs, ys = each.xy
            ax.plot(xs, ys, color=BOARD, lw=2.5, zorder=5, solid_capstyle="butt")
    for x in (span.coords[0][0], span.coords[-1][0]):
        zoom.add_patch(Circle((x, 0), args["hole"] / 2, fill=False, ec=BOARD, lw=0.9, zorder=6))
        zoom.add_patch(Circle((x, 0), args["screw"] / 2, fill=False, ec=HARDWARE, lw=1.2, ls="--", zorder=6))
    frame(whole, disk.bounds)
    centre = span.centroid
    frame(zoom, centre.buffer(7).bounds, pad=0)
    whole.set_title("From the disk's side")
    zoom.set_title(f"Its hole at {span.coords[0][0]:+.1f} mm")
    for ax in (whole, zoom):
        scale_bar(ax)
    legend = [patch_key(PART, "Plastic 0.3 mm behind the disk", EDGE), patch_key(FAIL, "Plastic where the disk's board itself is"),
              line_key(BOARD, "The disk's edge, and where each hole can be", "--"), line_key(HARDWARE, "An M3 screw at either end of that range", "--")]
    return View("disk-plan", fig, legend)


@_readable
def view_estoa_r2(design, finding):
    args = design.args("R2")
    piece = design.piece()
    board = enclosure._placed_once(piece, args["item"])
    if board is None:
        raise NoView(f"{args['item']} isn't placed once")
    meshes = placed.into(piece.meshes, board)
    through = enclosure._screws_through(piece, board, enclosure._hole_spans(args["holes_r"]))
    if not through:
        raise NoView("no screw goes through the disk's holes, so there's no screw to cut along")
    thin, thick = min(args["board_thickness"]), max(args["board_thickness"])
    named = numbers(finding["detail"])[:1]
    pick = next(((span, screw, crossing) for span, screw, crossing in through if named and abs(screw.length - named[0]) < 0.01), through[0])
    _, screw, crossing = pick
    cut = plane_cut(meshes, (crossing[0], crossing[1], 0), (1, 0, 0), (0, 0, 1))
    fig, (ax,) = new_figure("one")
    fill(ax, cut, fc=PART, ec=EDGE, lw=0.6)
    radius = args["screw_d"] / 2
    fill(ax, box_of((-12, 0, 12, thick)), z=2, fc=DISK, ec=BOARD, lw=0.8)
    shank = box_of((-radius, thick - screw.length, radius, thick))
    fill(ax, shank, z=3, fc=HARDWARE, ec=HARDWARE, alpha=0.5, lw=0.8)
    fill(ax, box_of((-2.75, thick, 2.75, thick + 2.0)), z=3, fc=HARDWARE, ec=HARDWARE, alpha=0.5, lw=0.8)
    hit = shank.intersection(cut)
    fill(ax, hit, z=4, fc=FAIL, ec="none", alpha=0.9)
    frame(ax, (-12, thick - screw.length - 6, 12, thick + 4))
    ax.set_title(f"Cut along the screw at {crossing[0]:+.1f} mm, the disk on top")
    scale_bar(ax)
    legend = [patch_key(PART, "Printed box, cut", EDGE), patch_key(DISK, f"The disk's board, drawn {thick} mm thick (its thickest)", BOARD),
              patch_key(HARDWARE, f"The {screw.length:g} mm screw (head not to scale)"), patch_key(FAIL, "Where the screw meets plastic")]
    return View("screw-cut", fig, legend)


def _turned(socket):
    """A frame whose +z runs out of the socket, x and y its long and short sides (enclosure._clear_passage's)."""
    return Placement(origin=socket.origin, x_axis=placed.to_piece(socket, (0, 1, 0)) - np.asarray(socket.origin),
                     z_axis=placed.to_piece(socket, (1, 0, 0)) - np.asarray(socket.origin))


def _covered(obstacles, socket, window, start):
    meshes = placed.into(obstacles, _turned(socket))
    beam = placed.box((-window / 2, -window / 2, start), (window / 2, window / 2, enclosure.REACH))
    return placed.shadow(placed.plastic_in(meshes, beam))


@_readable
def view_estoa_r3(design, finding):
    if "isn't inside the box" in finding["detail"]:
        return _view_open_sides(design, finding, "R3")
    args = design.args("R3")
    piece = design.piece()
    socket = enclosure._placed_once(piece, args["item"])
    if socket is None:
        raise NoView(f"{args['item']} isn't placed once")
    disk = enclosure._placed_once(piece, args["disk"])
    obstacles = enclosure._obstacles(piece, disk, args["disk_radius"], args["disk_thickness"], True)
    window = args["window"]
    near = _covered(obstacles, socket, window, 0.05)
    far = _covered(obstacles, socket, window, args["failed_from"])
    head = enclosure.measured_plug(args["plug"])
    bare = (head.head_width_mm, head.head_thickness_mm)
    fits = (bare[0] + 2 * args["margin"], bare[1] + 2 * args["margin"])
    fig, (ax,) = new_figure("one")
    ax.add_patch(Rectangle((-window / 2, -window / 2), window, window, fc="white", ec="#999", lw=0.6, zorder=0))
    fill(ax, near, z=1, fc=LIGHT, ec=EDGE, lw=0.4)
    fill(ax, far, z=2, fc=PART, ec=EDGE, lw=0.6)
    fill(ax, enclosure._stadium(*bare), z=4, fc=ROOF, ec=FAIL, alpha=0.85, lw=1.2)
    fill(ax, enclosure._stadium(*fits), z=4, fc="none", ec=FAIL, lw=1.0, ls="--")
    body = args["socket_body"]
    ax.add_patch(Rectangle((-body[1] / 2, -body[2] / 2), body[1], body[2], fc="none", ec=BOARD, lw=1.2, zorder=5))
    frame(ax, (-window / 2, -window / 2, window / 2, window / 2), pad=0.5)
    ax.set_title("Looking into the USB-C port from outside")
    scale_bar(ax)
    legend = [patch_key(PART, f"In the way {args['failed_from']:g} mm or more out from the port", EDGE),
              patch_key(LIGHT, "In the way nearer the port", EDGE),
              patch_key(ROOF, f"Plug head {bare[0]} x {bare[1]} mm (Dan's measured plug)", FAIL),
              line_key(FAIL, f"With {args['margin']} mm a side", "--"), line_key(BOARD, "The port", lw=1.4)]
    return View("port-view", fig, legend)


def _arrow(ax, start, direction, words, length):
    end = (start[0] + direction[0] * length, start[1] + direction[1] * length)
    ax.annotate("", xy=end, xytext=start, arrowprops={"arrowstyle": "-|>", "color": FAIL, "lw": 1.6}, zorder=9)
    ax.text(end[0], end[1], words, color=FAIL, fontsize=7, ha="center", va="bottom" if direction[1] >= 0 else "top", zorder=9)


def _view_open_sides(design, finding, check):
    """The board isn't inside the box: cuts through the point the check started from, with an arrow along each side it
    found nothing on."""
    args = design.args(check)
    piece = design.piece()
    item = enclosure._placed_once(piece, args["item"])
    if item is None:
        raise NoView(f"{args['item']} isn't placed once")
    disk = enclosure._placed_once(piece, args["disk"])
    open_words = re.search(r"nothing on its (.+?) side", finding["detail"])
    sides = [side.strip() for side in open_words.group(1).split(",")] if open_words else []
    if check == "R3":  # in the piece's own frame, from a point inside the ESP32
        meshes, start = piece.meshes, placed.to_piece(item, args["inside"])
        disk_mesh = None
        if disk is not None:
            disk_mesh = placed.column(args["disk_radius"], 0.0, args["disk_thickness"])
            disk_mesh.apply_transform(placed.matrix(disk))
        frame_words = "the assembled box"
    else:  # in the board's frame, from its middle, 2 mm above it
        meshes = placed.into(piece.meshes, item)
        start = np.array([0.0, 0.0, 2.0])
        disk_mesh = None
        if disk is not None:
            disk_mesh = placed.column(args["disk_radius"], 0.0, args["disk_thickness"])
            disk_mesh.apply_transform(placed.matrix(disk))
            disk_mesh = placed.into([disk_mesh], item)[0]
        frame_words = "the perfboard's frame"
    vertical_axis = 1 if any(side[1] == "y" for side in sides) and not any(side[1] == "x" for side in sides) else 0
    fig, (plan, side_ax) = new_figure("two")
    span = max(float(np.ptp(np.vstack([mesh.bounds for mesh in meshes]), axis=0).max()), 40.0)
    plan_cut = merged(placed.section(meshes, start[2]))
    u = np.eye(3)[vertical_axis]
    side_cut = plane_cut(meshes, start, u, (0, 0, 1))
    disk_plan = merged(placed.section([disk_mesh], start[2])) if disk_mesh is not None else Polygon()
    disk_side = plane_cut([disk_mesh], start, u, (0, 0, 1)) if disk_mesh is not None else Polygon()
    plan_shifted = merged([Polygon([(x - start[0], y - start[1]) for x, y in poly.exterior.coords],
                                   [[(x - start[0], y - start[1]) for x, y in ring.coords] for ring in poly.interiors])
                           for poly in polygons_of(plan_cut)])
    disk_plan_shifted = merged([Polygon([(x - start[0], y - start[1]) for x, y in poly.exterior.coords]) for poly in polygons_of(disk_plan)])
    fill(plan, plan_shifted, fc=PART, ec=EDGE, lw=0.5)
    fill(plan, disk_plan_shifted, z=0, fc=DISK, ec=BOARD, lw=1.0)
    fill(side_ax, side_cut, fc=PART, ec=EDGE, lw=0.5)
    fill(side_ax, disk_side, z=0, fc=DISK, ec=BOARD, lw=1.0)
    for ax in (plan, side_ax):
        ax.plot([0], [0], marker="o", ms=6, color=BOARD, zorder=8)
    def past_the_edge(geom, direction):
        """An arrow long enough to leave the drawn plastic: it shows the way out the check found."""
        minx, miny, maxx, maxy = bounds_of(geom, Point(0, 0))
        edge = {(1, 0): maxx, (-1, 0): -minx, (0, 1): maxy, (0, -1): -miny}[direction]
        return max(edge, 0) + max(span * 0.08, 4)
    for words in sides:
        sign = 1 if words[0] == "+" else -1
        axis = "xyz".index(words[1])
        if axis < 2:
            direction = (sign, 0) if axis == 0 else (0, sign)
            _arrow(plan, (0, 0), direction, f"nothing on {words}", past_the_edge(plan_shifted, direction))
        if axis == 2 or axis == vertical_axis:
            direction = (0, sign) if axis == 2 else (sign, 0)
            _arrow(side_ax, (0, 0), direction, f"nothing on {words}", past_the_edge(side_cut, direction))
    for ax, geom in ((plan, plan_shifted), (side_ax, side_cut)):
        frame(ax, bounds_of(geom, Point(0, 0).buffer(span * 0.12), *[Point(t.get_position()) for t in ax.texts]))
        scale_bar(ax)
    plan.set_title(f"Cut across at the board ({frame_words})")
    side_ax.set_title(f"Side cut along {'xyz'[vertical_axis]}, up is +z")
    what = "a point inside the ESP32" if check == "R3" else "the perfboard's middle, 2 mm above it"
    legend = [patch_key(PART, "Printed box, cut", EDGE), patch_key(DISK, "The disk's board, cut", BOARD),
              Line2D([], [], marker="o", color=BOARD, ls="", label=f"Where the check looks from: {what}"),
              line_key(FAIL, "The check's probe out that side: it meets no plastic")]
    return View("enclosure-cut", fig, legend, "each red arrow follows one of the check's 1 mm probes out to the open air")


@_readable
def view_estoa_r5(design, finding):
    if "isn't inside the box" in finding["detail"]:
        return _view_open_sides(design, finding, "R5")
    args = design.args("R5")
    piece = design.piece()
    board = enclosure._placed_once(piece, args["item"])
    if board is None:
        raise NoView(f"{args['item']} isn't placed once")
    meshes = placed.into(piece.meshes, board)
    slab = enclosure.Envelope(*args["slab"])
    certain = enclosure.Envelope(*args["certain"])
    in_slab = "sits in printed plastic" in finding["detail"]
    z = -slab.height / 2 if in_slab else 2.0
    cut = merged(placed.section(meshes, z))
    fig, (ax,) = new_figure("one")
    fill(ax, cut, fc=PART, ec=EDGE, lw=0.6)
    board_shape = box_of((-slab.width / 2, -slab.length / 2, slab.width / 2, slab.length / 2))
    hole_across, hole_along, keep_clear = args["holes"]
    posts = merged([Point(sx * hole_across, sy * hole_along).buffer(keep_clear) for sx in (-1, 1) for sy in (-1, 1)])
    fill(ax, board_shape.difference(posts), z=2, fc=DISK, ec=BOARD, alpha=0.8, lw=1.0)
    ax.add_patch(Rectangle((-certain.width / 2, -certain.length / 2), certain.width, certain.length, fill=False, ec=BOARD, lw=1, ls=":", zorder=3))
    if in_slab:
        fill(ax, cut.intersection(board_shape.difference(posts)), z=4, fc=FAIL, ec=FAIL, alpha=0.85, lw=0.4)
    frame(ax, board_shape.buffer(18).bounds)
    ax.set_title(f"The box cut {'through the perfboard' if in_slab else '2 mm above the perfboard'}, in the board's frame")
    scale_bar(ax)
    legend = [patch_key(PART, "Printed box, cut", EDGE), patch_key(DISK, "The perfboard (less its corner holes, where posts may go)", BOARD),
              line_key(BOARD, "Where the ESP32 certainly stands", ":")]
    if in_slab:
        legend.append(patch_key(FAIL, "Plastic where the board is"))
    return View("board-cut", fig, legend)


@_readable
def view_estoa_r6(design, finding):
    """The back as R6 reads it (a cut at_depth from the wall) with each keyhole's entry, slot and a head at the slot's
    end, zoomed on a failing one; for a slot whose plastic is as thick as the screws stand out, a cut across the slot
    there, as enclosure._lip probes it beside the slot."""
    args = design.args("R6")
    piece = design.piece()
    wall_z = piece.wall_z
    back = merged(placed.section(piece.meshes, wall_z + args["at_depth"]))
    holes = [Polygon(ring) for poly in polygons_of(back) for ring in poly.interiors]
    found = [keyhole for keyhole in (enclosure._keyhole(hole) for hole in holes) if keyhole is not None]
    limits = (enclosure.EntryLimits.model_validate(args["entry"]), enclosure.SlotLimits.model_validate(args["slot"]),
              args["travel"], enclosure.AngleLimits.model_validate(args["angle"]), args["standoff"])
    head = args.get("head", 9.9)
    up = enclosure._hanging_up(found) if found else np.array([0.0, 1.0])
    verdicts = [enclosure._keyhole_verdict(piece.meshes, wall_z, keyhole, up, *limits, args.get("head")) for keyhole in found]
    if found and not any(verdict.ok is False for verdict in verdicts) and finding["ok"] is False:
        raise NoView("today's check finds every keyhole hangs, so there's no failing keyhole to draw")
    worst = next((k for k, v in zip(found, verdicts) if v.ok is False), found[0] if found else None)
    worst_words = next((v.detail for k, v in zip(found, verdicts) if k is worst), "")
    lip_failure = worst is not None and "plastic at its slot" in worst_words
    fig, axes = new_figure("two+strip" if lip_failure else ("two" if found else "one"))
    overview = axes[0]

    def draw_keyholes(ax, lw):
        fill(ax, back, fc=PART, ec=EDGE, lw=0.5)
        for keyhole, verdict in zip(found, verdicts):
            centre, entry, slot, direction, travel = keyhole
            colour = FAIL if verdict.ok is False else (OK if verdict.ok else WARN)
            ax.add_patch(Circle(centre, entry / 2, fill=False, ls="--", ec=colour, lw=lw, zorder=4))
            rest = centre + direction * travel
            ax.add_patch(Circle(rest, head / 2, fill=False, ec=HARDWARE, lw=lw * 1.2, zorder=5))
            ax.annotate("", xy=rest, xytext=centre, arrowprops={"arrowstyle": "-|>", "color": colour, "lw": lw}, zorder=6)
    draw_keyholes(overview, 0.9)
    span = bounds_of(back)
    size = max(span[2] - span[0], span[3] - span[1])
    if found:
        middle = ((span[0] + span[2]) / 2, (span[1] + span[3]) / 2)
        overview.annotate("up", xy=(middle[0] + up[0] * size * 0.2, middle[1] + up[1] * size * 0.2), xytext=middle, color=BOARD,
                          arrowprops={"arrowstyle": "-|>", "color": BOARD, "lw": 1.4}, fontsize=7.5, zorder=7)
    frame(overview, span)
    overview.set_title("The back, seen from the front")
    scale_bar(overview)
    legend = [patch_key(PART, f"Printed back, cut {args['at_depth']} mm from the wall", EDGE),
              line_key(FAIL, "Keyhole entry (red: fails, green: passes)", "--"),
              line_key(HARDWARE, f"A {head} mm screw head where the slot ends"), line_key(BOARD, "Up when it hangs: the way the slots run")]
    if not found:
        return View("back-keyholes", fig, legend, "no keyhole shape was found in the back")
    centre, entry, slot, direction, travel = worst
    rest = centre + direction * travel
    zoom = axes[1]
    draw_keyholes(zoom, 1.4)
    window = Point(*((centre + rest) / 2)).buffer(max(head, entry) * 0.5 + travel / 2 + 3)
    frame(zoom, window.bounds, pad=0)
    zoom.text(centre[0], centre[1], f"entry {entry:.1f}", fontsize=6.8, ha="center", va="center", zorder=8)
    zoom.set_title(f"Zoomed: slot {slot:.2f} wide")
    scale_bar(zoom)
    overview.add_patch(Circle(window.centroid.coords[0], size * 0.06, fill=False, ec=FAIL, lw=1.2, zorder=8))
    if lip_failure:
        side = axes[2]
        across = np.array([-direction[1], direction[0]])
        cut = plane_cut(piece.meshes, (rest[0], rest[1], wall_z), (across[0], across[1], 0), (0, 0, 1))
        standoff = args["standoff"]
        lip = max(enclosure._lip(piece.meshes, wall_z, rest + across * (slot / 2 + 1.0)),
                  enclosure._lip(piece.meshes, wall_z, rest - across * (slot / 2 + 1.0)))
        reach = head / 2 + 6
        fill(side, cut, fc=PART, ec=EDGE, lw=0.5)
        side.add_patch(Rectangle((-reach, -3), 2 * reach, 3, fc="#d9d4c7", ec="none", zorder=0))
        shank = box_of((-4.17 / 2, 0, 4.17 / 2, standoff))
        screw_head = box_of((-head / 2, standoff, head / 2, standoff + 1.5))
        fill(side, merged([shank, screw_head]), z=3, fc=HARDWARE, ec=HARDWARE, alpha=0.5, lw=0.8)
        fill(side, screw_head.intersection(cut), z=4, fc=FAIL, ec="none", alpha=0.9)
        side.annotate("", xy=(reach - 1, lip), xytext=(reach - 1, 0), arrowprops={"arrowstyle": "<->", "color": TEXT, "lw": 0.9})
        side.text(reach - 1.6, lip / 2, f"plastic {lip:.1f}", fontsize=6.8, ha="right", va="center")
        frame(side, (-reach, -3, reach, max(lip, standoff + 1.5) + 2), bottom_room=0.25)
        side.set_title(f"Across the slot at the head: screws stand {standoff} mm out")
        scale_bar(side)
        legend += [patch_key("#d9d4c7", "The wall"), patch_key(FAIL, "Where the screw head meets plastic (head height not to scale)")]
    return View("back-keyholes", fig, legend)


@_readable
def view_estoa_r7(design, finding):
    tolerance = design.args("R7")["tolerance"]
    piece = design.piece()
    wall_z = piece.wall_z
    keyholes = [hole for poly in placed.section(piece.meshes, wall_z + 0.3) for ring in poly.interiors
                if enclosure._keyhole(hole := Polygon(ring)) is not None]
    proud = []
    for screw in piece.screws:  # as enclosure.nothing_proud reads each screw
        if any(hole.buffer(0.5).contains(Point(screw.head[0], screw.head[1])) for hole in keyholes):
            continue
        tilt = np.sqrt(max(0.0, 1 - screw.direction[2] ** 2))
        head_low = min(screw.head[2], screw.head[2] - screw.head_h * screw.direction[2]) - screw.head_d / 2 * tilt
        if min(head_low, screw.tip[2]) < wall_z - tolerance:
            proud.append((screw, wall_z - min(head_low, screw.tip[2])))
    if not proud:
        raise NoView("today's check finds no screw standing out of the back")
    screw, out = proud[0]
    flat = np.array([screw.direction[0], screw.direction[1], 0.0])
    u = unit(flat) if np.linalg.norm(flat) > 0.2 else np.array([1.0, 0.0, 0.0])
    cut = plane_cut(piece.meshes, screw.head, u, (0, 0, 1))
    fig, (ax,) = new_figure("one")
    fill(ax, cut, fc=PART, ec=EDGE, lw=0.5)
    wall = wall_z - screw.head[2]
    along = np.array([screw.direction @ u, screw.direction[2]])
    tip = along * screw.length
    radius = 1.5
    body = LineString([(0, 0), tip]).buffer(radius, cap_style="flat")
    if screw.head_d:
        side = np.array([-along[1], along[0]])
        corners = [side * screw.head_d / 2, -side * screw.head_d / 2, -side * screw.head_d / 2 - along * screw.head_h,
                   side * screw.head_d / 2 - along * screw.head_h]
        body = body.union(Polygon(corners))
    fill(ax, body, z=3, fc=HARDWARE, ec=HARDWARE, alpha=0.55, lw=0.8)
    fill(ax, body.intersection(box_of((-500, wall - 500, 500, wall))), z=4, fc=FAIL, ec="none", alpha=0.9)
    reach = max(screw.length, 12)
    ax.add_patch(Rectangle((-reach, wall - 4), reach * 2, 4, fc="#d9d4c7", ec="none", zorder=0))
    ax.axhline(wall, color=EDGE, lw=0.8)
    frame(ax, (-reach, wall - 5, reach, max(reach * 0.8, wall + 6)))
    ax.set_title(f"Cut along the {screw.item} screw; the wall at the bottom")
    scale_bar(ax)
    more = f"{len(proud) - 1} more like it, not drawn" if len(proud) > 1 else ""
    legend = [patch_key(PART, "Printed box, cut", EDGE), patch_key(HARDWARE, f"The {screw.length:g} mm screw where the design puts it"),
              patch_key("#d9d4c7", "The wall the box hangs on"), patch_key(FAIL, f"Screw standing out of the back ({out:.2f} mm)")]
    return View("screw-proud", fig, legend, more)


# ---- the M5 spacer (control) ----

def view_spacer(design, finding):
    mesh = _single_final(design)
    if min(mesh.extents) < 0.01:
        raise NoView(f"the part built as a flat sheet {min(mesh.extents):.2f} mm thick, so there's no section to cut")
    fig, (top, side) = new_figure("two")
    for ax, axes in ((top, (0, 1)), (side, (0, 2))):
        silhouette(ax, mesh, axes, PART)
        low, high = mesh.bounds
        frame(ax, (low[axes[0]], low[axes[1]], high[axes[0]], high[axes[1]]))
        scale_bar(ax)
    return View("spacer-views", fig, [patch_key(PART, "The spacer")])


# ---- which view for which finding ----

DRAWERS = {
    ("*", "bridges"): view_bridges, ("*", "connected_bodies"): view_connected, ("*", "bed_fit"): view_bed_fit,
    ("nut-knob", "R1"): view_knob_r1, ("nut-knob", "R2"): view_knob_r2, ("nut-knob", "R3"): view_knob_r3,
    ("nut-knob", "R4"): view_knob_r4, ("nut-knob", "R5"): view_knob_r5,
    ("bearing-wheel", "R1"): view_wheel_r1, ("bearing-wheel", "R2"): view_wheel_r2, ("bearing-wheel", "R3"): view_wheel_r3,
    ("bearing-wheel", "R4"): view_wheel_r4,
    ("tripod-plate", "R1"): view_tripod_r1, ("tripod-plate", "R2"): view_tripod_r2, ("tripod-plate", "R3"): view_tripod_bolt, ("tripod-plate", "R4"): view_tripod_bolt,
    ("tripod-plate", "R5"): view_tripod_bolt,
    ("estoa-light", "R1"): view_estoa_r1, ("estoa-light", "R2"): view_estoa_r2, ("estoa-light", "R3"): view_estoa_r3,
    ("estoa-light", "R5"): view_estoa_r5, ("estoa-light", "R6"): view_estoa_r6, ("estoa-light", "R7"): view_estoa_r7,
    ("m5-spacer", "R2"): view_spacer, ("m5-spacer", "R3"): view_spacer, ("m5-spacer", "R4"): view_spacer,
}
PER_PART = {"bridges", "connected_bodies", "bed_fit"}
KIND_GUESS = {"bridges": "bridge-layer", "connected_bodies": "pieces", "bed_fit": "bed", "builds": "build-error"}


def choose(family, check):
    """The drawer for a check, or None."""
    return DRAWERS.get(("*", check)) or DRAWERS.get((family, check))


def not_reached(finding):
    return finding.get("ok") is None and any(phrase in (finding.get("detail") or "") for phrase in results_page.CONSEQUENCE)


def wanted_findings(findings, declined, failed_only=False):
    """Failed findings first (counted, then test prints), then genuinely ungraded ones; never a check that wasn't
    reached (another check already failed what it needs). A declined trial counts no failures."""
    if declined:
        return []
    failed = [f for f in findings if f.get("ok") is False]
    failed.sort(key=lambda f: bool(f.get("test_print")))
    if failed_only:
        return failed
    ungraded = [f for f in findings if f.get("ok") is None and not not_reached(f) and not f.get("test_print")]
    return failed + ungraded


def reader_words_keeping(text, part_ids):
    """results_site.reader_words (test print, not coupon), leaving part ids as the design named them."""
    text = text.replace("test coupon ", "test print ")  # the graders' own phrase, before any id that is the word itself
    kept = {}
    for index, part_id in enumerate(sorted(part_ids, key=len, reverse=True)):
        if part_id and part_id in text:
            kept[f"\x00{index}\x00"] = part_id
            text = re.sub(rf"(?<![\w-]){re.escape(part_id)}(?![\w-])", f"\x00{index}\x00", text)
    text = results_site.reader_words(text)
    for token, part_id in kept.items():
        text = text.replace(token, part_id)
    return text


def caption_of(design, finding, note=""):
    family = design.family
    titles = results_site.CHECK_TITLES["*"] | results_site.CHECK_TITLES.get(family, {})
    title = titles.get(finding["check"], finding["check"])
    state = "not graded" if finding.get("ok") is None else "fails"
    where = f" ({'test print ' if finding.get('test_print') else ''}{finding['part']})" if finding.get("part") not in ("-", None) else ""
    detail = reader_words_keeping(re.sub(r"\s+", " ", finding.get("detail") or "").strip(), [part.id for part in design.sub.parts])
    if len(detail) > 230:
        detail = detail[:227].rsplit(" ", 1)[0] + "…"
    text = f"{title}{where}: {state}. {detail[:1].upper()}{detail[1:]}"
    if note:
        text += f" ({results_site.reader_words(note)})"
    return text


def safe(name):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name)[:60] or "view"


def draw_one(design, finding):
    """{check, part, state, test_print, kind, caption, object, no_view_reason} for one finding. Never raises."""
    check = finding["check"]
    part_id = media.owner(finding, design.sub) if check in PER_PART else finding.get("part")
    entry = {"check": check, "part": finding.get("part"), "state": "not graded" if finding.get("ok") is None else "fail",
             "test_print": bool(finding.get("test_print")), "kind": KIND_GUESS.get(check, "none"), "caption": caption_of(design, finding),
             "object": None, "no_view_reason": None}
    if check == "builds":
        entry["no_view_reason"] = "the code didn't run; there is no shape to draw"
        return entry
    drawer = choose(design.family, check)
    if drawer is None:
        entry["no_view_reason"] = "no drawn view exists for this check yet"
        return entry
    started = time.time()
    try:
        view = drawer(design, finding, part_id) if check in PER_PART else drawer(design, finding)
        entry["kind"] = view.kind
        entry["caption"] = caption_of(design, finding, view.note)
        data = render(view, entry["caption"])
        owner = part_id if part_id not in (None, "-") else "design"
        name = f"{safe(owner)}-{safe(check)}{'-ng' if finding.get('ok') is None else ''}.webp"
        entry["object"] = store(data, name)
    except NoView as why:
        entry["no_view_reason"] = str(why)
        plt.close("all")
    except Exception as error:  # a figure that can't be drawn mustn't stop the rest; say so plainly
        entry["no_view_reason"] = f"the drawing failed ({type(error).__name__}: {str(error)[:120]})"
        entry["error"] = traceback.format_exc()[-800:]
        plt.close("all")
    entry["seconds"] = round(time.time() - started, 2)
    return entry


def store(data: bytes, name):
    digest = hashlib.sha256(data).hexdigest()[:8]
    path = OBJECTS / digest / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    return f"{digest}/{name}"


def record_path(folder):
    return RECORDS / (re.sub(r"[^\w.-]+", "__", media.rel(folder)) + ".json")


def process(folder, failed_only=False):
    findings, declined = media.saved_findings(folder)
    wanted = wanted_findings(findings, declined, failed_only)
    record = {"rel": media.rel(folder), "version": VERSION, "failed_only": failed_only, "views": []}
    if not wanted:
        return record
    try:
        design = load_design(folder)
    except Exception as error:
        reason = f"the design couldn't be loaded ({type(error).__name__}: {str(error)[:120]})"
        record["views"] = [{"check": f["check"], "part": f.get("part"), "state": "not graded" if f.get("ok") is None else "fail",
                            "test_print": bool(f.get("test_print")), "kind": KIND_GUESS.get(f["check"], "none"), "caption": f["detail"],
                            "object": None, "no_view_reason": reason} for f in wanted]
        return record
    record["views"] = [draw_one(design, finding) for finding in wanted]
    return record


def work(job):
    folder, failed_only = job
    path = record_path(folder)
    if path.exists():
        saved = json.loads(path.read_text())
        if saved.get("version") == VERSION and (failed_only or not saved.get("failed_only")):
            return saved
    started = time.time()
    record = process(folder, failed_only)
    record["seconds"] = round(time.time() - started, 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1, sort_keys=True))
    return record


# ---- the manifest ----

def saved_records():
    wanted = {media.rel(folder) for folder in media.design_folders()}
    records = [json.loads(path.read_text()) for path in sorted(RECORDS.glob("*.json"))]
    return [record for record in records if record["rel"] in wanted and record.get("version") == VERSION]


def view_ref(obj, uploaded):
    if obj is None:
        return None
    return media.url_of(obj) if obj in uploaded else (OBJECTS / obj).relative_to(ROOT).as_posix()


@cache
def pixel_size(obj):
    """(width, height) of a saved figure in pixels, so a page can reserve its exact shape."""
    from PIL import Image
    with Image.open(OBJECTS / obj) as picture:
        return picture.size


def manifest(records, uploaded):
    designs = {}
    for record in records:
        if not record["views"]:
            continue
        designs[record["rel"]] = [{"check": view["check"], "part": view["part"], "state": view["state"], "test_print": view["test_print"],
                                   "kind": view["kind"], "caption": view["caption"], "view": view_ref(view["object"], uploaded),
                                   "no_view_reason": view["no_view_reason"],
                                   "width": pixel_size(view["object"])[0] if view["object"] else None,
                                   "height": pixel_size(view["object"])[1] if view["object"] else None}
                                  for view in record["views"]]
    return {"version": VERSION, "designs": designs}


def upload(objects, workers):
    """Upload with the media script's uploader, pointed at this script's objects and ledger."""
    media.OBJECTS, media.LEDGER = OBJECTS, LEDGER
    return media.upload(objects, workers)


def report(records):
    views = [(record["rel"], view) for record in records for view in record["views"]]
    table = defaultdict(Counter)
    reasons = Counter()
    for rel, view in views:
        task = rel.split("/")
        family = next((part for part in task if part in ("tripod-plate", "bearing-wheel", "nut-knob", "estoa-light", "m5-spacer")), "?")
        key = (family, view["check"], view["state"] + (" tp" if view["test_print"] else ""))
        table[key]["findings"] += 1
        table[key]["drawn" if view["object"] else "none"] += 1
        if not view["object"]:
            reasons[(family, view["check"], re.sub(r"\d+(\.\d+)?", "N", view["no_view_reason"] or "")[:90])] += 1
    print(f"{'task':15} {'check':17} {'state':14} findings drawn none", file=sys.stderr)
    for key in sorted(table):
        row = table[key]
        print(f"{key[0]:15} {key[1]:17} {key[2]:14} {row['findings']:8} {row['drawn']:5} {row['none']:4}", file=sys.stderr)
    print("no-view reasons:", file=sys.stderr)
    for (family, check, reason), count in sorted(reasons.items()):
        print(f"  {count:4} {family} {check}: {reason}", file=sys.stderr)
    objects = sorted({view["object"] for _, view in views if view["object"]})
    total = sum((OBJECTS / obj).stat().st_size for obj in objects)
    print(f"{len(objects)} images, {total / 1e6:.1f} MB", file=sys.stderr)
    return objects


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--limit", type=int, help="process at most this many designs")
    parser.add_argument("--only", help="only designs whose path under results/runs contains this")
    parser.add_argument("--no-upload", action="store_true", help="draw, but don't upload")
    parser.add_argument("--failed-only", action="store_true", help="skip the not-graded checks")
    parser.add_argument("--manifest-only", action="store_true", help="rewrite the manifests from the saved records, drawing nothing")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--upload-workers", type=int, default=6, help="the media host rate-limits above 6")
    args = parser.parse_args()
    for folder in (RECORDS, OBJECTS, CACHE):
        folder.mkdir(parents=True, exist_ok=True)
    folders = [folder for folder in media.design_folders() if not args.only or args.only in media.rel(folder)]
    folders = folders[:args.limit] if args.limit else folders
    print(f"{len(folders)} designs", file=sys.stderr)
    started = time.time()
    with Pool(1 if args.manifest_only else args.workers, maxtasksperchild=10) as pool:
        if args.manifest_only:
            folders = []
        for count, _ in enumerate(pool.imap_unordered(work, [(folder, args.failed_only) for folder in folders]), 1):
            if count % 50 == 0:
                print(f"  {count}/{len(folders)} ({time.time() - started:.0f} s)", file=sys.stderr)
    records = saved_records()
    objects = report(records)
    uploaded = set(LEDGER.read_text().split()) if LEDGER.exists() else set()
    if not args.no_upload:
        done, failures = upload(objects, args.upload_workers)
        print(f"uploaded {done}; {len(failures)} failed", file=sys.stderr)
        uploaded = set(LEDGER.read_text().split()) if LEDGER.exists() else set()
    MANIFEST.write_text(json.dumps(manifest(records, uploaded), indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"wrote {MANIFEST.relative_to(ROOT)} in {time.time() - started:.0f} s", file=sys.stderr)
    missing = [obj for obj in objects if obj not in uploaded]
    if missing:
        print(f"{len(missing)} images aren't uploaded, so {COMMITTED.name} is left as it was", file=sys.stderr)
        return
    write_committed(records, uploaded)
    print(f"wrote {COMMITTED.relative_to(ROOT)}", file=sys.stderr)


def write_committed(records, uploaded):
    """The committed manifest, scripts/results_site_views.json: media-host URLs only, sorted, no local paths."""
    text = json.dumps(manifest(records, uploaded), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    assert "/Users/" not in text and str(Path.home()) not in text and "results/local" not in text
    COMMITTED.write_text(text)


if __name__ == "__main__":
    main()
