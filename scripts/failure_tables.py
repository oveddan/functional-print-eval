"""docs/reference.md's counts of what went wrong and what wasn't graded, task by task, from the saved runs, and the
not-graded list in README.md too.
No model calls.

    uv run python scripts/failure_tables.py           # print the sections
    uv run python scripts/failure_tables.py --write   # put them in docs/reference.md, between their markers
    uv run python scripts/failure_tables.py --check   # exit 1 if docs/reference.md's sections are out of date

Each failing or undecided check is diagnosed as the results page does it (scripts/results_page.py: `issues_of`),
and counted once per trial. Whether a failed bridge check is a roof with a hole cut through it is read from the
part's mesh (`bridges.is_holed_roof`). Meshes aren't committed (parts/ is ignored), so the parts found holed are
kept in results/holed_roofs.json: --write reads the meshes on this machine and updates it, and --check reads only
that file, so it runs where no part has been built. The estoa-light task is left out: it has its own section.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import results_page  # noqa: E402  the results page's diagnoses, so both say the same thing
from results_table import SMOKE_RUNS  # noqa: E402

from pbe.runner.trial_record import TrialRecord  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs"
DOC = ROOT / "docs/reference.md"
README = ROOT / "README.md"  # carries the not-graded list too
README_NOT_GRADED = "not-graded (README)"  # the same list, its pictures linked from the repository's root
HOLED = ROOT / "results/holed_roofs.json"
FAMILIES = ["tripod-plate", "bearing-wheel", "nut-knob", "m5-spacer"]
HEADINGS = {"tripod-plate": "`tripod-plate`", "bearing-wheel": "`bearing-wheel`", "nut-knob": "`nut-knob` (M3 and M5)",
            "m5-spacer": "`m5-spacer`"}

# the results page's diagnosis, in the words the reference uses
WRONG = {
    "Its code didn't run": "Code didn't run",
    "Geometry slip: a part in pieces": "A part in pieces",
    "Geometry slip: a broken shape": "A broken shape",
    "A roof or ledge too wide to bridge, with no hole through it": "A roof or ledge too wide to bridge, with no hole through it",
    "Nut pocket a size the prints don't take": "Nut pocket a size the prints don't take",
    "Geometry slip: the pocket is closed": "The pocket is closed, so the nut can't be pressed in",
    "Bearing seat a size the prints don't take": "Bearing seat a size the prints don't take",
    "Wheel geometry": "Other wheel geometry",
    "Bolt doesn't reach far enough into the camera": "Bolt doesn't reach far enough into the camera",
    "Head recess too small (a CAD slip)": "Head recess too small for the bolt's head",
    "Geometry slip: straight sides, nothing for the clamp to grip": "Straight sides, nothing for the clamp's lips to grip",
    "Geometry slip: dovetail upside down": "Dovetail upside down: the bolt head's recess is on the camera's side",
    "Geometry slip: no usable bolt hole": "No usable bolt hole",
    "Test coupon labelled as a final part": "Its test print labelled as a final part",
}
HOLED_ROOF = {"tripod-plate": "A roof with the bolt's hole cut through it (`bridges`)",
              "bearing-wheel": "A roof with the bolt's hole cut through it (`bridges`), over the seat that opens at the bed",
              "nut-knob": "A roof with the bolt's hole cut through it", "m5-spacer": "A roof with the bolt's hole cut through it"}
DECLINED = {"tripod-plate": "Declined: handed in only a test print, because the clamp's size isn't known"}
NO_DESIGN = "No design handed in"

# not graded: (the reference's words, the print that would settle it)
NOT_GRADED = {
    "Not graded: a nut pocket with ribs or clips, never printed":
        ("A nut pocket with crush ribs or clips",
         "Pockets with ribs, clips or relief beside plain ones. Each model's ribs differ, so one print settles only designs like it"),
    "Not graded: head recess under 5 mm deep, never printed":
        ("A tripod head recess under 5 mm deep", "Recesses 3, 4 and 4.5 mm deep for the 5 mm head"),
    "Not graded: a roof ledge 1.5 to 3 mm wide, never printed":
        ("A roof ledge 1.5 to 3 mm wide", "Ring roofs 1.5 to 3 mm wide around a bolt hole"),
    "Not graded: bolt hole between 6.35 and 6.8 mm, never printed":
        ("A tripod bolt hole between 6.35 and 6.8 mm", "Bolt holes at 6.5 and 6.6 mm"),
    "Not graded: plate width outside 37 to 39 mm (jaw travel not recorded)":
        ("A plate width outside 37 to 39 mm", "Dovetail plates from 34 to 45 mm tried in the clamp"),
    "Not graded: wheel bolt hole between 8.0 and 8.4 mm, never printed":
        ("A wheel bolt hole between 8.0 and 8.4 mm", "Holes at 8.1, 8.2 and 8.3 mm on an M8"),
    "Not graded: bearing seat between printed sizes or ribbed":
        ("A bearing seat between printed sizes, or ribbed", "Seats at 22.05, 22.4 and 22.5 mm, and lobed seats"),
    "Not graded: bearing a little proud, or no shoulder, never printed":
        ("Bearings a little proud, or no shoulder", "Wheels with bearings 0.2 to 0.6 mm proud, and a bore with no shoulder"),
    "Not graded: a nut pocket tighter than any printed":
        ("A nut pocket tighter than any printed", "M5 pockets at -0.15, -0.10 and -0.05 mm"),
    "Not graded: a nut pocket looser than any printed":
        ("A nut pocket looser than any printed", "Pockets more than 0.3 mm over the nut, beyond coupon B's steps"),
    "Not graded: its test coupon's pockets are ribbed or sizes no print settled":
        ("A test print whose pockets are ribbed or unsettled", "The ribbed pockets above, and coupon B2's finer steps"),
    "Not graded: a nut pocket between printed sizes":
        ("A nut pocket between printed sizes", "Coupon B2's finer steps"),
    "Not graded: no recorded print settles this nut pocket":
        ("A nut pocket no recorded print settles", "A print of that pocket"),
    "Not graded: a pocket shape the checker can't read":
        ("A pocket shape the checker can't read", "None: the checker needs fixing"),
}


def trial_key(run: str, record: TrialRecord) -> str:
    return f"{run}|{record.task}|{record.condition}|{record.model}|{record.trial}"


def holed_roofs(run: str, folder: Path, record: TrialRecord, cache: dict, from_meshes: bool) -> set:
    """The parts whose failed bridge check is a roof with a hole through it: from the meshes on --write,
    from results/holed_roofs.json otherwise."""
    failed = {f.part for f in record.counted_findings if f.check == "bridges" and f.ok is False}
    key = trial_key(run, record)
    if not failed:
        cache.pop(key, None)
        return set()
    meshes = all((folder / "parts" / f"{part}.stl").exists() for part in failed)
    if from_meshes and meshes:
        found = results_page.holed_roof_parts(folder, record)
        cache[key] = sorted(found)
        return found
    if key not in cache:
        raise SystemExit(f"{key}: a failed bridge check with no mesh and no entry in {HOLED.relative_to(ROOT)}; "
                         "build its parts (scripts/results_page.py) and run --write")
    return set(cache[key])


def tally(from_meshes: bool, save_cache: bool = False) -> tuple[Counter, dict, dict, dict]:
    """Trials per family, what went wrong per family, what wasn't graded, and each family's verdicts."""
    audit = json.loads(results_page.AUDIT.read_text())
    cache = json.loads(HOLED.read_text()) if HOLED.exists() else {}
    trials, verdicts = Counter(), defaultdict(Counter)
    wrong, not_graded = defaultdict(Counter), Counter()
    for run_dir in sorted(path for path in RUNS.iterdir() if path.is_dir() and path.name not in SMOKE_RUNS):
        for folder, record in TrialRecord.all_in(run_dir):
            family = record.task.split("/")[0]
            if family not in FAMILIES:
                continue
            trials[family] += 1
            verdicts[family][record.verdict] += 1
            holed = holed_roofs(run_dir.name, folder, record, cache, from_meshes)
            issues = results_page.issues_of(run_dir.name, record, audit.get(trial_key(run_dir.name, record)), holed)
            labels = set()
            for issue in issues:
                name = issue["family"]
                if name in NOT_GRADED:
                    continue
                if name == "A roof with the bolt's hole cut through it":
                    labels.add(HOLED_ROOF[family])
                elif name.startswith("Declined"):
                    labels.add(DECLINED.get(family, "Declined: handed in only a test print"))
                else:
                    labels.add(WRONG.get(name, name))
            if record.verdict not in ("pass", "fail", "not graded", "declined"):
                labels.add(NO_DESIGN)
            wrong[family].update(labels)
            not_graded.update({issue["family"] for issue in issues if issue["family"] in NOT_GRADED})
    if save_cache:
        HOLED.write_text(json.dumps(dict(sorted(cache.items())), indent=1) + "\n")
    return trials, wrong, not_graded, verdicts


def ranked(counts: Counter) -> list[tuple[str, int]]:
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def family_section(family: str, trials: Counter, wrong: dict, verdicts: dict) -> str:
    lines = [f"### {HEADINGS[family]}: {trials[family]} trials", ""]
    v = verdicts[family]
    if family == "m5-spacer":
        lines.append(f"The control. {v['pass']} of {trials[family]} trials pass.")
        return "\n".join(lines)
    lines += ["| What went wrong | Trials |", "|---|---|"]
    lines += [f"| {label} | {count} |" for label, count in ranked(wrong[family])]
    if family == "nut-knob":
        lines += ["", f"Most knob trials that didn't pass weren't failed: {v['pass']} pass, {v['fail']} fail and "
                      f"{v['not graded']} are not graded, mostly for the pockets below."]
    return "\n".join(lines)


EXAMPLES = ROOT / "docs/media/not-graded/examples.json"  # one render per reason (scripts/not_graded_figures.py)


def example_cell(name: str, media: str) -> str:
    """A small render of one design that hit this reason, with its model and trial, or nothing if none is drawn."""
    examples = json.loads(EXAMPLES.read_text()) if EXAMPLES.exists() else {}
    if name not in examples:
        return ""
    found = examples[name]
    task = found["task"].replace("nut-knob/", "knob ").replace("-", " ")
    return (f'<img src="{media}/not-graded/{found["image"]}" width="160" alt="{NOT_GRADED[name][0]}: '
            f'{found["model"]}, {task}, trial {found["trial"]}"><br><sub>{found["model"]}, {task}, trial {found["trial"]}</sub>')


def not_graded_section(not_graded: Counter, media: str = "media") -> str:
    lines = ["| Not graded because | Example | Trials | The print that would settle it |", "|---|---|---|---|"]
    for name, count in ranked(not_graded):
        label, settle = NOT_GRADED[name]
        lines.append(f"| {label} | {example_cell(name, media)} | {count} | {settle} |")
    return "\n".join(lines)


def sections(from_meshes: bool, save_cache: bool = False) -> dict[str, str]:
    trials, wrong, not_graded, verdicts = tally(from_meshes, save_cache)
    found = {f"wrong-{family}": family_section(family, trials, wrong, verdicts) for family in FAMILIES}
    found["not-graded"] = not_graded_section(not_graded)
    found[README_NOT_GRADED] = not_graded_section(not_graded, "docs/media")  # README.md sits a folder up from docs/
    return found


def markers(name: str) -> tuple[str, str]:
    return (f"<!-- {name}:start (written by scripts/failure_tables.py; don't edit by hand) -->", f"<!-- {name}:end -->")


def doc_with(text: str, found: dict[str, str], doc: Path = DOC) -> str:
    for name, body in found.items():
        start, end = markers(name)
        if start not in text or end not in text:
            raise SystemExit(f"{doc.relative_to(ROOT)} has no {name} markers: add {start!r} and {end!r}")
        before, rest = text.split(start, 1)
        text = f"{before}{start}\n{body}\n{end}{rest.split(end, 1)[1]}"
    return text


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    found = sections(from_meshes=not args.check, save_cache=args.write)
    if not (args.write or args.check):
        print("\n\n".join(found.values()))
        return
    readme_list = found.pop(README_NOT_GRADED)
    docs = {DOC: found, README: {"not-graded": readme_list}}
    updated = {doc: doc_with(doc.read_text(), sections_for, doc) for doc, sections_for in docs.items()}
    if args.check:
        stale = [doc.relative_to(ROOT).as_posix() for doc, text in updated.items() if text != doc.read_text()]
        if stale:
            sys.exit(f"{', '.join(stale)}: failure counts don't match results/runs/: run scripts/failure_tables.py --write")
        print("docs/reference.md's and README.md's failure counts match results/runs/")
        return
    for doc, text in updated.items():
        doc.write_text(text)
    print("docs/reference.md's and README.md's failure counts updated")


if __name__ == "__main__":
    main()
