"""Graders for tasks built by combining records (issue 41), made only from existing readers.

A task synthesized from two recorded fits reuses the checks written for each: wheel.* for the
608's seat, nut.* for a hex nut's pocket. This module adds no geometry of its own. It decides
which record applies (the model picks the nut, and whether to use a bearing) and turns a case
no test print covers into "not graded".
"""
import math
import re

from shapely.geometry import Polygon

from pbe.graders import nuts, wheel
from pbe.graders.checks import Verdict
from pbe.graders.sections import clear_width, holes_in, sections_by_layer, single_final
from pbe.parts import catalog

# The nuts coupon B printed (results/predictions/round1-coupons.yaml), with each bolt's diameter
# and ISO 273's fine clearance hole for it (the same values as tasks/nut-knob/variants.yaml).
RECORDED_NUTS = {"M3": (3.0, 3.2), "M5": (5.0, 5.3), "M8": (8.0, 8.4)}
HEX_NUT = re.compile(r"^ISO 4032 (M\d+)$")
BEARING = "608"
BEARING_WIDTH = 7  # mm, the 608 (catalog/hardware.yaml)
PAUSE = re.compile(r"\bpaus(e|es|ed|ing)\b", re.I)


def bolt_through_nut(sub, built, nut, bolt, fine) -> Verdict:
    """The bolt goes through the nut's pocket and the whole part, read by nuts.bolt_passes. Narrower
    than the bolt fails, and at least ISO 273's fine clearance hole passes. In between, no print has
    said whether a printed hole passes the bolt, so it's not graded, as wheel.bolt_passes does for the
    M8. (nut.bolt_passes on its own fails everything under `fine`, which the knob task asks for.)"""
    at_fine = Verdict(*nuts.bolt_passes(sub, built, nut, fine))
    if at_fine.ok is not False:  # passes, or there's no pocket to line the bolt up with
        return at_fine
    at_bolt = Verdict(*nuts.bolt_passes(sub, built, nut, bolt))
    if at_bolt.ok is False:
        return at_bolt
    return Verdict(None, f"{at_fine.detail}: wide enough for a {bolt} mm bolt, but no print has measured a hole this size")


# --- the handle's nut: whichever recorded nut the design uses ---------------------------------

def _hex_nuts_listed(sub):
    """The ISO 4032 hex nut sizes in the design's hardware list."""
    return [found.group(1) for item in sub.hardware if (found := HEX_NUT.match(item.ref.strip()))]


def _other_threads_listed(sub):
    """Hardware a handle could thread into that no test print covers: other nuts and inserts."""
    return [item.ref for item in sub.hardware if item.ref.startswith(("ISO 10511", "ASME")) or "insert" in item.ref.lower()]


def _af(size):
    return catalog.resolve(f"ISO 4032 {size}")["af"]


def _sizes_with_a_pocket(sub, built, sizes):
    """Of these nut sizes, the ones the final part has a hex pocket for."""
    part, _ = single_final(sub, built)
    if part is None:
        return []
    return [size for size in sizes if nuts._nuts_pocket(part.mesh, _af(size)) is not None]


def handle_nut(sub, built) -> tuple[str | None, str]:
    """The recorded nut the handle threads into: (size, "") or (None, why it can't be graded). With
    one recorded size listed, that's it. With several (an M5 for the handle and M8s for the axle,
    say), it's the one the wheel has a pocket for."""
    recorded = list(dict.fromkeys(size for size in _hex_nuts_listed(sub) if size in RECORDED_NUTS))
    unrecorded = _other_threads_listed(sub) + [f"ISO 4032 {size}" for size in _hex_nuts_listed(sub) if size not in RECORDED_NUTS]
    if len(recorded) == 1:
        # an M8 for the axle beside an M4 or a lock nut for the handle: the M8 isn't the handle's
        if unrecorded and not _sizes_with_a_pocket(sub, built, recorded):
            return None, f"{', '.join(unrecorded)}: no test print covers it, and the wheel has no pocket for the {recorded[0]}"
        return recorded[0], ""
    if len(recorded) > 1:
        with_pockets = _sizes_with_a_pocket(sub, built, recorded)
        if len(with_pockets) == 1:
            return with_pockets[0], ""
        if with_pockets:
            return None, f"pockets for {' and '.join(with_pockets)}, so which is the handle's can't be told"
        return None, (f"no hex pocket along z for {' or '.join(recorded)}: a nut loaded from the side, or held by "
                      "snap fingers, reads this way, and no test print covers either")
    if unrecorded:
        return None, f"{', '.join(unrecorded)}: no test print covers it"
    return None, "no nut in the hardware list, so the handle threads into something no test print covers"


def _with_handle_nut(check):
    def graded(sub, built, **args) -> Verdict:
        size, why = handle_nut(sub, built)
        if size is None:
            return Verdict(None, why)
        ok, detail = check(sub, built, size, **args)
        return Verdict(ok, f"{size}: {detail}")
    graded.__doc__ = check.__doc__
    return graded


def _sealed_pocket(sub, built, size):
    """The nut's pocket, if it's closed on both faces and the manual says to pause the print and
    drop the nut in, so the print seals it; else None."""
    part, _ = single_final(sub, built)
    found = nuts._nuts_pocket(part.mesh, _af(size)) if part is not None else None
    told = any(PAUSE.search(f"{step.text} {step.tool or ''}") for step in sub.manual)
    return found if found is not None and not found.opens and told else None


SEALED = "sealed in by a print pause the manual describes: no test print covers printing over a nut"


@_with_handle_nut
def handle_pocket(sub, built, size):
    """nut.pocket, for the nut the design uses. A nut sealed in by a print pause is not graded."""
    if _sealed_pocket(sub, built, size):
        return None, SEALED
    return nuts.pocket(sub, built, f"ISO 4032 {size}")


@_with_handle_nut
def handle_nut_fit(sub, built, size):
    """nut.fit against that nut's row of coupon B. Coupon B's press fits say nothing about a sealed nut."""
    if _sealed_pocket(sub, built, size):
        return None, SEALED
    return nuts.fit(sub, built, f"ISO 4032 {size}", size)


def _clear_from_one_face(sub, part, pocket, bolt, fine):
    """For a sealed nut: the bolt reaches it from one face. The narrowest clear circle round the
    pocket's centre, on the clearer side, read as nuts.bolt_passes reads each layer, with the same
    allowance for a closed drill-out layer up to nuts.MAX_DRILL_OUT that the manual says to clear."""
    layer_h, sections = sections_by_layer(part.mesh, 2, nuts.LAYER)
    bottom = part.mesh.bounds[0, 2]
    clears = [(bottom + (i + 0.5) * layer_h, nuts._clear_around(holes_in(polys), nuts._outline(polys), pocket.centre))
              for i, polys in enumerate(sections)]
    told = nuts._sentence_saying_to_clear_it(sub)

    def narrowest(side):
        closed = [clear for clear in side if clear == 0.0]
        drilled = bool(told and closed and len(closed) * layer_h <= nuts.MAX_DRILL_OUT + nuts.TOL)
        open_layers = [clear for clear in side if clear != 0.0] if drilled else side
        return min(open_layers, default=math.inf), drilled
    below = narrowest([clear for z, clear in clears if z < pocket.z[0]])
    above = narrowest([clear for z, clear in clears if z > pocket.z[1]])
    side, (clear, drilled) = max((("below", below), ("above", above)), key=lambda pair: pair[1][0])
    reading = f"sealed nut, reached from {side}" + (f" through a drill-out layer the manual says to clear (\"{told}\")" if drilled else "")
    reading += f": {clear:.2f} clear at its narrowest"
    if clear < bolt - nuts.TOL:
        return False, f"{reading}; a {bolt} mm bolt can't reach it from either face"
    if clear < fine - nuts.TOL:
        return None, f"{reading}: wide enough for a {bolt} mm bolt, but no print has measured a hole this size"
    return True, f"{reading} (want at least {fine})"


@_with_handle_nut
def handle_bolt(sub, built, size):
    """The handle's bolt gets through its nut and the part: bolt_through_nut at that bolt's sizes. A
    sealed nut only has to be reached from one face."""
    bolt, fine = RECORDED_NUTS[size]
    if pocket := _sealed_pocket(sub, built, size):
        return _clear_from_one_face(sub, single_final(sub, built)[0], pocket, bolt, fine)
    return bolt_through_nut(sub, built, f"ISO 4032 {size}", bolt, fine)


# --- the bearing: graded only if the design uses the 608 ----------------------------------------

def _uses_the_bearing(sub, built, seat_range):
    """The 608 is in the hardware list, or the part has a hole its size: a model told the person
    has the bearing may leave it off the list, as two did on the first look."""
    return any(BEARING in item.ref for item in sub.hardware) or _a_seat_sized_hole(sub, built, seat_range)


def _seats_found(sub, built, seat_range, bearing_width, bearings):
    return [seat for mesh in wheel._finals(sub, built) or [] for seat in wheel._seats(mesh, seat_range, bearing_width, bearings)[0]]


def _seat_sized(region, seat_range):
    pieces = getattr(region, "geoms", [region])
    return any(piece.geom_type == "Polygon" and not piece.is_empty and seat_range[0] <= clear_width(piece) <= seat_range[1]
               for piece in pieces)


def _a_seat_sized_hole(sub, built, seat_range):
    """Is there a hole the bearing's size in any layer of a final part, whether or not it runs through?
    A seat slotted open to the rim isn't a closed hole, so the notches in each layer's outline (what
    its convex hull adds) count too."""
    for mesh in wheel._finals(sub, built) or []:
        _, layers = sections_by_layer(mesh, int(mesh.extents.argmin()), wheel.STEP)
        for polys in layers:
            if any(_seat_sized(hole, seat_range) for hole in holes_in(polys)):
                return True
            for poly in polys:
                outline = Polygon(poly.exterior)
                if _seat_sized(outline.convex_hull.difference(outline), seat_range):
                    return True
    return False


NO_BEARING = Verdict(None, "no 608 in the hardware list and no hole its size: no test print says how a printed bore spins on a bolt")


def bearing_room(sub, built, seat_range, bearing_width, bearings) -> Verdict:
    """wheel.room, except that a seat shallower than its bearing is not graded instead of failed.
    wheel.room fails a seat under bearing_width - 0.6 mm because the bearing wheel needed two
    bearings inside its width. Here the bearing may stand proud on purpose, and no test print tried
    a seat shallower than its bearing. A seat-sized hole the wheel reader can't follow (slots, snap
    fingers, a boss taller than the wheel) is not graded either. A part with no seat-sized hole fails."""
    if not _uses_the_bearing(sub, built, seat_range):
        return NO_BEARING
    verdict = Verdict(*wheel.room(sub, built, seat_range, bearing_width, bearings))
    if verdict.ok is not False:
        return verdict
    seats = _seats_found(sub, built, seat_range, bearing_width, bearings)
    if not seats:
        if _a_seat_sized_hole(sub, built, seat_range):
            return Verdict(None, "a seat-sized hole the wheel reader can't follow through the part: slots, snap fingers or "
                                 "a boss taller than the wheel read this way, and only plain seats were printed")
        return verdict
    deepest = max(seat.depth for seat in seats)
    return Verdict(None, f"seat {deepest:.1f} mm deep, so the bearing stands {bearing_width - deepest:.1f} mm proud; "
                         "no test print tried a seat shallower than its bearing")


def bearing_fit(sub, built, **args) -> Verdict:
    """wheel.fit, if the design uses the 608."""
    return Verdict(*wheel.fit(sub, built, **args)) if _uses_the_bearing(sub, built, args["seat_range"]) else NO_BEARING


def bearing_bolt(sub, built, seat_range, bolt, fine) -> Verdict:
    """wheel.bolt_passes, if the design uses the 608: its 8 mm bore takes the M8 bolt. With no seat
    found, wheel.bolt_passes reads whatever hole runs through instead, such as the handle's, so it's
    not graded: R3 has already counted the missing seat."""
    if not _uses_the_bearing(sub, built, seat_range):
        return NO_BEARING
    if not _seats_found(sub, built, seat_range, BEARING_WIDTH, 1):
        return Verdict(None, "no seat found, so there's no bearing bore to read")
    return Verdict(*wheel.bolt_passes(sub, built, seat_range, bolt, fine))
