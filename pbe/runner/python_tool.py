"""run_python: the tool that lets a model run code during a trial, in the can_run_code condition.

The code runs in pbe.runner.code_sandbox, in a working folder of its own that starts with
the task's provided files (tasks/<family>/files/, if the task has any) and keeps whatever
earlier calls wrote. The reply is what the code printed, its errors, and the names of
files it wrote: never a check's verdict, and nothing of the checks, which the sandbox
can't see.
"""
import math
import os
import shutil
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from pbe.runner import code_sandbox
from pbe.runner.code_sandbox import Limits, Ran
from pbe.runner.trial_record import CodeSettings

ROOT = Path(__file__).resolve().parents[2]
CONDITION = "can_run_code"
PROVIDED = "files"  # tasks/<family>/files/: what a task hands the model's code. Nothing hidden goes here.
MAX_LISTED = 40  # file names in one reply

DESCRIPTION = (
    "Run Python and see what it prints. CadQuery (import cadquery as cq), trimesh, NumPy and OpenCV (cv2) are "
    "installed; nothing else can be installed, and there's no network. The code runs in a working folder that "
    "holds the files you were given and whatever earlier calls wrote. Each call is a new process, so keep what "
    "you need in files. To try a part, run its code and call build(p) yourself, with p = types.SimpleNamespace(...). "
    "Returns what the code printed, its errors and the names of files it wrote. A call stops after {timeout_s} s "
    "or once the folder holds more than {workspace_mb} MB or {workspace_files} files, all calls in the trial share "
    "{trial_s} s, and output past {output_chars} characters is cut."
)


def spec(limits=Limits()):
    description = DESCRIPTION.format(timeout_s=limits.timeout_s, output_chars=limits.output_chars, trial_s=limits.trial_s,
                                     workspace_mb=limits.workspace_mb, workspace_files=limits.workspace_files)
    parameters = {"type": "object", "properties": {
        "code": {"type": "string", "description": "The Python to run, as a whole script"}},
        "required": ["code"]}
    return {"type": "function", "function": {"name": "run_python", "description": description, "parameters": parameters}}


def provided_files(task_id) -> Path:
    family = task_id.split("/")[0]
    return ROOT / "tasks" / family / PROVIDED


def _fresh_workdir(task_id, workdir) -> Path:
    """An empty working folder holding only the task's provided files."""
    workdir = Path(workdir or tempfile.mkdtemp(prefix="pbe-run-python-"))
    if workdir.exists():  # left by an attempt that ended in an infrastructure error, or the empty temp folder
        shutil.rmtree(workdir)
    provided = provided_files(task_id)
    if provided.is_dir():
        shutil.copytree(provided, workdir, symlinks=False)
    else:
        workdir.mkdir(parents=True)
    return workdir


class PythonTool:
    def __init__(self, sandbox, workdir: Path, limits=Limits()):
        self.sandbox = sandbox
        self.workdir = Path(workdir).resolve()
        self.limits = limits
        self.seconds_used = 0.0  # by every call so far, against limits.trial_s

    @classmethod
    def for_trial(cls, task_id, workdir=None, limits=Limits()):
        """A fresh working folder holding the task's provided files. Raises SandboxUnavailable
        before the trial starts if there's nowhere safe to run code."""
        sandbox = code_sandbox.find()
        return cls(sandbox, _fresh_workdir(task_id, workdir), limits)

    @property
    def settings(self) -> CodeSettings:
        return CodeSettings(sandbox=self.sandbox.describe(), timeout_s=self.limits.timeout_s,
                            trial_s=self.limits.trial_s, output_chars=self.limits.output_chars)

    def spec(self):
        return spec(self.limits)

    def prompt_line(self) -> str:
        names = sorted(_files(self.workdir))
        given = f" Files you're given: {', '.join(names)}." if names else ""
        return (f"- run_python(code): run Python in a working folder of its own, with CadQuery, trimesh, NumPy and "
                f"OpenCV installed, and see what it prints and any errors.{given}")

    def seconds_left(self) -> int:
        """What's left of the trial's code time, which building on submit draws on too."""
        return max(0, math.floor(self.limits.trial_s - self.seconds_used))

    def _this_call(self) -> Limits | None:
        """The limits for the next call: its timeout is what's left of the trial's code time, if
        that's less. None once it's used up."""
        left = self.seconds_left()
        if left < 1:
            return None
        return replace(self.limits, timeout_s=min(self.limits.timeout_s, left))

    def run(self, code: str) -> str:
        this_call = self._this_call()
        if this_call is None:
            return f"Not run: this trial's {self.limits.trial_s} s of code time is used up."
        before = _files(self.workdir)
        started = time.monotonic()
        ran = code_sandbox.run(self.sandbox, code, self.workdir, this_call)
        self.seconds_used += time.monotonic() - started
        after = _files(self.workdir)
        written = sorted(name for name, stamp in after.items() if before.get(name) != stamp)
        return reply(ran, written)


def _files(folder: Path) -> dict[str, tuple[int, int]]:
    """Every file under the folder, by relative name, with its size and modification time.
    Links aren't followed: one could point anywhere on this machine."""
    found = {}
    for here, _, names in os.walk(folder, followlinks=False):
        for name in names:
            path = Path(here) / name
            stat = path.lstat()
            found[str(path.relative_to(folder))] = (stat.st_size, stat.st_mtime_ns)
    return found


def _listed(written: list[str]) -> str:
    shown = ", ".join(written[:MAX_LISTED])
    more = len(written) - MAX_LISTED
    return f"{shown}, and {more} more" if more > 0 else shown


def reply(ran: Ran, written: list[str]) -> str:
    """What the model is told about one run."""
    if ran.stopped:
        lines = [f"Stopped: {ran.stopped}."]
    else:
        lines = [f"Exit code {ran.exit_code}."]
    if ran.stdout:
        lines.append(f"stdout:\n{ran.stdout}")
    if ran.stderr:
        lines.append(f"stderr:\n{ran.stderr}")
    if not (ran.stdout or ran.stderr):
        lines.append("It printed nothing.")
    if written:
        lines.append(f"Files written: {_listed(written)}")
    return "\n".join(lines)
