"""Checks for a printed plate that holds an MG996R servo by its tabs: does the body go through the
cutout (class C2), do screws through the tabs land in the plate's holes (C3), and do the tabs sit
flush against the plate (C5)?

The servo's place comes from the plate's own cutout: the opening the body fits through gives its
centre and which way it runs. Nothing assumes how the plate is built or which way up it prints.
Which limits, and the record behind each, are in tasks/servo-mount/brief.md. A case no record
decides comes back None, "not graded", which is never a pass.
"""
from dataclasses import dataclass

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from pbe.graders.checks import Verdict
from pbe.graders.sections import clear_width, holes_in, sections_by_layer
from pbe.parts import catalog

STEP = 0.2  # mm, a layer
TOL = 0.02  # mm; a curve's facets read a modeled width slightly narrow
AREA = 0.05  # mm²; less solid than this in a region is faceting, not material
COARSE_LAYERS = 40  # layers read along each axis while looking for the cutout


@dataclass(frozen=True)
class Body:
    """The servo as the records give it, from requirements.yaml's args."""
    length: float
    width: float
    seats: float  # clearance a side the test print seated the body at


@dataclass(frozen=True)
class Tabs:
    pitch: tuple[float, ...]  # centre to centre along the servo, end to end: each value a record gives
    pair: float  # centre to centre of the two holes in one tab
    hole: float  # the tab hole's diameter


@dataclass(frozen=True)
class Frame:
    """The servo's place on the plate, in the plane of the plate's layers."""
    centre: np.ndarray
    along: np.ndarray  # unit vector along the servo's length
    across: np.ndarray

    def at(self, x, y):
        return self.centre + x * self.along + y * self.across

    def rect(self, x0, x1, y0, y1) -> Polygon:
        return Polygon([self.at(x0, y0), self.at(x1, y0), self.at(x1, y1), self.at(x0, y1)])


@dataclass
class Mount:
    """The plate the servo mounts in: its layers along the plate's thickness, the cutout, where the servo sits."""
    part_id: str
    layer_h: float
    layers: list[Polygon]  # the solid in each layer, from the low end
    plate: range  # the layers the cutout runs through
    cutout: Polygon  # clear through every one of those layers
    frame: Frame
    per_side: float  # the clearance a side around the body; negative if it doesn't fit, -inf if by over 3 mm


# --- finding the cutout ---------------------------------------------------------------------------

def _solid(polys):
    return unary_union(polys) if polys else Polygon()


def _pieces(solid):
    """A layer's solid as a list of polygons, as sections.holes_in reads them."""
    return [piece for piece in getattr(solid, "geoms", [solid]) if isinstance(piece, Polygon) and not piece.is_empty]


def _openings(solid):
    """The gaps in a layer: each piece's holes, and notches open to its outline (a cutout may run out to
    an edge). The space between two separate pieces, such as two walls standing either side of the
    case, isn't an opening."""
    found = []
    for piece in _pieces(solid):
        gaps = piece.convex_hull.difference(piece)
        found += [gap for gap in getattr(gaps, "geoms", [gaps]) if isinstance(gap, Polygon) and gap.area > AREA]
    return found


def _could_take(opening, body):
    """A quick look: is the opening near the body's size?"""
    rect = opening.minimum_rotated_rectangle
    sides = sorted(_rect_sides(rect))
    return sides[0] >= body.width - 6 and sides[1] >= body.length - 6 and opening.area >= 0.5 * body.length * body.width


def _rect_sides(rect):
    coords = np.asarray(rect.exterior.coords)[:3]
    return [float(np.linalg.norm(coords[1] - coords[0])), float(np.linalg.norm(coords[2] - coords[1]))]


def _span(region, point, direction, reach=500.0):
    """Along the line through `point` in `direction`: the (low, high) distances of the stretch of
    the region that contains the point, or None if the point isn't in it."""
    line = LineString([point - reach * direction, point + reach * direction])
    cut = region.intersection(line)
    for piece in getattr(cut, "geoms", [cut]):
        if isinstance(piece, LineString) and not piece.is_empty and piece.distance(Point(point)) < 1e-6:
            along = [float(np.dot(np.asarray(xy) - point, direction)) for xy in piece.coords]
            return min(along), max(along)
    return None


def _middle(region, centre, direction, sideways, offsets):
    """The middle of the region along `direction`, read on lines at `offsets` sideways of `centre`,
    so a notch on the centreline (room for a cable or the rib) doesn't pull it off the body."""
    middles = []
    for offset in offsets:
        span = _span(region, centre + offset * sideways, direction)
        if span is not None:
            middles.append((span[0] + span[1]) / 2)
    return float(np.mean(middles)) if middles else 0.0


def _frame(cutout, body) -> Frame:
    rect = cutout.minimum_rotated_rectangle
    coords = np.asarray(rect.exterior.coords)[:3]
    edges = [coords[1] - coords[0], coords[2] - coords[1]]
    longest = max(edges, key=np.linalg.norm)
    along = longest / np.linalg.norm(longest)
    across = np.array([-along[1], along[0]])
    centre = np.asarray(rect.centroid.coords[0])
    near_sides = (-(body.width / 2 - 1), body.width / 2 - 1)
    centre = centre + along * _middle(cutout, centre, along, across, near_sides)
    near_ends = (-(body.length / 2 - 2), body.length / 2 - 2)
    centre = centre + across * _middle(cutout, centre, across, along, near_ends)
    return Frame(centre, along, across)


def _body_fits(cutout, frame, body, per_side):
    half_l, half_w = body.length / 2 + per_side, body.width / 2 + per_side
    return cutout.buffer(TOL).contains(frame.rect(-half_l, half_l, -half_w, half_w))


def _per_side(cutout, frame, body, lowest=-3.0, highest=3.0):
    """The clearance a side around the body, to 0.005 mm, within [lowest, highest]; None if even
    a body `lowest` too small a side doesn't fit."""
    if not _body_fits(cutout, frame, body, lowest):
        return None
    if _body_fits(cutout, frame, body, highest):
        return highest
    low, high = lowest, highest
    while high - low > 0.005:
        middle = (low + high) / 2
        low, high = (middle, high) if _body_fits(cutout, frame, body, middle) else (low, middle)
    return low - TOL  # _body_fits allows TOL for facets; the clearance reported is the modeled one


def _runs(openings_by_layer, body):
    """Each stretch of consecutive layers with a body-sized opening, the opening carried from layer
    to layer by overlap: (first layer, the opening clear through every layer of the stretch)."""
    runs, open_runs = [], []
    for index, openings in enumerate(openings_by_layer):
        candidates = [opening for opening in openings if _could_take(opening, body)]
        carried = []
        for opening in candidates:
            run = next((run for run in open_runs if run[1].intersects(opening)), None)
            if run is None:
                carried.append([index, opening])
            else:
                open_runs.remove(run)
                carried.append([run[0], run[1].intersection(opening)])
        for start, cleared in open_runs:
            runs.append((range(start, index), cleared))
        open_runs = carried
    runs += [(range(start, len(openings_by_layer)), cleared) for start, cleared in open_runs]
    return [(layers, cleared) for layers, cleared in runs if isinstance(cleared, Polygon) and not cleared.is_empty]


def _mount_along(part_id, mesh, axis, body):
    """The servo's mount in a part, with the plate's thickness along `axis`, or None."""
    count = min(COARSE_LAYERS, max(int(round(mesh.extents[axis] / STEP)), 2))
    _, coarse = sections_by_layer(mesh, axis, mesh.extents[axis] / count)
    if not any(_could_take(opening, body) for polys in coarse for opening in _openings(_solid(polys))):
        return None
    layer_h, sections = sections_by_layer(mesh, axis, STEP)
    layers = [_solid(polys) for polys in sections]
    best = None
    for plate, cutout in _runs([_openings(solid) for solid in layers], body):
        frame = _frame(cutout, body)
        per_side = _per_side(cutout, frame, body)
        if per_side is None:  # more than 3 mm a side too small
            per_side = -np.inf
        if best is None or (per_side, len(plate)) > (best.per_side, len(best.plate)):
            best = Mount(part_id, layer_h, layers, plate, cutout, frame, per_side)
    return best


def find_mount(sub, built, body):
    """The final part and plate the servo mounts in, with the roomiest cutout: (Mount or None, why not)."""
    finals = [part for part in sub.parts if part.role == "final"]
    if not finals:
        return None, "no final part"
    if not all(part.id in built and built[part.id].ok for part in finals):
        return None, "a final part didn't build, and that's already a failure"
    best = None
    for part in finals:
        mesh = built[part.id].mesh
        for axis in np.argsort(mesh.extents):
            mount = _mount_along(part.id, mesh, int(axis), body)
            if mount is not None and (best is None or mount.per_side > best.per_side):
                best = mount
    if best is None:
        return None, f"no opening near the servo body's {body.length} x {body.width} mm in any final part"
    return best, ""


# --- R1: the body goes through ----------------------------------------------------------------------

def cutout(sub, built, body, seats):
    """The body passes through the cutout. Looser than the test print isn't graded down: the tabs and
    their screws hold the servo, not the cutout's sides."""
    servo = Body(*body, seats)
    mount, why = find_mount(sub, built, servo)
    if mount is None:
        return (None, why) if "didn't build" in why else (False, why)
    clearance = mount.per_side
    detail = f"{clearance:.2f} mm a side around the {servo.length} x {servo.width} mm body in {mount.part_id}"
    if clearance == -np.inf:
        return False, f"the {servo.length} x {servo.width} mm body doesn't fit through: the opening is over 3 mm a side too small"
    if clearance < -TOL:
        return False, detail + ": the body doesn't fit through"
    if clearance < seats - TOL:
        return None, detail + f": between the body's size and the {seats} a side it seated at, and nothing printed there"
    return True, detail + f"; it seated at {seats} a side"


# --- R2: screws land in the plate ------------------------------------------------------------------

def _smallest_screw(sub):
    """The diameter of the thinnest screw in the hardware list, or None."""
    sizes = []
    for item in sub.hardware:
        resolved = catalog.resolve(item.ref)
        if resolved.get("kind") == "screw":
            sizes.append(float(resolved["d"]))
    return min(sizes) if sizes else None


def _screw_axis_region(opening, screw_d):
    """Where a screw's axis can sit in a hole of the plate: in a clearance hole, anywhere it fits;
    in a hole narrower than the screw, at its middle, where the screw cuts its own thread."""
    inset = min(screw_d / 2, clear_width(opening) / 2 - 0.05)
    return opening.buffer(-max(inset, 0.0))


def _plate_holes(mount):
    """The holes clear through the whole plate, apart from the cutout."""
    holes = holes_in(_pieces(_solid([mount.layers[index] for index in mount.plate])))
    return [hole for hole in holes if not hole.intersects(Point(mount.frame.centre))]


def _blind_hole_at(mount, spot, screw_d):
    """A hole in some layer of the plate that would take the screw at the spot, though not clear through it."""
    return any(_screw_axis_region(hole, screw_d).intersects(spot)
               for index in mount.plate for hole in holes_in(_pieces(mount.layers[index])))


def _lands(mount, holes, x, y, tabs, screw_d) -> Verdict:
    """Whether a screw through the tab hole centred at (x, y) goes into a hole in the plate."""
    room = max(tabs.hole / 2 - screw_d / 2, 0.01)
    spot = Point(mount.frame.at(x, y)).buffer(room)
    if any(_screw_axis_region(hole, screw_d).intersects(spot) for hole in holes):
        return Verdict(True, "lands")
    # the tab hole is a U-slot open to the tab's end; how far the tab runs past it wasn't measured
    outward = mount.frame.rect(x, x + np.sign(x) * 10, y - room, y + room)
    if any(_screw_axis_region(hole, screw_d).intersects(outward) for hole in holes):
        return Verdict(None, "only past the tab hole's centre, in the open end of the U-slot, whose length wasn't measured")
    if mount.cutout.buffer(-TOL).intersects(spot):
        return Verdict(False, "the tab hole is over the cutout, with nothing to screw into")
    if _blind_hole_at(mount, spot, screw_d):
        return Verdict(None, "a hole that doesn't go through the plate; only holes through it are read")
    return Verdict(False, "no hole in the plate under it")


# misses under the tabs that another printed part could fill: a rail, a spacer, a clamp
UNSUPPORTED = ("nothing under the tab", "no hole in the plate under it", "with nothing to screw into")


def _other_finals(sub, mount):
    return [part.id for part in sub.parts if part.role == "final" and part.id != mount.part_id]


def _maybe_elsewhere(verdict, others) -> Verdict:
    """A miss under the tabs, on a design with other printed parts, is not graded: they may sit there,
    and without an assembly where they go isn't known. A single plate's miss stays a failure."""
    if verdict.ok is False and others and any(miss in verdict.detail for miss in UNSUPPORTED):
        return Verdict(None, f"{verdict.detail}, unless {', '.join(others)} sits there, and where it goes isn't recorded")
    return verdict


def _tab_holes(pitch, tabs):
    return [(side * pitch / 2, row * tabs.pair / 2) for side in (-1, 1) for row in (-1, 1)]


def _worst(verdicts):
    """The first failure, else the first not graded, else the first verdict."""
    for wanted in (False, None):
        for verdict in verdicts:
            if verdict.ok is wanted:
                return verdict
    return verdicts[0]


def screws(sub, built, body, seats, pitch, pair, tab_hole):
    """A screw from the hardware list through each of the four tab holes goes into a hole in the
    plate, at every hole spacing the records give."""
    servo, tabs = Body(*body, seats), Tabs(tuple(pitch), pair, tab_hole)
    mount, why = find_mount(sub, built, servo)
    if mount is None or mount.per_side < -TOL:
        return None, why or "the body doesn't fit through the cutout, and that's already a failure"
    screw_d = _smallest_screw(sub)
    if screw_d is None:
        return None, "no screw in the hardware list; only screws through the tabs are graded"
    if screw_d > tabs.hole + TOL:
        return False, f"an M{screw_d:g} screw doesn't pass the {tabs.hole} mm tab hole"
    holes, others = _plate_holes(mount), _other_finals(sub, mount)
    by_pitch = []
    for spacing in tabs.pitch:
        verdict = _worst([_maybe_elsewhere(_lands(mount, holes, x, y, tabs, screw_d), others) for x, y in _tab_holes(spacing, tabs)])
        by_pitch.append((spacing, verdict))
    oks = [verdict.ok for _, verdict in by_pitch]
    detail = "; ".join(f"at {spacing} mm between the ends' holes: {verdict.detail}" for spacing, verdict in by_pitch)
    detail = f"M{screw_d:g} screws, holes {tabs.pair} mm apart across each tab: {detail}"
    if all(ok is True for ok in oks):
        return True, detail
    if all(ok is False for ok in oks):
        return False, detail
    return None, detail


# --- R3: the tabs sit flush ------------------------------------------------------------------------

def _area_in(solid, region):
    return solid.intersection(region).area if not solid.is_empty else 0.0


def _contact(mount, order, tab_rect):
    """The first layer, going in from one face, with solid under the tab: the face the tab meets.
    A layer that's solid at the servo's middle, such as a box's floor, is something else."""
    middle = Point(mount.frame.centre)
    return next((index for index in order
                 if _area_in(mount.layers[index], tab_rect) > AREA and not mount.layers[index].contains(middle)), None)


def _clear_depth(mount, order, start, band, limit):
    """How deep the band is clear going in from layer `start`, up to `limit`."""
    position = order.index(start)
    depth = 0.0
    for index in order[position:]:
        if depth >= limit or _area_in(mount.layers[index], band) > AREA:
            return depth
        depth += mount.layer_h
    return limit  # out past the part's last layer, with nothing in the way


def _sides(servo, tabs):
    """For each end of the servo: (its sign, the tab's footprint along it, from the case to past its holes)."""
    reach = max(tabs.pitch) / 2 + tabs.hole / 2
    return [(side, sorted((side * servo.length / 2, side * reach))) for side in (-1, 1)]


def _seat(mount, order, servo, tabs):
    """The layer both tabs meet, going in from one face: (layer, "") or (None, why not). The tabs
    are one flat flange, so supports at two heights leave one tab off the plate."""
    width_y = tabs.pair / 2 + tabs.hole / 2
    contacts = [_contact(mount, order, mount.frame.rect(x0, x1, -width_y, width_y)) for _, (x0, x1) in _sides(servo, tabs)]
    if None in contacts:
        return None, "nothing under the tab at one end"
    if len(set(contacts)) > 1:
        step = abs(order.index(contacts[0]) - order.index(contacts[1])) * mount.layer_h
        return None, f"the two tabs meet the plate {step:.1f} mm apart in height, so one can't sit flush"
    return contacts[0], ""


def _rib_route(mount, order, face, servo, tabs, rib, margin) -> Verdict:
    """Seated with the tab's top face against `face`: the rib between each tab's holes needs room
    `rib["protrudes"]` deep and `rib["width"]` wide, plus `margin` a side to pass."""
    contact, why = _seat(mount, order, servo, tabs)
    if contact is None:
        return Verdict(False, f"from the {face}: {why}")
    findings = []
    for side, (x0, x1) in _sides(servo, tabs):
        tight = mount.frame.rect(x0, x1, -rib["width"] / 2, rib["width"] / 2)
        loose = mount.frame.rect(x0, x1, -rib["width"] / 2 - margin, rib["width"] / 2 + margin)
        limit = rib["protrudes"] - TOL
        findings.append((_clear_depth(mount, order, contact, tight, limit), _clear_depth(mount, order, contact, loose, limit)))
    deepest_tight = min(tight for tight, _ in findings)
    deepest_loose = min(loose for _, loose in findings)
    if deepest_loose >= rib["protrudes"] - TOL:
        return Verdict(True, f"from the {face}: room for the rib, {rib['width']} wide with {margin} a side, {rib['protrudes']} deep")
    if deepest_tight >= rib["protrudes"] - TOL:
        return Verdict(None, f"from the {face}: room for the rib, but less than {margin} a side, and no relieved plate was printed")
    return Verdict(False, f"from the {face}: the rib stands {rib['protrudes']} mm proud of the tab and has {deepest_tight:.1f} mm of room")


def _cable_route(mount, servo, tabs, cable_stopped) -> Verdict:
    """Seated from above: the tab's underside meets the plate and the case end below the tabs, where
    the cable leaves, has to pass through the cutout first."""
    up = list(range(len(mount.layers)))
    seats = [_seat(mount, order, servo, tabs) for order in (up, up[::-1])]
    if all(contact is None for contact, _ in seats):
        return Verdict(False, f"from above: {seats[0][1]}")
    span = _span(mount.cutout, mount.frame.centre, mount.frame.along)
    if span is None:
        return Verdict(False, "from above: no cutout at the servo's middle")
    room = max(-span[0], span[1]) - servo.length / 2
    if room <= cable_stopped + TOL:
        return Verdict(False, f"from above: {room:.2f} mm past the case end, and the test print's servo stopped at its cable "
                              f"exit with {cable_stopped}")
    return Verdict(None, f"from above: {room:.2f} mm past the case end for the cable, and the cable exit was never measured")


def flush(sub, built, body, seats, pitch, pair, tab_hole, rib, cable_stopped):
    """The tabs sit flush on the plate, seated either way: from underneath, the tab's top face meets the
    plate, so the rib needs room; from above, its underside does, and the cable has to pass the cutout."""
    servo, tabs = Body(*body, seats), Tabs(tuple(pitch), pair, tab_hole)
    mount, why = find_mount(sub, built, servo)
    if mount is None or mount.per_side < -TOL:
        return None, why or "the body doesn't fit through the cutout, and that's already a failure"
    up = list(range(len(mount.layers)))
    others = _other_finals(sub, mount)
    routes = [_maybe_elsewhere(route, others) for route in (
        _rib_route(mount, up, "low face", servo, tabs, rib, seats),
        _rib_route(mount, up[::-1], "high face", servo, tabs, rib, seats),
        _cable_route(mount, servo, tabs, cable_stopped))]
    detail = "; ".join(route.detail for route in routes)
    for wanted in (True, None):
        if any(route.ok is wanted for route in routes):
            return wanted, detail
    return False, detail
