"""Slicer estimates of print time and filament for each saved design: final parts and test prints.

    uv run python scripts/slice_estimates.py pilot-tripod
    uv run python scripts/slice_estimates.py pilot-tripod pilot-tripod-given pilot-nut-knob pilot-nut-knob-2 pilot-wheel

These are estimates from Bambu Studio's slicer, run offline on this machine, not measured prints: nothing is sent
to a printer. Each part is sliced as its own plate with one fixed setup, the one Dan's test prints used
(catalog/printer.yaml): machine "Bambu Lab X1 Carbon 0.4 nozzle", process "0.20mm Standard @BBL X1C" and filament
"Generic PLA High Speed @BBL X1C", Bambu's stock system presets with one change: the machine's start and end G-code
are left out. Homing, nozzle cleaning, calibration and the purge line depend on the printer, not on the design, so
neither the time nor the filament counts them. docs/slice-estimates.md has the method and its limits.

A part's mesh is built from the saved design the way the results page builds it (parts/ isn't committed), dropped
onto the bed (lowest point to z = 0) without turning it, since a design's z = 0 is already its bed face. Writes,
next to each run's summary.csv, slice_estimates_parts.csv (one row per part) and slice_estimates.csv (one row per
trial). It changes no grade and no summary.csv. Needs Bambu Studio (BAMBU_STUDIO, default the macOS app).
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, fields
from multiprocessing import Pool
from pathlib import Path

import trimesh

from pbe.parts import submission
from pbe.parts.build import build_parts
from pbe.runner.trial_record import TrialRecord

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs"
APP = Path(os.environ.get("BAMBU_STUDIO", "/Applications/BambuStudio.app"))
PRESETS = {  # Dan's test print setup (catalog/printer.yaml), Bambu's stock system presets
    "machine": "Bambu Lab X1 Carbon 0.4 nozzle",
    "process": "0.20mm Standard @BBL X1C",
    "filament": "Generic PLA High Speed @BBL X1C",
}
SLICE_TIMEOUT_S = 300
PARTS_CSV = "slice_estimates_parts.csv"
TRIALS_CSV = "slice_estimates.csv"


# ---- Bambu Studio and its presets ----

def slicer_binary(app=APP) -> Path:
    return app / "Contents/MacOS/BambuStudio" if app.suffix == ".app" else app


def profiles_dir(app=APP) -> Path:
    return app / "Contents/Resources/profiles/BBL"


def slicer_version(app=APP) -> str:
    """The version Bambu Studio prints at the top of its help, e.g. 02.08.02.61. It runs in a temporary folder
    because even --help leaves a result.json in the working folder."""
    with tempfile.TemporaryDirectory() as tmp:
        shown = subprocess.run([slicer_binary(app), "--help"], cwd=tmp, capture_output=True, text=True,
                               errors="replace").stdout
    found = re.search(r"BambuStudio-([\d.]+)", shown)
    return found.group(1) if found else "unknown"


def resolved_preset(folder: Path, name: str) -> dict:
    """A system preset with everything it inherits and includes written out.

    The command line doesn't follow a preset's `inherits` chain, so a stock preset loaded as it is slices with
    half its settings at zero (filament density 0, so 0 g). Parents come first, then included templates (the
    X1C's start and end G-code live in those), then the preset's own keys."""
    own = json.loads((folder / f"{name}.json").read_text())
    merged = resolved_preset(folder, own["inherits"]) if own.get("inherits") else {}
    for template in own.get("include", []):
        merged.update(_template_keys(folder, template))
    merged.update(own)
    merged.pop("inherits", None)
    merged.pop("include", None)
    return merged


def _template_keys(folder, name):
    template = json.loads((folder / f"{name}.json").read_text())
    return {key: value for key, value in template.items() if key not in ("name", "instantiation")}


PRINTER_SEQUENCES = ("machine_start_gcode", "machine_end_gcode")


def without_printer_sequences(machine: dict) -> dict:
    """The machine preset with its start and end G-code empty: the printer's own routine, the same for every design."""
    return machine | {key: "" for key in PRINTER_SEQUENCES}


def write_presets(out_dir: Path, profiles=None) -> dict[str, Path]:
    """Each fixed preset, resolved, as a JSON file the command line can load."""
    profiles = profiles or profiles_dir()
    paths = {}
    for kind, name in PRESETS.items():
        preset = resolved_preset(profiles / kind, name)
        if kind == "machine":
            preset = without_printer_sequences(preset)
        paths[kind] = out_dir / f"{kind}.json"
        paths[kind].write_text(json.dumps(preset, indent=1))
    return paths


# ---- reading what the slicer wrote ----

@dataclass
class SlicedPlate:
    print_s: float  # Bambu's "model printing time": moving and extruding
    total_s: float  # its "total estimated time", which adds the start and end G-code (left out here, so about equal)
    filament_mm: float
    filament_g: float
    layers: int


def duration_s(text: str) -> float:
    """Seconds in a Bambu duration such as '1d 2h 3m 4s', '8m 46s' or '45s'."""
    units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    parts = re.findall(r"(\d+(?:\.\d+)?)([dhms])", text)
    if not parts or re.sub(r"[\d.dhms\s]", "", text):
        raise ValueError(f"not a Bambu duration: {text!r}")
    return sum(float(amount) * units[unit] for amount, unit in parts)


def header_value(header: str, label: str) -> str:
    found = re.search(rf"^; {re.escape(label)}\s*:\s*(.+)$", header, re.M)
    if not found:
        raise ValueError(f"the G-code header has no '{label}'")
    return found.group(1).strip()


def _summed(values: str) -> float:
    """A per-filament list such as '1226.18' or '120.5,3.2' as one total."""
    return sum(float(value) for value in values.split(","))


def parse_gcode_header(gcode_head: str) -> SlicedPlate:
    """Time, filament and layers from the header Bambu Studio writes at the top of each plate's G-code."""
    header = gcode_head.split("; HEADER_BLOCK_END")[0]
    times = re.search(r"^; model printing time: (.+?); total estimated time: (.+)$", header, re.M)
    if not times:
        raise ValueError("the G-code header has no printing time")
    return SlicedPlate(print_s=duration_s(times.group(1)), total_s=duration_s(times.group(2)),
                       filament_mm=_summed(header_value(header, "total filament length [mm]")),
                       filament_g=_summed(header_value(header, "total filament weight [g]")),
                       layers=int(header_value(header, "total layer number")))


def slicer_complaint(result_json: Path, stderr: str) -> str:
    """Why a slice failed, from the result.json Bambu writes, else the last line it printed."""
    if result_json.exists():
        result = json.loads(result_json.read_text())
        if result.get("return_code", 0) != 0:
            return f"{result.get('error_string', '').strip()} (code {result['return_code']})"
    lines = [line for line in stderr.splitlines() if line.strip()]
    return lines[-1].strip() if lines else "no G-code written"


def slicer_warning(result_json: Path) -> str:
    if not result_json.exists():
        return ""
    plates = json.loads(result_json.read_text()).get("sliced_plates", [])
    return " | ".join(plate.get("warning_message", "") for plate in plates if plate.get("warning_message"))


# ---- slicing one part ----

@dataclass
class PartJob:
    run: str
    folder: Path
    task: str
    condition: str
    model: str
    trial: int
    verdict: str
    part: str
    role: str
    stl: Path | None
    build_error: str = ""


@dataclass
class PartEstimate:
    run: str
    task: str
    condition: str
    model: str
    trial: int
    verdict: str
    part: str
    role: str
    status: str  # sliced, not_built or not_sliced
    error: str
    warning: str
    print_s: float | None = None
    filament_m: float | None = None
    filament_g: float | None = None
    layers: int | None = None
    height_mm: float | None = None


def on_the_bed(stl: Path, out: Path) -> float:
    """The part moved so its lowest point is on the bed, without turning it. Returns its height."""
    mesh = trimesh.load(stl, force="mesh")
    mesh.apply_translation((0, 0, -mesh.bounds[0][2]))
    mesh.export(out)
    return float(mesh.bounds[1][2])


def slice_command(stl: Path, presets: dict[str, Path], out_dir: Path, data_dir: Path) -> list[str]:
    """Slice one part on plate 1, arranged to the middle of the bed, never turned. Its own data folder, so the
    command line doesn't read or write Bambu Studio's saved settings."""
    return [str(slicer_binary()), "--datadir", str(data_dir), "--debug", "1",
            "--load-settings", f"{presets['machine']};{presets['process']}",
            "--load-filaments", str(presets["filament"]),
            "--orient", "0", "--arrange", "1", "--slice", "0", "--outputdir", str(out_dir), str(stl)]


def slice_part(job_and_presets) -> PartEstimate:
    job, presets = job_and_presets
    estimate = PartEstimate(run=job.run, task=job.task, condition=job.condition, model=job.model, trial=job.trial,
                            verdict=job.verdict, part=job.part, role=job.role, status="not_built", error=job.build_error,
                            warning="")
    if job.stl is None:
        return estimate
    estimate.status = "not_sliced"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        placed = tmp / f"{job.part}.stl"
        estimate.height_mm = round(on_the_bed(job.stl, placed), 2)
        (tmp / "out").mkdir()
        (tmp / "data").mkdir()
        try:
            finished = subprocess.run(slice_command(placed, presets, tmp / "out", tmp / "data"), cwd=tmp,
                                      capture_output=True, text=True, errors="replace", timeout=SLICE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            estimate.error = f"slicing timed out after {SLICE_TIMEOUT_S} s"
            return estimate
        gcode = tmp / "out/plate_1.gcode"
        estimate.warning = slicer_warning(tmp / "out/result.json")
        if finished.returncode != 0 or not gcode.exists():
            estimate.error = slicer_complaint(tmp / "out/result.json", finished.stderr + finished.stdout)
            return estimate
        with gcode.open(errors="replace") as text:
            plate = parse_gcode_header(text.read(4000))
    estimate.status = "sliced"
    estimate.print_s = round(plate.print_s)
    estimate.filament_m, estimate.filament_g = round(plate.filament_mm / 1000, 3), round(plate.filament_g, 2)
    estimate.layers = plate.layers
    return estimate


# ---- the saved trials and their parts ----

def built_parts(folder: Path, sub) -> dict[str, str]:
    """Build the design's parts into folder/parts unless they're there (parts/ isn't committed), the way the
    results page does. Returns each part's build error, empty for a part that built."""
    parts = folder / "parts"
    if all((parts / f"{part.id}.stl").exists() for part in sub.parts):
        return {part.id: "" for part in sub.parts}
    return {part_id: built.error for part_id, built in build_parts(sub, parts).items()}


def jobs_for_trial(run: str, folder: Path, record: TrialRecord) -> list[PartJob]:
    """One job per part of the trial's saved design; none when there's no design."""
    sub_path = folder / "submission.yaml"
    if not sub_path.exists():
        return []
    sub = submission.load(sub_path)
    errors = built_parts(folder, sub)
    jobs = []
    for part in sub.parts:
        stl = folder / "parts" / f"{part.id}.stl"
        error = errors.get(part.id, "") or ("" if stl.exists() else "no mesh")
        jobs.append(PartJob(run=run, folder=folder, task=record.task, condition=record.condition, model=record.model,
                            trial=record.trial, verdict=record.verdict if record.outcome == "submitted" else "error",
                            part=part.id, role=part.role, stl=None if error else stl, build_error=error))
    return jobs


def jobs_for_run(run: str) -> list[PartJob]:
    jobs = []
    for folder, record in TrialRecord.all_in(RUNS / run):
        jobs.extend(jobs_for_trial(run, folder, record))
    return jobs


# ---- per trial ----

@dataclass
class TrialEstimate:
    run: str
    task: str
    condition: str
    model: str
    trial: int
    verdict: str
    final_parts: int
    test_print_parts: int
    parts_not_sliced: int  # when above 0, the totals below are blank: a partial sum would read as the whole
    final_print_s: float | None
    final_filament_m: float | None
    final_filament_g: float | None
    test_print_s: float | None
    test_print_filament_m: float | None
    test_print_filament_g: float | None
    all_print_s: float | None
    all_filament_g: float | None


def _sum(estimates, attribute, digits):
    return round(sum(getattr(estimate, attribute) for estimate in estimates), digits)


def trial_estimate(parts: list[PartEstimate]) -> TrialEstimate:
    """A trial's totals: final parts, test prints (role coupon) and both. Without the printer's start sequence, the
    totals don't depend on how the parts are grouped onto plates."""
    first = parts[0]
    finals = [part for part in parts if part.role == "final"]
    tests = [part for part in parts if part.role == "coupon"]
    unsliced = sum(part.status != "sliced" for part in parts)
    whole = unsliced == 0

    def total(group, attribute, digits):
        return _sum(group, attribute, digits) if whole else None

    return TrialEstimate(
        run=first.run, task=first.task, condition=first.condition, model=first.model, trial=first.trial,
        verdict=first.verdict, final_parts=len(finals), test_print_parts=len(tests), parts_not_sliced=unsliced,
        final_print_s=total(finals, "print_s", 0),
        final_filament_m=total(finals, "filament_m", 3), final_filament_g=total(finals, "filament_g", 2),
        test_print_s=total(tests, "print_s", 0), test_print_filament_m=total(tests, "filament_m", 3),
        test_print_filament_g=total(tests, "filament_g", 2),
        all_print_s=total(parts, "print_s", 0), all_filament_g=total(parts, "filament_g", 2))


def trial_estimates(parts: list[PartEstimate]) -> list[TrialEstimate]:
    by_trial = {}
    for part in parts:
        by_trial.setdefault((part.run, part.task, part.condition, part.model, part.trial), []).append(part)
    return [trial_estimate(group) for group in by_trial.values()]


# ---- writing ----

def write_csv(path: Path, rows, row_type):
    with path.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=[field.name for field in fields(row_type)])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if value is None else value for key, value in asdict(row).items()})


def write_run(run: str, parts: list[PartEstimate]):
    write_csv(RUNS / run / PARTS_CSV, parts, PartEstimate)
    write_csv(RUNS / run / TRIALS_CSV, trial_estimates(parts), TrialEstimate)


def report(run: str, parts: list[PartEstimate]):
    sliced = [part for part in parts if part.status == "sliced"]
    print(f"{run}: {len(parts)} parts, {len(sliced)} sliced", file=sys.stderr)
    for part in parts:
        if part.status != "sliced":
            print(f"  {part.status}: {part.model} t{part.trial} {part.part}: {part.error}", file=sys.stderr)


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="+", help="run folders under results/runs, e.g. pilot-tripod")
    ap.add_argument("--workers", type=int, default=4, help="parts sliced at once")
    return ap.parse_args()


def main():
    args = parse_args()
    if not slicer_binary().exists():
        sys.exit(f"No Bambu Studio at {APP}. Install it, or point BAMBU_STUDIO at the .app or its binary.")
    print(f"Bambu Studio {slicer_version()}, presets: {', '.join(PRESETS.values())}", file=sys.stderr)
    with tempfile.TemporaryDirectory() as tmp:
        presets = write_presets(Path(tmp))
        for run in args.runs:
            jobs = jobs_for_run(run)
            with Pool(args.workers) as pool:
                parts = pool.map(slice_part, [(job, presets) for job in jobs])
            write_run(run, parts)
            report(run, parts)


if __name__ == "__main__":
    main()
