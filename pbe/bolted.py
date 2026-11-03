"""Checks for any flat part with a bolt through it: does the hole pass the bolt (class C2), does
the head fit its recess (C1, C5), does the bolt reach what it screws into (C3)?

Nothing here knows about a tripod. Which bolt, and every limit, comes from the task's
requirements.yaml, whose brief says where each limit comes from. What the records can't decide comes
back as None, "not graded", which is never a pass. Nothing assumes one way of doing it: a slot or a
round hole, either face on the bed, any number of extra holes.
"""
from dataclasses import dataclass
from itertools import takewhile

from shapely.ops import unary_union

from pbe.sections import clear_width, holes, section

MIN_RECESS = 1.0  # mm; a lead-in chamfer is shallower than this, and isn't a place for a head
STEP = 0.2
TOL = 0.01  # mm; a curve's facets read a modeled width slightly narrow
MONOTONIC = 0.05  # mm between layers; less than this is a facet's noise, not a change of width
MIN_OPENING = 1.0  # mm; narrower than this, a gap in the outline is a facet's sliver, not a passage
PRINTED_SCREW = "the design prints its own screw, and no print has measured a printed thread"
WRONG_BOLT = "it uses {} instead of {}"


@dataclass
class Bore:
    """A hole all the way through the plate's thickness."""
    widths: list  # clear width per layer, from the plate's z-low face to its z-high face
    layer: float  # layer thickness

    @property
    def thickness(self):
        return len(self.widths) * self.layer

    @property
    def tightest(self):
        return min(self.widths)

    def _seat(self, widths):
        """The wide part at this end that could hold a head: (how deep, its width). A roof that
        tapers or steps down to the hole is wider than the hole but holds nothing."""
        run = list(takewhile(lambda w: w > self.tightest + STEP, widths))
        if not run:
            return 0.0, 0.0
        held = max(int(round(MIN_RECESS / self.layer)), 1)  # the width kept over a whole recess's depth
        width = sorted(run, reverse=True)[min(held, len(run)) - 1]
        seat = list(takewhile(lambda w: w >= width - STEP, run))
        return len(seat) * self.layer, min(seat)

    def recess(self):
        """The head's seat, the widest of the two ends': (how deep, its width, which end: 0 or -1).
        A shallow one is a lead-in chamfer, and counts only if there's nothing better."""
        seats = [self._seat(widths) + (end,) for end, widths in ((0, self.widths), (-1, self.widths[::-1]))]
        real = [seat for seat in seats if seat[0] >= MIN_RECESS]
        if real:
            return max(real, key=lambda seat: (seat[1], seat[0]))
        return max(seats, key=lambda seat: seat[0])


def _plate(sub, built):
    """The final part with the largest footprint, and its thickness axis (its shortest side). None
    if a final part failed to build: the one that's left may not be the plate."""
    finals = [built[p.id] for p in sub.parts if p.role == "final" and p.id in built]
    if not finals or not all(b.ok for b in finals):
        return None, None
    plate = max(finals, key=lambda b: sorted(b.mesh.extents)[-1] * sorted(b.mesh.extents)[-2])
    return plate, int(plate.mesh.extents.argmin())


def _layers(mesh, axis):
    """The plate's own layers, as fractions of its thickness. A pad, lip or mark standing on a face
    isn't the plate: a bolt hole doesn't have to run through it, and it isn't a dovetail."""
    n = max(int(round(mesh.extents[axis] / STEP)), 2)
    fracs = [(i + 0.5) / n for i in range(n)]
    areas = [unary_union(section(mesh, axis, f)).area for f in fracs]
    kept = [i for i, area in enumerate(areas) if area >= max(areas) / 2]
    return fracs[kept[0]:kept[-1] + 1]


def _follow(layer, layers):
    """Holes that run through every layer, followed from layer to layer by overlap."""
    bores = []
    for start in layers[0]:
        hole, widths = start, [clear_width(start)]
        for found in layers[1:]:
            next_hole = next((h for h in found if h.intersects(hole)), None)
            if next_hole is None:
                break
            hole, widths = next_hole, widths + [clear_width(next_hole)]
        if len(widths) == len(layers):
            bores.append(Bore(widths, layer))
    return bores


def _gaps(solid):
    """What a layer's convex hull has that the layer doesn't: its holes and the gaps in its outline."""
    gaps = solid.convex_hull.difference(solid)
    return [g for g in getattr(gaps, "geoms", [gaps]) if not g.is_empty and clear_width(g) >= MIN_OPENING]


def _bores(mesh, axis, bolt_across):
    """Holes that run the whole thickness, those the bolt fits if any do. If no closed hole fits it,
    the bolt may still pass where a recess is open at the side, as a channel the head slides in
    along is (GPT-6 Luna's plate)."""
    fracs = _layers(mesh, axis)
    layer = float(mesh.extents[axis]) * (fracs[1] - fracs[0])
    closed = _follow(layer, [holes(mesh, axis, f) for f in fracs])
    fits = lambda bore: bore.tightest >= bolt_across - TOL
    if any(fits(b) for b in closed):
        return [b for b in closed if fits(b)]
    opened = _follow(layer, [_gaps(unary_union(section(mesh, axis, f))) for f in fracs])
    return [b for b in opened if fits(b)] or closed or opened


def _main_bore(mesh, axis, bolt_across):
    """The bolt's bore. With several, the one with the widest recess, or the narrowest if none has one."""
    bores = _bores(mesh, axis, bolt_across)
    return max(bores, key=lambda b: (b.recess()[1], -b.tightest)) if bores else None


def _edges_by_layer(mesh, axis):
    """Each layer's outline, as (low edge, high edge), across each of the plate's two plan sides. The
    outline's bounds don't see a slot or recess inside it."""
    others = [a for a in range(3) if a != axis]
    bounds = [unary_union(section(mesh, axis, f)).bounds for f in _layers(mesh, axis)]
    return [[(box[side], box[side + 2]) for box in bounds] for side in (0, 1)], others


def _narrowing(edges):
    """How far both edges move in. One edge alone gives the lips nothing to pinch on the other side."""
    low, high = zip(*edges)
    return min(max(low) - min(low), max(high) - min(high))


def _clamped_widths(mesh, axis):
    """The width per layer across the side the clamp grips, and how much it narrows. That's the side
    that narrows most, or the shorter if neither does: a plate may be shorter than it is wide."""
    sides, others = _edges_by_layer(mesh, axis)
    shorter_first = sorted((0, 1), key=lambda side: mesh.extents[others[side]])
    side = max(shorter_first, key=lambda side: round(_narrowing(sides[side]), 2))
    return [high - low for low, high in sides[side]], _narrowing(sides[side])


def _wide_end(widths):
    """Which end of a simple dovetail is the wide one: 0 for the low end, -1 for the high end, or
    None if the part narrows and widens again, as a groove in its side does. Then the outline
    doesn't say which face goes in the clamp."""
    steps = [b - a for a, b in zip(widths, widths[1:])]
    narrows = any(step < -MONOTONIC for step in steps)
    widens = any(step > MONOTONIC for step in steps)
    if narrows == widens:
        return None
    return 0 if narrows else -1


def _other_fastener(sub, bolt):
    """(how the bolt-hole check should score it, why) if the design doesn't use the task's bolt."""
    refs = [h.ref for h in sub.hardware]
    if bolt in refs:
        return None
    wrong = [r for r in refs if r.startswith("ISO 4762")]
    return (False, WRONG_BOLT.format(wrong[0], bolt)) if wrong else (None, PRINTED_SCREW)


def exists(sub, built):
    plate, _ = _plate(sub, built)
    if plate:
        return True, f"plate is {plate.part}"
    if any(p.role == "final" and p.id in built for p in sub.parts):
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
    bore = _main_bore(plate.mesh, axis, too_tight)
    if bore is None:
        return False, "no hole runs through the plate"
    d = bore.tightest
    if d < too_tight - TOL:
        return False, f"{d:.2f} mm clear at its tightest: a {too_tight} mm bolt won't pass"
    if d >= head_passes - TOL:
        return False, f"{d:.2f} mm clear at its tightest: the head would pull through"
    depth, _, end = bore.recess()
    wide_end = _wide_end(_clamped_widths(plate.mesh, axis)[0])
    if depth >= MIN_RECESS and wide_end is not None and end != wide_end:
        return False, "the head's recess opens on the narrow face: the head is on the camera's side, or the dovetail is upside down"
    if d < printed - TOL or d > head_stopped:
        return None, f"{d:.2f} mm clear at its tightest: no print has measured that"
    return True, f"{d:.2f} mm clear at its tightest"


def head_recess(sub, built, bolt, bolt_across, too_tight, fits, head_height):
    plate, axis = _plate(sub, built)
    if plate is None or (bore := _main_bore(plate.mesh, axis, bolt_across)) is None:
        return None, "no bolt hole to read"
    if other := _other_fastener(sub, bolt):
        return None, other[1]  # a wrong bolt has already failed R3: one mistake counts once
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
    if plate is None or (bore := _main_bore(plate.mesh, axis, bolt_across)) is None:
        return None, "no bolt hole to read"
    if other := _other_fastener(sub, bolt):
        return None, other[1]
    depth, _, _ = bore.recess()
    depth = depth if depth >= MIN_RECESS else 0
    roof = bore.thickness - depth  # a lip standing elsewhere on the face doesn't lengthen the bolt's path
    past = bolt_length - roof
    return past >= min_reach, f"{past:.1f} mm into the camera with an assumed {bolt_length} mm bolt, through {roof:.1f} mm of plate (want {min_reach})"
