"""Checks for a wheel with bearings pressed in: how big is it (class C5), is there room for the
bearings (C5), will they press in and stay on this printer (C2), does the
bolt pass (C3)?

Nothing here assumes how it's done: a seat on each side, two bearings stacked from one side, or two
halves bolted together. Which limits, and where they come from, are in the task's brief: round 2's and
round 3's seats (E, H) and round 3's bolt holes (F). A seat no print has measured comes back None,
"not graded", which is never a pass.
"""
import math
import tempfile
from dataclasses import dataclass
from itertools import groupby

from pbe.graders import assumed, bolt_fits
from pbe.graders.checks import Verdict
from pbe.graders.nuts import coupons_in_the_manual
from pbe.graders.sections import clear_width, diameter, hole_axis, holes_by_layer
from pbe.parts.build import build_parts

STEP = 0.2
TOL = 0.02  # mm; a curve's facets read a modeled width slightly narrow
PLAIN = 1.06  # a hole this much bigger than its clear circle has ribs, lobes or a slot in it
# mm a hole may be wider at its widest than its clear circle and still be plain. A plain printed seat reads within
# 0.01 mm; crush ribs 0.2 mm high (Sonnet 5.5's, game spinner first look) read 0.4 mm but add only 3.4% to the area
RIBS_MM = 0.1
# mm a bearing may stand out of its seat and still count as seated: round 3's H5 to H7 held a 608 standing 0.2,
# 0.4 and 0.6 mm proud of a 22.2 seat (Claude's scoring call to read it for any seat that holds, 2026-11-12)
PROUD = 0.6


@dataclass
class Seat:
    across: float  # the width held over the bearings' whole depth
    depth: float
    bearings: int  # how many fit
    plain: bool  # a plain round seat, the only kind the coupon measured
    stopped: bool  # the bore narrows past it, so a bearing can't go straight through
    proud: bool  # the bearings stand a little out of it


def _bore_stacks(mesh, axis):
    """Each hole that runs the whole width, as its hole in each layer: (stacks, layer thickness).
    Every layer counts: a hub boss is part of the seat that runs into it, and of the bolt's path."""
    layer, layers = holes_by_layer(mesh, axis, STEP)
    stacks = []
    for start in layers[0]:
        stack = [start]
        for found in layers[1:]:
            following = next((hole for hole in found if hole.intersects(stack[-1])), None)
            if following is None:
                break
            stack.append(following)
        if len(stack) == len(layers):
            stacks.append(stack)
    return stacks, layer


def _sized(width, seat_range):
    return seat_range[0] <= width <= seat_range[1]


def _axle(mesh, axis, seat_range):
    """The bore the bearings go in: the one with the most seat-sized layers, then the narrowest."""
    stacks, layer = _bore_stacks(mesh, axis)
    if not stacks:
        return None, layer
    def most_seat_layers_then_narrowest(stack):
        widths = [clear_width(hole) for hole in stack]
        return sum(_sized(width, seat_range) for width in widths), -min(widths)
    return max(stacks, key=most_seat_layers_then_narrowest), layer


def _is_round(hole):
    """A plain round hole: no more area than its clear circle's, and no wider anywhere. Ribs, lobes or
    a slot show in one or the other: big ones in the area, small ribs only in the widest span."""
    clear = clear_width(hole)
    return hole.area <= PLAIN * math.pi * clear ** 2 / 4 and diameter(hole) - clear <= RIBS_MM


def _read_seat(run, layer, tightest, bearing_width, bearings):
    depth = len(run) * layer
    fits = min(int((depth + PROUD + STEP / 2 + TOL) / bearing_width), bearings)  # depth is read in whole layers
    held = max(int(round((fits or 1) * bearing_width / layer)), 1)  # layers deep the bearings sit
    widest_held = sorted(run, key=clear_width, reverse=True)[:held]
    across = clear_width(widest_held[-1])
    plain = all(_is_round(hole) for hole in widest_held)
    stopped = tightest < across - 1
    proud = 0 < fits and depth < fits * bearing_width - STEP / 2
    return Seat(across, depth, fits, plain, stopped, proud)


def _seats(mesh, seat_range, bearing_width, bearings):
    """The seat-sized stretches of a part's bore, and the bore's tightest width (None if no bore)."""
    axis = int(mesh.extents.argmin())
    stack, layer = _axle(mesh, axis, seat_range)
    if stack is None:
        return [], None
    tightest = min(clear_width(hole) for hole in stack)
    seats = []
    for sized, run in groupby(stack, key=lambda hole: _sized(clear_width(hole), seat_range)):
        if sized:
            seats.append(_read_seat(list(run), layer, tightest, bearing_width, bearings))
    return seats, tightest


def _tightest_bore(mesh, seat_range):
    """The narrowest width of the bore the bearings go in, or None if no hole runs through."""
    stack, _ = _axle(mesh, int(mesh.extents.argmin()), seat_range)
    return None if stack is None else min(clear_width(hole) for hole in stack)


def _finals(sub, built):
    """The final parts' meshes, or None if one failed to build: `builds` has already said so."""
    finals = [built[part.id] for part in sub.parts if part.role == "final" and part.id in built]
    return [final.mesh for final in finals] if all(final.ok for final in finals) else None


def _middle_side(mesh):
    """The second longest side: for a wheel, or half of one, its diameter."""
    return sorted(mesh.extents)[-2]


def size(sub, built, across, max_width):
    finals = _finals(sub, built)
    if finals is None:
        return None, "a final part didn't build, and that's already a failure"
    if not finals:
        return False, "no final part"
    biggest = max(max(mesh.extents) for mesh in finals)
    # halves or layers of the wheel count towards its width, a separate spacer or knob doesn't
    wheel_pieces = [mesh for mesh in finals if _middle_side(mesh) >= across[0]]
    width = sum(min(mesh.extents) for mesh in wheel_pieces)
    if not across[0] <= biggest <= across[1]:
        return False, f"{biggest:.1f} mm across; about {across[0]} to {across[1]} mm was asked for"
    if width > max_width:
        return False, f"{width:.1f} mm wide; the old wheel's about {max_width} mm at most"
    return True, f"{biggest:.1f} mm across, {width:.1f} mm wide"


def room(sub, built, seat_range, bearing_width, bearings):
    finals = _finals(sub, built)
    if not finals:
        return None, "no wheel to read"
    seats = []
    for mesh in finals:
        seats_here, _ = _seats(mesh, seat_range, bearing_width, bearings)
        seats += seats_here
    held = sum(seat.bearings for seat in seats)
    if held < bearings:
        deep = ", ".join(f"{seat.depth:.1f}" for seat in seats) or "none"
        return False, f"room for {held} of {bearings} bearings {bearing_width} mm wide; seat-sized depth: {deep} mm"
    return True, f"room for {held} bearings, in {len(seats)} seat(s){_how_placed(seats)}"


def _how_placed(seats):
    """What round 3 says about bearings with no shoulder behind them, or standing a little out of their seat,
    in words. Claude's scoring call (2026-11-12): a seat with no shoulder counts, because H8 (22.2, no shoulder)
    held its bearing upside down. Whether a push moves it through wasn't reported; whether the seat's width
    holds is R3's question, so one mistake counts once."""
    notes = []
    if not all(seat.stopped for seat in seats if seat.bearings):
        notes.append("no shoulder stops the bearings, as on round 3's H8, which held its bearing upside down")
    if any(seat.proud for seat in seats):
        notes.append(f"the bearings stand a little proud, no more than round 3's H7 ({PROUD} mm), which held")
    return "".join(f"; {note}" for note in notes)


def _holds(across, too_tight, holds, too_loose) -> Verdict:
    if across <= too_tight + TOL:
        return Verdict(False, f"{across:.2f} mm: a {too_tight} mm seat wouldn't take the bearing")
    if across >= too_loose - TOL:
        return Verdict(False, f"{across:.2f} mm: from {too_loose} mm the bearing was too loose and fell out")
    if holds[0] - TOL <= across <= holds[1] + TOL:
        return Verdict(True, f"{across:.2f} mm: it presses in and holds upside down")
    close = assumed.nearest(across, [(too_tight, False), (holds[0], True), (holds[1], True), (too_loose, False)])
    if close:
        if close[1]:
            result = "it presses in and holds upside down"
        elif close[0] == too_loose:
            result = "the bearing would be too loose and fall out"
        else:
            result = "the seat wouldn't take the bearing"
        return Verdict(close[1], f"{across:.2f} mm: {result} ({assumed.note(close[0])})")
    if across < holds[0]:
        return Verdict(None, f"{across:.2f} mm: between {too_tight}, too tight, and {holds[0]}, which held")
    return Verdict(None, f"{across:.2f} mm: between {holds[1]}, which held, and {too_loose}, which fell out")


def _param_that_moves_seat(sub, part_id, across, seat_range, bearing_width, bearings):
    """The param that changes the final part's seat, or None. Without one, a coupon's answer can't
    be applied without rewriting the code."""
    only_final = sub.model_copy(update={"parts": [part for part in sub.parts if part.id == part_id]})
    with tempfile.TemporaryDirectory() as tmp:
        for name, param in sub.params.items():
            if param.value is None:
                continue
            rebuilt = build_parts(only_final, tmp, overrides={name: param.value + 0.2})[part_id]
            if not rebuilt.ok:
                continue
            seats, _ = _seats(rebuilt.mesh, seat_range, bearing_width, bearings)
            if seats and abs(seats[0].across - across) >= 0.1:
                return name
    return None


def _coupon_seat_that_holds(sub, built, seat_range, too_tight, holds, too_loose, bearing_width):
    """A test coupon in the manual with a seat that holds: its id, or None."""
    for part_id, coupon in coupons_in_the_manual(sub, built):
        seats = _coupon_seats(coupon.mesh, seat_range, bearing_width)
        if any(seat.plain and _holds(seat.across, too_tight, holds, too_loose).ok is True for seat in seats):
            return part_id
    return None


def _coupon_seats(mesh, seat_range, bearing_width):
    """A coupon may be a row of seats, through or blind, and half a bearing's depth is enough to
    feel the fit."""
    layer, layers = holes_by_layer(mesh, int(mesh.extents.argmin()), STEP)
    runs, finished = [], []
    for found in layers:
        sized = [hole for hole in found if _sized(clear_width(hole), seat_range)]
        runs, ended = _carry_runs(runs, sized)
        finished += ended
    finished += runs
    return [_read_seat(run, layer, 0, bearing_width, 1) for run in finished if len(run) * layer >= bearing_width / 2]


def _carry_runs(runs, holes_here):
    """Extend each run of seat-sized holes with the hole in this layer it overlaps, or start a new
    run from it: (the runs that go on, the runs that ended in the layer below)."""
    runs = list(runs)
    carried = []
    for hole in holes_here:
        run = next((candidate for candidate in runs if candidate[-1].intersects(hole)), None)
        if run is not None:
            runs.remove(run)
        carried.append((run or []) + [hole])
    return carried, runs


def _seats_with_bearings(sub, built, seat_range, bearing_width, bearings):
    """(part id, seat) for every seat in a final part that built with room for a bearing."""
    found = []
    for part in sub.parts:
        if part.role != "final" or part.id not in built or not built[part.id].ok:
            continue
        seats, _ = _seats(built[part.id].mesh, seat_range, bearing_width, bearings)
        found += [(part.id, seat) for seat in seats if seat.bearings]
    return found


def _worst(verdicts):
    """The first failure, else the first not graded, else the first verdict."""
    for wanted in (False, None):
        for verdict in verdicts:
            if verdict.ok is wanted:
                return verdict
    return verdicts[0]


def _why_no_coupon_helps(sub, built, coupon):
    """Why the design's test coupons don't rescue a seat, in words."""
    if coupon:
        return f"test print {coupon} has a size that holds, but no param moves the seat"
    in_the_manual = coupons_in_the_manual(sub, built)
    if in_the_manual:
        return f"test print {in_the_manual[0][0]} has no size known to hold"
    return "no test print in the manual"


def fit(sub, built, seat_range, too_tight, holds, too_loose, bearing_width, bearings):
    """The bearing presses in and stays upside down, or a test coupon would have found a size that
    does and the design has a param to apply it with."""
    found = _seats_with_bearings(sub, built, seat_range, bearing_width, bearings)
    if not found:
        return None, "no seat to read"
    if not all(seat.plain for _, seat in found):
        return None, "ribs, lobes or a slot in the seat: only plain round seats were printed"
    worst = _worst([_holds(seat.across, too_tight, holds, too_loose) for _, seat in found])
    if worst.ok is True:
        return worst
    coupon = _coupon_seat_that_holds(sub, built, seat_range, too_tight, holds, too_loose, bearing_width)
    part_id, seat = found[0]
    if coupon and (param := _param_that_moves_seat(sub, part_id, seat.across, seat_range, bearing_width, bearings)):
        return True, f"{worst.detail}; test coupon {coupon} would find a size that holds, and {param} moves the seat"
    return worst.ok, f"{worst.detail}; {_why_no_coupon_helps(sub, built, coupon)}"


def _bolt_through(clear, bolt, thread, fine, spins) -> Verdict:
    """How the bolt goes through a printed bore this wide, from round 3's F (bolt_fits). A bore the bolt only
    screws through fails on the wheel itself: Claude's scoring call (2026-11-12), because the wheel would grip
    the bolt and couldn't spin on it. A spacer or sleeve on the bolt doesn't spin, so there it's enough."""
    if clear < bolt - TOL:
        return Verdict(False, f"{clear:.2f} mm clear at its tightest: a {bolt} mm bolt won't pass")
    if clear >= fine - TOL:
        return Verdict(True, f"{clear:.2f} mm clear at its tightest")
    how, assumed_from = bolt_fits.reading(thread, clear)
    assumed_words = f" ({assumed.note(assumed_from)})" if assumed_from is not None else ""
    if how == "screws in" and spins:
        return Verdict(False, f"{clear:.2f} mm clear at its tightest: round 3's {thread} only screwed through a hole that size"
                              f"{assumed_words}, so the wheel would grip the bolt and not spin")
    if how is None:
        return Verdict(None, f"{clear:.2f} mm clear at its tightest: no print has measured that")
    return Verdict(True, f"{clear:.2f} mm clear at its tightest: round 3's {thread} went through a hole that size ({how}){assumed_words}")


def bolt_passes(sub, built, seat_range, bolt, thread, fine):
    """The bolt goes through every part of the wheel, and the wheel turns on it. Between the bolt's size
    and ISO 273's fine clearance hole, round 3's F says how a printed hole takes it."""
    finals = _finals(sub, built)
    if not finals:
        return None, "no wheel to read"
    wheels = [mesh for mesh in finals if _middle_side(mesh) >= seat_range[1]]
    wheel_bores = [_tightest_bore(mesh, seat_range) for mesh in wheels]
    if not wheel_bores or None in wheel_bores:
        return False, "no hole runs through the wheel"
    verdicts = [_bolt_through(clear, bolt, thread, fine, spins=True) for clear in wheel_bores]
    # a printed spacer or sleeve on the bolt has to pass it too
    others = [mesh for mesh in finals if not any(mesh is wheel_mesh for wheel_mesh in wheels)]
    for mesh in others:
        axis = hole_axis(mesh)
        if axis is None:
            continue
        stacks, _ = _bore_stacks(mesh, axis)
        verdicts += [_bolt_through(min(clear_width(hole) for hole in stack), bolt, thread, fine, spins=False) for stack in stacks]
    return _worst(verdicts)
