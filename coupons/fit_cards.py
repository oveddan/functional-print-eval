"""One picture per fit learned from the test prints: the part, the hole, and which sizes worked.

    uv run python coupons/fit_cards.py      # writes docs/media/fit-cards.png

Every size and outcome is read from the round 3 and 3b records in results/predictions/ (Dan's outcomes,
2026-11-11 and 12) or catalog/connectors.yaml. What's typed in here is only the job each card asks of the
fit, and so which outcomes count as good for that job: a bolt that screws in is too tight for a hole it
should pass through.
"""
import re
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "docs/media/fit-cards.png"
FONT = "/System/Library/Fonts/Helvetica.ttc"
GOOD, LOOSE, TIGHT, UNTRIED = (46, 160, 67), (230, 150, 20), (210, 50, 50), (165, 165, 165)
INK, MUTED, PART, HOLE = (25, 25, 25), (110, 110, 110), (150, 155, 165), (60, 60, 60)
CARD_W, CARD_H, HEADER_H = 1100, 520, 120


class Try(BaseModel):
    size: float
    said: str
    colour: tuple[int, int, int]


class Card(BaseModel):
    title: str
    job: str
    part_label: str
    part_size: float | None
    unit: str
    tries: list[Try]
    use: str
    shape: str = "round"  # round, hex, slot or strand


def load(path):
    return yaml.safe_load((ROOT / path).read_text())


def said(text):
    """Dan's words without the attribution."""
    return (text or "not tried").split(" (Dan")[0].replace("'the only successful one was the bottom row M5, second one' ", "")


def has(text, *words):
    return any(word in (text or "").lower() for word in words)


def untried(text):
    return not text or text.lower().startswith("not reported")


def pass_through(text):
    """A bolt that should slide through: screwing in is too tight."""
    if untried(text):
        return UNTRIED
    return TIGHT if has(text, "screws in") else GOOD


def press_fit(text):
    """A part that should press in and stay."""
    if untried(text):
        return UNTRIED
    if has(text, "too loose", "too big"):
        return LOOSE
    if has(text, "won't", "doesn't go", "doesn't fit", "doesn't really"):
        return TIGHT
    return GOOD


def use_range(tries, unit_word="mm"):
    good = sorted(t.size for t in tries if t.colour == GOOD)
    if not good:
        return "nothing tried fits"
    return f"use {good[0]:g} {unit_word}" if len(good) == 1 else f"use {good[0]:g} to {good[-1]:g} {unit_word}"


def bolt_cards(r3):
    out = []
    for bolt, size in (("M8", 8.0), ("1/4-20", 6.35)):
        holes = [h for h in r3["F_bolt_holes"]["holes"] if h["bolt"] == bolt]
        tries = [Try(size=h["hole_d"], said=said(h["outcome"]), colour=pass_through(h["outcome"])) for h in holes]
        first_good = min(t.size for t in tries if t.colour == GOOD)
        out.append(Card(title=f"{bolt} bolt through a hole", job="the bolt should pass through by hand",
                        part_label=f"{bolt} bolt, {size:g}", part_size=size, unit="hole diameter, mm", tries=tries,
                        use=f"use {first_good:g} mm or more"))
    return out


def bearing_card(r3):
    seats = [s for s in r3["H_bearings"]["seats"] if s["shoulder"] and s["bearing_stands_out_mm"] in (0, 0.2)]
    seats = [s for s in seats if s["cell"] != "5" or True]
    by_size = {}
    for seat in seats:
        by_size.setdefault(seat["seat_d"], seat)
    tries = [Try(size=d, said=said(s["outcome"]), colour=press_fit(s["outcome"])) for d, s in sorted(by_size.items())]
    return Card(title="608 bearing pressed into a seat", job="presses in by thumb and stays in upside down",
                part_label="608 bearing, 22", part_size=22.0, unit="seat diameter, mm", tries=tries, use=use_range(tries))


def horn_card(r3):
    tries = [Try(size=p["pocket_d"], said=said(p["outcome"]), colour=press_fit(p["outcome"]))
             for p in r3["N_horn_pockets"]["pockets"]]
    return Card(title="Servo horn hub in a pocket", job="sits in without forcing and doesn't fall out",
                part_label="25T horn hub, 14.66", part_size=14.66, unit="pocket diameter, mm", tries=tries, use=use_range(tries))


def nut_cards(r3):
    pockets = r3["I_nuts"]["pockets"]
    plain = [p for p in pockets if p["cell"].startswith("U")]
    tries = [Try(size=round(p["af"] if "af" in p else 8.0 + p["clearance"], 2), said=said(p.get("outcome_pressed_with_bolt")),
                 colour=press_fit(p.get("outcome_pressed_with_bolt"))) for p in plain]
    tries = [Try(size=round(8.0 + p["clearance"], 2), said=t.said, colour=t.colour) for p, t in zip(plain, tries)]
    lips = [p for p in pockets if p["cell"].startswith("L")]
    lip_tries = [Try(size=p["lip_af"], said=said(p["outcome"]), colour=press_fit(p["outcome"])) for p in lips]
    return [
        Card(title="M5 nut in a plain hex pocket", job="pressed in on a bolt, stays in upside down",
             part_label="M5 nut, 8.0 across flats", part_size=8.0, unit="pocket across flats, mm",
             tries=sorted(tries, key=lambda t: t.size), use=use_range(tries), shape="hex"),
        Card(title="M5 nut past a lip at the mouth", job="pushes past the lip by thumb and stays",
             part_label="M5 nut, 8.0 across flats", part_size=8.0, unit="lip across flats, mm",
             tries=sorted(lip_tries, key=lambda t: t.size), use=use_range(lip_tries), shape="hex"),
    ]


def servo_card(r3):
    body = 19.82  # catalog/hardware.yaml, MG996R width
    tries = [Try(size=round(body + 2 * f["frame_clearance"], 2), said=said(f["outcome"]), colour=press_fit(f["outcome"]))
             for f in r3["M_servo_mount"]["frames"]]
    return Card(title="MG996R servo body in a cutout", job="slides on over the body from the top",
                part_label="servo body, 19.82 wide", part_size=body, unit="cutout width, mm", tries=tries,
                use=use_range(tries) + " (everything tried fit)", shape="slot")


def strand_card(r3, r3b):
    tries = []
    for cell in r3["G_ring_roofs"]["cells"]:
        found = re.search(r"longest ([\d.]+) mm", cell["why"])
        if found and cell["cell"] in ("2", "3", "4", "5"):
            colour = TIGHT if has(cell["outcome"], "messed up") else GOOD
            tries.append(Try(size=float(found.group(1)), said=f"ring roof {cell['cell']}: {said(cell['outcome'])}", colour=colour))
    for crop in r3b["roof_crops"]["crops"]:
        if "gpt" in crop["trial"] and crop.get("outcome"):
            tries.append(Try(size=crop["longest"], said=f"GPT's roof: {said(crop['outcome'])}", colour=GOOD))
    return Card(title="A roof strand with nothing under it", job="prints as a solid roof, no loose strands",
                part_label="", part_size=None, unit="longest unsupported strand, mm", tries=sorted(tries, key=lambda t: t.size),
                use="keep strands to 6.8 mm or less", shape="strand")


def plug_card():
    plug = load("catalog/connectors.yaml")["usb_c_plug_overmold"]["measured"]
    return Card(title="USB-C plug head (measured)", job="the opening has to pass the plastic head, not just the metal",
                part_label=f"{plug['head_width_mm']} x {plug['head_thickness_mm']} head, {plug['metal_length_mm']} mm of metal",
                part_size=None, unit="calipers on Dan's charger plug", tries=[],
                use=f"opening over {plug['head_width_mm']} x {plug['head_thickness_mm']}, within {plug['metal_length_mm']} mm of the port",
                shape="slot")


def cards():
    r3 = load("results/predictions/round3-coupons.yaml")
    r3b = load("results/predictions/round3b-roofs.yaml")
    return [*bolt_cards(r3), bearing_card(r3), horn_card(r3), *nut_cards(r3), servo_card(r3), strand_card(r3, r3b), plug_card()]


def draw_part(d, shape, cx, cy):
    """The part (grey) in its hole (dark), seen end on."""
    if shape == "slot":
        d.rounded_rectangle([cx - 110, cy - 55, cx + 110, cy + 55], radius=18, fill=HOLE)
        d.rounded_rectangle([cx - 98, cy - 43, cx + 98, cy + 43], radius=12, fill=PART)
    elif shape == "hex":
        hexagon = lambda r: [(cx + r * c, cy + r * s) for c, s in ((1, 0), (.5, .866), (-.5, .866), (-1, 0), (-.5, -.866), (.5, -.866))]
        d.polygon(hexagon(84), fill=HOLE)
        d.polygon(hexagon(72), fill=PART)
        d.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill="white")
    elif shape == "strand":
        d.rectangle([cx - 110, cy - 10, cx - 70, cy + 70], fill=HOLE)
        d.rectangle([cx + 70, cy - 10, cx + 110, cy + 70], fill=HOLE)
        d.line([cx - 70, cy - 4, cx + 70, cy - 4], fill=PART, width=8)
        d.arc([cx - 70, cy - 30, cx + 70, cy + 40], 20, 160, fill=TIGHT, width=4)
    else:
        d.ellipse([cx - 84, cy - 84, cx + 84, cy + 84], fill=HOLE)
        d.ellipse([cx - 72, cy - 72, cx + 72, cy + 72], fill=PART)


def draw_gauge(d, card, x0, x1, y, small):
    sizes = [t.size for t in card.tries] + ([card.part_size] if card.part_size else [])
    span = max(sizes) - min(sizes)
    lo, hi = min(sizes) - span * 0.08, max(sizes) + span * 0.08
    at = lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)
    d.line([x0, y, x1, y], fill=MUTED, width=4)
    ends = ("shorter", "longer") if card.shape == "strand" else ("tighter", "looser")
    d.text((x0, y + 52), ends[0], font=small, fill=MUTED)
    d.text((x1, y + 52), ends[1], font=small, fill=MUTED, anchor="ra")
    if card.part_size:
        px = at(card.part_size)
        d.polygon([(px, y - 10), (px - 13, y - 34), (px + 13, y - 34)], fill=INK)
        d.text((px, y - 40), "part", font=small, fill=INK, anchor="mb")
    for t in card.tries:
        x = at(t.size)
        d.ellipse([x - 15, y - 15, x + 15, y + 15], fill=t.colour)
        d.text((x, y + 22), f"{t.size:g}", font=small, fill=INK, anchor="mt")


def draw_plug(d, card, small):
    """The plug from the side: bare metal, then the moulded head, with the measured sizes."""
    plug = load("catalog/connectors.yaml")["usb_c_plug_overmold"]["measured"]
    y, x = 300, 360
    d.rounded_rectangle([x, y - 22, x + 120, y + 22], radius=8, fill=PART)
    d.rounded_rectangle([x + 120, y - 60, x + 420, y + 60], radius=20, fill=HOLE)
    d.rectangle([x + 420, y - 20, x + 640, y + 20], fill=HOLE)
    d.line([x, y + 90, x + 120, y + 90], fill=TIGHT, width=3)
    d.text((x + 60, y + 100), f"{plug['metal_length_mm']} metal", font=small, fill=TIGHT, anchor="mt")
    d.line([x + 440, y - 60, x + 440, y + 60], fill=TIGHT, width=3)
    d.text((x + 455, y - 70), f"{plug['head_width_mm']} wide", font=small, fill=TIGHT)
    d.text((x + 455, y + 45), f"{plug['head_thickness_mm']} thick", font=small, fill=TIGHT)
    d.text((x, 440), "one charger cable, calipers, 2026-11-12", font=small, fill=MUTED)


def draw_card(card, fonts):
    big, small = fonts
    im = Image.new("RGB", (CARD_W, CARD_H), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, CARD_W - 1, CARD_H - 1], outline=(215, 215, 215), width=3)
    d.text((30, 22), card.title, font=big, fill=INK)
    d.text((30, 72), card.job, font=small, fill=MUTED)
    d.text((30, 108), card.use, font=big, fill=GOOD)
    draw_part(d, card.shape, 150, 290)
    if card.tries:
        d.text((150, 395), card.part_label, font=small, fill=MUTED, anchor="mt")
    if not card.tries:
        draw_plug(d, card, small)
        return im
    draw_gauge(d, card, 320, CARD_W - 50, 230, small)
    d.text((320, 330), card.unit, font=small, fill=MUTED)
    for i, t in enumerate(card.tries):
        y = 368 + i * 30
        d.ellipse([320, y + 4, 340, y + 24], fill=t.colour)
        d.text((352, y), f"{t.size:g}: {t.said}"[:58], font=small, fill=INK)
    return im


def header(fonts):
    big, small = fonts
    im = Image.new("RGB", (CARD_W * 2, HEADER_H), "white")
    d = ImageDraw.Draw(im)
    d.text((30, 18), "What fit on our X1C: 0.20 mm Standard, 4 walls, 15% infill, black PLA. From Dan's test prints, 2026-11-11 and 12.",
           font=small, fill=INK)
    x = 30
    for colour, words in ((TIGHT, "too tight / failed"), (GOOD, "good"), (LOOSE, "too loose"), (UNTRIED, "not tried")):
        d.ellipse([x, 66, x + 28, 94], fill=colour)
        d.text((x + 40, 64), words, font=small, fill=INK)
        x += 320
    return im


def main():
    fonts = (ImageFont.truetype(FONT, 38), ImageFont.truetype(FONT, 24))
    tiles = [draw_card(card, fonts) for card in cards()]
    rows = (len(tiles) + 1) // 2
    sheet = Image.new("RGB", (CARD_W * 2, HEADER_H + rows * CARD_H), "white")
    sheet.paste(header(fonts), (0, 0))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % 2) * CARD_W, HEADER_H + (i // 2) * CARD_H))
    DEST.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(DEST)
    print(f"wrote {DEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
