"""The tripod plate: the reference passes every check, wrong designs fail the check aimed at
them and no other, and designs unlike the reference still pass. Not graded (ok = None) is kept
apart from failed: it's what a check says when no recorded print can decide the case."""
import pytest
import yaml

from pbe import agent, submission, tasks

REFERENCE = tasks.load("tripod-plate").reference


def design(hardware=None, code=None, **params):
    """The reference, changed only where a test says."""
    data = yaml.safe_load(REFERENCE)
    for name, value in params.items():
        data["params"][name]["value"] = value
    if hardware is not None:
        data["hardware"] = hardware
        data["criteria"] = []
        for step in data["manual"]:
            step["hardware"] = []
    if code is not None:
        data["parts"][0]["code"] = code
    return submission.Submission.model_validate(data)


def grade(sub, tmp_path):
    return agent.grade(tasks.load("tripod-plate"), sub, tmp_path)


def failed(findings):
    return {f.check for f in findings if f.ok is False}


def not_graded(findings):
    return {f.check for f in findings if f.ok is None}


REFERENCE_CODE = yaml.safe_load(REFERENCE)["parts"][0]["code"]

# Plain shapes for designs that don't look like the reference. p has the reference's params.
OUTLINE = '''
def blank(p, narrow=True):
    w, top = p.width / 2, p.width / 2 - (p.bevel if narrow else 0)
    outline = [(-w, 0), (w, 0), (w, p.land), (top, p.land + p.bevel), (top, p.height),
               (-top, p.height), (-top, p.land + p.bevel), (-w, p.land)]
    return cq.Workplane("XZ").polyline(outline).close().extrude(p.length / 2, both=True)

def round_recess(p, z=0):
    return cq.Workplane("XY").workplane(offset=z).circle(p.head_d / 2).extrude(p.head_h)

def round_hole(p):
    return cq.Workplane("XY").circle(p.hole / 2).extrude(p.height)

def stepped_roof(p):
    # the recess's roof bridges in two steps, so it prints on its own
    strip = cq.Workplane("XY").workplane(offset=p.head_h).rect(p.hole, p.head_d).extrude(p.step)
    return strip.union(cq.Workplane("XY").workplane(offset=p.head_h).rect(p.hole, p.hole).extrude(2 * p.step))
'''

ROUND_HOLE = OUTLINE + '''
def build(p):
    return blank(p).cut(round_recess(p)).cut(stepped_roof(p)).cut(round_hole(p))
'''
STRAIGHT_SIDES = OUTLINE + '''
def build(p):
    return blank(p, narrow=False).cut(round_recess(p)).cut(stepped_roof(p)).cut(round_hole(p))
'''
RECESS_ON_CAMERA_SIDE = OUTLINE + '''
def build(p):
    return blank(p).cut(round_recess(p, p.height - p.head_h)).cut(round_hole(p))
'''
HEAD_SLIDES_IN_FROM_THE_END = OUTLINE + '''
def build(p):
    channel = cq.Workplane("XY").center(0, -p.length / 4).rect(p.head_d, p.length / 2).extrude(p.head_h)
    return blank(p).cut(round_recess(p)).cut(channel).cut(stepped_roof(p)).cut(round_hole(p))
'''
CONE_ROOF = OUTLINE + '''
def build(p):
    cone = cq.Solid.makeCone(p.head_d / 2, p.hole / 2, (p.head_d - p.hole) / 2, pnt=cq.Vector(0, 0, p.head_h))
    return blank(p).cut(round_recess(p)).cut(cq.Workplane(obj=cone)).cut(round_hole(p))
'''
RELIEF_ON_THE_CAMERA_SIDE = OUTLINE + '''
def build(p):
    relief = cq.Workplane("XY").workplane(offset=p.height - 3.5).circle(4.5).extrude(3.5)
    return blank(p).cut(round_recess(p)).cut(stepped_roof(p)).cut(relief).cut(round_hole(p))
'''
LIP_ON_THE_CAMERA_FACE = OUTLINE + '''
def build(p):
    lip = cq.Workplane("XY").workplane(offset=p.height).center(0, p.length / 2 - 2).rect(20, 4).extrude(2)
    return blank(p).union(lip).cut(round_recess(p)).cut(stepped_roof(p)).cut(round_hole(p))
'''
PIN_HOLE = '''
    pin = cq.Workplane("XY").center(0, 22).circle(1.5).extrude(p.height)
'''
NO_RECESS_AND_A_PIN_HOLE = OUTLINE + '''
def build(p):''' + PIN_HOLE + '''    return blank(p).cut(round_hole(p)).cut(pin)
'''
CHANNEL_AND_A_PIN_HOLE = OUTLINE + '''
def build(p):''' + PIN_HOLE + '''    channel = cq.Workplane("XY").center(0, -p.length / 4).rect(p.head_d, p.length / 2).extrude(p.head_h)
    return blank(p).cut(round_recess(p)).cut(channel).cut(stepped_roof(p)).cut(round_hole(p)).cut(pin)
'''
STRAIGHT_WITH_A_RAISED_PAD = OUTLINE + '''
def build(p):
    pad = cq.Workplane("XY").workplane(offset=p.height).rect(30, 30).extrude(1)
    return blank(p, narrow=False).union(pad).cut(round_recess(p)).cut(stepped_roof(p)).cut(round_hole(p))
'''
ONE_BEVEL = OUTLINE + '''
def build(p):
    w = p.width / 2
    outline = [(-w, 0), (w, 0), (w, p.height), (-w + p.bevel, p.height), (-w, p.height - p.bevel)]
    body = cq.Workplane("XZ").polyline(outline).close().extrude(p.length / 2, both=True)
    return body.cut(round_recess(p)).cut(stepped_roof(p)).cut(round_hole(p))
'''
GROOVE_AND_A_NARROW_TOP = OUTLINE + '''
def build(p):
    w, neck = p.width / 2, p.width / 2 - 2
    outline = [(-w, 0), (w, 0), (w, 3), (neck, 5), (neck, 6), (w, 8), (neck, p.height), (-neck, p.height), (-w, 8), (-neck, 6), (-neck, 5), (-w, 3)]
    body = cq.Workplane("XZ").polyline(outline).close().extrude(p.length / 2, both=True)
    return body.cut(round_recess(p)).cut(stepped_roof(p)).cut(round_hole(p))
'''
NO_RECESS = OUTLINE + '''
def build(p):
    return blank(p).cut(round_hole(p))
'''
PRINTED_NARROW_FACE_DOWN = OUTLINE + '''
def build(p):
    plate = blank(p).cut(round_recess(p)).cut(stepped_roof(p)).cut(round_hole(p))
    return plate.rotate((0, 0, 0), (1, 0, 0), 180).translate((0, 0, p.height))
'''
# from Gemini 3.8 Flash's plate: a V-groove in the side, flat camera face on the bed, recess on top
GROOVE_IN_THE_SIDE = """
def build(p):
    w, neck = p.width / 2, p.width / 2 - 2.5
    outline = [(-w, 0), (w, 0), (w, 3), (neck, 5.5), (w, 8), (w - 2, 10), (-w + 2, 10), (-w, 8), (-neck, 5.5), (-w, 3)]
    plate = cq.Workplane("XZ").polyline(outline).close().extrude(p.length / 2, both=True)
    recess = cq.Workplane("XY").workplane(offset=p.height - p.head_h).circle(p.head_d / 2).extrude(p.head_h)
    return plate.cut(recess).cut(cq.Workplane("XY").circle(p.hole / 2).extrude(p.height))
"""
TWO_HOLES = OUTLINE + '''
def build(p):
    locating_pin = cq.Workplane("XY").center(0, 22).circle(2).extrude(p.height)
    return blank(p).cut(round_recess(p)).cut(stepped_roof(p)).cut(round_hole(p)).cut(locating_pin)
'''


def test_reference_passes_every_check(tmp_path):
    findings = grade(design(), tmp_path)
    assert all(f.ok is True for f in findings), [f for f in findings if f.ok is not True]


@pytest.mark.parametrize("sub, want_failed, want_not_graded", [
    # the real first print: the recess the head didn't fit (the depth isn't what stopped it)
    pytest.param(design(head_d=13), {"R4"}, set(), id="recess-13-too-tight"),
    pytest.param(design(head_d=14), set(), {"R4"}, id="recess-14-between-records"),
    pytest.param(design(head_h=4, height=9), set(), {"R4"}, id="recess-4-deep-never-tried"),
    pytest.param(design(code=STRAIGHT_SIDES), {"R2"}, set(), id="straight-sides"),
    pytest.param(design(width=45), set(), {"R2"}, id="width-only-38-was-printed"),
    pytest.param(design(hole=6), {"R3"}, set(), id="hole-under-the-thread"),
    pytest.param(design(hole=6.5), set(), {"R3"}, id="hole-between-thread-and-printed"),
    pytest.param(design(code=RECESS_ON_CAMERA_SIDE), {"R3"}, set(), id="head-on-the-camera-side"),
    pytest.param(design(height=15), {"R5"}, set(), id="too-much-plate-for-the-bolt"),
    pytest.param(design(code=NO_RECESS, height=6, bevel=2), set(), {"R4"}, id="no-recess-thin-plate"),
    pytest.param(design(code=NO_RECESS_AND_A_PIN_HOLE, height=6, bevel=2), set(), {"R4"}, id="no-recess-and-a-pin-hole"),
    pytest.param(design(code=STRAIGHT_WITH_A_RAISED_PAD), {"R2"}, set(), id="a-raised-pad-is-not-a-dovetail"),
    pytest.param(design(code=ONE_BEVEL), {"R2"}, set(), id="a-bevel-on-one-edge-only"),
    pytest.param(design(hole=6.35), set(), {"R3"}, id="hole-exactly-the-thread"),
    pytest.param(design(hardware=[{"id": "bolt", "ref": "ISO 4762 M5x20"}]), {"R3"}, {"R4", "R5"}, id="a-bolt-that-wont-fit-a-camera"),
    pytest.param(design(hardware=[]), set(), {"R3", "R4", "R5"}, id="printed-screw"),
])
def test_wrong_or_undecided_designs(tmp_path, sub, want_failed, want_not_graded):
    findings = grade(sub, tmp_path)
    assert failed(findings) == want_failed, [f for f in findings if f.ok is False]
    assert not_graded(findings) == want_not_graded, [f for f in findings if f.ok is None]


@pytest.mark.parametrize("sub", [
    pytest.param(design(code=ROUND_HOLE), id="round-hole-no-slot"),
    pytest.param(design(code=PRINTED_NARROW_FACE_DOWN), id="printed-narrow-face-down"),
    pytest.param(design(code=TWO_HOLES), id="a-second-hole-for-a-pin"),
    pytest.param(design(code=GROOVE_IN_THE_SIDE), id="a-groove-in-the-side"),
    pytest.param(design(head_d=16, hole=6.8), id="roomier-recess-tighter-hole"),
    pytest.param(design(code=RELIEF_ON_THE_CAMERA_SIDE), id="a-relief-on-the-camera-side"),
    pytest.param(design(code=LIP_ON_THE_CAMERA_FACE), id="a-lip-on-the-camera-face"),
    pytest.param(design(length=30, slot=2), id="shorter-than-it-is-wide"),
    pytest.param(design(height=10.3), id="depth-read-in-whole-layers"),
    pytest.param(design(code=GROOVE_AND_A_NARROW_TOP), id="a-groove-and-a-narrow-top"),
])
def test_other_correct_designs_pass(tmp_path, sub):
    findings = grade(sub, tmp_path)
    assert all(f.ok is True for f in findings), [f for f in findings if f.ok is not True]


def test_a_recess_open_at_the_side_still_has_a_bolt_hole(tmp_path):
    findings = grade(design(code=HEAD_SLIDES_IN_FROM_THE_END), tmp_path)
    assert {f.check: f.ok for f in findings if f.check in {"R3", "R4", "R5"}} == {"R3": True, "R4": True, "R5": True}


@pytest.mark.parametrize("code", [
    pytest.param(CONE_ROOF, id="a-cone-roof-is-not-the-seat"),
    pytest.param(CHANNEL_AND_A_PIN_HOLE, id="a-channel-and-a-pin-hole"),
])
def test_the_bolt_checks_read_the_real_seat(tmp_path, code):
    findings = grade(design(code=code), tmp_path)
    assert {f.check: f.ok for f in findings if f.check in {"R3", "R4", "R5"}} == {"R3": True, "R4": True, "R5": True}


def test_a_final_part_that_fails_isnt_replaced_by_another(tmp_path):
    data = yaml.safe_load(REFERENCE)
    washer = dict(data["parts"][0], id="washer", code='def build(p):\n    return cq.Workplane("XY").circle(10).circle(3.5).extrude(2)\n')
    data["parts"][0]["code"] = 'def build(p):\n    raise ValueError("no")\n'
    data["parts"].append(washer)
    findings = grade(submission.Submission.model_validate(data), tmp_path)
    assert "builds" in failed(findings)
    assert {"R1", "R2", "R3", "R4", "R5"} <= not_graded(findings)


def test_the_person_answers_what_the_records_say():
    person = agent.Person(tasks.load("tripod-plate").hidden_facts)
    assert "about 15" in person.measure("webcam mount bolt", "head diameter")
    assert "about 5" in person.measure("bolt", "head height")
    assert "angled lips" in person.measure("tripod clamp", "what kind is it")
    assert "1/4-20" in person.measure("my camera's bottom socket", "thread size")


def test_no_plate_says_so_rather_than_blaming_a_screw(tmp_path):
    data = yaml.safe_load(REFERENCE)
    data["parts"][0]["role"] = "coupon"
    data["hardware"], data["criteria"] = [], []
    for step in data["manual"]:
        step["hardware"] = []
    details = {f.check: f.detail for f in grade(submission.Submission.model_validate(data), tmp_path)}
    assert details["R3"] == "no plate built"
