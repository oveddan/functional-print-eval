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

from pbe.parts import catalog

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


# Only tasks with a format.yaml that asks for it get `assembly` in their tool schema
# (pbe/runner/agent.py); every other task's schema, prompt and saved files stay as they were.
Vector = tuple[float, float, float]
ASSEMBLY_FRAME = (
    "The finished piece as it's used, in mm: z = 0 is the plane it rests against (the wall, the desk), and +z points away "
    "from it; +y points up, against gravity; +x completes a right-handed frame (to the right as you face the piece)")
PERPENDICULAR = 0.01  # largest |cos| between x_axis and z_axis that still counts as square


class Placement(BaseModel):
    """Where something's own frame goes in the finished piece."""
    origin: Vector = Field(description="Where its own (0, 0, 0) goes")
    x_axis: Vector = Field(description="Where its own +x points")
    z_axis: Vector = Field(description="Where its own +z points; at right angles to x_axis")

    @model_validator(mode="after")
    def axes_are_square(self):
        x_length, z_length = (sum(value * value for value in axis) ** 0.5 for axis in (self.x_axis, self.z_axis))
        if x_length < 1e-9 or z_length < 1e-9:
            raise ValueError("x_axis and z_axis can't be zero")
        cos = sum(along_x * along_z for along_x, along_z in zip(self.x_axis, self.z_axis)) / (x_length * z_length)
        if abs(cos) > PERPENDICULAR:
            raise ValueError(f"x_axis {self.x_axis} and z_axis {self.z_axis} aren't at right angles")
        return self


class PartPlacement(Placement):
    part: str = Field(description="The id of a final part in `parts`; its own frame is the one its code builds it in")


class ItemPlacement(Placement):
    item: str = Field(description="The id of an item in `hardware` whose catalog entry defines its own frame")


class ScrewPlacement(BaseModel):
    item: str = Field(description="The id of a screw in `hardware`; one entry per screw, as many as its qty")
    head: Vector = Field(description="The centre of the underside of its head, in the finished piece's frame")
    direction: Vector = Field(description="The way it points, head to tip")


class Assembly(BaseModel):
    """Where everything goes in the finished piece."""
    parts: list[PartPlacement] = Field(description="Every final part, once")
    items: list[ItemPlacement] = Field(description="Every item in `hardware` whose catalog entry defines a frame, once")
    screws: list[ScrewPlacement] = Field(default_factory=list, description="Every screw in `hardware`, one entry per screw")


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
    assembly: Assembly | None = Field(None, description=ASSEMBLY_FRAME)

    @model_validator(mode="after")
    def references_resolve(self):
        part_ids = {part.id for part in self.parts}
        hardware_ids = {item.id for item in self.hardware}
        errors = self._part_id_errors(part_ids) + self._hardware_errors()
        errors += self._joint_errors(part_ids, hardware_ids) + self._criterion_errors(part_ids, hardware_ids)
        errors += self._manual_errors(part_ids, hardware_ids)
        if self.assembly is not None and not errors:
            errors += self._assembly_errors()
        if errors:
            raise ValueError("; ".join(errors) + f". Part ids: {sorted(part_ids)}; hardware ids: {sorted(hardware_ids)}")
        return self

    def dump(self) -> dict:
        """As saved: a submission without an assembly saves exactly as before the field existed."""
        return self.model_dump(exclude={"assembly"} if self.assembly is None else None)

    def resolved(self, item: "HardwareItem") -> dict:
        return catalog.resolve(item.ref, task=self.task)

    def _assembly_errors(self):
        placed_parts = [placement.part for placement in self.assembly.parts]
        finals = [part.id for part in self.parts if part.role == "final"]
        errors = [f"assembly: {part} isn't a final part" for part in placed_parts if part not in finals]
        errors += [f"assembly: place final part {part} exactly once" for part in finals if placed_parts.count(part) != 1]
        by_id = {item.id: item for item in self.hardware}
        framed = [item.id for item in self.hardware if "frame" in self.resolved(item)]
        placed_items = [placement.item for placement in self.assembly.items]
        errors += [f"assembly: {item} has no frame to place (only items whose catalog entry defines one)"
                   for item in placed_items if item not in framed]
        errors += [f"assembly: place {item} exactly {by_id[item].qty} time(s)" for item in framed
                   if placed_items.count(item) != by_id[item].qty]
        screws = [item.id for item in self.hardware if self.resolved(item)["kind"] == "screw"]
        placed_screws = [placement.item for placement in self.assembly.screws]
        errors += [f"assembly: {item} isn't a screw in hardware" for item in placed_screws if item not in screws]
        errors += [f"assembly: give each of the {by_id[item].qty} {item} screw(s) a place" for item in screws
                   if placed_screws.count(item) != by_id[item].qty]
        errors += [f"assembly: screw {placement.item} has no direction" for placement in self.assembly.screws
                   if not any(placement.direction)]
        return errors

    def _part_id_errors(self, part_ids):
        # a part id becomes a file name when the part is built
        errors = [f"part id {part.id!r}: use only letters, digits, - and _" for part in self.parts
                  if not re.fullmatch(r"[\w-]+", part.id, re.ASCII)]
        if len(part_ids) != len(self.parts):
            errors.append("two parts have the same id")
        return errors

    def _hardware_errors(self):
        errors = []
        for item in self.hardware:
            try:
                self.resolved(item)
            except KeyError as e:
                errors.append(f"hardware {item.id}: {e}")
        return errors

    def _joint_errors(self, part_ids, hardware_ids):
        errors = []
        for joint in self.joints:
            if joint.fastener not in hardware_ids:
                errors.append(f"joint {joint.id}: unknown fastener {joint.fastener}")
            if joint.nut and joint.nut not in hardware_ids:
                errors.append(f"joint {joint.id}: unknown nut {joint.nut}")
            errors += [f"joint {joint.id}: unknown part {seat.part}" for seat in joint.seats if seat.part not in part_ids]
        return errors

    def _criterion_errors(self, part_ids, hardware_ids):
        errors = []
        for criterion in self.criteria:
            if criterion.part not in part_ids:
                errors.append(f"criterion {criterion.id}: unknown part {criterion.part}")
            if criterion.hardware and criterion.hardware not in hardware_ids:
                errors.append(f"criterion {criterion.id}: unknown hardware {criterion.hardware}")
            errors += [f"criterion {criterion.id}: unknown param {name}" for name in criterion.params if name not in self.params]
        return errors

    def _manual_errors(self, part_ids, hardware_ids):
        errors = []
        for step in self.manual:
            errors += [f"step {step.n}: unknown part {part}" for part in step.parts if part not in part_ids]
            errors += [f"step {step.n}: unknown hardware {item}" for item in step.hardware if item not in hardware_ids]
        return errors


def parse(text) -> Submission:
    return Submission.model_validate(yaml.safe_load(text))


def load(path) -> Submission:
    return parse(Path(path).read_text())
