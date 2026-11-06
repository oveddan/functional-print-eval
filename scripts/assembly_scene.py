"""The assembled view of a design whose submission says where everything goes (`assembly`): its printed parts in
place, the person's own parts and every screw, and each failed check drawn where it fails. For the results page.

Each layer is one mesh in the finished piece's frame, written as a base64 binary STL next to the parts' meshes.
The person's parts are simple solids from their measurements; what was never measured uses the same labelled
estimates as the checks (`tasks/estoa-light/requirements.yaml`). A problem is drawn from the reason its check gave,
so it marks where to look, not a second grading.
"""
import base64
import re
from pathlib import Path

import numpy as np
import trimesh

from pbe.graders import placed
from pbe.parts.build import Built

# the person's parts, in each one's own frame (tasks/estoa-light/format.yaml)
DISK = {"radius": 120.5, "thickness": 1.6}  # ESTIMATES: never measured; the checks' smallest radius and R2's assumed board
PERFBOARD = {"width": 50.0, "length": 70.0, "thickness": 1.6}  # Dan's 50 x 70; thickness never measured
ESP32 = {"length": 63.17, "width": 28.25, "board": 1.5, "port": (7.35, 8.94, 3.2)}  # Dan's size; a standard USB-C receptacle
DISK_HOLES_X = 16.85  # the middle of Dan's readings
PLUG = (30.0, 14.0, 8.5)  # how far out, and the 14 x 8.5 mm opening that let a plug seat in Estoa

LAYERS = {"printed": "Printed parts", "disk": "LED disk", "yours": "Perfboard and ESP32", "screws": "Screws",
          "problem": "Fails", "assumed": "Fails under an assumption"}


def _box(low, high):
    low, high = np.asarray(low, float), np.asarray(high, float)
    mesh = trimesh.creation.box(extents=high - low)
    mesh.apply_translation((low + high) / 2)
    return mesh


def _cylinder(radius, z_low, z_high, at=(0.0, 0.0)):
    mesh = trimesh.creation.cylinder(radius=radius, height=z_high - z_low, sections=48)
    mesh.apply_translation((at[0], at[1], (z_low + z_high) / 2))
    return mesh


def _along(mesh, transform):
    mesh = mesh.copy()
    mesh.apply_transform(transform)
    return mesh


def _rod(start, end, radius):
    """A cylinder from one point to another."""
    start, end = np.asarray(start, float), np.asarray(end, float)
    length = float(np.linalg.norm(end - start))
    if length < 1e-6:
        return None
    mesh = trimesh.creation.cylinder(radius=radius, height=length, sections=24)
    mesh.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], (end - start) / length))
    mesh.apply_translation((start + end) / 2)
    return mesh


def own_part(ref):
    """The person's part as a solid in its own frame, or None for one with no shape here."""
    if ref == "own:led-disk":
        return _cylinder(DISK["radius"], 0.0, DISK["thickness"])
    if ref == "own:perfboard":
        return _box((-PERFBOARD["width"] / 2, -PERFBOARD["length"] / 2, -PERFBOARD["thickness"]),
                    (PERFBOARD["width"] / 2, PERFBOARD["length"] / 2, 0.0))
    if ref == "own:esp32":
        depth, across, tall = ESP32["port"]
        top = -tall / 2  # the frame's origin is the port mouth's centre, and the port sits on the board's top face
        board = _box((-ESP32["length"], -ESP32["width"] / 2, top - ESP32["board"]), (0.0, ESP32["width"] / 2, top))
        port = _box((-depth, -across / 2, -tall / 2), (0.0, across / 2, tall / 2))
        return trimesh.util.concatenate([board, port])
    return None


def screw_mesh(screw, d):
    parts = [_rod(screw.head, screw.tip, d / 2)]
    if screw.head_d and screw.head_h:
        parts.append(_rod(screw.head, screw.head - screw.direction * screw.head_h, screw.head_d / 2))
    return trimesh.util.concatenate([part for part in parts if part is not None])


def _screw_d(sub, item_id):
    item = next(item for item in sub.hardware if item.id == item_id)
    found = sub.resolved(item)
    return float(found.get("d") or found.get("nominal_d") or 3.0)


def _placed(piece, ref):
    found = piece.placements(ref)
    return found[0] if len(found) == 1 else None


def problem_marks(sub, piece, check, detail, part_placements):
    """Meshes that show where one failed check fails, from the reason it gave."""
    marks = []
    screws_named = lambda item: [screw for screw in piece.screws if screw.item == item]
    if check == "R1" and (disk := _placed(piece, "own:led-disk")) is not None:
        marks += [_along(_cylinder(1.8, -6.0, 3.0, (side * DISK_HOLES_X, 0)), placed.matrix(disk)) for side in (-1, 1)]
    if check == "R2" and (disk := _placed(piece, "own:led-disk")) is not None:
        for screw in piece.screws:  # the screws through the disk's holes
            local = placed.from_piece(disk, screw.head)
            if abs(abs(local[0]) - DISK_HOLES_X) < 2.5 and abs(local[1]) < 2.5:
                marks.append(screw_mesh(screw, _screw_d(sub, screw.item) + 1.0))
    if check == "R3" and (port := _placed(piece, "own:esp32")) is not None:
        out, across, tall = PLUG
        marks.append(_along(_box((0.0, -across / 2, -tall / 2), (out, across / 2, tall / 2)), placed.matrix(port)))
    if check == "R4" and (named := re.search(r"the (\S+) screw's insert", detail)):
        marks += [screw_mesh(screw, _screw_d(sub, screw.item) + 2.5) for screw in screws_named(named.group(1))]
    if check == "R5":
        for ref in ("own:perfboard", "own:esp32"):
            if (where := _placed(piece, ref)) is not None and (shape := own_part(ref)) is not None:
                marks.append(_along(shape, placed.matrix(where)))
    if check == "R6":
        for x, y in re.findall(r"keyhole at \((-?[\d.]+), (-?[\d.]+)\)", detail):
            ring = _cylinder(7.0, piece.wall_z - 0.5, piece.wall_z + 4.0, (float(x), float(y)))
            marks.append(ring.difference(_cylinder(5.0, piece.wall_z - 1, piece.wall_z + 5, (float(x), float(y))),
                                         engine="manifold"))
    if check == "R7":
        for item in re.findall(r"a (\S+) screw stands", detail):
            marks += [screw_mesh(screw, _screw_d(sub, screw.item) + 1.5) for screw in screws_named(item)]
    return [mark for mark in marks if mark is not None]


def bridge_marks(findings, built, part_placements):
    """Each part's first overhang that won't bridge, where it is: the area that appears at that height with
    nothing under it, as a thin red sheet in the part's place."""
    from shapely.ops import unary_union

    from pbe.graders.sections import section_at
    marks = []
    for finding in findings:
        height = re.search(r"first at z = (-?[\d.]+) mm", finding.detail)
        if finding.check != "bridges" or finding.ok is not False or not height or finding.part not in built:
            continue
        mesh, z = built[finding.part].mesh, float(height.group(1))
        above, below = unary_union(section_at(mesh, 2, z + 0.25)), unary_union(section_at(mesh, 2, z - 0.25))
        new = above.difference(below.buffer(0.3))  # what's new at this layer, past a small step in from the edge
        sheets = [trimesh.creation.extrude_polygon(area, 0.8) for area in getattr(new, "geoms", [new])
                  if area.geom_type == "Polygon" and area.area > 2.0]
        for sheet in sheets:
            sheet.apply_translation((0, 0, z - 0.4))
            if finding.part in part_placements:
                marks.append(_along(sheet, placed.matrix(part_placements[finding.part])))
    return marks


def write(mesh, path: Path):
    path.write_text(base64.b64encode(mesh.export(file_type="stl")).decode())


def scene(sub, record, assumed, parts_dir: Path, out_dir: Path, slug: str, part_names: dict):
    """The trial's layers for the viewer, or None when the design doesn't say where its parts go."""
    if sub is None or sub.assembly is None or not parts_dir.exists():
        return None
    built = {part.id: Built(part.id, True, path, trimesh.load(path))
             for part in sub.parts if (path := parts_dir / f"{part.id}.stl").exists()}
    piece, _ = placed.piece(sub, built)
    if piece is None:
        return None
    part_placements = {placement.part: placement for placement in sub.assembly.parts}
    layers = [{"key": "printed", "label": LAYERS["printed"], "color": "#9fb0bf",
               "parts": [{"name": part_names[part_id], "matrix": placed.matrix(placement).T.flatten().round(6).tolist()}
                         for part_id, placement in part_placements.items() if part_id in part_names]}]
    disk = [_along(shape, placed.matrix(placement)) for ref, placement in piece.items
            if ref == "own:led-disk" and (shape := own_part(ref)) is not None]
    yours = [_along(shape, placed.matrix(placement)) for ref, placement in piece.items
             if ref != "own:led-disk" and (shape := own_part(ref)) is not None]
    screws = [screw_mesh(screw, _screw_d(sub, screw.item)) for screw in piece.screws]
    failed = [finding for finding in record.counted_findings if finding.ok is False]
    problem = bridge_marks(failed, built, part_placements)
    for finding in failed:
        problem += problem_marks(sub, piece, finding.check, finding.detail, part_placements)
    under = [finding for finding in (assumed.findings if assumed else []) if finding.ok is False]
    assumed_marks = [mark for finding in under for mark in problem_marks(sub, piece, finding.check, finding.detail, part_placements)]
    for key, color, meshes in (("disk", "#e9e4d8", disk), ("yours", "#4f9a72", yours), ("screws", "#3a4148", screws),
                               ("problem", "#d23c2f", problem), ("assumed", "#e08a1e", assumed_marks)):
        if meshes:
            name = f"scene-{slug}-{key}"
            write(trimesh.util.concatenate(meshes), out_dir / f"{name}.txt")
            layers.append({"key": key, "label": LAYERS[key], "color": color, "parts": [{"name": name, "matrix": None}]})
    return {"layers": layers, "fails": [f"{f.check}: {f.detail}" for f in failed],
            "assumed_fails": [f"{f.check}: {f.detail}" for f in under]}
