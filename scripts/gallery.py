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

from string import Template

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from pydantic import BaseModel

from pbe.parts import submission
from pbe.runner import tasks
from pbe.runner.trial_record import TrialRecord

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/local/gallery"
TEMPLATE = Path(__file__).with_name("gallery_template.html")
MAX_VIEWER_MB = 4  # a publish has a size limit; a bigger mesh keeps its thumbnail only
MAX_DRAWN_FACES = 40000  # matplotlib slows badly past this; a thumbnail doesn't need them all
# frontier first, then the smaller models
FRONTIER = ["anthropic/claude-opus-5.5", "anthropic/claude-sonnet-5.5", "openai/gpt-6.1-sol", "google/gemini-4-argon",
            "x-ai/grok-4.7", "deepseek/deepseek-v4-pro-0813"]


class GalleryPart(BaseModel):
    id: str
    name: str  # the file names its render and mesh are saved under
    viewer: bool  # small enough for the page's 3D viewer
    role: str = ""  # final or coupon, from the submission
    thumb: str = ""  # its render's path, once rendered


class GalleryTrial(BaseModel):
    """One trial as the page shows it."""
    task: str
    condition: str
    model: str
    trial: int
    run: str
    verdict: str
    cost: float
    asked: list[str]
    answers: list[str]
    findings: list[dict]  # the checks that didn't pass
    parts: list[GalleryPart]


def _shaded_faces(mesh):
    """The faces to draw, at most MAX_DRAWN_FACES of them, each with a colour lit from above left."""
    light = np.array([0.45, -0.35, 0.82])
    faces = mesh.triangles
    normals = mesh.face_normals
    if len(faces) > MAX_DRAWN_FACES:
        keep = np.linspace(0, len(faces) - 1, MAX_DRAWN_FACES).astype(int)
        faces, normals = faces[keep], normals[keep]
    shade = 0.32 + 0.6 * np.clip(normals @ light, 0, 1)
    colours = np.column_stack([shade * 0.86, shade * 0.9, shade * 0.98, np.ones(len(shade))])
    return faces, colours


def render(stl_and_png):
    stl, png = stl_and_png
    if png.exists() and png.stat().st_mtime > stl.stat().st_mtime:
        return
    mesh = trimesh.load(stl, force="mesh")
    faces, colours = _shaded_faces(mesh)
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


def parts_of(folder, renders, slug):
    """The trial's built parts, each queued to render and, if it's small enough, copied for the 3D viewer."""
    if not (folder / "parts").exists():
        return []
    parts = []
    for stl in sorted((folder / "parts").glob("*.stl")):
        name = f"{slug}-{stl.stem}"
        renders.append((stl, OUT / "thumbs" / f"{name}.png"))
        fits = stl.stat().st_size <= MAX_VIEWER_MB * 1024 * 1024
        if fits:
            # as base64 text, because an artifact can't publish a .stl file
            (OUT / "stl" / f"{name}.txt").write_text(base64.b64encode(stl.read_bytes()).decode())
        parts.append(GalleryPart(id=stl.stem, name=name, viewer=fits))
    return parts


def verdict(record):
    if record.outcome != "submitted":
        return "error"
    if record.all_pass:
        return "pass"
    return "fail" if record.failed_checks else "not_graded"


def brief_of(task):
    """The person's words and the first paragraph on why the task is hard, from brief.md."""
    family, _, variant = task.partition("/")
    text = (ROOT / "tasks" / family / "brief.md").read_text()
    words = " ".join(line[1:].strip() for line in text.splitlines() if line.startswith(">"))
    why = re.search(r"## Why it'?s hard\s+(.+?)\n\n", text, re.S)
    if variant and "$" in words:  # a family's brief is a template
        words = Template(words).safe_substitute(tasks.variant_values(family, variant))
    return {"request": words, "why": " ".join(why.group(1).split()) if why else ""}


def final_roles(folder):
    """Each part's role, by id, from the trial's submission: final or coupon."""
    sub_path = folder / "submission.yaml"
    if not sub_path.exists():
        return {}
    return {part.id: part.role for part in submission.load(sub_path).parts}


def trial_entry(run, folder, record, renders):
    """One trial as the page shows it. Its parts are queued in `renders`."""
    slug = re.sub(r"[^\w-]+", "_", f"{record.task}-{record.condition}-{record.model}-t{record.trial}")
    roles = final_roles(folder)
    parts = parts_of(folder, renders, slug)
    for part in parts:
        part.role = roles.get(part.id, "")
    parts.sort(key=lambda part: part.role != "final")
    asked = [measurement.what or measurement.item for measurement in record.measures]
    answers = [measurement.reply for measurement in record.measures]
    not_passed = [finding.model_dump() for finding in record.findings if finding.ok is not True]
    return GalleryTrial(task=record.task, condition=record.condition, model=record.model, trial=record.trial, run=run,
                        verdict=verdict(record), cost=record.cost_usd, asked=asked, answers=answers,
                        findings=not_passed, parts=parts)


def link_thumbnails(trials):
    """Point each part at its render, or at nothing if it didn't render."""
    for trial in trials:
        for part in trial.parts:
            png = OUT / "thumbs" / f"{part.name}.png"
            part.thumb = f"thumbs/{part.name}.png" if png.exists() else ""


def write_page(trials):
    briefs = {trial.task: brief_of(trial.task) for trial in trials}
    data = json.dumps({"trials": [trial.model_dump() for trial in trials], "tasks": briefs, "frontier": FRONTIER})
    (OUT / "index.html").write_text(TEMPLATE.read_text().replace("/*DATA*/null", data.replace("</", "<\\/")))
    files = [f for f in OUT.rglob("*") if f.is_file()]
    size_mb = sum(f.stat().st_size for f in files) / 1e6
    print(f"{len(trials)} trials on {len(briefs)} tasks; {len(files)} files, {size_mb:.1f} MB; {OUT / 'index.html'}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    args = ap.parse_args()
    (OUT / "thumbs").mkdir(parents=True, exist_ok=True)
    shutil.rmtree(OUT / "stl", ignore_errors=True)
    (OUT / "stl").mkdir()
    renders = []
    trials = [trial_entry(run, folder, record, renders) for run, folder, record in load_trials(args.runs)]
    with Pool() as pool:
        pool.map(render, renders)
    link_thumbnails(trials)
    write_page(trials)


if __name__ == "__main__":
    main()
