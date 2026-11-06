"""The nut-knob family: the references pass every check, wrong designs fail the check aimed
at them and no other, and correct designs that don't look like the reference still pass.

"Not graded" (ok = None) is kept apart from "failed" (ok = False): it's what a check says
when no print has measured the case, or when another check has already failed the design."""
import pytest

from pbe.graders import nuts
from pbe.parts import submission
from pbe.runner import tasks

from pbe.parts.build import build_parts

from helpers import checked, failed, grade, not_graded, not_passing

# Shared by the designs below, so each one shows only what makes it different.
HELPERS = '''
import math

def height(p):
    return p.floor + p.nut_h + p.recess

def blank(p):
    return cq.Workplane("XY").circle(p.knob_d / 2).extrude(height(p))

def bolt_hole(p, x=0):
    return cq.Workplane("XY").center(x, 0).circle(p.bolt_hole / 2).extrude(height(p))

def hex_cut(p, z, depth, across=None):
    across = (p.nut_af + p.clearance) if across is None else across
    return cq.Workplane("XY").workplane(offset=z).polygon(6, across / math.cos(math.radians(30))).extrude(depth)

def pocket_on_top(p):
    return hex_cut(p, p.floor, p.nut_h + p.recess)

def pocket_at_bed(p):
    return hex_cut(p, 0, p.nut_h + p.recess)

def chamfer_on_top(p, c):
    r = (p.nut_af + p.clearance) / 2 / math.cos(math.radians(30))
    return cq.Workplane(cq.Solid.makeCone(r, r + c, c, cq.Vector(0, 0, height(p) - c), cq.Vector(0, 0, 1)))
'''
ROUND_POCKET = HELPERS + '''
def build(p):
    bore = cq.Workplane("XY").workplane(offset=p.floor).circle((p.nut_af + p.clearance) / 2).extrude(p.nut_h + p.recess)
    return blank(p).cut(bolt_hole(p)).cut(bore)
'''
CLOSED_POCKET = HELPERS + '''
def build(p):
    # the nut's cavity is sealed under a 3 mm roof; only the bolt hole reaches it
    tall = p.floor + p.nut_h + 3
    body = cq.Workplane("XY").circle(p.knob_d / 2).extrude(tall)
    hole = cq.Workplane("XY").circle(p.bolt_hole / 2).extrude(tall)
    return body.cut(hole).cut(hex_cut(p, p.floor, p.nut_h))
'''
NO_THROUGH_HOLE = HELPERS + '''
def build(p):
    return blank(p).cut(pocket_on_top(p))
'''
OFF_CENTRE_HOLE = HELPERS + '''
def build(p):
    return blank(p).cut(bolt_hole(p, x=1.5)).cut(pocket_on_top(p))
'''
HARD_CODED_POCKET = HELPERS + '''
def build(p):
    return blank(p).cut(bolt_hole(p)).cut(hex_cut(p, p.floor, p.nut_h + p.recess, across=8.3))
'''
BED_POCKET_PLAIN_HOLE = HELPERS + '''
def build(p):
    return blank(p).cut(bolt_hole(p)).cut(pocket_at_bed(p))
'''
BED_POCKET_STEPPED_ROOF = HELPERS + '''
def build(p):
    # coupon A's cell S: a strip the hole's width, then a square, then the hole
    roof = p.nut_h + p.recess
    strip = cq.Workplane("XY").workplane(offset=roof).rect(p.bolt_hole, 2 * p.nut_af).extrude(0.4)
    square = cq.Workplane("XY").workplane(offset=roof).rect(p.bolt_hole, p.bolt_hole).extrude(0.8)
    return blank(p).cut(pocket_at_bed(p)).cut(strip).cut(square).cut(bolt_hole(p))
'''
BED_POCKET_DRILL_OUT = HELPERS + '''
def build(p):
    # two closed layers over the pocket, so the roof bridges wall to wall; the hole starts above them
    roof = p.nut_h + p.recess
    hole_above = cq.Workplane("XY").workplane(offset=roof + 0.4).circle(p.bolt_hole / 2).extrude(p.floor)
    return blank(p).cut(pocket_at_bed(p)).cut(hole_above)
'''
CHAMFERED_MOUTH = HELPERS + '''
def build(p):
    return blank(p).cut(bolt_hole(p)).cut(pocket_on_top(p)).cut(chamfer_on_top(p, 0.6))
'''
ROUND_COLLAR_ABOVE = HELPERS + '''
def build(p):
    # the hex is 2 mm deep; above it a round bore a nut's corners can't pass
    collar = cq.Workplane("XY").workplane(offset=p.floor + 2).circle((p.nut_af + p.clearance) / 2 + 0.2).extrude(p.nut_h)
    return blank(p).cut(bolt_hole(p)).cut(hex_cut(p, p.floor, 2)).cut(collar)
'''
FILLETED_SQUARE = HELPERS + '''
def build(p):
    across = p.nut_af + p.clearance
    square = cq.Workplane("XY").workplane(offset=p.floor).rect(across, across).extrude(p.nut_h + p.recess).edges("|Z").fillet(1.6)
    return blank(p).cut(bolt_hole(p)).cut(square)
'''
PENTAGON = HELPERS + '''
def build(p):
    pentagon = cq.Workplane("XY").workplane(offset=p.floor).polygon(5, 9.5).extrude(p.nut_h + p.recess)
    return blank(p).cut(bolt_hole(p)).cut(pentagon)
'''
LIGHTENED = HELPERS + '''
def build(p):
    # three round holes for lightening, about the nut's size and deeper than its pocket
    holes = cq.Workplane("XY").polarArray(11, 0, 360, 3).circle(3.5).extrude(height(p))
    return cq.Workplane("XY").circle(18).extrude(height(p)).cut(holes).cut(bolt_hole(p)).cut(pocket_on_top(p))
'''
FILLETED_HEX = HELPERS + '''
def build(p):
    # a hex pocket with its sharp corners rounded a little: real nuts' corners are chamfered, so it fits
    return blank(p).cut(bolt_hole(p)).cut(pocket_on_top(p).edges("|Z").fillet(0.4))
'''
ROTATED_HEX = HELPERS + '''
def build(p):
    return blank(p).cut(bolt_hole(p)).cut(pocket_on_top(p).rotate((0, 0, 0), (0, 0, 1), 17))
'''
RELIEVED_CORNERS = HELPERS + '''
def build(p):
    # a round relief at each corner, so the corners can't foul; the flats still stop the nut turning
    r = (p.nut_af + p.clearance) / 2 / math.cos(math.radians(30))
    relief = cq.Workplane("XY").workplane(offset=p.floor).polarArray(r, 0, 360, 6).circle(1).extrude(p.nut_h + p.recess)
    return blank(p).cut(bolt_hole(p)).cut(pocket_on_top(p)).cut(relief)
'''
SECOND_HEX_RECESS = HELPERS + '''
def build(p):
    # the nut's pocket on top, and a 2 mm hex recess under it on the same axis
    return blank(p).cut(bolt_hole(p)).cut(pocket_on_top(p)).cut(hex_cut(p, 0, 2))
'''
RELIEF_SLOTS = HELPERS + '''
def build(p):
    # slots out from three flats make the hole's farthest point not a corner of the hexagon
    slot = cq.Workplane("XY").workplane(offset=p.floor).box(8, 1, p.nut_h + p.recess, centered=(False, True, False))
    body = blank(p).cut(bolt_hole(p)).cut(pocket_on_top(p))
    for i in range(3):
        body = body.cut(slot.rotate((0, 0, 0), (0, 0, 1), 30 + 120 * i))
    return body
'''
SPRING_CLIPS = HELPERS + '''
def build(p):
    # as Grok 4.7's and GPT-6.1 Sol's knobs (run pilot-nut-knob): a hex +0.5 over the nut, and three
    # clips standing 0.25 proud of the nut's flats, free to flex, with a slot behind each
    pocket = hex_cut(p, p.floor, p.nut_h + p.recess, across=p.nut_af + 0.5)
    body = blank(p).cut(bolt_hole(p)).cut(pocket)
    for i in range(3):
        slot = cq.Workplane("XY").workplane(offset=p.floor).center(p.nut_af / 2 + 1.1, 0).rect(2.4, 3.6).extrude(p.nut_h + p.recess)
        clip = cq.Workplane("XY").workplane(offset=p.floor - 0.5).center(p.nut_af / 2 + 0.25, 0).rect(1, 2.2).extrude(p.nut_h + 0.5)
        turn = 30 + 120 * i
        body = body.cut(slot.rotate((0, 0, 0), (0, 0, 1), turn)).union(clip.rotate((0, 0, 0), (0, 0, 1), turn))
    return body
'''
RIBS = HELPERS + '''
def build(p):
    # as Gemini 4 Argon's knob: a hex with a thin crush rib standing on each flat
    across = p.nut_af + p.clearance + 0.3
    body = blank(p).cut(bolt_hole(p)).cut(hex_cut(p, p.floor, p.nut_h + p.recess, across=across))
    for i in range(6):
        rib = cq.Workplane("XY").workplane(offset=p.floor).center(across / 2 - 0.1, 0).rect(0.3, 1).extrude(p.nut_h)
        body = body.union(rib.rotate((0, 0, 0), (0, 0, 1), 30 + 60 * i))
    return body
'''
SNAP_RING = HELPERS + '''
def build(p):
    # as GLM 5.3 Flash's knob: a narrower hex band near the mouth, with a wider seat below it
    body = blank(p).cut(bolt_hole(p)).cut(pocket_on_top(p))
    ring = hex_cut(p, height(p) - 1, 0.8, across=p.nut_af + p.clearance)
    wide = hex_cut(p, p.floor, p.nut_h + p.recess - 1, across=p.nut_af + p.clearance + 0.4)
    return blank(p).cut(bolt_hole(p)).cut(wide).cut(ring).cut(hex_cut(p, height(p) - 0.2, 1, across=p.nut_af + p.clearance + 0.4))
'''
SPLIT_FINGERS = HELPERS + '''
def build(p):
    # as GPT-6 Luna's M3 knob: slits run out through the wall, so the pocket's walls are separate fingers
    body = blank(p).cut(bolt_hole(p)).cut(pocket_at_bed(p))
    for i in range(6):
        slit = cq.Workplane("XY").box(p.knob_d, 0.8, p.nut_h + 1, centered=(False, True, False))
        body = body.cut(slit.rotate((0, 0, 0), (0, 0, 1), 60 * i))
    return body
'''
SHALLOW_HEX_UNDER_BORE = HELPERS + '''
def build(p):
    # 0.4 mm of hex at the bottom, and above it a round bore the nut could spin in
    bore = cq.Workplane("XY").workplane(offset=p.floor + 0.4).circle(1.15 * p.nut_af / 2 + 0.2).extrude(p.nut_h)
    return blank(p).cut(bolt_hole(p)).cut(hex_cut(p, p.floor, 0.4)).cut(bore)
'''
SLEEVE_IN_POCKET = HELPERS + '''
def build(p):
    # a printed sleeve stands in the middle of the pocket, where the nut's thread would go
    sleeve = cq.Workplane("XY").workplane(offset=p.floor).circle(3.5).circle(p.bolt_hole / 2).extrude(p.nut_h)
    return blank(p).cut(bolt_hole(p)).cut(pocket_on_top(p)).union(sleeve)
'''
THROUGH_HEX = HELPERS + '''
def build(p):
    return blank(p).cut(hex_cut(p, 0, height(p)))
'''
WIDE_CHAMFER = HELPERS + '''
def build(p):
    # with recess = 0: a pocket exactly the nut's height, with a 1 mm chamfer round its mouth
    return blank(p).cut(bolt_hole(p)).cut(pocket_on_top(p)).cut(chamfer_on_top(p, 1))
'''
ON_ITS_SIDE = HELPERS + '''
def build(p):
    knob = blank(p).cut(bolt_hole(p)).cut(pocket_on_top(p))
    return knob.rotate((0, 0, 0), (1, 0, 0), 90).translate((0, 0, p.knob_d / 2))
'''
BED_POCKET_CONE_ROOF = HELPERS + '''
def build(p):
    # a 45 degree cone from the pocket's roof down to the bolt hole, so nothing needs a bridge
    roof = p.nut_h + p.recess
    r = (p.nut_af + p.clearance) / 2
    cone = cq.Workplane(cq.Solid.makeCone(r, p.bolt_hole / 2, r - p.bolt_hole / 2, cq.Vector(0, 0, roof), cq.Vector(0, 0, 1)))
    return blank(p).cut(pocket_at_bed(p)).cut(cone).cut(bolt_hole(p))
'''
RELIEF_UNDER_POCKET = HELPERS + '''
def build(p):
    relief = cq.Workplane("XY").workplane(offset=p.floor - 1).circle(3.5).extrude(1)
    return blank(p).cut(bolt_hole(p)).cut(pocket_on_top(p)).cut(relief)
'''
RAISED_NUB = HELPERS + '''
def build(p):
    # as DeepSeek V4.1 Flash's M3 test print: a 1.5 mm marker standing on the top face, off to one side
    nub = cq.Workplane("XY").workplane(offset=height(p)).center(p.knob_d / 2 - 3, 0).rect(2, 2).extrude(1.5)
    return blank(p).cut(bolt_hole(p)).cut(pocket_on_top(p)).union(nub)
'''
HEX_CELLS = HELPERS + '''
def build(p):
    # six nut-sized hex cells run all the way through for lightening; the pocket in the middle is blind
    cells = cq.Workplane("XY").polarArray(12, 0, 360, 6).polygon(6, (p.nut_af + p.clearance) / math.cos(math.radians(30))).extrude(height(p))
    return cq.Workplane("XY").circle(18).extrude(height(p)).cut(cells).cut(pocket_on_top(p))
'''


def coupon_code(clearances, depth, closed=False):
    """A bar with one pocket per clearance, this deep. closed: each has a roof, so no nut can get in."""
    roof = 2 if closed else 0
    return HELPERS + f'''
def build(p):
    cs = {list(clearances)}
    bar = cq.Workplane("XY").box(16 * len(cs), 16, 1.6 + {depth} + {roof}, centered=(False, True, False))
    for i, c in enumerate(cs):
        bar = bar.cut(hex_cut(p, 1.6, {depth}, across=p.nut_af + c).translate((8 + 16 * i, 0, 0)))
    return bar
'''


def design(nut="M5", code=None, **params):
    """The nut's reference, with some params changed or its part's code replaced."""
    sub = submission.parse(tasks.load(f"nut-knob/{nut}").reference)
    for name, value in params.items():
        sub.params[name].value = value
    if code is not None:
        sub.parts[0].code = code
    return sub


def with_coupon(sub, clearances=(0.0, 0.1, 0.2, 0.3), depth=3, closed=False, in_manual=True):
    sub.parts.append(sub.parts[0].model_copy(update={"id": "coupon", "role": "coupon", "code": coupon_code(clearances, depth, closed)}))
    if in_manual:
        sub.manual.insert(0, submission.Step(n="0", text="Print the coupon first and try the nut in each pocket.", parts=["coupon"]))
    return sub


def with_second_part(sub):
    sub.parts.append(sub.parts[0].model_copy(update={"id": "knob2"}))
    return sub


def told(sub, text):
    sub.manual.insert(1, submission.Step(n="1b", text=text, parts=["knob"]))
    return sub


def told_to_drill(sub):
    return told(sub, "Drill out the thin layer over the pocket with a 5.5 mm bit.")


@pytest.mark.parametrize("nut", ["M3", "M5", "M8"])
def test_reference_passes_every_check(tmp_path, nut):
    findings = grade(design(nut), tmp_path)
    assert all(f.ok is True for f in findings), not_passing(findings)


@pytest.mark.parametrize("sub, want_failed, want_not_graded", [
    # prints settle that this clearance fails, and no test print would have caught it
    pytest.param(design("M3", clearance=0.0), {"R4"}, set(), id="wont-go-in"),
    pytest.param(design("M5", clearance=0.3), {"R4"}, set(), id="falls-out"),
    # no print has settled this clearance: not graded, which is still not a pass
    pytest.param(design("M5", clearance=0.15), set(), {"R4"}, id="between-steps"),
    pytest.param(design("M5", clearance=0.2), set(), {"R4"}, id="loose-nobody-turned-over"),
    # the pocket itself is wrong, so the checks that need a hex pocket can't say
    pytest.param(design(code=ROUND_POCKET), {"R3"}, {"R4", "R5"}, id="round-pocket"),
    pytest.param(design(nut_af=13.0), {"R3"}, {"R4", "R5"}, id="an-M8-pocket-in-an-M5-knob"),
    pytest.param(design(recess=-2), {"R3"}, set(), id="shallow-2.7-for-a-4.7-nut"),
    pytest.param(design(code=CLOSED_POCKET), {"R3"}, {"bridges"}, id="closed-under-a-roof-with-a-narrow-ledge"),
    pytest.param(design(code=ROUND_COLLAR_ABOVE), {"R3"}, {"R4"}, id="round-collar-the-corners-cant-pass"),
    pytest.param(design(code=FILLETED_SQUARE), {"R3"}, {"R4", "R5"}, id="filleted-square-as-wide-as-the-hex"),
    pytest.param(design(code=PENTAGON), {"R3"}, {"R4", "R5"}, id="pentagon"),
    pytest.param(design(code=SHALLOW_HEX_UNDER_BORE), {"R3"}, set(), id="0.4mm-of-hex-under-a-round-bore"),
    pytest.param(design(code=SLEEVE_IN_POCKET), {"R3"}, {"R4", "R5"}, id="sleeve-standing-in-the-pocket"),
    pytest.param(design(code=THROUGH_HEX), {"R3"}, set(), id="hex-right-through-so-it-can-go-out-the-far-side"),
    # the bolt can't get through
    pytest.param(design(code=NO_THROUGH_HOLE), {"R5"}, set(), id="no-through-hole"),
    pytest.param(design(bolt_hole=5.0), {"R5"}, set(), id="bolt-hole-at-the-bolts-own-diameter"),
    pytest.param(design(code=OFF_CENTRE_HOLE), {"R5"}, set(), id="off-centre-bolt-hole"),
    pytest.param(design(code=HEX_CELLS, knob_d=36), {"R5"}, set(), id="a-hex-lightening-cell-isnt-the-nuts-path"),
    pytest.param(design(code=BED_POCKET_DRILL_OUT), {"R5"}, set(), id="closed-layer-nobody-told-to-clear"),
    # two printed parts; the checks that need one part can't say
    pytest.param(with_second_part(design()), {"R1"}, {"R2", "R3", "R4", "R5"}, id="two-parts"),
    # a coupon doesn't rescue it: nothing on it holds, a nut can't get in or only barely,
    # the manual never mentions it, or the pocket can't be changed to match its answer
    pytest.param(with_coupon(design(clearance=0.3), clearances=(0.3, 0.4, 0.5)), {"R4"}, set(), id="coupon-nothing-holds"),
    pytest.param(with_coupon(design(clearance=0.3), closed=True), {"R4"}, set(), id="coupon-sealed"),
    pytest.param(with_coupon(design(clearance=0.3), depth=1.2), {"R4"}, set(), id="coupon-too-shallow"),
    pytest.param(with_coupon(design(clearance=0.3), in_manual=False), {"R4"}, set(), id="coupon-not-in-the-manual"),
    pytest.param(with_coupon(design(code=HARD_CODED_POCKET)), {"R4"}, set(), id="coupon-but-hard-coded-pocket"),
])
def test_wrong_designs_fail_only_their_check(tmp_path, sub, want_failed, want_not_graded):
    findings = grade(sub, tmp_path)
    assert (failed(findings), not_graded(findings)) == (want_failed, want_not_graded), not_passing(findings)


@pytest.mark.parametrize("sub, says", [
    pytest.param(with_coupon(design("M3", clearance=0.0), clearances=(0.0,)), "would show the size is wrong", id="only-the-wrong-size"),
    pytest.param(with_coupon(design(clearance=0.3), in_manual=False), "no test print in the manual", id="not-in-the-manual"),
    pytest.param(with_coupon(design(clearance=0.3), depth=1.2), "no pocket a nut could try", id="too-shallow"),
    pytest.param(with_coupon(design(code=HARD_CODED_POCKET)), "no param moves the pocket", id="hard-coded-pocket"),
])
def test_r4_says_why_a_test_print_doesnt_rescue_it(tmp_path, sub, says):
    r4 = next(finding for finding in grade(sub, tmp_path) if finding.check == "R4")
    assert r4.ok is False and says in r4.detail, r4.detail


@pytest.mark.parametrize("sub", [
    pytest.param(with_coupon(design(clearance=0.3)), id="coupon-rescues-a-clearance-that-falls-out"),
    pytest.param(with_coupon(design(clearance=0.15)), id="coupon-rescues-one-no-print-measured"),
    pytest.param(with_coupon(design("M3", clearance=0.0)), id="coupon-rescues-one-the-nut-wont-go-into"),
    pytest.param(design(code=BED_POCKET_STEPPED_ROOF), id="bed-pocket-stepped-roof-as-coupon-As-S"),
    pytest.param(design("M8", code=BED_POCKET_STEPPED_ROOF), id="bed-pocket-stepped-roof-M8"),
    pytest.param(design("M3", code=BED_POCKET_PLAIN_HOLE), id="bed-pocket-M3-ledge-is-an-ordinary-overhang"),
    pytest.param(design(code=BED_POCKET_CONE_ROOF), id="bed-pocket-cone-roof-narrower-than-the-nut"),
    pytest.param(told_to_drill(design(code=BED_POCKET_DRILL_OUT)), id="closed-layer-the-manual-says-to-clear"),
    pytest.param(design(code=CHAMFERED_MOUTH), id="chamfered-mouth"),
    pytest.param(design(code=WIDE_CHAMFER, recess=0), id="1mm-chamfer-on-a-pocket-exactly-the-nuts-height"),
    pytest.param(design(code=RELIEF_UNDER_POCKET), id="round-relief-under-the-pocket"),
    pytest.param(design(code=LIGHTENED, knob_d=36), id="deeper-round-holes-elsewhere"),
    pytest.param(design(code=FILLETED_HEX), id="corners-rounded-a-little"),
    pytest.param(design(code=ROTATED_HEX), id="hex-rotated-17-degrees"),
])
def test_right_designs_that_differ_from_the_reference_pass(tmp_path, sub):
    findings = grade(sub, tmp_path)
    assert all(f.ok is True for f in findings), not_passing(findings)


@pytest.mark.parametrize("nut", ["M5", "M8"])
def test_a_bed_pocket_with_a_plain_hole_is_not_measured(tmp_path, nut):
    # its roof is a ring 1.3 to 3 mm wide around the hole. It fails the strand test, but it's
    # narrower than any roof seen to tangle (3.1 mm, the Arca plate) and wider than the 1.5 mm
    # allowance, so no print can say. Everything else about the design passes.
    findings = grade(design(nut, code=BED_POCKET_PLAIN_HOLE), tmp_path)
    assert (failed(findings), not_graded(findings)) == (set(), {"bridges"})


@pytest.mark.parametrize("sub", [
    pytest.param(with_coupon(design("M8", clearance=0.3), clearances=(0.05, 0.15, 0.25, 0.35), depth=5), id="M8-grid-between-the-steps"),
    pytest.param(with_coupon(design(clearance=0.3), clearances=(0.15, 0.25)), id="M5-grid-between-the-steps"),
    pytest.param(with_coupon(design(clearance=0.3), clearances=(0.2, 0.3)), id="M5-loose-nobody-turned-over"),
])
def test_a_coupon_no_print_can_judge_is_not_a_failure(tmp_path, sub):
    findings = grade(sub, tmp_path)
    assert (failed(findings), not_graded(findings)) == (set(), {"R4"}), not_passing(findings)


def test_the_deeper_of_two_hex_pockets_on_one_axis_is_the_nuts(tmp_path):
    # the recess's own roof is a narrow ledge round the bolt hole, which no print has measured
    findings = grade(design(code=SECOND_HEX_RECESS), tmp_path)
    assert (failed(findings), not_graded(findings)) == (set(), {"bridges"})


@pytest.mark.parametrize("sub", [
    # GPT-6.1 Sol's and Grok 4.7's clips read as "no hex pocket" and "+0.50, falls out" before,
    # because the shape test aimed the nut's corner at a slot's end. The hex is there, and the
    # clips may well hold, but coupon B only measured plain pockets.
    pytest.param(design(code=SPRING_CLIPS), id="clips"),
    pytest.param(design(code=RIBS), id="ribs"),
    pytest.param(design(code=SNAP_RING), id="snap-ring"),
    pytest.param(design("M3", code=SNAP_RING, clearance=0.0), id="snap-ring-M3-not-wont-go-in"),
    pytest.param(design(code=RELIEVED_CORNERS), id="corner-relief"),
    pytest.param(design(code=RELIEF_SLOTS), id="slots-out-from-three-flats"),
    pytest.param(with_coupon(design(code=RIBS)), id="a-plain-coupon-cant-speak-for-ribs"),
])
def test_a_pocket_that_isnt_plain_is_not_graded(tmp_path, sub):
    findings = grade(sub, tmp_path)
    assert (failed(findings), not_graded(findings)) == (set(), {"R4"}), not_passing(findings)


def test_a_raised_feature_beside_the_pockets_mouth_doesnt_close_it(tmp_path):
    # above the top face, the nut's place is open air outside the part's outline: that doesn't block
    # it. It used to read as closed (issue 15, the pocket-reader bug)
    sub = design(code=RAISED_NUB)
    findings = grade(sub, tmp_path)
    assert (failed(findings), not_graded(findings)) == (set(), set()), not_passing(findings)
    with_coupon(sub, clearances=(0.0, 0.2), depth=5)
    sub.parts[1].code = sub.parts[1].code.replace("return bar", "return bar.union(cq.Workplane('XY').box(2, 2, 1.6 + 5 + 1.5, centered=(True, True, False)))")
    coupon = build_parts(checked(sub), tmp_path / "coupon")["coupon"]
    assert [found.opens for found in nuts.find_pockets(coupon.mesh, 8.0)] == [["top"], ["top"]]


def test_fingers_split_by_slits_are_not_graded_rather_than_failed(tmp_path):
    findings = grade(design("M3", code=SPLIT_FINGERS), tmp_path)
    assert {"R3", "R4", "R5"} <= not_graded(findings) and failed(findings) == set(), not_passing(findings)


def test_a_knob_printed_on_its_side_is_not_graded_rather_than_failed(tmp_path):
    findings = grade(design(code=ON_ITS_SIDE), tmp_path)
    assert {"R3", "R4", "R5"} <= not_graded(findings) and failed(findings) == set()


def test_a_crash_in_a_design_is_one_failure(tmp_path):
    # code that doesn't run fails `builds`; the requirement checks can't say anything about it
    findings = grade(design(code="def build(p):\n    raise ValueError('no')\n"), tmp_path)
    assert failed(findings) == {"builds"}
    assert not_graded(findings) == {"R2", "R3", "R4", "R5"}


@pytest.mark.parametrize("label, clearance, expected", [
    ("M3", 0.0, "won't go in"), ("M3", 0.2, "holds"), ("M3", 0.3, "holds"),
    ("M3", 0.1, "holds"),          # coded "won't go in"; Dan: "with force it goes in" (nuts.READ_AS)
    ("M5", 0.0, "holds"), ("M5", 0.1, "holds"), ("M5", 0.2, "loose"), ("M5", 0.3, "falls out"),
    ("M8", 0.0, "holds"), ("M8", 0.1, "loose"), ("M8", 0.2, "loose"), ("M8", 0.3, "falls out"),
    ("M5", 0.05, "holds"),         # between two steps that agree
    ("M8", 0.15, "loose"),
    ("M3", 0.15, "holds"),
    ("M3", 0.05, None),            # Gemini 4 Argon's M3 knob, between two that disagree
    ("M5", 0.15, None),
    ("M5", 0.25, None),
    ("M8", 0.05, None),
    ("M3", -0.2, "won't go in"),   # tighter than "won't go in" is settled
    ("M5", -0.1, None),            # tighter than "holds" isn't: it might not go in
    ("M3", 0.5, None),             # looser than "holds" isn't: it might fall out
    ("M5", 0.5, "falls out"),      # looser than "falls out" is settled
])
def test_verdict_reads_what_the_prints_say(label, clearance, expected):
    assert nuts.verdict(label, clearance) == expected


@pytest.mark.parametrize("label, clearance, expected", [
    ("M3", -0.1, False), ("M5", 0.3, False), ("M8", 0.3, False), ("M8", 0.5, False),
    ("M3", 0.2, True), ("M5", 0.05, True), ("M8", 0.0, True),
    ("M5", 0.2, None), ("M8", 0.1, None), ("M8", 0.2, None),   # "loose": nobody has turned them over
    ("M5", 0.15, None), ("M5", -0.1, None), ("M3", 1.2, None), ("M3", 0.05, None),   # no print says
    ("M3", 0.1, True), ("M3", 0.15, True),   # with force it goes in (nuts.READ_AS)
])
def test_holds_is_settled_only_where_prints_settle_it(label, clearance, expected):
    assert nuts._holds(label, clearance) is expected


@pytest.mark.parametrize("sentence, tells", [
    ("Drill out the thin layer over the pocket with a 5.5 mm bit.", True),
    ("Drill out the thin layer with a 5.5 mm bit, taking care not to enlarge the pocket.", True),
    ("Poke through the sacrificial layer with an awl.", True),
    ("Open the hole with a drill.", True),
    ("Clear the build plate before printing.", False),
    ("No need to drill the hole.", False),
    ("The bolt hole doesn't need drilling.", False),
    ("Don\u2019t drill the hole.", False),
    ("Thread the bolt through the clearance hole.", False),
    ("Remove the brim from the first layer.", False),
    ("Press the nut in and check the hole", False),
    ("From the top face, run a hobby knife round the inside of the slot and push the skin out.", True),  # Opus 5.5, loop-tripod
    ("Cut the thin layer out with a hobby knife.", True),
    ("Push the bolt out of the hole.", False),
    ("Pop the plate off the bed.", False),
])
def test_what_counts_as_being_told_to_clear_a_layer(sentence, tells):
    sub = told(design(), sentence)
    sub.manual[1].tool = "drill press"  # a tool on its own doesn't tell anyone to open a layer
    assert (nuts.sentence_saying_to_clear_it(sub) is not None) is tells
