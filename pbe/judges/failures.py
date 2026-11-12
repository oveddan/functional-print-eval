"""Sorting failure records into the eval's failure classes, and flagging ones that fit none.

The key is the class each record in seeds/*-failures.yaml already has (`class:`, with `also:` for a second one).
The judge sees what went wrong and how it was found, not the fix: a new failure coming in from a build or a
grader's finding has those, and the fix ("ask for the size first") would give the class away. Claude's call.

Flagging is tested by holding a class out: its records are judged against the other nine plus "none of these",
and a flag is a "none" answer or a weak top answer. Naming a new class is left to a chat model and Dan; a
decisions model only flags (docs/decisions-api.md).
"""
from pathlib import Path

import yaml
from pydantic import BaseModel

NONE = "none_of_these"
NONE_GUIDANCE = "The failure fits none of the classes above."


class FailureClass(BaseModel):
    id: str
    name: str
    description: str

    def guidance(self) -> str:
        return f"{self.name}: {self.description}"


class Failure(BaseModel):
    id: str
    source: str          # the seeds file it's from
    cls: str             # its class
    also: list[str]      # any second class
    text: str            # what the judge sees

    def accepts(self, pick: str) -> bool:
        return pick == self.cls or pick in self.also


def load_classes(seeds: Path) -> list[FailureClass]:
    return [FailureClass(**{k: c[k] for k in ("id", "name", "description")})
            for c in yaml.safe_load((seeds / "classes.yaml").read_text())]


def _text(record: dict) -> str:
    return f"What went wrong: {record['did']}\nHow it was found: {record['found_by']}"


def load_failures(seeds: Path) -> list[Failure]:
    found = []
    for path in sorted(seeds.glob("*-failures.yaml")):
        for record in yaml.safe_load(path.read_text()):
            found.append(Failure(id=record["id"], source=path.name, cls=record["class"],
                                 also=record.get("also", []), text=_text(record)))
    return found


def criteria(classes: list[FailureClass], leave_out: str | None = None) -> dict[str, str]:
    """Option id -> guidance for the choice question, without `leave_out`, always with "none of these"."""
    options = {c.id: c.guidance() for c in classes if c.id != leave_out}
    options[NONE] = NONE_GUIDANCE
    return options
