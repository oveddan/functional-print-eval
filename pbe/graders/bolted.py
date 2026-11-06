"""Checks for any flat part with a bolt through it: does the hole pass the bolt (class C2), does
the head fit its recess (C1, C5), does the bolt reach what it screws into (C3)?

Nothing here knows about a tripod. Which bolt, and every limit, comes from the task's
requirements.yaml, whose brief says where each limit comes from. What the records can't decide comes
back as None, "not graded", which is never a pass. Nothing assumes one way of doing it: a slot or a
round hole, either face on the bed, any number of extra holes.
"""
from dataclasses import dataclass
from itertools import takewhile
from typing import NamedTuple

from shapely.ops import unary_union

from pbe.graders.checks import Verdict
from pbe.graders.nuts import MAX_DRILL_OUT, sentence_saying_to_clear_it
from pbe.graders.sections import clear_width, holes, section

MIN_RECESS = 1.0  # mm; a lead-in chamfer is shallower than this, and isn't a place for a head
STEP = 0.2
TOL = 0.01  # mm; a curve's facets read a modeled width slightly narrow
MONOTONIC = 0.05  # mm between layers; less than this is a facet's noise, not a change of width
MIN_OPENING = 1.0  # mm; narrower than this, a gap in the outline is a facet's sliver, not a passage
PRINTED_SCREW = "the design prints its own screw, and no print has measured a printed thread"
WRONG_BOLT = "it uses {} instead of {}"


class Recess(NamedTuple):
    """The seat for the bolt's head at one end of its bore."""
    depth: float
    width: float
    end: int  # 0 for the plate's z-low face, -1 for its z-high face


@dataclass
class Bore:
    """A hole all the way through the plate's thickness."""
    widths: list  # clear width per layer, from the plate's z-low face to its z-high face
    layer: float  # layer thickness
    drill_out: float = 0.0  # mm of closed layers across the bore that the manual says to clear

    @property
    def thickness(self):
        return len(self.widths) * self.layer

    @property
    def tightest(self):
        return min(self.widths)

    def _seat(self, widths):
        """The wide part at this end that could hold a head: (how deep, its width). A roof that
        tapers or steps down to the hole is wider than the hole but holds nothing."""
        run = list(takewhile(lambda layer_width: layer_width > self.tightest + STEP, widths))
        if not run:
            return 0.0, 0.0
        held = max(int(round(MIN_RECESS / self.layer)), 1)  # the width kept over a whole recess's depth
        width = sorted(run, reverse=True)[min(held, len(run)) - 1]
        seat = list(takewhile(lambda layer_width: layer_width >= width - STEP, run))
        return len(seat) * self.layer, min(seat)

    def recess(self) -> Recess:
        """The head's seat, the widest of the two ends'. A shallow one is a lead-in chamfer, and
        counts only if there's nothing better."""
        seats = [Recess(*self._seat(self.widths), end=0), Recess(*self._seat(self.widths[::-1]), end=-1)]
        real = [seat for seat in seats if seat.depth >= MIN_RECESS]
        if real:
            return max(real, key=lambda seat: (seat.width, seat.depth))
        return max(seats, key=lambda seat: seat.depth)


def _footprint(part):
    """Its two longest sides multiplied: the area it covers lying flat."""
    _, middle, longest = sorted(part.mesh.extents)
    return longest * middle


def _plate(sub, built):
    """The final part with the largest footprint, and its thickness axis (its shortest side). None
    if a final part failed to build: the one that's left may not be the plate."""
    finals = [built[part.id] for part in sub.parts if part.role == "final" and part.id in built]
    if not finals or not all(final.ok for final in finals):
        return None, None
    plate = max(finals, key=_footprint)
    return plate, int(plate.mesh.extents.argmin())


def _layers(mesh, axis):
    """The plate's own layers, as fractions of its thickness. A pad, lip or mark standing on a face
    isn't the plate: a bolt hole doesn't have to run through it, and it isn't a dovetail."""
    count = max(int(round(mesh.extents[axis] / STEP)), 2)
    fracs = [(i + 0.5) / count for i in range(count)]
    areas = [unary_union(section(mesh, axis, frac)).area for frac in fracs]
    kept = [i for i, area in enumerate(areas) if area >= max(areas) / 2]
    return fracs[kept[0]:kept[-1] + 1]


def _follow(layer_h, layers, closed_ok=0):
    """Holes that run through every layer, followed from layer to layer by overlap. Up to closed_ok
    layers with nothing open over the hole are let through (a drill-out layer); they read as wide
    as the narrower of the bore's layers on either side, the hole drilled through."""
    bores = []
    for start in layers[0]:
        hole, widths, closed = start, [clear_width(start)], 0
        for found in layers[1:]:
            next_hole = next((candidate for candidate in found if candidate.intersects(hole)), None)
            if next_hole is None and closed < closed_ok:
                closed, widths = closed + 1, widths + [None]
                continue
            if next_hole is None:
                break
            hole, widths = next_hole, widths + [clear_width(next_hole)]
        if len(widths) == len(layers) and widths[-1] is not None:
            bores.append(Bore(_drilled(widths), layer_h, drill_out=closed * layer_h))
    return bores


def _drilled(widths):
    """A closed layer's width once drilled: the narrower of the open layers just below and above it."""
    below = [None] + widths[:-1]
    for i, width in enumerate(widths):
        if width is None:
            above = next(w for w in widths[i + 1:] if w is not None)
            widths[i] = min(below[i], above)
            below = [None] + widths[:-1]
    return widths


def _gaps(solid):
    """What a layer's convex hull has that the layer doesn't: its holes and the gaps in its outline."""
    gaps = solid.convex_hull.difference(solid)
    return [gap for gap in getattr(gaps, "geoms", [gaps]) if not gap.is_empty and clear_width(gap) >= MIN_OPENING]


def _bores(mesh, axis, bolt_across, drill_out=False):
    """Holes that run the whole thickness, those the bolt fits if any do. If no closed hole fits it,
    the bolt may still pass where a recess is open at the side, as a channel the head slides in
    along is (GPT-6 Luna's plate). With drill_out (the manual says to clear a layer), a hole closed
    by up to nuts.MAX_DRILL_OUT of layers counts, as the knob's bolt path does."""
    fracs = _layers(mesh, axis)
    layer_h = float(mesh.extents[axis]) * (fracs[1] - fracs[0])
    hole_layers = [holes(mesh, axis, frac) for frac in fracs]
    closed = _follow(layer_h, hole_layers)

    def bolt_fits(bore):
        return bore.tightest >= bolt_across - TOL
    if any(bolt_fits(bore) for bore in closed):
        return [bore for bore in closed if bolt_fits(bore)]
    drilled = _follow(layer_h, hole_layers, int((MAX_DRILL_OUT + TOL) / layer_h)) if drill_out else []
    if any(bolt_fits(bore) for bore in drilled):
        return [bore for bore in drilled if bolt_fits(bore)]
    opened = _follow(layer_h, [_gaps(unary_union(section(mesh, axis, frac))) for frac in fracs])
    return [bore for bore in opened if bolt_fits(bore)] or closed or opened


def _main_bore(mesh, axis, bolt_across, drill_out=False):
    """The bolt's bore. With several, the one with the widest recess, or the narrowest if none has one."""
    bores = _bores(mesh, axis, bolt_across, drill_out)

    def widest_recess_then_narrowest(bore):
        return bore.recess().width, -bore.tightest
    return max(bores, key=widest_recess_then_narrowest) if bores else None


def _edges_by_layer(mesh, axis):
    """Each layer's outline, as (low edge, high edge), across each of the plate's two plan sides. The
    outline's bounds don't see a slot or recess inside it."""
    boxes = [unary_union(section(mesh, axis, frac)).bounds for frac in _layers(mesh, axis)]  # (min x, min y, max x, max y)
    return [[(box[side], box[side + 2]) for box in boxes] for side in (0, 1)]


def _narrowing(edges):
    """How far both edges move in. One edge alone gives the lips nothing to pinch on the other side."""
    low, high = zip(*edges)
    return min(max(low) - min(low), max(high) - min(high))


def _clamped_widths(mesh, axis):
    """The width per layer across the side the clamp grips, and how much it narrows. That's the side
    that narrows most, or the shorter if neither does: a plate may be shorter than it is wide."""
    sides = _edges_by_layer(mesh, axis)
    plan_axes = [other for other in range(3) if other != axis]
    shorter_first = sorted((0, 1), key=lambda side: mesh.extents[plan_axes[side]])
    side = max(shorter_first, key=lambda side: round(_narrowing(sides[side]), 2))
    return [high - low for low, high in sides[side]], _narrowing(sides[side])


def _wide_end(widths):
    """Which end of a simple dovetail is the wide one: 0 for the low end, -1 for the high end, or
    None if the part narrows and widens again, as a groove in its side does. Then the outline
    doesn't say which face goes in the clamp."""
    steps = [above - below for below, above in zip(widths, widths[1:])]
    narrows = any(step < -MONOTONIC for step in steps)
    widens = any(step > MONOTONIC for step in steps)
    if narrows == widens:
        return None
    return 0 if narrows else -1


def _other_fastener(sub, bolt) -> Verdict | None:
    """How the bolt-hole check should score a design that doesn't use the task's bolt, or None if it does."""
    refs = [item.ref for item in sub.hardware]
    if bolt in refs:
        return None
    wrong = [ref for ref in refs if ref.startswith("ISO 4762")]
    if wrong:
        return Verdict(False, WRONG_BOLT.format(wrong[0], bolt))
    return Verdict(None, PRINTED_SCREW)


def exists(sub, built):
    plate, _ = _plate(sub, built)
    if plate:
        return True, f"plate is {plate.part_id}"
    if any(part.role == "final" and part.id in built for part in sub.parts):
        return None, "a final part didn't build, and that's already a failure"
    return False, "no final part built"


def fits_clamp(sub, built, width, narrows_by):
    """The plate's width is what fit the clamp, and both edges narrow so the angled lips have
    something to bear on. Narrowing is measured from the wide face toward the other."""
    plate, axis = _plate(sub, built)
    if plate is None:
        return None, "no plate built"
    widths, narrowing = _clamped_widths(plate.mesh, axis)
    widest = max(widths)
    if narrowing < narrows_by - STEP / 2:  # a taper read at layers' middles reads slightly short
        return False, f"straight sides: it narrows by only {narrowing:.2f} mm on both edges (want {narrows_by}), so the clamp's lips have nothing to bear on"
    if not width[0] <= widest <= width[1]:
        return None, f"{widest:.1f} mm wide; only {width[0]} to {width[1]} mm is backed by a print, and how far the clamp's jaws travel isn't recorded"
    return True, f"{widest:.1f} mm wide, narrowing by {narrowing:.1f} mm on both edges"


def bolt_hole(sub, built, bolt, too_tight, printed, head_stopped, head_passes):
    """The bolt passes, its head doesn't, and the head goes on the clamp side."""
    plate, axis = _plate(sub, built)
    if plate is None:
        return None, "no plate built"
    if other := _other_fastener(sub, bolt):
        return other
    told = sentence_saying_to_clear_it(sub)
    bore = _main_bore(plate.mesh, axis, too_tight, told is not None)
    if bore is None:
        return False, "no hole runs through the plate"
    drilled = f"; a {bore.drill_out:.1f} mm drill-out layer the manual says to clear (\"{told}\")" if bore.drill_out else ""
    clear = bore.tightest
    if clear < too_tight - TOL:
        return False, f"{clear:.2f} mm clear at its tightest: a {too_tight} mm bolt won't pass"
    if clear >= head_passes - TOL:
        return False, f"{clear:.2f} mm clear at its tightest: the head would pull through"
    recess = bore.recess()
    widths, _ = _clamped_widths(plate.mesh, axis)
    wide_end = _wide_end(widths)
    if recess.depth >= MIN_RECESS and wide_end is not None and recess.end != wide_end:
        return False, "the head's recess opens on the narrow face: the head is on the camera's side, or the dovetail is upside down"
    if clear < printed - TOL or clear > head_stopped:
        return None, f"{clear:.2f} mm clear at its tightest: no print has measured that{drilled}"
    return True, f"{clear:.2f} mm clear at its tightest{drilled}"


def _drill_out_told(sub):
    return sentence_saying_to_clear_it(sub) is not None


def head_recess(sub, built, bolt, bolt_across, too_tight, fits, head_height):
    plate, axis = _plate(sub, built)
    if plate is None or (bore := _main_bore(plate.mesh, axis, bolt_across, _drill_out_told(sub))) is None:
        return None, "no bolt hole to read"
    if other := _other_fastener(sub, bolt):
        return None, other.detail  # a wrong bolt has already failed R3: one mistake counts once
    depth, width, _ = bore.recess()
    if depth < MIN_RECESS:
        return None, "no recess: the head stands proud of the plate, and no print has tried that"
    if width <= too_tight:
        return False, f"recess {width:.2f} mm across: the {too_tight} mm one was too tight for this head"
    if width < fits - TOL:
        return None, f"recess {width:.2f} mm across: between {too_tight}, too tight, and {fits}, which fit"
    if depth < head_height - STEP / 2 - TOL:  # depth is read in whole layers
        return None, f"recess {depth:.1f} mm deep: only {head_height} mm has been printed"
    return True, f"recess {width:.2f} mm across and {depth:.1f} mm deep"


def reach(sub, built, bolt, bolt_across, bolt_length, min_reach):
    """How far the bolt gets past the plate's far face. The length is an assumption: see brief.md."""
    plate, axis = _plate(sub, built)
    if plate is None or (bore := _main_bore(plate.mesh, axis, bolt_across, _drill_out_told(sub))) is None:
        return None, "no bolt hole to read"
    if other := _other_fastener(sub, bolt):
        return None, other.detail
    depth = bore.recess().depth
    depth = depth if depth >= MIN_RECESS else 0
    roof = bore.thickness - depth  # a lip standing elsewhere on the face doesn't lengthen the bolt's path
    past = bolt_length - roof
    return past >= min_reach, f"{past:.1f} mm into the camera with an assumed {bolt_length} mm bolt, through {roof:.1f} mm of plate (want {min_reach})"
