"""Cross-sections of a built part, shared by the requirement graders."""
from functools import reduce

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import polylabel


def section(mesh, axis, frac):
    """The cross-section across `axis` at `frac` of the part's length, as polygons
    with their holes. The plane is axis-aligned, so the other two coordinates are the
    plane's; XOR of the section's loops nests the holes inside their outlines."""
    normal = np.eye(3)[axis]
    low, high = mesh.bounds[:, axis]
    origin = mesh.bounds.mean(axis=0)
    origin[axis] = low + frac * (high - low)
    cut = mesh.section(plane_origin=origin, plane_normal=normal)
    if cut is None:
        return []
    in_plane = [i for i in range(3) if i != axis]
    loops = [Polygon(loop[:, in_plane]).buffer(0) for loop in cut.discrete if len(loop) >= 3]
    if not loops:
        return []
    shape = reduce(lambda so_far, loop: so_far.symmetric_difference(loop), loops)
    return [piece for piece in getattr(shape, "geoms", [shape]) if isinstance(piece, Polygon)]


def holes(mesh, axis, frac):
    """The holes in a cross-section. Anything solid standing inside a hole is cut out of it."""
    polys = section(mesh, axis, frac)
    found = []
    for poly in polys:
        for ring in poly.interiors:
            hole = Polygon(ring)
            for other in polys:
                if hole.contains(other):
                    hole = hole.difference(other)
            found.append(hole)
    return found


def holes_by_layer(mesh, axis, step):
    """The part cut into layers about `step` thick along an axis, each read at its middle, away
    from the end faces: (the layers' exact thickness, the holes in each layer, in order)."""
    length = float(mesh.extents[axis])
    count = max(int(round(length / step)), 2)
    return length / count, [holes(mesh, axis, (i + 0.5) / count) for i in range(count)]


def hole_axis(mesh):
    """The axis whose middle cross-section shows exactly one hole, else None."""
    return next((axis for axis in range(3) if len(holes(mesh, axis, 0.5)) == 1), None)


def diameter(poly):
    """The largest distance between two points of the polygon's outline."""
    points = np.asarray(poly.exterior.coords)
    return float(np.max(np.linalg.norm(points[:, None] - points[None], axis=-1)))


def clear_width(hole):
    """The diameter of the largest circle that fits in the hole. For a hex pocket, its
    across-flats."""
    return 2 * hole.boundary.distance(polylabel(hole, tolerance=0.001))


def single_final(sub, built):
    """The one printed part a single-part task expects: (Built, "") or (None, why not)."""
    finals = [built[part.id] for part in sub.parts if part.role == "final" and part.id in built]
    if len(finals) != 1:
        return None, f"expected one printed part, got {len(finals)}"
    if not finals[0].ok:
        return None, f"{finals[0].part_id} didn't build"
    return finals[0], ""
