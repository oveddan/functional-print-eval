"""The coupon loop (docs/coupon-loop.md): replay a saved trial with one more turn, in which the
person reports how the model's test coupons came out, then grade the revised design.

The report comes from recorded prints only. Nut pockets and bearing seats get an answer only at a
size that was printed, in Dan's own words from the coupon records. A holed roof gets the bridge
check's prediction, worded as the tangled cell H was recorded; each line says what it rests on, so
the results can mark it as a prediction. Anything else gets "I can't tell you how that came out".
A control arm gets a neutral second turn instead, so a gain from the report can be told apart from
a second look.

The tripod sample (docs/coupon-loop.md, "Tripod sample") also prints the final plate, as Dan did with the
Arca plate: the report says whether it fits the clamp (only at the 38 mm width that was printed), whether the
bolt's head fits its recess (the 13 mm recess that didn't and the 15 x 5 mm one that did) and, for a holed roof,
the bridge check's prediction. It never names a cause or a fix.

A design is graded with its coupons left out: once the coupon has been printed, its credit in
nut.fit and wheel.fit no longer applies, and the final part has to land on a size that held. The
saved turn 1 design is graded the same way, so the three grades share one rule.
"""
import math
import re
import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, Field
from shapely.geometry import Polygon

from pbe.graders import assumed, nuts, requirements, wheel
from pbe.graders.bridges import is_holed_roof, overhangs
from pbe.graders.sections import clear_circle, clear_width, holes_by_layer, section_at
from pbe.parts import catalog
from pbe.runner import agent, llm
from pbe.runner.measure import Person
from pbe.runner.trial_record import CheckResult, Measurement, ModelCall, Saved

ROOT = Path(__file__).resolve().parents[2]
FILE_NAME = "loop.json"  # not grades.json, so tools that read every trial record skip these
SEAT_LAYER = 0.2  # mm: the slice height for reading seats on a coupon
MIN_SEAT_DEPTH = 1.0  # mm: shallower than this is a chamfer, not a seat
ROOF_NOTE = "loose loops and tangles around the hole; hole partly closed"  # coupon A, cell H, round 1
CANT_TELL = "I can't tell you how that one came out."
ENDING = "Send me the design again with submit_design, changed or unchanged. I'll print the final part from what you send."
NEUTRAL = "Before I print anything, take another look at your design. " + ENDING
PRINTED_ENDING = "Send me the design again with submit_design, changed or unchanged, and I'll print it again from what you send."
PRINTED_PLATE_MM = 38.0  # the one plate width that was printed and fit the clamp (tasks/tripod-plate/brief.md)
PRINTED_WIDTH_TOL = 0.5  # mm: a plate this close to 38 reads as the printed width

# "tighter than a record": smaller than the tightest size printed, which wouldn't take the nut or bearing,
# so it won't either. The checks already read it that way (nuts.verdict, wheel._holds).
Basis = Literal["coupon B record", "coupon E record", "tighter than a record", "bridge check prediction", "no record", "build error",
                "tripod plate record", "Estoa record", "Dan's calipers", "geometry"]
Arm = Literal["baseline", "feedback", "neutral"]


@dataclass
class ReportLine:
    """One thing the person says about a coupon, and what it rests on."""
    text: str
    basis: Basis


# --- what the coupon prints recorded -------------------------------------------------------------

class NotedPocket(BaseModel):
    """A pocket printed on coupon B, with Dan's note on what the nut did."""
    label: str
    clearance: float
    outcome: str
    notes: str = ""

    @property
    def said(self) -> str:
        return self.notes.removeprefix("Dan: ").strip()


class NotedPockets(BaseModel):
    pockets: list[NotedPocket]


class RoundOne(BaseModel):
    B_nuts: NotedPockets


class PrintedSeat(BaseModel):
    """A 608 seat printed on coupon E. Its outcome is Dan's own words."""
    seat_d: float
    outcome: str


class BearingCoupon(BaseModel):
    seats: list[PrintedSeat] = Field(alias="608_seats")


class RoundTwo(BaseModel):
    E_splines_bearings: BearingCoupon


def _predictions(name):
    return yaml.safe_load((ROOT / "results/predictions" / name).read_text())


@cache
def printed_pockets() -> list[NotedPocket]:
    return RoundOne.model_validate(_predictions("round1-coupons.yaml")).B_nuts.pockets


@cache
def printed_seats() -> list[PrintedSeat]:
    return RoundTwo.model_validate(_predictions("round2-coupons.yaml")).E_splines_bearings.seats


# --- reading a coupon ------------------------------------------------------------------------------

def _requirement_args(task, grader):
    return next((requirement.args for requirement in task.requirements if requirement.grader == grader), None)


def _pocket_line(found, af, label) -> ReportLine:
    """What the person says about one pocket: what coupon B's pocket at that size did, or, within the assumption
    tolerance (graders/assumed.py), what the nearest printed pocket did."""
    size = f"{found.across:.2f} mm pocket"
    if not found.plain:  # coupon B only printed plain hexagons; crush ribs or clips are a different thing
        return ReportLine(f"{size}: {CANT_TELL}", "no record")
    clearance = found.across - af
    outcome, assumed_from = nuts.reading(label, clearance)
    if outcome is None:
        return ReportLine(f"{size}: {CANT_TELL}", "no record")
    if assumed_from is None:
        printed = [pocket for pocket in printed_pockets() if pocket.label == label and abs(clearance - pocket.clearance) <= nuts.TOL]
        if not printed:  # settled by the trend: tighter than one that wouldn't go in, or looser than a loose one
            return ReportLine(f"{size}: {outcome}.", "tighter than a record")
        said = printed[0].said
        outcome = printed[0].outcome  # Dan's own coding for that pocket: "holds" only where he turned it over
    else:
        nearest = next(pocket for pocket in printed_pockets() if pocket.label == label and abs(pocket.clearance - assumed_from) <= nuts.TOL)
        size = f"{found.across:.2f} mm pocket (I printed {af + nearest.clearance:.2f} mm, the nearest size)"
        said = nearest.said
    if outcome == "holds":
        return ReportLine(f"{size}: {said}. The nut stayed in when I turned it over and shook it.", "coupon B record")
    return ReportLine(f"{size}: {said}.", "coupon B record")


def nut_lines(mesh, nut, label) -> list[ReportLine]:
    af = catalog.resolve(nut)["af"]
    found = sorted(nuts.find_pockets(mesh, af), key=lambda pocket: pocket.across)
    return [_pocket_line(pocket, af, label) for pocket in found]


@dataclass
class CouponSeat:
    across: float  # the middle of its clear widths over its depth
    plain: bool  # a plain round seat, the only kind coupon E printed


def seats_on(mesh, seat_range) -> list[CouponSeat]:
    """Seat-sized round holes along z, one per position. A coupon seat often has a floor, so this
    doesn't need a hole through the whole part, as the wheel's own reader does."""
    layer_h, layers = holes_by_layer(mesh, 2, SEAT_LAYER)
    by_position = {}
    for found in layers:
        for hole in found:
            width = clear_width(hole)
            if not seat_range[0] <= width <= seat_range[1]:
                continue
            position = (round(hole.centroid.x), round(hole.centroid.y))
            plain = hole.area <= wheel.PLAIN * math.pi * width * width / 4
            by_position.setdefault(position, []).append((width, plain))
    seats = []
    for rows in by_position.values():
        if len(rows) * layer_h < MIN_SEAT_DEPTH:
            continue
        widths = sorted(width for width, _ in rows)
        seats.append(CouponSeat(across=widths[len(widths) // 2], plain=all(plain for _, plain in rows)))
    return sorted(seats, key=lambda seat: seat.across)


def _seat_line(seat: CouponSeat) -> ReportLine:
    """What coupon E's seat at that size did, or the nearest printed seat within the assumption tolerance."""
    size = f"{seat.across:.2f} mm seat"
    if not seat.plain:  # coupon E only printed plain round seats
        return ReportLine(f"{size}: {CANT_TELL}", "no record")
    printed = [printed for printed in printed_seats() if abs(seat.across - printed.seat_d) <= wheel.TOL]
    if printed:
        return ReportLine(f"{size}: {printed[0].outcome}.", "coupon E record")
    tightest = min(printed_seats(), key=lambda printed: printed.seat_d)
    if tightest.outcome == "won't go in" and seat.across < tightest.seat_d - wheel.TOL:
        return ReportLine(f"{size}: won't go in.", "tighter than a record")
    close = assumed.nearest(seat.across, [(printed.seat_d, printed) for printed in printed_seats()])
    if close:
        return ReportLine(f"{size} (I printed {close[0]:.2f} mm, the nearest size): {close[1].outcome}.", "coupon E record")
    return ReportLine(f"{size}: {CANT_TELL}", "no record")


def seat_lines(mesh, seat_range) -> list[ReportLine]:
    return [_seat_line(seat) for seat in seats_on(mesh, seat_range)]


def roof_lines(mesh) -> list[ReportLine]:
    """The bridge check's prediction for the piece's roofs: a roof with a hole through it in the words cell H was
    recorded in, a roof over air as loose strands, and every roof bridging as a clean print."""
    found = overhangs(mesh)
    failed = [overhang for overhang in found if not overhang.ok and not overhang.narrow]
    holed = [overhang for overhang in failed if len(overhang.region.interiors)]
    if holed:
        return [ReportLine(f"the roof over the pocket: {ROOF_NOTE}.", "bridge check prediction")]
    if failed:
        return [ReportLine(f"a roof about {failed[0].longest:.0f} mm across printed over air: loose strands hanging under it.",
                           "bridge check prediction")]
    return []


# --- Estoa's test pieces, answered from the same records the checks use (tasks/estoa-light/requirements.yaml) ---
DISK_HOLE_CENTRES = (33.2, 34.22)  # mm apart: Dan's calipers, 2 x 16.6 to 2 x 17.11 (30.2 between the holes' edges + 3.3)
DISK_SCREW_PLAY = 0.15  # mm a side: a 3.0 mm screw in the disk's 3.3 mm holes
USB_SEATED = (14.0, 8.5)  # the opening a plug seated through
USB_STOPPED_W = 11.5  # the opening width that stopped the plug's boot
KEYHOLE_HUNG = {"entry": 10.5, "slot": (4.5, 6.0), "travel": 12.0,  # the keyhole that hung the piece
                "entry_fails_under": 8.0, "slot_fails_under": 4.17}  # smaller than the heads bought; narrower than a #8 thread
WALL_SCREW_STANDOFF = 3.5  # mm the wall screws stand out
INSERT_HOLE = (4.3, 1.85)  # the hole inserts were set in, and the post wall that held at 20% infill
FLAT_PIECE = 6.0  # mm: a piece no thicker than this is read as a plate, so its thickness is the plastic at a keyhole
KEYHOLE_ENTRY = (7.0, 14.0)  # mm: an entry a #8 round head could be meant for
KEYHOLE_SLOT = (3.0, 7.5)  # mm: a slot a #8 screw could be meant to ride in


def _piece_holes(mesh):
    """The holes right through a flat test piece, at half its thickness: (hole, the plastic around it)."""
    axis = int(mesh.extents.argmin())
    middle = (mesh.bounds[0][axis] + mesh.bounds[1][axis]) / 2
    return [(Polygon(ring).buffer(0), polygon) for polygon in section_at(mesh, axis, middle) for ring in polygon.interiors], \
        float(mesh.extents[axis])


def _keyhole_line(found, thickness) -> ReportLine:
    """Against the keyhole that hung (10.5 mm entry, 4.5 to 6 mm slot, 12 mm run) and the limits the checks use."""
    _, entry, slot, _, travel = found
    tol = assumed.ASSUMED_WITHIN
    problems = []
    if entry < KEYHOLE_HUNG["entry_fails_under"] - tol:
        problems.append(f"the screw head doesn't go through the {entry:.1f} mm entry")
    if slot < KEYHOLE_HUNG["slot_fails_under"] - tol:
        problems.append(f"the {slot:.1f} mm slot is narrower than the screw")
    if WALL_SCREW_STANDOFF <= thickness <= FLAT_PIECE:  # a flat piece is that thick at its slot too
        problems.append(f"the plastic is {thickness:.1f} mm thick, more than the screw stands out of the wall, so the head can't hook behind it")
    if problems:
        return ReportLine(f"keyhole: {'; '.join(problems)}.", "Estoa record")
    low, high = KEYHOLE_HUNG["slot"]
    if entry >= KEYHOLE_HUNG["entry"] - tol and low - tol <= slot <= high + tol and travel >= KEYHOLE_HUNG["travel"] - tol:
        return ReportLine(f"keyhole: the screw head goes in the {entry:.1f} mm entry, slides up the {slot:.1f} mm slot and holds.",
                          "Estoa record")
    return ReportLine(f"keyhole: {CANT_TELL}", "no record")


def _usb_line(hole) -> ReportLine:
    """Against the 14 x 8.5 mm opening a plug seated through and the 11.5 mm one that stopped it, within the tolerance."""
    from pbe.graders.enclosure import _fits_somewhere, _stadium
    tol = assumed.ASSUMED_WITHIN
    if _fits_somewhere(_stadium(USB_SEATED[0] - tol, USB_SEATED[1] - tol).buffer(-0.01), hole):
        return ReportLine("the USB-C opening: the plug goes through and seats fully.", "Estoa record")
    if not _fits_somewhere(_stadium(USB_STOPPED_W + tol, USB_SEATED[1] - tol).buffer(-0.01), hole):
        return ReportLine("the USB-C opening: the plug's boot stops at it and the plug doesn't reach.", "Estoa record")
    return ReportLine(f"the USB-C opening: {CANT_TELL}", "no record")


def _insert_line(hole, plastic) -> ReportLine:
    """Against the 4.3 mm holes inserts were set in and the 1.85 mm walls that held, within the tolerance."""
    from pbe.graders.enclosure import _thinnest_wall
    _, width = clear_circle(hole)
    wall = _thinnest_wall(hole, plastic)
    tol = assumed.ASSUMED_WITHIN
    if abs(width - INSERT_HOLE[0]) <= tol and wall >= INSERT_HOLE[1] - tol:
        return ReportLine(f"the {width:.1f} mm insert hole: the insert went in straight and holds.", "Estoa record")
    return ReportLine(f"the {width:.1f} mm insert hole: {CANT_TELL}", "no record")


def _disk_hole_line(first, second) -> ReportLine:
    """Against Dan's caliper readings of the disk's holes, with the screws' play in them."""
    apart = first.centroid.distance(second.centroid)
    low, high = DISK_HOLE_CENTRES[0] - DISK_SCREW_PLAY * 2, DISK_HOLE_CENTRES[1] + DISK_SCREW_PLAY * 2
    if low <= apart <= high:
        return ReportLine(f"holes {apart:.1f} mm apart: I held it against the disk and both screws go through its holes.", "Dan's calipers")
    off = low - apart if apart < low else apart - high
    if off > assumed.ASSUMED_WITHIN:
        return ReportLine(f"holes {apart:.1f} mm apart: against the disk, they're about {off:.1f} mm off its holes, so both "
                          "screws won't go in.", "Dan's calipers")
    return ReportLine(f"holes {apart:.1f} mm apart: {CANT_TELL}", "no record")


def estoa_piece_lines(mesh) -> list[ReportLine]:
    """What the person says about an Estoa test piece: its keyholes, USB-C openings, insert holes and any pair of
    disk-screw holes, from the records the checks use."""
    from pbe.graders.enclosure import _keyhole
    holes, thickness = _piece_holes(mesh)
    lines, small = [], []
    for hole, plastic in holes:
        _, width = clear_circle(hole)
        length = max(hole.minimum_rotated_rectangle.exterior.length / 2 - width, width)
        found = _keyhole(hole)
        if found is not None and KEYHOLE_ENTRY[0] <= found[1] <= KEYHOLE_ENTRY[1] and KEYHOLE_SLOT[0] <= found[2] <= KEYHOLE_SLOT[1]:
            lines.append(_keyhole_line(found, thickness))
        elif 9.0 <= length <= 22.0 and 5.0 <= width <= 13.0 and length > width + 1.5:
            lines.append(_usb_line(hole))
        elif 3.9 <= width <= 4.9 and hole.area >= 0.8 * math.pi * width * width / 4:
            lines.append(_insert_line(hole, plastic))
        elif 2.4 <= width <= 3.7:
            small.append(hole)
    pairs = [(a, b) for i, a in enumerate(small) for b in small[i + 1:] if 25.0 <= a.centroid.distance(b.centroid) <= 45.0]
    if pairs:
        lines.append(_disk_hole_line(*min(pairs, key=lambda pair: abs(pair[0].centroid.distance(pair[1].centroid) - 33.7))))
    return lines


def coupon_lines(task, mesh) -> list[ReportLine]:
    lines = []
    nut = _requirement_args(task, "nut.fit")
    if nut:
        lines += nut_lines(mesh, nut["nut"], nut["label"])
    seat = _requirement_args(task, "wheel.fit")
    if seat:
        lines += seat_lines(mesh, seat["seat_range"])
    if task.id == "estoa-light":
        lines += estoa_piece_lines(mesh)
    lines += roof_lines(mesh)
    return lines or [ReportLine("it printed cleanly, but there's nothing on it I've printed before to tell you more.",
                                "bridge check prediction")]


def coupon_report(task, sub, built) -> dict[str, list[ReportLine]]:
    """The person's report on each test coupon, by part id."""
    report = {}
    for part in sub.parts:
        if part.role != "coupon":
            continue
        built_part = built.get(part.id)
        if built_part is None or not built_part.ok:
            report[part.id] = [ReportLine("it didn't come out: the file wouldn't open.", "build error")]
        else:
            report[part.id] = coupon_lines(task, built_part.mesh)
    return report


def printed_parts_report(task, sub, built) -> dict[str, list[ReportLine]]:
    """The person's report on every part they printed, test prints and final parts alike (the loop on every trial,
    `loop-all`): the same readings as a coupon's, a pocket's fit, a seat's fit and a holed roof, taken on each part."""
    report = {}
    for part in sub.parts:
        built_part = built.get(part.id)
        if built_part is None or not built_part.ok:
            report[part.id] = [ReportLine("it didn't come out: the file wouldn't open.", "build error")]
        else:
            report[part.id] = coupon_lines(task, built_part.mesh)
    return report


# --- printing the final plate (the tripod sample) ---------------------------------------------------

def _finding(findings, check):
    return next((finding for finding in findings if finding.check == check), None)


def clamp_line(findings) -> ReportLine:
    """Fits the clamp only at the printed width; R2's 37 to 39 mm pass is an estimate, not a print."""
    fit = _finding(findings, "R2")
    width = re.match(r"([\d.]+) mm wide", fit.detail) if fit is not None else None
    if fit is not None and fit.ok is True and width and abs(float(width.group(1)) - PRINTED_PLATE_MM) <= PRINTED_WIDTH_TOL:
        return ReportLine("the clamp: it fits.", "tripod plate record")
    return ReportLine(f"the clamp: {CANT_TELL}", "no record")


def head_line(findings) -> ReportLine:
    """R4 reads the recess against the two that were printed: 13 mm didn't take the head, 15 x 5 mm did."""
    recess = _finding(findings, "R4")
    if recess is not None and recess.ok is True:
        return ReportLine("the bolt's head: it fits in its recess.", "tripod plate record")
    if recess is not None and recess.ok is False:
        return ReportLine("the bolt's head: it didn't fit in its recess.", "tripod plate record")
    return ReportLine(f"the bolt's head: {CANT_TELL}", "no record")


def holed_roof_line(mesh) -> list[ReportLine]:
    if not any(is_holed_roof(found) for found in overhangs(mesh)):
        return []
    return [ReportLine(f"the roof the hole goes through: {ROOF_NOTE}.", "bridge check prediction")]


def plate_report(task, sub, built) -> dict[str, list[ReportLine]]:
    """The person's report on the final part(s), once printed: the clamp, the bolt's head and a holed roof."""
    finals = [part for part in sub.parts if part.role == "final"]
    if any(built.get(part.id) is None or not built[part.id].ok for part in finals):
        return {", ".join(part.id for part in finals): [ReportLine("it didn't come out: the file wouldn't open.", "build error")]}
    findings = requirements.grade(task, without_coupons(sub), {part.id: built[part.id] for part in finals})
    lines = [clamp_line(findings), head_line(findings)]
    for part in finals:
        lines += holed_roof_line(built[part.id].mesh)
    return {", ".join(part.id for part in finals): lines}


# --- printing and putting together the Estoa box (the Estoa sample) ----------------------------------

# What the person sees, by check and by the reason the check gave, for each failure on the records. Each says what
# happened, never why or how to fix it, and names what it rests on: an Estoa record, Dan's readings, or plain
# geometry a person would see on putting it together (docs/coupon-loop.md, "Estoa sample").
ESTOA_LINES = {
    "R1": [("", "the disk: its screws don't line up with the holes in the box.", "Dan's calipers")],
    "R2": [("bottoms out", "the disk's screws: they hit the bottom of their holes before they tighten, so the disk stays loose.",
            "Estoa record"),
           ("comes out of the back", "the disk's screws: their tips come out of the back.", "geometry"),
           ("into the ESP32", "the disk's screws: they run into the ESP32.", "geometry"),
           ("of plastic around its thread", "the disk's screws: they strip out of the plastic.", "Estoa record"),
           ("", "the disk's screws: they don't hold the disk; there's nothing for them to bite into.", "geometry")],
    "R3": [("isn't inside the box", "the ESP32: the box doesn't close around it.", "geometry"),
           ("right in front of the socket", "the charger: the opening in the box doesn't line up with the ESP32's port; "
            "there's plastic in front of it.", "geometry"),
           ("where the socket itself is", "the ESP32: it won't sit where the box puts it; the plastic runs into its USB port.",
            "geometry"),
           ("", "the charger: the plug's head doesn't fit through the opening, so it can't get far enough in to connect "
            "to the ESP32.", "Estoa record")],
    "R4": [("", "the inserts: the posts around them softened and bulged as I pressed them in, and the inserts sit crooked.",
            "Estoa record")],
    "R5": [("isn't inside the box", "the perfboard: the box doesn't close around it.", "geometry"),
           ("", "the perfboard: it doesn't fit in the box.", "geometry")],
    "R6": [("from straight up", "hanging it: it won't drop onto the wall screws.", "geometry"),
           ("its entry is", "hanging it: the screw heads don't go into the keyholes.", "geometry"),
           ("too wide to hold", "hanging it: the screw heads pull straight through the slots.", "geometry"),
           ("narrower than a #8", "hanging it: the screws don't fit in the slots.", "geometry"),
           ("as far as the screws stand out", "hanging it: the screw heads don't fit behind the slots.", "geometry"),
           ("rest inside the entry", "hanging it: it slips off the wall screws.", "geometry"),
           ("nothing in the back", "hanging it: there's nothing on the back to hang it by.", "geometry"),
           ("", "hanging it: it won't hang on the wall screws.", "geometry")],
    "R7": [("", "the back: screw heads stick out of it, so it won't sit flat on the wall.", "Estoa record")],
}


def estoa_lines(findings, parts_dir: Path) -> list[ReportLine]:
    """The person's report on the Estoa box once printed and put together: one line per thing that went wrong on
    the records. A check no record decides gets no line, and neither does one that passed."""
    lines = []
    for finding in findings:
        if finding.ok is not False or finding.test_print:
            continue
        if finding.check == "builds":
            lines.append(ReportLine(f"{finding.part}: it didn't come out: the file wouldn't open.", "build error"))
        elif finding.check == "connected_bodies":
            lines.append(ReportLine(f"{finding.part}: it came off the bed in separate pieces.", "geometry"))
        elif finding.check == "bridges":
            mesh_path = parts_dir / f"{finding.part}.stl"
            holed = mesh_path.exists() and any(is_holed_roof(found) for found in overhangs(trimesh_load(mesh_path)))
            height = re.search(r"first at z = (-?[\d.]+) mm", finding.detail)
            where = f"about {float(height.group(1)):.0f} mm up" if height else "partway up"
            text = (f"{finding.part}: the roof the hole goes through: {ROOF_NOTE}." if holed
                    else f"{finding.part}: the overhang {where} printed with loose, sagging loops under it.")
            lines.append(ReportLine(text, "bridge check prediction"))
        elif finding.check in ESTOA_LINES:
            for words in finding.detail.split("; "):
                text, basis = next((text, basis) for match, text, basis in ESTOA_LINES[finding.check] if match in words)
                if all(line.text != text for line in lines):
                    lines.append(ReportLine(text, basis))
    return lines


def trimesh_load(path):
    import trimesh
    return trimesh.load(path, force="mesh")


def estoa_report(findings, parts_dir: Path) -> dict[str, list[ReportLine]]:
    return {"the light": estoa_lines(findings, parts_dir)}


def printed_text(report: dict[str, list[ReportLine]]) -> str:
    """What the person says after printing everything in the design, coupons and final part alike."""
    blocks = [f"{part_id}:\n" + "\n".join(f"- {line.text}" for line in lines) for part_id, lines in report.items()]
    return "I printed what you sent. Here's how it came out:\n" + "\n".join(blocks) + "\n\n" + PRINTED_ENDING


def feedback_text(report: dict[str, list[ReportLine]]) -> str:
    blocks = [f"{part_id}:\n" + "\n".join(f"- {line.text}" for line in lines) for part_id, lines in report.items()]
    several = len(report) > 1
    opening = f"I printed the test coupon{'s' if several else ''} first. Here's how {'they' if several else 'it'} came out:"
    return opening + "\n" + "\n".join(blocks) + "\n\n" + ENDING


# --- the second turn ------------------------------------------------------------------------------

SUBMIT_PLEASE = "Please use submit_design to send me the design."
SECOND_TURN_CALLS = 8  # as many as a whole first turn gets (pbe/eval.py --max-turns)
TurnOutcome = Literal["submitted", "no_submission", "token_limit", "error"]


@dataclass
class SecondTurn:
    outcome: TurnOutcome
    error: str | None
    messages: list[dict]  # only the ones this turn added
    submission: object  # a Submission, or None
    calls: list[ModelCall]
    repairs: int
    measures: list[Measurement]  # anything the model asked the person to measure in this turn
    elapsed_s: float


def turn_outcome(error, submission, calls) -> TurnOutcome:
    """As a first turn's outcome, except that no design after every call stopped at the token limit is the
    limit stopping the model, not a design it chose: token_limit, reported apart from pass and fail."""
    if error is None and submission is None and calls and all(call.finish_reason == "length" for call in calls):
        return "token_limit"
    return agent.outcome_of(error, submission)


def facts_as_saved(task, hidden):
    """The task's facts cut to the measurements a saved trial's person had (its record's `hidden`), so a
    replay answers as turn 1 did even after a fact is added to the task, such as the clamp's width."""
    facts = {}
    for name, thing in (task.hidden_facts or {}).items():
        kept = {key: value for key, value in thing.get("measurements", {}).items() if f"{name}.{key}" in hidden}
        if kept:
            facts[name] = {**thing, "measurements": kept}
    return facts


def second_turn(task, model, saved_messages, text, max_turns=SECOND_TURN_CALLS, max_tokens=32000, chat=llm.chat,
                condition="can_ask", python=None, facts=None) -> SecondTurn:
    """Continue a saved conversation with one message from the person, until the model resubmits. A
    can_run_code trial keeps run_python (python: its PythonTool) and the tools it had in turn 1. facts:
    what the person knows (facts_as_saved for a replay); the task's current facts if None."""
    person = Person(task.hidden_facts if facts is None else facts)
    trial_tools = agent.TrialTools(task, person, python)
    added = [{"role": "user", "content": text}]
    calls, error = [], None
    started = time.monotonic()
    for _ in range(max_turns):
        try:
            response = chat(model, [*saved_messages, *added], tools=agent.tools(condition, task.format.assembly),
                            max_tokens=max_tokens)
        except llm.LLMError as e:
            error = str(e)
            break
        reply = llm.Reply.model_validate(response)
        calls.append(ModelCall.from_reply(reply))
        added.append(agent.as_sent_back(reply.message))
        if not reply.tool_calls:
            added.append({"role": "user", "content": SUBMIT_PLEASE})
            continue
        added += agent.answers_to(reply, trial_tools)
        if trial_tools.submission is not None:
            break
    return SecondTurn(outcome=turn_outcome(error, trial_tools.submission, calls), error=error, messages=added,
                      submission=trial_tools.submission, calls=calls, repairs=trial_tools.repairs, measures=person.log,
                      elapsed_s=round(time.monotonic() - started, 1))


# --- grading and the record -----------------------------------------------------------------------

def without_coupons(sub):
    """The design with its coupons left out, for grading once the coupons have been printed."""
    return sub.model_copy(update={"parts": [part for part in sub.parts if part.role != "coupon"]})


def grade(task, sub, out_dir):
    return agent.grade(task, without_coupons(sub), out_dir)


def passed(findings) -> bool:
    return bool(findings) and all(finding.ok is True for finding in findings)


class SavedLine(Saved):
    text: str
    basis: Basis


class LoopRecord(Saved):
    """One arm of one replayed trial, saved as loop.json."""
    task: str
    model: str
    arm: Arm
    replayed: str  # the saved trial's folder, under results/runs
    outcome: Literal["submitted", "no_submission", "token_limit", "error", "saved"]  # saved: the baseline, turn 1 as it was
    error: str | None = None
    turns: int = 0
    repairs: int = 0
    measures: list[Measurement] = []
    cost_usd: float = 0.0
    elapsed_s: float = 0.0
    calls: list[ModelCall] = []
    reply: str | None = None  # what the person said in the second turn
    report: dict[str, list[SavedLine]] = {}  # the feedback arm's report, line by line, with what each rests on
    findings: list[CheckResult] = []
    all_pass: bool = False
    date: str = ""
    commit: str = ""
    platform: str | None = None

    @classmethod
    def load(cls, folder: Path) -> Self:
        return cls.model_validate_json((folder / FILE_NAME).read_text())

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / FILE_NAME).write_text(self.model_dump_json(indent=1))

    def set_verdict(self, findings) -> None:
        self.findings = [CheckResult.from_finding(finding) for finding in findings]
        self.all_pass = passed(findings)

    def summary(self) -> str:
        """pass, fail and the checks, not graded and the checks, or what stopped the turn."""
        if not self.findings:
            return self.outcome
        if self.all_pass:
            return "pass"
        failed = [result.check for result in self.findings if result.ok is False]
        if failed:
            return "fail " + " ".join(failed)
        return "not graded " + " ".join(result.check for result in self.findings if result.ok is None)


def saved_report(report: dict[str, list[ReportLine]]) -> dict[str, list[SavedLine]]:
    return {part_id: [SavedLine(text=line.text, basis=line.basis) for line in lines] for part_id, lines in report.items()}
