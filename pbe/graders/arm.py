"""Checks for a servo arm's joint: does the arm press onto the MG996R's shaft and stay on (class C2),
does a seat hold the 608 bearing (C2), is the arm about as long as asked, and can it swing both ways
through the servo's range without hitting anything printed (C5)?

The servo's mount is graded by servo.py's checks. These read holes in the printed parts: a plain round
bore the size of the shaft is the arm's hub, and a bearing-sized one is the bearing's seat. Which part
is which, and how they're laid out, is left to the design. Limits and records: tasks/servo-arm/brief.md.
A case no record decides comes back None, "not graded", which is never a pass.
"""
import math
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import yaml
from shapely.geometry import Point
from shapely.ops import polylabel

from pbe.graders import assumed, servo
from pbe.graders.checks import Verdict
from pbe.graders.sections import clear_width, diameter, holes_by_layer, section
from pbe.graders.wheel import RIBS_MM, _carry_runs, _holds
from pbe.parts import catalog

STEP = 0.2  # mm, a layer
TOL = 0.02  # mm; a curve's facets read a modeled width slightly narrow
PLAIN = 1.06  # a hole this much bigger than its clear circle has ribs, teeth or a slot in it
SCREW_PLAY = 0.7  # mm; a hole up to this much over a listed screw is that screw's clearance hole


@dataclass
class Bore:
    """A run of same-sized holes through consecutive layers of a part."""
    part_id: str
    axis: int
    clear: float  # the tightest clear width along the run
    depth: float
    plain: bool  # round all the way, the only kind the test prints measured
    centre: np.ndarray  # in the plane of the layers
    mesh: object
    span: tuple[float, float] = (0.0, 0.0)  # where the run starts and ends along the axis
    horn: bool = False  # a pocket for the aluminium horn's hub, not a bore on the spline


def _bores(sub, built, size, min_depth):
    """Every run of holes `size` wide (clear width), at least `min_depth` deep, in a final part that built."""
    found = []
    for part in sub.parts:
        if part.role != "final" or part.id not in built or not built[part.id].ok:
            continue
        mesh = built[part.id].mesh
        for axis in range(3):
            found += _bores_along(part.id, mesh, axis, size, min_depth)
    return found


def _bores_along(part_id, mesh, axis, size, min_depth):
    layer_h, layers = holes_by_layer(mesh, axis, STEP)
    runs, finished, starts = [], [], {}
    for index, holes in enumerate(layers):
        sized = [hole for hole in holes if size[0] - TOL <= clear_width(hole) <= size[1] + TOL]
        runs, ended = _carry_runs(runs, sized)
        for run in runs:
            starts.setdefault(id(run[0]), index)
        finished += [(run, starts[id(run[0])]) for run in ended]
    finished += [(run, starts[id(run[0])]) for run in runs]
    low = float(mesh.bounds[0][axis])
    bores = []
    for run, first in finished:
        depth = len(run) * layer_h
        if depth < min_depth - TOL:
            continue
        widths = [clear_width(hole) for hole in run]
        plain = all(_is_plain(hole) for hole in run)
        middle = run[len(run) // 2]  # the centre of its clear circle, so a horn-shaped pocket centres on the hub
        centre = np.asarray(polylabel(middle, tolerance=0.001).coords[0])
        span = (low + first * layer_h, low + (first + len(run)) * layer_h)
        bores.append(Bore(part_id, axis, min(widths), depth, plain, centre, mesh, span))
    return bores


def _is_plain(hole):
    """A plain round hole: no more area than its clear circle's, and no wider anywhere. A big slot or teeth
    show in the area; a narrow slot or small teeth add little area, so they show only in the widest span."""
    clear = clear_width(hole)
    return hole.area <= PLAIN * math.pi * clear ** 2 / 4 and diameter(hole) - clear <= RIBS_MM


def _best(verdicts):
    """A passing verdict if any, else the worst."""
    return next((verdict for verdict in verdicts if verdict.ok), None) or _worst(verdicts)


def _worst(verdicts):
    for wanted in (False, None):
        for verdict in verdicts:
            if verdict.ok is wanted:
                return verdict
    return verdicts[0]


def _finals_built(sub, built):
    finals = [part for part in sub.parts if part.role == "final"]
    return bool(finals) and all(part.id in built and built[part.id].ok for part in finals)


# --- the arm on the shaft ----------------------------------------------------------------------------

def _shaft_verdict(bore, grips, loose) -> Verdict:
    where = f"{bore.clear:.2f} mm bore in {bore.part_id}"
    if not bore.plain:
        return Verdict(None, f"{where}: teeth or slots in it, and only plain round bores were printed")
    if bore.clear >= loose - TOL:
        return Verdict(False, f"{where}: a {loose} mm bore was loose on the shaft")
    if grips[0] - TOL <= bore.clear <= grips[1] + TOL:
        return Verdict(True, f"{where}: {grips[0]} was a hard push and {grips[1]} snug")
    close = assumed.nearest(bore.clear, [(grips[0], True), (grips[1], True), (loose, False)])
    if close:
        result = "it grips" if close[1] else "it's loose on the shaft"
        return Verdict(close[1], f"{where}: {result} ({assumed.note(close[0])})")
    if bore.clear < grips[0]:
        return Verdict(None, f"{where}: tighter than {grips[0]}, a hard push, and nothing tighter was reported")
    return Verdict(None, f"{where}: between {grips[1]}, snug, and {loose}, loose")


def _screw_sizes(sub):
    sizes = []
    for item in sub.hardware:
        resolved = catalog.resolve(item.ref)
        if resolved.get("kind") == "screw" and resolved.get("d"):
            sizes.append(float(resolved["d"]))
    return sizes


def _is_screw_hole(bore, screws):
    return any(d - TOL <= bore.clear <= d + SCREW_PLAY for d in screws)


def _mount_part(sub, built, body):
    mount, _ = servo.find_mount(sub, built, body) if body is not None else (None, "")
    return mount


def _shaft_bores(sub, built, size, min_depth, body=None):
    """The bores that could be the arm's hub: shaft-sized, not in the part the servo mounts in, and not
    a clearance hole for a screw in the hardware list."""
    mount = _mount_part(sub, built, body)
    screws = _screw_sizes(sub)
    return [bore for bore in _bores(sub, built, size, min_depth)
            if (mount is None or bore.part_id != mount.part_id) and not _is_screw_hole(bore, screws)]


HORN_PLAY = 1.5  # mm; a pocket up to this much over the horn's hub is read as the horn's
HORN_DEPTH = 1.0  # mm, the shallowest pocket read as one for the horn


def _horn_pocket(sub, built, horn_hub, body):
    """A pocket in the arm for the aluminium horn's hub, found by the hub's clear circle: the pocket can
    be round or horn-shaped. None if there isn't one."""
    mount = _mount_part(sub, built, body)
    pockets = [bore for bore in _bores(sub, built, (horn_hub, horn_hub + HORN_PLAY), HORN_DEPTH)
               if mount is None or bore.part_id != mount.part_id]
    return replace(max(pockets, key=lambda bore: bore.depth), horn=True) if pockets else None


def _coaxial(bore, other, within=1.0):
    return (bore.part_id == other.part_id and bore.axis == other.axis
            and float(np.linalg.norm(bore.centre - other.centre)) <= within)


def _hub(sub, built, size, grips, loose, min_depth, body=None, horn_hub=None):
    """(the arm's hub bore, its verdict), the one that grips if any does, else the worst. With no bore on
    the spline, a pocket for the aluminium horn stands in for the shaft's axis, not graded for its fit.
    (None, why) if neither."""
    bores = _shaft_bores(sub, built, size, min_depth, body)
    horn = _horn_pocket(sub, built, horn_hub, body) if horn_hub else None
    if horn is not None:  # a hole on the horn pocket's axis is for the horn's screw, not a press fit on the spline
        bores = [bore for bore in bores if not _coaxial(bore, horn)]
    if not bores:
        if horn is not None:
            return horn, Verdict(None, f"{horn.part_id} takes the aluminium horn, in a pocket {horn.clear:.2f} mm across its hub: "
                                       "no pocket for the horn was printed, and where its screw holes are was only estimated from a photo")
        return None, Verdict(None, f"no plain bore {size[0]} to {size[1]} mm across for the shaft, apart from screw holes, "
                                   "and no pocket for the aluminium horn: another hub isn't graded")
    verdicts = [(bore, _shaft_verdict(bore, grips, loose)) for bore in bores]
    gripping = [pair for pair in verdicts if pair[1].ok is True]
    if gripping:
        return gripping[0]
    worst = _worst([verdict for _, verdict in verdicts])
    return next(pair for pair in verdicts if pair[1] is worst)


def shaft_fit(sub, built, size, grips, loose, min_depth, body=None, horn_hub=None, horn_test=None):
    """The arm's hub presses onto the servo's shaft and grips it, from the test print of plain round bores;
    or, for an arm on the aluminium horn, the horn's hub seats in the arm's pocket, from round 3's horn
    pockets once their outcomes are recorded (`horn_test`, read by horn_records)."""
    if not _finals_built(sub, built):
        return None, "a final part didn't build, and that's already a failure"
    bore, verdict = _hub(sub, built, size, grips, loose, min_depth, None if body is None else servo.Body(*body, 0.25), horn_hub)
    if bore is not None and bore.horn and horn_test:
        return horn_fit(bore, horn_records(**{key: horn_test[key] for key in ("file", "piece", "outcomes")}),
                        horn_test["depth"])
    return verdict


# --- the arm on the horn -----------------------------------------------------------------------------
# Round 3's piece N: three round pockets 2 mm deep, 0.1, 0.5 and 1.0 mm over the horn's 14.66 hub, with
# the hub set in each by hand. Its outcomes go into the predictions file in the person's words; the
# requirement's `outcomes` says which words mean the pocket works (the hub goes in and centres the arm)
# and which don't. Until a pocket's outcome is recorded it isn't a record, and with none recorded, an
# arm on the horn is not graded. The horn's own screw holes weren't on the piece, so nothing here reads them.

WORKS, TOO_TIGHT, TOO_LOOSE = "works", "too tight", "too loose"


def horn_records(file, piece, outcomes):
    """[(pocket diameter, result)] for every pocket of `piece` whose outcome is recorded in `file` (relative
    to the repo, or absolute), in diameter order. A result is WORKS, TOO_TIGHT or TOO_LOOSE, so a failure
    keeps which way it failed. An outcome is matched by the first key of `outcomes` it contains, so
    "tight, went in with a push" reads as "tight"; one that matches none is left out."""
    path = Path(file) if Path(file).is_absolute() else catalog.ROOT / file
    if not path.exists():
        return []
    pockets = (yaml.safe_load(path.read_text()) or {}).get(piece, {}).get("pockets", [])
    records = []
    for pocket in pockets:
        said = str(pocket.get("outcome") or "").lower()
        result = next((value for words, value in outcomes.items() if words.lower() in said), None) if said else None
        if result is not None:
            assert result in (WORKS, TOO_TIGHT, TOO_LOOSE), result
            records.append((float(pocket["pocket_d"]), result))
    return sorted(records)


def horn_fit(pocket, records, depth) -> Verdict:
    """The horn's hub seats in the arm's pocket and centres it, from the recorded pockets: no bigger than a
    pocket the hub wouldn't go in, or no smaller than a loose one, fails; a size on a pocket that worked, or
    between two that worked, passes; within the assumption tolerance of one, takes the nearest's; else None."""
    where = f"{pocket.clear:.2f} mm pocket for the aluminium horn's hub in {pocket.part_id}"
    if not records:
        return Verdict(None, f"{where}: round 3's horn pockets have no recorded outcome yet")
    if not pocket.plain:
        return Verdict(None, f"{where}: horn-shaped or slotted, and only round pockets were printed")
    if pocket.depth < depth - assumed.ASSUMED_WITHIN - TOL:
        return Verdict(None, f"{where}: {pocket.depth:.1f} mm deep, shallower than the {depth} mm printed")
    d = pocket.clear
    sizes = ", ".join(f"{size:g} {result}" for size, result in records)
    tight = [size for size, result in records if result == TOO_TIGHT and d <= size + TOL]
    if tight:
        return Verdict(False, f"{where}: no bigger than the {max(tight):g} mm pocket, which was too tight ({sizes})")
    loose = [size for size, result in records if result == TOO_LOOSE and d >= size - TOL]
    if loose:
        return Verdict(False, f"{where}: no smaller than the {min(loose):g} mm pocket, which was too loose ({sizes})")
    for (low, low_result), (high, high_result) in zip(records, records[1:]):
        if low - TOL <= d <= high + TOL and low_result == high_result == WORKS:
            return Verdict(True, f"{where}: between {low:g} and {high:g}, which both worked")
    for size, result in records:
        if abs(d - size) <= TOL:
            return Verdict(result == WORKS, f"{where}: the {size:g} mm pocket {'worked' if result == WORKS else 'was ' + result}")
    close = assumed.nearest(d, records)
    if close:
        return Verdict(close[1] == WORKS, f"{where}: {'works' if close[1] == WORKS else close[1]} ({assumed.note(close[0])})")
    return Verdict(None, f"{where}: no recorded pocket within {assumed.ASSUMED_WITHIN} mm decides it ({sizes})")


# --- the bearing's seat ------------------------------------------------------------------------------

def _has_bearing(sub, bearing):
    for item in sub.hardware:
        resolved = catalog.resolve(item.ref)
        if resolved.get("kind") == "bearing" and resolved.get("id", "").removesuffix("ZZ") == bearing.removesuffix("ZZ"):
            return True
    return False


def bearing_seat(sub, built, bearing, size, too_tight, holds, too_loose, min_depth):
    """A seat holds the 608 bearing, pressed in by hand, from round 2's seats and round 3's H, as bearing-wheel's R3."""
    if not _finals_built(sub, built):
        return None, "a final part didn't build, and that's already a failure"
    if not _has_bearing(sub, bearing):
        return None, f"no {bearing} in the hardware list: the person offered it, and a design without it has no seat to grade"
    seats = _bores(sub, built, size, min_depth)
    if not seats:
        return None, f"no seat for the {bearing}'s outside: a bearing on a peg, or held another way, isn't graded"
    verdicts = []
    for seat in seats:
        if not seat.plain:
            verdicts.append(Verdict(None, f"{seat.part_id}: ribs or slots in the seat, and only plain round seats were printed"))
            continue
        verdict = _holds(seat.clear, too_tight, holds, too_loose)
        verdicts.append(Verdict(verdict.ok, f"{seat.part_id}: {verdict.detail}"))
    return _best(verdicts)  # the design uses one 608: other openings this size, such as a servo cutout, aren't its seat


# --- the arm's length --------------------------------------------------------------------------------

def _reach(bore):
    """How far the part reaches from the bore's axis, across it."""
    plane = [i for i in range(3) if i != bore.axis]
    points = bore.mesh.vertices[:, plane]
    return float(np.max(np.linalg.norm(points - bore.centre, axis=1)))


def length(sub, built, size, grips, loose, min_depth, reach, body=None, horn_hub=None):
    """The arm reaches about as far as asked from the shaft: the part with the shaft's bore, measured from it."""
    if not _finals_built(sub, built):
        return None, "a final part didn't build, and that's already a failure"
    bore, _ = _hub(sub, built, size, grips, loose, min_depth, None if body is None else servo.Body(*body, 0.25), horn_hub)
    if bore is None:
        return None, "no bore for the shaft or pocket for the horn, so there's no arm to measure from"
    got = _reach(bore)
    detail = f"{bore.part_id} reaches {got:.1f} mm from the shaft (about {reach[0]} to {reach[1]} asked)"
    return reach[0] <= got <= reach[1], detail


# --- the swing ---------------------------------------------------------------------------------------
# The arm turns on the shaft. With the shaft's place estimated from the datasheet drawing and the
# servo's place read from the plate's cutout, everything is put in one frame around the shaft: radius,
# angle about the shaft (counterclockwise, looking down the shaft from its tip) and height above the
# case top. The arm can go onto the 25-tooth spline at any angle, so it passes if a clear arc as wide as
# the servo's range exists somewhere, whatever way the uncertain heights fall.

PITCH = 0.5  # mm, the voxel and bin size
DEG = 360  # angle bins


def _points(mesh):
    """The centres of the voxels inside the part, at PITCH."""
    return np.asarray(mesh.voxelized(PITCH).fill().points)


def _handed(axis):
    """+1 if the plane's two axes and `axis` make a right-handed frame, as sections orders them."""
    return -1 if axis == 1 else 1


def _cylinder(points_2d, heights, sign):
    """(radius, angle in degrees, height) for points in the plane around the shaft."""
    r = np.linalg.norm(points_2d, axis=1)
    angle = np.degrees(np.arctan2(points_2d[:, 1], points_2d[:, 0])) * sign
    return r, np.mod(angle, 360.0), heights


def _mask(r, angle, h, r_bins, h_low, h_bins):
    """Occupancy in (radius, height, angle) bins. A point near the shaft covers more than one degree."""
    grid = np.zeros((r_bins, h_bins, DEG), dtype=bool)
    rb = np.floor(r / PITCH).astype(int)
    hb = np.floor((h - h_low) / PITCH).astype(int)
    keep = (rb < r_bins) & (hb >= 0) & (hb < h_bins)
    rb, hb, r, angle = rb[keep], hb[keep], r[keep], angle[keep]
    half = np.minimum(np.ceil(np.degrees(PITCH * 0.75 / np.maximum(r, 1e-6))), 180).astype(int)
    centre = np.floor(angle).astype(int)
    for width in np.unique(half):
        pick = half == width
        for offset in range(-width, width + 1):
            grid[rb[pick], hb[pick], np.mod(centre[pick] + offset, DEG)] = True
    return grid


OPEN_AREA = 0.05  # mm²; less solid than this over the hub's circle is faceting, not a wall


def _arm_frames(bore):
    """For each way the arm can go onto the shaft: (sign of the shaft's direction along the bore's axis,
    the bore's mouth along that axis). A blind bore goes on one way, a through bore either way. An end
    counts as open only if the whole hub fits through it, not just its centre: a horn pocket under a
    screw hole goes on from the pocket's side only (Codex review, PR 4)."""
    mesh, axis = bore.mesh, bore.axis
    low, high = mesh.bounds[:, axis]
    hub = Point(bore.centre).buffer(max(bore.clear / 2 - 0.1, TOL), 64)
    frames = []
    for direction, mouth, beyond in ((1, bore.span[0], bore.span[0] - STEP / 2), (-1, bore.span[1], bore.span[1] + STEP / 2)):
        frac = (beyond - low) / (high - low)
        if not 0 < frac < 1 or sum(piece.intersection(hub).area for piece in section(mesh, axis, frac)) < OPEN_AREA:
            frames.append((direction, mouth))
    return frames


def _arm_cylinder(bore, direction, mouth, points):
    """The arm around its own bore: height measured from the mouth, away from the servo."""
    plane = [i for i in range(3) if i != bore.axis]
    flat = points[:, plane] - bore.centre
    return _cylinder(flat, (points[:, bore.axis] - mouth) * direction, _handed(bore.axis) * direction)


def _case_points(body, tabs, case_h, tab_t, tab_to_top):
    """The servo's case and tabs in its own frame: x along it from its middle, y across, z up from the case top."""
    xs = np.arange(-body.length / 2, body.length / 2 + 1e-9, PITCH)
    ys = np.arange(-body.width / 2, body.width / 2 + 1e-9, PITCH)
    zs = np.arange(-case_h, 1e-9, PITCH)
    case = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), -1).reshape(-1, 3)
    reach = max(tabs.pitch) / 2 + tabs.hole / 2
    tab_x = np.concatenate([np.arange(-reach, -body.length / 2, PITCH), np.arange(body.length / 2, reach + 1e-9, PITCH)])
    tab_z = np.arange(-(tab_to_top + tab_t), -tab_to_top + 1e-9, PITCH)
    tab = np.stack(np.meshgrid(tab_x, ys, tab_z, indexing="ij"), -1).reshape(-1, 3)
    return np.vstack([case, tab])


def _poses(mount, body, tabs, tab_t, tab_to_top):
    """Each way the servo can seat in the plate: (shaft direction along the plate's axis, case top's
    height along it). From underneath, the tab's top face meets the plate; from above, its underside."""
    up = list(range(len(mount.layers)))
    poses = []
    low_seat, _ = servo._seat(mount, up, body, tabs)
    high_seat, _ = servo._seat(mount, up[::-1], body, tabs)
    if low_seat is not None:
        face = mount.low + low_seat * mount.layer_h
        poses += [(1, face + tab_to_top), (-1, face - tab_t - tab_to_top)]
    if high_seat is not None:
        face = mount.low + (high_seat + 1) * mount.layer_h
        poses += [(-1, face - tab_to_top), (1, face + tab_t + tab_to_top)]
    return poses


def _obstacles(mount, mount_points, pose, end, offset, body, case):
    """Everything that stays put, around the shaft: the plate's part and the servo's case."""
    direction, case_top = pose
    frame = mount.frame
    shaft = frame.at(end * (body.length / 2 - offset), 0.0)
    plane = [i for i in range(3) if i != mount.axis]
    flat = mount_points[:, plane] - shaft
    heights = (mount_points[:, mount.axis] - case_top) * direction
    sign = _handed(mount.axis) * direction
    # the case: its own x along the servo, so place it in the plane the same way
    case_flat = np.outer(case[:, 0], frame.along) + np.outer(case[:, 1], frame.across) + frame.centre - shaft
    r1, a1, h1 = _cylinder(flat, heights, sign)
    r2, a2, h2 = _cylinder(case_flat, case[:, 2], sign)
    return np.concatenate([r1, r2]), np.concatenate([a1, a2]), np.concatenate([h1, h2])


def _case_only(body, case, offset):
    shaft = np.array([body.length / 2 - offset, 0.0])
    return _cylinder(case[:, :2] - shaft, case[:, 2], 1)


def _clear_arc(blocked):
    """The widest run of free angles, in degrees, around the circle."""
    if not blocked.any():
        return 360
    free = np.concatenate([~blocked, ~blocked])
    best = run = 0
    for value in free:
        run = run + 1 if value else 0
        best = max(best, run)
    return min(best, 360)


def _arcs(arm, obstacles, sits, r_bins):
    """The clear arc for each height the arm's mouth can sit at above the case top."""
    ar, aa, ah = arm
    h_low = float(np.min(ah)) + sits[0] - PITCH
    h_high = float(np.max(ah)) + sits[1] + PITCH
    h_bins = int(np.ceil((h_high - h_low) / PITCH)) + 1
    arm_bins = int(np.ceil((np.max(ah) - np.min(ah)) / PITCH)) + 2
    arm_mask = _mask(ar, aa, ah - np.min(ah), r_bins, 0.0, arm_bins)
    obstacle_mask = _mask(*obstacles, r_bins, h_low, h_bins)
    arm_f = np.conj(np.fft.rfft(arm_mask, axis=2))
    obs_f = np.fft.rfft(obstacle_mask, axis=2)
    arcs = []
    for sit in np.arange(sits[0], sits[1] + 1e-9, PITCH):
        start = round((np.min(ah) + sit - h_low) / PITCH)
        window = obs_f[:, start:start + arm_bins]
        overlap = np.fft.irfft(np.einsum("rha,rha->a", arm_f[:, :window.shape[1]], window), n=DEG, axis=0)
        arcs.append(_clear_arc(overlap > 0.5))
    return arcs


def swing(sub, built, size, grips, loose, min_depth, body, pitch, pair, tab_hole, tab_t, tab_to_top, case_h,
          shaft_from_end, sits, rotation, horn_hub=None):
    """The arm swings both ways through the servo's range: a clear arc of `rotation` degrees around the
    shaft, past the plate's part and the servo's own case, however the uncertain heights fall."""
    if not _finals_built(sub, built):
        return None, "a final part didn't build, and that's already a failure"
    servo_body, tabs = servo.Body(*body, 0.25), servo.Tabs(tuple(pitch), pair, tab_hole)
    bore, _ = _hub(sub, built, size, grips, loose, min_depth, servo_body, horn_hub)
    if bore is None:
        return None, "no bore for the shaft or pocket for the horn, so there's no arm to swing"
    mount = _mount_part(sub, built, servo_body)
    others = [part.id for part in sub.parts if part.role == "final"
              and part.id not in {bore.part_id, mount.part_id if mount else None}]
    arm_points = _points(bore.mesh)
    r_bins = int(np.ceil(_reach(bore) / PITCH)) + 2
    case = _case_points(servo_body, tabs, case_h, tab_t, tab_to_top)
    offsets = sorted({shaft_from_end[0], sum(shaft_from_end) / 2, shaft_from_end[1]})
    if mount is not None:
        mount_points = _points(built[mount.part_id].mesh)
        settings = [(pose, end) for pose in _poses(mount, servo_body, tabs, tab_t, tab_to_top) for end in (-1, 1)]
    else:
        settings = [(None, 1)]
    if not settings:
        return None, "the servo's tabs have no seat in the plate, so where the shaft sits isn't known"
    choices = []  # for each way the person can put it together: the narrowest clear arc, the widest
    for direction, mouth in _arm_frames(bore):
        arm = _arm_cylinder(bore, direction, mouth, arm_points)
        for pose, end in settings:
            arcs = []
            for offset in offsets:
                obstacles = (_obstacles(mount, mount_points, pose, end, offset, servo_body, case)
                             if mount is not None else _case_only(servo_body, case, offset))
                arcs += _arcs(arm, obstacles, sits, r_bins)
            choices.append((min(arcs), max(arcs)))
    if not choices:
        return None, f"the shaft bore in {bore.part_id} is closed at both ends"
    best_low = max(low for low, _ in choices)
    best_high = max(high for _, high in choices)
    where = "the plate's part and the case" if mount is not None else "the servo's case"
    if best_low >= rotation:
        if others:
            return None, (f"{best_low} degrees clear of {where}, but {', '.join(others)} isn't placed by the design, "
                          f"so whether it's in the way isn't known")
        return True, f"{best_low} degrees clear of {where}, at least the servo's {rotation}"
    if best_high < rotation:
        return False, f"at most {best_high} degrees clear of {where}, short of the servo's {rotation}, wherever the arm sits"
    return None, (f"{best_low} to {best_high} degrees clear of {where}, depending on how high the arm sits on the shaft "
                  f"and where the shaft is, which the datasheet drawing only estimates")
