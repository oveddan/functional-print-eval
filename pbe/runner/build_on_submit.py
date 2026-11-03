"""In can_run_code, submit_design builds every part before it accepts a design, so a model
that hands in code that doesn't build hears about it and can fix it (issue 26).

The error text goes back to the model and its provider, so the parts are built in
run_python's sandbox (pbe.runner.code_sandbox), never in pbe.parts.build's: that one can
read files anywhere on macOS, so part code could read the task's hidden facts and put them
in an exception message. Each part builds in a folder holding only its own code and the
params, as grading builds it, so a part can't lean on files the model wrote with
run_python. Nothing comes back but whether each part built and, if not, its error: no
check, measurement or anything else from the graders. A part that builds gets no comment.

Building draws on the trial's code time, which run_python's calls share (Limits.trial_s),
so a submission with many slow parts, or many submissions in one reply, can't hold a worker
for longer than that. Once it's used up, the parts still to build aren't built: if no part
built so far has an error, the design is accepted as it would be in the other conditions,
and grading builds it.

Grading builds the parts again itself, with pbe.parts.build, so this build can't change a
verdict. The two differ only where their sandboxes do: here a part has run_python's
limits (memory_mb, file_mb, tmp_mb), and grading has none of those.
"""
import json
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from pbe.parts.submission import Submission
from pbe.runner import code_sandbox
from pbe.runner.code_sandbox import Limits
from pbe.runner.python_tool import PythonTool

SPEC = "part.json"
MESH = "part.stl"
TIMEOUT_S = 120  # one part, the same as grading's build
ERROR_CHARS = 2000  # of one part's error: a traceback's end says what went wrong

# runs in the sandbox, as run_python's code does: build(p) as grading's runner calls it, the
# traceback without this script's own frame, so it starts in the part's code. The mesh is read
# back here too, as grading reads it, so that also stays inside the sandbox's limits and time
BUILD = r"""
import json, sys, traceback, types
import cadquery as cq
spec = json.load(open("part.json"))
p = types.SimpleNamespace(**spec["params"])
ns = {"cq": cq}
try:
    exec(compile(spec["code"], spec["part"], "exec"), ns)
    if not callable(ns.get("build")):
        sys.exit("The code doesn't define build(p).")
    cq.exporters.export(ns["build"](p), "part.stl", tolerance=0.01, angularTolerance=0.1)
except Exception as error:
    traceback.print_exception(type(error), error, error.__traceback__.tb_next)
    sys.exit(1)
import trimesh
try:
    trimesh.load("part.stl", force="mesh")
except Exception as error:  # a shape can export as something trimesh can't read
    sys.exit(f"It exported, but the mesh can't be read ({type(error).__name__}).")
"""


class BuildUnavailable(RuntimeError):
    """The sandbox couldn't start, so nothing was built: an infrastructure error, not the model's."""


@dataclass
class Built:
    errors: dict[str, str] = field(default_factory=dict)  # each part that didn't build, by id, with its error
    unbuilt: list[str] = field(default_factory=list)  # parts not built because the trial's code time ran out


def _limits(timeout_s) -> Limits:
    # each stream gets half of output_chars: the error is stderr
    return replace(Limits(), timeout_s=timeout_s, output_chars=2 * ERROR_CHARS)


def _why_not(ran: code_sandbox.Ran, folder: Path) -> str | None:
    """Why one part didn't build, or None if it did."""
    if ran.stopped and ran.stopped.startswith(code_sandbox.COULD_NOT_START):
        raise BuildUnavailable(ran.stopped)
    if ran.stopped:
        return f"Stopped: {ran.stopped}."
    if ran.exit_code != 0:
        return ran.stderr.strip() or f"It ended with exit code {ran.exit_code} and no error."
    if not (folder / MESH).exists():  # the code ended the build early, e.g. with sys.exit(0)
        return "build(p) ran, but nothing was exported."
    return None  # the sandbox read the mesh back


def _build_one(python: PythonTool, part, params, timeout_s) -> tuple[code_sandbox.Ran, str | None]:
    """Run one part's build in a folder of its own, charged to the trial's code time: (what ran, why it didn't build or None)."""
    with tempfile.TemporaryDirectory(prefix="pbe-build-on-submit-") as scratch:
        folder = Path(scratch)
        (folder / SPEC).write_text(json.dumps({"params": params, "code": part.code, "part": part.id}))
        started = time.monotonic()
        ran = code_sandbox.run(python.sandbox, BUILD, folder, _limits(timeout_s))
        python.seconds_used += time.monotonic() - started
        return ran, _why_not(ran, folder)


def build(python: PythonTool, sub: Submission) -> Built:
    """Build every part in run_python's sandbox, within what's left of the trial's code time.
    Raises BuildUnavailable if the sandbox couldn't start."""
    params = {name: param.value for name, param in sub.params.items()}
    built = Built()
    for part in sub.parts:
        timeout_s = min(TIMEOUT_S, python.seconds_left())
        if timeout_s < 1:
            built.unbuilt.append(part.id)
            continue
        ran, why = _build_one(python, part, params, timeout_s)
        if timeout_s < TIMEOUT_S and ran.stopped == code_sandbox.ran_too_long(timeout_s):
            built.unbuilt.append(part.id)  # cut short by the trial's code time, not by grading's limit
        elif why:
            built.errors[part.id] = why
    return built


def sent_back(errors: dict[str, str]) -> str:
    """What the model is told when a part doesn't build."""
    parts = "\n\n".join(f"Part {part_id}:\n{error}" for part_id, error in errors.items())
    return (f"Not handed in: {len(errors)} part{'s' if len(errors) > 1 else ''} didn't build. "
            f"Fix {'them' if len(errors) > 1 else 'it'} and call submit_design again.\n\n{parts}")
