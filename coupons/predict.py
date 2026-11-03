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

from coupons import BRIDGE_CELLS, CLEARANCES, NUTS, OUT, SQUARE_FITS, TUNNELS, cell_spans
from pbe.graders.bridges import overhangs, settings
from pbe.parts.printer import printer

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "results/predictions/round1-coupons.yaml"


def commit_hash():
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _has_outcomes(node):
    """Is any field named ...outcome filled in?"""
    if isinstance(node, dict):
        return any((key.endswith("outcome") and value is not None) or _has_outcomes(value) for key, value in node.items())
    if isinstance(node, list):
        return any(_has_outcomes(item) for item in node)
    return False


def refuse_to_overwrite_outcomes(dest):
    """Stop if `dest` already holds printed outcomes: the nut checks grade from them."""
    if dest.exists() and _has_outcomes(yaml.safe_load(dest.read_text())):
        raise SystemExit(f"{dest} already has printed outcomes; write the predictions somewhere else")


def _why(in_cell):
    """The overhang that comes closest to failing in a cell, in words."""
    if not in_cell:
        return "no overhang found"
    worst = min(in_cell, key=lambda overhang: (overhang.ok, overhang.anchored))
    return (f"{len(in_cell)} overhang(s); worst: {worst.anchored:.0%} of strands anchored at both ends, "
            f"longest strand {worst.longest:.1f} mm (limit {printer().bridging.max_span_mm} mm)")


def bridge_predictions(stl="A-bridges.stl", spec=BRIDGE_CELLS):
    found = overhangs(trimesh.load(OUT / stl))
    spans, _ = cell_spans(spec)
    cells = []
    for name, size, hole, start, end in spans:
        in_cell = [overhang for overhang in found if start <= overhang.region.centroid.x <= end]
        cells.append({
            "cell": name,
            "pocket_mm": size,
            "hole": hole or "none",
            "prediction": "clean" if all(overhang.ok for overhang in in_cell) else "tangled or sagging",
            "why": _why(in_cell),
            "outcome": None,  # clean | sagging | tangled | failed
            "notes": None,
        })
    return cells


# from catalog/printer.yaml observed_fits (tripod build; filament not recorded)
NUT_PRIOR = {
    "M5": {0.0: "holds", 0.1: "holds", 0.2: "unknown (held at +0.15, fell out at +0.30)", 0.3: "falls out"},
    "M8": {0.0: "holds", 0.1: "no data", 0.2: "no data", 0.3: "falls out"},
    "Q": {0.0: "falls out", 0.1: "falls out", 0.2: "falls out", 0.3: "falls out"},
    "M3": {clearance: "no data" for clearance in CLEARANCES},
}
TUNNEL_PRIOR = {"1": "won't seat without force (Estoa's first leg pocket, 2026-10-02)",
                "2": "slides in (Estoa's fixed leg pocket)"}


def nut_name(label):
    return "1/4-20" if label == "Q" else label


def nut_predictions():
    pockets = []
    for label, af, _ in NUTS:
        for clearance in CLEARANCES:
            pockets.append({"nut": nut_name(label), "label": label, "across_flats": af, "clearance": clearance,
                            "expected": NUT_PRIOR[label][clearance], "outcome": None})  # won't go in | holds | falls out
    return pockets


def fit_predictions():
    square = [{"hole": f"{i + 1} dot(s)", "per_side": per_side, "expected": "no data (first measurement)",
               "outcome": None} for i, per_side in enumerate(SQUARE_FITS)]  # won't go in | tight | slides | loose
    tunnels = [{"tunnel": name, "per_side": side, "above": top, "bed_flare": flare, "expected": TUNNEL_PRIOR[name],
                "outcome": None} for name, side, top, flare in TUNNELS]
    return {"square_holes_for_10mm_peg": square, "tunnels_for_10x6_bar": tunnels}


def main():
    refuse_to_overwrite_outcomes(DEST)
    doc = {
        "written": datetime.datetime.now().astimezone().isoformat(timespec="minutes"),
        "code_at": commit_hash(),
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
    for cell in doc["A_bridges"]["cells"]:
        print(f"A {cell['cell']:3} {cell['prediction']:20} {cell['why']}")
    print(f"wrote {DEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
