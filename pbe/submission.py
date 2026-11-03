"""The submission format: what a model hands in for a task.

Everything a grader needs is declared here, so the graders can be code:
- params: every hardware and real-world dimension as a named input, with its source.
  Part code may only use these, which is what lets the metamorphic check vary them.
- parts: CadQuery code per part, with how it's printed and how it's used.
- hardware, joints: what fastens what, along which axis, seated in which feature.
- criteria: the model's own acceptance criteria, typed, each with how it's checked.
- manual: the steps a person follows, naming parts, hardware and tools.
- questions: what the model asked before designing.
"""
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from pbe import catalog

Source = Literal["measured", "datasheet", "catalog", "asked", "guessed", "unknown", "design"]


class Param(BaseModel):
    value: int | float | None  # an int stays an int: part code uses counts in range()
    unit: Literal["mm", "deg", "count"] = "mm"
    kind: Literal["hardware", "world", "design"] = Field(description=(
        "What the dimension belongs to: hardware (a bought part, such as a bolt or nut), world (something "
        "the person has, such as their desk or phone) or design (a choice you make)"))
    source: Source = Field(description=(
        "Where the value came from: measured (the person measured it for you), datasheet, catalog (the "
        "hardware list), asked (the person told you), guessed, unknown, or design (your own choice)"))
    note: str = ""

    @model_validator(mode="after")
    def whole_counts_are_ints(self):
        # a saved submission can carry 8 as 8.0
        if self.unit == "count" and isinstance(self.value, float) and self.value.is_integer():
            self.value = int(self.value)
        return self


class Part(BaseModel):
    id: str = Field(description="Letters, digits, - and _ only; unique among the parts")
    role: Literal["final", "coupon"] = Field(description=(
        "final: part of the finished thing. coupon: a small test print, to check something before printing the full part"))
    material: str
    code: str = Field(description="Python defining build(p) -> cadquery Workplane or Shape; p.<name> gives each param's value")
    print_orientation: str = Field(description="Which face goes on the bed, in the part's own frame (z = 0 is the bed)")
    use_orientation: str


class HardwareItem(BaseModel):
    id: str
    ref: str = Field(description='Catalog reference, e.g. "ISO 4762 M5x30", "ISO 4032 M5", "salvaged:webcam-mount-bolt"')
    qty: int = 1


class Seat(BaseModel):
    part: str = Field(description="The id of a part in `parts`")
    feature: str
    role: Literal["head_seat", "clearance", "thread", "nut_pocket", "insert", "washer"]


class Joint(BaseModel):
    id: str
    fastener: str = Field(description="The id of an item in `hardware` (not its catalog reference)")
    axis_origin: tuple[float, float, float] = Field(description="Where the fastener's head sits, in the frame of the first part in seats")
    axis_dir: tuple[float, float, float] = Field(description="Direction the fastener points, head to tip")
    seats: list[Seat]
    nut: str | None = Field(None, description="The id of an item in `hardware`")
    external: str | None = Field(None, description="Anything outside the design it threads into, e.g. a camera's 1/4-20 socket")


class Check(BaseModel):
    method: Literal["coupon", "template", "measure", "none"]
    ref: str | None = None
    description: str = ""


class Criterion(BaseModel):
    id: str
    part: str = Field(description="The id of a part in `parts`")
    feature: str
    relation: Literal["contains", "clears", "engages", "seats", "supports", "faces"]
    hardware: str | None = Field(None, description="The id of an item in `hardware` (not its catalog reference)")
    clearance_mm: float | None = None
    params: list[str] = Field(default_factory=list, description="The params this criterion depends on")
    check: Check


class Step(BaseModel):
    n: str
    text: str
    parts: list[str] = Field(default_factory=list, description="Ids of parts in `parts`")
    hardware: list[str] = Field(default_factory=list, description="Ids of items in `hardware` (not their catalog references)")
    tool: str | None = None


class Question(BaseModel):
    text: str
    answer: str | None = None


class Submission(BaseModel):
    task: str
    note: str = ""
    questions: list[Question] = Field(default_factory=list)
    params: dict[str, Param]
    parts: list[Part]
    hardware: list[HardwareItem] = Field(default_factory=list)
    joints: list[Joint] = Field(default_factory=list)
    criteria: list[Criterion] = Field(default_factory=list)
    manual: list[Step] = Field(default_factory=list)

    @model_validator(mode="after")
    def references_resolve(self):
        part_ids = {p.id for p in self.parts}
        hw_ids = {h.id for h in self.hardware}
        errors = []
        # a part id becomes a file name when the part is built
        errors += [f"part id {p.id!r}: use only letters, digits, - and _" for p in self.parts if not re.fullmatch(r"[\w-]+", p.id, re.ASCII)]
        if len(part_ids) != len(self.parts):
            errors.append("two parts have the same id")
        for h in self.hardware:
            try:
                catalog.resolve(h.ref)
            except KeyError as e:
                errors.append(f"hardware {h.id}: {e}")
        for j in self.joints:
            if j.fastener not in hw_ids:
                errors.append(f"joint {j.id}: unknown fastener {j.fastener}")
            if j.nut and j.nut not in hw_ids:
                errors.append(f"joint {j.id}: unknown nut {j.nut}")
            errors += [f"joint {j.id}: unknown part {s.part}" for s in j.seats if s.part not in part_ids]
        for c in self.criteria:
            if c.part not in part_ids:
                errors.append(f"criterion {c.id}: unknown part {c.part}")
            if c.hardware and c.hardware not in hw_ids:
                errors.append(f"criterion {c.id}: unknown hardware {c.hardware}")
            errors += [f"criterion {c.id}: unknown param {p}" for p in c.params if p not in self.params]
        for s in self.manual:
            errors += [f"step {s.n}: unknown part {p}" for p in s.parts if p not in part_ids]
            errors += [f"step {s.n}: unknown hardware {h}" for h in s.hardware if h not in hw_ids]
        if errors:
            raise ValueError("; ".join(errors) + f". Part ids: {sorted(part_ids)}; hardware ids: {sorted(hw_ids)}")
        return self


def parse(text) -> Submission:
    return Submission.model_validate(yaml.safe_load(text))


def load(path) -> Submission:
    return parse(Path(path).read_text())
