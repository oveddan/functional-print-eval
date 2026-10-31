"""Run each part's CadQuery code and export a mesh.

Part code comes from models, so it runs in a separate Python process with a
time limit, never in the grader's own process. `overrides` replaces param values,
which is how the metamorphic check varies hardware dimensions.
"""
import json
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


@dataclass
class Built:
    part: str
    ok: bool
    stl: Path | None = None
    mesh: trimesh.Trimesh | None = None
    error: str = ""


def build_parts(sub: Submission, out_dir, overrides=None, timeout=120) -> dict[str, Built]:
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
            try:
                r = subprocess.run([sys.executable, "-I", str(runner), str(spec)], cwd=tmp,
                                   capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                results[part.id] = Built(part.id, False, error=f"timed out after {timeout} s")
                continue
            if r.returncode != 0 or not stl.exists():
                results[part.id] = Built(part.id, False, error=(r.stderr.strip().splitlines() or ["no output"])[-1])
                continue
            results[part.id] = Built(part.id, True, stl, trimesh.load(stl, force="mesh"))
    return results
