"""Write the predictions for round 3 before it's printed.

    uv run python coupons/predict3.py

G's roofs: the bridge check, unchanged. Everything else: Claude's expectation from rounds
1 and 2, not a grader. Each row says which record it leans on, so a result can prove it wrong.
"""
import datetime
from pathlib import Path

import trimesh
import yaml

from coupons import OUT
from pbe.graders.bridges import overhangs, settings
from predict import commit_hash, refuse_to_overwrite_outcomes
from round3 import (HUB_D, HUB_OVER, M_FRAMES, M_PLATES, RIB_W, POST_DS, POST_HOLE, BOLT_HOLES, H_SEATS, I_POCKETS, ring_roof_cells)

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "results/predictions/round3-coupons.yaml"

EXPECT_HOLE = {  # printed holes come out small: round 1's 10 mm peg was tight at +0.1 a side and slid at +0.2
    "M8": {8.0: "won't go through, or only screwed in", 8.1: "goes through, threads drag", 8.2: "goes through with light drag",
           8.3: "slides through", 8.4: "slides through (ISO 273 fine clearance)"},
    "Q": {6.35: "won't go through, or only screwed in", 6.5: "goes through, threads drag", 6.6: "goes through with light drag",
          6.8: "slides through (6.8 printed fine on the tripod plate)"},
}
EXPECT_SEAT = {  # round 2: 22.0 wouldn't go in; 22.1, 22.2 and 22.3 went in and held upside down
    22.05: "won't go in, or only pressed hard", 22.4: "goes in, holds upside down, barely",
    22.5: "goes in, falls out upside down", 22.7: "drops in, loose",
}


def hole_rows():
    return [{"bolt": "M8" if name == "M8" else "1/4-20", "column_dots": column, "hole_d": diameter,
             "expected": EXPECT_HOLE[name][diameter], "outcome": None}
            for name, sizes in BOLT_HOLES.items() for column, diameter in enumerate(sizes)]


def roof_rows():
    found = overhangs(trimesh.load(OUT / "G-ring-roofs.stl"))
    rows = []
    for cell, x, y in ring_roof_cells():
        reach = cell.pocket / 2 + 1
        near = [o for o in found if abs(o.region.centroid.x - x) < reach and abs(o.region.centroid.y - y) < reach]
        if not near:
            check = "no bridge: the ledge is within the small-overhang guess (1.5 mm), so taken to print clean"
            prediction = "clean"
        else:
            worst = min(near, key=lambda o: o.anchored)
            prediction = "clean" if all(o.ok for o in near) else "tangled or sagging"
            check = f"{worst.anchored:.0%} of strands anchored at both ends, longest {worst.longest:.1f} mm"
        rows.append({"cell": cell.name, "pocket": f"{'hex ' if cell.hex else ''}{cell.pocket} mm", "hole_d": cell.hole,
                     "ledge_mm": cell.ledge, "stepped": cell.stepped, "prediction": prediction, "why": check,
                     "outcome": None, "notes": None})
    return rows


def seat_rows():
    rows = []
    for seat in H_SEATS:
        if not seat.shoulder:
            expected = "presses in and holds, but a push from either side moves it: nothing stops it"
        elif seat.short:
            expected = f"presses in and holds, standing {seat.short} mm out of the top"
        else:
            expected = EXPECT_SEAT[seat.diameter]
        rows.append({"cell": seat.name, "seat_d": seat.diameter, "bearing_stands_out_mm": seat.short,
                     "shoulder": seat.shoulder, "expected": expected, "outcome": None, "notes": None})
    return rows


def nut_expectation(cell):
    if cell.lip_af is not None:
        return f"presses in past the lip with force (the lip bites {cell.bite} mm a side), then holds upside down"
    if cell.ribs:
        return f"presses in with force, crushing each rib by {cell.bite} mm, and holds upside down"
    if cell.clearance <= -0.1:
        return "won't go in by hand (round 1: M5 at +0.0 held, tight)"
    return "forced in, or won't go in"


def nut_rows():
    return [{"cell": cell.name, "nut": cell.nut, "clearance": cell.clearance, "ribs": cell.ribs,
             "rib_shape": cell.rib_shape if cell.ribs else None, "rib_size": cell.rib_size or None,
             "rib_stands": cell.rib_stands or None, "lip_af": cell.lip_af, "bite": cell.bite,
             "expected": nut_expectation(cell), "outcome": None, "notes": None} for cell in I_POCKETS]


def post_rows():
    rows = []
    for diameter in POST_DS + ["8 solid"]:
        wall = (8 if diameter == "8 solid" else diameter) - POST_HOLE
        rows.append({"post": diameter, "plastic_around_insert_mm": round(wall / 2, 2),
                     "infill": "100% (set in the slicer)" if diameter == "8 solid" else "the plate's",
                     "expected": {5.5: "flares and splits", 6: "flares when the insert goes in", 7: "bulges a little, insert sits off-centre",
                                  8: "holds, insert straight", "8 solid": "holds, insert straight"}[diameter],
                     "outcome": None, "notes": None})
    return rows


def servo_rows():
    plates = [{"plate": spec.name, "clearance": spec.clearance,
               "channels": [round(width, 2) for width in spec.channels],
               "channel_room_a_side": [round((width - RIB_W) / 2, 3) for width in spec.channels],
               "expected": ("servo comes up from underneath, tabs flush with the ribs in their channels; "
                            "M3 screws find all four holes, so the 10 mm across a tab is right" if spec.name == "M1" else
                            "the 0.05-a-side channel (dotted end) binds or rocks the tab; the 0.15 side sits flush"),
               "outcome": None, "notes": None} for spec in M_PLATES]
    frames = [{"frame_clearance": clearance,
               "expected": "won't go through" if clearance == 0 else "goes through tight",
               "outcome": None} for clearance in M_FRAMES]
    return {"plates": plates, "frames": frames}


def horn_rows():
    expected = {0.1: "hub goes in tight or not at all", 0.5: "hub goes in, a little play", 1.0: "hub drops in, loose"}
    return [{"pocket_d": round(HUB_D + over, 2), "over_hub": over, "expected": expected[over], "outcome": None}
            for over in HUB_OVER]


def main():
    refuse_to_overwrite_outcomes(DEST)
    doc = {
        "written": datetime.datetime.now().astimezone().isoformat(timespec="minutes"),
        "code_at": f"{commit_hash()} + coupons/round3.py as committed with these predictions",
        "printer": "Bambu Lab X1C",
        "print_settings": {"layer_mm": 0.2, "supports": "off", "filament": "the same PLA as rounds 1 and 2",
                           "walls": 4, "infill": "15%"},
        "F_bolt_holes": {"source": "Claude's expectation, not a grader", "how_to_test": "push each bolt through by hand",
                         "holes": hole_rows()},
        "G_ring_roofs": {"source": "bridge check (pbe/graders/bridges.py), unchanged", "settings": settings(),
                         "how_to_test": "look at each roof from underneath: clean, sagging, or loose strands",
                         "cells": roof_rows()},
        "H_bearings": {"source": "Claude's expectation from round 2's seats, not a grader",
                       "how_to_test": "press a 608 in, turn the block over, shake; measure how far it stands out",
                       "seats": seat_rows()},
        "I_nuts": {"source": "Claude's expectation, not a grader", "how_to_test": "press in, turn over, shake",
                   "pockets": nut_rows()},
        "M_servo_mount": {"source": "Claude's expectation from test print D, not a grader. For tasks/servo-mount "
                                    "(branch claude/servo-mount): R1's 0 to 0.25 band, R3's rib channel, R2's 10 mm",
                          "how_to_test": "push the MG996R up through each frame and plate from underneath, shaft first; "
                                         "on M1 and M2, check both tabs sit flat and try an M3 screw through each hole",
                          **servo_rows()},
        "N_horn_pockets": {"source": "Claude's expectation, not a grader. For tasks/servo-arm's R4 with the aluminium horn",
                           "how_to_test": "set the 25T aluminium horn's hub into each pocket, face down",
                           "pockets": horn_rows()},
        "L_insert_posts": {"source": "Claude's expectation, against Dan's 2026-11-08 reading that Estoa's 8 mm posts "
                                     "bulged because of 100% infill. At 1.85 mm a side, four 0.4 mm walls are most of the "
                                     "post at any infill, so Claude expects infill to change little either way",
                           "how_to_test": "set an M3 x 4 x 5 insert in each with the chisel tip, as on Estoa; look for "
                                          "flaring, bending, an insert off-centre",
                           "posts": post_rows()},
    }
    DEST.write_text(yaml.safe_dump(doc, sort_keys=False, width=120))
    print(f"wrote {DEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
