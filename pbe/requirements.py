"""Task requirement graders, named in each task's requirements.yaml.

A requirement whose grader isn't built yet is reported as not graded, never as a pass,
and a grader that crashes on a submission records a failure instead of stopping the run.
A check that needs a part or feature another check already failed reports not graded too,
so one mistake counts once in the failures by class.
"""
import numpy as np
from shapely.geometry import Polygon

from pbe import bolted, nuts, wheel
from pbe.checks import Finding
from pbe.sections import clear_width, diameter, hole_axis, holes_by_layer, section, single_final

FLOAT_EPS = 1e-4  # mm; STL coordinates are single-precision


def part_count(sub, built, n):
    finals = [p.id for p in sub.parts if p.role == "final"]
    return len(finals) == n, f"{len(finals)} printed part(s): {', '.join(finals)}"


def extents(sub, built, mm, tol):
    """The part's bounding box, largest side first, matches `mm` within `tol`."""
    b, why = single_final(sub, built)
    if b is None:
        return None, why
    got = sorted(b.mesh.extents, reverse=True)
    want = sorted(mm, reverse=True)
    ok = all(abs(g - w) <= tol for g, w in zip(got, want, strict=True))
    return ok, f"{' x '.join(f'{g:.2f}' for g in got)} mm (want {' x '.join(map(str, want))} ± {tol})"


def round_outline(sub, built, min_roundness):
    """The outline across the hole's axis (or the longest axis) is round: its area over
    the area of a circle as wide as the outline is at least `min_roundness`. A circle
    scores 1, a hexagon 0.83, a square 0.64."""
    b, why = single_final(sub, built)
    if b is None:
        return None, why
    axis = hole_axis(b.mesh)
    if axis is None:
        axis = int(np.argmax(b.mesh.extents))
    polys = section(b.mesh, axis, 0.5)
    if len(polys) != 1:
        return False, f"{len(polys)} separate pieces in the middle cross-section"
    outline = Polygon(polys[0].exterior)
    d = diameter(outline)
    score = outline.area / (np.pi * d * d / 4)
    return score >= min_roundness, f"roundness {score:.3f} (want at least {min_roundness}), {d:.2f} mm across"


def through_hole(sub, built, d_min, d_max, step=0.2, tol=0.01):
    """One hole runs the part's full length and fits the bolt. Every cross-section along
    the hole's axis, one per `step` mm (a layer), has exactly one hole, and the bolt must
    pass every one: its clear width (largest inscribed circle) is at least d_min. The upper
    limit says the bolt is located: at least a quarter of the hole's length is at most d_max
    across at its widest. Lead-in chamfers and counterbores at the ends are wider and pass;
    an oversized or slotted bore fails, even with one thin neck in it.
    `tol` only lowers d_min: the mesh's facets make a modeled hole read up to about
    0.002 mm narrow, which would fail a hole drawn at exactly d_min. d_max gets only
    FLOAT_EPS: the STL's single-precision floats read 5.8 as 5.80000022."""
    b, why = single_final(sub, built)
    if b is None:
        return None, why
    axis = hole_axis(b.mesh)
    if axis is None:
        return False, "no single hole through the middle of the part"
    layer_h, layers = holes_by_layer(b.mesh, axis, step)
    length = layer_h * len(layers)
    sections = []  # (clear width, widest point) per layer
    for i, found in enumerate(layers):
        if len(found) != 1:
            return False, f"{len(found)} holes at {(i + 0.5) * layer_h:.1f} mm along the hole (the hole doesn't run through)"
        sections.append((clear_width(found[0]), diameter(found[0])))
    clear = min(c for c, _ in sections)
    across = float(np.percentile([w for _, w in sections], 25))  # three quarters of the hole is at least this wide
    ok = clear >= d_min - tol and across <= d_max + FLOAT_EPS
    return ok, (f"hole through {length:.1f} mm; {clear:.2f} mm clear at its tightest and {across:.2f} mm across over a quarter of it "
                f"(want {d_min} to {d_max}); widest anywhere {max(w for _, w in sections):.2f} mm")


def hole_profile(mesh, step=0.2):
    """The through hole's tightest clear width and how much each end flares beyond it,
    or None if the part has no single through hole. For observations, not grading."""
    axis = hole_axis(mesh)
    if axis is None:
        return None
    _, layers = holes_by_layer(mesh, axis, step)
    if any(len(found) != 1 for found in layers):
        return None
    clear = [clear_width(found[0]) for found in layers]
    tight = min(clear)
    return {"clear_mm": round(tight, 2), "end_flare_mm": [round(clear[0] - tight, 2), round(clear[-1] - tight, 2)]}


def across(sub, built, d, tol_frac):
    """Width on the bed: the part's larger side in x and y, within a fraction of `d`."""
    b, why = single_final(sub, built)
    if b is None:
        return None, why
    got = float(max(b.mesh.extents[:2]))
    return abs(got - d) <= tol_frac * d, f"{got:.1f} mm across (want {d} within {tol_frac:.0%})"


GRADERS = {
    "dims.across": across,
    "nut.pocket": nuts.pocket,
    "nut.fit": nuts.fit,
    "nut.bolt_passes": nuts.bolt_passes,
    "bolted.plate_exists": bolted.exists,
    "bolted.fits_clamp": bolted.fits_clamp,
    "bolted.hole": bolted.bolt_hole,
    "bolted.head_recess": bolted.head_recess,
    "bolted.reach": bolted.reach,
    "wheel.size": wheel.size,
    "wheel.room": wheel.room,
    "wheel.fit": wheel.fit,
    "wheel.bolt_passes": wheel.bolt_passes,
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
        # numpy bools aren't `True`; None means the check can't say, which is never a pass
        out.append(Finding(r["id"], "-", None if ok is None else bool(ok), detail, r.get("class", "")))
    return out
