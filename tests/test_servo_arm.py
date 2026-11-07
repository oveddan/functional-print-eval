"""The servo arm: the reference passes every check, each real mistake fails the check aimed at it and
no other, and cases between the records come back not graded (ok = None), which is never a pass.
servo-mount's tests cover R1 to R3; these cover the arm."""
import math

from helpers import checked, failed, grade, not_graded, not_passing

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


def test_a_bore_at_the_spline_reading_is_not_graded(tmp_path):
    """5.84 is the reading itself, and test print E's 5.84 bore wasn't reported."""
    findings = grade(design(shaft_bore=5.84), tmp_path)
    assert arm_checks(findings)["R4"] is None


def test_between_snug_and_loose_is_not_graded(tmp_path):
    assert arm_checks(grade(design(shaft_bore=6.09), tmp_path))["R4"] is None


def test_a_clearance_hole_for_a_listed_screw_isnt_read_as_the_hub(tmp_path):
    """An M6 hole in the arm, with M6 screws listed, isn't a loose bore for the shaft."""
    hardware = [submission.HardwareItem(id="screw", ref="ISO 4762 M3x10", qty=4),
                submission.HardwareItem(id="nut", ref="ISO 4032 M3", qty=4),
                submission.HardwareItem(id="bearing", ref="608ZZ", qty=1),
                submission.HardwareItem(id="m6", ref="ISO 4762 M6x12", qty=1)]
    findings = grade(design(shaft_bore=6.4, hardware=hardware), tmp_path)
    ok, detail = result(findings, "R4")
    assert ok is None and "apart from screw holes" in detail


def horn_arm(hole=3.4):
    """The reference arm on the aluminium horn: a pocket for its 14.66 hub from underneath, 6 mm deep, and a
    hole through the top on the same axis, for the horn's screw."""
    return REFERENCE_ARM.replace(
        "link = link.cut(cq.Workplane(\"XY\").circle(p.shaft_bore / 2).extrude(p.arm_t))",
        "link = link.cut(cq.Workplane(\"XY\").circle(15.0 / 2).extrude(6))\n"
        f"    link = link.cut(cq.Workplane(\"XY\").circle({hole} / 2).extrude(p.arm_t))")


def test_an_arm_on_the_horn_is_graded_for_length_and_swing_but_not_its_fit(tmp_path):
    """The horn's pocket stands in for the shaft's axis. How the arm holds the horn was never printed."""
    findings = grade(design(arm=horn_arm()), tmp_path)
    assert arm_checks(findings) == {"R4": None, "R5": True, "R6": True, "R7": True}, not_passing(findings)
    assert "takes the aluminium horn" in result(findings, "R4")[1]


def test_a_hole_on_the_horns_axis_isnt_read_as_a_loose_bore(tmp_path):
    """A 6.5 hole through the top of a horn pocket is for the horn's screw (Opus 5.5's and Sonnet 5.5's
    first-look arms failed R4 on it before)."""
    findings = grade(design(arm=horn_arm(hole=6.5)), tmp_path)
    assert arm_checks(findings)["R4"] is None, result(findings, "R4")


def test_an_arm_with_neither_a_bore_nor_a_horn_pocket_is_not_graded(tmp_path):
    clamp = REFERENCE_ARM.replace("circle(p.shaft_bore / 2)", "circle(10 / 2)")
    findings = grade(design(arm=clamp), tmp_path)
    assert arm_checks(findings) == {"R4": None, "R5": True, "R6": None, "R7": None}, not_passing(findings)


# --- R5: the bearing's seat --------------------------------------------------------------------------

def test_a_seat_at_the_bearings_nominal_size_fails_only_the_seat(tmp_path):
    findings = grade(design(seat_d=22.0), tmp_path)
    assert arm_checks(findings) == {"R4": True, "R5": False, "R6": True, "R7": True}, not_passing(findings)


def test_a_seat_looser_than_any_print_is_not_graded(tmp_path):
    assert arm_checks(grade(design(seat_d=22.5), tmp_path))["R5"] is None


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
