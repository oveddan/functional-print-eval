"""The bridge rule on shapes with known answers, independent of the Arca plate."""
import cadquery as cq
import pytest
import trimesh

from pbe.bridges import overhangs


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


def test_45_degree_chamfer_needs_no_bridge(tmp_path):
    # a 45 degree overhang is built up a little each layer; nothing to bridge
    part = cq.Workplane("XZ").polyline([(0, 0), (10, 0), (20, 10), (0, 10)]).close().extrude(10)
    assert overhangs(mesh(part, tmp_path)) == []
