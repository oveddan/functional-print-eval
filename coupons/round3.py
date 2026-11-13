"""Test prints, round 3: the sizes and shapes the models drew that rounds 1 and 2 never tried.
Writes coupons/out/*.stl (gitignored).

    uv run python coupons/round3.py

Each piece answers one row of the not-graded list in docs/reference.md.
F  bolt holes:   through holes for the M8 bolt at 8.0 to 8.4 mm and for the 1/4-20 bolt at
                 6.35 to 6.8 mm. The ends of each row repeat a limit the checks already use.
G  ring roofs:   pockets open at the bed with a bolt hole through the roof. Six with a ledge of
                 1.1 to 3 mm from the pocket's wall to the hole, and the two sizes the models drew
                 for the tripod plate and the wheel, each plain and stepped.
H  bearings:     608 seats at 22.05, 22.4, 22.5 and 22.7 mm, a 22.2 mm seat too shallow by 0.2,
                 0.4 and 0.6 mm, and a 22.2 mm bore with no shoulder.
I  nuts:         M5 pockets under the nut's size, and M3 and M5 pockets with crush ribs or a lip.
M  servo mount:  the MG996R plate from tasks/servo-mount, one with narrower rib channels, and two cutout frames.
N  horn pockets: pockets for the 25T aluminium horn's hub, for tasks/servo-arm.
L  insert posts: freestanding posts 5.5, 6, 7 and 8 mm across for M3 heat-set inserts, and an 8 mm one at 100% infill.
Not here: keyholes (any common wall screw should fit, so no one screw settles them), the tripod clamp's plate widths and head recesses, which need the clamp to try them in.
All print as modeled, z = 0 on the bed, with no supports.
"""
import math

import cadquery as cq
from pydantic import BaseModel

from coupons import B_FLOOR, OUT, at, cut_dots, label

# --- F: bolt holes ----------------------------------------------------------------
BOLT_HOLES = {"M8": [8.0, 8.1, 8.2, 8.3, 8.4], "Q": [6.35, 6.5, 6.6, 6.8]}  # Q = 1/4-20
F_PITCH, F_HEIGHT = 13, 5  # about 4.5 mm of wall between M8 holes


def hole_x(column, pitch=F_PITCH):
    return 12 + pitch / 2 + column * pitch


def bolt_holes():
    columns = max(len(sizes) for sizes in BOLT_HOLES.values())
    width, depth = 12 + columns * F_PITCH, len(BOLT_HOLES) * F_PITCH + 6
    body = cq.Workplane("XY").box(width, depth, F_HEIGHT, centered=False)
    for row, (name, sizes) in enumerate(BOLT_HOLES.items()):
        row_y = depth - F_PITCH / 2 - row * F_PITCH
        body = label(body, name, 6, row_y, F_HEIGHT, size=4)
        for column, diameter in enumerate(sizes):
            body = body.cut(at(hole_x(column), row_y, -1).circle(diameter / 2).extrude(F_HEIGHT + 2))
    for column in range(columns):  # 0 to 4 dots along the near edge, smallest hole first
        body = cut_dots(body, column, hole_x(column), 2.5, F_HEIGHT, spacing=2.4, radius=0.7)
    return body


# --- G: ring roofs ----------------------------------------------------------------
class RingRoof(BaseModel):
    """A pocket open at the bed, with a bolt hole through its roof."""
    name: str
    pocket: float  # diameter, or across flats for a hex pocket
    hole: float
    hex: bool = False
    stepped: bool = False

    @property
    def ledge(self):
        """The narrowest roof from the pocket's wall to the hole's edge."""
        return round((self.pocket - self.hole) / 2, 2)


G_SMALL = [  # a ledge series around an M5 clearance hole, then the plain nut pockets the models drew
    RingRoof(name="1", pocket=8.5, hole=5.5), RingRoof(name="2", pocket=9.5, hole=5.5),
    RingRoof(name="3", pocket=10.5, hole=5.5), RingRoof(name="4", pocket=11.5, hole=5.5),
    RingRoof(name="5", pocket=8.1, hole=5.5, hex=True), RingRoof(name="6", pocket=5.7, hole=3.4, hex=True),
]
G_LARGE = [  # the tripod plate's head recess and the wheel's bearing seat, as the models drew them
    RingRoof(name="7", pocket=16, hole=6.8), RingRoof(name="8", pocket=16, hole=6.8, stepped=True),
    RingRoof(name="9", pocket=22, hole=8.4), RingRoof(name="10", pocket=22, hole=8.4, stepped=True),
]
G_DEPTH, G_ROOF, G_STEP = 3, 3, 0.4
G_SMALL_PITCH, G_LARGE_PITCH = 15, 26  # about 3.5 mm of wall between pockets
G_SMALL_Y, G_LARGE_Y = 42, 15


def ring_roof_cells():
    """Every cell with its centre: (cell, x, y)."""
    small = [(cell, 4 + G_SMALL_PITCH / 2 + i * G_SMALL_PITCH, G_SMALL_Y) for i, cell in enumerate(G_SMALL)]
    large = [(cell, 4 + G_LARGE_PITCH / 2 + i * G_LARGE_PITCH, G_LARGE_Y) for i, cell in enumerate(G_LARGE)]
    return small + large


def cut_ring_roof(body, cell, x, y):
    pocket = at(x, y, -1)
    pocket = pocket.polygon(6, cell.pocket / math.cos(math.radians(30))) if cell.hex else pocket.circle(cell.pocket / 2)
    body = body.cut(pocket.extrude(G_DEPTH + 1))
    if cell.stepped:  # a strip the hole's width across the pocket, then a square, then the hole
        for along, steps in ((cell.pocket, 1), (cell.hole, 2)):
            body = body.cut(at(x, y, G_DEPTH - 0.01).rect(cell.hole, along).extrude(steps * G_STEP + 0.01))
    return body.cut(at(x, y, -1).circle(cell.hole / 2).extrude(G_DEPTH + G_ROOF + 2))


def ring_roofs():
    height = G_DEPTH + G_ROOF
    width = 8 + max(len(G_SMALL) * G_SMALL_PITCH, len(G_LARGE) * G_LARGE_PITCH)
    body = cq.Workplane("XY").box(width, 58, height, centered=False)
    for cell, x, y in ring_roof_cells():
        body = cut_ring_roof(body, cell, x, y)
        body = label(body, cell.name, x, y + cell.pocket / 2 + 3.2, height, size=3.5)
    return body


# --- H: bearing seats -------------------------------------------------------------
class Seat(BaseModel):
    """A 608 seat cut into the top of the block. `short` is how far the bearing stands out of it."""
    name: str
    diameter: float
    short: float = 0.0
    shoulder: bool = True


BEARING_W = 7.0
H_SEATS = [
    Seat(name="1", diameter=22.05), Seat(name="2", diameter=22.4), Seat(name="3", diameter=22.5),
    Seat(name="4", diameter=22.7),
    Seat(name="5", diameter=22.2, short=0.2), Seat(name="6", diameter=22.2, short=0.4),
    Seat(name="7", diameter=22.2, short=0.6), Seat(name="8", diameter=22.2, shoulder=False),
]
H_PITCH, H_FLOOR, H_PUSH = 26, 1.2, 12  # 3.3 mm of wall at the widest seat, as round 2's 28 mm pitch left 6
H_HEIGHT = H_FLOOR + BEARING_W + 0.2


def bearing_seat_cells():
    """(seat, x, y): four to a row, the first row at the back."""
    return [(seat, 4 + H_PITCH / 2 + (i % 4) * H_PITCH, 4 + H_PITCH / 2 + (1 - i // 4) * H_PITCH)
            for i, seat in enumerate(H_SEATS)]


def bearing_seats():
    body = cq.Workplane("XY").box(8 + 4 * H_PITCH, 8 + 2 * H_PITCH, H_HEIGHT, centered=False)
    for seat, x, y in bearing_seat_cells():
        depth = BEARING_W - seat.short if seat.short else BEARING_W + 0.2  # 0.2 below flush when it seats fully
        through = seat.diameter if not seat.shoulder else H_PUSH  # a hole to push the bearing back out
        body = body.cut(at(x, y, H_HEIGHT - depth).circle(seat.diameter / 2).extrude(depth + 1))
        body = body.cut(at(x, y, -1).circle(through / 2).extrude(H_HEIGHT + 2))
        body = label(body, seat.name, x - H_PITCH / 2 + 2.2, y + H_PITCH / 2 - 2.6, H_HEIGHT, size=3)
    return body


# --- I: nut pockets under size, with crush ribs, and with a lip ---------------------
# The shapes are the commonest the models drew (111 trials not graded for want of them):
# six ribs on every flat (33 trials, mostly Gemini), three on alternate flats (17, mostly Opus),
# a solid undersized lip at the mouth (23, mostly Haiku). Snap fingers (19, mostly GPT-6.1 Sol)
# are left out: their count, width and hook vary so much that one print would settle few.
LEAD_IN = 0.6  # ribs stop this far below the mouth, as most models drew them
POCKET_EXTRA = 0.4  # the pocket is this much deeper than the nut


class NutPocket(BaseModel):
    """A hex pocket opening at the top, with ribs standing in from its flats or a lip at its mouth."""
    name: str
    nut: str
    af: float  # the nut's across-flats size
    nut_height: float
    clearance: float  # pocket across flats, over the nut
    ribs: int = 0  # 0, 3 (alternate flats) or 6
    rib_shape: str = "round"  # "round": a half-buried cylinder; "flat": a rectangle
    rib_size: float = 0.0  # a round rib's radius, or a flat rib's width
    rib_stands: float = 0.0  # how far a rib stands in from its flat
    lip_af: float | None = None  # a solid hex lip at the mouth, narrower than the nut
    lip_h: float = 1.0

    @property
    def bite(self):
        """How far the nut has to crush each rib, or the lip on each side."""
        if self.lip_af is not None:
            return round((self.af - self.lip_af) / 2, 3)
        return round(self.rib_stands - self.clearance / 2, 3) if self.ribs else 0.0

    @property
    def depth(self):
        return self.nut_height + POCKET_EXTRA + (self.lip_h if self.lip_af is not None else 0)


M3 = {"nut": "M3", "af": 5.5, "nut_height": 2.4}
M5 = {"nut": "M5", "af": 8.0, "nut_height": 4.7}
I_UNDER = [NutPocket(name=f"U{i + 1}", clearance=clearance, **M5) for i, clearance in enumerate([-0.15, -0.1, -0.05])]
I_RIBBED = [
    NutPocket(name="R1", clearance=0.2, ribs=6, rib_size=0.5, rib_stands=0.2, **M5),
    NutPocket(name="R2", clearance=0.2, ribs=6, rib_shape="flat", rib_size=1.0, rib_stands=0.2, **M5),
    NutPocket(name="R3", clearance=0.15, ribs=3, rib_size=0.6, rib_stands=0.275, **M5),
    NutPocket(name="R4", clearance=0.1, ribs=6, rib_size=0.5, rib_stands=0.15, **M3),
    NutPocket(name="R5", clearance=0.2, ribs=3, rib_size=0.5, rib_stands=0.3, **M3),
    NutPocket(name="L1", clearance=0.2, lip_af=7.8, **M5),
    NutPocket(name="L2", clearance=0.2, lip_af=7.6, **M5),
]
I_POCKETS = I_UNDER + I_RIBBED
I_PITCH = 16  # about 6 mm of wall between M5 pockets, flat to flat


def hexagon(x, y, z, across_flats):
    return at(x, y, z).polygon(6, across_flats / math.cos(math.radians(30)))


def rib(cell, across, floor, height):
    """One rib on the flat facing +x, standing `rib_stands` in from it."""
    if cell.rib_shape == "round":
        return at(across / 2 + cell.rib_size - cell.rib_stands, 0, floor).circle(cell.rib_size).extrude(height)
    wall_overlap = 0.5
    width = cell.rib_stands + wall_overlap
    return at(across / 2 - cell.rib_stands + width / 2, 0, floor).rect(width, cell.rib_size).extrude(height)


def cut_nut_pocket(body, cell, x, y, top):
    across = cell.af + cell.clearance
    floor = top - cell.depth
    body = body.cut(hexagon(x, y, floor, across).extrude(cell.depth + 1))
    if cell.lip_af is not None:
        lip = hexagon(x, y, top - cell.lip_h, across).extrude(cell.lip_h)
        return body.union(lip.cut(hexagon(x, y, top - cell.lip_h - 1, cell.lip_af).extrude(cell.lip_h + 2)))
    for k in range(cell.ribs):
        angle = 30 + k * (360 / cell.ribs)  # polygon(6, d) has corners on x, so its flats face 30, 90, ...
        one = rib(cell, across, floor, cell.depth - LEAD_IN).rotate((0, 0, 0), (0, 0, 1), angle).translate((x, y, 0))
        body = body.union(one)
    return body


def nut_pocket_cells(pockets=None):
    pockets = I_POCKETS if pockets is None else pockets
    per_row = 5
    rows = math.ceil(len(pockets) / per_row)
    return [(cell, 4 + I_PITCH / 2 + (i % per_row) * I_PITCH, 4 + I_PITCH / 2 + (rows - 1 - i // per_row) * I_PITCH)
            for i, cell in enumerate(pockets)]


def nut_pockets(pockets=None):
    cells = nut_pocket_cells(pockets)
    height = B_FLOOR + max(cell.depth for cell, _, _ in cells)
    width = 8 + I_PITCH * max(1 + round((x - 4 - I_PITCH / 2) / I_PITCH) for _, x, _ in cells)
    depth = 8 + I_PITCH * (1 + round((max(y for _, _, y in cells) - 4 - I_PITCH / 2) / I_PITCH))
    body = cq.Workplane("XY").box(width, depth, height, centered=False)
    for cell, x, y in cells:
        body = cut_nut_pocket(body, cell, x, y, height)
        body = label(body, cell.name, x, y + I_PITCH / 2 - 1.6, height, size=2.5)  # above the pocket's flat
    return body


# --- L: insert posts --------------------------------------------------------------
# Estoa's lid-screw posts were 8 mm across, freestanding and 26 mm tall, with 4.3 mm holes for
# M3 x 4 x 5 inserts; they softened and flared when the inserts went in. Dan, 2026-11-08: that was
# the 100% infill, and at 20% they'd hold, which the estoa task now assumes. These settle it: 5.5, 6, 7
# and 8 mm posts (5.5 leaves 0.6 mm, about the thinnest the models drew) at the plate's infill, and a second 8 mm post (L-post-8-solid) to set to 100% in the slicer.
POST_DS, POST_H, POST_HOLE, POST_BASE = [5.5, 6, 7, 8], 26, 4.3, 2
POST_PITCH = 16


def insert_post(diameter, base=True):
    post = at(0, 0, 0).circle(diameter / 2).extrude(POST_BASE + POST_H)
    if base:
        post = post.union(at(0, 0, 0).rect(POST_PITCH - 2, POST_PITCH - 2).extrude(POST_BASE))
    return post.cut(at(0, 0, POST_BASE + POST_H - 8).circle(POST_HOLE / 2).extrude(9))


def insert_posts():
    body = None
    for i, diameter in enumerate(POST_DS):
        post = insert_post(diameter).translate((i * POST_PITCH, 0, 0))
        post = label(post, f"{diameter:g}", i * POST_PITCH, -(POST_PITCH - 2) / 2 + 2.4, POST_BASE, size=3)
        body = post if body is None else body.union(post)
    return body


# --- M: the MG996R mount (tasks/servo-mount, on branch claude/servo-mount) ---------
# The task's brief leaves three things to records nobody has: a cutout between 0 and 0.25 a side,
# whether a channel really clears the tab's rib (no relieved plate was ever printed), and the 10 mm
# between a tab's two holes (datasheet only). M1 is the task's reference plate. M2 narrows the rib's
# channels, a different width each side, so a rocking tab says which side failed. M3 is two thin
# frames, the cutout alone at 0.0 and 0.1 a side.
BODY_L, BODY_W = 40.58, 19.82  # catalog/hardware.yaml, MG996R
PITCH, PAIR, TAB_HOLE, SCREW_HOLE = 49.19, 10, 4.58, 3.4
RIB_W, RIB_H = 1.51, 1.8


class ServoPlate(BaseModel):
    name: str
    clearance: float = 0.25  # a side, round the body
    channels: tuple[float, float] = (2.1, 2.1)  # the rib's channel on each tab, widths
    channel_h: float = 2.2
    plate_l: float = 72
    plate_w: float = 28
    plate_t: float = 4


M_PLATES = [
    ServoPlate(name="M1"),
    ServoPlate(name="M2", channels=(RIB_W + 2 * 0.05, RIB_W + 2 * 0.15)),
]
M_FRAMES = [0.0, 0.1]


def servo_plate(spec):
    """The reference plate (tasks/servo-mount/reference.yaml), channels on the bed."""
    plate = cq.Workplane("XY").rect(spec.plate_l, spec.plate_w).extrude(spec.plate_t)
    plate = plate.cut(cq.Workplane("XY").rect(BODY_L + 2 * spec.clearance, BODY_W + 2 * spec.clearance).extrude(spec.plate_t))
    start, end = BODY_L / 2, PITCH / 2 + TAB_HOLE / 2 + 1
    for side, width in zip((-1, 1), spec.channels):
        channel = cq.Workplane("XY").center(side * (start + end) / 2, 0).rect(end - start, width).extrude(spec.channel_h)
        plate = plate.cut(channel)
        for row in (-1, 1):
            plate = plate.cut(cq.Workplane("XY").center(side * PITCH / 2, row * PAIR / 2).circle(SCREW_HOLE / 2).extrude(spec.plate_t))
    plate = label(plate, spec.name, 0, spec.plate_w / 2 - 3.5, spec.plate_t, size=3.5)
    if spec.channels[0] != spec.channels[1]:  # mark the narrower channel's end
        plate = cut_dots(plate, 1, -spec.plate_l / 2 + 4, 0, spec.plate_t)
    return plate


def servo_frame(clearance, wall=4, height=3):
    inner_l, inner_w = BODY_L + 2 * clearance, BODY_W + 2 * clearance
    frame = cq.Workplane("XY").rect(inner_l + 2 * wall, inner_w + 2 * wall).extrude(height)
    frame = frame.cut(cq.Workplane("XY").rect(inner_l, inner_w).extrude(height))
    return cut_dots(frame, round(clearance * 10), 0, inner_w / 2 + wall / 2, height, spacing=2.4, radius=0.6)


# --- N: an arm on the 25T aluminium horn (tasks/servo-arm, on branch claude/servo-arm) ---
# servo-arm's R4 is not graded for an arm on the horn: no pocket for its 14.66 mm hub was printed.
# Three pockets 2 mm deep, at 0.1, 0.5 and 1.0 over the hub, each with a hole for the horn's
# centre screw. The horn's own screw holes were only estimated from a photo, so they're not here.
HUB_D, HUB_OVER, HUB_POCKET_DEPTH = 14.66, [0.1, 0.5, 1.0], 2.0
N_PITCH, N_T, CENTRE_SCREW = 22, 5, 3.4


def horn_pockets():
    body = cq.Workplane("XY").box(len(HUB_OVER) * N_PITCH + 4, N_PITCH + 4, N_T, centered=False)
    for i, over in enumerate(HUB_OVER):
        x, y = 2 + N_PITCH / 2 + i * N_PITCH, 2 + N_PITCH / 2
        body = body.cut(at(x, y, N_T - HUB_POCKET_DEPTH).circle((HUB_D + over) / 2).extrude(HUB_POCKET_DEPTH + 1))
        body = body.cut(at(x, y, -1).circle(CENTRE_SCREW / 2).extrude(N_T + 2))
        body = cut_dots(body, i, x, 2.2, N_T, spacing=2.4, radius=0.6)
    return body


def parts():
    found = {"F-bolt-holes": bolt_holes(), "G-ring-roofs": ring_roofs(), "H-bearings": bearing_seats()}
    found["I-nuts"] = nut_pockets()
    found |= {f"{spec.name}-servo-plate": servo_plate(spec) for spec in M_PLATES}
    found |= {f"M3-servo-frame-{c:g}": servo_frame(c) for c in M_FRAMES}
    found["N-horn-pockets"] = horn_pockets()
    found |= {"L-posts": insert_posts(), "L-post-8-solid": insert_post(8)}
    return found


def main():
    OUT.mkdir(exist_ok=True)
    for name, shape in parts().items():
        cq.exporters.export(shape, str(OUT / f"{name}.stl"), tolerance=0.01, angularTolerance=0.1)
        box = shape.val().BoundingBox()
        print(f"{name:14} {box.xlen:6.1f} x {box.ylen:5.1f} x {box.zlen:4.1f} mm  {shape.val().Volume() / 1000:5.1f} cm3")


if __name__ == "__main__":
    main()
