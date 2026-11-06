"""The finished piece, put together from a submission's `assembly`: every printed part moved to where the
design says it goes, every placed item's frame, every screw's line, and probes that ask what plastic
lies where.

A probe is a small solid (a column, a beam, a ring) intersected with the parts with manifold3d, which
needs closed meshes: a part that isn't one can't be probed, and the check says so instead of guessing.
Nothing here knows about a light or a disk; the checks in pbe/graders/enclosure.py do.
"""
from dataclasses import dataclass

import numpy as np
import trimesh
from shapely.geometry import Polygon
from shapely.ops import unary_union

from pbe.graders.sections import section_at

UP = np.array([0.0, 0.0, 1.0])  # out from the wall, in the finished piece's frame


class NotReadable(Exception):
    """A part's mesh isn't a closed volume, so plastic can't be located in it."""


def unit(vector):
    vector = np.asarray(vector, dtype=float)
    return vector / np.linalg.norm(vector)


def matrix(placement) -> np.ndarray:
    """The 4x4 transform from a placed thing's own frame to the finished piece's."""
    z_axis = unit(placement.z_axis)
    x_axis = unit(np.asarray(placement.x_axis, dtype=float) - z_axis * np.dot(placement.x_axis, z_axis))
    transform = np.eye(4)
    transform[:3, 0], transform[:3, 1], transform[:3, 2] = x_axis, np.cross(z_axis, x_axis), z_axis
    transform[:3, 3] = placement.origin
    return transform


def to_piece(placement, point) -> np.ndarray:
    return (matrix(placement) @ np.append(np.asarray(point, dtype=float), 1.0))[:3]


def from_piece(placement, point) -> np.ndarray:
    return (np.linalg.inv(matrix(placement)) @ np.append(np.asarray(point, dtype=float), 1.0))[:3]


def direction_in(placement, direction) -> np.ndarray:
    """A direction in the piece's frame, in the placed thing's own frame."""
    return np.linalg.inv(matrix(placement))[:3, :3] @ np.asarray(direction, dtype=float)


@dataclass
class PlacedScrew:
    item: str  # its id in hardware
    length: float
    head_d: float  # 0 where the catalog doesn't say
    head_h: float
    head: np.ndarray  # the centre of the underside of its head
    direction: np.ndarray  # unit, head to tip

    @property
    def tip(self):
        return self.head + self.length * self.direction


@dataclass
class Piece:
    parts: dict  # part id -> mesh, in the finished piece's frame
    items: list  # (catalog reference, Placement) for each placed item
    screws: list[PlacedScrew]

    @property
    def meshes(self):
        return list(self.parts.values())

    @property
    def wall_z(self):
        """The plane the piece rests against: the lowest point of any printed part."""
        return min(float(mesh.bounds[0][2]) for mesh in self.meshes)

    def placements(self, ref):
        return [placement for item_ref, placement in self.items if item_ref == ref]

    def uses(self, ref_start):
        return any(item_ref.startswith(ref_start) for item_ref, _ in self.items)


def _screw(sub, by_id, placement) -> PlacedScrew:
    found = sub.resolved(by_id[placement.item])
    return PlacedScrew(item=placement.item, length=float(found["length"]), head_d=float(found.get("head_d", 0)),
                       head_h=float(found.get("head_h", 0)), head=np.asarray(placement.head, dtype=float),
                       direction=unit(placement.direction))


def piece(sub, built) -> tuple[Piece | None, str]:
    """(the finished piece, "") or (None, why it can't be put together)."""
    if sub.assembly is None:
        return None, "the design doesn't say where its parts go"
    finals = [part.id for part in sub.parts if part.role == "final"]
    if not finals or not all(part_id in built and built[part_id].ok for part_id in finals):
        return None, "a final part didn't build, and that's already a failure"
    placed_parts = {}
    for placement in sub.assembly.parts:
        mesh = built[placement.part].mesh.copy()
        mesh.apply_transform(matrix(placement))
        placed_parts[placement.part] = mesh
    by_id = {item.id: item for item in sub.hardware}
    items = [(by_id[placement.item].ref, placement) for placement in sub.assembly.items]
    screws = [_screw(sub, by_id, placement) for placement in sub.assembly.screws]
    return Piece(placed_parts, items, screws), ""


# --- moving meshes and probing them ---

def moved(meshes, transform):
    out = []
    for mesh in meshes:
        copy = mesh.copy()
        copy.apply_transform(transform)
        out.append(copy)
    return out


def into(meshes, placement):
    """The meshes in a placed thing's own frame."""
    return moved(meshes, np.linalg.inv(matrix(placement)))


def along(meshes, origin, direction):
    """The meshes in a frame whose origin is `origin` and whose +z is `direction`."""
    z_axis = unit(direction)
    helper = np.array([1.0, 0.0, 0.0]) if abs(z_axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    x_axis = unit(helper - z_axis * np.dot(helper, z_axis))
    transform = np.eye(4)
    transform[:3, 0], transform[:3, 1], transform[:3, 2] = x_axis, np.cross(z_axis, x_axis), z_axis
    transform[:3, 3] = origin
    return moved(meshes, np.linalg.inv(transform))


def box(low, high) -> trimesh.Trimesh:
    low, high = np.asarray(low, dtype=float), np.asarray(high, dtype=float)
    return trimesh.creation.box(extents=high - low, transform=trimesh.transformations.translation_matrix((low + high) / 2))


def column(radius, z_low, z_high, inner=0.0) -> trimesh.Trimesh:
    """A cylinder (or, with `inner`, a tube) on the z axis."""
    centre = trimesh.transformations.translation_matrix((0, 0, (z_low + z_high) / 2))
    if inner > 0:
        return trimesh.creation.annulus(r_min=inner, r_max=radius, height=z_high - z_low, transform=centre, sections=48)
    return trimesh.creation.cylinder(radius=radius, height=z_high - z_low, transform=centre, sections=48)


def plastic_in(meshes, probe) -> list[trimesh.Trimesh]:
    """The plastic inside the probe, one mesh per part that has any."""
    found = []
    for mesh in meshes:
        if not mesh.is_volume:
            raise NotReadable("a part's mesh isn't a closed volume")
        low, high = mesh.bounds
        probe_low, probe_high = probe.bounds
        if np.any(probe_low > high) or np.any(probe_high < low):
            continue
        overlap = trimesh.boolean.intersection([mesh, probe], engine="manifold")
        if len(overlap.faces) and overlap.volume > 1e-4:
            found.append(overlap)
    return found


def lowest_z(pieces):
    """The lowest point of what a probe found, or None if it found nothing."""
    return min(float(found.bounds[0][2]) for found in pieces) if pieces else None


def highest_z(pieces):
    return max(float(found.bounds[1][2]) for found in pieces) if pieces else None


def shadow(pieces):
    """What the pieces cover seen along z, as a shapely shape in x and y."""
    triangles = []
    for found in pieces:
        for corners in found.triangles[:, :, :2]:
            triangle = Polygon(corners)
            if triangle.area > 1e-9:
                triangles.append(triangle)
    return unary_union(triangles) if triangles else Polygon()


def section(meshes, z):
    """Every part's cross-section where z is `z`, merged, as polygons with their holes."""
    polygons = [polygon for mesh in meshes for polygon in section_at(mesh, 2, z)]
    merged = unary_union(polygons) if polygons else Polygon()
    return [piece for piece in getattr(merged, "geoms", [merged]) if isinstance(piece, Polygon) and not piece.is_empty]
