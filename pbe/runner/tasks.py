"""Load a task: the person's request, the hidden facts, the typed requirements and
the reference solution."""
from dataclasses import dataclass, field
from pathlib import Path
from string import Template

import yaml
from pydantic import BaseModel, ConfigDict, Field

from pbe.parts import catalog

ROOT = Path(__file__).resolve().parents[2]


class Assumption(BaseModel):
    """What a requirement assumes where no record decides it. It never changes the verdict the records give:
    `python -m pbe.assumptions` grades only the trials' undecided checks with it, and reports them apart."""
    model_config = ConfigDict(extra="forbid")
    text: str  # the assumption, in a sentence
    source: str  # why this value: the record, standard or reasoning it rests on
    args: dict  # grader arguments that replace `args` under the assumption


class Requirement(BaseModel):
    """One entry of a task's requirements.yaml: what's checked, and which grader checks it."""
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str
    grader: str  # a name in requirements.GRADERS
    args: dict | None = None  # passed to the grader
    failure_class: str = Field("", alias="class")
    assume: Assumption | None = None


class OwnPart(BaseModel):
    """One of the person's own parts, listed for one task (format.yaml). What's unmeasured stays null:
    the model has to ask for it."""
    model_config = ConfigDict(extra="allow")
    id: str
    kind: str
    description: str
    frame: str | None = None  # how its own frame sits on it, for a design to place it in `assembly`


class TaskFormat(BaseModel):
    """What one task adds to the submission format and the prompt. A task without format.yaml gets
    exactly the base format, prompt and tools."""
    model_config = ConfigDict(extra="forbid")
    assembly: bool = False  # the design says where every part and framed item goes in the finished piece
    own_hardware: list[OwnPart] = []


@dataclass
class Task:
    id: str
    request: str
    hidden_facts: dict
    requirements: list[Requirement]
    reference: str | None  # the reference solution, as YAML text
    format: TaskFormat = field(default_factory=TaskFormat)


def _variants(family):
    """Each variant of a task family, by name, with the $values it fills the templates with."""
    return yaml.safe_load((ROOT / "tasks" / family / "variants.yaml").read_text())


def variant_values(family, variant):
    return _variants(family)[variant]


def _request(brief):
    """The person's words: the brief's first blockquote. The rest of brief.md is notes, and a
    later quote in the notes must not leak into the prompt."""
    lines = brief.splitlines()
    start = next((number for number, line in enumerate(lines) if line.startswith(">")), len(lines))
    quote = []
    for line in lines[start:]:
        if not line.startswith(">"):
            break
        quote.append(line[1:].strip())
    return "\n".join(quote).strip()


def load(task_id) -> Task:
    """A task folder, or one variant of a task family: "family/variant". A family is a
    task folder whose files are templates, with variants.yaml giving each variant's $values
    (the parametric families in PLAN), so one design makes many tasks."""
    family, _, variant = task_id.partition("/")
    folder = ROOT / "tasks" / family
    if (folder / "variants.yaml").exists() and not variant:
        first_variant = next(iter(_variants(family)))
        raise ValueError(f"{family} is a task family: name a variant, e.g. {family}/{first_variant}")
    values = variant_values(family, variant) if variant else None

    def read(name):
        text = (folder / name).read_text()
        return Template(text).substitute(values) if variant else text
    request = _request(read("brief.md"))
    if not request:
        raise ValueError(f"{folder / 'brief.md'} has no blockquote with the person's request")
    facts = yaml.safe_load(read("hidden_facts.yaml")) or {}
    requirements = [Requirement.model_validate(entry) for entry in yaml.safe_load(read("requirements.yaml")) or []]
    reference = read("reference.yaml") if (folder / "reference.yaml").exists() else None
    task_format = TaskFormat.model_validate(catalog.task_format(task_id))
    return Task(task_id, request, facts, requirements, reference, task_format)
