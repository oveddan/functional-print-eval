"""Task requirement graders, named in each task's requirements.yaml.

A requirement whose grader isn't built yet is reported as not graded, never as a pass,
and a grader that crashes on a submission records a failure instead of stopping the run.
"""
from functools import reduce

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import polylabel

from pbe.checks import Finding

FLOAT_EPS = 1e-4  # mm; STL coordinates are single-precision


def _finals(sub, built):
    return [built[p.id] for p in sub.parts if p.role == "final" and p.id in built]


def part_count(sub, built, n):
    finals = [p.id for p in sub.parts if p.role == "final"]
    return len(finals) == n, f"{len(finals)} printed part(s): {', '.join(finals)}"


def _single(sub, built):
    finals = _finals(sub, built)
    if len(finals) != 1:
        return None, f"expected one printed part, got {len(finals)}"
    if not finals[0].ok:
        return None, f"{finals[0].part} didn't build"
    return finals[0], ""


def _section(mesh, axis, frac):
    """The cross-section across `axis` at `frac` of the part's length, as polygons
    with their holes. The plane is axis-aligned, so the other two coordinates are the
    plane's; XOR of the section's loops nests the holes inside their outlines."""
    normal = np.eye(3)[axis]
    lo, hi = mesh.bounds[:, axis]
    origin = mesh.bounds.mean(axis=0)
    origin[axis] = lo + frac * (hi - lo)
    sec = mesh.section(plane_origin=origin, plane_normal=normal)
    if sec is None:
        return []
    keep = [i for i in range(3) if i != axis]
    loops = [Polygon(loop[:, keep]).buffer(0) for loop in sec.discrete if len(loop) >= 3]
    if not loops:
        return []
    shape = reduce(lambda a, c: a.symmetric_difference(c), loops)
    return [g for g in getattr(shape, "geoms", [shape]) if isinstance(g, Polygon)]


def _holes(mesh, axis, frac):
    return [Polygon(ring) for poly in _section(mesh, axis, frac) for ring in poly.interiors]


def _hole_axis(mesh):
    """The axis whose middle cross-section shows exactly one hole, else None."""
    return next((a for a in range(3) if len(_holes(mesh, a, 0.5)) == 1), None)


def _diameter(poly):
    """The largest distance between two points of the polygon's outline."""
    pts = np.asarray(poly.exterior.coords)
    return float(np.max(np.linalg.norm(pts[:, None] - pts[None], axis=-1)))


def extents(sub, built, mm, tol):
    """The part's bounding box, largest side first, matches `mm` within `tol`."""
    b, why = _single(sub, built)
    if b is None:
        return False, why
    got = sorted(b.mesh.extents, reverse=True)
    want = sorted(mm, reverse=True)
    ok = all(abs(g - w) <= tol for g, w in zip(got, want, strict=True))
    return ok, f"{' x '.join(f'{g:.2f}' for g in got)} mm (want {' x '.join(map(str, want))} ± {tol})"


def round_outline(sub, built, min_roundness):
    """The outline across the hole's axis (or the longest axis) is round: its area over
    the area of a circle as wide as the outline is at least `min_roundness`. A circle
    scores 1, a hexagon 0.83, a square 0.64."""
    b, why = _single(sub, built)
    if b is None:
        return False, why
    axis = _hole_axis(b.mesh)
    if axis is None:
        axis = int(np.argmax(b.mesh.extents))
    polys = _section(b.mesh, axis, 0.5)
    if len(polys) != 1:
        return False, f"{len(polys)} separate pieces in the middle cross-section"
    outline = Polygon(polys[0].exterior)
    d = _diameter(outline)
    score = outline.area / (np.pi * d * d / 4)
    return score >= min_roundness, f"roundness {score:.3f} (want at least {min_roundness}), {d:.2f} mm across"


def through_hole(sub, built, d_min, d_max, step=0.2, tol=0.01):
    """One hole runs the part's full length and fits the bolt. Every cross-section along
    the hole's axis, one per `step` mm (a layer), has exactly one hole, and the bolt must
    pass every one: its clear width (largest inscribed circle) is at least d_min. The fit
    is set where the hole is tightest, so the upper limit applies there: that section is
    at most d_max across at its widest. Lead-in chamfers and counterbores at the ends are
    wider and pass; an oversized or slotted bore fails.
    `tol` only lowers d_min: the mesh's facets make a modeled hole read up to about
    0.002 mm narrow, which would fail a hole drawn at exactly d_min. d_max gets only
    FLOAT_EPS: the STL's single-precision floats read 5.8 as 5.80000022."""
    b, why = _single(sub, built)
    if b is None:
        return False, why
    axis = _hole_axis(b.mesh)
    if axis is None:
        return False, "no single hole through the middle of the part"
    length = float(b.mesh.extents[axis])
    n = max(int(round(length / step)), 2)
    sections = []  # (clear width, widest point) per slice
    for frac in (np.arange(n) + 0.5) / n:  # the middle of each layer, away from the end faces
        holes = _holes(b.mesh, axis, frac)
        if len(holes) != 1:
            return False, f"{len(holes)} holes at {frac * length:.1f} mm along the hole (the hole doesn't run through)"
        h = holes[0]
        sections.append((2 * h.exterior.distance(polylabel(h, tolerance=0.001)), _diameter(h)))
    clear, across = min(sections)  # the tightest section
    ok = clear >= d_min - tol and across <= d_max + FLOAT_EPS
    return ok, (f"hole through {length:.1f} mm; at its tightest {clear:.2f} mm clear and {across:.2f} mm across "
                f"(want {d_min} to {d_max}); widest anywhere {max(w for _, w in sections):.2f} mm")


def hole_profile(mesh, step=0.2):
    """The through hole's tightest clear width and how much each end flares beyond it,
    or None if the part has no single through hole. For observations, not grading."""
    axis = _hole_axis(mesh)
    if axis is None:
        return None
    n = max(int(round(float(mesh.extents[axis]) / step)), 2)
    clear = []
    for frac in (np.arange(n) + 0.5) / n:
        holes = _holes(mesh, axis, frac)
        if len(holes) != 1:
            return None
        clear.append(2 * holes[0].exterior.distance(polylabel(holes[0], tolerance=0.001)))
    tight = min(clear)
    return {"clear_mm": round(tight, 2), "end_flare_mm": [round(clear[0] - tight, 2), round(clear[-1] - tight, 2)]}


GRADERS = {
    "dims.part_count": part_count,
    "dims.extents": extents,
    "dims.round_outline": round_outline,
    "dims.through_hole": through_hole,
}


def grade(task, sub, built) -> list[Finding]:
    out = []
    for r in task.requirements:
        fn = GRADERS.get(r["grader"])
        if fn is None:
            out.append(Finding(r["id"], "-", None, f"not graded ({r['grader']} isn't built): {r['text']}", r.get("class", "")))
            continue
        try:
            ok, detail = fn(sub, built, **(r.get("args") or {}))
        except Exception as e:  # model geometry can break a grader; that's a failed check, not a crash
            ok, detail = False, f"grader error: {type(e).__name__}: {e}"
        out.append(Finding(r["id"], "-", bool(ok), detail, r.get("class", "")))  # numpy bools aren't `True`
    return out
