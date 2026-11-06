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

from pbe.graders import nuts, requirements, wheel
from pbe.graders.bridges import is_holed_roof, overhangs
from pbe.graders.sections import clear_width, holes_by_layer
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
    size = f"{found.across:.2f} mm pocket"
    if not found.plain:  # coupon B only printed plain hexagons
        return ReportLine(f"{size}: {CANT_TELL}", "no record")
    clearance = found.across - af
    printed = [pocket for pocket in printed_pockets() if pocket.label == label and abs(clearance - pocket.clearance) <= nuts.TOL]
    if not printed:
        return _tighter_pocket_line(size, clearance, label)
    pocket = printed[0]
    if pocket.outcome == "holds":
        return ReportLine(f"{size}: {pocket.said}. The nut stayed in when I turned it over and shook it.", "coupon B record")
    return ReportLine(f"{size}: {pocket.said}.", "coupon B record")


def _tighter_pocket_line(size, clearance, label) -> ReportLine:
    """A pocket tighter than the tightest one printed, if that one wouldn't take the nut; else no answer."""
    tightest = min((pocket for pocket in printed_pockets() if pocket.label == label), key=lambda pocket: pocket.clearance)
    if tightest.outcome == "won't go in" and clearance < tightest.clearance - nuts.TOL:
        return ReportLine(f"{size}: won't go in.", "tighter than a record")
    return ReportLine(f"{size}: {CANT_TELL}", "no record")


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
    size = f"{seat.across:.2f} mm seat"
    if not seat.plain:  # coupon E only printed plain round seats
        return ReportLine(f"{size}: {CANT_TELL}", "no record")
    printed = [printed for printed in printed_seats() if abs(seat.across - printed.seat_d) <= wheel.TOL]
    if printed:
        return ReportLine(f"{size}: {printed[0].outcome}.", "coupon E record")
    tightest = min(printed_seats(), key=lambda printed: printed.seat_d)
    if tightest.outcome == "won't go in" and seat.across < tightest.seat_d - wheel.TOL:
        return ReportLine(f"{size}: won't go in.", "tighter than a record")
    return ReportLine(f"{size}: {CANT_TELL}", "no record")


def seat_lines(mesh, seat_range) -> list[ReportLine]:
    return [_seat_line(seat) for seat in seats_on(mesh, seat_range)]


def roof_lines(mesh) -> list[ReportLine]:
    """The bridge check's prediction for a roof with a hole through it, in the words cell H was recorded in."""
    holed = [found for found in overhangs(mesh) if not found.ok and not found.narrow and len(found.region.interiors)]
    if not holed:
        return []
    return [ReportLine(f"the roof over the pocket: {ROOF_NOTE}.", "bridge check prediction")]


def coupon_lines(task, mesh) -> list[ReportLine]:
    lines = []
    nut = _requirement_args(task, "nut.fit")
    if nut:
        lines += nut_lines(mesh, nut["nut"], nut["label"])
    seat = _requirement_args(task, "wheel.fit")
    if seat:
        lines += seat_lines(mesh, seat["seat_range"])
    lines += roof_lines(mesh)
    return lines or [ReportLine("I printed it, but I can't tell you how it came out.", "no record")]


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
