"""A checklist over saved Estoa design sessions: did the designer do what Estoa's own failures say to do?

A prototype for the test-print planning eval (coupons/PLANNING.md). One yes/no question per known Estoa failure
(seeds/estoa-failures.yaml) that the estoa-light task can show. Where a question is decided by the session's tool
calls (what it asked `measure`, what it sent to `print_test`), code gives the key; the rest are checked by hand
on a sample. Claude's calls: which failures fit this task, and the wording of each question.
"""
import json
import re
from pathlib import Path

from pydantic import BaseModel

TOOL_ARGS_CHARS = 2500   # a submitted design's code is long; what was asked and test-printed is kept whole
TOOL_REPLY_CHARS = 1500
MAX_CHARS = 400_000      # about 100K tokens, under Jev's 262K context


class Item(BaseModel):
    id: str
    failure: str        # the seed id it comes from
    question: str


ITEMS = [
    Item(id="plug_head", failure="usb-opening-sized-to-receptacle",
         question="Did the designer ask the person for the size of the USB-C plug or cable head that goes into the "
                  "port (the plastic grip, not only the port itself)?"),
    Item(id="plug_reach", failure="usb-tunnel-too-long",
         question="Did the designer check that the plug can reach the port from outside the closed box, i.e. that the "
                  "port isn't set so deep behind the wall that the plug's metal can't seat?"),
    Item(id="keyhole_test", failure="keyholes-point-down",
         question="Before handing in the final design, did the designer ask for a test print of the wall-hanging "
                  "slots or keyholes?"),
    Item(id="wall_screw_size", failure="washer-recess-assumed",
         question="Did the designer ask for the size of the wall screws or their heads before sizing the hanging "
                  "slots?"),
    Item(id="disk_holes", failure="breakout-holes-read-from-listing",
         question="Did the designer ask the person to measure the LED disk's mounting holes (size, spacing or "
                  "position) instead of guessing them?"),
    Item(id="esp32_height", failure="esp32-headers-vs-lid",
         question="Did the designer ask how tall the ESP32 or the parts on the perfboard stand before setting the "
                  "box's depth?"),
    Item(id="screw_length", failure="screws-bottomed-pulled-inserts",
         question="Did the designer work out the disk screws' length from the thickness of what they clamp and how "
                  "deep the hole or nut is?"),
    Item(id="fastener_test", failure="insert-bosses-bulged",
         question="Before the final design, did the designer ask for a test print of a screw post, insert or nut "
                  "pocket?"),
    Item(id="bridge_reasoned", failure="bridged-hole-sealed",
         question="Did the designer consider how a roof, or the top of a hole or opening, prints over air without "
                  "supports (a bridge or an overhang)?"),
    Item(id="any_test", failure="test-print-overscoped",
         question="Did the designer ask for any test print at all before handing in the final design?"),
    Item(id="tool_reach", failure="leg-screw-under-lip",
         question="Did the designer check that a screwdriver or key can reach every screw once the box is assembled?"),
]


class Call(BaseModel):
    name: str
    args: str


def tool_calls(messages: list[dict]) -> list[Call]:
    calls = []
    for message in messages:
        for call in message.get("tool_calls") or []:
            calls.append(Call(name=call["function"]["name"], args=call["function"]["arguments"]))
    return calls


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f" [... {len(text) - limit} more characters]"


def render(messages: list[dict]) -> str:
    """The session as plain text: the request, what the designer said, its tool calls and the replies.
    The system prompt (the same for every trial) and the designer's private reasoning are left out."""
    lines = []
    for message in messages:
        role = message["role"]
        if role == "system":
            continue
        if role == "user":
            lines.append(f"PERSON: {message['content']}")
        elif role == "assistant":
            if message.get("content"):
                lines.append(f"DESIGNER: {message['content']}")
            for call in tool_calls([message]):
                limit = TOOL_ARGS_CHARS if call.name == "submit_design" else MAX_CHARS  # a test print is evidence
                lines.append(f"DESIGNER CALLS {call.name}: {_short(call.args, limit)}")
        elif role == "tool":
            lines.append(f"REPLY: {_short(str(message['content']), TOOL_REPLY_CHARS)}")
    return _short("\n".join(lines), MAX_CHARS)


def _measured(calls: list[Call], item: str, what: str) -> bool:
    return any(c.name == "measure" and re.search(item, c.args, re.I) and re.search(what, c.args, re.I) for c in calls)


def _fields(call: Call) -> tuple[str, str]:
    """A measure call's item and what, or its whole text twice if it isn't JSON."""
    try:
        args = json.loads(call.args)
        return str(args.get("item", "")), str(args.get("what", ""))
    except (json.JSONDecodeError, AttributeError):
        return call.args, call.args


PLUG_ITEM = re.compile(r"\b(plug|charger|cable)\b", re.I)  # "plugged" doesn't match
PLUG_WHAT = re.compile(r"\b(charger|overmou?ld)\b|\bcable'?s? plug\b|\bplug (head|body|housing|tip)\b|\bplastic (grip|housing)\b", re.I)


def _asked_plug_size(calls: list[Call]) -> bool:
    """The charger's plug named as the thing measured: in the item, or as the object in what. Not "with the ESP32
    plugged in", "the opening the plug goes into", the disk connector's plug or its "cable exit direction"
    (2026-11-12 hand check)."""
    for call in calls:
        if call.name != "measure":
            continue
        item, what = _fields(call)
        if PLUG_ITEM.search(item) or PLUG_WHAT.search(what):
            return True
    return False


def _tested(calls: list[Call], what: str) -> bool:
    return any(c.name == "print_test" and re.search(what, c.args, re.I) for c in calls)


def code_keys(messages: list[dict], can_test: bool) -> dict[str, bool]:
    """The questions a program can answer from the tool calls. Claude's keyword choices; a disagreement with a
    judge is checked by hand. Test-print questions are keyed only where the session had the print_test tool.
    The 2026-11-12 run used looser patterns, which the hand check corrected 10 times; these are the corrected
    ones, and they agree with every hand-checked key on the 48 Estoa transcripts."""
    calls = tool_calls(messages)
    keys = {
        "plug_head": _asked_plug_size(calls),
        "wall_screw_size": _measured(calls, r"\bwall\b|\bhang(s|ing)?\b|#8", r"head|diameter|size"),  # not "overhang"
        "disk_holes": _measured(calls, r"dis[ck]", r"hole"),
        "esp32_height": _measured(calls, r"esp|perfboard",
                                  r"tall|stand|overall height|total height|maximum height|"
                                  r"height of (the )?(everything|esp32|tallest|components)"),
    }
    if can_test:
        keys["any_test"] = any(c.name == "print_test" for c in calls)
        keys["keyhole_test"] = _tested(calls, r"keyhole|slot|hang")
        keys["fastener_test"] = _tested(calls, r"post|boss|insert|nut|screw")
    return keys


def estoa_trials(runs: Path) -> list[Path]:
    """The 48 saved Estoa trials (pilot-estoa and test-first): their transcript files."""
    found = sorted(runs.glob("pilot-estoa/estoa-light/*/*/*/transcript.json"))
    return found + sorted(runs.glob("test-first/estoa-light/*/*/*/transcript.json"))


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text())
