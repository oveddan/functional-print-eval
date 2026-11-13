"""One trial: a model designs for a task through a fixed tool set, then is graded.

Tools: measure (the person's own measurements, from a lookup table), submit_design
(schema errors go back to the model to fix; repairs are counted, not failed) and
report_limitation (changes nothing; records what the model wanted to use but couldn't,
and what stopped it, so a failure caused by the eval's constraints shows as one).
In the can_run_code condition the model also has run_python (pbe/runner/python_tool.py), and
submit_design builds every part before accepting the design, sending build errors back to
fix (pbe/runner/build_on_submit.py). In the can_test condition the model also has print_test: it may ask the
person to print test pieces before handing in the final design, and hears how each came out, from the recorded
test prints only (pbe/runner/coupon_loop.py's readings). Whether to test, and what, is the model's call. The other
conditions' prompt and tools are exactly as they were before either existed.
"""
import base64
import json
import re
import tempfile
import time
from functools import cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from pbe.graders import checks, nuts, requirements
from pbe.parts.build import build_parts
from pbe.parts.printer import printer
from pbe.parts.submission import Submission
from pbe.runner import build_on_submit, llm, python_tool
from pbe.runner.measure import Person
from pbe.runner.python_tool import PythonTool
from pbe.runner.tasks import TaskFormat
from pbe.runner.trial_record import BuildOnSubmit, ModelCall, Settings, TrialRecord

ROOT = Path(__file__).resolve().parents[2]
TEST_CONDITION = "can_test"
DATASHEET = "can_ask_datasheet"  # can_ask, with the task's datasheet handed over with the request
CONDITIONS = ("can_ask", "all_given", python_tool.CONDITION, TEST_CONDITION, DATASHEET)
# each code run or test print takes a turn, so a model that can do either gets more of them
DEFAULT_MAX_TURNS = {"can_ask": 8, "all_given": 8, python_tool.CONDITION: 20, TEST_CONDITION: 12, DATASHEET: 8}

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


def hardware_text(left_out=()):
    """The hardware list as the prompt shows it. `left_out` names top-level sections a task gives
    through its hidden facts instead (its format.yaml); with none, the whole catalog."""
    data = yaml.safe_load((ROOT / "catalog/hardware.yaml").read_text())
    unknown = set(left_out) - set(data)
    if unknown:
        raise ValueError(f"no section {sorted(unknown)} in catalog/hardware.yaml to leave out")
    data = {section: value for section, value in data.items() if section not in left_out}

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


SUBMIT = "Hand in the finished design. This ends the conversation."
# can_run_code: what changes in submit_design's description and its line in the system prompt
SUBMIT_BUILDS_FIRST = ("Hand in the finished design. Every part is built first: if one doesn't build, you get its "
                       "error back to fix and call this again. A design whose parts all build ends the conversation. "
                       "Building uses run_python's shared code time; once that's used up, the design is handed in "
                       "without being built.")
SUBMIT_LINE = "- submit_design(...): hand in the finished design. This ends the conversation."
# can_test: the tool, and its line in the system prompt, just under measure's
PRINT_TEST = ("Optional. If you need to know whether something is going to work but you're not sure, ask the person to "
              "print a test of it before you hand in the final design, so you both save time and filament. They print "
              "it and tell you how each piece came out.")
PRINT_TEST_LINE = ("- print_test(params, parts): optional. If you need to know whether something is going to work but you're "
                   "not sure, ask the person to print a test of it before you hand in the final design, so you both save "
                   "time and filament. They print it and tell you how each piece came out.")
NO_SUPPORTS = "- Supports: none. Every part has to print without them."  # every condition since 2026-11-12, under the bridge line
MEASURE_LINE = "- measure(item, what): ask the person to measure one of their own things"
SUBMIT_LINE_BUILDS_FIRST = ("- submit_design(...): hand in the finished design. Every part is built first: if one doesn't "
                            "build, you get its error back to fix. A design whose parts all build ends the conversation.")


def _design_schema(assembly):
    """submit_design's parameters. `assembly` appears only for a task whose format.yaml asks for it,
    and is then required; every other task gets exactly the schema it had before the field existed."""
    design = _inline(Submission.model_json_schema())
    design["properties"].pop("task")  # the runner fills it in
    design["required"] = [r for r in design["required"] if r != "task"]
    field = design["properties"].pop("assembly")
    if assembly:
        schema = next(option for option in field["anyOf"] if option.get("type") == "object")
        design["properties"]["assembly"] = {**schema, "description": field["description"]}
        design["required"].append("assembly")
    return design


@cache
def tools(condition="can_ask", assembly=False):
    design = _design_schema(assembly)
    submit = SUBMIT_BUILDS_FIRST if condition == python_tool.CONDITION else SUBMIT

    def function_tool(name, description, parameters):
        return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}
    return [
        function_tool("measure", "Ask the person to measure one of their own things. They answer with what they measured, or say they can't.",
           {"type": "object", "properties": {
               "item": {"type": "string", "description": "What to measure, e.g. 'desk'"},
               "what": {"type": "string", "description": "Which dimension, e.g. 'thickness at the edge'"}},
            "required": ["item", "what"]}),
        function_tool("submit_design", submit, design),
        function_tool("report_limitation", "Say you wanted to use something (a technique, a tool, a part or material, a way of "
           "handing in the design) but couldn't because of what's available here. It changes nothing; it's noted.",
           {"type": "object", "properties": {
               "wanted": {"type": "string", "description": "What you wanted to use or do"},
               "blocked_by": {"type": "string", "description": "What stopped you, e.g. not in the hardware list, no such tool, the submission format"},
               "why": {"type": "string", "description": "Why you wanted it"}},
            "required": ["wanted", "blocked_by", "why"]}),
    ] + ([python_tool.spec()] if condition == python_tool.CONDITION else []) + (
        [function_tool("print_test", PRINT_TEST, test_print_schema(design))] if condition == TEST_CONDITION else [])


def test_print_schema(design):
    """print_test's parameters: the params and parts of submit_design's schema, nothing else."""
    return {"type": "object", "properties": {"params": design["properties"]["params"],
                                             "parts": {**design["properties"]["parts"], "description": "The test pieces to print"}},
            "required": ["params", "parts"]}


class NoDatasheet(ValueError):
    """can_ask_datasheet on a task with no datasheet in its format.yaml."""


def _image(page):
    return {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(page.read_bytes()).decode()}}


def first_message(task, condition, person):
    """The person's opening message: the request, with every measurement in all_given, and with the
    datasheet's pages as images in can_ask_datasheet."""
    if condition == "all_given" and person.things:
        return f"{task.request}\n\nMeasurements I took:\n{person.all_measurements()}"
    if condition == DATASHEET:
        if not task.format.datasheet:
            raise NoDatasheet(f"{task.id} has no datasheet for {DATASHEET}")
        line = task.format.datasheet_line
        text = f"{task.request}\n\n{line}" if line else task.request
        return [{"type": "text", "text": text}] + [_image(page) for page in task.format.datasheet]
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
TEST_PRINTED = "I printed the test pieces. Here's how they came out:"
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
    """The model's tools (three, and run_python where it can run code), and what its calls
    to them collect over one trial."""

    def __init__(self, task, person, python: PythonTool | None = None, can_test: bool = False):
        self.task = task
        self.person = person
        self.python = python
        self.can_test = can_test
        self.test_prints = []  # can_test: each print_test call that was printed, and what the person said
        self.limitations = []  # whatever the model passed to report_limitation
        self.repairs = 0  # submit_design calls sent back to be fixed
        self.sent_back_unbuilt = []  # can_run_code: per call sent back for a build error, the parts that didn't build
        self.accepted_unbuilt = []  # can_run_code: parts of the accepted design left unbuilt when code time ran out
        self.submission = None  # the valid design, once one is handed in

    def answer(self, call: llm.ToolCall) -> str:
        """Run one tool call; what the model is told."""
        tools_by_name = {"measure": self.measure, "report_limitation": self.report_limitation, "submit_design": self.submit_design}
        if self.python is not None:
            tools_by_name["run_python"] = self.run_python
        if self.can_test:
            tools_by_name["print_test"] = self.print_test
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

    def run_python(self, arguments):
        return self.python.run(str(arguments.get("code", "")))

    def print_test(self, arguments):
        """Print the test pieces and say how each came out: the same readings the person gives in the test-print
        loop (a pocket's fit, a seat's fit, a holed roof), from the recorded prints only, with no cause or fix."""
        from pbe.runner import coupon_loop  # it imports this module
        parts = [{**part, "role": "coupon"} if isinstance(part, dict) else part for part in arguments.get("parts") or []]
        try:
            pieces = Submission.model_validate({"task": self.task.id, "params": arguments.get("params") or {}, "parts": parts})
        except ValidationError as e:
            return f"I can't print that yet. Fix these and call print_test again:\n{e}"
        if not pieces.parts:
            return "There's nothing to print: send at least one part."
        with tempfile.TemporaryDirectory() as out:
            built = build_parts(pieces, Path(out) / "parts")
            report = coupon_loop.printed_parts_report(self.task, pieces, built)
        reply = TEST_PRINTED + "\n" + "\n".join(
            f"{part_id}:\n" + "\n".join(f"- {line.text}" for line in lines) for part_id, lines in report.items())
        self.test_prints.append({"params": arguments.get("params"), "parts": [part.id for part in pieces.parts],
                                 "reply": {part_id: [{"text": line.text, "basis": line.basis} for line in lines]
                                           for part_id, lines in report.items()}})
        return reply

    def report_limitation(self, arguments):
        self.limitations.append(arguments)
        return "Noted. Continue with what you have."

    def _own_parts_missing(self, submission) -> list[str]:
        """The person's own parts (format.yaml) a design for an assembly task doesn't list in its hardware."""
        if not self.task.format.assembly:
            return []
        listed = {item.ref for item in submission.hardware}
        return [f"own:{part.id}" for part in self.task.format.own_hardware
                if part.kind != "screw" and f"own:{part.id}" not in listed]

    def submit_design(self, arguments):
        if not self.task.format.assembly:
            # not in this task's schema: ignored, as any unknown field was before `assembly` existed
            arguments = {key: value for key, value in arguments.items() if key != "assembly"}
        try:
            submission = Submission.model_validate({**arguments, "task": self.task.id})
        except ValidationError as e:
            self.repairs += 1
            return f"That isn't a valid submission. Fix these and call submit_design again:\n{e}"
        if self.task.format.assembly and submission.assembly is None:
            self.repairs += 1
            return "That isn't a valid submission. Fix this and call submit_design again:\nassembly is required for this design."
        if missing := self._own_parts_missing(submission):
            self.repairs += 1  # DeepSeek left them out twice in pilot-estoa, so no check could read where they went
            return ("That isn't a valid submission. Fix this and call submit_design again:\n"
                    f"hardware has to list the person's own parts, and assembly has to place them: {', '.join(missing)} missing.")
        if self.python is not None:
            built = build_on_submit.build(self.python, submission)
            if built.errors:
                self.repairs += 1
                self.sent_back_unbuilt.append(list(built.errors))
                return build_on_submit.sent_back(built.errors)
            self.accepted_unbuilt = built.unbuilt
        self.submission = submission
        return "Received."

    def build_record(self, error) -> BuildOnSubmit | None:
        """can_run_code only: what building on submit sent back, and whether turns ran out while fixing it."""
        if self.python is None:
            return None
        still_fixing = bool(self.sent_back_unbuilt) and self.submission is None and error is None
        return BuildOnSubmit(sent_back=self.sent_back_unbuilt, out_of_turns_while_fixing=still_fixing,
                             accepted_unbuilt=self.accepted_unbuilt)


OWN_PARTS = """
## Their own parts
The person has these too, for this design only. Refer to each by its reference, such as "own:{first}". What isn't listed hasn't been measured: ask them.

```yaml
{parts}```
"""
ASSEMBLY_RULE = ("- Say where each final part and each of their own parts with a frame goes in the finished piece, and where "
                 "each screw goes, in `assembly`.")


def own_parts_text(task_format: TaskFormat) -> str:
    listed = [{"ref": f"own:{part.id}", **part.model_dump(exclude={"id"}, exclude_none=True)} for part in task_format.own_hardware]
    return yaml.safe_dump(listed, sort_keys=False, allow_unicode=True, width=1000)


def _with_task_format(text, task_format: TaskFormat | None):
    """The prompt with what the task's format.yaml adds. A task without one gets the prompt unchanged."""
    if task_format is None:
        return text
    if task_format.own_hardware:
        before_how_to_work = "\n## How to work"
        assert text.count(before_how_to_work) == 1
        section = OWN_PARTS.format(first=task_format.own_hardware[0].id, parts=own_parts_text(task_format))
        text = text.replace(before_how_to_work, section + before_how_to_work)
    if task_format.assembly:
        text = f"{text}\n{ASSEMBLY_RULE}"
    return text


def _below_line(text, line_start, new_line):
    """The text with new_line added just below the line that starts with line_start."""
    end = text.index("\n", text.index(line_start))
    return text[:end + 1] + new_line + "\n" + text[end + 1:]


def system_prompt(max_turns, python: PythonTool | None = None, task_format: TaskFormat | None = None, can_test=False):
    left_out = task_format.hardware_left_out if task_format else ()
    text = SYSTEM.format(setup=setup_text(), hardware=hardware_text(left_out), max_turns=max_turns)
    text = _with_task_format(text, task_format)
    text = _below_line(text, "- Longest bridge seen to print cleanly", NO_SUPPORTS)  # every condition since 2026-11-12
    if can_test:
        text = _below_line(text, MEASURE_LINE, PRINT_TEST_LINE)
    if python is None:
        return text
    assert text.count(SUBMIT_LINE) == 1
    text = text.replace(SUBMIT_LINE, SUBMIT_LINE_BUILDS_FIRST)
    before_turns = "\nYou have at most "  # run_python joins the list of tools, just above this line
    assert text.count(before_turns) == 1
    return text.replace(before_turns, f"\n{python.prompt_line()}{before_turns}")


def opening_messages(task, condition, person, max_turns, python: PythonTool | None = None):
    system = system_prompt(max_turns, python, task.format, can_test=condition == TEST_CONDITION)
    return [{"role": "system", "content": system}, {"role": "user", "content": first_message(task, condition, person)}]


def code_tool(task, condition, workdir) -> PythonTool | None:
    """run_python for a condition that has it. Raises before the trial if there's no safe sandbox."""
    if condition != python_tool.CONDITION:
        return None
    return PythonTool.for_trial(task.id, workdir)


def trial_settings(model, max_turns, max_tokens, python: PythonTool | None) -> Settings:
    code_settings = python.settings if python is not None else None
    return Settings(max_turns=max_turns, max_tokens=max_tokens, temperature="provider default", run_python=code_settings,
                    prompt_caching=llm.requests_caching(model))


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


def run_trial(task, model, condition="can_ask", max_turns=8, max_tokens=32000, chat=llm.chat, workdir=None):
    """Returns (record, messages, submission or None). Infrastructure errors end the trial
    with outcome "error", counted apart from the model's own failures. `workdir` is
    run_python's working folder, in the condition that has it."""
    person = Person(task.hidden_facts)
    python = code_tool(task, condition, workdir)
    trial_tools = TrialTools(task, person, python, can_test=condition == TEST_CONDITION)
    messages = opening_messages(task, condition, person, max_turns, python)
    calls, error = [], None
    started = time.monotonic()
    for _ in range(max_turns):
        try:
            response = chat(model, messages, tools=tools(condition, task.format.assembly), max_tokens=max_tokens,
                            **llm.caching_params(model))
        except llm.LLMError as e:
            error = str(e)
            break
        reply = llm.Reply.model_validate(response)
        calls.append(ModelCall.from_reply(reply))
        messages.append(as_sent_back(reply.message))
        try:
            messages += answers_to(reply, trial_tools)
        except build_on_submit.BuildUnavailable as e:
            error = f"building on submit: {e}"
            break
        if trial_tools.submission is not None:
            break
    record = TrialRecord(
        task=task.id, model=model, condition=condition, outcome=outcome_of(error, trial_tools.submission), error=error,
        turns=len(calls), repairs=trial_tools.repairs, build_on_submit=trial_tools.build_record(error), measures=person.log, revealed=person.revealed,
        hidden=[f"{thing}.{measurement}" for thing, measurement in person.every_measurement()],
        limitations=trial_tools.limitations, cost_usd=round(sum(call.cost_usd for call in calls), 6),
        elapsed_s=round(time.monotonic() - started, 1),
        settings=trial_settings(model, max_turns, max_tokens, python),
        calls=calls, test_prints=trial_tools.test_prints,
    )
    return record, messages, trial_tools.submission


def asked_test_prints(task_id, messages) -> list[Submission]:
    """can_test: the test pieces the model asked the person to print, one design per print_test call that the person
    printed (a call sent back to fix isn't one), from a saved transcript. For slicing what the trial printed."""
    replies = {message.get("tool_call_id"): message.get("content", "") for message in messages if message.get("role") == "tool"}
    pieces = []
    for message in messages:
        for call in message.get("tool_calls") or []:
            if call["function"]["name"] != "print_test" or not replies.get(call["id"], "").startswith(TEST_PRINTED):
                continue
            arguments = json.loads(call["function"]["arguments"] or "{}")
            parts = [{**part, "role": "coupon"} for part in arguments.get("parts") or []]
            pieces.append(Submission.model_validate({"task": task_id, "params": arguments.get("params") or {}, "parts": parts}))
    return pieces


def graded_design(condition, sub):
    """The design the checks grade. In can_test the person has printed whatever tests the model asked for, so the
    final design is graded without any test pieces it still lists: it has to land on a size that worked, as a
    second turn in the test-print loop does (coupon_loop.without_coupons)."""
    if condition != TEST_CONDITION:
        return sub
    return sub.model_copy(update={"parts": [part for part in sub.parts if part.role != "coupon"]})
