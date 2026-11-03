"""Load a task: the person's request, the hidden facts, the typed requirements and
the reference solution."""
from dataclasses import dataclass
from pathlib import Path
from string import Template

import yaml
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]


class Requirement(BaseModel):
    """One entry of a task's requirements.yaml: what's checked, and which grader checks it."""
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str
    grader: str  # a name in requirements.GRADERS
    args: dict | None = None  # passed to the grader
    failure_class: str = Field("", alias="class")


@dataclass
class Task:
    id: str
    request: str
    hidden_facts: dict
    requirements: list[Requirement]
    reference: str | None  # the reference solution, as YAML text


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
    return Task(task_id, request, facts, requirements, reference)
