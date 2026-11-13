"""What a printed hole does to a bolt pushed through it by hand, from round 3's F
(results/predictions/round3-coupons.yaml): M8 and 1/4"-20 bolts through round holes on this printer.

Each recorded outcome reads one of two ways. "screws in": the bolt only goes through turned, cutting
its own thread (M8 at 8.0, 1/4"-20 at 6.35). "by hand": it goes through pushed or slides (M8 at 8.1
and 8.2, 1/4"-20 at 6.5 and 6.6). Holes Dan didn't report (8.3, 8.4, 6.8) aren't read. Whether
"screws in" is good enough is the requirement's call, not this module's.
"""
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from pbe.graders import assumed

ROOT = Path(__file__).resolve().parents[2]
TOL = 0.01  # mm: as the nut checks match round 1's steps
Fit = Literal["screws in", "by hand"]


class PrintedHole(BaseModel):
    """One hole on round 3's F, and what the bolt did in it."""
    bolt: str
    hole_d: float
    outcome: str | None  # Dan's words, or None where he didn't report it

    @property
    def fit(self) -> Fit:
        return "screws in" if self.outcome.startswith("screws in") else "by hand"


class BoltHoles(BaseModel):
    holes: list[PrintedHole]


class RoundThree(BaseModel):
    """results/predictions/round3-coupons.yaml, as far as the bolt-hole checks read it."""
    F_bolt_holes: BoltHoles


@cache
def printed_holes(bolt) -> list[tuple[float, Fit]]:
    """The reported holes for this bolt: (hole diameter, fit), tightest first."""
    record = RoundThree.model_validate(yaml.safe_load((ROOT / "results/predictions/round3-coupons.yaml").read_text()))
    return sorted((hole.hole_d, hole.fit) for hole in record.F_bolt_holes.holes if hole.bolt == bolt and hole.outcome)


def fit(bolt, hole_d) -> Fit | None:
    """How this bolt goes through a hole this wide: a printed step's reading, the reading of two steps that
    agree on either side of it, "by hand" looser than the loosest step, or None: between steps that
    disagree, or tighter than the tightest (which may not take the bolt at all; the caller checks that)."""
    rows = printed_holes(bolt)
    for printed, reading in rows:
        if abs(hole_d - printed) <= TOL:
            return reading
    below = [reading for printed, reading in rows if printed < hole_d]
    above = [reading for printed, reading in rows if printed > hole_d]
    if below and above:
        return below[-1] if below[-1] == above[0] else None
    if below:
        return "by hand" if below[-1] == "by hand" else None
    return None


def reading(bolt, hole_d) -> tuple[Fit | None, float | None]:
    """(how the bolt goes through, the printed hole it was assumed from or None if a print or the trend settles it).
    Where `fit` can't say, the nearest printed hole within the assumption tolerance decides (assumed.py)."""
    how = fit(bolt, hole_d)
    if how is not None:
        return how, None
    close = assumed.nearest(hole_d, printed_holes(bolt))
    return (close[1], close[0]) if close else (None, None)
