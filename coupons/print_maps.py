"""Each test print drawn from above, its holes coloured by what happened when Dan tried them.

    uv run python coupons/print_maps.py      # writes docs/media/test-print-maps.png

The outlines are slices of the printed STLs (coupons/out/), at the height where each piece's holes do their
job. Every outcome is read from results/predictions/round3-coupons.yaml. What's typed in here is the job
each piece's holes do, and so which outcomes count as good for it (fit_cards.py has the same rules).
"""
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
import trimesh
import yaml
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

from coupons import OUT
from fit_cards import GOOD, LOOSE, TIGHT, UNTRIED, pass_through, press_fit, said
from round3 import (BOLT_HOLES, F_PITCH, HUB_D, HUB_OVER, N_PITCH, bearing_seat_cells, hole_x,
                            nut_pocket_cells, ring_roof_cells)

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "docs/media/test-print-maps.png"
FONT = "/System/Library/Fonts/Helvetica.ttc"
SCALE, MARGIN = 9, 40  # pixels per mm, pixels round the piece
PLASTIC, INK, MUTED = (70, 72, 78), (25, 25, 25), (110, 110, 110)
DOESNT_COUNT = (120, 120, 200)


class Hole(BaseModel):
    x: float
    y: float
    colour: tuple[int, int, int]
    label: str
    words: str


class Piece(BaseModel):
    title: str
    job: str
    stl: str
    slice_z: float
    holes: list[Hole]
    underside: bool = False  # drawn as seen from below (mirrored), as Dan held it
    parts: list[str] = []  # what goes in the holes, drawn beside the piece at the same scale


def record():
    return yaml.safe_load((ROOT / "results/predictions/round3-coupons.yaml").read_text())


def bolt_piece(r3):
    columns = max(len(sizes) for sizes in BOLT_HOLES.values())
    depth = len(BOLT_HOLES) * F_PITCH + 6
    rows = {"M8": "M8", "Q": "1/4-20"}
    holes = []
    for row, (name, sizes) in enumerate(BOLT_HOLES.items()):
        y = depth - F_PITCH / 2 - row * F_PITCH
        for column, size in enumerate(sizes):
            found = next(h for h in r3["F_bolt_holes"]["holes"] if h["bolt"] == rows[name] and h["hole_d"] == size)
            holes.append(Hole(x=hole_x(column), y=y, colour=pass_through(found["outcome"]), label=f"{size:g}",
                              words=said(found["outcome"])))
    del columns
    return Piece(title="F: bolt holes (M8 top row, 1/4-20 bottom)", job="green: the bolt passes through by hand",
                 stl="F-bolt-holes", slice_z=2.5, holes=holes, parts=["M8 bolt", "1/4-20 bolt"])


def ring_roof_piece(r3):
    by_name = {c["cell"]: c for c in r3["G_ring_roofs"]["cells"]}
    holes = []
    for cell, x, y in ring_roof_cells():
        outcome = by_name[cell.name]["outcome"]
        colour = TIGHT if "messed up" in outcome else GOOD
        holes.append(Hole(x=x, y=y, colour=colour, label=cell.name, words=said(outcome).split(";")[0]))
    return Piece(title="G: ring roofs, seen from underneath", job="green: the roof over the pocket printed solid",
                 stl="G-ring-roofs", slice_z=1.5, holes=holes, underside=True,
                 parts=["M3 nut", "M5 nut", "608 bearing"])


def bearing_piece(r3):
    by_name = {s["cell"]: s for s in r3["H_bearings"]["seats"]}
    holes = []
    for seat, x, y in bearing_seat_cells():
        outcome = by_name[seat.name]["outcome"]
        proud = f", {seat.short:g} proud" if seat.short else ("" if seat.shoulder else ", no shoulder")
        holes.append(Hole(x=x, y=y, colour=press_fit(outcome), label=f"{seat.diameter:g}{proud}", words=said(outcome).split(";")[0]))
    return Piece(title="H: 608 bearing seats", job="green: presses in by thumb and stays upside down",
                 stl="H-bearings", slice_z=7.5, holes=holes, parts=["608 bearing"])


def nut_piece(r3):
    by_name = {p["cell"]: p for p in r3["I_nuts"]["pockets"]}
    holes = []
    for cell, x, y in nut_pocket_cells():
        found = by_name[cell.name]
        outcome = found.get("outcome_pressed_with_bolt") or found["outcome"]
        colour = DOESNT_COUNT if cell.name == "R1" else press_fit(outcome)
        words = "rib sheared: doesn't count" if cell.name == "R1" else said(outcome).split(";")[0]
        holes.append(Hole(x=x, y=y, colour=colour, label=f"{cell.name} {cell.nut}", words=words))
    return Piece(title="I: nut pockets (pressed in on a bolt)", job="green: the nut goes in and stays upside down",
                 stl="I-nuts", slice_z=6.5, holes=holes, parts=["M5 nut", "M3 nut"])


def horn_piece(r3):
    pockets = r3["N_horn_pockets"]["pockets"]
    holes = []
    for i, over in enumerate(HUB_OVER):
        found = next(p for p in pockets if p["over_hub"] == over)
        holes.append(Hole(x=2 + N_PITCH / 2 + i * N_PITCH, y=2 + N_PITCH / 2, colour=press_fit(found["outcome"]),
                          label=f"{HUB_D + over:.2f}", words=said(found["outcome"]).split(":")[0]))
    return Piece(title="N: servo horn hub pockets", job="green: the hub sits in without forcing and stays",
                 stl="N-horn-pockets", slice_z=4.0, holes=holes, parts=["25T horn"])


def frame_pieces(r3):
    out = []
    for frame in r3["M_servo_mount"]["frames"]:
        c = frame["frame_clearance"]
        out.append(Piece(title=f"M3: servo frame, {c:g} mm a side", job="green: slides on over the servo body",
                         stl=f"M3-servo-frame-{c:g}", slice_z=1.5,
                         holes=[Hole(x=0, y=0, colour=press_fit(frame["outcome"]), label=f"{19.82 + 2 * c:.2f} wide",
                                     words=said(frame["outcome"]).split(",")[0])], parts=["MG996R servo"] if c else []))
    return out


def outline(piece):
    mesh = trimesh.load(OUT / f"{piece.stl}.stl")
    section = mesh.section(plane_origin=[0, 0, piece.slice_z], plane_normal=[0, 0, 1])
    planar, _ = section.to_2D(to_2D=np.eye(4), check=False)
    loops = sorted((Polygon(points) for points in planar.discrete if len(points) > 3), key=lambda loop: -loop.area)
    return mesh.bounds, loops


METAL, METAL_DARK = (190, 192, 198), (120, 122, 130)


def hexagon(cx, cy, across_flats):
    r = across_flats / 2 / 0.866 * SCALE
    return [(cx + r * c, cy + r * s) for c, s in ((1, 0), (.5, .866), (-.5, .866), (-1, 0), (-.5, -.866), (.5, -.866))]


def circle(d, cx, cy, diameter, **kw):
    r = diameter / 2 * SCALE
    d.ellipse([cx - r, cy - r, cx + r, cy + r], **kw)


def draw_bolt(d, x, y, shank, head_af, head_h, length):
    """A hex bolt from the side, head on the left, at true size."""
    hw, hh = head_h * SCALE, head_af * SCALE
    d.rectangle([x, y - hh / 2, x + hw, y + hh / 2], fill=METAL, outline=METAL_DARK, width=2)
    sw, sh = length * SCALE, shank * SCALE
    d.rectangle([x + hw, y - sh / 2, x + hw + sw, y + sh / 2], fill=METAL, outline=METAL_DARK, width=2)
    for k in range(int(length / 1.25)):
        tx = x + hw + 6 + k * 1.25 * SCALE
        d.line([tx, y - sh / 2, tx + 6, y + sh / 2], fill=METAL_DARK, width=1)
    return hw + sw, hh


def draw_part(d, name, x, y):
    """One part at true size with its top-left near (x, y); returns its width and height in pixels."""
    if name in ("M8 bolt", "1/4-20 bolt"):
        shank, head = (8.0, 13.0) if name == "M8 bolt" else (6.35, 11.1)
        w, h = draw_bolt(d, x, y + 13 * SCALE / 2, shank, head, 5.3, 30)
        return w, 13 * SCALE
    if name in ("M5 nut", "M3 nut"):
        af, bore = (8.0, 5.0) if name == "M5 nut" else (5.5, 3.0)
        cx, cy = x + af * SCALE / 2 / 0.866, y + af * SCALE / 2
        d.polygon(hexagon(cx, cy, af), fill=METAL, outline=METAL_DARK)
        circle(d, cx, cy, bore, fill="white", outline=METAL_DARK)
        return af * SCALE / 0.866, af * SCALE
    if name == "608 bearing":
        cx, cy = x + 11 * SCALE, y + 11 * SCALE
        circle(d, cx, cy, 22, fill=METAL, outline=METAL_DARK, width=2)
        circle(d, cx, cy, 13, fill=METAL_DARK)
        circle(d, cx, cy, 12, fill=METAL)
        circle(d, cx, cy, 8, fill="white", outline=METAL_DARK, width=2)
        return 22 * SCALE, 22 * SCALE
    if name == "25T horn":
        cx, cy = x + 7.33 * SCALE, y + 7.33 * SCALE
        d.rounded_rectangle([cx, cy - 4 * SCALE, cx + 30 * SCALE, cy + 4 * SCALE], radius=4 * SCALE, fill=METAL, outline=METAL_DARK, width=2)
        circle(d, cx, cy, 14.66, fill=METAL, outline=METAL_DARK, width=2)
        circle(d, cx, cy, 3.4, fill="white", outline=METAL_DARK)
        for r in (20.4, 24.1):
            circle(d, cx + r * SCALE, cy, 2.5, fill="white", outline=METAL_DARK)
        return 38 * SCALE, 14.66 * SCALE
    if name == "MG996R servo":
        bw, bh = 40.58 * SCALE, 19.82 * SCALE
        tab = 4 * SCALE
        d.rectangle([x, y + 3 * SCALE, x + bw + 2 * tab, y + bh - 3 * SCALE], fill=(40, 40, 40))
        d.rectangle([x + tab, y, x + tab + bw, y + bh], fill=(25, 25, 25))
        circle(d, x + tab + bw * 0.75, y + bh / 2, 6, fill=(200, 160, 60))
        return bw + 2 * tab, bh
    raise ValueError(name)


def part_panel_width(piece):
    return 0 if not piece.parts else int(max(48 if "bolt" in n else 40 for n in piece.parts) * SCALE + 60)


def draw_piece(piece, fonts):
    big, small = fonts
    bounds, polygons = outline(piece)
    (x0, y0, _), (x1, y1, _) = bounds
    w, h = (x1 - x0) * SCALE, (y1 - y0) * SCALE
    columns = 1 if w < 700 else 2
    label_room = ((len(piece.holes) + columns - 1) // columns) * 30 + 20
    panel = part_panel_width(piece)
    parts_h = sum(26 * SCALE + 40 for _ in piece.parts)
    im = Image.new("RGB", (int(w + 2 * MARGIN + panel), int(max(h + 2 * MARGIN, parts_h) + 110 + label_room)), "white")
    d = ImageDraw.Draw(im)
    d.text((MARGIN, 14), piece.title, font=big, fill=INK)
    d.text((MARGIN, 60), piece.job, font=small, fill=MUTED)
    top = 110

    def px(x, y):
        x = x1 - x + x0 if piece.underside else x
        return MARGIN + (x - x0) * SCALE, top + MARGIN + (y1 - y) * SCALE

    def nearest(poly):
        cx, cy = poly.centroid.x, poly.centroid.y
        best = min(piece.holes, key=lambda hole: (hole.x - cx) ** 2 + (hole.y - cy) ** 2)
        size = max(poly.bounds[2] - poly.bounds[0], poly.bounds[3] - poly.bounds[1])
        close = (best.x - cx) ** 2 + (best.y - cy) ** 2 < (size / 2) ** 2 and size > 3
        return best if close else None

    for loop in polygons:  # largest first; a loop inside an odd number of others is a hole
        inside = sum(other.contains(loop.representative_point()) for other in polygons if other is not loop and other.area > loop.area)
        points = [px(*p) for p in loop.exterior.coords]
        if inside % 2 == 0:
            d.polygon(points, fill=PLASTIC)
            continue
        match = nearest(loop)
        if match is None:
            d.polygon(points, fill="white")
            continue
        d.polygon(points, fill="white", outline=match.colour, width=7)
    for hole in piece.holes:
        hx, hy = px(hole.x, hole.y)
        d.text((hx, hy), hole.label, font=small, fill=INK, anchor="mm")
    py = top + MARGIN
    for name in piece.parts:
        pw, ph = draw_part(d, name, w + 2 * MARGIN, py + 24)
        d.text((w + 2 * MARGIN, py), name, font=small, fill=MUTED)
        py += ph + 70
    legend_y = top + max(h + 2 * MARGIN, py - top)
    for i, hole in enumerate(piece.holes):
        col, row = i % columns, i // columns
        x, y = MARGIN + col * (w / columns), legend_y + row * 30
        room = int((w / columns - 50) / 11)
        d.ellipse([x, y + 4, x + 20, y + 24], fill=hole.colour)
        d.text((x + 30, y), f"{hole.label}: {hole.words}"[:room], font=small, fill=INK)
    return im


def stack(tiles, width):
    rows, row, used = [], [], 0
    for tile in tiles:
        if used + tile.width > width and row:
            rows.append(row)
            row, used = [], 0
        row.append(tile)
        used += tile.width
    rows.append(row)
    height = sum(max(t.height for t in r) for r in rows)
    sheet = Image.new("RGB", (width, height + 90), "white")
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(FONT, 24)
    d.text((MARGIN, 20), "Round 3 test prints on our X1C (0.20 mm Standard, 4 walls, 15% infill, black PLA), as Dan tried them, "
                         "2026-11-11 and 12", font=font, fill=INK)
    x = MARGIN
    for colour, words in ((TIGHT, "too tight / failed"), (GOOD, "good"), (LOOSE, "too loose"), (UNTRIED, "not tried"),
                          (DOESNT_COUNT, "doesn't count")):
        d.ellipse([x, 56, x + 24, 80], fill=colour)
        d.text((x + 34, 54), words, font=font, fill=INK)
        x += 290
    y = 90
    for r in rows:
        x = 0
        for tile in r:
            sheet.paste(tile, (x, y))
            x += tile.width
        y += max(t.height for t in r)
    return sheet


def main():
    r3 = record()
    fonts = (ImageFont.truetype(FONT, 34), ImageFont.truetype(FONT, 22))
    pieces = [bolt_piece(r3), horn_piece(r3), bearing_piece(r3), ring_roof_piece(r3), nut_piece(r3), *frame_pieces(r3)]
    tiles = [draw_piece(piece, fonts) for piece in pieces]
    sheet = stack(tiles, width=2200)
    DEST.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(DEST)
    print(f"wrote {DEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
