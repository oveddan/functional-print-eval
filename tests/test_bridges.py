"""The bridge rule on shapes with known answers, independent of the Arca plate."""
import cadquery as cq
import pytest
import trimesh

from pbe.graders import checks
from pbe.graders.bridges import is_holed_roof, overhangs
from pbe.parts.build import Built
from pbe.parts.submission import Part, Step, Submission
from pbe.parts.supports import asks_for_supports, printed_with_supports


def mesh(shape, tmp_path):
    path = tmp_path / "part.stl"
    cq.exporters.export(shape, str(path), tolerance=0.01, angularTolerance=0.1)
    return trimesh.load(path)


def block_with_pocket(pocket_w, pocket_l, hole_d=0.0):
    """A 10 mm block with a pocket open at the bed (5 mm deep), and optionally a
    hole straight up through the pocket's roof."""
    body = cq.Workplane("XY").box(pocket_l + 20, pocket_w + 20, 10, centered=(True, True, False))
    body = body.cut(cq.Workplane("XY").workplane(offset=-1).rect(pocket_l, pocket_w).extrude(6))
    if hole_d:
        body = body.cut(cq.Workplane("XY").workplane(offset=-1).circle(hole_d / 2).extrude(12))
    return body


@pytest.mark.parametrize("w, l, hole, ok", [
    (10, 20, 0, True),    # a closed roof over a pocket: strands land on the walls
    (10, 20, 5, False),   # a hole through that roof: strands end at the hole
    (60, 70, 0, False),   # no hole, but every direction spans more than 40 mm
])
def test_pocket_roofs(tmp_path, w, l, hole, ok):
    found = overhangs(mesh(block_with_pocket(w, l, hole), tmp_path))
    assert found, "the roof should need a bridge"
    assert all(o.ok for o in found) is ok, [(o.z, o.anchored, o.longest) for o in found]


def ring_roof(pocket, hole_d=5.5, hexagonal=False):
    """Round 3's ring roofs: a pocket open at the bed under a roof with a bolt hole through it."""
    body = cq.Workplane("XY").box(30, 30, 10, centered=(True, True, False))
    sketch = cq.Workplane("XY").workplane(offset=-1)
    cut = sketch.polygon(6, pocket / 0.8660254) if hexagonal else sketch.circle(pocket / 2)
    body = body.cut(cut.extrude(6))
    return body.cut(cq.Workplane("XY").workplane(offset=-1).circle(hole_d / 2).extrude(12))


@pytest.mark.parametrize("shape, ok", [
    (lambda: ring_roof(8.1, hexagonal=True), True),  # cell 5: 24% anchored, longest 6.0; printed mostly ok and held a nut
    (lambda: ring_roof(9.5), False),                 # cell 2: longest 7.5; messed up
])
def test_a_roof_of_short_strands_passes_however_few_are_anchored(tmp_path, shape, ok):
    found = overhangs(mesh(shape(), tmp_path))
    assert found and all(o.ok for o in found) is ok, [(o.z, o.anchored, o.longest) for o in found]


def roof_cut_by_slot():
    """A 26 x 17 mm pocket roof with a 6 x 24 mm slot through it, cutting the roof in two strips
    (GPT-6 Luna's tripod plate, pilot-tripod t3): no ring inside the roof, but still a hole through it."""
    body = block_with_pocket(17, 26)
    return body.cut(cq.Workplane("XY").workplane(offset=-1).rect(24, 6).extrude(12))


def plate_stepping_out():
    """A plate 30 mm wide for 3 mm, then 40 mm wide: 5 mm ledges whose free edge is the part's outside
    (DeepSeek V4 Pro's can_run_code tripod t2)."""
    base = cq.Workplane("XY").box(30, 55, 3, centered=(True, True, False))
    return base.union(cq.Workplane("XY").workplane(offset=3).box(40, 55, 5, centered=(True, True, False)))


@pytest.mark.parametrize("shape, holed", [
    (lambda: block_with_pocket(10, 20, 5), True),   # the Arca plate's shape: strands end at the hole
    (roof_cut_by_slot, False),                      # since 2026-11-13 it passes: strands run wall to wall beside the slot, and
                                                    # the 1 mm stubs past its ends lie within small_overhang_mm of the wall
    (lambda: block_with_pocket(10, 20), False),     # the same roof closed: it passes
    (lambda: block_with_pocket(60, 70), False),     # fails on span, with nothing cut through it
    (plate_stepping_out, False),                    # fails, but its free edge is the outside
])
def test_a_holed_roof_is_a_failed_roof_with_a_hole_through_it(tmp_path, shape, holed):
    found = overhangs(mesh(shape(), tmp_path))
    assert any(is_holed_roof(o) for o in found) is holed


def test_45_degree_chamfer_needs_no_bridge(tmp_path):
    # a 45 degree overhang is built up a little each layer; nothing to bridge
    part = cq.Workplane("XZ").polyline([(0, 0), (10, 0), (20, 10), (0, 10)]).close().extrude(10)
    assert overhangs(mesh(part, tmp_path)) == []


# a design that says to print with supports passes (Dan, 2026-11-12)

@pytest.mark.parametrize("text, asks", [
    ("Print with supports.", True),
    ("Use tree supports for the pocket roof.", True),
    ("Supports under the bridge, touching the build plate only.", True),
    ("Enable supports in the slicer.", True),
    ("Turn supports ON (auto) - the pocket ceiling is the only overhang.", True),
    ("Use build-plate-only support inside the lower pocket.", True),
    ("Print flat, no supports.", False),
    ("Print it upright without supports.", False),
    ("Supports: none.", False),
    ("The bore is vertical, so it doesn't need supports.", False),
    ("A support-free design: every overhang is 45 degrees.", False),
    ("If your slicer proposes supports inside the bearing bores, turn them off.", False),
    ("The floor supports the nut; the 45 degree sides are self-supporting.", False),
    ("Use supports only if your slicer asks for them.", False),
    ("Check the slide with support maintained over a padded surface.", False),
])
def test_only_a_request_for_supports_counts_as_one(text, asks):
    assert asks_for_supports(text) is asks


def test_an_instruction_covers_the_parts_it_names_or_else_every_part():
    def part(part_id, orientation="flat on the bed"):
        return Part(id=part_id, role="final", material="PLA", code="", print_orientation=orientation, use_orientation="")

    def design(note="", orientation="flat on the bed", step_parts=()):
        steps = [Step(n="1", text="Print with supports.", parts=list(step_parts))] if step_parts else []
        return Submission(task="t", note=note, params={}, parts=[part("plate", orientation), part("knob")], manual=steps)

    assert printed_with_supports(design()) == {}
    assert printed_with_supports(design(orientation="flat, tree supports under the roof")).keys() == {"plate"}
    assert printed_with_supports(design(step_parts=["knob"])).keys() == {"knob"}
    assert printed_with_supports(design(note="Print both with supports.")).keys() == {"plate", "knob"}


def test_a_part_the_design_says_to_print_with_supports_passes_the_bridge_check(tmp_path):
    holed_roof = mesh(block_with_pocket(10, 20, 5), tmp_path)
    built = {"bare": Built("bare", True, mesh=holed_roof, role="final"),
             "supported": Built("supported", True, mesh=holed_roof, role="final", supports="Print with tree supports.")}
    findings = {finding.part: finding for finding in checks.bridges(built)}
    assert findings["bare"].ok is False
    assert findings["supported"].ok is True
    assert findings["supported"].detail.startswith("prints with supports, as the design's instructions say")


def test_a_short_strand_direction_counts_even_when_another_anchors_more():
    """A 60 x 6 mm strip held at both ends and along a third of each long side: lengthwise every strand lands
    but spans 60 mm; across, a third land and none is over 6.8 mm, so it prints. With nothing along the sides,
    the short strands land on nothing and it fails (short_strand_min_anchored)."""
    from shapely.geometry import box

    from pbe.graders.bridges import assess

    strip, ends = box(0, 0, 60, 6), box(-3, 0, 0, 6).union(box(60, 0, 63, 6))
    sides = box(0, -3, 20, 0).union(box(0, 6, 20, 9))
    assert assess(strip, ends.union(sides))[3] is True
    assert assess(strip, ends)[3] is False
