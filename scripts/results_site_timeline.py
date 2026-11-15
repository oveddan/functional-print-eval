"""The timeline on a trial's page of the results site: the trial's phases in the order they happened, each with a
short label and one line of what was done. scripts/results_site.py puts it in every trial's detail as `timeline`.

A phase is one of:
- asked: measurements the model asked the person for, in a row (the replies are in the trial's `measures`);
- round: one request for test prints before the design (the trial's `test_prints`), with a render of each piece
  from scripts/results_site_media_rounds.json where there is one;
- design: a design handed in, with its verdict: the first print, or the second after the person's reply;
- told: what the person said after the first print (a loop arm's `reply` and `report`), or a build error sent back.

A first print and its second print share one timeline: each of the two trials' details carries the same phases,
and each phase names the trial (`slug`) whose detail holds what it shows.

Nothing here is printed. The person is a program that answers from Dan's records; the labels say "test print" for
what the model asked that person to print, and a design's verdict is the saved one, never recomputed here.
"""
import json
from functools import cache
from itertools import groupby
from pathlib import Path

ROUNDS_MEDIA = Path(__file__).with_name("results_site_media_rounds.json")
TEST_PRINTED = "I printed"  # how the person's reply to an answered print_test call starts (pbe/runner/agent.py)
LINE_CAP = 150


def count(n: int, one: str) -> str:
    return f"{n} {one}{'' if n == 1 else 's'}"


def clip(text: str) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= LINE_CAP else text[:LINE_CAP - 1].rstrip() + "…"


# ---- renders of the test prints a model asked for ----

@cache
def round_media() -> dict:
    """{trial id: {"error", "rounds": [{"round", "parts", "not_built"}]}}, or {} when the manifest isn't there."""
    if not ROUNDS_MEDIA.exists():
        return {}
    try:
        return json.loads(ROUNDS_MEDIA.read_text()).get("trials") or {}
    except (json.JSONDecodeError, AttributeError):
        return {}


def with_media(trial_id: str, rounds: list[dict]) -> list[dict]:
    """Each test-print round with `media` ({"parts": [...]}, as a design's media lists its parts) and `not_built`
    (pieces whose code didn't run), or with `media_none`: why the round has no picture."""
    saved = round_media().get(trial_id)
    drawn = {entry["round"]: entry for entry in (saved or {}).get("rounds") or []}
    out = []
    for round_ in rounds:
        found = drawn.get(round_["round"])
        asked = [part["id"] for part in round_["parts"]]
        if found and found["parts"] and {part["id"] for part in found["parts"]} <= set(asked):
            parts = [part | {"role_label": "test print"} for part in found["parts"]]
            out.append(round_ | {"media": {"parts": parts, "scene": None}, "not_built": found.get("not_built") or {}})
        elif found and found.get("not_built"):
            out.append(round_ | {"media": None, "not_built": found["not_built"],
                                 "media_none": "The code of these test prints didn't run when it was built again for a picture"})
        else:
            out.append(round_ | {"media": None, "not_built": {}, "media_none": "No render of these test prints is saved"})
    return out


# ---- the order things were asked in ----

def _text(content) -> str:
    if isinstance(content, list):
        return "".join(piece.get("text", "") for piece in content if isinstance(piece, dict))
    return content or ""


def asked_order(folder: Path, measures: int, rounds: int) -> list[str]:
    """"measure" or "round" for each question and each answered test-print request, in the saved transcript's order.
    When the transcript doesn't account for exactly what the record holds, measurements come first, then rounds."""
    fallback = ["measure"] * measures + ["round"] * rounds
    path = folder / "transcript.json"
    if not path.exists():
        return fallback
    messages = json.loads(path.read_text())
    replies = {m.get("tool_call_id"): _text(m.get("content")) for m in messages if m.get("role") == "tool"}
    order = []
    for message in messages:
        for call in message.get("tool_calls") or []:
            name = (call.get("function") or {}).get("name")
            if name == "measure":
                order.append("measure")
            elif name == "print_test" and replies.get(call.get("id"), "").startswith(TEST_PRINTED):
                order.append("round")
    return order if (order.count("measure"), order.count("round")) == (measures, rounds) else fallback


# ---- phases ----

def asked_phase(entry, first: int, n: int, number: int, again: bool) -> dict:
    asked = entry.record.measures[first:first + n]
    what = next((" ".join(m.what.split()) for m in asked if m.what and m.what.strip()), "")
    what = what if len(what) <= 80 else what[:79].rstrip() + "…"
    example = f"{'It asked' if n == 1 else 'The first'}: “{what}”. " if what else ""
    return {"key": f"asked-again-{number}" if again else f"asked-{number}", "kind": "asked", "slug": entry.slug,
            "label": f"Asked {count(n, 'more measurement' if again else 'measurement')}",
            "line": f"{example}The person answered from a fixed list of measurements.",
            "first": first, "count": n}


def round_phase(entry, number: int, of: int) -> dict:
    test = entry.record.test_prints[number - 1]
    pieces = len(test["parts"])
    cant = sum("can't tell" in line["text"] for lines in test["reply"].values() for line in lines)
    told = ("The reply comes from Dan's recorded test prints" if not cant
            else f"The reply comes from Dan's recorded test prints, with {count(cant, 'answer')} “I can't tell”")
    return {"key": f"round-{number}", "kind": "round", "slug": entry.slug, "round": number,
            "label": f"Test prints, round {number}" if of > 1 else "Test prints",
            "line": clip(f"Asked the person to print {count(pieces, 'test piece')}. {told}; nothing was printed."),
            "pieces": pieces}


def design_line(entry, reasons: list[str]) -> str:
    if entry.verdict == "pass":
        return "Every counted check passes against the recorded test prints. The design wasn't printed."
    if reasons:
        more = f", and {count(len(reasons) - 1, 'more reason')}" if len(reasons) > 1 else ""
        return clip(f"{reasons[0].replace('`', '')}{more}.")
    return clip(entry.summary.split(": ", 1)[-1].capitalize() + ".")


def design_phase(entry, key: str, name: str, reasons: list[str]) -> dict:
    return {"key": key, "kind": "design", "slug": entry.slug, "verdict": entry.verdict,
            "label": f"{name}: {entry.verdict}", "line": design_line(entry, reasons)}


def own_phases(entry, name: str, reasons, again: bool = False) -> list[dict]:
    """What one trial or one second turn did, in order: its questions, its test-print rounds, then its design."""
    measures = len(getattr(entry.record, "measures", None) or [])
    rounds = len(getattr(entry.record, "test_prints", None) or [])
    phases, first, round_, group = [], 0, 0, 0
    for kind, run in groupby(asked_order(entry.folder, measures, rounds)):
        n = len(list(run))
        if kind == "measure":
            group += 1
            phases.append(asked_phase(entry, first, n, group, again))
            first += n
        else:
            for _ in range(n):
                round_ += 1
                phases.append(round_phase(entry, round_, rounds))
    return phases + [design_phase(entry, "second" if again else "design", name, list(dict.fromkeys(reasons(entry))))]


TOLD = {
    "feedback": ("Told how it came out", "The person, a program, said how the first design would come out, from Dan's recorded test prints. Nothing was printed."),
    "neutral": ("Asked to look again", "The person only asked for the design again, without saying how the first came out."),
    "crash": ("Sent its build error", "The model was sent the error its design's code stopped on and asked to fix it."),
}
SECOND_NAME = {"feedback": "Second print", "neutral": "Second look", "crash": "Retry"}


def timeline(entry, by_id: dict, reasons) -> list[dict]:
    """The phases of the trial `entry` belongs to, first to last. `reasons(entry)` gives the short reasons a design
    didn't pass (the site's own issue rows). A trial that only handed in a design has one phase, and the page draws
    no timeline for it."""
    if entry.kind == "trial":
        first, second = entry, by_id.get(entry.second_print) if entry.second_print else None
    else:
        first, second = by_id.get(entry.replays), entry
    phases = []
    if first is not None:
        name = ("First print" if second is not None or first.group.startswith("first")
                else "Final design" if first.condition == "can_test" else "Design")
        phases += own_phases(first, name, reasons)
    if second is not None:
        arm = second.arm or "crash"
        label, line = TOLD[arm]
        phases.append({"key": "told", "kind": "told", "slug": second.slug, "arm": arm, "label": label, "line": line})
        phases += own_phases(second, SECOND_NAME[arm], reasons, again=True)
    return phases
