"""Every measure(item, what) call a designer made in a saved trial, with the reply it got and what today's lookup
finds, for test 7 (docs/decisions-api.md): can a decisions model match a request to the person's recorded facts?

A trial's transcript holds the call (an assistant tool call named `measure`) and its reply (the tool message with
the same id). The trial record beside it (grades.json, loop.json, replay.json) names the task and the contestant.
Identical requests (task, item, what) are kept once, with every trial that made them.
"""
import json
from pathlib import Path

import yaml
from pydantic import BaseModel

from pbe.runner.measure import NO_ANSWER, Person

RECORD_FILES = ("grades.json", "loop.json", "replay.json", "loop.schema-bug.json")


class Asked(BaseModel):
    """One measure call in one trial."""
    task: str
    contestant: str
    item: str
    what: str
    reply: str  # what the person said then
    trial: str  # the transcript's folder, relative to results/runs


class Request(BaseModel):
    """One distinct (task, item, what), with every trial that asked it."""
    task: str
    item: str
    what: str
    asked: list[Asked]
    lookup: list[str]  # today's lookup: thing.measurement ids, empty for NO_ANSWER

    @property
    def id(self) -> str:
        return f"{self.task} | {self.item} | {self.what}"

    @property
    def answered_then(self) -> bool:
        return any(a.reply != NO_ANSWER for a in self.asked)


def record_beside(transcript: Path) -> dict | None:
    for name in RECORD_FILES:
        path = transcript.parent / name
        if path.exists():
            return json.loads(path.read_text())
    return None


def _arguments(call: dict) -> dict:
    try:
        return json.loads(call["function"].get("arguments") or "{}")
    except json.JSONDecodeError:
        return {}


def _replies(messages: list[dict]) -> dict[str, str]:
    return {m["tool_call_id"]: m.get("content") or "" for m in messages if m.get("role") == "tool"}


def calls_in(messages: list[dict]) -> list[tuple[str, str, str]]:
    """(item, what, reply) for each measure call in a transcript, in order."""
    replies = _replies(messages)
    found = []
    for message in messages:
        for call in message.get("tool_calls") or []:
            if call.get("function", {}).get("name") != "measure":
                continue
            args = _arguments(call)
            found.append((str(args.get("item", "")), str(args.get("what", "")), replies.get(call.get("id"), "")))
    return found


def asked_in(transcript: Path, runs: Path) -> list[Asked]:
    record = record_beside(transcript)
    if record is None:
        return []
    trial = str(transcript.parent.relative_to(runs))
    return [Asked(task=record["task"], contestant=record["model"], item=item, what=what, reply=reply, trial=trial)
            for item, what, reply in calls_in(json.loads(transcript.read_text()))]


def facts_for(task: str, tasks: Path) -> dict:
    """A task's hidden_facts.yaml. A family's variants share one file ("nut-knob/M3" reads tasks/nut-knob)."""
    return yaml.safe_load((tasks / task.split("/")[0] / "hidden_facts.yaml").read_text()) or {}


def lookup(facts: dict, item: str, what: str) -> list[str]:
    """What pbe/runner/measure.py's lookup reveals for this request today."""
    person = Person(facts)
    person.measure(item, what)
    return person.log[-1].revealed


def collect(runs: Path, tasks: Path) -> list[Request]:
    """Every distinct measure request in the saved runs, in a stable order."""
    grouped: dict[tuple[str, str, str], list[Asked]] = {}
    for transcript in sorted(runs.glob("**/transcript.json")):
        for asked in asked_in(transcript, runs):
            grouped.setdefault((asked.task, asked.item, asked.what), []).append(asked)
    requests = []
    for (task, item, what), asked in sorted(grouped.items()):
        requests.append(Request(task=task, item=item, what=what, asked=asked,
                                lookup=lookup(facts_for(task, tasks), item, what)))
    return requests
