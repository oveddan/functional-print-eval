"""Write the predictions for tonight's coupons before they're printed.

    uv run python coupons/predict.py

Coupon A's predictions come from the bridge check, run blind on the coupon's
mesh. B's and C's are expectations from earlier prints (the tripod's nut pockets,
Estoa's leg pocket), not from a grader: those coupons measure the printer.
Outcome fields are left empty for Dan to fill in after printing.
"""
import datetime
import subprocess
from pathlib import Path

import trimesh
import yaml

from coupons import BRIDGE_CELLS, A_WALL, CLEARANCES, NUTS, OUT, SQUARE_FITS, TUNNELS
from pbe.bridges import overhangs, settings

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "results/predictions/round1-coupons.yaml"


def bridge_predictions(stl="A-bridges.stl", spec=BRIDGE_CELLS):
    found = overhangs(trimesh.load(OUT / stl))
    x, cells = A_WALL, []
    for name, size, hole in spec:
        lo, hi = x, x + size
        x += size + A_WALL
        mine = [o for o in found if lo <= o.region.centroid.x <= hi]
        ok = all(o.ok for o in mine)
        worst = min(mine, key=lambda o: (o.ok, o.anchored)) if mine else None
        cells.append({
            "cell": name,
            "pocket_mm": size,
            "hole": hole or "none",
            "prediction": "clean" if ok else "tangled or sagging",
            "why": (f"{len(mine)} overhang(s); worst: {worst.anchored:.0%} of strands anchored at both ends, "
                    f"longest strand {worst.longest:.1f} mm (limit {settings()['max_span_mm']} mm)") if worst else "no overhang found",
            "outcome": None,  # clean | sagging | tangled | failed
            "notes": None,
        })
    return cells


def nut_predictions():
    # from catalog/printer.yaml observed_fits (tripod build; filament not recorded)
    prior = {
        "M5": {0.0: "holds", 0.1: "holds", 0.2: "unknown (held at +0.15, fell out at +0.30)", 0.3: "falls out"},
        "M8": {0.0: "holds", 0.1: "no data", 0.2: "no data", 0.3: "falls out"},
        "Q": {0.0: "falls out", 0.1: "falls out", 0.2: "falls out", 0.3: "falls out"},
        "M3": {c: "no data" for c in CLEARANCES},
    }
    return [{"nut": "1/4-20" if n == "Q" else n, "label": n, "across_flats": af, "clearance": c,
             "expected": prior[n][c], "outcome": None}  # won't go in | holds | falls out
            for n, af, _ in NUTS for c in CLEARANCES]


def fit_predictions():
    square = [{"hole": f"{i + 1} dot(s)", "per_side": c, "expected": "no data (first measurement)",
               "outcome": None} for i, c in enumerate(SQUARE_FITS)]  # won't go in | tight | slides | loose
    tunnel_prior = {"1": "won't seat without force (Estoa's first leg pocket, 2026-10-02)",
                    "2": "slides in (Estoa's fixed leg pocket)"}
    tunnels = [{"tunnel": n, "per_side": s, "above": t, "bed_flare": f, "expected": tunnel_prior[n],
                "outcome": None} for n, s, t, f in TUNNELS]
    return {"square_holes_for_10mm_peg": square, "tunnels_for_10x6_bar": tunnels}


def main():
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    doc = {
        "written": datetime.datetime.now().astimezone().isoformat(timespec="minutes"),
        "code_at": commit,
        "printer": "Bambu Lab X1C",
        "print_settings": {"layer_mm": 0.2, "supports": "off", "filament": None, "nozzle_c": None, "walls": None, "infill": None},
        "A_bridges": {"source": "bridge check (pbe/bridges.py), run blind on coupons/out/A-bridges.stl",
                      "settings": settings(), "cells": bridge_predictions()},
        "B_nuts": {"source": "earlier prints, not a grader", "how_to_test": "press the nut in by hand, turn the coupon over and shake",
                   "pockets": nut_predictions()},
        "C_fits": {"source": "earlier prints, not a grader", **fit_predictions()},
    }
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(yaml.safe_dump(doc, sort_keys=False, width=120))
    for c in doc["A_bridges"]["cells"]:
        print(f"A {c['cell']:3} {c['prediction']:20} {c['why']}")
    print(f"wrote {DEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
