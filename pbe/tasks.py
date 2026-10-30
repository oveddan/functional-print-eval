"""Load a task: the person's request, the hidden facts, the typed requirements and
the reference solution."""
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Task:
    id: str
    request: str
    hidden_facts: dict
    requirements: list
    reference: Path | None


def load(task_id) -> Task:
    d = ROOT / "tasks" / task_id
    brief = (d / "brief.md").read_text()
    # the person's words are the brief's first blockquote; the rest of brief.md is notes,
    # and a later quote in the notes must not leak into the prompt
    lines = brief.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(">")), len(lines))
    quote = []
    for line in lines[start:]:
        if not line.startswith(">"):
            break
        quote.append(line[1:].strip())
    request = "\n".join(quote).strip()
    if not request:
        raise ValueError(f"{d / 'brief.md'} has no blockquote with the person's request")
    facts = yaml.safe_load((d / "hidden_facts.yaml").read_text()) or {}
    reqs = yaml.safe_load((d / "requirements.yaml").read_text()) or []
    ref = d / "reference.yaml"
    return Task(task_id, request, facts, reqs, ref if ref.exists() else None)
