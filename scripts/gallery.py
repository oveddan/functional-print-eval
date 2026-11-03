"""A page comparing what each model designed: a render of every trial beside its verdict, with
each check's reason. Built only from saved runs, with no model calls.

    uv run python scripts/gallery.py pilot-nut-knob pilot-nut-knob-2 pilot-tripod

Name runs oldest first: a later run's trial replaces an earlier one's. Writes to
results/local/gallery/: index.html, thumbs/ (kept, so a rebuild only renders new parts) and
stl/ (the meshes the page's 3D viewer loads).
"""
import argparse
import base64
import json
import re
import shutil
import sys
from multiprocessing import Pool
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from pbe.trial_record import TrialRecord

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/local/gallery"
TEMPLATE = Path(__file__).with_name("gallery_template.html")
MAX_VIEWER_MB = 4  # a publish has a size limit; a bigger mesh keeps its thumbnail only
MAX_DRAWN_FACES = 40000  # matplotlib slows badly past this; a thumbnail doesn't need them all
GROUPS = {"anthropic/claude-opus-5.5": 0, "anthropic/claude-sonnet-5.5": 0, "openai/gpt-6.1-sol": 0, "google/gemini-4-argon": 0,
          "x-ai/grok-4.7": 0, "deepseek/deepseek-v4-pro-0813": 0}  # frontier first, then the smaller models


def render(job):
    stl, png = job
    if png.exists() and png.stat().st_mtime > stl.stat().st_mtime:
        return
    mesh = trimesh.load(stl, force="mesh")
    light = np.array([0.45, -0.35, 0.82])
    faces = mesh.triangles
    normals = mesh.face_normals
    if len(faces) > MAX_DRAWN_FACES:
        keep = np.linspace(0, len(faces) - 1, MAX_DRAWN_FACES).astype(int)
        faces, normals = faces[keep], normals[keep]
    shade = 0.32 + 0.6 * np.clip(normals @ light, 0, 1)
    colours = np.column_stack([shade * 0.86, shade * 0.9, shade * 0.98, np.ones(len(shade))])
    fig = plt.figure(figsize=(4, 3.2), dpi=110)
    fig.patch.set_alpha(0)
    ax = fig.add_axes([0, 0, 1, 1], projection="3d")
    ax.patch.set_alpha(0)
    ax.add_collection3d(Poly3DCollection(faces, facecolors=colours, edgecolors="none", antialiaseds=False))
    low, high = mesh.bounds
    middle, reach = (low + high) / 2, float((high - low).max()) * 0.47
    ax.set_xlim(middle[0] - reach, middle[0] + reach)
    ax.set_ylim(middle[1] - reach, middle[1] + reach)
    ax.set_zlim(middle[2] - reach, middle[2] + reach)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=38, azim=-52)
    ax.set_axis_off()
    fig.savefig(png, transparent=True)
    plt.close(fig)


def load_trials(runs):
    """The newest saved copy of each trial, across runs named oldest first."""
    found = {}
    for run in runs:
        for folder, record in TrialRecord.all_in(ROOT / "results/runs" / run):
            found[record.task, record.condition, record.model, record.trial] = (run, folder, record)
    return found.values()


def parts_of(folder, jobs, slug):
    parts = []
    for stl in sorted((folder / "parts").glob("*.stl")) if (folder / "parts").exists() else []:
        name = f"{slug}-{stl.stem}"
        png = OUT / "thumbs" / f"{name}.png"
        jobs.append((stl, png))
        fits = stl.stat().st_size <= MAX_VIEWER_MB * 1024 * 1024
        if fits:
            # as base64 text, because an artifact can't publish a .stl file
            (OUT / "stl" / f"{name}.txt").write_text(base64.b64encode(stl.read_bytes()).decode())
        parts.append({"id": stl.stem, "name": name, "viewer": fits})
    return parts


def verdict(record):
    if record.outcome != "submitted":
        return "error"
    if record.all_pass:
        return "pass"
    return "fail" if record.failed_checks else "not_graded"


def brief_of(task):
    """The person's words and the first paragraph on why the task is hard, from brief.md."""
    text = (ROOT / "tasks" / task.split("/")[0] / "brief.md").read_text()
    words = " ".join(line[1:].strip() for line in text.splitlines() if line.startswith(">"))
    why = re.search(r"## Why it'?s hard\s+(.+?)\n\n", text, re.S)
    if "/" in task and "$" in words:  # a family's brief is a template
        import yaml
        from string import Template
        values = yaml.safe_load((ROOT / "tasks" / task.split("/")[0] / "variants.yaml").read_text())[task.split("/")[1]]
        words = Template(words).safe_substitute(values)
    return {"request": words, "why": " ".join(why.group(1).split()) if why else ""}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    args = ap.parse_args()
    (OUT / "thumbs").mkdir(parents=True, exist_ok=True)
    shutil.rmtree(OUT / "stl", ignore_errors=True)
    (OUT / "stl").mkdir()
    jobs, trials = [], []
    for run, folder, record in load_trials(args.runs):
        slug = re.sub(r"[^\w-]+", "_", f"{record.task}-{record.condition}-{record.model}-t{record.trial}")
        finals = {}
        if (folder / "submission.yaml").exists():
            import yaml
            finals = {p["id"]: p["role"] for p in yaml.safe_load((folder / "submission.yaml").read_text())["parts"]}
        parts = parts_of(folder, jobs, slug)
        for p in parts:
            p["role"] = finals.get(p["id"], "")
        parts.sort(key=lambda p: p["role"] != "final")
        trials.append({"task": record.task, "condition": record.condition, "model": record.model, "trial": record.trial, "run": run,
                       "verdict": verdict(record), "cost": record.cost_usd, "asked": [m.what or m.item for m in record.measures],
                       "answers": [m.reply for m in record.measures],
                       "findings": [f.model_dump() for f in record.findings if f.ok is not True],
                       "parts": parts})
    with Pool() as pool:
        pool.map(render, jobs)
    for t in trials:
        for p in t["parts"]:
            png = OUT / "thumbs" / f"{p['name']}.png"
            p["thumb"] = f"thumbs/{p['name']}.png" if png.exists() else ""
    tasks = {t["task"]: brief_of(t["task"]) for t in trials}
    data = json.dumps({"trials": trials, "tasks": tasks, "frontier": list(GROUPS)})
    (OUT / "index.html").write_text(TEMPLATE.read_text().replace("/*DATA*/null", data.replace("</", "<\\/")))
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    files = sum(1 for f in OUT.rglob("*") if f.is_file())
    print(f"{len(trials)} trials on {len(tasks)} tasks; {files} files, {size:.1f} MB; {OUT / 'index.html'}", file=sys.stderr)


if __name__ == "__main__":
    main()
