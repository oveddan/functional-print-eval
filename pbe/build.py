"""Run each part's CadQuery code and export a mesh.

Part code comes from models, so it runs in a separate Python process with a
time limit, never in the grader's own process, and with none of this process's
environment, so it can't see the API key. On macOS it also runs in a sandbox: no
network, no child processes, and it can write only to its own two folders. It can
still read files. Where there's no sandbox it doesn't run at all, unless PBE_NO_SANDBOX=1
says someone has chosen that. `overrides` replaces param values, which is how the
metamorphic check varies hardware dimensions.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import trimesh

from pbe.submission import Submission

RUNNER = r"""
import json, sys, types
import cadquery as cq
spec = json.load(open(sys.argv[1]))
p = types.SimpleNamespace(**spec["params"])
ns = {"cq": cq}
exec(compile(spec["code"], spec["part"], "exec"), ns)
shape = ns["build"](p)
cq.exporters.export(shape, spec["out"], tolerance=0.01, angularTolerance=0.1)
"""


def require_sandbox():
    if not shutil.which("sandbox-exec") and os.environ.get("PBE_NO_SANDBOX") != "1":
        raise RuntimeError("No sandbox-exec here (it's macOS only), so model-written code would run with your "
                           "network and files. Run it in a throwaway container or VM with PBE_NO_SANDBOX=1.")


def _isolated(command, out_dir, tmp):
    """(command, env) for running model code: no inherited environment, and a sandbox if there is one."""
    env = {"PATH": os.environ.get("PATH", ""), "HOME": tmp, "TMPDIR": tmp}
    if not shutil.which("sandbox-exec"):
        return command, env
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
