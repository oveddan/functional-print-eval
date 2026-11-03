"""Run each part's CadQuery code and export a mesh.

Part code comes from models, so it runs in a separate Python process with a
time limit, never in the grader's own process, and with none of this process's
environment, so it can't see the API key. It also runs in a sandbox, `sandbox-exec` on
macOS and bubblewrap on Linux: no network, and it can write only to its own two folders.
It can still read files. Child processes are refused too, by the OS on macOS. On Linux only
the runner's audit hook refuses them, which ordinary code can't get past but ctypes could.
Where there's no sandbox it doesn't run at all, unless PBE_NO_SANDBOX=1 says someone has
chosen that. `overrides` replaces param values, which is how the metamorphic check varies
hardware dimensions.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import trimesh

from pbe.submission import Submission

RUNNER = r"""
import json, sys, types
import cadquery as cq
spec = json.load(open(sys.argv[1]))
REFUSED = {"socket.connect", "subprocess.Popen", "os.system", "os.fork", "os.forkpty", "os.posix_spawn", "os.spawn", "os.exec"}
def refuse(event, args):
    if event in REFUSED:
        raise PermissionError(f"{event} is not permitted here")
sys.addaudithook(refuse)  # the same refusal on every platform, so a part can't pass on one and fail on another
p = types.SimpleNamespace(**spec["params"])
ns = {"cq": cq}
exec(compile(spec["code"], spec["part"], "exec"), ns)
shape = ns["build"](p)
cq.exporters.export(shape, spec["out"], tolerance=0.01, angularTolerance=0.1)
"""


BWRAP = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
         "--unshare-net", "--unshare-pid", "--new-session", "--die-with-parent"]


@cache
def _bwrap_runs():
    """A kernel or VM can refuse bubblewrap's namespaces, and every part would then look like a failed build."""
    return subprocess.run([*BWRAP, "true"], capture_output=True).returncode == 0


def sandbox():
    if shutil.which("sandbox-exec"):
        return "sandbox-exec"
    if shutil.which("bwrap") and _bwrap_runs():
        return "bwrap"
    return None


def require_sandbox():
    if not sandbox() and os.environ.get("PBE_NO_SANDBOX") != "1":
        raise RuntimeError("No working sandbox here (sandbox-exec on macOS, bwrap on Linux), so model-written code "
                           "would run with your network and files. Run it in a throwaway container or VM with PBE_NO_SANDBOX=1.")


def _isolated(command, out_dir, tmp):
    """(command, env) for running model code: no inherited environment, and a sandbox if there is one."""
    env = {"PATH": os.environ.get("PATH", ""), "HOME": tmp, "TMPDIR": tmp}
    kind = sandbox()
    if kind is None:
        return command, env
    if kind == "bwrap":
        binds = [arg for d in (out_dir, tmp) for arg in ("--bind", str(Path(d).resolve()), str(Path(d).resolve()))]
        return [*BWRAP, *binds, *command], env
    writable = " ".join(f'(subpath "{Path(d).resolve()}")' for d in (out_dir, tmp))
    profile = (f'(version 1)(allow default)(deny network*)(deny process-fork)(deny file-write*)'
               f'(allow file-write* {writable} (literal "/dev/null"))')
    return ["sandbox-exec", "-p", profile, *command], env


@dataclass
class Built:
    part: str
    ok: bool
    stl: Path | None = None
    mesh: trimesh.Trimesh | None = None
    error: str = ""
    role: str = ""


def build_parts(sub: Submission, out_dir, overrides=None, timeout=120) -> dict[str, Built]:
    require_sandbox()
    out_dir = Path(out_dir).resolve()  # the runner's cwd is a temp dir
    out_dir.mkdir(parents=True, exist_ok=True)
    params = {k: v.value for k, v in sub.params.items()}
    params.update(overrides or {})
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        runner = Path(tmp) / "runner.py"
        runner.write_text(RUNNER)
        for part in sub.parts:
            stl = out_dir / f"{part.id}.stl"
            spec = Path(tmp) / f"{part.id}.json"
            spec.write_text(json.dumps({"params": params, "code": part.code, "part": part.id, "out": str(stl)}))
            command, env = _isolated([sys.executable, "-I", str(runner), str(spec)], out_dir, tmp)
            try:
                r = subprocess.run(command, cwd=tmp, env=env, capture_output=True, text=True, errors="replace", timeout=timeout)
            except subprocess.TimeoutExpired:
                results[part.id] = Built(part.id, False, error=f"timed out after {timeout} s")
                continue
            if r.returncode != 0 or not stl.exists():
                results[part.id] = Built(part.id, False, error=(r.stderr.strip().splitlines() or ["no output"])[-1])
                continue
            try:
                results[part.id] = Built(part.id, True, stl, trimesh.load(stl, force="mesh"))
            except Exception as e:  # a model's shape can export as something trimesh can't read
                results[part.id] = Built(part.id, False, error=f"exported, but the mesh can't be read: {e}")
    for part in sub.parts:
        results[part.id].role = part.role
    return results
