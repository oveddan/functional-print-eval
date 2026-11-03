"""Checks for a wheel with bearings pressed in: how big is it (class C5), is there room for the
bearings (C5), will they press in and stay on this printer (C2), does the
bolt pass (C3)?

Nothing here assumes how it's done: a seat on each side, two bearings stacked from one side, or two
halves bolted together. Which limits, and where they come from, are in the task's brief. A seat no
print has measured comes back None, "not graded", which is never a pass.
"""
import math
import tempfile
from dataclasses import dataclass
from itertools import groupby

from pbe.nuts import _in_the_manual
from pbe.build import build_parts
from pbe.sections import clear_width, hole_axis, holes, holes_by_layer

STEP = 0.2
TOL = 0.02  # mm; a curve's facets read a modeled width slightly narrow
PLAIN = 1.06  # a hole this much bigger than its clear circle has ribs, lobes or a slot in it
PROUD = 0.5  # mm a bearing may stand out of its seat and still count as seated, though no print has tried it


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
            following = next((h for h in found if h.intersects(stack[-1])), None)
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
    def score(stack):
        widths = [clear_width(h) for h in stack]
        return (sum(_sized(w, seat_range) for w in widths), -min(widths))
    return max(stacks, key=score), layer


def _read_seat(run, layer, tightest, bearing_width, bearings):
    depth = len(run) * layer
    fits = min(int((depth + PROUD + STEP / 2 + TOL) / bearing_width), bearings)  # depth is read in whole layers
    held = max(int(round((fits or 1) * bearing_width / layer)), 1)
    by_width = sorted(run, key=clear_width, reverse=True)[:held]
    across = clear_width(by_width[-1])
    plain = all(h.area <= PLAIN * math.pi * clear_width(h) ** 2 / 4 for h in by_width)
    return Seat(across, depth, fits, plain, tightest < across - 1, 0 < fits and depth < fits * bearing_width - STEP / 2)


def _seats(mesh, seat_range, bearing_width, bearings):
    """The seat-sized stretches of a part's bore, and the bore's tightest width (None if no bore)."""
    axis = int(mesh.extents.argmin())
    stack, layer = _axle(mesh, axis, seat_range)
    if stack is None:
        return [], None
    tightest = min(clear_width(h) for h in stack)
    runs = groupby(stack, key=lambda h: _sized(clear_width(h), seat_range))
    return [_read_seat(list(run), layer, tightest, bearing_width, bearings) for sized, run in runs if sized], tightest


def _finals(sub, built):
    """The final parts' meshes, or None if one failed to build: `builds` has already said so."""
    finals = [built[p.id] for p in sub.parts if p.role == "final" and p.id in built]
    return [b.mesh for b in finals] if all(b.ok for b in finals) else None


def size(sub, built, across, max_width):
    finals = _finals(sub, built)
    if finals is None:
        return None, "a final part didn't build, and that's already a failure"
    if not finals:
        return False, "no final part"
    biggest = max(sorted(m.extents)[-1] for m in finals)
    # halves or layers of the wheel count towards its width, a separate spacer or knob doesn't
    width = sum(min(m.extents) for m in finals if sorted(m.extents)[-2] >= across[0])
    if not across[0] <= biggest <= across[1]:
        return False, f"{biggest:.1f} mm across; about {across[0]} to {across[1]} mm was asked for"
    if width > max_width:
        return False, f"{width:.1f} mm wide; the old wheel's about {max_width} mm at most"
    return True, f"{biggest:.1f} mm across, {width:.1f} mm wide"


def room(sub, built, seat_range, bearing_width, bearings):
    finals = _finals(sub, built)
    if not finals:
        return None, "no wheel to read"
    seats = [s for m in finals for s in _seats(m, seat_range, bearing_width, bearings)[0]]
    held = sum(s.bearings for s in seats)
    if held < bearings:
        deep = ", ".join(f"{s.depth:.1f}" for s in seats) or "none"
        return False, f"room for {held} of {bearings} bearings {bearing_width} mm wide; seat-sized depth: {deep} mm"
    if not all(s.stopped for s in seats if s.bearings):
        return None, "the bore doesn't narrow past the seat, so only the press fit places the bearings, and no print has tried that"
    if any(s.proud for s in seats):
        deep = ", ".join(f"{s.depth:.1f}" for s in seats)
        return None, f"the bearings would stand a little proud (seat depth {deep} mm), and no print has tried that"
    return True, f"room for {held} bearings, in {len(seats)} seat(s)"


def _holds(across, too_tight, holds):
    if across <= too_tight + TOL:
        return False, f"{across:.2f} mm: a {too_tight} mm seat wouldn't take the bearing"
    if holds[0] - TOL <= across <= holds[1] + TOL:
        return True, f"{across:.2f} mm: it presses in and holds upside down"
    if across < holds[0]:
        return None, f"{across:.2f} mm: between {too_tight}, too tight, and {holds[0]}, which held"
    return None, f"{across:.2f} mm: no print has measured above {holds[1]}"


def _param_that_moves_seat(sub, part_id, across, seat_range, bearing_width, bearings):
    """The param that changes the final part's seat, or None. Without one, a coupon's answer can't
    be applied without rewriting the code."""
    only = sub.model_copy(update={"parts": [p for p in sub.parts if p.id == part_id]})
    with tempfile.TemporaryDirectory() as tmp:
        for name, param in sub.params.items():
            if param.value is None:
                continue
            b = build_parts(only, tmp, overrides={name: param.value + 0.2})[part_id]
            seats = _seats(b.mesh, seat_range, bearing_width, bearings)[0] if b.ok else []
            if seats and abs(seats[0].across - across) >= 0.1:
                return name
    return None


def _coupon_seat_that_holds(sub, built, seat_range, too_tight, holds, bearing_width):
    """A test coupon in the manual with a seat that holds: its id, or None."""
    for part in sub.parts:
        b = built.get(part.id)
        if part.role == "coupon" and b is not None and b.ok and _in_the_manual(sub, part.id):
            for seat in _coupon_seats(b.mesh, seat_range, bearing_width):
                if seat.plain and _holds(seat.across, too_tight, holds)[0] is True:
                    return part.id
    return None


def _coupon_seats(mesh, seat_range, bearing_width):
    """A coupon may be a row of seats, through or blind, and half a bearing's depth is enough to
    feel the fit."""
    layer, layers = holes_by_layer(mesh, int(mesh.extents.argmin()), STEP)
    runs, finished = [], []
    for found in layers:
        sized = [h for h in found if _sized(clear_width(h), seat_range)]
        carried = []
        for hole in sized:
            run = next((r for r in runs if r[-1].intersects(hole)), None)
            if run is not None:
                runs.remove(run)
            carried.append((run or []) + [hole])
        finished += runs
        runs = carried
    finished += runs
    return [_read_seat(run, layer, 0, bearing_width, 1) for run in finished if len(run) * layer >= bearing_width / 2]


def fit(sub, built, seat_range, too_tight, holds, bearing_width, bearings):
    """The bearing presses in and stays upside down, or a test coupon would have found a size that
    does and the design has a param to apply it with."""
    finals = [p for p in sub.parts if p.role == "final" and p.id in built and built[p.id].ok]
    found = [(p.id, s) for p in finals for s in _seats(built[p.id].mesh, seat_range, bearing_width, bearings)[0] if s.bearings]
    if not found:
        return None, "no seat to read"
    if not all(s.plain for _, s in found):
        return None, "ribs, lobes or a slot in the seat: only plain round seats were printed"
    verdicts = [_holds(s.across, too_tight, holds) for _, s in found]
    worst = next((v for v in verdicts if v[0] is False), next((v for v in verdicts if v[0] is None), verdicts[0]))
    if worst[0] is True:
        return worst
    coupon = _coupon_seat_that_holds(sub, built, seat_range, too_tight, holds, bearing_width)
    part_id, seat = found[0]
    if coupon and (param := _param_that_moves_seat(sub, part_id, seat.across, seat_range, bearing_width, bearings)):
        return True, f"{worst[1]}; test coupon {coupon} would find a size that holds, and {param} moves the seat"
    return worst[0], worst[1] + "; no test coupon in the manual would catch it"


def bolt_passes(sub, built, seat_range, bolt, fine):
    """The bolt fits through every part of the wheel. Between the bolt's size and ISO 273's fine
    clearance hole, no print has said whether a printed hole passes it."""
    finals = _finals(sub, built)
    if not finals:
        return None, "no wheel to read"
    wheels = [m for m in finals if sorted(m.extents)[-2] >= seat_range[1]]
    tightest = [_seats(m, seat_range, 7, 2)[1] for m in wheels]
    if not tightest or None in tightest:
        return False, "no hole runs through the wheel"
    # a printed spacer or sleeve on the bolt has to pass it too
    for m in finals:
        if not any(m is w for w in wheels) and (axis := hole_axis(m)) is not None:
            stacks, _ = _bore_stacks(m, axis)
            tightest += [min(clear_width(h) for h in stack) for stack in stacks]
    d = min(tightest)
    if d < bolt - TOL:
        return False, f"{d:.2f} mm clear at its tightest: a {bolt} mm bolt won't pass"
    if d < fine - TOL:
        return None, f"{d:.2f} mm clear at its tightest: no print has measured that"
    return True, f"{d:.2f} mm clear at its tightest"
