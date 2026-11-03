"""One trial: a model designs for a task through a fixed tool set, then is graded.

Tools: measure (the person's own measurements, from a lookup table), submit_design
(schema errors go back to the model to fix; repairs are counted, not failed) and
report_limitation (changes nothing; records what the model wanted to use but couldn't,
and what stopped it, so a failure caused by the eval's constraints shows as one).
"""
import json
import time
from functools import cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from pbe import checks, llm, requirements
from pbe.build import build_parts
from pbe.measure import Person
from pbe.submission import Submission

ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = ("can_ask", "all_given")

SYSTEM = """You're designing a part for someone to 3D print at home. They'll print it on their own printer, use only the hardware listed below, and put it together by following your manual.

## Their setup
{setup}

## Hardware they can use
Refer to an item by its catalog reference: "ISO 4762 M5x30" (socket head screw, size x length, from the lengths listed), "ISO 4032 M5" (hex nut), "ISO 10511 M5" (nylon-insert lock nut), "ISO 7089 M5" (washer), "ASME B18.2.2 1/4-20" (1/4"-20 nut), "insert M3x4x5" (heat-set insert), "salvaged:webcam-mount-bolt".

```yaml
{hardware}```

## How to work
You have these tools:
- measure(item, what): ask the person to measure one of their own things, such as their desk or their phone. They answer with what they measured, or say they can't measure it.
- submit_design(...): hand in the finished design. This ends the conversation.
- report_limitation(wanted, blocked_by, why): say you wanted to use something (a technique, a tool, a part or material, a way of handing in the design) but couldn't because of what's available here. It doesn't change anything, but it's noted.
You have at most {max_turns} turns. Hand in a design before they run out.

## The design you hand in
submit_design's schema describes every field. The rules that matter:
- Every dimension that comes from hardware or the real world is a named param, with its source: measured (the person measured it for you), datasheet, catalog, asked (the person told you), guessed, unknown, or design (your own choice).
- Each part's `code` is Python that defines build(p) and returns a CadQuery Workplane or Shape. `cq` is already imported, and p.<name> is each param's value. Dimensions that come from hardware or the real world must come from params.
- Model each part in the orientation it's printed in, with z = 0 on the bed.
- The manual is the steps the person follows, naming the parts and hardware each step uses."""


def setup_text():
    p = yaml.safe_load((ROOT / "catalog/printer.yaml").read_text())
    bx, by, bz = p["bed_mm"]
    return "\n".join([
        f"- Printer: {p['printer']}, build volume {bx} x {by} x {bz} mm",
        f"- Nozzle: {p['eval_setup']['nozzle_mm']} mm",
        f"- Layer height: {p['layer_mm']} mm",
        f"- Filament: {p['eval_setup']['filament']}",
        f"- Longest bridge seen to print cleanly on this setup: {p['bridging']['max_span_mm']} mm",
    ])


def hardware_text():
    data = yaml.safe_load((ROOT / "catalog/hardware.yaml").read_text())

    def strip(node):  # internal bookkeeping, not facts about the hardware
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items() if k != "verify"}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node
    return yaml.safe_dump(strip(data), sort_keys=False, allow_unicode=True)


def _inline(schema):
    """Tool schemas can't rely on $ref or prefixItems across providers: inline both."""
    defs = schema.pop("$defs", {})

    def walk(n):
        if isinstance(n, dict):
            if "$ref" in n:
                return walk(dict(defs[n["$ref"].split("/")[-1]]))
            n = dict(n)
            if "prefixItems" in n:
                items = n.pop("prefixItems")
                n.update(items=items[0], minItems=len(items), maxItems=len(items))
            return {k: walk(v) for k, v in n.items()}
        if isinstance(n, list):
            return [walk(v) for v in n]
        return n
    return walk(schema)


@cache
def tools():
    design = _inline(Submission.model_json_schema())
    design["properties"].pop("task")  # the runner fills it in
    design["required"] = [r for r in design["required"] if r != "task"]

    def fn(name, description, parameters):
        return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}
    return [
        fn("measure", "Ask the person to measure one of their own things. They answer with what they measured, or say they can't.",
           {"type": "object", "properties": {
               "item": {"type": "string", "description": "What to measure, e.g. 'desk'"},
               "what": {"type": "string", "description": "Which dimension, e.g. 'thickness at the edge'"}},
            "required": ["item", "what"]}),
        fn("submit_design", "Hand in the finished design. This ends the conversation.", design),
        fn("report_limitation", "Say you wanted to use something (a technique, a tool, a part or material, a way of "
           "handing in the design) but couldn't because of what's available here. It changes nothing; it's noted.",
           {"type": "object", "properties": {
               "wanted": {"type": "string", "description": "What you wanted to use or do"},
               "blocked_by": {"type": "string", "description": "What stopped you, e.g. not in the hardware list, no such tool, the submission format"},
               "why": {"type": "string", "description": "Why you wanted it"}},
            "required": ["wanted", "blocked_by", "why"]}),
    ]


def first_message(task, condition, person):
    if condition == "all_given" and person.facts:
        return f"{task.request}\n\nMeasurements I took:\n{person.all_measurements()}"
    return task.request


# printing know-how a model shows in its own words; recorded, never scored
KNOW_HOW = {
    "chamfer": r"chamfer", "elephant's foot": r"elephant", "holes print undersize": r"undersi|print\w* (small|tight)|shrink",
    "drill or ream out": r"\bdrill|\bream", "clearance": r"clearance", "supports": r"support",
}


def observe(sub, built):
    """Behaviour worth seeing across models, not graded: per final part with a through hole,
    the hole's tightest clear width and how much its two ends flare (a lead-in chamfer
    or counterbore); and which printing know-how the submission's text mentions."""
    import re
    out = {"holes": {}, "mentions": []}
    for p in sub.parts:
        b = built.get(p.id)
        if p.role != "final" or b is None or not b.ok:
            continue
        prof = requirements.hole_profile(b.mesh)
        if prof:
            out["holes"][p.id] = prof
    text = " ".join([sub.note] + [v.note for v in sub.params.values()] + [s.text for s in sub.manual]
                    + [p.print_orientation for p in sub.parts] + [c.check.description for c in sub.criteria]).lower()
    out["mentions"] = [name for name, pat in KNOW_HOW.items() if re.search(pat, text)]
    return out


def evaluate(task, sub, out_dir):
    """Build the parts, run every check, and record observations: (findings, observations)."""
    built = build_parts(sub, Path(out_dir) / "parts")
    findings = [f for check in checks.ALL for f in check(built)] + requirements.grade(task, sub, built)
    return findings, observe(sub, built)


def grade(task, sub, out_dir):
    return evaluate(task, sub, out_dir)[0]


def run_trial(task, model, condition="can_ask", max_turns=8, max_tokens=32000, chat=llm.chat):
    """Returns (record, messages, submission or None). Infrastructure errors end the trial
    with outcome "error", counted apart from the model's own failures."""
    person = Person(task.hidden_facts)
    messages = [
        {"role": "system", "content": SYSTEM.format(setup=setup_text(), hardware=hardware_text(), max_turns=max_turns)},
        {"role": "user", "content": first_message(task, condition, person)},
    ]
    calls, limitations, repairs, sub, error = [], [], 0, None, None
    t0 = time.monotonic()
    for _ in range(max_turns):
        try:
            resp = chat(model, messages, tools=tools(), max_tokens=max_tokens)
        except llm.LLMError as e:
            error = str(e)
            break
        choice = resp["choices"][0]
        msg = choice["message"]
        calls.append({"model": resp.get("model"), "provider": resp.get("provider"), "finish_reason": choice.get("finish_reason"),
                      "usage": resp.get("usage"), "elapsed_s": resp.get("elapsed_s")})
        # pass reasoning back unchanged: some providers need it to continue a tool-use turn
        messages.append({k: v for k, v in msg.items() if v is not None and k in ("role", "content", "tool_calls", "reasoning", "reasoning_details")})
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            messages.append({"role": "user", "content": "Please use your tools: measure to ask me for a measurement, submit_design to hand in the design."})
            continue
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError as e:
                repairs += name == "submit_design"
                result = f"Couldn't read your arguments as JSON ({e}). Call {name} again."
            else:
                if name == "measure":
                    result = person.measure(str(args.get("item", "")), str(args.get("what", "")))
                elif name == "report_limitation":
                    limitations.append(args)
                    result = "Noted. Continue with what you have."
                elif name == "submit_design":
                    try:
                        sub = Submission.model_validate({**args, "task": task.id})
                        result = "Received."
                    except ValidationError as e:
                        repairs += 1
                        result = f"That isn't a valid submission. Fix these and call submit_design again:\n{e}"
                else:
                    result = f"There's no tool called {name}."
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
        if sub is not None:
            break
    cost = sum((c["usage"] or {}).get("cost") or 0 for c in calls)
    outcome = "error" if error else "submitted" if sub else "no_submission"
    record = {
        "task": task.id, "model": model, "condition": condition, "outcome": outcome, "error": error,
        "turns": len(calls), "repairs": repairs, "measures": person.log, "revealed": person.revealed,
        "hidden": [f"{k}.{m}" for k, v in person.facts.items() for m in v["measurements"]],
        "limitations": limitations, "cost_usd": round(cost, 6), "elapsed_s": round(time.monotonic() - t0, 1),
        "settings": {"max_turns": max_turns, "max_tokens": max_tokens, "temperature": "provider default"},
        "calls": calls,
    }
    return record, messages, sub
