"""Load a task: the person's request, the hidden facts, the typed requirements and
the reference solution."""
from dataclasses import dataclass
from pathlib import Path
from string import Template

import yaml

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Task:
    id: str
    request: str
    hidden_facts: dict
    requirements: list
    reference: str | None  # the reference solution, as YAML text


def load(task_id) -> Task:
    """A task folder, or one variant of a task family: "family/variant". A family is a
    task folder whose files are templates, with variants.yaml giving each variant's $values
    (the parametric families in PLAN), so one design makes many tasks."""
    family, _, variant = task_id.partition("/")
    d = ROOT / "tasks" / family
    if (d / "variants.yaml").exists() and not variant:
        raise ValueError(f"{family} is a task family: name a variant, e.g. {family}/{next(iter(yaml.safe_load((d / 'variants.yaml').read_text())))}")
    values = yaml.safe_load((d / "variants.yaml").read_text())[variant] if variant else None

    def read(name):
        text = (d / name).read_text()
        return Template(text).substitute(values) if variant else text
    # the person's words are the brief's first blockquote; the rest of brief.md is notes,
    # and a later quote in the notes must not leak into the prompt
    lines = read("brief.md").splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(">")), len(lines))
    quote = []
    for line in lines[start:]:
        if not line.startswith(">"):
            break
        quote.append(line[1:].strip())
    request = "\n".join(quote).strip()
    if not request:
        raise ValueError(f"{d / 'brief.md'} has no blockquote with the person's request")
    facts = yaml.safe_load(read("hidden_facts.yaml")) or {}
    reqs = yaml.safe_load(read("requirements.yaml")) or []
    return Task(task_id, request, facts, reqs, read("reference.yaml") if (d / "reference.yaml").exists() else None)
