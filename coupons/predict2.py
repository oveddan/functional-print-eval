"""Write the predictions for round 2 before it's printed.

    uv run python coupons/predict2.py

A and C's tunnel roofs: the bridge check, unchanged since round 1. A repeats round 1,
so its predictions are the same; C's tunnel 1 already failed once, so that one isn't
blind. B2, D and E: Claude's expectations from round 1's measured fits, not a grader.
D's screw slots also test Claude's reading of the tab-hole pitch from Dan's video
(inner edges, so centres = reading + hole diameter).
"""
import datetime
from pathlib import Path

import trimesh
import yaml
from pydantic import BaseModel

from coupons import A2_CELLS, BRIDGE_CELLS, NUTS, NUTS2, OUT, PEG_DS, SEAT_FITS, SERVO, SERVO_CUTS, SPLINE_FITS, TUNNELS
from pbe.graders.bridges import overhangs, settings
from predict import bridge_predictions, commit_hash, nut_name, refuse_to_overwrite_outcomes

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "results/predictions/round2-coupons.yaml"


class PrintedCell(BaseModel):
    cell: str
    outcome: str | None


class BridgeRecord(BaseModel):
    cells: list[PrintedCell]


class Round1(BaseModel):
    """results/predictions/round1-coupons.yaml, as far as round 2 reads it."""
    A_bridges: BridgeRecord


ROUND1 = Round1.model_validate(yaml.safe_load((ROOT / "results/predictions/round1-coupons.yaml").read_text()))


def a_cells(stl="A-bridges.stl", spec=None):
    before = {printed.cell: printed.outcome for printed in ROUND1.A_bridges.cells}
    cells = bridge_predictions(stl, spec or BRIDGE_CELLS)
    return [{**cell, "round1_outcome": before[cell["cell"]]} for cell in cells]


def tunnels():
    found = sorted(overhangs(trimesh.load(OUT / "C2-tunnels.stl")), key=lambda overhang: overhang.region.centroid.y)
    out = []
    for (name, side, top, flare), overhang in zip(TUNNELS, found):
        out.append({"tunnel": name, "per_side": side, "above": top, "bed_flare": flare,
                    "prediction": "clean" if overhang.ok else "tangled or sagging",
                    "why": f"{overhang.anchored:.0%} of strands anchored at both ends, longest {overhang.longest:.1f} mm",
                    "blind": name != "1",
                    "round1": "roof failed, strands along the tunnel" if name == "1" else "void: tunnel broke through the wall (fixed)",
                    "outcome": None})
    return out


EXPECT_NUT = {  # from round 1, 0.05 mm steps between its results
    "M3": {0.1: "won't go in (round 1: barely)", 0.15: "tight", 0.2: "holds (round 1: snug)", 0.25: "holds, easier"},
    "M5": {0.0: "holds, tight (round 1)", 0.05: "holds", 0.1: "holds (round 1: easier)", 0.15: "loose (round 1: loose at +0.2)"},
    "M8": {-0.1: "won't go in", -0.05: "tight", 0.0: "holds, snaps in (round 1)", 0.05: "loose (round 1: loose at +0.1)"},
    "Q": {-0.1: "tight", -0.05: "holds", 0.0: "holds without snapping (round 1)", 0.05: "loose"},
}
EXPECT_SERVO = {0.15: "drops in, snug (round 1: 10 mm peg tight at 0.1, slid at 0.2)", 0.25: "drops in", 0.3: "drops in, rattles"}
EXPECT_SPLINE = {0.0: "won't go on", 0.1: "press on, grips", 0.2: "press on, grips", 0.3: "slips"}
EXPECT_SEAT = {0.0: "won't go in", 0.1: "press in", 0.2: "press in, light", 0.3: "slides in, loose"}
EXPECT_PEG = {-0.2: "slides into the bore", -0.1: "snug", 0.0: "tight or won't go"}


def nuts2():
    pockets = []
    for label, af, _ in NUTS:
        for column, clearance in enumerate(NUTS2[label]):
            pockets.append({"nut": nut_name(label), "label": label, "column_dots": column, "across_flats": af,
                            "clearance": clearance, "expected": EXPECT_NUT[label][clearance], "outcome": None})
    return pockets


def servos():
    return [{"servo": name, "per_side": clearance, "body_l": SERVO[name].body_l.value, "body_w": SERVO[name].body_w.value,
             "expected": EXPECT_SERVO[clearance], "screws_reach": "yes: slot centres at reading + hole diameter",
             "outcome": None, "screws_outcome": None} for name, clearance in SERVO_CUTS]


def splines_bearings():
    splines = []
    for servo in ("MG996R", "MG90S"):
        for column, over in enumerate(SPLINE_FITS):
            splines.append({"servo": servo, "column_dots": column, "bore": round(SERVO[servo].spline_od.value + over, 2),
                            "over_od": over, "expected": EXPECT_SPLINE[over], "outcome": None})
    seats = [{"column_dots": column, "seat_d": round(22.0 + over, 2), "expected": EXPECT_SEAT[over], "outcome": None}
             for column, over in enumerate(SEAT_FITS)]
    pegs = [{"column_dots": column, "peg_d": round(8.0 + under, 2), "expected": EXPECT_PEG[under], "outcome": None}
            for column, under in enumerate(PEG_DS)]
    return {"spline_bores": splines, "608_seats": seats, "8mm_pegs": pegs}


def main():
    refuse_to_overwrite_outcomes(DEST)
    doc = {
        "written": datetime.datetime.now().astimezone().isoformat(timespec="minutes"),
        "code_at": f"{commit_hash()} + this commit's coupon changes",
        "printer": "Bambu Lab X1C",
        "print_settings": {"layer_mm": 0.2, "supports": "off", "filament": "black PLA, high speed (as round 1)",
                           "walls": 4, "infill": "15%"},
        "bridge_check_on_every_coupon": "A2: 50 flagged, 40 passes; A: 2 of 9 overhangs flagged (H, 50); C2: 2 roofs, both pass; B2, D, E: no overhangs",
        "A_bridges": {"source": "bridge check (pbe/bridges.py), unchanged; repeat of round 1", "settings": settings(),
                      "cells": a_cells()},
        "A2_bridges": {"source": "bridge check, unchanged; the 40 and 50 mm pockets of A alone, the pair that contradicted the span limit in round 1",
                       "cells": a_cells("A2-bridges.stl", A2_CELLS)},
        "B2_nuts": {"source": "Claude's expectation from round 1, not a grader", "how_to_test": "press in, turn over, shake",
                    "pockets": nuts2()},
        "C2_tunnels": {"source": "bridge check on C2-tunnels.stl (C-fits without the square holes)", "tunnels": tunnels()},
        "D_servos": {"source": "Claude's expectation from round 1's square-hole fits, not a grader",
                     "how_to_test": "drop each servo into its cutout from above, then screw its tabs down", "cutouts": servos()},
        "E_splines_bearings": {"source": "Claude's expectation, not a grader. 608 seats designed to 22.0 mm (nominal), "
                               "not the 21.22 reading, which the video suggests was taken at an angle",
                               **splines_bearings()},
    }
    DEST.write_text(yaml.safe_dump(doc, sort_keys=False, width=120))
    print(f"wrote {DEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
