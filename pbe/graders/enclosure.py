"""Checks for a printed box that holds bought boards and hangs on a wall: do the screws meet a board's own
holes (class C1), are the screws the right length for what they clamp (C3), can a plug reach a socket from
outside (C5), will the heat-set inserts hold (C3), do the boards and what stands on them fit inside (C5),
do the keyholes hang it (C7), and does anything stand proud of the back (C5)?

They read the finished piece from the submission's `assembly` (pbe/graders/placed.py), so nothing assumes
how many parts the box has or which way they print. Which board, and every limit, comes from the task's
requirements.yaml; the brief says where each comes from. What the records can't decide comes back None,
"not graded", which is never a pass.
"""
import tempfile
from typing import NamedTuple

import numpy as np
from pydantic import BaseModel
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from pbe.graders import placed
from pbe.graders.nuts import coupons_in_the_manual
from pbe.graders.checks import Verdict
from pbe.graders.placed import NotReadable
from pbe.graders.sections import clear_circle, holes_by_layer
from pbe.parts.build import build_parts
from pbe.parts.submission import Placement

TOL = 0.02  # mm; a curve's facets read a modelled width slightly narrow
NEAR = 4.0  # mm around a board's hole that's read for what lies behind it
LAYER = 0.4  # mm between the cross-sections read along a screw
CORE = 1.0  # mm, the radius probed down a screw's axis: inside any M3 hole, thread or pilot
REACH = 400.0  # mm a beam is followed: past anything in a piece that fits the bed
PARALLEL = 0.98  # |cos| between a screw and a board's axis that counts as going through it
UNREADABLE = "a part's mesh isn't a closed volume, so this can't be read"


class Envelope(NamedTuple):
    """A box standing on a board's top face, centred on its origin: across, along, and how high."""
    width: float
    length: float
    height: float


class Electronics(BaseModel):
    """The parts standing on a board: where they certainly are, and where they might be."""
    item: str
    certain: Envelope
    possible: Envelope


class EntryLimits(BaseModel):
    fails_under: float
    passes_from: float


class SlotLimits(BaseModel):
    fails_under: float
    fails_from: float
    passes: tuple[float, float]


class AngleLimits(BaseModel):
    """Degrees from straight up."""
    passes_within: float
    fails_beyond: float


def _worst(verdicts):
    """The first failure, else the first not graded, else the first verdict."""
    for wanted in (False, None):
        for verdict in verdicts:
            if verdict.ok is wanted:
                return verdict
    return verdicts[0]


def _readable(check):
    """A check that answers not graded, rather than failing, when a part's mesh can't be probed."""
    def run(sub, built, **args):
        try:
            return check(sub, built, **args)
        except NotReadable:
            return Verdict(None, UNREADABLE)
    run.__name__, run.__doc__ = check.__name__, check.__doc__
    return run


def _placed_once(piece, ref):
    found = piece.placements(ref)
    return found[0] if len(found) == 1 else None


def _uses(sub, ref):
    return any(item.ref == ref for item in sub.hardware)


def _stadium(width, height):
    """A slot shape, long side along x, centred on the origin."""
    straight = max(width - height, 0) / 2
    return LineString([(-straight, 0), (straight, 0)]).buffer(height / 2, quad_segs=32)


# --- a board's own holes, and what's behind them ---

def _hole_spans(holes_r):
    """Where each of a board's two holes can be, in its own frame: a short stretch of its x axis either
    side of the centre."""
    near, far = holes_r
    return [LineString([(side * near, 0), (side * far, 0)]) for side in (1, -1)]


def _threaded(width, screw, inserts, insert_hole):
    """Whether a hole this wide holds the screw at its centre: a pilot it cuts its thread in, or an insert."""
    return width < screw - TOL or (inserts and insert_hole[0] <= width <= insert_hole[1])


def _room_for_screw(material, near, screw, inserts, insert_hole):
    """Where a screw's axis can be at one depth: anywhere it clears in an open space or a clearance
    hole, but only at the centre of a hole that threads it."""
    room = []
    free = near.difference(unary_union(material))
    for space in getattr(free, "geoms", [free]):
        if space.is_empty or not isinstance(space, Polygon):
            continue
        centre, width = clear_circle(space)
        if _threaded(width, screw, inserts, insert_hole):
            room.append(centre.buffer(0.05))
        elif width >= screw - TOL:
            room.append(space.buffer(-screw / 2 + TOL))
    return unary_union(room) if room else Polygon()


def _behind_hole(meshes, span, screw, inserts, insert_hole, rests_within, depth, slack=0.0):
    """For one of the board's holes: where a screw through it can go in the plastic behind, as
    (Verdict or None if it can go somewhere, the room it has)."""
    near = span.buffer(NEAR)
    layers = []
    for behind in np.arange(0.2, depth, LAYER):
        material = [polygon for polygon in placed.section(meshes, -behind) if polygon.intersects(near)]
        layers.append((behind, material))
    first = next((index for index, (_, material) in enumerate(layers) if material), None)
    if first is None:
        return Verdict(False, f"nothing behind the hole at {span.coords[0][0]:+.1f} mm to screw into"), None
    if layers[first][0] > rests_within:
        return Verdict(False, f"the board doesn't rest on anything at its hole: the first plastic is {layers[first][0]:.1f} mm behind it"), None
    room = None
    for _, material in layers[first:]:
        if not material:
            break  # open space
        here = _room_for_screw(material, near, screw, inserts, insert_hole)
        if room is not None and not here.intersects(room.intersection(span.buffer(slack + TOL)).buffer(0.05)):
            break  # where a screw through the board's hole can be ends here, as at a blind hole's bottom: whether
            # it bottoms out is R2's. Gaps out of its reach aren't this hole (a 0.36 mm sliver 4 mm from Haiku's
            # insert pocket, in pilot-estoa)
        room = here if room is None else room.intersection(here)
    return None, room if room is not None else Polygon()


def _hole_verdict(meshes, span, slack, screw, inserts, insert_hole, rests_within, depth) -> Verdict:
    failed, room = _behind_hole(meshes, span, screw, inserts, insert_hole, rests_within, depth, slack)
    if failed:
        return failed
    where = f"{span.coords[0][0]:+.1f} mm"
    if room.is_empty:
        return Verdict(False, f"{MISSED_HOLE} {where} finds no hole in the box to go into")  # a template can still move one there
    samples = [span.interpolate(fraction, normalized=True) for fraction in np.linspace(0, 1, 11)]
    distances = [sample.distance(room) for sample in samples]
    if min(distances) > slack + TOL:
        return Verdict(False, f"a screw through the hole at {where} misses the box's hole by at least {min(distances) - slack:.2f} mm")
    if max(distances) <= slack + TOL:
        return Verdict(True, f"a screw through the hole at {where} goes into the box wherever the hole really is")
    return Verdict(None, f"a screw through the hole at {where} goes in only if the hole is at one end of where Dan's readings put it")


def _board_in_plastic(meshes, board_radius, board_thickness, spans, hole):
    """Plastic where the board itself is: (pins through its holes, plastic elsewhere in it)."""
    inside = unary_union(placed.section(meshes, board_thickness / 2))
    inside = inside.intersection(Point(0, 0).buffer(board_radius, quad_segs=64))
    holes = unary_union([span.buffer(hole / 2 + 0.5) for span in spans])
    return inside.intersection(holes).area > 0.5, inside.difference(holes).area > 0.5


def _board_holes(sub, built, item, holes_r, hole, screw, insert, insert_hole, board_radius, board_thickness, rests_within, depth):
    """A screw through each of the board's holes goes into the box, for anywhere the person's readings put
    the holes: through a clearance hole it can move in, or into a thread at the hole's centre."""
    piece, why = placed.piece(sub, built)
    if piece is None:
        return Verdict(None, why)
    board = _placed_once(piece, item)
    if board is None:
        return Verdict(None, f"{item} isn't placed once")
    if np.dot(placed.unit(board.z_axis), placed.UP) < 0.9:
        return Verdict(False, "the disk doesn't face out from the wall")
    meshes = placed.into(piece.meshes, board)
    spans = _hole_spans(holes_r)
    pins, in_board = _board_in_plastic(meshes, board_radius, board_thickness[0], spans, hole)
    if in_board:
        return Verdict(False, "printed plastic stands where the disk's board is")
    if pins:
        return Verdict(None, "printed pins through the disk's holes: no print has tried that")
    slack = (hole - screw) / 2
    inserts = _uses(sub, insert)
    return _worst([_hole_verdict(meshes, span, slack, screw, inserts, insert_hole, rests_within, depth) for span in spans])


# --- a test that would have found the answer: a template or test print, and a param that applies it ---

TEST_METHODS = ("template", "coupon")  # the schema's names for a template and a test print
MISSED_HOLE = "a screw through the hole at"
MAX_PARAMS_TRIED = 8  # each try rebuilds the final parts, a few seconds each


def _rebuilt_piece(sub, name, value, tmp):
    """The finished piece with one param changed, or None if a final part no longer builds."""
    finals = sub.model_copy(update={"parts": [part for part in sub.parts if part.role == "final"]})
    rebuilt = build_parts(finals, tmp, overrides={name: value})
    found, _ = placed.piece(sub, rebuilt)
    return found


def _param_that_moves(sub, names, reading, step=1.0):
    """The first of these params whose change moves what `reading(piece)` returns, as a shapely shape,
    by more than a sliver: the param the person changes once the test has told them what to. None if
    none does: then the answer can't be applied without rewriting the code."""
    with tempfile.TemporaryDirectory() as tmp:
        before = reading(_rebuilt_piece(sub, names[0], sub.params[names[0]].value, tmp)) if names else None
        for name in names[:MAX_PARAMS_TRIED]:
            piece = _rebuilt_piece(sub, name, sub.params[name].value + step, tmp)
            if piece is not None and reading(piece).symmetric_difference(before).area > 0.5:
                return name
    return None


def _holes_behind_board(item, holes_r):
    """What the plastic just behind a board's holes looks like, in its own frame, for a piece."""
    def reading(piece):
        board = _placed_once(piece, item)
        near = unary_union([span.buffer(NEAR) for span in _hole_spans(holes_r)])
        return unary_union(placed.section(placed.into(piece.meshes, board), -0.3)).intersection(near)
    return reading


def _template_rescue(sub, item, holes_r) -> Verdict | None:
    """A template or test print the design checks the board's holes with, and a param that moves the box's holes
    to match: Estoa placed the disk's holes from a printout ("They put it where the two holes go, based on the
    printout. We're good."). None if the design has no such test."""
    named = [name for criterion in sub.criteria if criterion.check.method in TEST_METHODS
             for name in criterion.params if name in sub.params and sub.params[name].value is not None]
    if not named:
        return None
    param = _param_that_moves(sub, list(dict.fromkeys(named)), _holes_behind_board(item, holes_r))
    if param is None:
        return None
    return Verdict(True, f"a template or test print checks the holes, and param {param} moves them to match")


@_readable
def board_holes(sub, built, item, holes_r, hole, screw, insert, insert_hole, board_radius, board_thickness, rests_within, depth):
    """A screw through each of the board's holes goes into the box wherever the person's readings put the holes,
    or the design checks the holes against the board with a template or test print and can move them to match."""
    found = _board_holes(sub, built, item, holes_r, hole, screw, insert, insert_hole, board_radius, board_thickness,
                         rests_within, depth)
    position_only = found.detail.startswith(MISSED_HOLE)  # a template finds where holes go, nothing else
    if found.ok is True or not position_only or placed.piece(sub, built)[0] is None:
        return found
    rescue = _template_rescue(sub, item, holes_r)
    if rescue is None:
        return Verdict(found.ok, f"{found.detail}; no template or test print in the design would catch it")
    return Verdict(True, f"{found.detail}; {rescue.detail}")


# --- screws: what they go through, and where their tips end ---

def _screws_through(piece, board, spans):
    """The screws that go through the board's holes, as (span, screw), in the board's frame."""
    found = []
    for span in spans:
        for screw in piece.screws:
            axis = placed.direction_in(board, screw.direction)
            if abs(axis[2]) < PARALLEL:
                continue
            start = placed.from_piece(board, screw.head)
            crossing = start - axis * (start[2] / axis[2])  # where its line meets the board's back face
            if span.distance(Point(crossing[0], crossing[1])) <= 1.5:
                found.append((span, screw, crossing))
    return found


def _first_plastic_down(meshes, x, y, top, bottom):
    """How far below `top` the first plastic stands on the axis at (x, y), down to `bottom`, or None."""
    probe = placed.column(CORE, bottom, top)
    probe.apply_translation((x, y, 0))
    highest = placed.highest_z(placed.plastic_in(meshes, probe))
    return None if highest is None else top - highest


def _plastic_run(meshes, x, y, radius, depth):
    """How deep the plastic around a hole of this radius runs down from the board's back face."""
    ring = placed.column(radius + 0.7, -depth, 0.05, inner=radius + 0.2)
    ring.apply_translation((x, y, 0))
    found = [piece for found in placed.plastic_in(meshes, ring) for piece in found.split(only_watertight=False)]
    touching = [piece for piece in found if piece.bounds[1][2] >= -0.6]
    return -min(piece.bounds[0][2] for piece in touching) if touching else 0.0


def _hole_at(meshes, x, y, depth=0.2):
    """The hole the axis at (x, y) passes `depth` mm behind the board: its clear width, or None if it's solid."""
    material = placed.section(meshes, -depth)
    near = Point(x, y).buffer(NEAR)
    free = near.difference(unary_union([polygon for polygon in material if polygon.intersects(near)]) if material else Polygon())
    for space in getattr(free, "geoms", [free]):
        if isinstance(space, Polygon) and space.contains(Point(x, y)):
            return clear_circle(space)[1]
    return None


def _insert_behind(meshes, x, y, reach, insert_hole):
    """An insert's hole further along a clearance hole, within the screw's reach, as when an insert is pressed
    in from the inside behind a thin skin: how deep it starts and how wide it is, or None."""
    for depth in np.arange(0.3, reach, 0.1):
        width = _hole_at(meshes, x, y, depth)
        if width is None or width > insert_hole[1]:
            return None  # plastic in the way, or open space: no insert's hole on this axis
        if width >= insert_hole[0]:
            return depth - 0.1, width
    return None


def _inside(point, envelope: Envelope):
    across, along, up = point
    return abs(across) <= envelope.width / 2 and abs(along) <= envelope.length / 2 and 0 <= up <= envelope.height


def _among_electronics(piece, shank, electronics: Electronics):
    """A Verdict if the screw, from where it leaves the board to its tip (points in the piece's frame, tip last),
    runs among the parts on a board, else None. The whole shank counts, not only the tip, so a longer screw
    that passes right through the ESP32 doesn't pass where a shorter one ending in it fails."""
    board = _placed_once(piece, electronics.item)
    if board is None:
        return None
    local = [placed.from_piece(board, point) for point in shank]
    if _inside(local[-1], electronics.certain):
        return Verdict(False, "its tip reaches into the ESP32 on the perfboard")
    if any(_inside(point, electronics.certain) for point in local):
        return Verdict(False, "its shank runs into the ESP32 on the perfboard and out past it")
    if any(_inside(point, electronics.possible) for point in local):
        return Verdict(None, "it runs over the perfboard, where the parts' heights aren't all recorded")
    return None


def _nut_for(sub, screw):
    """The nut in the hardware that fits this screw's thread: (the nut's catalog entry or None, the sizes of any
    nuts that don't fit)."""
    size = sub.resolved(next(item for item in sub.hardware if item.id == screw.item)).get("size")
    nuts = [found for item in sub.hardware if (found := sub.resolved(item))["kind"] == "nut"]
    fits = [nut for nut in nuts if size is not None and nut.get("size") == size]
    return (fits[0] if fits else None), [str(nut.get("size", "unknown")) for nut in nuts if nut not in fits]


def _nut_slot(meshes, x, y, reach, nut_af, nut_h):
    """A captive nut's slot along the screw within its reach: (how deep it starts, how deep it ends), or None.
    A void at least the nut's width across flats, and at least its height deep, counts (Gemini 4 Argon t3 in
    pilot-estoa slid its nuts into slots across its pillars, partway down the bore)."""
    start = None
    for depth in np.arange(0.3, reach + LAYER, LAYER):
        width = _hole_at(meshes, x, y, depth)
        if width is not None and width >= nut_af - TOL:
            start = depth if start is None else start
            continue
        if start is not None and depth - start >= nut_h - TOL:
            return start - LAYER / 2, depth - LAYER / 2
        start = None
    return None


def _engaged(sub, meshes, crossing, screw, board_thickness, threaded, width, engage, nut_h, start=0.0, nut_af=None):
    """Whether the screw holds: enough of it in a thread, or a whole nut on it past the plastic. The thread is
    only as long as the plastic around the hole, so a thin boss with open space behind it holds less. An
    insert behind a skin threads the screw only from `start`, how deep its hole begins."""
    thick, thin = max(board_thickness), min(board_thickness)
    if threaded:
        run = _plastic_run(meshes, crossing[0], crossing[1], width / 2, 30.0) - start
        held = min(screw.length - thick - start, run)
        if held >= engage:
            return Verdict(True, f"{held:.1f} mm or more of it in the thread")
        if screw.length - thin <= start:
            return Verdict(False, "it doesn't reach past the board" if not start else "it doesn't reach the insert")
        if run < engage:
            return Verdict(False, f"only {run:.1f} mm of plastic around its thread; {engage:g} mm or more held")
        return Verdict(None, f"{held:.1f} mm of thread with the thickest board; {engage:g} mm or more held")
    nut, others = _nut_for(sub, screw)
    if nut is None and others:
        return Verdict(False, f"a clearance hole, and the only nuts ({', '.join(sorted(set(others)))}) don't fit its thread")
    if nut is None:
        return Verdict(False, "a clearance hole and no nut: nothing to screw into")
    nut_h = float(nut.get("h", nut_h))  # the nut it actually uses, from the catalog
    nut_af = float(nut["af"]) if nut_af and nut.get("af") else nut_af
    slot = _nut_slot(meshes, crossing[0], crossing[1], screw.length - thin, nut_af, nut_h) if nut_af else None
    if slot is not None:
        top, bottom = slot
        through = top + nut_h  # the screw has to come through the whole nut
        if screw.length - thick >= through - TOL:
            return Verdict(True, f"a captive nut in a slot {top:.1f} to {bottom:.1f} mm behind the board, and the screw runs through it")
        if screw.length - thin < through - TOL:
            return Verdict(False, f"it doesn't reach through the nut in its slot {top:.1f} mm behind the board")
        return Verdict(None, f"it reaches through the nut in its slot only if the board is thin, which wasn't measured")
    run = _plastic_run(meshes, crossing[0], crossing[1], (_hole_at(meshes, crossing[0], crossing[1]) or 0) / 2, 30.0)
    past = screw.length - thick - run
    if past >= nut_h:
        return Verdict(True, f"{past:.1f} mm or more past {run:.1f} mm of plastic, room for the whole nut")
    if screw.length - thin - run < 0:
        return Verdict(False, f"it doesn't get through the {run:.1f} mm of plastic to a nut")
    return Verdict(None, f"{past:.1f} mm past the plastic with the thickest board, less than a nut")


def _screw_through_board(sub, piece, board, meshes, screw, crossing, board_thickness, screw_d, insert, insert_hole,
                         engage, nut_h, electronics, nut_af=None) -> Verdict:
    thick, thin = max(board_thickness), min(board_thickness)
    bottom = _first_plastic_down(meshes, crossing[0], crossing[1], -0.05, -(screw.length - thin) - 0.05)
    if bottom is not None and screw.length - thick > bottom + 0.05 + TOL:
        return Verdict(False, f"a {screw.length:g} mm screw bottoms out {bottom + 0.05:.1f} mm behind the board")
    if bottom is not None and screw.length - thin > bottom + 0.05 + TOL:
        return Verdict(None, "it may bottom out, depending on the board's thickness, which wasn't measured")
    tip_local = np.array([crossing[0], crossing[1], thin - screw.length])
    tip = placed.to_piece(board, tip_local)
    if tip[2] < piece.wall_z - TOL:
        return Verdict(False, f"its tip comes out of the back by {piece.wall_z - tip[2]:.1f} mm")
    shank = [placed.to_piece(board, np.array([crossing[0], crossing[1], z]))
             for z in [*np.arange(0.0, tip_local[2], -0.25), tip_local[2]]]
    if among := _among_electronics(piece, shank, electronics):
        return among
    width = _hole_at(meshes, crossing[0], crossing[1]) or 0
    threaded = _threaded(width, screw_d, _uses(sub, insert), insert_hole)
    start = 0.0
    if not threaded and _uses(sub, insert):
        behind = _insert_behind(meshes, crossing[0], crossing[1], screw.length - min(board_thickness), insert_hole)
        if behind:
            (start, width), threaded = behind, True
    return _engaged(sub, meshes, crossing, screw, board_thickness, threaded, width, engage, nut_h, start, nut_af)


@_readable
def board_screws(sub, built, item, holes_r, hole, screw_d, insert, insert_hole, board_radius, board_thickness, rests_within,
                 depth, nut_h, engage, electronics, nut_af=None):
    """The screws through the board's holes are the right length for what they clamp: they hold (a whole
    nut, or enough thread), don't bottom out, and their tips don't reach the electronics or the wall."""
    holes = _board_holes(sub, built, item=item, holes_r=holes_r, hole=hole, screw=screw_d, insert=insert, insert_hole=insert_hole,
                        board_radius=board_radius, board_thickness=board_thickness, rests_within=rests_within, depth=depth)
    if holes.ok is False:
        return Verdict(None, f"already failed: {holes.detail}")
    electronics = Electronics.model_validate(electronics)
    piece, why = placed.piece(sub, built)
    if piece is None:
        return Verdict(None, why)
    board = _placed_once(piece, item)
    if board is None:
        return Verdict(None, f"{item} isn't placed once")
    meshes = placed.into(piece.meshes, board)
    spans = _hole_spans(holes_r)
    through = _screws_through(piece, board, spans)
    missing = [span for span in spans if not any(found_span is span for found_span, _, _ in through)]
    if missing and holes.ok is None:
        return Verdict(None, f"no screw through the disk's hole at {missing[0].coords[0][0]:+.1f} mm, and {holes.detail}")
    if missing:
        return Verdict(False, f"no screw goes through the disk's hole at {missing[0].coords[0][0]:+.1f} mm")
    verdicts = [_screw_through_board(sub, piece, board, meshes, screw, crossing, board_thickness, screw_d, insert,
                                     insert_hole, engage, nut_h, electronics, nut_af)
                for _, screw, crossing in through]
    return _worst(verdicts)


def _screws_into(piece, board, near):
    """The screws whose axis runs through the board within `near` mm of its origin."""
    found = []
    for screw in piece.screws:
        axis = placed.direction_in(board, screw.direction)
        if abs(axis[2]) < PARALLEL:
            continue
        start = placed.from_piece(board, screw.head)
        crossing = start - axis * (start[2] / axis[2])
        if np.hypot(crossing[0], crossing[1]) <= near:
            found.append(screw)
    return found


def _post_under(piece, screw, board_thickness, engage, ring):
    """One screw through a board into a post: does it bottom out, and does it reach far enough in?"""
    meshes = placed.along(piece.meshes, screw.head, screw.direction)
    around = placed.column(ring[1], 0.0, screw.length + 20, inner=ring[0])
    top = placed.lowest_z(placed.plastic_in(meshes, around))
    if top is None:
        return Verdict(False, f"nothing under the board for the {screw.item} screw to go into")
    reach = screw.length - board_thickness  # head on the board, the board on the post
    core = placed.column(CORE, top + 0.05, top + 40)
    bottom = placed.lowest_z(placed.plastic_in(meshes, core))
    hole_depth = np.inf if bottom is None else bottom - top
    if reach <= 0:
        return Verdict(False, f"a {screw.length:g} mm screw doesn't get through the {board_thickness} mm board")
    if reach > hole_depth + TOL:
        return Verdict(False, f"a {screw.length:g} mm screw reaches {reach:.1f} mm into a {hole_depth:.1f} mm hole: it bottoms out")
    if reach >= engage - TOL:
        depth_text = "a through hole" if bottom is None else f"a {hole_depth:.1f} mm hole"
        return Verdict(True, f"a {screw.length:g} mm screw reaches {reach:.1f} mm into {depth_text}")
    return Verdict(None, f"{reach:.1f} mm of thread: 3 mm or more held, and no print has tried less")


@_readable
def post_screws(sub, built, item, board_thickness, near, engage, ring):
    """The screws through a board into posts under it don't bottom out, and reach far enough to hold."""
    piece, why = placed.piece(sub, built)
    if piece is None:
        return Verdict(None, why)
    board = _placed_once(piece, item)
    if board is None:
        return Verdict(None, f"{item} isn't placed once")
    screws = _screws_into(piece, board, near)
    if not screws:
        return Verdict(None, "the board isn't screwed down, so there's no screw length to check")
    return _worst([_post_under(piece, screw, board_thickness, engage, ring) for screw in screws])


# --- a plug reaching a socket from outside ---

def _obstacles(piece, disk, disk_radius, disk_thickness, with_wall):
    """The printed parts, the disk's board and, if asked, the wall, as meshes in the piece's frame."""
    found = list(piece.meshes)
    if disk is not None:
        board = placed.column(disk_radius, 0.0, disk_thickness)
        board.apply_transform(placed.matrix(disk))
        found.append(board)
    if with_wall:
        found.append(placed.box((-5000, -5000, piece.wall_z - 100), (5000, 5000, piece.wall_z)))
    return found


def _enclosed(obstacles, start, skip):
    """The sides of a point, among the piece's six, with nothing on them; `skip` is left out."""
    open_sides = []
    for axis in range(3):
        for sign in (1, -1):
            direction = np.zeros(3)
            direction[axis] = sign
            if np.dot(direction, skip) > 0.7:
                continue
            low = start + np.minimum(direction * REACH, 0) - (1 - np.abs(direction)) * 0.5
            high = start + np.maximum(direction * REACH, 0) + (1 - np.abs(direction)) * 0.5
            if not placed.plastic_in(obstacles, placed.box(low, high)):
                open_sides.append(("-+"[sign > 0]) + "xyz"[axis])
    return open_sides


def _clear_passage(obstacles, socket, window, start=0.05):
    """The way in to the socket, seen from outside: the part of a window around its mouth that nothing
    covers from `start` mm out of the mouth to the outside. Its long side is along the socket's y."""
    # a frame whose +z runs out of the socket and whose x and y are the socket's y and z
    turned = Placement(origin=socket.origin, x_axis=placed.to_piece(socket, (0, 1, 0)) - np.asarray(socket.origin),
                          z_axis=placed.to_piece(socket, (1, 0, 0)) - np.asarray(socket.origin))
    meshes = placed.into(obstacles, turned)
    beam = placed.box((-window / 2, -window / 2, start), (window / 2, window / 2, REACH))
    covered = placed.shadow(placed.plastic_in(meshes, beam))
    return _component_at_axis(covered, window)


def _wall_at_port(meshes, socket, way_in):
    """How thick the wall is that the way in runs through: the first stretch of plastic out from the mouth,
    read just outside the way in at its four extremes, the thinnest of them."""
    turned = Placement(origin=socket.origin, x_axis=placed.to_piece(socket, (0, 1, 0)) - np.asarray(socket.origin),
                       z_axis=placed.to_piece(socket, (1, 0, 0)) - np.asarray(socket.origin))
    local = placed.into(meshes, turned)
    low_x, low_y, high_x, high_y = way_in.bounds
    beside = [(low_x - 0.5, 0.0), (high_x + 0.5, 0.0), (0.0, low_y - 0.5), (0.0, high_y + 0.5)]
    runs = []
    for x, y in beside:
        column = placed.box((x - 0.2, y - 0.2, 0.05), (x + 0.2, y + 0.2, REACH))
        pieces = [piece for found in placed.plastic_in(local, column) for piece in found.split(only_watertight=False)]
        if pieces:
            first = min(pieces, key=lambda piece: piece.bounds[0][2])
            runs.append(first.bounds[1][2] - first.bounds[0][2])
    return min(runs) if runs else 0.0


def _component_at_axis(covered, window):
    clear = Polygon([(-window / 2, -window / 2), (window / 2, -window / 2), (window / 2, window / 2), (-window / 2, window / 2)]).difference(covered)
    return next((space for space in getattr(clear, "geoms", [clear]) if space.contains(Point(0, 0))), None)


def _fits_somewhere(shape, hole, turns=18):
    """Whether the shape fits in the hole, centred on the hole's widest point, turned any way."""
    centre, _ = clear_circle(hole)
    for turn in range(turns):
        angle = np.pi * turn / turns
        cos, sin = np.cos(angle), np.sin(angle)
        coords = [(centre.x + x * cos - y * sin, centre.y + x * sin + y * cos) for x, y in shape.exterior.coords]
        if Polygon(coords).difference(hole).area < 0.01:
            return True
    return False


def _test_print_openings(sub, built, fits, min_wall):
    """Test prints the manual uses with an opening right through them that holds the shape that let a plug seat,
    in a wall at least as thick as the final part's at the port: their ids."""
    found = []
    for part_id, test_print in coupons_in_the_manual(sub, built):
        axis = int(test_print.mesh.extents.argmin())
        if test_print.mesh.extents[axis] < min_wall - TOL:
            continue
        _, layers = holes_by_layer(test_print.mesh, axis, 0.4)
        through = [hole for hole in layers[0] if all(any(other.intersects(hole) for other in layer) for layer in layers[1:])]
        for hole in through:
            narrowest = hole
            for layer in layers[1:]:
                narrowest = narrowest.intersection(unary_union([other for other in layer if other.intersects(hole)]))
            if isinstance(narrowest, Polygon) and _fits_somewhere(_stadium(*fits).buffer(-TOL), narrowest):
                found.append(part_id)
                break
    return found


def _way_in_width(item, window, disk, disk_radius, disk_thickness):
    """How wide the way in is, along the socket's long side, as a strip: a param has to move this,
    not only the height, to apply a width a test print found."""
    def reading(piece):
        socket = _placed_once(piece, item)
        way_in = _clear_passage(_obstacles(piece, _placed_once(piece, disk), disk_radius, disk_thickness, True), socket, window)
        if way_in is None:
            return Polygon()
        low, _, high, _ = way_in.bounds
        return Polygon([(low, -0.5), (high, -0.5), (high, 0.5), (low, 0.5)])
    return reading


def _test_print_rescue(sub, built, piece, item, way_in, fits, window, disk, disk_radius, disk_thickness) -> Verdict | None:
    """A test print the manual uses would have found an opening that lets the plug seat, and the final
    opening follows a param the person can change. None if not."""
    if way_in is None:
        return None
    wall = _wall_at_port(piece.meshes, _placed_once(piece, item), way_in)
    test_prints = _test_print_openings(sub, built, fits, wall)
    if not test_prints:
        return None
    width = way_in.bounds[2] - way_in.bounds[0] if way_in is not None else 0.0
    candidates = sorted((name for name, param in sub.params.items() if isinstance(param.value, (int, float)) and 3 <= param.value <= 40),
                        key=lambda name: abs(sub.params[name].value - width))
    param = _param_that_moves(sub, candidates, _way_in_width(item, window, disk, disk_radius, disk_thickness), step=1.0)
    if param is None:
        return None
    return Verdict(True, f"test print {test_prints[0]} has an opening of {fits[0]} x {fits[1]} mm or more in a wall at least {wall:.1f} mm "
                         f"thick, and param {param} moves the final opening")


@_readable
def plug_reaches(sub, built, item, fits, failed, failed_from, socket_body, disk, disk_radius, disk_thickness, inside, window):
    """A plug reaches the socket from outside: the board sits inside the box, and the way in from its
    mouth to the outside is at least as roomy as the opening that let a plug seat. It fails only like
    the opening that stopped plugs: no roomier, that far or further out from the mouth, where the plug's
    boot stops and its bare metal can't reach. A small opening nearer the mouth may work, and no print
    says whether it does."""
    piece, why = placed.piece(sub, built)
    if piece is None:
        return Verdict(None, why)
    socket = _placed_once(piece, item)
    if socket is None:
        return Verdict(None, f"{item} isn't placed once")
    if placed.plastic_in(placed.into(piece.meshes, socket), placed.box((-socket_body[0], -socket_body[1] / 2, -socket_body[2] / 2),
                                                                      (-0.05, socket_body[1] / 2, socket_body[2] / 2))):
        return Verdict(False, "printed plastic stands where the socket itself is")
    disk_at = _placed_once(piece, disk)
    out_of_socket = placed.unit(placed.to_piece(socket, (1, 0, 0)) - np.asarray(socket.origin))
    open_sides = _enclosed(_obstacles(piece, disk_at, disk_radius, disk_thickness, False), placed.to_piece(socket, inside), out_of_socket)
    if open_sides:
        return Verdict(False, f"the board with the socket isn't inside the box: nothing on its {', '.join(open_sides)} side")
    way_in = _clear_passage(_obstacles(piece, disk_at, disk_radius, disk_thickness, True), socket, window)
    if way_in is None:
        return Verdict(False, "something stands right in front of the socket")
    roomy, tight = _stadium(*fits).buffer(-TOL), _stadium(*failed).buffer(TOL)
    low_y, low_z, high_y, high_z = way_in.bounds
    size = f"{high_y - low_y:.1f} x {high_z - low_z:.1f} mm"
    if roomy.difference(way_in).area < 0.01:
        return Verdict(True, f"the way in is at least {fits[0]} x {fits[1]} mm ({size} at its widest)")
    farther_out = _clear_passage(_obstacles(piece, disk_at, disk_radius, disk_thickness, True), socket, window, start=failed_from)
    if farther_out is None or farther_out.difference(tight).area < 0.01:
        found = Verdict(False, f"{failed_from} mm or more out from the socket, the way in is no roomier than the {failed[0]} x {failed[1]} mm "
                               f"opening that stopped plugs there ({size} at its widest overall)")
    else:
        found = Verdict(None, f"the way in ({size}) is smaller than the {fits[0]} x {fits[1]} mm opening that let a plug seat, and no "
                              f"print says whether a plug gets through it")
    rescue = _test_print_rescue(sub, built, piece, item, way_in, fits, window, disk, disk_radius, disk_thickness)
    if rescue is None:
        return Verdict(found.ok, f"{found.detail}; no test print in the manual would catch it")
    return Verdict(True, f"{found.detail}; {rescue.detail}")


# --- heat-set inserts ---

def _hole_around_axis(polygons):
    """The hole the axis (the origin) runs through in a cross-section: (the hole, the plastic around it)."""
    axis = Point(0, 0)
    for polygon in polygons:
        for ring in polygon.interiors:
            hole = Polygon(ring).buffer(0)  # a section's ring can cross itself; this mends it
            for other in polygons:
                if hole.contains(other):  # a post standing in it: take away all of it, its own holes too
                    hole = hole.difference(Polygon(other.exterior))
            around = [piece for piece in getattr(hole, "geoms", [hole]) if isinstance(piece, Polygon) and piece.contains(axis)]
            if around:
                return around[0], polygon
    return None, None


def _thinnest_wall(hole, plastic):
    """The thinnest plastic around the hole: to the outline or any other hole in the same piece."""
    edges = [plastic.exterior] + [ring for ring in plastic.interiors if not Polygon(ring).buffer(-0.01).contains(hole.representative_point())]
    hole_ring = hole.exterior
    return min(hole_ring.distance(edge) for edge in edges)


def _insert_under(piece, screw, insert_sized, depth_into):
    """The insert hole a screw goes into: (its width, the thinnest wall around it), or None if it goes into none."""
    meshes = placed.along(piece.meshes, screw.head, screw.direction)
    layers = []
    for along in np.arange(0.2, screw.length + 0.2, LAYER):
        hole, plastic = _hole_around_axis(placed.section(meshes, along))
        if hole is not None and insert_sized[0] <= clear_circle(hole)[1] <= insert_sized[1]:
            layers.append((along, hole, plastic))
    if not layers:
        return None
    mouth = layers[0][0]
    _, hole, plastic = min(layers, key=lambda layer: abs(layer[0] - (mouth + depth_into)))
    return clear_circle(hole)[1], _thinnest_wall(hole, plastic)


@_readable
def insert_posts(sub, built, insert, insert_sized, hole_ok, bulged, held, depth_into):
    """Every insert a screw goes into has plastic around it like the posts that held, not the ones that
    bulged, and sits in a hole like the ones inserts were set in."""
    if not _uses(sub, insert):
        return Verdict(None, "no heat-set inserts")
    piece, why = placed.piece(sub, built)
    if piece is None:
        return Verdict(None, why)
    verdicts = []
    for screw in piece.screws:
        found = _insert_under(piece, screw, insert_sized, depth_into)
        if found is None:
            continue
        width, wall = found
        where = f"the {screw.item} screw's insert"
        if wall <= bulged + TOL:
            verdicts.append(Verdict(False, f"{where} has {wall:.2f} mm of plastic at its thinnest: posts with {bulged} mm bulged"))
        elif not hole_ok[0] - TOL <= width <= hole_ok[1] + TOL:
            verdicts.append(Verdict(None, f"{where} is in a {width:.2f} mm hole; inserts were only set in {hole_ok[0]} to {hole_ok[1]} mm"))
        elif wall >= held - TOL:
            verdicts.append(Verdict(True, f"{where}: {width:.2f} mm hole, {wall:.2f} mm of plastic at its thinnest"))
        else:
            verdicts.append(Verdict(None, f"{where} has {wall:.2f} mm of plastic: between {bulged}, which bulged, and {held}, which held"))
    if not verdicts:
        return Verdict(None, "inserts are listed, but no screw goes into a hole sized for one")
    return _worst(verdicts)


# --- the boards inside ---

def _over(envelope: Envelope, height):
    """The column over a stretch of the board, from just above its top face to `height`."""
    return placed.box((-envelope.width / 2, -envelope.length / 2, 0.05), (envelope.width / 2, envelope.length / 2, height))


def _in_the_board(slab: Envelope, holes):
    """The board's own volume, under its top face and in from its edges, less the corner holes, where posts go."""
    board = placed.box((-slab.width / 2, -slab.length / 2, -slab.height), (slab.width / 2, slab.length / 2, -0.05))
    hole_across, hole_along, keep_clear = holes
    for across_sign in (-1, 1):
        for along_sign in (-1, 1):
            post = placed.column(keep_clear, -slab.height - 1, 1)
            post.apply_translation((across_sign * hole_across, along_sign * hole_along, 0))
            board = board.difference(post, engine="manifold")
    return board


@_readable
def board_room(sub, built, item, certain, room, slab, holes, disk, disk_radius, disk_thickness):
    """The perfboard sits inside the box, not in its plastic, and what stands on it has room: nothing
    lower than the ESP32 over where the ESP32 certainly is, and room for its whole height over the board."""
    piece, why = placed.piece(sub, built)
    if piece is None:
        return Verdict(None, why)
    board = _placed_once(piece, item)
    if board is None:
        return Verdict(None, f"{item} isn't placed once")
    obstacles = _obstacles(piece, _placed_once(piece, disk), disk_radius, disk_thickness, False)
    certain, room, slab = Envelope(*certain), Envelope(*room), Envelope(*slab)
    # a side is open only if nothing is on it from the board's centre and from each corner: from the centre
    # alone, a probe can leave through a big opening in one wall (Gemini 4 Argon's 40 mm USB cutout in pilot-estoa)
    starts = [np.array([across, along, 2.0]) for across, along in
              [(0.0, 0.0)] + [(sx * room.width / 2, sy * room.length / 2) for sx in (-1, 1) for sy in (-1, 1)]]
    open_from = [set(_enclosed(placed.into(obstacles, board), start, np.zeros(3))) for start in starts]
    open_sides = sorted(set.intersection(*open_from))
    if open_sides:
        return Verdict(False, f"the perfboard isn't inside the box: nothing on its {', '.join(open_sides)} side")
    if placed.plastic_in(placed.into(piece.meshes, board), _in_the_board(slab, holes)):
        return Verdict(False, "the perfboard sits in printed plastic")
    overhead = placed.into(obstacles, board)  # the disk can be the ceiling over the ESP32 too
    over_esp32 = placed.lowest_z(placed.plastic_in(overhead, _over(certain, room.height)))
    if over_esp32 is not None and over_esp32 < certain.height - TOL:
        return Verdict(False, f"plastic or the disk {over_esp32:.1f} mm above the perfboard, where the ESP32 stands at least {certain.height} mm")
    over_board = placed.lowest_z(placed.plastic_in(overhead, _over(room, room.height)))
    if over_board is None:
        return Verdict(True, f"at least {room.height} mm clear above the perfboard")
    return Verdict(None, f"plastic or the disk {over_board:.1f} mm above the perfboard: the ESP32 stands about {room.height} mm, and its exact spot isn't recorded")


# --- hanging on the wall ---

def _keyhole(hole):
    """A keyhole's (entry centre, entry width, slot width, slot direction, travel), or None if the hole isn't one."""
    centre, entry = clear_circle(hole)
    rest = hole.difference(centre.buffer(entry / 2 + 0.3, quad_segs=64))
    pieces = [piece for piece in getattr(rest, "geoms", [rest]) if isinstance(piece, Polygon) and piece.area > 1.0]
    if not pieces:
        return None
    slot = max(pieces, key=lambda piece: piece.area)
    _, slot_width = clear_circle(slot)
    if slot_width >= entry - 1.0:
        return None
    # the slot's direction runs from the entry's centre through the slot's own centre: towards its farthest
    # point instead, a square-ended slot reads as tilted towards one corner (Sonnet's in pilot-estoa, by 11 degrees)
    origin = np.array([centre.x, centre.y])
    direction = np.array([slot.centroid.x, slot.centroid.y]) - origin
    direction /= np.linalg.norm(direction)
    reach = float(max((np.asarray(slot.exterior.coords) - origin) @ direction))
    return origin, entry, slot_width, direction, reach - slot_width / 2


def _lip(meshes, wall_z, point):
    """How thick the plastic is at a point on the back, from the wall."""
    probe = placed.box((point[0] - 0.3, point[1] - 0.3, wall_z - 1), (point[0] + 0.3, point[1] + 0.3, wall_z + 30))
    pieces = [piece for found in placed.plastic_in(meshes, probe) for piece in found.split(only_watertight=False)]
    touching = [piece for piece in pieces if piece.bounds[0][2] <= wall_z + 0.5]
    return max(piece.bounds[1][2] for piece in touching) - wall_z if touching else 0.0


def _keyhole_verdict(meshes, wall_z, found, entry: EntryLimits, slot_limits: SlotLimits, travel_limit, angle_limits: AngleLimits,
                     standoff, head=None) -> Verdict:
    """`head`, given only under an assumption: the wall screws' head size. The entry must then pass it and the
    slot must carry it clear of the entry, in place of the entry and run of the one keyhole that hung."""
    centre, entry_width, slot, direction, travel = found
    angle = float(np.degrees(np.arccos(np.clip(direction[1], -1, 1))))
    where = f"keyhole at ({centre[0]:.0f}, {centre[1]:.0f})"
    rest = centre + direction * travel
    side = np.array([-direction[1], direction[0]]) * (slot / 2 + 1.0)
    lip = max(_lip(meshes, wall_z, rest + side), _lip(meshes, wall_z, rest - side))
    failures = []
    if angle > angle_limits.fails_beyond:
        failures.append(f"its slot runs {angle:.0f} degrees from straight up, so the piece can't drop onto the screw")
    if entry_width < entry.fails_under - TOL:
        failures.append(f"its entry is {entry_width:.1f} mm, too small for a head the screws were bought at about 8 to 9 mm")
    if slot < slot_limits.fails_under - TOL:
        failures.append(f"its slot is {slot:.2f} mm, narrower than a #8 screw")
    if slot >= slot_limits.fails_from - TOL:
        failures.append(f"its slot is {slot:.1f} mm, too wide to hold a head of about 8 mm")
    if travel <= entry_width / 2:
        failures.append("the screw would rest inside the entry, not under the slot's lip")
    if lip >= standoff - TOL:
        failures.append(f"the plastic at its slot is {lip:.1f} mm thick, as far as the screws stand out of the wall")
    if head is not None and entry_width < head - TOL:
        failures.append(f"its entry is {entry_width:.1f} mm, smaller than a {head:g} mm head")
    if head is not None and travel < entry_width / 2 + head / 2 - TOL:
        failures.append(f"its slot runs {travel:.1f} mm, short of the {entry_width / 2 + head / 2:.1f} that carries "
                        f"a {head:g} mm head clear of the entry")
    if failures:
        return Verdict(False, f"{where}: {'; '.join(failures)}")
    sizes = f"entry {entry_width:.1f}, slot {slot:.2f} running {travel:.1f} mm, {angle:.0f} degrees from up"
    unsure = []
    if angle > angle_limits.passes_within:
        unsure.append("its slot leans from straight up more than any that hung")
    if head is None and entry_width < entry.passes_from - TOL:
        unsure.append("its entry is smaller than the one that hung")
    low, high = slot_limits.passes
    if not low - TOL <= slot <= high + TOL:
        unsure.append("its slot is outside the range estimated from the one that hung")
    if head is None and travel < travel_limit - TOL:
        unsure.append("its slot is shorter than the one that hung")
    if unsure:
        return Verdict(None, f"{where} ({sizes}): {'; '.join(unsure)}")
    return Verdict(True, f"{where}: {sizes}")


@_readable
def keyholes(sub, built, entry, slot, travel, angle, standoff, count, at_depth, head=None):
    """The piece hangs on the wall screws: keyholes in its back whose slots run up from entries that pass
    the screws' heads, narrow enough to hold them, in plastic thinner than the screws stand out."""
    piece, why = placed.piece(sub, built)
    if piece is None:
        return Verdict(None, why)
    wall_z = piece.wall_z
    back = placed.section(piece.meshes, wall_z + at_depth)
    holes = [Polygon(ring) for polygon in back for ring in polygon.interiors]
    if not holes:
        return Verdict(False, "nothing in the back for the wall screws to go through")
    found = [keyhole for keyhole in (_keyhole(hole) for hole in holes) if keyhole is not None]
    if len(found) < count:
        return Verdict(None, f"{len(found)} keyhole(s) found in the back, and this check reads only keyholes")
    entry, slot, angle = EntryLimits.model_validate(entry), SlotLimits.model_validate(slot), AngleLimits.model_validate(angle)
    return _worst([_keyhole_verdict(piece.meshes, wall_z, keyhole, entry, slot, travel, angle, standoff, head) for keyhole in found])


@_readable
def nothing_proud(sub, built, tolerance):
    """No screw head or tip stands out of the back, where it would catch on the wall screws or the wall."""
    piece, why = placed.piece(sub, built)
    if piece is None:
        return Verdict(None, why)
    wall_z = piece.wall_z
    # a screw standing in one of the back's keyholes is a wall screw: it belongs in the wall (GPT 6.1 Sol t2 in
    # pilot-estoa declared its two, and they were once read as standing 17 mm out of the back)
    keyholes = [hole for polygon in placed.section(piece.meshes, wall_z + 0.3) for ring in polygon.interiors
                if _keyhole(hole := Polygon(ring)) is not None]
    proud = []
    for screw in piece.screws:
        if any(hole.buffer(0.5).contains(Point(screw.head[0], screw.head[1])) for hole in keyholes):
            continue
        tilt = np.sqrt(max(0.0, 1 - screw.direction[2] ** 2))
        head_low = min(screw.head[2], screw.head[2] - screw.head_h * screw.direction[2]) - screw.head_d / 2 * tilt
        lowest = min(head_low, screw.tip[2])
        if lowest < wall_z - tolerance:
            proud.append(f"a {screw.item} screw stands {wall_z - lowest:.2f} mm out of the back")
    if proud:
        return Verdict(False, "; ".join(proud))
    held = len(piece.screws) - sum(any(hole.buffer(0.5).contains(Point(screw.head[0], screw.head[1])) for hole in keyholes)
                                   for screw in piece.screws)
    return Verdict(True, f"none of the {held} screws that hold the box stands out of the back")
