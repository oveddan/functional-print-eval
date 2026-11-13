"""The servo arm: the reference passes every check, each real mistake fails the check aimed at it and
no other, and cases between the records come back not graded (ok = None), which is never a pass.
servo-mount's tests cover R1 to R3; these cover the arm."""
import copy
import math

import numpy as np
import yaml

from helpers import checked, failed, grade, not_graded, not_passing

from pbe.graders import arm
from pbe.graders.checks import Verdict
from pbe.parts import submission
from pbe.runner import agent, measure, tasks

TASK = tasks.load("servo-arm")
REFERENCE = TASK.reference
SERVO_CHECKS = {"R1", "R2", "R3"}
ARM_CHECKS = {"R4", "R5", "R6", "R7"}


def design(plate=None, arm=None, hardware=None, extra_parts=(), **params):
    """The reference, changed only where a test says."""
    sub = submission.parse(REFERENCE)
    for name, value in params.items():
        sub.params[name].value = value
    if plate is not None:
        sub.parts[0].code = plate
    if arm is not None:
        sub.parts[1].code = arm
    if hardware is not None:
        sub.hardware = hardware
        ids = {entry.id for entry in hardware}
        for step in sub.manual:
            step.hardware = [item for item in step.hardware if item in ids]
        sub.criteria = [criterion for criterion in sub.criteria if criterion.hardware in ids | {None}]
    for part in extra_parts:
        sub.parts.append(submission.Part(**part))
    return checked(sub)


def result(findings, check):
    finding = next(finding for finding in findings if finding.check == check)
    return finding.ok, finding.detail


def arm_checks(findings):
    return {check: result(findings, check)[0] for check in sorted(ARM_CHECKS)}


def disc_plate(posts=(), low=0.0, high=0.0):
    """The reference plate as a 60 mm radius disc, with posts `low` below and `high` above it at each
    angle in `posts`, 50 mm from the disc's middle."""
    code = REFERENCE_PLATE.replace(
        'plate = cq.Workplane("XY").rect(p.plate_l, p.plate_w).extrude(p.plate_t)',
        'plate = cq.Workplane("XY").circle(60).extrude(p.plate_t)')
    lines = []
    for angle in posts:
        x, y = 50 * math.cos(math.radians(angle)), 50 * math.sin(math.radians(angle))
        lines.append(f"    plate = plate.union(cq.Workplane('XY').workplane(offset={-low}).center({x:.3f}, {y:.3f})"
                     f".circle(4).extrude({low + high}))")
    return code.replace("    return plate\n", "".join(line + "\n" for line in lines) + "    return plate\n")


REFERENCE_PLATE = submission.parse(REFERENCE).parts[0].code
REFERENCE_ARM = submission.parse(REFERENCE).parts[1].code


# --- the reference ------------------------------------------------------------------------------------

def test_reference_passes(tmp_path):
    findings = grade(design(), tmp_path)
    assert all(finding.ok is True for finding in findings), not_passing(findings)


def test_the_request_is_dans():
    assert TASK.request == ("I want to prototype the first version of a robot arm. I have an MG996R servo and a 608 "
                            "bearing to work with. It should swing both ways, and the arm should be about 100 mm long.")


# --- R4: the arm on the shaft ------------------------------------------------------------------------

def test_a_loose_bore_fails_only_the_shaft_fit(tmp_path):
    findings = grade(design(shaft_bore=6.2), tmp_path)
    assert arm_checks(findings) == {"R4": False, "R5": True, "R6": True, "R7": True}, not_passing(findings)


def test_a_bore_well_under_the_hard_push_is_not_graded(tmp_path):
    """5.70 is more than the assumption tolerance under 5.94, a hard push, and nothing tighter was reported."""
    findings = grade(design(shaft_bore=5.70), tmp_path)
    assert arm_checks(findings)["R4"] is None


def test_a_bore_near_a_print_takes_its_result(tmp_path):
    """5.84, the spline's reading, is within 0.2 of 5.94 (a hard push); 6.09 is midway between 6.04 (snug)
    and 6.14 (loose), where the tighter print decides. Both pass, saying which print they're assumed from."""
    for bore in (5.84, 6.09):
        folder = tmp_path / str(bore)
        folder.mkdir()
        ok, detail = result(grade(design(shaft_bore=bore), folder), "R4")
        assert ok is True and "assumed from" in detail, (bore, detail)


def test_a_clearance_hole_for_a_listed_screw_isnt_read_as_the_hub(tmp_path):
    """An M6 hole in the arm, with M6 screws listed, isn't a loose bore for the shaft."""
    hardware = [submission.HardwareItem(id="screw", ref="ISO 4762 M3x10", qty=4),
                submission.HardwareItem(id="nut", ref="ISO 4032 M3", qty=4),
                submission.HardwareItem(id="bearing", ref="608ZZ", qty=1),
                submission.HardwareItem(id="m6", ref="ISO 4762 M6x12", qty=1)]
    findings = grade(design(shaft_bore=6.4, hardware=hardware), tmp_path)
    ok, detail = result(findings, "R4")
    assert ok is None and "apart from screw holes" in detail


def horn_arm(hole=3.4, pocket=14.8):
    """The reference arm on the aluminium horn: a pocket for its 14.66 hub from underneath, 6 mm deep, and a
    hole through the top on the same axis, for the horn's screw."""
    return REFERENCE_ARM.replace(
        "link = link.cut(cq.Workplane(\"XY\").circle(p.shaft_bore / 2).extrude(p.arm_t))",
        f"link = link.cut(cq.Workplane(\"XY\").circle({pocket} / 2).extrude(6))\n"
        f"    link = link.cut(cq.Workplane(\"XY\").circle({hole} / 2).extrude(p.arm_t))")


ROUND3_OUTCOMES = [(14.76, "won't go in"), (15.16, "goes in, a little play"), (15.66, "loose, it drops in")]


HORN_TEST = next(req for req in TASK.requirements if req.id == "R4").args["horn_test"]


def round3_fixture(tmp_path, outcomes):
    """A predictions file with round 3's horn pockets: `outcomes` as (pocket, what the person said), None
    for not recorded yet."""
    path = tmp_path / "round3-coupons.yaml"
    pockets = [{"pocket_d": size, "outcome": said} for size, said in outcomes]
    path.write_text(yaml.safe_dump({"N_horn_pockets": {"pockets": pockets}}))
    return path


def horn_task(tmp_path, outcomes):
    """servo-arm with R4 reading round 3's horn pockets from a fixture."""
    task = copy.deepcopy(TASK)
    next(req for req in task.requirements if req.id == "R4").args["horn_test"]["file"] = str(round3_fixture(tmp_path, outcomes))
    return task


def grade_with(task, sub, tmp_path):
    out = tmp_path / "graded"
    out.mkdir()
    return agent.grade(task, sub, out)


def test_an_arm_on_the_horn_is_graded_for_length_and_swing_but_not_its_fit_until_round_3_is_recorded(tmp_path):
    """The horn's pocket stands in for the shaft's axis. Round 3's pockets printed, but with no outcome
    recorded there's no record, so R4 is not graded."""
    task = horn_task(tmp_path, [(size, None) for size, _ in ROUND3_OUTCOMES])
    findings = grade_with(task, design(arm=horn_arm(pocket=15.0)), tmp_path)
    assert arm_checks(findings) == {"R4": None, "R5": True, "R6": True, "R7": True}, not_passing(findings)
    assert "no recorded outcome yet" in result(findings, "R4")[1]


def test_once_round_3_is_recorded_the_horn_pocket_is_graded_from_it(tmp_path):
    """A 15.0 pocket is within the assumption tolerance of 15.16, where the hub went in with a little play."""
    findings = grade_with(horn_task(tmp_path, ROUND3_OUTCOMES), design(arm=horn_arm(pocket=15.0)), tmp_path)
    assert arm_checks(findings) == {"R4": True, "R5": True, "R6": True, "R7": True}, not_passing(findings)
    assert "assumed from the 15.16" in result(findings, "R4")[1]


def test_round_3s_recorded_pockets_decide_the_horn_arm(tmp_path):
    """Round 3 as recorded (Dan, 2026-11-12): the 14.76 pocket "fits nicely ... a bit loose but doesn't fall
    out", 15.16 and 15.66 "too big". A 14.8 pocket passes on 14.76; a 15.0 one fails, nearer 15.16."""
    records = arm.horn_records(HORN_TEST["file"], HORN_TEST["piece"], HORN_TEST["outcomes"])
    assert records == [(14.76, "works"), (15.16, "too loose"), (15.66, "too loose")]
    assert result(grade(design(arm=horn_arm(pocket=14.8)), tmp_path), "R4")[0] is True
    assert result(grade(design(arm=horn_arm(pocket=15.0)), tmp_path / "loose"), "R4")[0] is False


def test_the_requirement_reads_round_3s_predictions_file():
    assert HORN_TEST["file"] == "results/predictions/round3-coupons.yaml" and HORN_TEST["piece"] == "N_horn_pockets"


def pocket(clear, depth=6.0, plain=True):
    return arm.Bore("arm", 2, clear, depth, plain, np.zeros(2), None, horn=True)


def test_horn_pocket_sizes_take_the_recorded_result(tmp_path):
    records = arm.horn_records(round3_fixture(tmp_path, ROUND3_OUTCOMES), "N_horn_pockets", HORN_TEST["outcomes"])
    assert records == [(14.76, "too tight"), (15.16, "works"), (15.66, "too loose")]
    expected = {14.5: False, 14.76: False, 15.0: True, 15.16: True, 15.3: True, 15.41: None, 15.66: False, 16.2: False}
    for clear, ok in expected.items():
        assert arm.horn_fit(pocket(clear), records, 2.0).ok is ok, clear
    assert arm.horn_fit(pocket(15.16, depth=1.2), records, 2.0).ok is None  # shallower than printed
    assert arm.horn_fit(pocket(15.16, plain=False), records, 2.0).ok is None  # horn-shaped


def test_a_failure_only_rules_out_the_side_it_failed_on(tmp_path):
    """With only the loose pocket recorded, a tighter pocket isn't failed by it (Codex review, PR 4); with only
    the tight one, a looser pocket isn't either."""
    loose_only = arm.horn_records(round3_fixture(tmp_path, [(15.66, "loose, it drops in")]), "N_horn_pockets", HORN_TEST["outcomes"])
    assert arm.horn_fit(pocket(14.76), loose_only, 2.0).ok is None
    assert arm.horn_fit(pocket(15.5), loose_only, 2.0).ok is False  # within the tolerance of a loose pocket
    assert arm.horn_fit(pocket(16.0), loose_only, 2.0).ok is False
    tight_only = arm.horn_records(round3_fixture(tmp_path, [(14.76, "won't go in")]), "N_horn_pockets", HORN_TEST["outcomes"])
    assert arm.horn_fit(pocket(15.66), tight_only, 2.0).ok is None
    assert arm.horn_fit(pocket(14.5), tight_only, 2.0).ok is False


def test_an_outcome_in_words_the_requirement_doesnt_list_isnt_a_record(tmp_path):
    """"too tight" is read before "tight"; "printed badly" says nothing about the fit; None isn't recorded yet."""
    path = round3_fixture(tmp_path, [(14.76, "Too tight, it won't seat"), (15.16, "printed badly"), (15.66, None)])
    assert arm.horn_records(path, "N_horn_pockets", HORN_TEST["outcomes"]) == [(14.76, "too tight")]
    assert arm.horn_records(tmp_path / "missing.yaml", "N_horn_pockets", HORN_TEST["outcomes"]) == []


def test_a_hole_on_the_horns_axis_isnt_read_as_a_loose_bore(tmp_path):
    """A 6.5 hole through the top of a horn pocket is for the horn's screw (Opus 5.5's and Sonnet 5.5's
    first-look arms failed R4 on it before)."""
    findings = grade(design(arm=horn_arm(hole=6.5)), tmp_path)
    ok, detail = result(findings, "R4")
    assert ok is not False and "aluminium horn" in detail, detail


def test_an_arm_with_neither_a_bore_nor_a_horn_pocket_is_not_graded(tmp_path):
    clamp = REFERENCE_ARM.replace("circle(p.shaft_bore / 2)", "circle(10 / 2)")
    findings = grade(design(arm=clamp), tmp_path)
    assert arm_checks(findings) == {"R4": None, "R5": True, "R6": None, "R7": None}, not_passing(findings)


# --- R5: the bearing's seat --------------------------------------------------------------------------

def test_a_seat_at_the_bearings_nominal_size_fails_only_the_seat(tmp_path):
    findings = grade(design(seat_d=22.0), tmp_path)
    assert arm_checks(findings) == {"R4": True, "R5": False, "R6": True, "R7": True}, not_passing(findings)


def test_a_seat_as_loose_as_round_3s_fails(tmp_path):
    """Round 3's H: from 22.4 the 608 was too loose and fell out, so 22.6 fails, as on bearing-wheel."""
    ok, detail = result(grade(design(seat_d=22.6), tmp_path), "R5")
    assert ok is False and "too loose" in detail


def test_no_bearing_in_the_hardware_list_is_not_graded(tmp_path):
    hardware = [submission.HardwareItem(id="screw", ref="ISO 4762 M3x10", qty=4),
                submission.HardwareItem(id="nut", ref="ISO 4032 M3", qty=4)]
    ok, detail = result(grade(design(hardware=hardware), tmp_path), "R5")
    assert ok is None and "no 608ZZ" in detail


# --- R6: the arm's length ----------------------------------------------------------------------------

def test_a_short_arm_fails_only_its_length(tmp_path):
    findings = grade(design(centres=50), tmp_path)
    assert arm_checks(findings) == {"R4": True, "R5": True, "R6": False, "R7": True}, not_passing(findings)


def test_a_long_arm_fails_its_length(tmp_path):
    assert arm_checks(grade(design(centres=120), tmp_path))["R6"] is False


# --- R7: the swing -----------------------------------------------------------------------------------

def test_the_disc_plate_passes(tmp_path):
    findings = grade(design(plate=disc_plate()), tmp_path)
    assert not (failed(findings) | not_graded(findings)) & (SERVO_CHECKS | ARM_CHECKS), not_passing(findings)


def test_tall_posts_all_round_fail_the_swing(tmp_path):
    """Four posts around the shaft, standing well past the arm on both faces: no 120 degrees are clear."""
    findings = grade(design(plate=disc_plate(posts=(0, 90, 180, 270), low=40, high=40)), tmp_path)
    assert result(findings, "R7")[0] is False, result(findings, "R7")
    assert not (failed(findings) | not_graded(findings)) & (SERVO_CHECKS | {"R4", "R5", "R6"}), not_passing(findings)


def test_two_posts_leave_room_to_swing(tmp_path):
    findings = grade(design(plate=disc_plate(posts=(0, 180), low=40, high=40)), tmp_path)
    assert result(findings, "R7")[0] is True, result(findings, "R7")


def test_posts_the_arm_may_or_may_not_clear_are_not_graded(tmp_path):
    """Posts standing a little past the case top: whether the arm clears them depends on how high it sits
    on the shaft, which only the datasheet drawing estimates."""
    findings = grade(design(plate=disc_plate(posts=(0, 90, 180, 270), low=14, high=14)), tmp_path)
    assert result(findings, "R7")[0] is None, result(findings, "R7")


def test_a_part_the_design_doesnt_place_makes_the_swing_not_graded(tmp_path):
    bracket = {"id": "bracket", "role": "final", "material": "PLA", "print_orientation": "flat", "use_orientation": "beside the servo",
               "code": "def build(p):\n    return cq.Workplane('XY').box(30, 10, 40)\n"}
    findings = grade(design(extra_parts=[bracket]), tmp_path)
    ok, detail = result(findings, "R7")
    assert ok is None and "bracket" in detail


def test_a_blind_bore_goes_on_one_way_only(tmp_path):
    """A bore closed at the top: the arm can only go on with its open end down."""
    blind = REFERENCE_ARM.replace("circle(p.shaft_bore / 2).extrude(p.arm_t)", "circle(p.shaft_bore / 2).extrude(p.arm_t - 2)")
    assert result(grade(design(arm=blind), tmp_path), "R7")[0] is True


def test_a_horn_pocket_under_a_screw_hole_goes_on_one_way_only(tmp_path):
    """The hub can't come in through the 3.4 mm screw hole over the pocket, so only the pocket's side is a
    way on (Codex review, PR 4: the centre-point test let the arm on from either side)."""
    from pbe.parts.build import build_parts
    sub = design(arm=horn_arm(pocket=15.0))
    built = build_parts(sub, tmp_path / "parts")
    horn = arm._horn_pocket(sub, built, 14.66, None)
    assert horn is not None and len(arm._arm_frames(horn)) == 1
    through = design()
    reference_bore = arm._shaft_bores(through, build_parts(through, tmp_path / "ref"), (5.74, 6.2), 3.0)[0]
    assert len(arm._arm_frames(reference_bore)) == 2


# --- the person --------------------------------------------------------------------------------------

def test_the_person_gives_the_spline_and_says_the_shaft_position_wasnt_measured():
    person = measure.Person(TASK.hidden_facts)
    assert "5.84" in person.measure("servo", "shaft diameter")
    reply = person.measure("servo", "shaft position")
    assert "didn't measure" in reply and "near one end" in reply
    assert "120" in person.measure("servo", "rotation range")


def test_the_prompt_leaves_the_servos_out_and_offers_the_datasheet():
    system = agent.opening_messages(TASK, "can_ask", measure.Person(TASK.hidden_facts), 8)[0]["content"]
    assert "tab_notch" not in system and "608ZZ" in system
    assert len(TASK.format.datasheet) == 2 and all(page.exists() for page in TASK.format.datasheet)


def test_a_bore_with_a_narrow_clamping_slot_isnt_plain():
    """A 0.5 mm slot 3 mm long adds under 6% to a 5.84 bore's area, so area alone read it as plain
    (Codex review, PR 4); its widest span gives it away."""
    from shapely.geometry import Point, box
    round_bore = Point(0, 0).buffer(5.84 / 2, 256)
    slotted = round_bore.union(box(2.5, -0.25, 2.92 + 3, 0.25))
    assert arm._is_plain(round_bore)
    assert slotted.area <= arm.PLAIN * round_bore.area and not arm._is_plain(slotted)


def test_a_valid_bearing_seat_isnt_cancelled_by_another_opening_its_size():
    """The design uses one 608, so a servo cutout 20-26 mm across (not plain, so not graded) or any other
    such opening doesn't undo a seat that holds it (Codex review, PR 4)."""
    seat, cutout = Verdict(True, "seat"), Verdict(None, "cutout")
    assert arm._best([cutout, seat]) is seat
    assert arm._best([cutout, Verdict(False, "too tight")]).ok is False
