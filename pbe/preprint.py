"""The pre-print check: run the eval's checks on a design before anything is printed.

    uv run python -m pbe.preprint results/local/live/<session>/.../submission.yaml    # the agent's hand-in
    uv run python -m pbe.preprint knob.stl --nut M5                                   # a part exported from any CAD tool
    uv run python -m pbe.preprint wheel.step --bearing 608

It takes the agent's hand-in (a submission, or a trial folder holding one) or an exported STL or STEP file, so a
part modeled in OpenSCAD or anything else can be checked. A mesh is read as it sits in its file: z up, in mm,
its lowest point on the bed.

Each prediction names the recorded print it rests on, or says nothing recorded is near, which is "not graded"
and never a pass. It predicts from the design's geometry and the recorded prints. It is not a print simulation.
"""
import argparse
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import trimesh
from pydantic import ValidationError

from pbe.graders import assumed, checks, nuts, requirements, wheel
from pbe.graders.bridges import is_holed_roof, overhangs
from pbe.graders.checks import verdict_word
from pbe.parts import catalog, submission
from pbe.parts.build import Built, build_parts
from pbe.parts.printer import printer
from pbe.parts.submission import Submission
from pbe.runner import coupon_loop, tasks
from pbe.runner.tasks import Task

MESH_SUFFIXES = (".stl", ".step", ".stp")
NOTHING_NEAR = "nothing recorded is near"
GEOMETRY = "geometry alone; no print is needed to decide it"
NOT_A_SIMULATION = (
    "This predicts from the design's geometry and the prints recorded on one setup ({printer}, {filament}, "
    "{layer} mm layers). It is not a print simulation: warping, bed adhesion, stringing and strength aren't predicted.")
READ_FROM_A_SHAPE = ("Read from the shape: one body, bed fit and bridges; hex pockets along z for the nuts you name with "
                     "--nut or the hand-in's hardware lists ({nuts}); 608 seats along z with --bearing 608 or a 608 in the "
                     "hardware. Nothing else is checked: whether it fits what it's for, bolt reach and assembly need the "
                     "agent's hand-in for one of the eval's tasks.")
# the nut sizes test print B recorded, by its labels, and the catalog nut each is
NUT_REFS = {"M3": "ISO 4032 M3", "M5": "ISO 4032 M5", "M8": "ISO 4032 M8", "Q": "ASME B18.2.2 1/4-20"}
BEARINGS = ("608",)  # the bearing whose seats were test-printed
SEAT_RANGE_608 = (20.0, 26.0)  # mm: a round hole this wide is read as a 608's seat, as tasks/bearing-wheel does


@dataclass
class Prediction:
    """One check's answer for one part, and what it rests on."""
    check: str
    part: str
    ok: bool | None  # None: not graded, which is never a pass
    detail: str
    basis: str  # the recorded print or fact behind it, or NOTHING_NEAR


@dataclass
class Design:
    """What's being checked: built parts, and the hand-in they came from, if there was one."""
    name: str
    built: dict[str, Built]
    sub: Submission | None = None  # None: a mesh file
    task: Task | None = None  # the hand-in's task, if it's one of the eval's


class NotADesign(ValueError):
    """A path the pre-print check can't read as a hand-in or a mesh."""


# --- loading ---------------------------------------------------------------------------------------

def _step_mesh(path: Path) -> trimesh.Trimesh:
    """A STEP file's shape as a mesh, at the tolerance the eval exports its own parts with."""
    import cadquery as cq  # slow to import, and an STL doesn't need it
    shape = cq.importers.importStep(str(path))
    with tempfile.TemporaryDirectory() as tmp:
        stl = Path(tmp) / "part.stl"
        cq.exporters.export(shape, str(stl), tolerance=0.01, angularTolerance=0.1)
        return trimesh.load(stl, force="mesh")


def mesh_part(path: Path) -> Built:
    """An exported file as one built part, named after the file."""
    try:
        mesh = _step_mesh(path) if path.suffix.lower() in (".step", ".stp") else trimesh.load(path, force="mesh")
    except Exception as e:  # whatever a CAD tool wrote may not be readable
        return Built(part_id=path.stem, ok=False, error=f"can't be read as a mesh: {type(e).__name__}: {e}", role="final")
    if not len(mesh.faces):
        return Built(part_id=path.stem, ok=False, error="the file holds no shape", role="final")
    return Built(part_id=path.stem, ok=True, stl=path, mesh=mesh, role="final")


def _own_task(sub: Submission) -> Task | None:
    """The eval task a hand-in answers, or None for someone's own request or a task this repo doesn't have."""
    try:
        return tasks.load(sub.task)
    except (OSError, ValueError, KeyError):
        return None


def _read_built(part, parts_dir: Path) -> Built | None:
    """A part's STL as an earlier build left it in parts_dir, or None if it isn't there or can't be read."""
    stl = parts_dir / f"{part.id}.stl"
    if not stl.exists():
        return None
    try:
        return Built(part_id=part.id, ok=True, stl=stl, mesh=trimesh.load(stl, force="mesh"), role=part.role)
    except Exception:  # then it's built again
        return None


def _built(sub: Submission, out_dir: Path, built_in: Path | None) -> dict[str, Built]:
    """Every part built, in the hand-in's order. Parts an earlier build of this same hand-in left in `built_in`
    are read from there, and only the rest are built."""
    found = {part.id: _read_built(part, built_in) for part in sub.parts} if built_in else {}
    missing = [part for part in sub.parts if found.get(part.id) is None]
    fresh = build_parts(sub.model_copy(update={"parts": missing}), out_dir) if missing else {}
    return {part.id: found.get(part.id) or fresh[part.id] for part in sub.parts}


def load_hand_in(path: Path, out_dir: Path, built_in: Path | None = None) -> Design:
    path = path / "submission.yaml" if path.is_dir() else path
    try:
        sub = submission.load(path)
    except (OSError, ValidationError) as e:
        raise NotADesign(f"{path} isn't a hand-in the checks can read:\n{e}") from None
    return Design(name=str(path), built=_built(sub, out_dir, built_in), sub=sub, task=_own_task(sub))


def load_design(path, out_dir, built_in: Path | None = None) -> Design:
    """A hand-in (a submission file, or a folder holding submission.yaml) or one exported STL or STEP file."""
    path = Path(path)
    if path.suffix.lower() in MESH_SUFFIXES:
        if not path.exists():
            raise NotADesign(f"{path} doesn't exist")
        part = mesh_part(path)
        return Design(name=str(path), built={part.part_id: part})
    return load_hand_in(path, Path(out_dir), built_in)


# --- the general checks ----------------------------------------------------------------------------

def _bed_basis() -> str:
    return "the printer's build volume (catalog/printer.yaml); the slicer's edge zones aren't measured"


def _from_finding(finding: checks.Finding, basis: str) -> Prediction:
    return Prediction(finding.check, finding.part, finding.ok, finding.detail, basis)


RECORDED_ROOFS = "catalog/printer.yaml, bridging"


def _bridge_basis(ok, found, supports) -> str:
    """Which prints a part's bridging verdict rests on."""
    if ok is None:
        return NOTHING_NEAR
    if ok and supports and any(not overhang.ok for overhang in found):
        return "the design's own instruction to print this part with supports; no print is behind it"
    if ok:
        return f"the roofs recorded as printing clean, up to {printer().bridging.max_span_mm} mm ({RECORDED_ROOFS})"
    if any(is_holed_roof(overhang) for overhang in found):
        return "the Arca plate's first roof and test print A's cell H: roofs with a hole through them, which tangled"
    return (f"the strand rule, set from the roofs recorded as failing ({RECORDED_ROOFS}): a strand needs solid at both "
            "ends, within the longest span seen to print clean")


def bridge_prediction(part: Built) -> Prediction:
    """The bridge check's verdict, as a trial gets it: a part the design says to print with supports passes."""
    found = overhangs(part.mesh)
    ok, detail = checks._with_declared_supports(*checks._bridging_verdict(found), part.supports)
    return Prediction("bridges", part.part_id, ok, detail, _bridge_basis(ok, found, part.supports))


def _guarded(check: str, part: Built, predict) -> list[Prediction]:
    """`predict`'s predictions for one part. If the check crashes on the part's geometry, which an exported mesh
    can make it do, that check is not graded for this part and the others still run."""
    try:
        return predict()
    except Exception as e:
        return [Prediction(check, part.part_id, None, f"the check couldn't read this shape: {type(e).__name__}: {e}",
                           "no prediction: the check crashed on this geometry")]


def _one_body(part: Built) -> list[Prediction]:
    return [_from_finding(finding, GEOMETRY) for finding in checks.connected_bodies({part.part_id: part})]


def _fits_bed(part: Built) -> list[Prediction]:
    return [_from_finding(finding, _bed_basis()) for finding in checks.bed_fit({part.part_id: part})]


def general_predictions(built: dict[str, Built]) -> list[Prediction]:
    """The checks every design gets: it builds, each part is one body, fits the bed and can be bridged."""
    predictions = [_from_finding(finding, GEOMETRY) for finding in checks.builds(built)]
    for part in built.values():
        if not part.ok:
            continue
        predictions += _guarded("connected_bodies", part, lambda: _one_body(part))
        predictions += _guarded("bed_fit", part, lambda: _fits_bed(part))
        predictions += _guarded("bridges", part, lambda: [bridge_prediction(part)])
    return predictions


# --- nut pockets and bearing seats, read from any shape --------------------------------------------

def _af(label: str) -> float:
    return catalog.resolve(NUT_REFS[label])["af"]


def _nearest_label(across: float, labels) -> str:
    return min(labels, key=lambda label: abs(across - _af(label)))


def _note_on(label, clearance) -> str:
    """Dan's note on test print B's pocket at this size, quoted, or "" if round 1 didn't print it."""
    printed = next((pocket for pocket in coupon_loop.printed_pockets()
                    if pocket.label == label and abs(pocket.clearance - clearance) <= nuts.TOL), None)
    return f' (test print B: "{printed.said}")' if printed else ""


def _pocket_basis(label, shape, clearance, outcome, assumed_from) -> str:
    """Which printed pockets of this nut and shape a reading rests on, as nuts.reading decided it."""
    if outcome is None:
        return NOTHING_NEAR
    kind = f"{label} {shape} pocket"
    if assumed_from is not None:
        return (f"the {kind} test-printed at {assumed_from:+.2f} mm, the nearest size printed "
                f"(within the {assumed.ASSUMED_WITHIN} mm assumption tolerance)")
    sizes = [printed for printed, _ in nuts._measured()[label, shape]]
    if any(abs(printed - clearance) <= nuts.TOL for printed in sizes):
        return f"the {kind} test-printed at {clearance:+.2f} mm" + (_note_on(label, clearance) if shape == "plain" else "")
    if clearance < min(sizes):
        return f"the {kind}s test-printed: this is tighter than the tightest of them, {min(sizes):+.2f} mm, which wouldn't go in"
    if clearance > max(sizes):
        return f"the {kind}s test-printed: this is looser than the loosest of them, {max(sizes):+.2f} mm, which was already loose"
    return f"the {kind}s test-printed either side of this size, which agree"


def _unreachable(found: nuts.Pocket) -> str | None:
    """Why no nut can be pressed into this pocket and stay, from its shape alone, as nuts.pocket reads it."""
    if not found.opens:
        return f"closed at z {found.z[0]:.1f} to {found.z[1]:.1f}: a nut can't be pressed in from either face"
    if len(found.opens) == 2:
        return "the hex runs right through: nothing stops the nut going out the far side"
    return None


def pocket_prediction(part_id: str, found: nuts.Pocket, label: str) -> Prediction:
    """Does the nut press in by hand and stay in upside down, by what the test-printed pockets of its shape did?"""
    af = _af(label)
    clearance = round(found.across - af, 3) or 0.0
    size = f"{label} nut pocket ({found.shape}) {found.across:.2f} mm across flats, {clearance:+.2f} over the {af} mm nut"
    if why := _unreachable(found):
        return Prediction("nut pocket", part_id, False, f"{size}: {why}", GEOMETRY)
    outcome, assumed_from = nuts.reading(label, clearance, found.shape)
    ok = nuts.SETTLES.get(outcome)
    said = outcome or "not measured"
    if outcome is not None and ok is None:
        said += " (that doesn't settle whether it stays in upside down)"
    return Prediction("nut pocket", part_id, ok, f"{size}: prints say {said}",
                      _pocket_basis(label, found.shape, clearance, outcome, assumed_from))


def pocket_predictions(part: Built, labels) -> list[Prediction]:
    """Every hex pocket along z about the size of one of the named nuts, each read as the nearest of them. Only
    named nuts are looked for: a bolt head's recess or a lightening cell is a hexagon too."""
    predictions = []
    for label in labels:
        for found in nuts.find_pockets(part.mesh, _af(label)):
            if _nearest_label(found.across, labels) == label:
                predictions.append(pocket_prediction(part.part_id, found, label))
    return predictions


def _features(part: Built, labels, bearing: bool) -> list[Prediction]:
    return pocket_predictions(part, labels) + (seat_predictions(part) if bearing else [])


def seat_limits() -> dict:
    """The seat sizes the wheel task grades a 608's fit with (tasks/bearing-wheel/requirements.yaml), so the check
    and the task can't drift apart: the widest seat that wouldn't take the bearing, the range that held it, and
    the size from which it fell out. Its brief says which test print each comes from."""
    fit = next(requirement for requirement in tasks.load("bearing-wheel").requirements if requirement.grader == "wheel.fit")
    return {name: fit.args[name] for name in ("too_tight", "holds", "too_loose")}


def seat_prediction(part_id: str, seat: coupon_loop.CouponSeat) -> Prediction:
    """Does a 608 press in and stay in, by what the printed 608 seats did?"""
    if not seat.plain:
        return Prediction("bearing seat", part_id, None, f"608 seat {seat.across:.2f} mm, with ribs, lobes or a slot: "
                          "no print has measured those", NOTHING_NEAR)
    limits = seat_limits()
    verdict = wheel._holds(seat.across, **limits)
    low, high = limits["holds"]
    basis = NOTHING_NEAR if verdict.ok is None else (
        f"the 608 seats test-printed: {limits['too_tight']} mm wouldn't take the bearing, {low} to {high} mm held it "
        f"upside down, and from {limits['too_loose']} mm it fell out")
    return Prediction("bearing seat", part_id, verdict.ok, f"608 seat {verdict.detail}", basis)


def seat_predictions(part: Built) -> list[Prediction]:
    return [seat_prediction(part.part_id, seat) for seat in coupon_loop.seats_on(part.mesh, SEAT_RANGE_608)]


def _lists_a_608(sub: Submission | None) -> bool:
    return sub is not None and any(item.ref.removesuffix("ZZ") == "608" for item in sub.hardware)


def nuts_listed(sub: Submission | None) -> tuple[str, ...]:
    """The recorded nut sizes a hand-in's hardware lists, by test print B's labels."""
    refs = {item.ref for item in sub.hardware} if sub is not None else set()
    return tuple(label for label, ref in NUT_REFS.items() if ref in refs)


def feature_predictions(design: Design, labels, bearing: bool) -> list[Prediction]:
    predictions = []
    labels = tuple(dict.fromkeys([*labels, *nuts_listed(design.sub)]))
    bearing = bearing or _lists_a_608(design.sub)
    for part in design.built.values():
        if part.ok:
            predictions += _guarded("nut pockets and bearing seats", part, lambda: _features(part, labels, bearing))
    return predictions


# --- a hand-in for one of the eval's tasks ---------------------------------------------------------

def requirement_predictions(design: Design) -> list[Prediction]:
    """The task's own requirements, on the final parts only. A design's test pieces earn no credit here, as in
    a can_test trial (agent.graded_design): before printing, the question is whether the part as drawn works, not
    whether a test print would find a size that does. Each detail names the print it was read against."""
    family = design.task.id.split("/")[0]
    basis = f"the record behind this requirement, named in tasks/{family}/requirements.yaml"
    findings = requirements.grade(design.task, coupon_loop.without_coupons(design.sub), design.built)
    return [Prediction(finding.check, finding.part, finding.ok, finding.detail, NOTHING_NEAR if finding.ok is None else basis)
            for finding in findings]


def predict(design: Design, labels=(), bearing=False) -> list[Prediction]:
    """Every prediction for a design. A hand-in for one of the eval's tasks gets that task's requirements; any
    other design gets the pockets of the nuts named in `labels` or its hardware, and its bearing seats, read from
    the shape."""
    predictions = general_predictions(design.built)
    if design.task is not None and design.task.requirements:
        return predictions + requirement_predictions(design)
    return predictions + feature_predictions(design, labels, bearing)


# --- the report ------------------------------------------------------------------------------------

def not_a_simulation() -> str:
    setup = printer()
    return NOT_A_SIMULATION.format(printer=setup.printer, filament=setup.eval_setup.filament, layer=setup.layer_mm)


def _lines(prediction: Prediction) -> list[str]:
    return [f"  {verdict_word(prediction.ok):10}  {prediction.check:16} {prediction.part:14} {prediction.detail}",
            f"  {'':10}  {'':16} {'':14} based on: {prediction.basis}"]


def counts(predictions) -> str:
    passed = sum(prediction.ok is True for prediction in predictions)
    failed = sum(prediction.ok is False for prediction in predictions)
    return f"{passed} pass, {failed} FAIL, {len(predictions) - passed - failed} not graded"


def report(design: Design, predictions: list[Prediction]) -> str:
    lines = [f"Pre-print check: {design.name}", not_a_simulation()]
    for prediction in predictions:
        lines += _lines(prediction)
    lines.append(counts(predictions) + ". \"not graded\" is not a pass: no recorded print decides it.")
    if design.task is not None and design.task.requirements:
        lines.append("The task's requirements are read on the final parts only: a test piece in the design earns no credit here.")
    else:
        lines.append(READ_FROM_A_SHAPE.format(nuts=", ".join("1/4-20" if label == "Q" else label for label in NUT_REFS)))
    return "\n".join(lines)


def any_failed(predictions) -> bool:
    return any(prediction.ok is False for prediction in predictions)


def check(path, labels=(), bearing=False, out_dir=None, built_in=None) -> tuple[Design, list[Prediction]]:
    """One design's predictions. Its built parts go in out_dir, or nowhere if none is given. `built_in` is a
    folder an earlier build of the same hand-in left its parts in, to read instead of building them again."""
    with tempfile.TemporaryDirectory() as tmp:
        design = load_design(path, out_dir if out_dir is not None else tmp, built_in)
        return design, predict(design, labels, bearing)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Predict how a design will print, from its geometry and the recorded prints. "
                                             "Not a print simulation.")
    ap.add_argument("paths", nargs="+", type=Path, help="the agent's hand-in (submission.yaml or its folder), or STL or STEP "
                                                        "files as oriented for printing, z up, in mm")
    ap.add_argument("--nut", action="append", choices=list(NUT_REFS), metavar="SIZE",
                    help=f"the nut a hex pocket is for ({', '.join(NUT_REFS)}; Q is 1/4-20); repeat for several. "
                         "A hand-in's hardware list names its own")
    ap.add_argument("--bearing", choices=BEARINGS, help="read round holes of about its size as this bearing's seats")
    ap.add_argument("--out", type=Path, help="keep a hand-in's built parts here, as STL")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    failed = False
    for number, path in enumerate(args.paths):
        try:
            out_dir = args.out / path.stem if args.out else None
            design, predictions = check(path, tuple(args.nut or ()), bool(args.bearing), out_dir)
        except NotADesign as e:
            print(e)
            failed = True
            continue
        print(("\n" if number else "") + report(design, predictions))
        failed |= any_failed(predictions)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
