"""The bridge rule on shapes with known answers, independent of the Arca plate."""
import cadquery as cq
import pytest
import trimesh

from pbe.graders.bridges import is_holed_roof, overhangs


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
    (roof_cut_by_slot, True),                       # the slot is a hole in the roof's layer
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
