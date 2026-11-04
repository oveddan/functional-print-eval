"""A kernel-enforced cap on how many tasks (processes and threads) run_python's code can start
under bwrap, which, unlike a container, has no cgroup of its own.

Two ways, because the kernel offers different ones to different users:
- Not root: RLIMIT_NPROC, set to the tasks this user already has plus the budget. The kernel
  counts threads as well as processes, and checks the limit at every fork and thread start.
- Root: the kernel doesn't apply RLIMIT_NPROC to root, so a pids cgroup of its own, joined
  before bwrap starts (in the child, before exec, so nothing escapes it). cgroup v2 where
  it's mounted with the pids controller, else v1's pids hierarchy.

If neither works, there's no cap, and code_sandbox refuses bwrap rather than run without one.
"""
import os
import resource
import time
from pathlib import Path

CGROUP_ROOT = Path("/sys/fs/cgroup")
# what bwrap itself runs besides the code: bwrap, the PID namespace's init, and the interpreter
BWRAP_OWN_TASKS = 3


def running_as_root() -> bool:
    return os.geteuid() == 0


def _pids_hierarchy() -> Path | None:
    """Where root can make a pids cgroup: the cgroup v2 root if it offers the pids controller,
    else the v1 pids hierarchy. None if neither is mounted and writable."""
    controllers = CGROUP_ROOT / "cgroup.controllers"
    if controllers.exists() and "pids" in controllers.read_text().split():
        return CGROUP_ROOT if os.access(CGROUP_ROOT, os.W_OK) else None
    v1 = CGROUP_ROOT / "pids"
    if (v1 / "cgroup.procs").exists() and os.access(v1, os.W_OK):
        return v1
    return None


def problem() -> str | None:
    """Why tasks can't be capped here, or None."""
    if running_as_root() and _pids_hierarchy() is None:
        return "running as root with no writable pids cgroup, so nothing could cap the code's processes and threads"
    return None


def tasks_owned_by(uid: int) -> int:
    """The tasks (threads included) whose real user is `uid`: what RLIMIT_NPROC counts."""
    total = 0
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        try:
            status = Path(entry.path, "status").read_text()
        except OSError:
            continue  # it ended while counting
        fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
        if int(fields["Uid"].split()[0]) == uid:
            total += int(fields["Threads"])
    return total


class TaskLimit:
    """One run's cap: made before the run, applied in the child before exec, removed after."""

    def __init__(self, run_id: str, max_tasks: int):
        self.max_tasks = max_tasks + BWRAP_OWN_TASKS
        self.cgroup = None
        if running_as_root():
            self.cgroup = _pids_hierarchy() / run_id
            if _pids_hierarchy() == CGROUP_ROOT:  # v2: the controller has to be on for the root's children
                (CGROUP_ROOT / "cgroup.subtree_control").write_text("+pids")
            self.cgroup.mkdir()
            (self.cgroup / "pids.max").write_text(str(self.max_tasks))
        else:
            self.nproc = tasks_owned_by(os.getuid()) + self.max_tasks

    def apply_in_child(self) -> None:
        """Runs in the child between fork and exec, so bwrap and everything it starts is capped."""
        if self.cgroup is not None:
            (self.cgroup / "cgroup.procs").write_text(str(os.getpid()))
        else:
            resource.setrlimit(resource.RLIMIT_NPROC, (self.nproc, self.nproc))

    def remove(self, wait_s: float = 5.0) -> None:
        """Remove the cgroup once its tasks are gone. When bwrap ends, the kernel kills what's
        left in its PID namespace, but not instantly."""
        if self.cgroup is None:
            return
        deadline = time.monotonic() + wait_s
        while (self.cgroup / "cgroup.procs").read_text().strip() and time.monotonic() < deadline:
            time.sleep(0.05)
        try:
            self.cgroup.rmdir()
        except OSError:
            pass  # still busy after the wait; an empty cgroup left behind costs nothing
