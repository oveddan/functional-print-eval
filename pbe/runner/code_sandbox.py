"""Run Python a model wrote, in a sandbox that sees only one folder.

What run_python's code prints goes back to the model and on to its provider, so the code
must not be able to read anything a model shouldn't see: the task's hidden facts and
reference, pbe/ (the checks), other trials' results, the user's home folder or any
credential. It also gets no network and none of this process's environment.

Two sandboxes, tried in this order unless PBE_CODE_SANDBOX names one:
- `container`: Docker (or PBE_CONTAINER_ENGINE, e.g. podman) running the image from
  docker/run-python.Dockerfile, with --network none, a read-only root, no capabilities,
  and the trial's folder mounted at /work. The image holds the libraries and nothing
  of this repository. Works on macOS and Linux.
- `bwrap`: bubblewrap on Linux. A new mount namespace holding only /usr, the Python
  install, the project's site-packages (read-only), a few files from /etc that the
  libraries load, an empty /tmp, and the trial's folder at /work; new network, PID,
  IPC and user namespaces, running as nobody.

If neither works, nothing runs: there's no weaker fallback, and PBE_NO_SANDBOX doesn't
apply. That variable is for building parts after the conversation is over, when nothing
the code reads gets back to the model; here even a throwaway container would let the
code read the hidden facts in this repository.

Resources are capped by the kernel in both, since model code can loop by mistake as easily
as on purpose. The container has cgroups: --pids-limit and --memory cap tasks and memory in
all. bwrap has none, so it gets the same totals another way: a seccomp filter lets the code
start threads but no other process (pbe/runner/no_new_processes.py), so its one process's
RLIMIT_AS caps memory in all; and pbe/runner/task_limit.py caps its threads. In both, each
file is capped by RLIMIT_FSIZE, /tmp by its tmpfs size, and the working folder, a bind mount
the kernel can't cap, by watching its size and entries while the code runs. The code also
runs under an audit hook that refuses to start processes, for a readable error; ctypes could
get past the hook, but not past the kernel.
"""
import hashlib
import os
import resource
import shutil
import signal
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pbe.runner import no_new_processes, task_limit
from pbe.runner.task_limit import TaskLimit

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "pbe-run-python"
WORK = "/work"  # the trial's folder, as the code sees it
SITE = "/opt/site-packages"  # bwrap only: the project's libraries, read-only
BUILD_IMAGE = "build it with scripts/build_run_python_image.sh"

# the code's whole environment, the same in either sandbox
ENVIRONMENT = {"HOME": "/tmp", "TMPDIR": "/tmp", "MPLCONFIGDIR": "/tmp", "LANG": "C.UTF-8",
               "PATH": "/usr/local/bin:/usr/bin:/bin",
               # thread pools the same size on every machine, well inside the task cap
               "OMP_NUM_THREADS": "4", "OPENBLAS_NUM_THREADS": "4", "MKL_NUM_THREADS": "4", "NUMEXPR_MAX_THREADS": "4"}

# what bwrap mounts from /etc: what the dynamic loader and fontconfig read, and nothing else
ETC_FILES = ["/etc/ld.so.cache", "/etc/ld.so.conf", "/etc/ld.so.conf.d", "/etc/fonts", "/etc/alternatives", "/etc/localtime"]

# runs inside the sandbox: reads the model's code on stdin and runs it as __main__
WRAPPER = r"""
import sys
if len(sys.argv) > 1:
    import site
    site.addsitedir(sys.argv[1])
REFUSED = ("subprocess.Popen", "os.system", "os.fork", "os.forkpty", "os.posix_spawn", "os.spawn", "os.exec", "pty.spawn")
def refuse(event, args):
    if event.startswith(REFUSED):
        raise PermissionError(f"{event}: starting another process isn't allowed here")
code = sys.stdin.read()
sys.stdin = open("/dev/null")
sys.argv = ["main.py"]
sys.addaudithook(refuse)
import traceback
try:
    exec(compile(code, "main.py", "exec"), {"__name__": "__main__"})
except SystemExit:
    raise
except BaseException as error:
    traceback.print_exception(type(error), error, error.__traceback__.tb_next)  # without this wrapper's frame
    sys.exit(1)
"""


COULD_NOT_START = "the sandbox couldn't start"  # Ran.stopped begins with this when nothing ran


def ran_too_long(timeout_s) -> str:
    """Ran.stopped when the code reached its timeout."""
    return f"it ran longer than {timeout_s} s"


class SandboxUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Limits:
    timeout_s: int = 120  # one call, the same as building a part
    trial_s: int = 1200  # every call in a trial together: a reply can hold several calls
    output_chars: int = 8000  # per call, stdout and stderr together
    file_mb: int = 256  # the largest file the code can write
    workspace_mb: int = 1024  # the working folder in all, which stays between calls
    workspace_files: int = 10_000
    tmp_mb: int = 512  # /tmp, which is memory and is emptied after each call
    memory_mb: int = 4096
    processes: int = 256  # tasks the code can start, threads included


@dataclass(frozen=True)
class Ran:
    exit_code: int | None  # None if it was stopped
    stdout: str
    stderr: str
    stopped: str | None = None  # why it was stopped or never started, e.g. "it ran longer than 120 s"


def uv_lock_sha256():
    return hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest()


class Container:
    name = "container"

    def __init__(self, engine=None, image=IMAGE):
        self.engine = engine or os.environ.get("PBE_CONTAINER_ENGINE", "docker")
        self.image = image

    def _inspect_image(self, field):
        """One field of the image, or None if there's no such image."""
        inspected = subprocess.run([self.engine, "image", "inspect", self.image, "--format", field],
                                   capture_output=True, text=True)
        return inspected.stdout.strip() if inspected.returncode == 0 else None

    def problem(self) -> str | None:
        """Why this sandbox can't run code here, or None if it can."""
        if not shutil.which(self.engine):
            return f"no `{self.engine}` command"
        if subprocess.run([self.engine, "info"], capture_output=True).returncode != 0:
            return f"`{self.engine} info` failed: is the daemon running?"
        built_from = self._inspect_image('{{index .Config.Labels "pbe.uv_lock_sha256"}}')
        if built_from is None:
            return f"no image {self.image}: {BUILD_IMAGE}"
        if built_from != uv_lock_sha256():
            return f"image {self.image} was built from a different uv.lock: {BUILD_IMAGE} again"
        return None

    def describe(self) -> str:
        return f"{self.engine} image {self.image} {self._inspect_image('{{.Id}}')}"

    def prepare(self, workdir: Path, limits: Limits, run_id: str) -> str | None:
        """Create the container before anything runs in it, so stop() always finds it: a
        `docker run` stopped while the daemon was still creating its container leaves one running
        with nobody attached. Why it couldn't be created, or None."""
        created = subprocess.run(self._create_command(workdir, limits, run_id), capture_output=True, text=True,
                                 env=self.client_environment())
        return None if created.returncode == 0 else created.stderr.strip() or "couldn't create the container"

    def _create_command(self, workdir: Path, limits: Limits, run_id: str) -> list[str]:
        locked_down = [
            "--network", "none", "--read-only", "--tmpfs", f"/tmp:rw,size={limits.tmp_mb}m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--user", f"{os.getuid()}:{os.getgid()}",  # so it can write the mounted folder, and nothing else
            "--pids-limit", str(limits.processes), "--memory", f"{limits.memory_mb}m",
            "--ulimit", f"fsize={limits.file_mb * 2**20}",
        ]
        environment = [f"{name}={value}" for name, value in ENVIRONMENT.items()]
        return [
            self.engine, "create", "--rm", "-i", "--name", run_id, *locked_down,
            "--volume", f"{workdir}:{WORK}:rw", "--workdir", WORK,
            self.image, "env", "-i", *environment, "python", "-I", "-c", WRAPPER,
        ]

    def command(self, workdir: Path, limits: Limits, run_id: str) -> list[str]:
        return [self.engine, "start", "--attach", "--interactive", run_id]

    def in_child(self, limits: Limits, run_id: str):
        return None  # the container's limits are set by `docker create`

    def kept_open(self, run_id: str) -> list[int]:
        return []

    def cleanup(self, run_id: str) -> None:
        pass  # --rm, or stop()'s `rm --force`

    def stop(self, run_id: str) -> None:
        """Killing the `docker start` client leaves the container running; removing it doesn't."""
        subprocess.run([self.engine, "rm", "--force", run_id], capture_output=True, env=self.client_environment())

    def client_environment(self) -> dict:
        """The docker command's own, to find its daemon (Docker Desktop keeps that under HOME).
        The container gets none of it: only what `env -i` sets."""
        return dict(os.environ)


class Bubblewrap:
    name = "bwrap"

    def problem(self) -> str | None:
        if not sys.platform.startswith("linux"):
            return "bubblewrap is Linux only"
        if not shutil.which("bwrap"):
            return "no `bwrap` command"
        if (_site_packages() / "pbe").exists():
            return "pbe is installed in site-packages, which the jail mounts: install the project editable (uv sync)"
        if no_new_processes.machine() is None:
            return f"no seccomp filter written for this machine ({', '.join(no_new_processes.MACHINES)} only)"
        if cannot_cap := task_limit.problem():
            return cannot_cap
        return _bwrap_problem()

    def __init__(self):
        self._task_limits = {}
        self._seccomp_fds = {}

    def prepare(self, workdir: Path, limits: Limits, run_id: str) -> str | None:
        self._task_limits[run_id] = TaskLimit(run_id, limits.processes)
        self._seccomp_fds[run_id] = _seccomp_program_fd()
        return None

    def describe(self) -> str:
        version = subprocess.run(["bwrap", "--version"], capture_output=True, text=True)
        return version.stdout.strip() or "bwrap"

    def command(self, workdir: Path, limits: Limits, run_id: str) -> list[str]:
        seccomp = ["--seccomp", str(self._seccomp_fds[run_id])]
        return [*_bwrap_jail(workdir, limits), *seccomp, _python(), "-I", "-c", WRAPPER, SITE]

    def in_child(self, limits: Limits, run_id: str):
        """Caps applied between fork and exec, so bwrap and everything it starts is under them."""
        tasks = self._task_limits[run_id]

        def apply():
            memory = limits.memory_mb * 2**20
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
            tasks.apply_in_child()
        return apply

    def kept_open(self, run_id: str) -> list[int]:
        """The file descriptors bwrap has to inherit: the seccomp program it reads."""
        return [self._seccomp_fds[run_id]]

    def cleanup(self, run_id: str) -> None:
        self._task_limits.pop(run_id).remove()
        os.close(self._seccomp_fds.pop(run_id))

    def stop(self, run_id: str) -> None:
        pass  # --die-with-parent: killing bwrap ends everything inside

    def client_environment(self) -> dict:
        return {"PATH": os.environ.get("PATH", "")}  # and --clearenv inside


def _seccomp_program_fd() -> int:
    """A pipe's read end holding the filter, for bwrap's --seccomp, which reads it to the end."""
    read_end, write_end = os.pipe()
    with os.fdopen(write_end, "wb") as pipe:
        pipe.write(no_new_processes.program(no_new_processes.machine()))
    return read_end


def _site_packages() -> Path:
    return Path(sysconfig.get_paths()["purelib"]).resolve()


def _python():
    """The interpreter itself, not the venv's link to it: the venv's folder isn't in the jail."""
    version = sys.version_info
    return str(Path(sys.base_prefix).resolve() / "bin" / f"python{version.major}.{version.minor}")


def _top_level_links():
    """/bin, /lib, /lib64 and /sbin as the host has them: links into /usr on most distributions."""
    args = []
    for name in ("bin", "lib", "lib64", "sbin"):
        path = Path("/") / name
        if path.is_symlink():
            args += ["--symlink", os.readlink(path), str(path)]
        elif path.is_dir():
            args += ["--ro-bind", str(path), str(path)]
    return args


def _bwrap_jail(workdir: Path, limits: Limits) -> list[str]:
    python_install = str(Path(sys.base_prefix).resolve())
    environment = [arg for name, value in ENVIRONMENT.items() for arg in ("--setenv", name, value)]
    etc = [arg for path in ETC_FILES for arg in ("--ro-bind-try", path, path)]
    return [
        "bwrap", "--unshare-all", "--unshare-user", "--uid", "65534", "--gid", "65534",
        "--die-with-parent", "--new-session", "--clearenv", *environment,
        "--ro-bind", "/usr", "/usr", *_top_level_links(), *etc,
        "--ro-bind", python_install, python_install,
        "--ro-bind", str(_site_packages()), SITE,
        "--proc", "/proc", "--dev", "/dev", "--size", str(limits.tmp_mb * 2**20), "--tmpfs", "/tmp",
        "--bind", str(workdir), WORK, "--chdir", WORK,
        "--remount-ro", "/",  # the jail's own root, so only /work and /tmp take writes
    ]


@cache
def _bwrap_problem() -> str | None:
    """A kernel or VM can refuse the namespaces; better to know before a trial than in every reply."""
    seccomp_fd = _seccomp_program_fd()
    with tempfile.TemporaryDirectory() as empty:
        command = [*_bwrap_jail(Path(empty), Limits()), "--seccomp", str(seccomp_fd), _python(), "-I", "-c", "pass"]
        probe = subprocess.run(command, capture_output=True, text=True, pass_fds=[seccomp_fd])
    os.close(seccomp_fd)
    if probe.returncode == 0:
        return None
    return f"bwrap couldn't start Python: {probe.stderr.strip()[-300:]}"


SANDBOXES = {"container": Container, "bwrap": Bubblewrap}


def find():
    """The sandbox to run code in. Raises SandboxUnavailable, never falls back to less."""
    chosen = os.environ.get("PBE_CODE_SANDBOX")
    if chosen and chosen not in SANDBOXES:
        raise SandboxUnavailable(f"PBE_CODE_SANDBOX={chosen}: expected one of {', '.join(SANDBOXES)}")
    problems = []
    for name in [chosen] if chosen else SANDBOXES:
        sandbox = SANDBOXES[name]()
        problem = sandbox.problem()
        if problem is None:
            return sandbox
        problems.append(f"{name}: {problem}")
    raise SandboxUnavailable("run_python needs a sandbox that hides this repository, and none works here ("
                             + "; ".join(problems) + "). PBE_NO_SANDBOX doesn't apply to run_python.")


def _in_child(sandbox, limits, run_id):
    """What runs in the child before exec: the per-file cap, then the sandbox's own caps."""
    sandbox_caps = sandbox.in_child(limits, run_id)

    def apply():
        size = limits.file_mb * 2**20
        resource.setrlimit(resource.RLIMIT_FSIZE, (size, size))
        signal.signal(signal.SIGXFSZ, signal.SIG_IGN)  # a write past the limit raises OSError instead of killing
        if sandbox_caps is not None:
            sandbox_caps()
    return apply


class _Capped:
    """Reads a stream to the end but keeps only its first and last `limit` bytes,
    so code that prints gigabytes can't fill this process's memory."""

    def __init__(self, stream, limit):
        self.head, self.tail, self.total, self.limit = b"", b"", 0, limit
        self.thread = threading.Thread(target=self._read, args=(stream,), daemon=True)
        self.thread.start()

    def _read(self, stream):
        while chunk := stream.read(65536):
            self.total += len(chunk)
            if len(self.head) < self.limit:
                room = self.limit - len(self.head)
                self.head, chunk = self.head + chunk[:room], chunk[room:]
            self.tail = (self.tail + chunk)[-self.limit:]

    def text(self, chars):
        """At most `chars` characters: all of it, or its start and end with a note of how much was cut.
        The end gets more room, because that's where a traceback says what went wrong."""
        self.thread.join(timeout=5)
        kept = self.head + self.tail
        if self.total <= chars:
            return kept.decode(errors="replace")
        start_chars = chars // 4
        end_chars = chars - start_chars
        cut = self.total - start_chars - end_chars
        start = kept[:start_chars].decode(errors="replace")
        end = kept[-end_chars:].decode(errors="replace")
        return f"{start}\n[... {cut} characters cut ...]\n{end}"


def _send_code(proc, code):
    try:
        proc.stdin.write(code.encode())
        proc.stdin.close()
    except BrokenPipeError:
        pass  # it ended before reading its code; stderr says why


def _disk_use(stat) -> int:
    """What an entry takes on disk: its size, or the blocks it holds if that's more. fallocate with
    FALLOC_FL_KEEP_SIZE holds blocks while the size stays 0 (Codex's review of PR 21)."""
    return max(stat.st_size, stat.st_blocks * 512)  # st_blocks counts 512-byte units on Linux and macOS


def folder_too_full(workdir: Path, limits: Limits) -> str | None:
    """Why the working folder is past its limits, or None. Per-file limits don't stop many
    files filling the disk, and the folder stays between calls. Every entry counts, folders
    and links as well as files, since each takes an inode. Stops counting at the limit."""
    size, count = 0, 0
    unreadable = []  # os.walk skips a folder it can't read; code could chmod one to hide what's in it
    for here, folders, files in os.walk(workdir, onerror=unreadable.append, followlinks=False):
        if unreadable:
            break
        for name in folders + files:  # a link to a folder is listed with the folders, and not followed
            try:
                size += _disk_use((Path(here) / name).lstat())
            except OSError:
                continue  # removed while counting
            count += 1
            if size > limits.workspace_mb * 2**20:
                return f"its folder passed {limits.workspace_mb} MB"
            if count > limits.workspace_files:
                return f"its folder passed {limits.workspace_files} files"
    if unreadable:
        return f"its folder couldn't be counted ({unreadable[0].strerror}: {Path(unreadable[0].filename).name})"
    return None


def _stop(proc, sandbox, run_id):
    sandbox.stop(run_id)
    proc.kill()
    proc.wait()


def _watch(proc, sandbox, run_id, workdir, limits) -> str | None:
    """Wait for it to finish, stopping it if it runs out of time or fills its folder. Why it was stopped, or None."""
    deadline = time.monotonic() + limits.timeout_s
    while True:
        try:
            proc.wait(timeout=0.25)
            return None
        except subprocess.TimeoutExpired:
            pass
        if time.monotonic() > deadline:
            _stop(proc, sandbox, run_id)
            return ran_too_long(limits.timeout_s)
        if too_full := folder_too_full(workdir, limits):
            _stop(proc, sandbox, run_id)
            return too_full


def run(sandbox, code: str, workdir: Path, limits: Limits = Limits()) -> Ran:
    workdir = Path(workdir).resolve()
    if too_full := folder_too_full(workdir, limits):
        return Ran(exit_code=None, stdout="", stderr="", stopped=f"{too_full} before it started; delete files to run again")
    run_id = f"pbe-run-python-{uuid.uuid4().hex[:12]}"
    if problem := sandbox.prepare(workdir, limits, run_id):
        return Ran(exit_code=None, stdout="", stderr="", stopped=f"{COULD_NOT_START}: {problem[-300:]}")
    try:
        proc = subprocess.Popen(sandbox.command(workdir, limits, run_id), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=sandbox.client_environment(), cwd=workdir,
                                preexec_fn=_in_child(sandbox, limits, run_id), pass_fds=sandbox.kept_open(run_id))
        stdout = _Capped(proc.stdout, limits.output_chars)
        stderr = _Capped(proc.stderr, limits.output_chars)
        _send_code(proc, code)
        stopped = _watch(proc, sandbox, run_id, workdir, limits)
    finally:
        sandbox.cleanup(run_id)
    each_stream = limits.output_chars // 2
    return Ran(exit_code=None if stopped else proc.returncode, stdout=stdout.text(each_stream),
               stderr=stderr.text(each_stream), stopped=stopped)
