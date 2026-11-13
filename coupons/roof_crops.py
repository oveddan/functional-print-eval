"""Round 3b: the roofs the bridge check fails, cut out of the models' own Estoa designs, to print as they are.

    uv run python coupons/roof_crops.py          # writes coupons/out/P-*.stl and prints each crop

The eight saved Estoa trials whose only failure is the bridge check (`bridges`). For each, the worst
roof it can't bridge is cut out of the part as a block: the roof's outline plus a margin, from a few
layers below the roof (so the walls it would bridge between are there) to a few above it, then set
down on the bed. Printed as cut, z = 0 on the bed, no supports, each block shows whether that roof
really tangles: the most direct check of the bridge check there is.

A roof wider than the crop's size limit is left out and listed: there the question is the span, not the
shape, so plain bridges 60, 80 and 100 mm long (Q-span-*: a deck between two pillars) find how far a roof really bridges.
The catalog's 50 mm is only the longest roof printed so far; two trials fail on spans of 94 and 208 mm.

    uv run python coupons/roof_crops.py --predict   # also writes results/predictions/round3b-roofs.yaml
"""
import datetime
import sys
from pathlib import Path

import cadquery as cq
import trimesh
import yaml
from pydantic import BaseModel

from coupons import OUT, at, label
from pbe.graders.bridges import overhangs, settings
from predict import commit_hash, refuse_to_overwrite_outcomes

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs"
MARGIN, BELOW, ABOVE, MAX_SIDE = 6.0, 4.0, 3.0, 80.0
SPANS, SPAN_PILLAR, SPAN_DECK_W, SPAN_DEPTH, SPAN_ROOF = [60, 80, 100], 8, 10, 3, 1.2
DEST = ROOT / "results/predictions/round3b-roofs.yaml"


class Trial(BaseModel):
    """A saved trial and the part its failing roof is in."""
    folder: str
    part: str

    @property
    def name(self):
        model, trial = self.folder.split("/")[-2:]
        return f"P-{model.split('__')[1]}-{self.folder.split('/')[2]}-{trial}"


TRIALS = [
    Trial(folder="test-first/estoa-light/can_test/openai__gpt-6.1-sol/t2", part="rear_cup"),
    Trial(folder="test-first/estoa-light/can_test/google__gemini-4-argon/t3", part="box"),
    Trial(folder="test-first/estoa-light/can_test/google__gemini-4-argon/t1", part="box"),
    Trial(folder="test-first/estoa-light/can_test/anthropic__claude-opus-5.5/t3", part="shell"),
    Trial(folder="test-first/estoa-light/can_test/anthropic__claude-sonnet-5.5/t2", part="box"),
    Trial(folder="pilot-estoa/estoa-light/can_ask/google__gemini-4-argon/t5", part="wall_box"),
    Trial(folder="pilot-estoa/estoa-light/can_ask/google__gemini-4-argon/t2", part="wall_box"),
    Trial(folder="pilot-estoa/estoa-light/can_ask/deepseek__deepseek-v4-pro-0813/t1", part="box"),
]


class Crop(BaseModel):
    trial: str
    part: str
    roof_z: float
    roof_area_mm2: float
    anchored: float
    longest: float
    box: list[float] | None  # xmin, ymin, zmin, xmax, ymax, zmax in the part's frame
    why_left_out: str | None = None


def worst_failing(mesh):
    failing = [overhang for overhang in overhangs(mesh) if not overhang.ok and not overhang.narrow]
    return max(failing, key=lambda overhang: overhang.region.area) if failing else None


def cut_to_box(mesh, box):
    """The part inside the box. A clean intersection where the mesh is a closed volume; otherwise six capped
    plane cuts, since some saved meshes aren't closed (the slicer repairs what's left)."""
    if mesh.is_volume:
        cutter = trimesh.creation.box(bounds=[box[:3], box[3:]])
        return trimesh.boolean.intersection([mesh, cutter], engine="manifold")
    block = mesh
    for axis in range(3):
        normal = [0.0, 0.0, 0.0]
        normal[axis] = 1.0
        block = block.slice_plane([box[0], box[1], box[2]], normal, cap=True)
        normal[axis] = -1.0
        block = block.slice_plane([box[3], box[4], box[5]], normal, cap=True)
    return block


def crop_for(trial: Trial):
    mesh = trimesh.load(RUNS / trial.folder / "parts" / f"{trial.part}.stl")
    roof = worst_failing(mesh)
    if roof is None:
        return Crop(trial=trial.folder, part=trial.part, roof_z=0, roof_area_mm2=0, anchored=1, longest=0, box=None,
                    why_left_out="no failing roof found on this part"), None
    x0, y0, x1, y1 = roof.region.bounds
    box = [x0 - MARGIN, y0 - MARGIN, max(0.0, roof.z - BELOW), x1 + MARGIN, y1 + MARGIN, roof.z + ABOVE]
    found = Crop(trial=trial.folder, part=trial.part, roof_z=roof.z, roof_area_mm2=round(roof.region.area),
                 anchored=round(roof.anchored, 2), longest=round(roof.longest, 1), box=[round(v, 1) for v in box])
    if max(box[3] - box[0], box[4] - box[1]) > MAX_SIDE:
        found.why_left_out = f"the roof is {x1 - x0:.0f} x {y1 - y0:.0f} mm: a span question, for the long-span roofs"
        return found, None
    block = cut_to_box(mesh, box)
    block.apply_translation([-(box[0] + box[3]) / 2, -(box[1] + box[4]) / 2, -block.bounds[0][2]])
    return found, block


def span_block(span):
    """A plain bridge `span` long: a 10 mm deck, 1.2 mm thick, between two pillars, open at the sides, so the
    only way to print the deck is strands running the whole span."""
    pillar = cq.Workplane("XY").box(SPAN_PILLAR, SPAN_DECK_W, SPAN_DEPTH + SPAN_ROOF, centered=(True, True, False))
    block = pillar.translate((-(span + SPAN_PILLAR) / 2, 0, 0)).union(pillar.translate(((span + SPAN_PILLAR) / 2, 0, 0)))
    deck = cq.Workplane("XY").box(span + 2 * SPAN_PILLAR, SPAN_DECK_W, SPAN_ROOF, centered=(True, True, False))
    block = block.union(deck.translate((0, 0, SPAN_DEPTH)))
    return label(block, str(span), (span + SPAN_PILLAR) / 2, 0, SPAN_DEPTH + SPAN_ROOF, size=4)


def span_rows():
    expected = {60: "clean, or a slight sag", 80: "sags", 100: "sags or tangles"}
    return [{"span_mm": span, "check": "tangled or sagging (longer than any roof printed, 50 mm)",
             "expected": expected[span], "outcome": None, "notes": None} for span in SPANS]


def write_predictions(crops):
    refuse_to_overwrite_outcomes(DEST)
    doc = {
        "written": datetime.datetime.now().astimezone().isoformat(timespec="minutes"),
        "code_at": f"{commit_hash()} + coupons/roof_crops.py as committed with these predictions",
        "printer": "Bambu Lab X1C",
        "print_settings": {"layer_mm": 0.2, "supports": "off", "filament": "the same PLA as rounds 1 to 3",
                           "walls": 4, "infill": "15%", "preset": "0.20mm Standard @BBL X1C"},
        "roof_crops": {"source": "bridge check (pbe/graders/bridges.py), unchanged: every one of these fails it",
                       "settings": settings(),
                       "how_to_test": "look at each roof from underneath: clean, sagging, or loose strands",
                       "crops": [{**crop.model_dump(), "check": "tangled or sagging", "outcome": None, "notes": None}
                                 for crop in crops]},
        "Q_spans": {"source": "bridge check fails every roof over 50 mm; Claude's expectation beside it",
                    "how_to_test": "look at each roof from underneath", "roofs": span_rows()},
    }
    DEST.write_text(yaml.safe_dump(doc, sort_keys=False, width=120))
    print(f"wrote {DEST.relative_to(ROOT)}")


def main():
    OUT.mkdir(exist_ok=True)
    crops = []
    for span in SPANS:
        shape = span_block(span)
        cq.exporters.export(shape, str(OUT / f"Q-span-{span}.stl"), tolerance=0.01, angularTolerance=0.1)
    for trial in TRIALS:
        found, block = crop_for(trial)
        crops.append(found)
        if block is not None:
            block.export(OUT / f"{trial.name}.stl")
        size = "" if block is None else " x ".join(f"{v:.0f}" for v in block.extents)
        print(f"{trial.name:42} roof at z {found.roof_z:5.1f}, {found.roof_area_mm2:6.0f} mm², "
              f"{found.anchored:.0%} anchored, longest {found.longest} | {size or found.why_left_out}")
    if "--predict" in sys.argv:
        write_predictions(crops)


if __name__ == "__main__":
    main()
