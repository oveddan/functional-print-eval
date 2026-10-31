"""Write the predictions for round 2 before it's printed.

    uv run python coupons/predict2.py

A and C's tunnel roofs: the bridge check, unchanged since round 1. A repeats round 1,
so its predictions are the same; C's tunnel 1 already failed once, so that one isn't
blind. B2, D and E: Claude's expectations from round 1's measured fits, not a grader.
D's screw slots also test Claude's reading of the tab-hole pitch from Dan's video
(inner edges, so centres = reading + hole diameter).
"""
import datetime
import subprocess
from pathlib import Path

import trimesh
import yaml

from coupons import A2_CELLS, NUTS, NUTS2, OUT, PEG_DS, SEAT_FITS, SERVO, SERVO_CUTS, SPLINE_FITS, TUNNELS, val
from pbe.bridges import overhangs, settings
from predict import bridge_predictions

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "results/predictions/round2-coupons.yaml"
ROUND1 = yaml.safe_load((ROOT / "results/predictions/round1-coupons.yaml").read_text())


def a_cells(stl="A-bridges.stl", spec=None):
    before = {c["cell"]: c["outcome"] for c in ROUND1["A_bridges"]["cells"]}
    cells = bridge_predictions(stl, spec) if spec else bridge_predictions()
    return [{**c, "round1_outcome": before[c["cell"]]} for c in cells]


def tunnels():
    found = sorted(overhangs(trimesh.load(OUT / "C2-tunnels.stl")), key=lambda o: o.region.centroid.y)
    out = []
    for (name, side, top, flare), o in zip(TUNNELS, found):
        out.append({"tunnel": name, "per_side": side, "above": top, "bed_flare": flare,
                    "prediction": "clean" if o.ok else "tangled or sagging",
                    "why": f"{o.anchored:.0%} of strands anchored at both ends, longest {o.longest:.1f} mm",
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


def nuts2():
    return [{"nut": "1/4-20" if n == "Q" else n, "label": n, "column_dots": i, "across_flats": af, "clearance": c,
             "expected": EXPECT_NUT[n][c], "outcome": None}
            for n, af, _ in NUTS for i, c in enumerate(NUTS2[n])]


def servos():
    cuts = [{"servo": n, "per_side": c, "body_l": val(SERVO[n]["body_l"]), "body_w": val(SERVO[n]["body_w"]),
             "expected": {0.15: "drops in, snug (round 1: 10 mm peg tight at 0.1, slid at 0.2)",
                          0.25: "drops in", 0.3: "drops in, rattles"}[c],
             "screws_reach": "yes: slot centres at reading + hole diameter",
             "outcome": None, "screws_outcome": None} for n, c in SERVO_CUTS]
    return cuts


def splines_bearings():
    spl = [{"servo": s, "column_dots": i, "bore": round(val(SERVO[s]["spline_od"]) + f, 2), "over_od": f,
            "expected": {0.0: "won't go on", 0.1: "press on, grips", 0.2: "press on, grips", 0.3: "slips"}[f],
            "outcome": None} for s in ("MG996R", "MG90S") for i, f in enumerate(SPLINE_FITS)]
    seats = [{"column_dots": i, "seat_d": round(22.0 + f, 2), "expected": {0.0: "won't go in", 0.1: "press in",
              0.2: "press in, light", 0.3: "slides in, loose"}[f], "outcome": None} for i, f in enumerate(SEAT_FITS)]
    pegs = [{"column_dots": i, "peg_d": round(8.0 + d, 2), "expected": {-0.2: "slides into the bore", -0.1: "snug",
             0.0: "tight or won't go"}[d], "outcome": None} for i, d in enumerate(PEG_DS)]
    return {"spline_bores": spl, "608_seats": seats, "8mm_pegs": pegs}


def main():
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    doc = {
        "written": datetime.datetime.now().astimezone().isoformat(timespec="minutes"),
        "code_at": f"{commit} + this commit's coupon changes",
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
