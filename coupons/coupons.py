"""Test-print coupons, round 1. Writes coupons/out/*.stl (gitignored).

    uv run python coupons/coupons.py

A  bridges:   pockets open at the bed with roofs of 20/30/40/50 mm, a 20 mm roof
              with a hole through it, and one with a stepped hole. Tests the bridge
              check blind and measures the real longest clean span.
B  nuts:      hex pockets for M3, M5, M8 and 1/4-20 at across-flats +0.0/+0.1/+0.2/+0.3.
              Which hold the nut, which let it fall out, which won't take it.
C  fits:      a block with square holes for a 10 mm peg at 0.1-0.4 per side, and two
              tunnels under bridged roofs for a 10 x 6 bar (Estoa's leg pocket:
              0.2 side / 0.2 top, and 0.35 side / 0.6 top with a flare at the bed).
C' pegs:      the 10 mm peg and the 10 x 6 bar.
All print as modeled, z = 0 on the bed, with no supports.
"""
import math
from pathlib import Path

import cadquery as cq
import yaml
from pydantic import BaseModel

OUT = Path(__file__).resolve().parent / "out"
LABEL_DEPTH = 0.6


def at(x, y, z):
    """A sketch plane at height z, centred on (x, y)."""
    return cq.Workplane("XY").workplane(offset=z).center(x, y)


def label(body, text, x, y, top, size=5):
    letters = at(x, y, top - LABEL_DEPTH).text(text, size, LABEL_DEPTH + 0.1, halign="center", valign="center")
    return body.cut(letters)


def cut_dots(body, count, x, y, top, spacing=3, radius=0.8):
    """A row of `count` dots centred on x, sunk into the top face: how a column is told apart."""
    for k in range(count):
        body = body.cut(at(x + (k - (count - 1) / 2) * spacing, y, top - LABEL_DEPTH).circle(radius).extrude(1))
    return body


# --- A: bridges -------------------------------------------------------------------
BRIDGE_CELLS = [  # (label, pocket size, hole: None | "plain" | "stepped")
    ("20", 20, None), ("30", 30, None), ("40", 40, None), ("50", 50, None),
    ("H", 20, "plain"), ("S", 20, "stepped"),
]
A_WALL, A_DEPTH, A_ROOF, A_HOLE, A_STEP = 4, 3, 3, 6, 0.4
A_WIDTH = 50 + 2 * A_WALL  # every pocket centred in a band this wide


A2_CELLS = [("40", 40, None), ("50", 50, None)]  # round 2: only the pair that contradicted the span limit


def cell_spans(spec=BRIDGE_CELLS):
    """Where each pocket runs along x: (name, size, hole, start, end), and the coupon's length."""
    spans, x = [], A_WALL
    for name, size, hole in spec:
        spans.append((name, size, hole, x, x + size))
        x += size + A_WALL
    return spans, x


def bridge_cells(spec=BRIDGE_CELLS):
    """Each pocket with its centre along x: (name, size, hole, centre), and the coupon's length."""
    spans, length = cell_spans(spec)
    return [(name, size, hole, start + size / 2) for name, size, hole, start, _ in spans], length


def bridges(spec=BRIDGE_CELLS):
    cells, length = bridge_cells(spec)
    height = A_DEPTH + A_ROOF
    body = cq.Workplane("XY").box(length, A_WIDTH, height, centered=False).translate((0, -A_WIDTH / 2, 0))
    for name, size, hole, centre in cells:
        body = body.cut(at(centre, 0, -1).rect(size, size).extrude(A_DEPTH + 1))
        if hole == "stepped":
            # a strip the hole's width across the whole pocket, then a square, then the hole
            for width, length_along, steps in ((A_HOLE, size, 1), (A_HOLE, A_HOLE, 2)):
                body = body.cut(at(centre, 0, A_DEPTH - 0.01).rect(width, length_along).extrude(steps * A_STEP + 0.01))
        if hole:
            body = body.cut(at(centre, 0, -1).circle(A_HOLE / 2).extrude(height + 2))
        if size < 50:  # the 50 mm pocket leaves no room for a label
            body = label(body, name, centre, size / 2 + 4, height, size=4)
    return body, cells


# --- B: nut pockets ---------------------------------------------------------------
NUTS = [("M3", 5.5, 2.4), ("M5", 8.0, 4.7), ("M8", 13.0, 6.8), ("Q", 11.11, 5.56)]  # Q = 1/4-20
CLEARANCES = [0.0, 0.1, 0.2, 0.3]
B_PITCH, B_FLOOR = 22, 1.6


def nut_block(clearances_for, mark=None):
    """A row of hex pockets per nut, one column per clearance; `clearances_for(name)` gives a row's."""
    height = B_FLOOR + max(nut_height for _, _, nut_height in NUTS)
    columns = len(CLEARANCES)
    width, depth = columns * B_PITCH + 12, len(NUTS) * B_PITCH + 4
    body = cq.Workplane("XY").box(width, depth, height, centered=False)
    if mark:
        body = label(body, mark, width - 4, 2.6, height, size=3)
    for row, (name, af, nut_height) in enumerate(NUTS):
        row_y = depth - 2 - B_PITCH / 2 - row * B_PITCH
        body = label(body, name, 6, row_y, height, size=4)
        for column, clearance in enumerate(clearances_for(name)):
            across_corners = (af + clearance) / math.cos(math.radians(30))
            pocket = at(_nut_column_x(column), row_y, height - nut_height).polygon(6, across_corners).extrude(nut_height + 1)
            body = body.cut(pocket)
    for column in range(columns):  # clearance marks along the near edge: 0 to 3 dots
        body = cut_dots(body, column, _nut_column_x(column), 2.2, height)
    return body


def _nut_column_x(column):
    return 12 + B_PITCH / 2 + column * B_PITCH


def nuts():
    return nut_block(lambda name: CLEARANCES)


# --- B2: nut pockets, round 2 ----------------------------------------
# Each size gets its own clearances, centred on its best fit in round 1 (M3 +0.2,
# M5 +0.1, M8 and 1/4-20 +0.0), so the round-1 best is repeated and its neighbours
# are filled in at 0.05 mm steps. Same dots as B: column 1 has none, column 4 has 3.
NUTS2 = {"M3": [0.1, 0.15, 0.2, 0.25], "M5": [0.0, 0.05, 0.1, 0.15],
         "M8": [-0.1, -0.05, 0.0, 0.05], "Q": [-0.1, -0.05, 0.0, 0.05]}


def nuts2():
    return nut_block(lambda name: NUTS2[name], mark="2")  # the 2 tells round 2 from round 1


# --- C: slide fits ----------------------------------------------------------------
PEG = 10.0
SQUARE_FITS = [0.1, 0.2, 0.3, 0.4]  # per side
BAR_W, BAR_H = 10.0, 6.0
TUNNELS = [  # (label, side, top, bed flare): Estoa's first leg pocket, then its fix
    ("1", 0.2, 0.2, 0.0),
    ("2", 0.35, 0.6, 0.5),
]
C_H = 12


def cut_tunnels(body, width, first_y):
    """The bar's tunnels, 12 mm apart from first_y. They run along x, open at both ends, sitting
    on the bed; their roofs are bridges."""
    for j, (name, side, top, flare) in enumerate(TUNNELS):
        tunnel_y = first_y + j * 12
        tunnel_w, tunnel_h = BAR_W + 2 * side, BAR_H + top
        body = body.cut(at(width / 2, tunnel_y, -1).rect(width + 2, tunnel_w).extrude(tunnel_h + 1))
        if flare:
            body = body.cut(at(width / 2, tunnel_y, -1).rect(width + 2, tunnel_w + 2 * flare).extrude(1 + flare))
        body = label(body, name, 4, tunnel_y, C_H, size=4)
    return body


def fits():
    pitch = 18
    width = len(SQUARE_FITS) * pitch + 4
    depth = 22 + 36  # was 22 + 30: tunnel 2 broke through the back wall (round 1 print)
    body = cq.Workplane("XY").box(width, depth, C_H, centered=False)
    for i, per_side in enumerate(SQUARE_FITS):
        hole_x = 2 + pitch / 2 + i * pitch
        side = PEG + 2 * per_side
        body = body.cut(at(hole_x, 11, -1).rect(side, side).extrude(C_H + 2))
        body = cut_dots(body, i + 1, hole_x, 20.5, C_H, spacing=2.5, radius=0.7)  # 1 to 4 dots
    return cut_tunnels(body, width, 30 + 6)


def tunnels():
    """C2 (round 2): C's two tunnels without the square holes, already measured in round 1."""
    width, depth = len(SQUARE_FITS) * 18 + 4, 36
    body = cq.Workplane("XY").box(width, depth, C_H, centered=False)
    return cut_tunnels(body, width, 12)


def pegs():
    peg = cq.Workplane("XY").box(PEG, PEG, 20, centered=(True, True, False))
    bar = cq.Workplane("XY").box(BAR_W, 60, BAR_H, centered=(True, True, False)).translate((20, 0, 0))
    return peg.union(bar)


# --- D: servo mounts, E: spline bores and bearing seats (round 2) ----------------
# Built from catalog/hardware.yaml (Dan's caliper readings), never typed in here.
# D: a plate with each servo's body cutout, at two clearances for the MG90S, and slots
#    for the tab screws. The slots run ±1 mm along the servo so an error in the hole
#    pitch (read from inner edges) doesn't stop the screws going in.
# E: through-bores for each spline at +0.0 to +0.3 over the measured outer diameter
#    (which press on and grip), 608 seats at +0.0 to +0.3 over 22 mm, and 8 mm pegs
#    at -0.2 to +0.0 for the bearing's bore.
Number = int | float


class Reading(BaseModel):
    """One dimension in catalog/hardware.yaml: what the calipers read, what's used, the nominal."""
    measured: Number | list[Number] | None = None
    used: Number | None = None
    nominal: Number | None = None

    @property
    def value(self):
        """What to design to: the value used if one is given, else the largest reading."""
        if self.used is not None:
            return self.used
        return max(self.measured) if isinstance(self.measured, list) else self.measured


class Servo(BaseModel):
    """The readings these coupons use; the catalog records more."""
    id: str
    body_l: Reading
    body_w: Reading
    tab_hole_pitch: Reading
    tab_hole_d: Reading
    spline_od: Reading


class Bearing(BaseModel):
    od: Reading
    bore: Reading
    width: Reading


HARDWARE = yaml.safe_load((Path(__file__).resolve().parents[1] / "catalog/hardware.yaml").read_text())
SERVO = {servo.id: servo for servo in (Servo.model_validate(entry) for entry in HARDWARE["servos"])}
BEARING = Bearing.model_validate(HARDWARE["bearings"][0])


SERVO_CUTS = [("MG996R", 0.25), ("MG90S", 0.15), ("MG90S", 0.3)]  # (servo, clearance per side)
D_T, D_GAP = 3, 9
SPLINE_FITS = [0.0, 0.1, 0.2, 0.3]
SEAT_FITS = [0.0, 0.1, 0.2, 0.3]
PEG_DS = [-0.2, -0.1, 0.0]


def _tab_slots(name):
    """(slot width, how far it runs either way, its length) for a servo's tab screws."""
    hole = SERVO[name].tab_hole_d.value
    if name == "MG996R":
        # one slot spans each tab's hole pair (datasheet 10 mm apart); the self-tapping screw bites its sides
        return 3.0, 1.0, 10 + hole
    return 2.0, 0.5, 2.0  # MG90S: more travel would leave under 1 mm of wall to the cutout


def servo_plate():
    width = 66
    cutouts = [(name, clearance, SERVO[name].body_l.value, SERVO[name].body_w.value) for name, clearance in SERVO_CUTS]
    depth = sum(body_w + 2 * clearance for _, clearance, _, body_w in cutouts) + D_GAP * (len(cutouts) + 1)
    body = cq.Workplane("XY").box(width, depth, D_T, centered=False)
    y = D_GAP
    for name, clearance, body_l, body_w in cutouts:
        cutout_y = y + body_w / 2 + clearance
        body = body.cut(at(width / 2, cutout_y, -1).rect(body_l + 2 * clearance, body_w + 2 * clearance).extrude(D_T + 2))
        pitch = SERVO[name].tab_hole_pitch.value
        slot_w, travel, slot_l = _tab_slots(name)
        for side in (-1, 1):
            body = body.cut(at(width / 2 + side * pitch / 2, cutout_y, -1).rect(slot_w + 2 * travel, slot_l).extrude(D_T + 2))
        short = "996" if name == "MG996R" else "90S"
        text = f"{short} {clearance:.2f}".replace("0.", ".")
        body = label(body, text, width / 2, cutout_y + body_w / 2 + clearance + D_GAP / 2, D_T, size=3.5)
        y += body_w + 2 * clearance + D_GAP
    return body


def spline_bearing_block():
    seat_d, floor, bore = BEARING.od.used, 1.2, BEARING.bore.nominal
    seat_h = BEARING.width.nominal + 0.2
    height = seat_h + floor
    pitch = seat_d + 6
    columns = len(SEAT_FITS)
    width = 12 + columns * pitch
    rows_y = {"608": 4 + pitch / 2, "996": 4 + pitch + 6, "90": 4 + pitch + 18, "peg": 4 + pitch + 30}
    depth = rows_y["peg"] + 8
    body = cq.Workplane("XY").box(width, depth, height, centered=False)
    for column in range(columns):
        column_x = 12 + pitch / 2 + column * pitch
        body = body.cut(at(column_x, rows_y["608"], floor).circle((seat_d + SEAT_FITS[column]) / 2).extrude(height))
        body = body.cut(at(column_x, rows_y["608"], -1).circle(6).extrude(floor + 2))  # push the bearing out
        for row, servo in (("996", "MG996R"), ("90", "MG90S")):
            bore_d = SERVO[servo].spline_od.value + SPLINE_FITS[column]
            body = body.cut(at(column_x, rows_y[row], -1).circle(bore_d / 2).extrude(height + 2))
        if column < len(PEG_DS):
            body = body.union(at(column_x, rows_y["peg"], height).circle((bore + PEG_DS[column]) / 2).extrude(8))
        body = cut_dots(body, column, column_x, rows_y["90"] + 6, height)  # 0 to 3 dots, like B
    for row in ("996", "90"):
        body = label(body, row, 6, rows_y[row], height, size=3.5)
    return body


def main():
    OUT.mkdir(exist_ok=True)
    bridge_coupon, _ = bridges()
    round2_bridges, _ = bridges(A2_CELLS)
    parts = {"A-bridges": bridge_coupon, "B-nuts": nuts(), "B2-nuts": nuts2(), "A2-bridges": round2_bridges,
             "C-fits": fits(), "C2-tunnels": tunnels(), "C-pegs": pegs(),
             "D-servos": servo_plate(), "E-splines-bearings": spline_bearing_block()}
    for name, shape in parts.items():
        cq.exporters.export(shape, str(OUT / f"{name}.stl"), tolerance=0.01, angularTolerance=0.1)
        box = shape.val().BoundingBox()
        volume_cm3 = shape.val().Volume() / 1000
        print(f"{name:10} {box.xlen:6.1f} x {box.ylen:5.1f} x {box.zlen:4.1f} mm  {volume_cm3:5.1f} cm3")


if __name__ == "__main__":
    main()
