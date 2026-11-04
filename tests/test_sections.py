"""Cross-sections: what counts as a hole when something solid stands inside one."""
import cadquery as cq
import trimesh

from pbe.graders.sections import holes


def mesh_of(shape, tmp_path):
    path = tmp_path / "part.stl"
    cq.exporters.export(shape, str(path))
    return trimesh.load(path)


def box_with_tube(tmp_path):
    """A 30 mm box with a 20 mm cavity open at the top, and a tube (8 mm, bore 4 mm) standing free
    in the cavity's middle on its floor."""
    box = cq.Workplane("XY").box(30, 30, 10, centered=(True, True, False))
    cavity = cq.Workplane("XY").workplane(offset=2).rect(20, 20).extrude(8)
    tube = cq.Workplane("XY").workplane(offset=2).circle(4).circle(2).extrude(8)
    return mesh_of(box.cut(cavity).union(tube), tmp_path)


def test_a_tube_in_a_cavity_leaves_no_piece_of_its_bore_in_the_cavity(tmp_path):
    found = sorted(holes(box_with_tube(tmp_path), 2, 0.6), key=lambda hole: hole.area)
    # the tube's bore, and the cavity with the tube's whole outline taken out of it
    assert [hole.geom_type for hole in found] == ["Polygon", "Polygon"]
    bore, cavity = found
    assert abs(bore.area - 3.1416 * 2 ** 2) < 0.2
    assert abs(cavity.area - (20 * 20 - 3.1416 * 4 ** 2)) < 0.5
    assert not cavity.intersects(bore.representative_point())
