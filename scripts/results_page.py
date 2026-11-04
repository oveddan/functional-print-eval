"""The results page: every trial grouped by what the run could do, each one opening onto its designs in 3D,
every check, what went wrong (a real failure, Dan's call, or something the records can't decide) and what
tool would have let the model do better. Coupon loop trials also show each replay. No model calls.

    uv run python scripts/results_page.py

Reads the saved runs, the coupon loop's replays (results/runs/loop-sample*/) and the audit notes in
scripts/results_page_audit.json. A part whose mesh isn't on this machine (parts/ isn't committed) is
built again from the saved design first. Writes results/local/results-page/: index.html, thumbs/ and stl/.
"""
import argparse
import base64
import json
import re
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gallery  # noqa: E402  the gallery's renderer and part list, so both pages render parts the same way

from pbe.parts import submission  # noqa: E402
from pbe.parts.build import build_parts  # noqa: E402
from pbe.runner import coupon_loop  # noqa: E402
from pbe.runner.trial_record import TrialRecord  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/local/results-page"
TEMPLATE = Path(__file__).with_name("results_page_template.html")
AUDIT = Path(__file__).with_name("results_page_audit.json")
RUNS = ["pilot-nut-knob", "pilot-nut-knob-2", "pilot-tripod", "pilot-tripod-given", "pilot-wheel"]
LOOP_RUNS = {1: "loop-sample", 2: "loop-sample-2"}

HELP = {
    "build": "Let it run its own code before handing in",
    "checks": "Let it run the eval's printability checks before handing in",
    "render": "Show it a render or measurements of what it built",
    "coupon": "Tell it how its test print came out (the coupon loop)",
    "measure": "Let the person measure the clamp, or say plainly they can't",
    "label": "Clearer instructions on marking a part as a test coupon",
    "prints": "Not the model's fault: needs more recorded prints",
    "reader": "Not the model's fault: the checker can't read this shape yet",
}
KIND = {"real": "Real failure", "decided": "Real failure (Dan decided)", "open": "Dan to decide", "gap": "Records can't decide",
        "declined": "Declined: neither a pass nor a fail"}
# a not-graded check that only follows from another failure, which is already counted
CONSEQUENCE = ("didn't build", "no plate built", "no bolt hole to read", "expected one printed part", "no hex pocket",
               "a final part didn't build", "no wheel to read", "no final part", "no seat to read")
BROKEN_ROOFS = {("pilot-tripod-given", "qwen/qwen3.8-flash", 1), ("pilot-tripod", "qwen/qwen3.8-flash", 1)}
MAIN_PART = ("wheel", "roller", "knob", "plate")  # the part a trial is about, shown first
OUTCOME_WORDS = {"error": "didn't run: an infrastructure error", "token_limit": "no design: every call stopped at the token limit",
                 "no_submission": "no design"}


# ---- what went wrong, and what would have helped ----

def missing_record(family, check, detail):
    """A check no recorded print can decide: which record is missing."""
    if "slits split" in detail:
        return "Not graded: a pocket shape the checker can't read", "gap", "reader"
    if check == "bridges":
        return "Not graded: a roof ledge 1.5 to 3 mm wide, never printed", "gap", "prints"
    if family == "nut-knob":
        if "ribs" in detail:
            return "Not graded: a nut pocket with ribs or clips, never printed", "gap", "prints"
        if "no print has settled whether any of them holds" in detail:  # the grader doesn't say why, so neither do we
            return "Not graded: its test coupon's pockets are ribbed or sizes no print settled", "gap", "prints"
        if "prints say struggles to go in" in detail:
            return "Not graded: the prints say this size struggles to go in", "open", "prints"
        over = re.search(r"([+-]\d+\.\d+) over the", detail)
        if "prints say not measured" in detail and over:
            # coupon B printed each nut at 0.0 to 0.3 mm over its across-flats size
            clearance = float(over.group(1))
            if clearance < 0:
                return "Not graded: a nut pocket tighter than any printed", "gap", "prints"
            if clearance > 0.3:
                return "Not graded: a nut pocket looser than any printed", "gap", "prints"
            return "Not graded: a nut pocket between printed sizes", "gap", "prints"
        return "Not graded: no recorded print settles this nut pocket", "gap", "prints"
    if family == "tripod-plate":
        if check == "R2":
            return "Not graded: plate width outside 37 to 39 mm (jaw travel not recorded)", "gap", "prints"
        if check == "R3":
            return "Not graded: bolt hole between 6.35 and 6.8 mm, never printed", "gap", "prints"
        return "Not graded: head recess under 5 mm deep, never printed", "gap", "prints"
    if check == "R4":
        return "Not graded: wheel bolt hole between 8.0 and 8.4 mm, never printed", "gap", "prints"
    if check == "R2":
        return "Not graded: bearing a little proud, or no shoulder, never printed", "gap", "prints"
    return "Not graded: bearing seat between printed sizes or ribbed", "gap", "prints"


def failure(run, record, finding, note):
    """A counted check that failed: (what went wrong, is it real, what would help)."""
    family, check, detail = record.task.split("/")[0], finding.check, finding.detail
    if note and note["kind"] == "open" and "marked final" in note["note"]:
        return "Test coupon labelled as a final part", "open", "label"
    if note and note["kind"] == "open" and "really struggles" in note["note"]:
        return "Nut pocket a size the prints don't take", "open", "coupon"
    if check == "builds":
        return "Its code didn't run", "real", "build"
    if check == "connected_bodies":
        return "Geometry slip: a part in pieces", "real", "render"
    if check == "bridges":
        if (run, record.model, record.trial) in BROKEN_ROOFS:
            return "Geometry slip: a broken shape", "real", "render"
        return "A roof with the bolt's hole cut through it", "decided", "checks"
    if family == "nut-knob":
        if check == "R4":
            return "Nut pocket a size the prints don't take", "real", "coupon"
        return "Geometry slip: the pocket is closed", "real", "render"
    if family == "bearing-wheel":
        if check == "R3":
            return "Bearing seat a size the prints don't take", "real", "coupon"
        return "Wheel geometry", "real", "render"
    if check == "R5":
        return "Bolt doesn't reach far enough into the camera", "real", "checks"
    if check == "R4":
        return "Head recess too small (a CAD slip)", "real", "render"
    if check == "R2":
        return "Geometry slip: straight sides, nothing for the clamp to grip", "real", "render"
    if check == "R3" and "narrow face" in detail:
        return "Geometry slip: dovetail upside down", "real", "render"
    return "Geometry slip: no usable bolt hole", "real", "render"


def issues_of(run, record, note):
    """Every counted check that didn't pass, diagnosed. A declined trial counts none, as its verdict says."""
    if record.declined:
        return [{"check": "-", "part": "-", "family": "Declined: the clamp's width isn't recorded", "kind": "declined", "help": "measure"}]
    found = []
    for finding in record.counted_findings:
        if finding.ok is True:
            continue
        if finding.ok is None:
            if any(phrase in finding.detail for phrase in CONSEQUENCE):
                continue
            diagnosis = missing_record(record.task.split("/")[0], finding.check, finding.detail)
        else:
            diagnosis = failure(run, record, finding, note)
        family, kind, help_key = diagnosis
        found.append({"check": finding.check, "part": finding.part, "family": family, "kind": kind, "help": help_key})
    return found


# ---- parts, rebuilt where this machine doesn't have them ----

def ensure_parts(folder, sub):
    """Build the design's parts into folder/parts if they aren't there: parts/ isn't committed."""
    parts = folder / "parts"
    if sub is None or (parts.exists() and any(parts.glob("*.stl"))):
        return
    build_parts(sub, parts)


def trial_card(run, folder, record, audit, rounds, renders):
    sub = submission.load(folder / "submission.yaml") if (folder / "submission.yaml").exists() else None
    ensure_parts(folder, sub)
    # unlike the gallery's names, these include the run: two runs can hold the same model's t1 on one task
    slug = re.sub(r"[^\w-]+", "_", f"{run}-{record.task}-{record.condition}-{record.model}-t{record.trial}")
    roles = gallery.final_roles(folder)
    parts = [part.model_dump() | {"role": roles.get(part.id, "")} for part in gallery.parts_of(folder, renders, slug)]
    key = f"{run}|{record.task}|{record.condition}|{record.model}|{record.trial}"
    has_coupon = sub is not None and any(part.role == "coupon" for part in sub.parts)
    parts.sort(key=lambda part: (part["role"] != "final", not any(word in part["id"].lower() for word in MAIN_PART)))
    findings = [finding.model_dump() for finding in record.findings]
    return {"key": key, "id": re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-"), "run": run, "task": record.task,
            "condition": record.condition, "model": record.model, "trial": record.trial, "verdict": gallery.verdict(record),
            "cost": record.cost_usd, "asked": [m.what or m.item for m in record.measures], "answers": [m.reply for m in record.measures],
            "findings": findings, "parts": parts,
            "audit": audit.get(key), "issues": issues_of(run, record, audit.get(key)),
            "group": "loop" if key in rounds else ("coupon" if has_coupon else "none"), "rounds": rounds.get(key, [])}


# ---- the coupon loop's replays ----

def loop_verdict(record):
    """(kind, label) for one arm: pass, fail, not_graded, or no_design when the turn produced none."""
    if record.outcome in OUTCOME_WORDS:
        return "no_design", OUTCOME_WORDS[record.outcome]
    if record.all_pass:
        return "pass", "pass"
    if any(finding.ok is False for finding in record.findings):
        return "fail", record.summary()
    return "not_graded", record.summary()


def arm_parts(folder, slug, renders):
    """The revised design's final parts, built if this machine doesn't have them, queued to render."""
    sub_path = folder / "submission.yaml"
    if not sub_path.exists():
        return []
    ensure_parts(folder, coupon_loop.without_coupons(submission.load(sub_path)))
    parts = []
    for stl in sorted((folder / "parts").glob("*.stl"), key=lambda path: -path.stat().st_size):
        name = f"{slug}-{folder.name}-{stl.stem}"
        renders.append((stl, OUT / "thumbs" / f"{name}.png"))
        viewer = stl.stat().st_size <= gallery.MAX_VIEWER_MB * 1024 * 1024
        if viewer:
            (OUT / "stl" / f"{name}.txt").write_text(base64.b64encode(stl.read_bytes()).decode())
        parts.append({"id": stl.stem, "name": name, "viewer": viewer, "thumb": f"thumbs/{name}.png", "role": "final"})
    return parts


def arm(folder, slug, renders):
    record = coupon_loop.LoopRecord.load(folder)
    kind, label = loop_verdict(record)
    return {"outcome": record.outcome, "verdict": kind, "label": label, "cost": record.cost_usd, "calls": len(record.calls),
            "findings": [finding.model_dump() for finding in record.findings],
            "parts": arm_parts(folder, slug, renders) if kind != "no_design" else []}


def card_key(replayed, model):
    run, family, *rest = replayed.split("/")
    task = f"nut-knob/{rest.pop(0)}" if family == "nut-knob" else family
    condition, _, trial = rest
    return f"{run}|{task}|{condition}|{model}|{int(trial[1:])}"


def loop_rounds(renders):
    """{card key: [one entry per sample: the report and both arms]}."""
    rounds = {}
    for sample, run in LOOP_RUNS.items():
        for baseline in sorted((ROOT / "results/runs" / run).rglob("baseline/" + coupon_loop.FILE_NAME)):
            folder = baseline.parent.parent
            record = coupon_loop.LoopRecord.load(baseline.parent)
            if not (folder / "feedback" / coupon_loop.FILE_NAME).exists():
                continue
            slug = f"loop{sample}-" + record.replayed.replace("/", "-").replace(".", "_")
            feedback = coupon_loop.LoopRecord.load(folder / "feedback")
            report = [{"part": part, "text": line.text, "basis": line.basis} for part, lines in feedback.report.items() for line in lines]
            rounds.setdefault(card_key(record.replayed, record.model), []).append(
                {"sample": sample, "report": report, "feedback": arm(folder / "feedback", slug, renders),
                 "neutral": arm(folder / "neutral", slug, renders)})
    return rounds


def loop_summary():
    """Per sample: passes per arm, failing checks that now pass, and trials made worse."""
    summary = []
    for sample, run in LOOP_RUNS.items():
        row = {"sample": sample, "trials": 0, "baseline": 0, "feedback": 0, "neutral": 0,
               "fixed": {"feedback": [], "neutral": []}, "worse": {"feedback": [], "neutral": []}, "cost": 0.0}
        for baseline_path in sorted((ROOT / "results/runs" / run).rglob("baseline/" + coupon_loop.FILE_NAME)):
            folder = baseline_path.parent.parent
            baseline = coupon_loop.LoopRecord.load(baseline_path.parent)
            before = {(f.check, f.part): f.ok for f in baseline.findings}
            parts = folder.relative_to(ROOT / "results/runs" / run).parts
            label = f"{parts[-2].split('__')[1]}, {'/'.join(parts[1:-3]).replace('nut-knob/', '').replace('bearing-wheel', 'wheel')} {parts[-1]}"
            row["trials"] += 1
            row["baseline"] += baseline.all_pass
            for arm_name in ("feedback", "neutral"):
                record = coupon_loop.LoopRecord.load(folder / arm_name)
                row["cost"] += record.cost_usd
                row[arm_name] += record.all_pass
                after = {(f.check, f.part): f.ok for f in record.findings}
                row["fixed"][arm_name] += [f"{label}: {check}" for (check, part), ok in after.items() if before.get((check, part)) is False and ok is True]
                if any(ok is False and before.get(key) is not False for key, ok in after.items()):
                    row["worse"][arm_name].append(label)
        row["cost"] = round(row["cost"], 2)
        summary.append(row)
    return summary


# ---- the page ----

def write_page(trials, tasks_seen):
    briefs = {task: gallery.brief_of(task) for task in tasks_seen}
    page = TEMPLATE.read_text()
    for placeholder, value in (("/*TRIALS*/[]", trials), ("/*TASKS*/{}", briefs), ("/*FRONTIER*/[]", gallery.FRONTIER),
                               ("/*HELP*/{}", HELP), ("/*KIND*/{}", KIND), ("/*LOOPSUM*/[]", loop_summary())):
        page = page.replace(placeholder, json.dumps(value, ensure_ascii=False).replace("</", "<\\/"))
    (OUT / "index.html").write_text(page)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="*", default=RUNS, help="saved runs to show; every trial in each is kept")
    args = parser.parse_args()
    gallery.OUT = OUT  # the gallery's helpers write renders and meshes under its OUT
    (OUT / "thumbs").mkdir(parents=True, exist_ok=True)
    (OUT / "stl").mkdir(parents=True, exist_ok=True)
    audit = json.loads(AUDIT.read_text())
    renders = []
    rounds = loop_rounds(renders)
    trials = []
    for run in args.runs:
        for folder, record in TrialRecord.all_in(ROOT / "results/runs" / run):
            trials.append(trial_card(run, folder, record, audit, rounds, renders))
    with Pool() as pool:
        pool.map(gallery.render, renders)
    for trial in trials:  # a part that didn't render shows as "no render"
        design_parts = trial["parts"] + [part for entry in trial["rounds"] for name in ("feedback", "neutral") for part in entry[name]["parts"]]
        for part in design_parts:
            render = f"thumbs/{part['name']}.png"
            part["thumb"] = render if (OUT / render).exists() else ""
    write_page(trials, sorted({trial["task"] for trial in trials}))
    print(f"{len(trials)} trials, {Counter(t['group'] for t in trials)}, {Counter(t['verdict'] for t in trials)}; {OUT / 'index.html'}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
