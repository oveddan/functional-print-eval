"""The assembled view of a bearing wheel, a tripod plate or a nut knob: the printed part the way it's used, with the
person's real hardware drawn where the grader found its seat, pocket or hole. For the results site.

Nothing here finds a seat of its own. Each piece of hardware goes where the task's grader located it, read with the
grader's own functions (pbe.graders.wheel, bolted, nuts), and a design where the grader found none gets no scene and
a short reason. Sizes come from the catalog and the task's requirements, never from the model's code:
- the wheel: two 608 bearings (catalog/hardware.yaml) in the seats wheel._seats reads, and the M8 bolt through them;
- the tripod plate: the salvaged 1/4"-20 bolt in the bore bolted._main_bore picks, its head (15 x 5 mm, the person's
  answer) in the recess the grader reads, and the 10 mm length R5 assumes. The clamp's jaws aren't drawn: no record
  says what they look like beyond the 38 mm plate they take;
- the knob: the ISO 4032 nut in the pocket nuts._nuts_pocket picks, turned the way the grader fitted it, and the bolt
  through it.

Each fit the grader decided also gets a `fit`: which way the part goes in, how far, and what the recorded test print of
that size did (it went in and held, it wouldn't go in, or it was loose and fell out), copied from the saved finding's
own words. A check with no recorded outcome gets no animation and a line saying why.
"""
import math
import re
from pathlib import Path

import numpy as np
import trimesh
import yaml
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]
TASKS = ("bearing-wheel", "tripod-plate", "nut-knob")

COLORS = {"printed": "#e0874a", "bearings": "#7f8c99", "bolt": "#3a4148", "nut": "#c9cfd6"}
LABELS = {"printed": "Printed part", "bearings": "608 bearings", "bolt": "Bolt", "nut": "Nut"}
LEAD = 3.0  # mm outside the part a piece starts from when its fit plays

# what the saved finding says the test print of that size did, in the grader's own words
WHEEL_SAYS = [("presses in and holds upside down", "seats"), ("wouldn't take the bearing", "stops"),
              ("too loose and fell out", "falls"), ("too loose and fall out", "falls")]
NUT_SAYS = {"holds": "seats", "won't go in": "stops", "falls out": "falls"}


def requirement_args(task_family, check):
    found = yaml.safe_load((ROOT / "tasks" / task_family / "requirements.yaml").read_text())
    return next(item for item in found if item["id"] == check).get("args") or {}


def bearing_608():
    found = yaml.safe_load((ROOT / "catalog/hardware.yaml").read_text())
    bearing = next(item for item in found["bearings"] if item["id"] == "608ZZ")
    return {"od": bearing["od"]["used"], "bore": bearing["bore"]["nominal"], "width": bearing["width"]["nominal"]}


# ---- shapes ----

def ring(outer, inner, low, high, axis=2):
    """A tube along an axis (0, 1 or 2) from low to high, centred on that axis."""
    shape = trimesh.creation.annulus(r_min=inner / 2, r_max=outer / 2, height=high - low, sections=64)
    shape.apply_translation((0, 0, (low + high) / 2))
    return along_axis(shape, axis)


def rod(d, low, high, axis=2, sections=32):
    shape = trimesh.creation.cylinder(radius=d / 2, height=high - low, sections=sections)
    shape.apply_translation((0, 0, (low + high) / 2))
    return along_axis(shape, axis)


def along_axis(shape, axis):
    """A shape made along z, turned to run along `axis` (x, y, z = 0, 1, 2) with the other two in order."""
    if axis == 2:
        return shape
    order = [i for i in range(3) if i != axis] + [axis]  # where z's mesh coordinates go
    turned = np.zeros_like(shape.vertices)
    for source, target in enumerate(order):
        turned[:, target] = shape.vertices[:, source]
    flipped = np.linalg.det(np.eye(3)[:, order]) < 0
    faces = shape.faces[:, ::-1] if flipped else shape.faces
    return trimesh.Trimesh(turned, faces, process=False)


def at(shape, plane_xy, axis):
    """Move a shape centred on an axis to sit at this point of the plane across it."""
    offset = np.zeros(3)
    offset[[i for i in range(3) if i != axis]] = plane_xy
    shape = shape.copy()
    shape.apply_translation(offset)
    return shape


def unit(axis, sign=1.0):
    vector = np.zeros(3)
    vector[axis] = sign
    return vector


def column_major(transform):
    return np.asarray(transform).T.flatten().round(6).tolist()


def stand(mesh, rotation):
    """A transform turning the part by `rotation` (3x3) about its middle and standing it on z = 0."""
    centre = mesh.bounds.mean(axis=0)
    transform = np.eye(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = -rotation @ centre
    turned = trimesh.transform_points(mesh.vertices, transform)
    transform[2, 3] -= turned[:, 2].min()
    return transform


def rotation_between(source, target):
    return trimesh.geometry.align_vectors(np.asarray(source, float), np.asarray(target, float))[:3, :3]


def fit_entry(axis, travel, outcome, stop_at):
    """What the viewer needs to play one fit, in the scene's frame: the way in (unit vector), how far the piece
    travels from LEAD mm outside to seated, the outcome, and for one that stops, how far it gets."""
    return {"axis": [round(float(v), 6) for v in axis], "travel": round(float(travel), 3), "outcome": outcome,
            "stop": round(float(stop_at), 3) if outcome == "stops" else None}


class Scene:
    """Layers in the scene's frame. The printed part is the design's own mesh with a matrix; hardware is a mesh
    already in place, with an optional fit."""

    def __init__(self, transform):
        self.transform = np.asarray(transform, float)
        self.layers = {}

    def add(self, key, mesh, fit=None):
        mesh = mesh.copy()
        mesh.apply_transform(self.transform)
        entry = {"mesh_obj": mesh, "matrix": None}
        if fit is not None:
            axis, travel, outcome, stop_at = fit
            entry["fit"] = fit_entry(self.transform[:3, :3] @ axis, travel, outcome, stop_at)
        self.layers.setdefault(key, []).append(entry)

    def result(self, part_id, fit, fit_note, notes, failed):
        layers = [{"key": "printed", "label": LABELS["printed"], "color": COLORS["printed"],
                   "parts": [{"name": part_id, "matrix": column_major(self.transform)}]}]
        for key, parts in self.layers.items():
            layers.append({"key": key, "label": LABELS[key], "color": COLORS[key], "parts": parts})
        return {"layers": layers, "fails": [f"{f.check}: {f.detail}" for f in failed], "assumed_fails": [],
                "fit": fit, "fit_note": fit_note, "notes": notes}


def finding(findings, check):
    return next((f for f in findings if f.check == check), None)


def saying(found, outcome, note=None):
    """The fit's caption record: the check, its saved words and the outcome they give."""
    return {"check": found.check, "detail": found.detail, "outcome": outcome, **({"note": note} if note else {})}


# ---- the wheel ----

def wheel_outcome(found):
    """(across the finding names, outcome) from R3's saved words, or (None, None) if they don't decide one."""
    if found is None or found.ok is None:
        return None, None
    words = re.match(r"(\d+\.\d+) mm: ([^;]*)", found.detail)
    if not words:
        return None, None
    for phrase, outcome in WHEEL_SAYS:
        if phrase in words.group(2):
            return float(words.group(1)), outcome
    return float(words.group(1)), None


def wheel_seats(mesh, seat_range, bearing_width, bearings):
    """Each seat the grader reads in the wheel's bore, with where it is: (Seat, first layer, last layer, its
    centre in the plane across the bore), the bore's layer count, layer thickness and axis."""
    from itertools import groupby

    from pbe.graders import wheel
    from pbe.graders.sections import clear_circle, clear_width
    axis = int(mesh.extents.argmin())
    stack, layer = wheel._axle(mesh, axis, seat_range)
    if stack is None:
        return [], 0, layer, axis
    tightest = min(clear_width(hole) for hole in stack)
    found, index = [], 0
    for sized, run in groupby(stack, key=lambda hole: wheel._sized(clear_width(hole), seat_range)):
        run = list(run)
        if sized:
            seat = wheel._read_seat(run, layer, tightest, bearing_width, bearings)
            centre, _ = clear_circle(max(run, key=clear_width))
            found.append((seat, index, index + len(run) - 1, (centre.x, centre.y)))
        index += len(run)
    return found, len(stack), layer, axis


def wheel_scene(sub, built, findings):
    """(scene, None) or (None, why there's none)."""
    from pbe.graders import wheel
    args = requirement_args("bearing-wheel", "R3")
    seat_range, width, bearings = args["seat_range"], args["bearing_width"], args["bearings"]
    finals = [part for part in sub.parts if part.role == "final" and part.id in built and built[part.id].ok]
    if len(finals) < sum(part.role == "final" for part in sub.parts) or not finals:
        return None, "a final part didn't build"
    wheels = [part for part in finals if wheel._middle_side(built[part.id].mesh) >= seat_range[1]]
    if len(wheels) != 1:
        return None, (f"the wheel is in {len(wheels)} printed pieces, and nothing saved says how they go together"
                      if wheels else "no printed part is big enough to be the wheel")
    part = wheels[0]
    mesh = built[part.id].mesh
    seats, layers, layer, axis = wheel_seats(mesh, seat_range, width, bearings)
    holding = [entry for entry in seats if entry[0].bearings]
    if not holding:
        return None, "the grader found no bearing seat in the wheel"
    size = bearing_608()
    low, high = mesh.bounds[:, axis]
    transform = stand(mesh, rotation_between(unit(axis), (1, 0, 0)))  # the axle level, the wheel on its edge
    scene = Scene(transform)
    across, outcome = wheel_outcome(finding(findings, "R3"))
    notes, fits, closed_match = [], 0, False
    # a bearing in each of two seats, else both in the one seat
    plan = [(entry, 1) for entry in holding[:2]] if len(holding) >= 2 else [(holding[0], min(holding[0][0].bearings, bearings))]
    for (seat, first, last, centre), count in plan:
        start, end = low + first * layer, low + (last + 1) * layer
        opens_low, opens_high = first == 0, last == layers - 1
        # pressed in flush with the face the seat opens to, as the failure drawing of R2 and R3 places them
        # (results_site_views._draw_bearings): from the low face if it opens there, else from the high face
        groups = []  # (low, high, way in or None)
        if opens_low:
            groups = [(start, start + width * count, 1.0)]
        elif opens_high:
            groups = [(end - width * count, end, -1.0)]
        else:
            middle = (start + end) / 2
            groups = [(middle - width * count / 2, middle + width * count / 2, None)]
            notes.append("A seat inside the wheel opens to neither face, so a bearing can't be pressed into it; it's drawn in the middle.")
        for g_low, g_high, sign in groups:
            shape = at(ring(size["od"], size["bore"], g_low, g_high, axis), centre, axis)
            fit = None
            matches = across is not None and abs(seat.across - across) <= 0.02
            closed_match |= sign is None and matches
            if sign is not None and outcome and matches:
                face = low if sign > 0 else high
                lead = (g_high - face) if sign > 0 else (face - g_low)  # how deep its leading face sits
                fit = (unit(axis, sign), lead + LEAD, outcome, LEAD)
                fits += 1
            scene.add("bearings", shape, fit)
    unmatched = outcome and not fits
    if outcome and 0 < fits < len(scene.layers["bearings"]):
        notes.append("Only the seat R3 names is played; the saved finding gives no outcome for the other.")
    bolt = requirement_args("bearing-wheel", "R4")["bolt"]
    head = _screw_head(f"M{int(bolt)}")
    bolt_low, bolt_high = low - 4, high + 4
    centre = holding[0][3]
    scene.add("bolt", at(trimesh.util.concatenate([rod(bolt, bolt_low, bolt_high, axis),
                                                     rod(head["head_d"], bolt_low - head["head_h"], bolt_low, axis)]), centre, axis))
    fit_note = None
    found = finding(findings, "R3")
    if unmatched and closed_match:
        fit_note = "No fit is played: the seat R3 names opens to neither face, so there's no way in to show."
    elif unmatched:
        fit_note = f"No fit is played: R3 names a {across:.2f} mm seat, and the bearings aren't drawn in a seat that size."
    elif outcome is None:
        fit_note = (f"No fit is played: R3 says “{found.detail}”, and no recorded test print decides what a bearing does in that seat."
                    if found is not None else "No fit is played: R3 has no saved result.")
    failed = [f for f in findings if f.ok is False and f.check in ("R2", "R3", "R4")]
    fit = saying(found, outcome, _rescued(found)) if outcome and fits else None
    return scene.result(part.id, fit, fit_note, notes, failed), None


def _rescued(found):
    """A note when the check passed only because a test print would find a size, while the size drawn doesn't hold."""
    if found is not None and found.ok is True and "would find a size" in found.detail:
        return "R3 passes because the design's test print would find a size that holds; the seat as drawn doesn't."
    return None


def _screw_head(size):
    found = yaml.safe_load((ROOT / "catalog/hardware.yaml").read_text())
    return next(item for item in found["screws"] if item["standard"] == "ISO 4762")["sizes"][size]


# ---- the tripod plate ----

def tripod_outcome(r3, r4):
    """(outcome, which part stops, note) from the saved R3 and R4, or (None, None, why not)."""
    if r3 is None or r3.ok is None:
        return None, None, "R3 has no result for the bolt hole" if r3 is None else f"R3 says “{r3.detail}”"
    if "goes through by hand" in r3.detail:
        if r4 is not None and r4.ok is False and "too tight for this head" in r4.detail:
            return "stops", "head", None
        return "seats", None, None
    if "won't pass" in r3.detail:
        return "stops", "tip", None
    return None, None, f"R3 says “{r3.detail}”, which isn't about the bolt pushing in"


def tripod_scene(sub, built, findings):
    from pbe.graders import bolted
    from pbe.graders.nuts import sentence_saying_to_clear_it
    from pbe.graders.sections import clear_circle
    r3 = requirement_args("tripod-plate", "R3")
    r4 = requirement_args("tripod-plate", "R4")
    r5 = requirement_args("tripod-plate", "R5")
    plate, axis = bolted._plate(sub, built)
    if plate is None:
        return None, "no plate built"
    if r3["bolt"] not in [item.ref for item in sub.hardware]:
        return None, "the design doesn't use the person's bolt, so there's no bolt of known size to draw"
    mesh = plate.mesh
    bore = bolted._main_bore(mesh, axis, r3["too_tight"], sentence_saying_to_clear_it(sub) is not None)
    if bore is None:
        return None, "the grader found no hole through the plate"
    import results_site_views  # the bore's holes, followed again as its failure drawing does
    holes = results_site_views._bore_holes(mesh, axis, bore)
    if holes is None:
        return None, "the grader's bore couldn't be found again to place the bolt in"
    centre, _ = clear_circle(min(holes, key=lambda hole: clear_circle(hole)[1]))
    fracs = bolted._layers(mesh, axis)
    low_bound, high_bound = mesh.bounds[:, axis]
    span = high_bound - low_bound
    low_face = low_bound + span * fracs[0] - bore.layer / 2
    high_face = low_bound + span * fracs[-1] + bore.layer / 2
    recess = bore.recess()
    widths, _ = bolted._clamped_widths(mesh, axis)
    wide_end = bolted._wide_end(widths)
    has_recess = recess.depth >= bolted.MIN_RECESS
    head_end = recess.end if has_recess else (wide_end if wide_end is not None else 0)
    down = wide_end if wide_end is not None else head_end
    # the clamp's face down, the camera on top
    rotation = rotation_between(unit(axis), (0, 0, 1) if down == 0 else (0, 0, -1))
    transform = stand(mesh, rotation)
    face = low_face if head_end == 0 else high_face
    inward = 1.0 if head_end == 0 else -1.0
    depth = recess.depth if has_recess else 0.0
    floor = face + inward * depth
    head_d, head_h, length, shank = r4["fits"], r4["head_height"], r5["bolt_length"], r5["bolt_across"]
    head = rod(head_d, min(floor, floor - inward * head_h), max(floor, floor - inward * head_h), axis)
    stem = rod(shank, min(floor, floor + inward * length), max(floor, floor + inward * length), axis)
    bolt = at(trimesh.util.concatenate([head, stem]), (centre.x, centre.y), axis)
    outcome, stopper, why = tripod_outcome(finding(findings, "R3"), finding(findings, "R4"))
    travel = depth + length + LEAD  # from its tip LEAD mm outside the face to seated
    fit = None
    if outcome:
        stop_at = travel - length if stopper == "tip" else travel - depth
        fit = (unit(axis, inward), travel, outcome, stop_at)
    scene = Scene(transform)
    scene.add("bolt", bolt, fit)
    notes = ["The bolt is drawn 15 mm across the head and 5 mm tall (the person's answer) with the 10 mm length R5 "
             "assumes; nobody measured it. The tripod's clamp isn't drawn: no record says more about it than the 38 mm "
             "plate it takes."]
    caption = None
    if outcome:
        check = finding(findings, "R4") if stopper == "head" else finding(findings, "R3")
        caption = saying(check, outcome)
    fit_note = None if outcome else f"No fit is played: {why}."
    failed = [f for f in findings if f.ok is False and f.check in ("R3", "R4", "R5")]
    return scene.result(plate.part_id, caption, fit_note, notes, failed), None


# ---- the nut knob ----

def nut_outcome(found):
    if found is None:
        return None
    said = re.search(r"say (holds|won't go in|falls out|loose|goes in|not measured)", found.detail)
    return NUT_SAYS.get(said.group(1)) if said else None


def nut_turn(mesh, pocket, af):
    """The nut the grader fits in the pocket's tightest hex layer (nuts._nut_in), as a polygon, or None."""
    from pbe.graders import nuts
    from pbe.graders.sections import clear_width, holes_in, sections_by_layer
    layer_h, sections = sections_by_layer(mesh, 2, nuts.LAYER)
    bottom = mesh.bounds[0, 2]
    best = None
    for index, polys in enumerate(sections):
        z = bottom + (index + 0.5) * layer_h
        if not pocket.z[0] <= z <= pocket.z[1]:
            continue
        for hole in holes_in(polys):
            if not hole.buffer(0.01).contains(Point(pocket.centre)):
                continue
            width = clear_width(hole)
            if nuts._nut_sized(width, af) and nuts._is_hex(hole, width) and (best is None or width < best[0]):
                best = (width, hole)
    if best is None:
        return None
    fitted = nuts._nut_in(best[1], best[0])
    corner = np.asarray(fitted.exterior.coords[0]) - np.asarray(fitted.centroid.coords[0])
    return nuts._hexagon(Point(pocket.centre), af, math.degrees(math.atan2(corner[1], corner[0])))


def knob_scene(sub, built, findings, variant):
    from pbe.graders import nuts
    from pbe.graders.sections import single_final
    from pbe.parts import catalog
    part, why = single_final(sub, built)
    if part is None:
        return None, ("the knob didn't build" if why.endswith("got 0") else why)
    nut = catalog.resolve(f"ISO 4032 {variant}")
    af, height = nut["af"], nut["h"]
    mesh = part.mesh
    pocket = nuts._nuts_pocket(mesh, af)
    if pocket is None:
        return None, "the grader found no hex pocket for the nut"
    hexagon = nut_turn(mesh, pocket, af)
    if hexagon is None:
        return None, "the grader's pocket has no hex layer to turn the nut by"
    bottom, top = mesh.bounds[:, 2]
    notes = []
    if pocket.opens == ["top"]:
        seat_low, way_in, face, mouth = pocket.z[0], -1.0, top, pocket.z[1]
    elif pocket.opens == ["bed"]:
        seat_low, way_in, face, mouth = pocket.z[1] - height, 1.0, bottom, pocket.z[0]
    else:
        seat_low, way_in, face, mouth = (pocket.z[0] + pocket.z[1] - height) / 2, None, None, None
        notes.append("The pocket opens to both faces, so nothing stops the nut; it's drawn in the middle."
                     if pocket.opens else "The pocket is closed, so a nut can't be pressed in; it's drawn where the pocket is.")
    shape = trimesh.creation.extrude_polygon(hexagon.difference(Point(pocket.centre).buffer(nut_bore(variant) / 2, 32)), height)
    shape.apply_translation((0, 0, seat_low))
    outcome = nut_outcome(finding(findings, "R4"))
    fit = None
    if outcome and way_in is not None:
        lead = (top - seat_low) if way_in < 0 else (seat_low + height - bottom)  # its leading face, from the face it enters
        reaches = (top - mouth) if way_in < 0 else (mouth - bottom)  # the pocket's mouth, from that face
        travel = lead + LEAD
        fit = (np.array([0, 0, way_in]), travel, outcome, travel - (lead - reaches))
    # a knob has no one way up in use: show the face the nut goes in from on top, where the view looks from
    scene = Scene(stand(mesh, np.diag([1.0, -1.0, -1.0]) if pocket.opens == ["bed"] else np.eye(3)))
    scene.add("nut", shape, fit)
    d = nut_bore(variant)
    scene.add("bolt", at(rod(d, bottom - 6, top + 6), (pocket.centre.x, pocket.centre.y), 2))
    found = finding(findings, "R4")
    fit_note = None
    if fit is None:
        if found is None:
            fit_note = "No fit is played: R4 has no saved result."
        elif way_in is None:
            fit_note = "No fit is played: the nut has no face to go in from."
        else:
            fit_note = f"No fit is played: R4 says “{found.detail}”, and no recorded test print decides whether the nut goes in and stays."
    notes.append("The bolt is drawn as a plain rod through the nut; only its size is in the task.")
    failed = [f for f in findings if f.ok is False and f.check in ("R3", "R4", "R5")]
    return scene.result(part.part_id, saying(found, outcome) if fit else None, fit_note, notes, failed), None


def nut_bore(variant):
    return float(re.sub(r"\D", "", variant))


# ---- entry ----

def scene(sub, task, findings, parts_dir: Path):
    """(scene, None), or (None, why there's none), or (None, None) for a task this doesn't draw."""
    from pbe.parts.build import Built
    family, _, variant = task.partition("/")
    if family not in TASKS:
        return None, None
    built = {part.id: Built(part.id, True, path, trimesh.load(path, force="mesh"))
             for part in sub.parts if (path := parts_dir / f"{part.id}.stl").exists()}
    if family == "bearing-wheel":
        return wheel_scene(sub, built, findings)
    if family == "tripod-plate":
        return tripod_scene(sub, built, findings)
    return knob_scene(sub, built, findings, variant)
