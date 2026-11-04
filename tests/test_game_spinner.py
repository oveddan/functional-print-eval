"""The game spinner (issue 41): a task synthesized from two recorded fits, the 608's seat (round 2) and
the M5's pocket (coupon B). The reference passes every check, each wrong design fails the check aimed
at it and no other, reward hacks fail, correct designs unlike the reference pass, and a case between
two records comes back not graded (ok = None), which is never a pass."""
from pathlib import Path

import pytest
import yaml

from pbe.graders import combined
from pbe.parts import submission
from pbe.runner import measure, tasks

from helpers import checked, failed, grade, not_graded, not_passing

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = tasks.load("game-spinner").reference

# Shared by the designs below, so each one shows only what makes it different.
HELPERS = '''
import math

def blank(p):
    return cq.Workplane("XY").circle(p.across / 2).extrude(p.thick)

def seat_from_top(p):
    return cq.Workplane("XY").workplane(offset=p.thick - p.seat_h).circle(p.seat / 2).extrude(p.seat_h)

def seat_from_bed(p):
    return cq.Workplane("XY").circle(p.seat / 2).extrude(p.seat_h)

def relief(p):
    return cq.Workplane("XY").circle(p.relief / 2).extrude(p.thick)

def handle_hole(p, start=0):
    return cq.Workplane("XY").workplane(offset=start).center(p.handle_r, 0).circle(p.bolt_hole / 2).extrude(p.thick - start)

def hex_cut(p, z, depth, across=None):
    across = (p.nut_af + p.clearance) if across is None else across
    return cq.Workplane("XY").workplane(offset=z).center(p.handle_r, 0).polygon(6, across / math.cos(math.radians(30))).extrude(depth)

def pocket_from_top(p):
    return hex_cut(p, p.thick - p.nut_h - p.recess, p.nut_h + p.recess)

def pocket_from_bed(p):
    return hex_cut(p, 0, p.nut_h + p.recess)
'''
SEAT_AT_THE_BED = HELPERS + '''
def build(p):
    # the seat opens at the bed, so its floor is a roof with the bolt's hole through it
    return blank(p).cut(seat_from_bed(p)).cut(relief(p)).cut(handle_hole(p)).cut(pocket_from_top(p))
'''
SEAT_AT_THE_BED_CONE_ROOF = HELPERS + '''
def build(p):
    # the seat opens at the bed, and a 45 degree cone narrows its roof to the relief, so nothing bridges
    r = p.seat / 2
    cone = cq.Workplane(cq.Solid.makeCone(r, p.relief / 2, r - p.relief / 2, cq.Vector(0, 0, p.seat_h), cq.Vector(0, 0, 1)))
    return blank(p).cut(seat_from_bed(p)).cut(cone).cut(relief(p)).cut(handle_hole(p)).cut(pocket_from_top(p))
'''
POCKET_AT_THE_BED = HELPERS + '''
def build(p):
    return blank(p).cut(seat_from_top(p)).cut(relief(p)).cut(handle_hole(p)).cut(pocket_from_bed(p))
'''
POCKET_AT_THE_BED_DRILL_OUT = HELPERS + '''
def build(p):
    # two closed layers over the pocket, so its roof bridges wall to wall; the hole starts above them
    above = p.nut_h + p.recess + 0.4
    return blank(p).cut(seat_from_top(p)).cut(relief(p)).cut(handle_hole(p, start=above)).cut(pocket_from_bed(p))
'''
HEX_RIGHT_THROUGH = HELPERS + '''
def build(p):
    return blank(p).cut(seat_from_top(p)).cut(relief(p)).cut(hex_cut(p, 0, p.thick))
'''
NO_HANDLE_HOLE = HELPERS + '''
def build(p):
    return blank(p).cut(seat_from_top(p)).cut(relief(p)).cut(pocket_from_top(p))
'''
HARD_CODED_POCKET = HELPERS + '''
def build(p):
    pocket = hex_cut(p, p.thick - p.nut_h - p.recess, p.nut_h + p.recess, across=8.3)
    return blank(p).cut(seat_from_top(p)).cut(relief(p)).cut(handle_hole(p)).cut(pocket)
'''
RIBBED_SEAT = HELPERS + '''
def build(p):
    # crush ribs round a seat 1 mm wider than the bearing
    seat = cq.Workplane("XY").workplane(offset=p.thick - p.seat_h).circle(p.seat / 2 + 0.5).extrude(p.seat_h)
    wheel = blank(p).cut(seat).cut(relief(p)).cut(handle_hole(p)).cut(pocket_from_top(p))
    for i in range(6):
        a = i * math.pi / 3
        r = p.seat / 2 + 0.75
        rib = cq.Workplane("XY").workplane(offset=p.thick - p.seat_h).center(r * math.cos(a), r * math.sin(a)).circle(0.75).extrude(p.seat_h)
        wheel = wheel.union(rib)
    return wheel
'''
LIGHTENED = HELPERS + '''
def build(p):
    # three round windows, well short of a seat's size, away from the handle
    windows = cq.Workplane("XY").pushPoints([(0, 23), (-23, 0), (0, -23)]).circle(5).extrude(p.thick)
    return blank(p).cut(seat_from_top(p)).cut(relief(p)).cut(handle_hole(p)).cut(pocket_from_top(p)).cut(windows)
'''
ROTATED_CHAMFERED_POCKET = HELPERS + '''
def build(p):
    # the hex turned 17 degrees about the handle's axis, with a 0.6 mm chamfer round its mouth
    pocket = pocket_from_top(p).rotate((p.handle_r, 0, 0), (p.handle_r, 0, 1), 17)
    r = (p.nut_af + p.clearance) / 2 / math.cos(math.radians(30))
    chamfer = cq.Workplane(cq.Solid.makeCone(r, r + 0.6, 0.6, cq.Vector(p.handle_r, 0, p.thick - 0.6), cq.Vector(0, 0, 1)))
    return blank(p).cut(seat_from_top(p)).cut(relief(p)).cut(handle_hole(p)).cut(pocket).cut(chamfer)
'''
SEALED_NUT = HELPERS + '''
def build(p):
    # as Opus 5.5's second design: a closed pocket the print seals over, and the handle's hole stopping above the floor
    floor = 1.6
    return blank(p).cut(seat_from_top(p)).cut(relief(p)).cut(hex_cut(p, floor, p.nut_h + 0.3)).cut(handle_hole(p, start=floor))
'''
SEALED_NUT_DRILL_OUT = HELPERS + '''
def build(p):
    # a sealed nut with a solid floor under it, and a 0.4 mm layer over it the manual says to drill through
    floor = 1.6
    top = floor + p.nut_h + 0.3
    return blank(p).cut(seat_from_top(p)).cut(relief(p)).cut(hex_cut(p, floor, p.nut_h + 0.3)).cut(handle_hole(p, start=top + 0.4))
'''
SLOTTED_SEAT = HELPERS + '''
def build(p):
    # a 3 mm slot from the seat out through the rim, the seat's whole depth, away from the handle
    slot = cq.Workplane("XY").workplane(offset=p.thick - p.seat_h).center(-p.across / 4, 0).rect(p.across / 2, 3).extrude(p.seat_h)
    return blank(p).cut(seat_from_top(p)).cut(relief(p)).cut(handle_hole(p)).cut(pocket_from_top(p)).cut(slot)
'''
TALL_BOSS = HELPERS + '''
def build(p):
    # as Gemini 4 Argon's first design: a boss round the handle stands 20 mm, twice the wheel
    boss = cq.Workplane("XY").center(p.handle_r, 0).circle(6.5).extrude(20)
    hole = cq.Workplane("XY").center(p.handle_r, 0).circle(p.bolt_hole / 2).extrude(20)
    return blank(p).union(boss).cut(seat_from_top(p)).cut(relief(p)).cut(hole).cut(pocket_from_bed(p))
'''
COUPON = '''
import math

def build(p):
    # one bar for both fits: 608 seats at round 2's sizes and M5 pockets at coupon B's
    bar = cq.Workplane("XY").box(4 * 28, 56, 6, centered=(False, True, False))
    for i, (seat, c) in enumerate(zip([22.0, 22.1, 22.2, 22.3], [0.0, 0.1, 0.2, 0.3])):
        x = 14 + 28 * i
        bar = bar.cut(cq.Workplane("XY").workplane(offset=1).center(x, 13).circle(seat / 2).extrude(5))
        corners = (p.nut_af + c) / math.cos(math.radians(30))
        bar = bar.cut(cq.Workplane("XY").workplane(offset=2).center(x, -15).polygon(6, corners).extrude(4))
    return bar
'''


def design(code=None, **params):
    """The reference, with some params changed or its part's code replaced."""
    sub = submission.parse(REFERENCE)
    for name, value in params.items():
        sub.params[name].value = value
    if code is not None:
        sub.parts[0].code = code
    return checked(sub)


def told(sub, text):
    sub.manual.insert(1, submission.Step(n="1b", text=text, parts=["wheel"]))
    return sub


def with_coupon(sub, in_manual=True):
    sub.parts.append(sub.parts[0].model_copy(update={"id": "coupon", "role": "coupon", "code": COUPON}))
    if in_manual:
        sub.manual.insert(0, submission.Step(n="0", text="Print the coupon first; try the bearing and the nut in each size.", parts=["coupon"]))
    return sub


def without_hardware(sub, ids):
    """The design with these hardware items gone, from its list and from every step of its manual."""
    sub.hardware = [item for item in sub.hardware if item.id not in ids]
    for step in sub.manual:
        step.hardware = [item for item in step.hardware if item not in ids]
    sub.criteria = [criterion for criterion in sub.criteria if criterion.hardware not in ids]
    return sub


def with_second_part(sub):
    sub.parts.append(sub.parts[0].model_copy(update={"id": "wheel2"}))
    return sub


def test_reference_passes_every_check(tmp_path):
    findings = grade(design(), tmp_path)
    assert all(f.ok is True for f in findings), not_passing(findings)


@pytest.mark.parametrize("sub, want_failed, want_not_graded", [
    # the catalog's 22.0 won't take the bearing (round 2); +0.3 is where nuts fell out (tripod build)
    pytest.param(design(seat=22.0), {"R4"}, set(), id="seat-at-the-catalogs-22.0"),
    pytest.param(design(clearance=0.3), {"R7"}, set(), id="pocket-at-plus-0.3"),
    # room and shape: one bearing needs 7 mm, the nut a closed hex reached from one face
    pytest.param(design(seat=19), {"R3"}, {"R4", "R5"}, id="no-seat-the-bearing-fits"),
    pytest.param(design(code=HEX_RIGHT_THROUGH), {"R6"}, set(), id="hex-right-through-so-it-can-go-out-the-far-side"),
    # the bolts can't get through
    pytest.param(design(relief=7.8), {"R5"}, set(), id="bore-too-small-for-the-M8"),
    pytest.param(design(bolt_hole=4.8), {"R8"}, set(), id="handle-hole-too-small-for-the-M5"),
    pytest.param(design(code=NO_HANDLE_HOLE), {"R8"}, set(), id="no-hole-for-the-handle"),
    pytest.param(design(code=POCKET_AT_THE_BED_DRILL_OUT), {"R8"}, set(), id="closed-layer-nobody-told-to-clear"),
    # the request's size
    pytest.param(design(across=100), {"R2"}, set(), id="100-mm-across"),
    # printing: a holed roof wider than 3.1 mm from its walls tangles (Arca plate, coupon A's H)
    pytest.param(design(code=SEAT_AT_THE_BED), {"bridges"}, set(), id="seat-at-the-bed-under-a-holed-roof"),
    # two printed parts; the checks that need one part can't say
    pytest.param(with_second_part(design()), {"R1"}, {"R2", "R6", "R7", "R8"}, id="two-parts"),
])
def test_wrong_designs_fail_only_their_check(tmp_path, sub, want_failed, want_not_graded):
    findings = grade(sub, tmp_path)
    assert (failed(findings), not_graded(findings)) == (want_failed, want_not_graded), not_passing(findings)


@pytest.mark.parametrize("sub, want_failed", [
    # a pocket loose enough that any nut goes in: looser than where nuts fell out
    pytest.param(design(clearance=0.5), {"R7"}, id="oversized-pocket"),
    # the labels say measured, the geometry says otherwise; the geometry is graded
    pytest.param(design(seat=22.0, clearance=0.3), {"R4", "R7"}, id="labelled-measured-but-wrong"),
    # a coupon that would find the answers, but the manual never says to print it
    pytest.param(with_coupon(design(seat=22.0, clearance=0.3), in_manual=False), {"R4", "R7"}, id="coupon-not-in-the-manual"),
    # a coupon in the manual, but no param would carry its answer to the pocket
    pytest.param(with_coupon(design(code=HARD_CODED_POCKET)), {"R7"}, id="coupon-but-hard-coded-pocket"),
])
def test_reward_hacks_fail(tmp_path, sub, want_failed):
    assert failed(grade(sub, tmp_path)) == want_failed


@pytest.mark.parametrize("sub", [
    pytest.param(design(seat=22.1), id="seat-22.1-the-tightest-that-held"),
    pytest.param(design(seat=22.3), id="seat-22.3-the-loosest-printed"),
    pytest.param(design(clearance=0.0), id="pocket-at-plus-0.0"),
    pytest.param(design(thick=14, handle_r=18), id="thicker-handle-nearer-the-middle"),
    pytest.param(design(code=SEAT_AT_THE_BED_CONE_ROOF), id="seat-at-the-bed-with-a-cone-roof"),
    pytest.param(told(design(code=POCKET_AT_THE_BED_DRILL_OUT), "Drill out the thin layer over the nut's pocket with a 5.5 mm bit."),
                 id="closed-layer-the-manual-says-to-clear"),
    pytest.param(design(code=ROTATED_CHAMFERED_POCKET), id="pocket-turned-17-degrees-with-a-chamfer"),
    pytest.param(design(code=LIGHTENED), id="three-windows"),
    # one coupon finds both answers, and a param carries each to the wheel
    pytest.param(with_coupon(design(seat=22.0, clearance=0.3)), id="coupon-rescues-both-fits"),
])
def test_right_designs_that_differ_from_the_reference_pass(tmp_path, sub):
    findings = grade(sub, tmp_path)
    assert all(f.ok is True for f in findings), not_passing(findings)


@pytest.mark.parametrize("sub, want_not_graded", [
    # between 22.0 (won't go in) and 22.1 (held); above 22.3, the loosest printed
    pytest.param(design(seat=22.05), {"R4"}, id="seat-22.05"),
    pytest.param(design(seat=22.5), {"R4"}, id="seat-22.5"),
    pytest.param(design(code=RIBBED_SEAT), {"R4"}, id="ribbed-seat"),
    # coupon B's M5 +0.2 is "loose", but nobody turned it upside down; nothing printed under +0.0
    pytest.param(design(clearance=0.2), {"R7"}, id="pocket-at-plus-0.2"),
    pytest.param(design(clearance=-0.05), {"R7"}, id="pocket-under-the-nuts-size"),
    # between the bolt's size and ISO 273's fine clearance hole, no print says
    pytest.param(design(relief=8.2), {"R5"}, id="M8-bore-8.2"),
    pytest.param(design(bolt_hole=5.15), {"R8"}, id="M5-hole-5.15"),
    # a bearing standing proud, or held only by its press fit: no print tried either
    pytest.param(design(seat_h=6.6), {"R3"}, id="bearing-0.4-proud"),
    # Opus 5.5's choice in the first look: 1 mm proud on purpose; no test print tried a shallow seat
    pytest.param(design(seat_h=6), {"R3", "R4"}, id="bearing-1-mm-proud"),
    pytest.param(design(relief=22.2), {"R3"}, id="no-shoulder-under-the-bearing"),
    # the pocket's roof is a ring 1.3 to 1.9 mm wide round the hole: narrower than any roof seen to
    # tangle, wider than the 1.5 mm allowance
    pytest.param(design(code=POCKET_AT_THE_BED), {"bridges"}, id="pocket-at-the-bed-with-a-plain-hole"),
])
def test_cases_between_records_are_not_graded(tmp_path, sub, want_not_graded):
    findings = grade(sub, tmp_path)
    assert (failed(findings), not_graded(findings)) == (set(), want_not_graded), not_passing(findings)


def _requirement(task_id, grader):
    return next(r for r in tasks.load(task_id).requirements if r.grader == grader)


def test_the_seat_limits_are_round_2s():
    seats = yaml.safe_load((ROOT / "results/predictions/round2-coupons.yaml").read_text())["E_splines_bearings"]["608_seats"]
    held = [row["seat_d"] for row in seats if "holds upside down" in row["outcome"]]
    too_tight = [row["seat_d"] for row in seats if row["outcome"] == "won't go in"]
    args = _requirement("game-spinner", "combined.bearing_fit").args
    assert args["too_tight"] == max(too_tight) and args["holds"] == [min(held), max(held)]
    # and they're the bearing wheel's, but for one bearing instead of two
    wheel = _requirement("bearing-wheel", "wheel.fit").args
    assert {**wheel, "bearings": 1} == args


def test_the_nuts_are_the_ones_coupon_B_printed():
    printed = {row["nut"] for row in yaml.safe_load((ROOT / "results/predictions/round1-coupons.yaml").read_text())["B_nuts"]["pockets"]}
    assert set(combined.RECORDED_NUTS) <= printed
    # each bolt's fine clearance hole is the one the knob uses
    knob = yaml.safe_load((ROOT / "tasks/nut-knob/variants.yaml").read_text())
    assert {size: fine for size, (_, fine) in combined.RECORDED_NUTS.items()} == {size: knob[size]["hole_fine"] for size in combined.RECORDED_NUTS}


def test_the_person_answers_about_the_bearing_and_nothing_else():
    person = measure.Person(tasks.load("game-spinner").hidden_facts)
    assert "22" in person.measure("608 bearing", "outside diameter")
    # GPT-6.1 Sol's questions in the first look, which used to get the M8 bolt's size back
    assert person.measure("board and M8 axle mounting", "board thickness") == measure.NO_ANSWER
    assert person.measure("board the spinner will mount on", "Thickness in mm, for the M8 bolt and nut?") == measure.NO_ANSWER


# --- the model picks the nut: each is graded against its own row of coupon B -----------------

NUTS = {"M3": (5.5, 2.4, 3.4), "M4": (7.0, 3.2, 4.5), "M5": (8.0, 4.7, 5.5), "M8": (13.0, 6.8, 9.0)}  # af, h, hole


def with_nut(size, clearance, ref=None, keep_axle_nut=False, **params):
    """The reference with its handle nut swapped for this size, at this clearance over its flats."""
    af, h, hole = NUTS[size]
    sub = design(**{"nut_af": af, "nut_h": h, "clearance": clearance, "bolt_hole": hole, **params})
    if not keep_axle_nut:
        without_hardware(sub, ("axle_nut",))
    next(item for item in sub.hardware if item.id == "nut").ref = ref or f"ISO 4032 {size}"
    return checked(sub)


@pytest.mark.parametrize("sub, want_failed, want_not_graded", [
    pytest.param(with_nut("M3", 0.2), set(), set(), id="M3-at-plus-0.2-holds"),
    pytest.param(with_nut("M3", 0.0), {"R7"}, set(), id="M3-at-plus-0.0-wont-go-in"),
    pytest.param(with_nut("M3", 0.1), set(), {"R7"}, id="M3-at-plus-0.1-struggles"),
    pytest.param(with_nut("M8", 0.0), set(), set(), id="M8-at-plus-0.0-holds"),
    pytest.param(with_nut("M8", 0.1), set(), {"R7"}, id="M8-at-plus-0.1-loose-never-turned-over"),
    pytest.param(with_nut("M8", 0.3), {"R7"}, set(), id="M8-at-plus-0.3-falls-out"),
    pytest.param(with_nut("M8", 0.0, bolt_hole=8.2), set(), {"R8"}, id="M8-hole-8.2-between-records"),
    pytest.param(with_nut("M4", 0.1), set(), {"R6", "R7", "R8"}, id="an-M4-nut-no-test-print-covers"),
    pytest.param(with_nut("M5", 0.1, ref="ISO 10511 M5"), set(), {"R6", "R7", "R8"}, id="a-lock-nut-no-test-print-covers"),
    # Codex on PR 44: with the M8 axle nuts listed too, the M8 isn't taken for the handle's nut
    pytest.param(with_nut("M4", 0.1, keep_axle_nut=True), set(), {"R6", "R7", "R8"}, id="an-M4-handle-nut-beside-M8-axle-nuts"),
    pytest.param(with_nut("M5", 0.1, ref="ISO 10511 M5", keep_axle_nut=True), set(), {"R6", "R7", "R8"}, id="a-lock-nut-beside-M8-axle-nuts"),
])
def test_each_nut_is_graded_against_its_own_record(tmp_path, sub, want_failed, want_not_graded):
    findings = grade(sub, tmp_path)
    assert (failed(findings), not_graded(findings)) == (want_failed, want_not_graded), not_passing(findings)


def test_two_nuts_listed_grades_the_one_with_a_pocket(tmp_path):
    sub = design()
    sub.hardware.append(submission.HardwareItem(id="spare", ref="ISO 4032 M8"))
    findings = grade(checked(sub), tmp_path)
    assert all(f.ok is True for f in findings), not_passing(findings)


def test_a_bearing_left_off_the_list_is_still_graded_by_its_seat(tmp_path):
    # Opus 5.5 and Sonnet 5.5 on the first look: told the person had the bearing, they didn't list it
    sub = without_hardware(design(), ("bearing",))
    findings = grade(checked(sub), tmp_path)
    assert all(f.ok is True for f in findings), not_passing(findings)


def test_no_nut_and_no_bearing_arent_graded(tmp_path):
    sub = design(seat=19)
    without_hardware(sub, ("nut", "axle_nut", "bearing"))
    findings = grade(checked(sub), tmp_path)
    assert (failed(findings), not_graded(findings)) == (set(), {"R3", "R4", "R5", "R6", "R7", "R8"})


def test_a_nut_sealed_in_by_a_print_pause_isnt_graded_on_its_fit(tmp_path):
    sub = told(design(code=SEALED_NUT), "Pause the print at 6.6 mm, drop the M5 nut into its pocket, and resume.")
    findings = grade(sub, tmp_path)
    # the roof over the nut is a ring round the handle's hole, narrower than any roof seen to tangle
    assert (failed(findings), not_graded(findings)) == (set(), {"R6", "R7", "bridges"}), not_passing(findings)
    assert next(f for f in findings if f.check == "R8").detail.startswith("M5: sealed nut, reached from above")


def test_a_closed_pocket_nobody_says_to_fill_fails(tmp_path):
    findings = grade(design(code=SEALED_NUT), tmp_path)
    assert (failed(findings), not_graded(findings)) == ({"R6", "R8"}, {"bridges"}), not_passing(findings)


def test_a_seat_hidden_by_a_tall_boss_isnt_graded(tmp_path):
    findings = grade(design(code=TALL_BOSS), tmp_path)
    assert (failed(findings), not_graded(findings)) == (set(), {"R3", "R4", "R5", "bridges"}), not_passing(findings)


def test_a_sealed_nut_reached_through_a_drill_out_layer_passes_R8(tmp_path):
    # Codex on PR 44: the drill-out allowance nut.bolt_passes gives applies to a sealed nut too
    sub = told(design(code=SEALED_NUT_DRILL_OUT), "Pause the print at 6.6 mm, drop the M5 nut into its pocket, and resume.")
    sub = told(sub, "Drill out the thin layer over the nut with a 5.5 mm bit.")
    findings = grade(sub, tmp_path)
    assert (failed(findings), not_graded(findings)) == (set(), {"R6", "R7"}), not_passing(findings)


def test_a_seat_slotted_open_to_the_rim_isnt_graded(tmp_path):
    # Codex on PR 44: the slot opens the seat into the outline, so it's no closed hole in any layer
    findings = grade(design(code=SLOTTED_SEAT), tmp_path)
    assert (failed(findings), not_graded(findings)) == (set(), {"R3", "R4", "R5"}), not_passing(findings)
