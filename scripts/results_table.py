"""The README's results, computed from the saved runs rather than typed. No model calls.

    uv run python scripts/results_table.py           # print the results and assumptions sections
    uv run python scripts/results_table.py --write   # put both sections in README.md, between their markers
    uv run python scripts/results_table.py --check   # exit 1 if README.md's section isn't what the runs say

Reads every trial's grades.json under results/runs/ (the crash replay and the coupon loop samples keep
none, so they aren't counted here; their own summaries are in docs/). Counts are raw: one to three trials
per model, so they're pilots, never pass rates. tests/test_results_table.py runs --check, so CI fails when
the README's numbers and main's saved runs disagree.
"""
import argparse
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from pbe.assumptions import Assumed
from pbe.runner import tasks as task_files
from pbe.runner.trial_record import TrialRecord

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs"
README = ROOT / "README.md"

VERDICTS = ("pass", "fail", "not graded", "declined")
SMOKE_RUNS = ("cloud-smoke", "cloud-smoke-2")  # one Haiku spacer each, to test a new cloud machine; not results

# Trials that fail on `bridges` alone, but not on a roof with a hole cut through it, so their verdict doesn't
# rest on the holed-roof assumption. Keyed by task, condition, model and trial. tests/test_results_table.py
# rebuilds every such trial's parts and checks this list against bridges.is_holed_roof.
NOT_HOLED_ROOFS = {
    ("nut-knob/M5", "can_ask", "google/gemini-4-argon", 2):
        "the underside of its 30 mm grip overhangs the 16 mm boss below: a ledge whose free edge is the outside",
    ("estoa-light", "can_ask", "deepseek/deepseek-v4-pro-0813", 1):
        "a closed roof over the whole box, 208 mm across: every strand lands, but none spans that far",
    ("estoa-light", "can_ask", "google/gemini-4-argon", 1):
        "its round rim bridges 39 mm over the USB opening; the strands end at the rim's curved outer edge",
}

# Whose words each task's request is, as of issue 35. The tripod's and the Estoa light's were approved by Dan
# before they ran.
WORDING = {
    "tripod-plate": "Dan's own words, approved by Dan",
    "estoa-light": "drafted from Dan's answers, approved by Dan",
    "bearing-wheel": "draft by Claude, not reviewed by Dan: exploratory",
    "nut-knob": "draft, not approved by Dan: exploratory",
    "m5-spacer": "control, draft wording: exploratory",
}


@dataclass
class Tally:
    """What one group of trials came to."""
    verdicts: Counter = field(default_factory=Counter)
    cost: float = 0.0

    @property
    def trials(self) -> int:
        return sum(self.verdicts.values())

    def add(self, record: TrialRecord) -> None:
        self.verdicts[record.verdict] += 1
        self.cost += record.cost_usd


@dataclass(frozen=True)
class Group:
    task: str
    condition: str
    model: str


def family(task: str) -> str:
    return task.split("/")[0]


def counted_records() -> list[TrialRecord]:
    """Every saved trial in a results run, smoke tests left out."""
    found = []
    for run_dir in sorted(path for path in RUNS.iterdir() if path.is_dir() and path.name not in SMOKE_RUNS):
        found += [record for _, record in TrialRecord.all_in(run_dir)]
    return found


def assumed_trials(task: str) -> list[tuple[TrialRecord, Assumed]]:
    """A task's graded trials whose undecided checks were graded under its assumptions (pbe.assumptions)."""
    found = []
    for run_dir in sorted(path for path in RUNS.iterdir() if path.is_dir() and path.name not in SMOKE_RUNS):
        for folder, record in TrialRecord.all_in(run_dir):
            if record.task == task and (assumed := Assumed.load_if_saved(folder)) is not None:
                found.append((record, assumed))
    return found


def word(ok) -> str:
    return "pass" if ok is True else "fail" if ok is False else "not graded"


def checks_table(task: str) -> list[str]:
    """Each check across a task's graded designs: what the records decide, then with the assumptions too."""
    trials = assumed_trials(task)
    if not trials:
        return []
    checks = list(dict.fromkeys(finding.check for record, _ in trials for finding in record.counted_findings))
    lines = [f"Each check across the {len(trials)} graded designs (one verdict per design), on the records alone and then with the assumptions below "
             "(`python -m pbe.assumptions`). A check the records decide never changes.", "",
             "| Check | Pass | Fail | Not graded | With assumptions: pass | fail | not graded |",
             "|---|---|---|---|---|---|---|"]
    worst = {False: 0, None: 1, True: 2}
    for check in checks:
        on_records, assumed = Counter(), Counter()
        for record, under in trials:  # one verdict per design: the worst over its parts, as the trial's verdict takes it
            oks = [f.ok for f in record.counted_findings if f.check == check]
            if not oks:
                continue
            ok = min(oks, key=worst.get)
            on_records[word(ok)] += 1
            assumed[word(next((a.ok for a in under.findings if a.check == check), None) if ok is None else ok)] += 1
        lines.append(f"| {check} | {on_records['pass']} | {on_records['fail']} | {on_records['not graded']} | "
                     f"{assumed['pass']} | {assumed['fail']} | {assumed['not graded']} |")
    verdicts = Counter(under.verdict for _, under in trials)
    lines += ["", f"Verdicts with the assumptions, of {len(trials)} graded designs: {verdicts['pass']} pass, "
              f"{verdicts['fail']} fail, {verdicts['not graded']} not graded."]
    return lines


def tally_by(records: list[TrialRecord], key) -> dict:
    tallies = defaultdict(Tally)
    for record in records:
        tallies[key(record)].add(record)
    return tallies


def count_cells(tally: Tally) -> str:
    other = tally.trials - sum(tally.verdicts[v] for v in VERDICTS)
    cells = [str(tally.verdicts[v]) for v in VERDICTS]
    return " | ".join(cells + [str(other), f"${tally.cost:.2f}"])


def totals_table(records: list[TrialRecord]) -> list[str]:
    by_condition = tally_by(records, lambda record: record.condition)
    lines = ["| Condition | Trials | Pass | Fail | Not graded | Declined | Other | Cost |",
             "|---|---|---|---|---|---|---|---|"]
    for condition, tally in sorted(by_condition.items()):
        lines.append(f"| `{condition}` | {tally.trials} | {count_cells(tally)} |")
    everything = Tally()
    for record in records:
        everything.add(record)
    lines.append(f"| **all** | **{everything.trials}** | {count_cells(everything)} |")
    return lines


def task_table(records: list[TrialRecord]) -> list[str]:
    lines = ["| Condition | Model | Trials | Pass | Fail | Not graded | Declined | Other | Cost |",
             "|---|---|---|---|---|---|---|---|---|"]
    by_group = tally_by(records, lambda record: Group(record.task, record.condition, record.model))
    for group, tally in sorted(by_group.items(), key=lambda item: (item[0].condition, item[0].model)):
        lines.append(f"| `{group.condition}` | {group.model} | {tally.trials} | {count_cells(tally)} |")
    return lines


def section(records: list[TrialRecord]) -> str:
    models = {record.model for record in records}
    per_model = Counter((record.task, record.condition, record.model) for record in records)
    lines = [
        f"{len(records)} trials of {len(models)} models, from the saved runs in `results/runs/` "
        f"(smoke tests left out). Each model ran {min(per_model.values())} to {max(per_model.values())} "
        "times per task and condition, so these are pilots: raw counts, not pass rates, and no ranking. "
        "Other is a trial with no submission or an infrastructure error. Cost is what OpenRouter charged.",
        "",
        *totals_table(records),
    ]
    tasks = sorted({record.task for record in records})
    for task in tasks:
        lines += ["", f"### `{task}` ({WORDING.get(family(task), 'wording status not recorded')})", ""]
        lines += task_table([record for record in records if record.task == task])
        if extra := checks_table(task):
            lines += ["", *extra]
    return "\n".join(lines)


def trial_key(record: TrialRecord) -> tuple:
    return record.task, record.condition, record.model, record.trial


def fails_on_bridges_alone(record: TrialRecord) -> bool:
    return record.verdict == "fail" and record.failed_checks == ["bridges"]


def graded(records: list[TrialRecord], check: str, ok) -> int:
    """How many findings of this check came out `ok` (True, False or None), declined trials left out."""
    return sum(1 for record in records if not record.declined
               for finding in record.findings if finding.check == check and finding.ok is ok)


def assumptions(records: list[TrialRecord]) -> str:
    """The three assumptions already changing results (issue 35), with how many verdicts rest on each."""
    tripod = [record for record in records if record.task == "tripod-plate"]
    tripod_passes = sum(1 for record in tripod if record.verdict == "pass")
    only_bridges = sum(1 for record in records if fails_on_bridges_alone(record) and trial_key(record) not in NOT_HOLED_ROOFS)
    lines = [
        "| Assumption | Check | What rests on it in the saved runs |",
        "|---|---|---|",
        "| The webcam bolt is 10 mm long under its head. Nobody recorded it. | tripod R5 | "
        f"Every tripod R5 verdict ({graded(tripod, 'R5', True)} pass, {graded(tripod, 'R5', False)} fail), "
        f"so all {tripod_passes} tripod passes |",
        "| One 38 mm plate fit the clamp; 37 to 39 mm passes on an estimate of the jaws' travel. | tripod R2 | "
        f"Every graded tripod R2 verdict ({graded(tripod, 'R2', True)} pass, {graded(tripod, 'R2', False)} fail) |",
        "| A roof with the bolt's hole cut through it tangles at the models' shapes and sizes, as it did on the "
        "Arca plate and coupon A's H cell (a 20 mm square with a 6 mm hole, printed once). | `bridges` | "
        f"{only_bridges} trials that fail on `bridges` alone, on a roof with a hole cut through it (Dan's call: they fail) |",
    ]
    for task in sorted({record.task for record in records}):
        lines += assumption_rows(task)
    return "\n".join(lines)


def assumption_rows(task: str) -> list[str]:
    """A task's stated assumptions (requirements.yaml), each with the verdicts it decides. These never change
    the verdicts above them: they grade only what the records leave undecided, and are reported apart."""
    rows = []
    trials = assumed_trials(task)
    for requirement in task_files.load(task).requirements:
        if requirement.assume is None:
            continue
        decided = Counter(word(finding.ok) for _, under in trials for finding in under.findings
                          if finding.check == requirement.id and finding.ok is not None)
        rows.append(f"| {requirement.assume.text} Source: {requirement.assume.source}. | {task} {requirement.id} | "
                    f"Graded apart: {decided['pass']} pass, {decided['fail']} fail of the {task} designs it decides |")
    return rows


def markers(name: str) -> tuple[str, str]:
    return (f"<!-- {name}:start (written by scripts/results_table.py; don't edit by hand) -->", f"<!-- {name}:end -->")


def replace_section(text: str, name: str, new: str) -> str:
    start, end = markers(name)
    if start not in text or end not in text:
        raise SystemExit(f"README.md has no {name} markers: add {start!r} and {end!r}")
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    return f"{before}{start}\n{new}\n{end}{after}"


def readme_with(text: str, records: list[TrialRecord]) -> str:
    """README.md's text with both computed sections brought up to date."""
    text = replace_section(text, "results", section(records))
    return replace_section(text, "assumptions", assumptions(records))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="update README.md's computed sections")
    parser.add_argument("--check", action="store_true", help="exit 1 if README.md's computed sections are out of date")
    args = parser.parse_args()
    records = counted_records()
    if not (args.write or args.check):
        print(section(records), assumptions(records), sep="\n\n")
        return
    text = README.read_text()
    updated = readme_with(text, records)
    if args.check:
        if updated != text:
            sys.exit("README.md's results don't match results/runs/: run uv run python scripts/results_table.py --write")
        print("README.md's results and assumptions match results/runs/")
        return
    README.write_text(updated)
    print("README.md's results and assumptions updated")


if __name__ == "__main__":
    main()
