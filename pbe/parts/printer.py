"""The printer every task assumes, read from catalog/printer.yaml through a typed model.

Numbers stay as written there, an int as an int, because some go into the prompt: "50 mm",
not "50.0 mm".
"""
from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]

Number = int | float


class EvalSetup(BaseModel):
    """What every task tells the model."""
    nozzle_mm: Number
    filament: str


class Bridging(BaseModel):
    """The bridge check's settings. See catalog/printer.yaml for where each comes from."""
    max_span_mm: Number
    small_overhang_mm: Number
    narrowest_tangled_mm: Number
    anchor_tol_mm: Number
    min_anchored: Number


class Printer(BaseModel):
    """Only what the eval reads. The file also keeps notes on filaments and earlier fits."""
    printer: str
    layer_mm: Number
    eval_setup: EvalSetup
    bridging: Bridging
    bed_mm: tuple[Number, Number, Number]


@cache
def printer() -> Printer:
    return Printer.model_validate(yaml.safe_load((ROOT / "catalog/printer.yaml").read_text()))
