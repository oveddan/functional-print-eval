"""The M5 spacer control task: the reference passes every check, and deliberately
wrong designs fail the check aimed at them."""
import pytest

from pbe.graders import requirements
from pbe.parts import submission
from pbe.runner import tasks

from helpers import failed, grade

TASK = tasks.load("m5-spacer")
REF = submission.parse(TASK.reference)

BLIND_HOLE = '''
def build(p):
    body = cq.Workplane("XY").circle(p.od / 2).extrude(p.length)
    return body.faces(">Z").workplane().hole(p.hole_d, depth=p.length / 2)
'''
PLUGGED = '''
def build(p):
    body = cq.Workplane("XY").circle(p.od / 2).circle(p.hole_d / 2).extrude(p.length)
    plug = cq.Workplane("XY").workplane(offset=5).circle(p.hole_d / 2 + 0.1).extrude(1)
    return body.union(plug)
'''
SQUARE = '''
def build(p):
    return cq.Workplane("XY").rect(p.od, p.od).circle(p.hole_d / 2).extrude(p.length)
'''
OVAL_HOLE = '''
def build(p):
    body = cq.Workplane("XY").circle(p.od / 2).extrude(p.length)
    return body.cut(cq.Workplane("XY").ellipse(3.05, 2.45).extrude(p.length))
'''

CHAMFERED = '''
def build(p):
    r, c = p.hole_d / 2, 0.6
    body = cq.Workplane("XY").circle(p.od / 2).circle(r).extrude(p.length)
    bottom = cq.Workplane(cq.Solid.makeCone(r + c, r, c, cq.Vector(0, 0, 0), cq.Vector(0, 0, 1)))
    top = cq.Workplane(cq.Solid.makeCone(r + c, r, c, cq.Vector(0, 0, p.length), cq.Vector(0, 0, -1)))
    return body.cut(bottom).cut(top)
'''
SLOT = '''
def build(p):
    body = cq.Workplane("XY").circle(p.od / 2).extrude(p.length)
    return body.cut(cq.Workplane("XY").slot2D(8, p.hole_d).extrude(p.length))
'''
NECKED = '''
def build(p):
    body = cq.Workplane("XY").circle(p.od / 2).circle(4).extrude(p.length)
    neck = cq.Workplane("XY").workplane(offset=p.length / 2).circle(4.1).circle(p.hole_d / 2).extrude(0.4)
    return body.union(neck)
'''
LONG_COUNTERBORE = '''
def build(p):
    # 5.5 mm for 40% of the length, then a 8.6 mm head counterbore
    body = cq.Workplane("XY").circle(p.od / 2).circle(p.hole_d / 2).extrude(p.length)
    return body.cut(cq.Workplane("XY").workplane(offset=0.4 * p.length).circle(4.3).extrude(0.6 * p.length))
'''


def variant(hole_d=None, length=None, code=None, extra_part=False):
    sub = REF.model_copy(deep=True)
    if hole_d is not None:
        sub.params["hole_d"].value = hole_d
    if length is not None:
        sub.params["length"].value = length
    if code is not None:
        sub.parts[0].code = code
    if extra_part:
        sub.parts.append(sub.parts[0].model_copy(update={"id": "spacer2"}))
    return sub


def test_request_is_the_blockquote():
    assert TASK.request.startswith("I need a round spacer") and TASK.hidden_facts == {}


def test_only_the_first_blockquote_is_the_request(tmp_path, monkeypatch):
    d = tmp_path / "tasks" / "t"
    d.mkdir(parents=True)
    (d / "brief.md").write_text("# T\n\n> Make a hook.\n> For my coat.\n\nNotes:\n\n> the agent assumed 10 mm\n")
    (d / "hidden_facts.yaml").write_text("{}")
    (d / "requirements.yaml").write_text("[]")
    monkeypatch.setattr(tasks, "ROOT", tmp_path)
    assert tasks.load("t").request == "Make a hook.\nFor my coat."


@pytest.mark.parametrize("hole_d", [5.3, 5.5, 5.8])  # ISO 273 fine, medium, coarse
def test_reference_and_range_edges_pass(tmp_path, hole_d):
    findings = grade(variant(hole_d=hole_d), tmp_path)
    assert failed(findings) == set(), [f for f in findings if not f.ok]
    assert all(f.ok is True for f in findings)  # the runner tests `is True`; a numpy bool fails it


@pytest.mark.parametrize("sub, expect", [
    (variant(hole_d=5.0), {"R3"}),        # the bolt's own diameter: no clearance
    (variant(hole_d=5.81), {"R3"}),       # just over ISO 273 coarse
    (variant(hole_d=6.5), {"R3"}),        # sloppy
    (variant(code=OVAL_HOLE), {"R3"}),    # same area as a 5.5 hole, but only 4.9 clear
    (variant(code=SLOT), {"R3"}),         # 5.5 clear but 8 long: the bolt isn't located
    (variant(code=BLIND_HOLE), {"R3"}),   # stops halfway
    (variant(code=PLUGGED), {"R3"}),      # a 1 mm plug across the bore
    (variant(code=NECKED), {"R3"}),       # an 8 mm bore with one 0.4 mm neck at 5.5
    (variant(code=SQUARE), {"R4"}),       # the request says round
    (variant(length=18), {"R2"}),
    (variant(length=10), {"R2"}),         # shorter than it is wide; the hole is still found
    (variant(extra_part=True), {"R1"}),   # the checks that need one part report not graded
], ids=["hole-5.0", "hole-5.81", "hole-6.5", "oval-hole", "slot", "blind-hole", "plugged", "necked", "square",
        "length-18", "length-10", "two-parts"])
def test_wrong_designs_fail_only_their_check(tmp_path, sub, expect):
    assert failed(grade(sub, tmp_path)) == expect


def test_a_counterbore_can_take_most_of_the_hole(tmp_path):
    assert failed(grade(variant(code=LONG_COUNTERBORE), tmp_path)) == set()


def test_lead_in_chamfers_pass(tmp_path):
    # Qwen 3.8 Flash's spacer (run pilot-spacer): a 5.5 bore with 0.6 mm chamfers at both
    # ends. The first version of R3 failed it for being 6.5 wide at the ends.
    assert failed(grade(variant(code=CHAMFERED), tmp_path)) == set()


def test_a_crashing_grader_is_a_failure_not_a_crash(monkeypatch):
    def boom(sub, built):
        raise ValueError("bad geometry")
    monkeypatch.setitem(requirements.GRADERS, "dims.boom", boom)
    task = tasks.Task("t", "x", {}, [tasks.Requirement(id="R9", text="t", grader="dims.boom")], None)
    [f] = requirements.grade(task, REF, {})
    assert f.ok is False and "bad geometry" in f.detail
