"""Hex nut pockets, read from the mesh one layer at a time, and compared with what
actually held on this printer (coupon B, results/predictions/round1-coupons.yaml:
press the nut in by hand, turn the coupon over, shake).

The right clearance can't be known before printing, and it changes with nut size, so a
design passes the fit check in either of two ways: its pocket lands where the prints say
the nut holds, or it comes with a test coupon that would have found a size that holds and
its pocket follows a param, so the person can change it.

A check that needs a hex pocket reports "not graded" when there isn't one: the pocket check
has already failed that design, and one mistake should count once.
"""
import math
import re
import tempfile
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from shapely.geometry import Point, Polygon
from shapely.ops import polylabel, unary_union

from pbe.graders.checks import Verdict
from pbe.graders.sections import clear_width, holes, holes_by_layer, holes_in, section, sections_by_layer, single_final
from pbe.parts import catalog
from pbe.parts.build import build_parts
from pbe.parts.printer import printer

ROOT = Path(__file__).resolve().parents[2]
LAYER = printer().layer_mm  # mm: one slice per printed layer
HEX_AREA = math.sqrt(3) / 2  # a hexagon's area over its across-flats squared
NUT_CORNERS = 0.95  # a real nut's corners over a sharp hexagon's: ISO 4032's minimum across-corners (M5: 8.79 over 9.24)
TOL = 0.01  # mm: the mesh's facets and the search's precision
MIN_DEPTH = 1.0  # mm: shallower than this is a chamfer, not a pocket
MAX_DRILL_OUT = 3 * LAYER  # mm: a closed layer thicker than this is a floor with no hole
OPENS_A_HOLE = re.compile(r"""\b(
    (drill|ream|punch|break|clear)(s|ed|ing)?
    | pok(e|es|ed|ing)
    | pierc(e|es|ed|ing)
    | open\ (up|out|the|that|this)
    | (push|cut|knock|pop|punch)(es|s|ed|ing)?\s+((the|that|this|its)\s+)?(\w+\s+)?(skin|layer|membrane|film|web|diaphragm)s?\s+out
)\b""", re.I | re.X)
A_THIN_LAYER = re.compile(r"\b(hole|layer|membrane|skin|film|web|roof|bridge|diaphragm)s?\b", re.I)
NEGATED = re.compile(r"\b(no|not|never|without)\b|n['’]t\b", re.I)
# Where nuts fell out on the tripod build, in PETG (catalog/printer.yaml observed_fits). Coupon B
# calls these sizes and some tighter ones "loose", but nobody has turned that coupon over yet.
FELL_OUT = {"M5": 0.3, "M8": 0.3}
# What each outcome says about the request's "presses in by hand and stays in upside down".
# Any other outcome, "loose" among them, doesn't settle it.
SETTLES = {"holds": True, "won't go in": False, "falls out": False}
# Printed outcomes the checks read differently from how the record codes them, by (nut, clearance).
# The record stays word for word. M3 +0.1 is coded "won't go in", but Dan's note says "really
# struggles to go in", and on 2026-11-05 he said "it was very hard to put in, but i could put it in"
# and "with force it goes in". So it presses in by hand. Nobody recorded turning it over; it's tighter
# than +0.2, which holds, so it's read as holding too (issue 38).
READ_AS = {("M3", 0.1): "holds"}


class PrintedPocket(BaseModel):
    """One pocket printed on coupon B, and what the nut did in it."""
    nut: str
    clearance: float
    outcome: str


class NutCoupon(BaseModel):
    pockets: list[PrintedPocket]


class CouponRound(BaseModel):
    """results/predictions/round1-coupons.yaml, as far as the nut checks read it."""
    B_nuts: NutCoupon


@dataclass
class LayerHole:
    layer: int
    hole: Polygon
    width: float  # its clear width


@dataclass
class Pocket:
    centre: Point
    across: float  # across flats, at its tightest
    depth: float
    z: tuple[float, float]
    opens: list[str]  # the faces a nut could be pressed in from: "bed", "top"
    plain: bool  # a plain hex, the only kind of pocket coupon B measured


def _fits_through(slice_holes, nut):
    """Could this nut shape pass through one of this layer's holes?"""
    return any(hole.buffer(TOL).contains(nut) for hole in slice_holes)


def _outline(polys):
    """A layer's outline, filled: everything inside it is the part or one of its holes."""
    return unary_union([Polygon(poly.exterior) for poly in polys])


def _passes(nut, slice_holes, shrunk_outline):
    """Could this nut pass this layer: through a hole, or through open air outside the part's outline?
    The outline comes shrunk by TOL, as the holes are grown by it."""
    return _fits_through(slice_holes, nut) or not shrunk_outline.intersects(nut)


def _hexagon(centre, across, degrees):
    """A real nut of this across-flats, with a corner at this angle."""
    radius = NUT_CORNERS * across / 2 / math.cos(math.radians(30))
    corners = [math.radians(degrees + corner * 60) for corner in range(6)]
    return Polygon([(centre.x + radius * math.cos(a), centre.y + radius * math.sin(a)) for a in corners])


def _nut_in(hole, across):
    """A nut as wide across its flats as this hole, placed in it, or None if it doesn't fit.
    It's sized from the hole, not from the catalog's nut: this asks whether the hole is
    hex-shaped, and the fit check compares its size with the real nut. A real nut's chamfered
    corners give it over 5 degrees of play either way, so trying every 5 degrees finds any fit."""
    centre = polylabel(hole, tolerance=0.001)
    room = hole.buffer(TOL)
    for degrees in range(0, 60, 5):
        nut = _hexagon(centre, across, degrees)
        if room.contains(nut):
            return nut
    return None


def _is_hex(hole, across):
    """A nut as wide across its flats as the hole fits in it, corners and all. So it can't turn,
    because there's no room for its corners to swing. A round bore, a square or a pentagon that
    wide has no room for the corners at all. Ribs, clips or relief slots around a hexagon still
    count, because they leave the flats where they are or stand on them."""
    return _nut_in(hole, across) is not None


def _nut_sized(width, af):
    """Roughly the nut's size. The upper limit is generous enough to take in a chamfered mouth."""
    return af * 0.8 <= width <= af * 1.5


def _stack_under(stacks, layer, hole):
    """The stack whose top is in the layer below, right under this hole, or None."""
    for stack in stacks:
        top = stack[-1]
        if top.layer == layer - 1 and top.hole.centroid.distance(hole.centroid) < 0.5:
            return stack
    return None


def _nut_sized_stacks(slices, af):
    """Holes about the nut's size, grouped into stacks that sit one on top of another."""
    stacks = []
    for layer, slice_holes in enumerate(slices):
        for hole in slice_holes:
            width = clear_width(hole)
            if not _nut_sized(width, af):
                continue
            stack = _stack_under(stacks, layer, hole)
            if stack is None:
                stacks.append([LayerHole(layer, hole, width)])
            else:
                stack.append(LayerHole(layer, hole, width))
    return stacks


def _is_plain(stack, tightest, opens):
    """Is this a plain hex pocket, the only kind coupon B measured? Ribs, clips and corner relief
    leave more room than the hexagon, and a snap ring or lip has a wider seat beyond it."""
    roomy = tightest.hole.area > 1.03 * HEX_AREA * tightest.width ** 2
    if "top" in opens:  # the nut comes in from the top, so beyond the tightest layer is below it
        beyond = [layer for layer in stack if layer.layer < tightest.layer]
    else:
        beyond = [layer for layer in stack if layer.layer > tightest.layer]
    return not roomy and all(layer.width <= tightest.width + TOL for layer in beyond)


def _read_pocket(stack, tightest, slices, outlines, bottom, layer_h):
    """How deep this pocket is, and which faces a nut can reach it from. Hex layers count in full,
    and up to MIN_DEPTH of other layers a nut's corners fit through, for a chamfered mouth. So a
    round collar it can't pass isn't part of the pocket, and nor is a round bore it could spin in.
    A layer where the nut's place is open air, beside a feature standing higher up, doesn't block it."""
    nut = _nut_in(tightest.hole, tightest.width)
    nut_passes = [_passes(nut, slice_holes, outline) for slice_holes, outline in zip(slices, outlines, strict=True)]
    hex_layers = [layer for layer in stack if nut_passes[layer.layer] and _is_hex(layer.hole, layer.width)]
    other_layers = sum(nut_passes[layer.layer] for layer in stack) - len(hex_layers)
    depth = len(hex_layers) * layer_h + min(other_layers * layer_h, MIN_DEPTH)
    opens = []
    if all(nut_passes[:tightest.layer]):
        opens.append("bed")
    if all(nut_passes[tightest.layer + 1:]):
        opens.append("top")
    z = (bottom + stack[0].layer * layer_h, bottom + (stack[-1].layer + 1) * layer_h)
    return Pocket(nut.centroid, tightest.width, depth, z, opens, _is_plain(stack, tightest, opens))


def find_pockets(mesh, af):
    """Every hex pocket along the print's z axis about the size of a nut with this across-flats.
    The hexagon decides its size: a cone or a round relief next to it can be narrower, but they
    aren't where the nut sits."""
    layer_h, sections = sections_by_layer(mesh, 2, LAYER)
    slices = [holes_in(polys) for polys in sections]
    outlines = [_outline(polys).buffer(-TOL) for polys in sections]
    bottom = mesh.bounds[0, 2]
    pockets = []
    for stack in _nut_sized_stacks(slices, af):
        hexes = [layer for layer in stack if _is_hex(layer.hole, layer.width)]
        if hexes:
            tightest = min(hexes, key=lambda layer: layer.width)
            pockets.append(_read_pocket(stack, tightest, slices, outlines, bottom, layer_h))
    return [found for found in pockets if found.depth >= MIN_DEPTH]


def _nuts_pocket(mesh, af):
    """The nut's pocket: the hex pocket nearest the part's middle, so a hex-shaped lightening
    cell isn't taken for it. The deepest of any on the same axis, so a shallow recess isn't."""
    middle = Point(mesh.centroid[:2])

    def nearest_then_deepest(found):
        return round(found.centre.distance(middle), 1), -found.depth
    return min(find_pockets(mesh, af), key=nearest_then_deepest, default=None)


def _outcome(printed):
    """What the print says, with "loose" read as "falls out" where nuts fell out on the tripod build,
    and READ_AS where the record's note doesn't back its coding."""
    if (printed.nut, printed.clearance) in READ_AS:
        return READ_AS[printed.nut, printed.clearance]
    fell_out = printed.outcome == "loose" and printed.clearance >= FELL_OUT.get(printed.nut, math.inf)
    return "falls out" if fell_out else printed.outcome


@cache
def _measured():
    """The prints' outcomes per nut: (clearance, outcome), tightest first."""
    coupons = CouponRound.model_validate(yaml.safe_load((ROOT / "results/predictions/round1-coupons.yaml").read_text()))
    table = {}
    for printed in coupons.B_nuts.pockets:
        table.setdefault(printed.nut, []).append((printed.clearance, _outcome(printed)))
    return {nut: sorted(rows) for nut, rows in table.items()}


def verdict(label, clearance):
    """What the prints say at this clearance: "holds", "loose", "falls out", "won't go in", a
    READ_AS reading, or None if they can't say: between measured steps that disagree, or beyond them in a direction
    the trend doesn't settle. Tighter than "won't go in" and looser than "loose" are settled."""
    rows = _measured()[label]
    for printed, outcome in rows:
        if abs(clearance - printed) <= TOL:
            return outcome
    below = [outcome for printed, outcome in rows if printed < clearance]
    above = [outcome for printed, outcome in rows if printed > clearance]
    if below and above:
        return below[-1] if below[-1] == above[0] else None
    if above:
        return above[0] if above[0] == "won't go in" else None
    return below[-1] if below[-1] in ("loose", "falls out") else None


def _holds(label, clearance):
    """Does the nut press in by hand and stay in upside down? None if no print has settled it."""
    return SETTLES.get(verdict(label, clearance))


def _pocket_holds(label, found, af):
    """The same for a pocket. The prints only speak for plain ones."""
    return _holds(label, found.across - af) if found.plain else None


def _walls_split(mesh):
    """Do slits cut the part into separate fingers at some height? Then there's no closed hole
    at that height for this check to read."""
    _, slices = holes_by_layer(mesh, 2, LAYER)
    for i in range(len(slices)):
        # filled outlines, so something standing inside a hole doesn't count as a separate piece
        outlines = [Polygon(piece.exterior) for piece in section(mesh, 2, (i + 0.5) / len(slices))]
        if unary_union(outlines).geom_type == "MultiPolygon":
            return True
    return False


def _hole_runs_sideways(mesh, af):
    """Is there a nut-sized hole along x or y? That's a part printed on its side, say."""
    for axis in (0, 1):
        for frac in (0.25, 0.5, 0.75):
            if any(_nut_sized(clear_width(hole), af) for hole in holes(mesh, axis, frac)):
                return True
    return False


def pocket(sub, built, nut):
    """A hex pocket that takes the whole nut and can be reached from one face: its shape stops
    the nut turning, and the far side stops it going through."""
    part, why = single_final(sub, built)
    if part is None:
        return None, why
    hardware = catalog.resolve(nut)
    found = _nuts_pocket(part.mesh, hardware["af"])
    if found is None:
        if _hole_runs_sideways(part.mesh, hardware["af"]):  # this check can't read that, so it can't say
            return None, "a nut-sized hole runs sideways on the bed; this check only reads pockets along z"
        if _walls_split(part.mesh):
            return None, "slits split the walls into fingers, so there's no closed pocket for this check to read"
        return False, f"no hex pocket about {hardware['af']} mm across along z"
    if not found.opens:
        return False, f"pocket at z {found.z[0]:.1f} to {found.z[1]:.1f} is closed: a nut can't be pressed in from either face"
    if len(found.opens) == 2:
        return False, "the hex runs right through: nothing stops the nut going out the far side"
    ok = found.depth >= hardware["h"] - LAYER - TOL  # read to the nearest layer
    return ok, f"hex pocket {found.across:.2f} across flats, {found.depth:.1f} deep (nut {hardware['h']} tall), opens to the {found.opens[0]}"


def _param_that_moves_pocket(sub, part_id, across, af):
    """The param that changes the final part's pocket, or None. Without one, a coupon's answer
    can't be applied without rewriting the code. Rebuilds the part once per param."""
    only_final = sub.model_copy(update={"parts": [part for part in sub.parts if part.id == part_id]})
    with tempfile.TemporaryDirectory() as tmp:
        for name, param in sub.params.items():
            if param.value is None:
                continue
            rebuilt = build_parts(only_final, tmp, overrides={name: param.value + 0.2})[part_id]
            moved = _nuts_pocket(rebuilt.mesh, af) if rebuilt.ok else None
            if moved and abs(moved.across - across) >= 0.1:
                return name
    return None


def _in_the_manual(sub, part_id):
    named = re.compile(rf"\b{re.escape(part_id)}\b")
    return any(part_id in step.parts or named.search(step.text) for step in sub.manual)


def coupons_in_the_manual(sub, built):
    """The test coupons that built and that the manual tells the person to print: (part id, Built)."""
    coupons = []
    for part in sub.parts:
        coupon = built.get(part.id)
        if part.role == "coupon" and coupon is not None and coupon.ok and _in_the_manual(sub, part.id):
            coupons.append((part.id, coupon))
    return coupons


def _coupon_sizes(sub, built, nut, af):
    """The pockets on test coupons the manual tells the person to print: (part id, pocket).
    A nut has to be able to get at least halfway in, or a pocket can't test whether it holds."""
    half_a_nut = catalog.resolve(nut)["h"] / 2
    sizes = []
    for part_id, coupon in coupons_in_the_manual(sub, built):
        sizes += [(part_id, found) for found in find_pockets(coupon.mesh, af) if found.opens and found.depth >= half_a_nut]
    return sizes


def _reading(found, clearance, af, said):
    """What the prints say about this pocket, in words."""
    if not found.plain:
        return f"pocket {found.across:.2f} across flats at its tightest, with ribs, clips, a lip or relief: no print has measured those"
    reading = f"pocket {found.across:.2f} across flats, {clearance:+.2f} over the {af} nut: prints say {said or 'not measured'}"
    if said == "loose":
        reading += " (nobody has turned that one upside down)"
    return reading


def _coupon_rescue(sub, built, nut, label, part_id, found, af) -> Verdict | str:
    """What the design's test coupons say, if one would have found a size that holds and the final
    part's pocket follows a param; otherwise why they don't get there, in words."""
    coupons = coupons_in_the_manual(sub, built)
    if not coupons:
        return "no test print in the manual"
    sizes = _coupon_sizes(sub, built, nut, af)
    if not sizes:
        return f"test print {coupons[0][0]} has no pocket a nut could try"
    first_coupon, _ = sizes[0]
    tries = [_pocket_holds(label, coupon_pocket, af) for _, coupon_pocket in sizes]
    if not any(held is not False for held in tries):  # finding out a size is wrong isn't finding one that holds
        return f"test print {first_coupon} would show the size is wrong, but has no size known to hold"
    param = _param_that_moves_pocket(sub, part_id, found.across, af)
    if param is None:
        return f"test print {first_coupon} could find a size, but no param moves the pocket"
    if True in tries:
        coupon, good = sizes[tries.index(True)]
        return Verdict(True, f"test coupon {coupon} has {len(sizes)} pocket(s), with {good.across:.2f} holding, and the pocket follows param {param}")
    return Verdict(None, f"test coupon {first_coupon} has {len(sizes)} pocket(s), and no print has settled whether any of them holds")


def fit(sub, built, nut, label):
    """The nut presses in by hand and stays in upside down, on this printer, or a test coupon
    would have found a size where it does, and the pocket can be changed to match."""
    part, why = single_final(sub, built)
    if part is None:
        return None, why
    af = catalog.resolve(nut)["af"]
    found = _nuts_pocket(part.mesh, af)
    if found is None:
        return None, "no hex pocket for a nut to fit"
    clearance = round(found.across - af, 3) or 0.0  # or 0.0: a tiny negative would print as "-0.00"
    reading = _reading(found, clearance, af, verdict(label, clearance))
    holds = _holds(label, clearance) if found.plain else None
    if holds:
        return True, reading
    if not found.plain:  # a size found on a plain coupon says nothing about a pocket with ribs or clips
        return holds, f"{reading}; test prints aren't counted for a pocket like this"
    rescue = _coupon_rescue(sub, built, nut, label, part.part_id, found, af)
    if isinstance(rescue, str):
        return holds, f"{reading}; {rescue}"
    return rescue.ok, f"{reading}; {rescue.detail}"


def _says_to_open_a_hole(sentence):
    verb = OPENS_A_HOLE.search(sentence)
    if verb is None or A_THIN_LAYER.search(sentence) is None:
        return False
    three_words_before = " ".join(sentence[:verb.start()].split()[-3:])
    return NEGATED.search(three_words_before) is None


def sentence_saying_to_clear_it(sub):
    """A sentence in the manual that says to open up a hole or layer, or None. It's a text match,
    not an understanding, so the check quotes the sentence for whoever reads the result."""
    for step in sub.manual:
        for sentence in re.split(r"[.;!?]\s", f"{step.text}. {step.tool or ''}"):
            if _says_to_open_a_hole(sentence):
                return sentence.strip()
    return None


def bolt_passes(sub, built, nut, d_min):
    """The bolt goes through the nut and out the other side: at every layer, a circle of d_min
    around the pocket's centre is clear. A layer or three left across the hole passes only if
    the manual says to clear it (a drill-out layer)."""
    part, why = single_final(sub, built)
    if part is None:
        return None, why
    found = _nuts_pocket(part.mesh, catalog.resolve(nut)["af"])
    if found is None:
        return None, "no hex pocket to line the bolt up with"
    layer_h, sections = sections_by_layer(part.mesh, 2, LAYER)
    clears = [_clear_around(holes_in(polys), _outline(polys), found.centre) for polys in sections]
    blocked = [i for i, c in enumerate(clears) if c < d_min - TOL]
    if not blocked:
        height = len(sections) * layer_h
        return True, f"clear all the way through {height:.1f} mm: {min(clears):.2f} at its narrowest (want at least {d_min})"
    thickness = len(blocked) * layer_h
    closed = all(clears[i] == 0.0 for i in blocked)
    told = sentence_saying_to_clear_it(sub)
    if closed and thickness <= MAX_DRILL_OUT + TOL and told:
        return True, f"a {thickness:.1f} mm drill-out layer the manual says to clear (\"{told}\"); otherwise at least {d_min} clear"
    z = part.mesh.bounds[0, 2] + (blocked[0] + 0.5) * layer_h
    return False, f"only {clears[blocked[0]]:.2f} clear at z = {z:.1f} (want at least {d_min})"


def _clear_around(slice_holes, outline, centre):
    """The widest circle around this point that's clear in this layer: in a hole, or in open air
    outside the part's outline, beside a feature standing higher up. 0 if it's solid."""
    hole = next((found for found in slice_holes if found.contains(centre)), None)
    if hole is not None:
        return 2 * hole.boundary.distance(centre)
    return math.inf if outline.is_empty else 2 * outline.distance(centre)


def summarize(sub, built, nut, label):
    """For observations, not grading: every hex pocket in every part."""
    af = catalog.resolve(nut)["af"]
    out = []
    for part in sub.parts:
        built_part = built.get(part.id)
        if built_part is None or not built_part.ok:
            continue
        for found in find_pockets(built_part.mesh, af):
            clearance = round(found.across - af, 2) or 0.0  # or 0.0: not "-0.0"
            prints_say = verdict(label, clearance) if found.plain else "not a plain pocket"
            out.append({"part": part.id, "role": part.role, "across": round(found.across, 2), "clearance": clearance,
                        "prints_say": prints_say, "depth": round(found.depth, 1), "opens": found.opens})
    return out
