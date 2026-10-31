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

OUT = Path(__file__).resolve().parent / "out"
LABEL_DEPTH = 0.6


def label(body, text, x, y, top, size=5):
    t = cq.Workplane("XY").workplane(offset=top - LABEL_DEPTH).center(x, y).text(text, size, LABEL_DEPTH + 0.1, halign="center", valign="center")
    return body.cut(t)


# --- A: bridges -------------------------------------------------------------------
BRIDGE_CELLS = [  # (label, pocket size, hole: None | "plain" | "stepped")
    ("20", 20, None), ("30", 30, None), ("40", 40, None), ("50", 50, None),
    ("H", 20, "plain"), ("S", 20, "stepped"),
]
A_WALL, A_DEPTH, A_ROOF, A_HOLE, A_STEP = 4, 3, 3, 6, 0.4
A_WIDTH = 50 + 2 * A_WALL  # every pocket centred in a band this wide


A2_CELLS = [("40", 40, None), ("50", 50, None)]  # round 2: only the pair that contradicted the span limit


def bridges(spec=BRIDGE_CELLS):
    cells, x = [], A_WALL
    for name, size, hole in spec:
        cells.append((name, size, hole, x + size / 2))
        x += size + A_WALL
    length, h = x, A_DEPTH + A_ROOF
    body = cq.Workplane("XY").box(length, A_WIDTH, h, centered=False).translate((0, -A_WIDTH / 2, 0))
    for name, size, hole, cx in cells:
        body = body.cut(cq.Workplane("XY").workplane(offset=-1).center(cx, 0).rect(size, size).extrude(A_DEPTH + 1))
        if hole == "stepped":
            # a strip the hole's width across the whole pocket, then a square, then the hole
            for w, l, steps in ((A_HOLE, size, 1), (A_HOLE, A_HOLE, 2)):
                body = body.cut(cq.Workplane("XY").workplane(offset=A_DEPTH - 0.01).center(cx, 0).rect(w, l).extrude(steps * A_STEP + 0.01))
        if hole:
            body = body.cut(cq.Workplane("XY").workplane(offset=-1).center(cx, 0).circle(A_HOLE / 2).extrude(h + 2))
        body = label(body, name, cx, size / 2 + 4 if size < 50 else -size / 2 + 2, h, size=4) if size < 50 else body
    return body, cells


# --- B: nut pockets ---------------------------------------------------------------
NUTS = [("M3", 5.5, 2.4), ("M5", 8.0, 4.7), ("M8", 13.0, 6.8), ("Q", 11.11, 5.56)]  # Q = 1/4-20
CLEARANCES = [0.0, 0.1, 0.2, 0.3]
B_PITCH, B_FLOOR = 22, 1.6


def nuts():
    h = B_FLOOR + max(n[2] for n in NUTS)
    rows, cols = len(NUTS), len(CLEARANCES)
    w, d = cols * B_PITCH + 12, rows * B_PITCH + 4
    body = cq.Workplane("XY").box(w, d, h, centered=False)
    for r, (name, af, nh) in enumerate(NUTS):
        cy = d - 2 - B_PITCH / 2 - r * B_PITCH
        body = label(body, name, 6, cy, h, size=4)
        for c, cl in enumerate(CLEARANCES):
            cx = 12 + B_PITCH / 2 + c * B_PITCH
            across_corners = (af + cl) / math.cos(math.radians(30))
            body = body.cut(cq.Workplane("XY").workplane(offset=h - nh).center(cx, cy).polygon(6, across_corners).extrude(nh + 1))
    for c, cl in enumerate(CLEARANCES):  # clearance marks along the near edge: 0 to 3 dots
        cx = 12 + B_PITCH / 2 + c * B_PITCH
        for k in range(c):
            body = body.cut(cq.Workplane("XY").workplane(offset=h - LABEL_DEPTH).center(cx + (k - (c - 1) / 2) * 3, 2.2).circle(0.8).extrude(1))
    return body


# --- B2: nut pockets, round 2 ----------------------------------------
# Each size gets its own clearances, centred on its best fit in round 1 (M3 +0.2,
# M5 +0.1, M8 and 1/4-20 +0.0), so the round-1 best is repeated and its neighbours
# are filled in at 0.05 mm steps. Same dots as B: column 1 has none, column 4 has 3.
NUTS2 = {"M3": [0.1, 0.15, 0.2, 0.25], "M5": [0.0, 0.05, 0.1, 0.15],
         "M8": [-0.1, -0.05, 0.0, 0.05], "Q": [-0.1, -0.05, 0.0, 0.05]}


def nuts2():
    h = B_FLOOR + max(n[2] for n in NUTS)
    rows, cols = len(NUTS), len(CLEARANCES)
    w, d = cols * B_PITCH + 12, rows * B_PITCH + 4
    body = cq.Workplane("XY").box(w, d, h, centered=False)
    body = label(body, "2", w - 4, 2.6, h, size=3)  # tells round 2 from round 1
    for r, (name, af, nh) in enumerate(NUTS):
        cy = d - 2 - B_PITCH / 2 - r * B_PITCH
        body = label(body, name, 6, cy, h, size=4)
        for c, cl in enumerate(NUTS2[name]):
            cx = 12 + B_PITCH / 2 + c * B_PITCH
            across_corners = (af + cl) / math.cos(math.radians(30))
            body = body.cut(cq.Workplane("XY").workplane(offset=h - nh).center(cx, cy).polygon(6, across_corners).extrude(nh + 1))
    for c in range(cols):
        cx = 12 + B_PITCH / 2 + c * B_PITCH
        for k in range(c):
            body = body.cut(cq.Workplane("XY").workplane(offset=h - LABEL_DEPTH).center(cx + (k - (c - 1) / 2) * 3, 2.2).circle(0.8).extrude(1))
    return body


# --- C: slide fits ----------------------------------------------------------------
PEG = 10.0
SQUARE_FITS = [0.1, 0.2, 0.3, 0.4]  # per side
BAR_W, BAR_H = 10.0, 6.0
TUNNELS = [  # (label, side, top, bed flare): Estoa's first leg pocket, then its fix
    ("1", 0.2, 0.2, 0.0),
    ("2", 0.35, 0.6, 0.5),
]
C_H = 12


def fits():
    pitch = 18
    w = len(SQUARE_FITS) * pitch + 4
    d = 22 + 36  # was 22 + 30: tunnel 2 broke through the back wall (round 1 print)
    body = cq.Workplane("XY").box(w, d, C_H, centered=False)
    for i, c in enumerate(SQUARE_FITS):
        cx = 2 + pitch / 2 + i * pitch
        s = PEG + 2 * c
        body = body.cut(cq.Workplane("XY").workplane(offset=-1).center(cx, 11).rect(s, s).extrude(C_H + 2))
        for k in range(i + 1):  # 1 to 4 dots
            body = body.cut(cq.Workplane("XY").workplane(offset=C_H - LABEL_DEPTH).center(cx + (k - i / 2) * 2.5, 20.5).circle(0.7).extrude(1))
    # tunnels run along x, open at both ends, sitting on the bed; their roofs are bridges
    for j, (name, side, top, flare) in enumerate(TUNNELS):
        cy = 30 + 6 + j * 12
        tw, th = BAR_W + 2 * side, BAR_H + top
        body = body.cut(cq.Workplane("XY").workplane(offset=-1).center(w / 2, cy).rect(w + 2, tw).extrude(th + 1))
        if flare:
            body = body.cut(cq.Workplane("XY").workplane(offset=-1).center(w / 2, cy).rect(w + 2, tw + 2 * flare).extrude(1 + flare))
        body = label(body, name, 4, cy, C_H, size=4)
    return body


def tunnels():
    """C2 (round 2): C's two tunnels without the square holes, already measured in round 1."""
    w, d = len(SQUARE_FITS) * 18 + 4, 36
    body = cq.Workplane("XY").box(w, d, C_H, centered=False)
    for j, (name, side, top, flare) in enumerate(TUNNELS):
        cy = 12 + j * 12
        tw, th = BAR_W + 2 * side, BAR_H + top
        body = body.cut(cq.Workplane("XY").workplane(offset=-1).center(w / 2, cy).rect(w + 2, tw).extrude(th + 1))
        if flare:
            body = body.cut(cq.Workplane("XY").workplane(offset=-1).center(w / 2, cy).rect(w + 2, tw + 2 * flare).extrude(1 + flare))
        body = label(body, name, 4, cy, C_H, size=4)
    return body


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
import yaml  # noqa: E402

HW = yaml.safe_load((Path(__file__).resolve().parents[1] / "catalog/hardware.yaml").read_text())
SERVO = {s["id"]: s for s in HW["servos"]}
BEARING = HW["bearings"][0]


def val(d):
    return d.get("used", d["measured"] if not isinstance(d["measured"], list) else max(d["measured"]))


SERVO_CUTS = [("MG996R", 0.25), ("MG90S", 0.15), ("MG90S", 0.3)]  # (servo, clearance per side)
D_T, D_GAP = 3, 9
SPLINE_FITS = [0.0, 0.1, 0.2, 0.3]
SEAT_FITS = [0.0, 0.1, 0.2, 0.3]
PEG_DS = [-0.2, -0.1, 0.0]


def servo_plate():
    w = 66
    rows = [(n, c, val(SERVO[n]["body_l"]), val(SERVO[n]["body_w"])) for n, c in SERVO_CUTS]
    d = sum(bw + 2 * c for _, c, _, bw in rows) + D_GAP * (len(rows) + 1)
    body = cq.Workplane("XY").box(w, d, D_T, centered=False)
    y = D_GAP
    for name, c, bl, bw in rows:
        cy = y + bw / 2 + c
        body = body.cut(cq.Workplane("XY").workplane(offset=-1).center(w / 2, cy).rect(bl + 2 * c, bw + 2 * c).extrude(D_T + 2))
        pitch, hole = val(SERVO[name]["tab_hole_pitch"]), val(SERVO[name]["tab_hole_d"])
        across = 10 + hole if name == "MG996R" else hole  # MG996R: one slot spans each tab's hole pair (datasheet 10 mm apart)
        slot_w = 3.0 if name == "MG996R" else 2.0  # self-tapping screw bites the slot sides
        travel = 1.0 if name == "MG996R" else 0.5  # MG90S: more would leave under 1 mm of wall to the cutout
        for sx in (-1, 1):
            body = body.cut(cq.Workplane("XY").workplane(offset=-1).center(w / 2 + sx * pitch / 2, cy)
                            .rect(slot_w + 2 * travel, slot_w if name == "MG90S" else across).extrude(D_T + 2))
        short = "996" if name == "MG996R" else "90S"
        body = label(body, f"{short} {c:.2f}".replace("0.", "."), w / 2, cy + bw / 2 + c + D_GAP / 2, D_T, size=3.5)
        y += bw + 2 * c + D_GAP
    return body


def spline_bearing_block():
    seat_d, floor, bore = BEARING["od"]["used"], 1.2, BEARING["bore"]["nominal"]
    seat_h = BEARING["width"]["nominal"] + 0.2
    h = seat_h + floor
    pitch = seat_d + 6
    cols = len(SEAT_FITS)
    w = 12 + cols * pitch
    rows_y = {"608": 4 + pitch / 2, "996": 4 + pitch + 6, "90": 4 + pitch + 18, "peg": 4 + pitch + 30}
    d = rows_y["peg"] + 8
    body = cq.Workplane("XY").box(w, d, h, centered=False)
    for c in range(cols):
        cx = 12 + pitch / 2 + c * pitch
        body = body.cut(cq.Workplane("XY").workplane(offset=floor).center(cx, rows_y["608"]).circle((seat_d + SEAT_FITS[c]) / 2).extrude(h))
        body = body.cut(cq.Workplane("XY").workplane(offset=-1).center(cx, rows_y["608"]).circle(6).extrude(floor + 2))  # push the bearing out
        for row, servo in (("996", "MG996R"), ("90", "MG90S")):
            dia = val(SERVO[servo]["spline_od"]) + SPLINE_FITS[c]
            body = body.cut(cq.Workplane("XY").workplane(offset=-1).center(cx, rows_y[row]).circle(dia / 2).extrude(h + 2))
        if c < len(PEG_DS):
            body = body.union(cq.Workplane("XY").workplane(offset=h).center(cx, rows_y["peg"]).circle((bore + PEG_DS[c]) / 2).extrude(8))
        for k in range(c):  # 0 to 3 dots, like B
            body = body.cut(cq.Workplane("XY").workplane(offset=h - LABEL_DEPTH).center(cx + (k - (c - 1) / 2) * 3, rows_y["90"] + 6).circle(0.8).extrude(1))
    for row in ("996", "90"):
        body = label(body, row, 6, rows_y[row], h, size=3.5)
    return body


def main():
    OUT.mkdir(exist_ok=True)
    a, _ = bridges()
    parts = {"A-bridges": a, "B-nuts": nuts(), "B2-nuts": nuts2(), "A2-bridges": bridges(A2_CELLS)[0], "C-fits": fits(), "C2-tunnels": tunnels(), "C-pegs": pegs(),
             "D-servos": servo_plate(), "E-splines-bearings": spline_bearing_block()}
    for name, shape in parts.items():
        cq.exporters.export(shape, str(OUT / f"{name}.stl"), tolerance=0.01, angularTolerance=0.1)
        bb = shape.val().BoundingBox()
        print(f"{name:10} {bb.xlen:6.1f} x {bb.ylen:5.1f} x {bb.zlen:4.1f} mm  {shape.val().Volume() / 1000:5.1f} cm3")


if __name__ == "__main__":
    main()
