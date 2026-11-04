"""One trial: a model designs for a task through a fixed tool set, then is graded.

Tools: measure (the person's own measurements, from a lookup table), submit_design
(schema errors go back to the model to fix; repairs are counted, not failed) and
report_limitation (changes nothing; records what the model wanted to use but couldn't,
and what stopped it, so a failure caused by the eval's constraints shows as one).
"""
import json
import re
import time
from functools import cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from pbe.graders import checks, nuts, requirements
from pbe.parts.build import build_parts
from pbe.parts.printer import printer
from pbe.parts.submission import Submission
from pbe.runner import llm
from pbe.runner.measure import Person
from pbe.runner.trial_record import ModelCall, Settings, TrialRecord

ROOT = Path(__file__).resolve().parents[2]
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
    setup = printer()
    bed_x, bed_y, bed_z = setup.bed_mm
    return "\n".join([
        f"- Printer: {setup.printer}, build volume {bed_x} x {bed_y} x {bed_z} mm",
        f"- Nozzle: {setup.eval_setup.nozzle_mm} mm",
        f"- Layer height: {setup.layer_mm} mm",
        f"- Filament: {setup.eval_setup.filament}",
        f"- Longest bridge seen to print cleanly on this setup: {setup.bridging.max_span_mm} mm",
    ])


def hardware_text():
    data = yaml.safe_load((ROOT / "catalog/hardware.yaml").read_text())

    def strip(node):  # internal bookkeeping, not facts about the hardware
        if isinstance(node, dict):
            return {key: strip(value) for key, value in node.items() if key != "verify"}
        if isinstance(node, list):
            return [strip(value) for value in node]
        return node
    return yaml.safe_dump(strip(data), sort_keys=False, allow_unicode=True)


def _inline(schema):
    """Tool schemas can't rely on $ref or prefixItems across providers: inline both."""
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, list):
            return [walk(value) for value in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return walk(dict(defs[node["$ref"].split("/")[-1]]))
        node = dict(node)
        if "prefixItems" in node:
            items = node.pop("prefixItems")
            node.update(items=items[0], minItems=len(items), maxItems=len(items))
        return {key: walk(value) for key, value in node.items()}
    return walk(schema)


@cache
def tools():
    design = _inline(Submission.model_json_schema())
    design["properties"].pop("task")  # the runner fills it in
    design["required"] = [r for r in design["required"] if r != "task"]

    def function_tool(name, description, parameters):
        return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}
    return [
        function_tool("measure", "Ask the person to measure one of their own things. They answer with what they measured, or say they can't.",
           {"type": "object", "properties": {
               "item": {"type": "string", "description": "What to measure, e.g. 'desk'"},
               "what": {"type": "string", "description": "Which dimension, e.g. 'thickness at the edge'"}},
            "required": ["item", "what"]}),
        function_tool("submit_design", "Hand in the finished design. This ends the conversation.", design),
        function_tool("report_limitation", "Say you wanted to use something (a technique, a tool, a part or material, a way of "
           "handing in the design) but couldn't because of what's available here. It changes nothing; it's noted.",
           {"type": "object", "properties": {
               "wanted": {"type": "string", "description": "What you wanted to use or do"},
               "blocked_by": {"type": "string", "description": "What stopped you, e.g. not in the hardware list, no such tool, the submission format"},
               "why": {"type": "string", "description": "Why you wanted it"}},
            "required": ["wanted", "blocked_by", "why"]}),
    ]


def first_message(task, condition, person):
    if condition == "all_given" and person.things:
        return f"{task.request}\n\nMeasurements I took:\n{person.all_measurements()}"
    return task.request


# printing know-how a model shows in its own words; recorded, never scored
KNOW_HOW = {
    "chamfer": r"chamfer", "elephant's foot": r"elephant", "holes print undersize": r"undersi|print\w* (small|tight)|shrink",
    "drill or ream out": r"\bdrill|\bream", "clearance": r"clearance", "supports": r"support",
}


def _hole_profiles(sub, built):
    """Each final part's through hole, by part id, for the parts that built and have one."""
    profiles = {}
    for part in sub.parts:
        built_part = built.get(part.id)
        if part.role != "final" or built_part is None or not built_part.ok:
            continue
        profile = requirements.hole_profile(built_part.mesh)
        if profile:
            profiles[part.id] = profile
    return profiles


def _know_how_mentioned(sub):
    """The KNOW_HOW the submission's own text names."""
    texts = [sub.note, *(param.note for param in sub.params.values()), *(step.text for step in sub.manual),
             *(part.print_orientation for part in sub.parts), *(criterion.check.description for criterion in sub.criteria)]
    text = " ".join(texts).lower()
    return [name for name, pattern in KNOW_HOW.items() if re.search(pattern, text)]


def observe(task, sub, built):
    """Behaviour worth seeing across models, not graded: per final part with a through hole,
    the hole's tightest clear width and how much its two ends flare (a lead-in chamfer
    or counterbore); every nut pocket, and whether the task's coupon says it holds; and
    which printing know-how the submission's text mentions."""
    seen = {"holes": _hole_profiles(sub, built), "mentions": _know_how_mentioned(sub)}
    for requirement in task.requirements:
        if requirement.grader == "nut.fit":
            seen["nut_pockets"] = nuts.summarize(sub, built, **requirement.args)
    return seen


def _check_error(check, e, part=None):
    """A check that crashed: on one part, if it's known, so a crash on a test print is marked as one."""
    return checks.Finding(check=check.__name__, part=part.part_id if part else "-", ok=False,
                          detail=f"check error: {type(e).__name__}: {e}", failure_class="C6-printability",
                          test_print=bool(part) and part.role == "coupon")


def _run_check(check, built):
    """A generic check's findings. If it crashes, it runs again part by part, so the crash is pinned on the
    part whose geometry broke it, and a test print's crash can't fail the trial on its own."""
    try:
        return check(built)
    except Exception:  # as in requirements.grade: model geometry can break a check
        pass
    findings = []
    for part_id, part in built.items():
        try:
            findings += check({part_id: part})
        except Exception as e:
            findings.append(_check_error(check, e, part))
    return findings


def evaluate(task, sub, out_dir):
    """Build the parts, run every check, and record observations: (findings, observations)."""
    built = build_parts(sub, Path(out_dir) / "parts")
    findings = []
    for check in checks.ALL:
        findings += _run_check(check, built)
    findings += requirements.grade(task, sub, built)
    try:
        observations = observe(task, sub, built)
    except Exception as e:  # observations aren't scored, so one that breaks mustn't cost the trial
        observations = {"error": f"{type(e).__name__}: {e}"}
    return findings, observations


def grade(task, sub, out_dir):
    return evaluate(task, sub, out_dir)[0]


# the model's message as the transcript keeps it and the next request sends it back. Reasoning
# goes back unchanged: some providers need it to continue a tool-use turn
KEPT_FROM_REPLY = ("role", "content", "tool_calls", "reasoning", "reasoning_details")
USE_YOUR_TOOLS = "Please use your tools: measure to ask me for a measurement, submit_design to hand in the design."


class UnreadableArguments(ValueError):
    """A tool call whose arguments the model has to send again. The message says why."""


def read_arguments(call: llm.ToolCall) -> dict:
    name = call.function.name
    try:
        arguments = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError as e:
        raise UnreadableArguments(f"Couldn't read your arguments as JSON ({e}). Call {name} again.") from None
    if not isinstance(arguments, dict):
        raise UnreadableArguments(f"Your arguments have to be a JSON object. Call {name} again.")
    return arguments


class TrialTools:
    """The model's three tools, and what its calls to them collect over one trial."""

    def __init__(self, task, person):
        self.task = task
        self.person = person
        self.limitations = []  # whatever the model passed to report_limitation
        self.repairs = 0  # submit_design calls sent back to be fixed
        self.submission = None  # the valid design, once one is handed in

    def answer(self, call: llm.ToolCall) -> str:
        """Run one tool call; what the model is told."""
        tools_by_name = {"measure": self.measure, "report_limitation": self.report_limitation, "submit_design": self.submit_design}
        try:
            arguments = read_arguments(call)
        except UnreadableArguments as e:
            if call.function.name == "submit_design":  # a submission sent back to fix is a repair
                self.repairs += 1
            return str(e)
        tool = tools_by_name.get(call.function.name)
        if tool is None:
            return f"There's no tool called {call.function.name}."
        return tool(arguments)

    def measure(self, arguments):
        return self.person.measure(str(arguments.get("item", "")), str(arguments.get("what", "")))

    def report_limitation(self, arguments):
        self.limitations.append(arguments)
        return "Noted. Continue with what you have."

    def submit_design(self, arguments):
        try:
            self.submission = Submission.model_validate({**arguments, "task": self.task.id})
        except ValidationError as e:
            self.repairs += 1
            return f"That isn't a valid submission. Fix these and call submit_design again:\n{e}"
        return "Received."


def opening_messages(task, condition, person, max_turns):
    system = SYSTEM.format(setup=setup_text(), hardware=hardware_text(), max_turns=max_turns)
    return [{"role": "system", "content": system}, {"role": "user", "content": first_message(task, condition, person)}]


def as_sent_back(message: dict) -> dict:
    return {key: value for key, value in message.items() if value is not None and key in KEPT_FROM_REPLY}


def answers_to(reply: llm.Reply, trial_tools: TrialTools) -> list[dict]:
    """What goes back to the model after its turn: each tool call's result, or a reminder to use the tools."""
    if not reply.tool_calls:
        return [{"role": "user", "content": USE_YOUR_TOOLS}]
    return [{"role": "tool", "tool_call_id": call.id, "content": trial_tools.answer(call)} for call in reply.tool_calls]


def outcome_of(error, sub):
    if error:
        return "error"
    return "submitted" if sub is not None else "no_submission"


def run_trial(task, model, condition="can_ask", max_turns=8, max_tokens=32000, chat=llm.chat):
    """Returns (record, messages, submission or None). Infrastructure errors end the trial
    with outcome "error", counted apart from the model's own failures."""
    person = Person(task.hidden_facts)
    trial_tools = TrialTools(task, person)
    messages = opening_messages(task, condition, person, max_turns)
    calls, error = [], None
    started = time.monotonic()
    for _ in range(max_turns):
        try:
            response = chat(model, messages, tools=tools(), max_tokens=max_tokens)
        except llm.LLMError as e:
            error = str(e)
            break
        reply = llm.Reply.model_validate(response)
        calls.append(ModelCall.from_reply(reply))
        messages.append(as_sent_back(reply.message))
        messages += answers_to(reply, trial_tools)
        if trial_tools.submission is not None:
            break
    record = TrialRecord(
        task=task.id, model=model, condition=condition, outcome=outcome_of(error, trial_tools.submission), error=error,
        turns=len(calls), repairs=trial_tools.repairs, measures=person.log, revealed=person.revealed,
        hidden=[f"{thing}.{measurement}" for thing, measurement in person.every_measurement()],
        limitations=trial_tools.limitations, cost_usd=round(sum(call.cost_usd for call in calls), 6),
        elapsed_s=round(time.monotonic() - started, 1),
        settings=Settings(max_turns=max_turns, max_tokens=max_tokens, temperature="provider default"),
        calls=calls,
    )
    return record, messages, trial_tools.submission
