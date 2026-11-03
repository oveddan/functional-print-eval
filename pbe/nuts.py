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
from shapely.geometry import Point, Polygon
from shapely.ops import polylabel, unary_union

from pbe import catalog
from pbe.bridges import settings
from pbe.build import build_parts
from pbe.sections import clear_width, holes, holes_by_layer, section, single_final

ROOT = Path(__file__).resolve().parents[1]
LAYER = settings()["layer"]  # mm: one slice per printed layer
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
)\b""", re.I | re.X)
A_THIN_LAYER = re.compile(r"\b(hole|layer|membrane|skin|film|web|roof|bridge|diaphragm)s?\b", re.I)
NEGATED = re.compile(r"\b(no|not|never|without)\b|n['’]t\b", re.I)
# Where nuts fell out on the tripod build, in PETG (catalog/printer.yaml observed_fits). Coupon B
# calls these sizes and some tighter ones "loose", but nobody has turned that coupon over yet.
FELL_OUT = {"M5": 0.3, "M8": 0.3}
# What each outcome says about the request's "presses in by hand and stays in upside down".
# Any other outcome, "loose" among them, doesn't settle it.
SETTLES = {"holds": True, "won't go in": False, "falls out": False}


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
    """Could this nut shape pass through this layer?"""
    return any(h.buffer(TOL).contains(nut) for h in slice_holes)


def _hexagon(centre, across, degrees):
    """A real nut of this across-flats, with a corner at this angle."""
    radius = NUT_CORNERS * across / 2 / math.cos(math.radians(30))
    corners = [math.radians(degrees + k * 60) for k in range(6)]
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
    beyond = [s for s in stack if (s.layer < tightest.layer if "top" in opens else s.layer > tightest.layer)]
    return not roomy and all(s.width <= tightest.width + TOL for s in beyond)


def _read_pocket(stack, tightest, slices, lo, layer_h):
    """How deep this pocket is, and which faces a nut can reach it from. Hex layers count in full,
    and up to MIN_DEPTH of other layers a nut's corners fit through, for a chamfered mouth. So a
    round collar it can't pass isn't part of the pocket, and nor is a round bore it could spin in."""
    nut = _nut_in(tightest.hole, tightest.width)
    nut_passes = [_fits_through(s, nut) for s in slices]
    hex_layers = [s for s in stack if nut_passes[s.layer] and _is_hex(s.hole, s.width)]
    other_layers = sum(nut_passes[s.layer] for s in stack) - len(hex_layers)
    depth = len(hex_layers) * layer_h + min(other_layers * layer_h, MIN_DEPTH)
    opens = []
    if all(nut_passes[:tightest.layer]):
        opens.append("bed")
    if all(nut_passes[tightest.layer + 1:]):
        opens.append("top")
    z = (lo + stack[0].layer * layer_h, lo + (stack[-1].layer + 1) * layer_h)
    return Pocket(nut.centroid, tightest.width, depth, z, opens, _is_plain(stack, tightest, opens))


def find_pockets(mesh, af):
    """Every hex pocket along the print's z axis about the size of a nut with this across-flats.
    The hexagon decides its size: a cone or a round relief next to it can be narrower, but they
    aren't where the nut sits."""
    layer_h, slices = holes_by_layer(mesh, 2, LAYER)
    lo = mesh.bounds[0, 2]
    pockets = []
    for stack in _nut_sized_stacks(slices, af):
        hexes = [s for s in stack if _is_hex(s.hole, s.width)]
        if hexes:
            pockets.append(_read_pocket(stack, min(hexes, key=lambda s: s.width), slices, lo, layer_h))
    return [p for p in pockets if p.depth >= MIN_DEPTH]


def _nuts_pocket(mesh, af):
    """The nut's pocket: the hex pocket nearest the part's middle, so a hex-shaped lightening
    cell isn't taken for it. The deepest of any on the same axis, so a shallow recess isn't."""
    middle = Point(mesh.centroid[:2])
    return min(find_pockets(mesh, af), key=lambda p: (round(p.centre.distance(middle), 1), -p.depth), default=None)


@cache
def _measured():
    """The prints' outcomes per nut: (clearance, outcome), tightest first."""
    data = yaml.safe_load((ROOT / "results/predictions/round1-coupons.yaml").read_text())
    table = {}
    for p in data["B_nuts"]["pockets"]:
        fell_out = p["outcome"] == "loose" and p["clearance"] >= FELL_OUT.get(p["nut"], math.inf)
        table.setdefault(p["nut"], []).append((p["clearance"], "falls out" if fell_out else p["outcome"]))
    return {k: sorted(v) for k, v in table.items()}


def verdict(label, clearance):
    """What the prints say at this clearance: "holds", "loose", "falls out", "won't go in", or
    None if they can't say: between measured steps that disagree, or beyond them in a direction
    the trend doesn't settle. Tighter than "won't go in" and looser than "loose" are settled."""
    rows = _measured()[label]
    for c, outcome in rows:
        if abs(clearance - c) <= TOL:
            return outcome
    below = [outcome for c, outcome in rows if c < clearance]
    above = [outcome for c, outcome in rows if c > clearance]
    if below and above:
        return below[-1] if below[-1] == above[0] else None
    if above:
        return above[0] if above[0] == "won't go in" else None
    return below[-1] if below[-1] in ("loose", "falls out") else None


def _holds(label, clearance):
    """Does the nut press in by hand and stay in upside down? None if no print has settled it."""
    return SETTLES.get(verdict(label, clearance))


def _pocket_holds(label, p, af):
    """The same for a pocket. The prints only speak for plain ones."""
    return _holds(label, p.across - af) if p.plain else None


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
            if any(_nut_sized(clear_width(h), af) for h in holes(mesh, axis, frac)):
                return True
    return False


def pocket(sub, built, nut):
    """A hex pocket that takes the whole nut and can be reached from one face: its shape stops
    the nut turning, and the far side stops it going through."""
    b, why = single_final(sub, built)
    if b is None:
        return None, why
    hw = catalog.resolve(nut)
    p = _nuts_pocket(b.mesh, hw["af"])
    if p is None:
        if _hole_runs_sideways(b.mesh, hw["af"]):  # this check can't read that, so it can't say
            return None, "a nut-sized hole runs sideways on the bed; this check only reads pockets along z"
        if _walls_split(b.mesh):
            return None, "slits split the walls into fingers, so there's no closed pocket for this check to read"
        return False, f"no hex pocket about {hw['af']} mm across along z"
    if not p.opens:
        return False, f"pocket at z {p.z[0]:.1f} to {p.z[1]:.1f} is closed: a nut can't be pressed in from either face"
    if len(p.opens) == 2:
        return False, "the hex runs right through: nothing stops the nut going out the far side"
    ok = p.depth >= hw["h"] - LAYER - TOL  # read to the nearest layer
    return ok, f"hex pocket {p.across:.2f} across flats, {p.depth:.1f} deep (nut {hw['h']} tall), opens to the {p.opens[0]}"


def _param_that_moves_pocket(sub, part_id, across, af):
    """The param that changes the final part's pocket, or None. Without one, a coupon's answer
    can't be applied without rewriting the code. Rebuilds the part once per param."""
    only_final = sub.model_copy(update={"parts": [p for p in sub.parts if p.id == part_id]})
    with tempfile.TemporaryDirectory() as tmp:
        for name, param in sub.params.items():
            if param.value is None:
                continue
            b = build_parts(only_final, tmp, overrides={name: param.value + 0.2})[part_id]
            moved = _nuts_pocket(b.mesh, af) if b.ok else None
            if moved and abs(moved.across - across) >= 0.1:
                return name
    return None


def _in_the_manual(sub, part_id):
    named = re.compile(rf"\b{re.escape(part_id)}\b")
    return any(part_id in s.parts or named.search(s.text) for s in sub.manual)


def _coupon_sizes(sub, built, nut, af):
    """The pockets on test coupons the manual tells the person to print: (part id, pocket).
    A nut has to be able to get at least halfway in, or a pocket can't test whether it holds."""
    half_a_nut = catalog.resolve(nut)["h"] / 2
    sizes = []
    for part in sub.parts:
        b = built.get(part.id)
        if part.role == "coupon" and b is not None and b.ok and _in_the_manual(sub, part.id):
            sizes += [(part.id, p) for p in find_pockets(b.mesh, af) if p.opens and p.depth >= half_a_nut]
    return sizes


def fit(sub, built, nut, label):
    """The nut presses in by hand and stays in upside down, on this printer, or a test coupon
    would have found a size where it does, and the pocket can be changed to match."""
    b, why = single_final(sub, built)
    if b is None:
        return None, why
    af = catalog.resolve(nut)["af"]
    p = _nuts_pocket(b.mesh, af)
    if p is None:
        return None, "no hex pocket for a nut to fit"
    clearance = round(p.across - af, 3) or 0.0  # or 0.0: a tiny negative would print as "-0.00"
    said = verdict(label, clearance)
    reading = f"pocket {p.across:.2f} across flats, {clearance:+.2f} over the {af} nut: prints say {said or 'not measured'}"
    if said == "loose":
        reading += " (nobody has turned that one upside down)"
    if not p.plain:
        reading = f"pocket {p.across:.2f} across flats at its tightest, with ribs, clips, a lip or relief: no print has measured those"
    holds = _holds(label, clearance) if p.plain else None
    if holds:
        return True, reading
    # a size found on a plain coupon says nothing about a pocket with ribs or clips
    sizes = _coupon_sizes(sub, built, nut, af) if p.plain else []
    tries = [_pocket_holds(label, pocket, af) for _, pocket in sizes]
    worth_changing = any(t is not False for t in tries)  # a coupon with only wrong sizes can't help
    param = _param_that_moves_pocket(sub, b.part, p.across, af) if worth_changing else None
    if param is None:
        return holds, f"{reading}; no test coupon in the manual would catch it"
    if True in tries:
        coupon, good = sizes[tries.index(True)]
        return True, f"{reading}; test coupon {coupon} has {len(sizes)} pocket(s), with {good.across:.2f} holding, and the pocket follows param {param}"
    return None, f"{reading}; test coupon {sizes[0][0]} has {len(sizes)} pocket(s), and no print has settled whether any of them holds"


def _says_to_open_a_hole(sentence):
    verb = OPENS_A_HOLE.search(sentence)
    if verb is None or A_THIN_LAYER.search(sentence) is None:
        return False
    three_words_before = " ".join(sentence[:verb.start()].split()[-3:])
    return NEGATED.search(three_words_before) is None


def _sentence_saying_to_clear_it(sub):
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
    b, why = single_final(sub, built)
    if b is None:
        return None, why
    p = _nuts_pocket(b.mesh, catalog.resolve(nut)["af"])
    if p is None:
        return None, "no hex pocket to line the bolt up with"
    layer_h, slices = holes_by_layer(b.mesh, 2, LAYER)
    clears = [_clear_around(s, p.centre) for s in slices]
    blocked = [i for i, c in enumerate(clears) if c < d_min - TOL]
    if not blocked:
        height = len(slices) * layer_h
        return True, f"clear all the way through {height:.1f} mm: {min(clears):.2f} at its narrowest (want at least {d_min})"
    thickness = len(blocked) * layer_h
    closed = all(clears[i] == 0.0 for i in blocked)
    told = _sentence_saying_to_clear_it(sub)
    if closed and thickness <= MAX_DRILL_OUT + TOL and told:
        return True, f"a {thickness:.1f} mm drill-out layer the manual says to clear (\"{told}\"); otherwise at least {d_min} clear"
    z = b.mesh.bounds[0, 2] + (blocked[0] + 0.5) * layer_h
    return False, f"only {clears[blocked[0]]:.2f} clear at z = {z:.1f} (want at least {d_min})"


def _clear_around(slice_holes, centre):
    """The widest circle around this point that's clear in this layer. 0 if it's solid."""
    hole = next((h for h in slice_holes if h.contains(centre)), None)
    return 0.0 if hole is None else 2 * hole.boundary.distance(centre)


def summarize(sub, built, nut, label):
    """For observations, not grading: every hex pocket in every part."""
    af = catalog.resolve(nut)["af"]
    out = []
    for part in sub.parts:
        b = built.get(part.id)
        if b is None or not b.ok:
            continue
        for p in find_pockets(b.mesh, af):
            c = round(p.across - af, 2) or 0.0  # or 0.0: not "-0.0"
            out.append({"part": part.id, "role": part.role, "across": round(p.across, 2), "clearance": c,
                        "prints_say": verdict(label, c) if p.plain else "not a plain pocket", "depth": round(p.depth, 1), "opens": p.opens})
    return out
