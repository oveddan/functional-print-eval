"""The data for the public results site: every saved trial and replay, as JSON a static page reads. No model calls
and no CadQuery builds, so it runs from a clean clone in under a minute.

    uv run python scripts/results_site.py

Writes results/local/site/ (git-ignored):
- data/index.json: what the list and filter views need for every trial, the groups and tasks, and a `scorecard`
  block with the README's aggregates, computed by scripts/scorecard.py's own functions.
- data/trials/<slug>.json: one trial's detail (findings and their diagnoses, test prints and the simulated person's
  answers, measurements, cost, tokens, slicer estimates, the design's code, a transcript excerpt), loaded on demand.
- data/system_prompts.json: the system prompts, once each; a transcript excerpt points at one by its hash.
- the frontend files from scripts/results_site/, copied as they are.

What is read, and from where:
- verdicts, first prints, second prints and test-first trials: scripts/scorecard.py (rows(), second_print(), Trial),
  so the site's counts and the README's agree; tests/test_results_site.py checks that they do;
- a diagnosis for each check that didn't pass: scripts/results_page.py (issues_of), with whether a failed bridge check
  is a roof with the bolt's hole cut through it read from results/holed_roofs.json rather than from meshes;
- the task's request: scripts/gallery.py (brief_of); what each check means: tasks/<family>/requirements.yaml;
- renders and meshes: scripts/results_site_media.json, written by another script, and optional;
- a drawn view of each failing or ungraded check: scripts/results_site_views.json (scripts/results_site_views.py), optional;
  with, as `view.audit`, an LLM judge's answer to whether it shows the failure legibly: scripts/results_site_view_audit.json
  (scripts/results_site_view_audit.py), optional.

Nothing here is printed. A test print's answer comes from the simulated person, who answers only from Dan's recorded
prints (or, for a roof with a hole through it, the bridge check's prediction); "not graded" is never a pass.
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import failure_tables  # noqa: E402  the README's not-graded table: its reasons and grouping
import gallery  # noqa: E402  brief_of, FRONTIER
import results_page  # noqa: E402  issues_of, KIND, HELP: the same diagnoses as the older results page
import scorecard  # noqa: E402  the README's counting rules

import yaml  # noqa: E402

from pbe.assumptions import Assumed  # noqa: E402
from pbe.runner import coupon_loop, crash_replay, measure  # noqa: E402
from pbe.runner import tasks as task_files  # noqa: E402
from pbe.runner.trial_record import CheckResult, ModelCall, TrialRecord  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs"
OUT = ROOT / "results/local/site"
FRONTEND = Path(__file__).with_name("results_site")
MEDIA = Path(__file__).with_name("results_site_media.json")
VIEWS = Path(__file__).with_name("results_site_views.json")
VIEW_AUDIT = Path(__file__).with_name("results_site_view_audit.json")
HOLED = ROOT / "results/holed_roofs.json"
REPO = "https://github.com/oveddan/functional-print-eval/blob/"
SCHEMA_VERSION = 3

FIRST_PRINT_RUNS = ("pilot-tripod", "pilot-wheel", "pilot-nut-knob", "pilot-nut-knob-2")  # can_ask on the four tasks
ESTOA_RUN = "pilot-estoa"
SECOND_PRINT_RUNS = ("loop-all", "loop-estoa")  # the feedback arm is the second print of the trial it replays
LOOP_ARMS = ("feedback", "neutral")  # a baseline arm is the replayed design regraded: shown inside its replay

# what the reader sees for each task; scorecard.TASKS keeps the scorecard's own short names
TASK_NAMES = {
    "tripod-plate": "Tripod plate", "bearing-wheel": "Closet door wheel", "nut-knob/M3": "Hand knob, M3",
    "nut-knob/M5": "Hand knob, M5", "estoa-light": "Estoa light box (harder)", "m5-spacer": "M5 spacer (control)",
}
TASK_SHORT = {"tripod-plate": "Tripod", "bearing-wheel": "Wheel", "nut-knob/M3": "Knob M3", "nut-knob/M5": "Knob M5",
              "estoa-light": "Estoa box", "m5-spacer": "Spacer"}
HEADLINE_TASKS = (*scorecard.TASKS, scorecard.HARDER[0])
EXTRA_SHORT = {"x-ai/grok-4.7": "Grok 4.7", "google/gemini-4-carbon": "Gemini 4 Carbon"}

CHECK_TITLES = {  # a few plain words per check, so a page can show titles and keep ids secondary
    "*": {"builds": "Code runs", "connected_bodies": "Each part is one piece", "bed_fit": "Fits the printer's bed",
          "bridges": "Overhangs can be bridged"},
    "tripod-plate": {"R1": "There's a plate", "R2": "Fits the tripod's clamp", "R3": "Bolt goes through, head on the clamp side",
                     "R4": "Bolt head fits its recess", "R5": "Bolt reaches the camera"},
    "bearing-wheel": {"R1": "Size of the old wheel", "R2": "Room for both bearings", "R3": "Bearings press in and stay",
                      "R4": "M8 bolt goes through"},
    "nut-knob": {"R1": "One printed part", "R2": "Right size across", "R3": "Hex pocket holds the nut",
                 "R4": "Nut presses in and stays", "R5": "Bolt passes through"},
    "estoa-light": {"R1": "Disk screws go into the box", "R2": "Disk screws hold safely", "R3": "USB-C plug reaches the port",
                    "R4": "Heat-set inserts sit in proven posts", "R5": "Electronics fit inside", "R6": "Hangs on the wall screws",
                    "R7": "No screw sticks out the back"},
    "m5-spacer": {"R1": "One printed part", "R2": "Right length and width", "R3": "M5 bolt clears the hole", "R4": "Round"},
}

# the generic checks every part gets (pbe/graders/checks.py), in a reader's words
GENERIC_CHECKS = {
    "builds": "The part's code runs and produces a solid.",
    "connected_bodies": "Each printed part is one connected body; a test print may be several pieces if all rest on the bed.",
    "bed_fit": "The part, as oriented for printing, fits the printer's 256 x 256 x 256 mm build volume.",
    "bridges": "Every overhang that needs a bridge can be bridged (its strands land on solid at both ends), or the "
               "design says to print it with supports.",
}

VERDICTS = {  # the site's verdict words, and what each means
    "pass": "Every counted check passes on Dan's recorded prints.",
    "fail": "At least one counted check fails.",
    "not graded": "No recorded print decides at least one check, and none fails. Never counted as a pass.",
    "declined": "The model handed in no final part on purpose (for example only a test print). Neither a pass nor a fail; never counted as a pass.",
    "no design": "The model never handed in a design (it ran out of turns or every reply stopped at the token limit).",
    "error": "An infrastructure stop (for example out of API credit), not a result of the model's.",
}

# what a line of the simulated person's answer rests on (coupon_loop.Basis), in a reader's words
BASIS_LABELS = {
    "coupon B record": "Dan's recorded test print B (nut pockets)",
    "coupon E record": "Dan's recorded test print E (bearing seats)",
    "tighter than a record": "Tighter than a recorded test print that wouldn't take the part, so it won't either",
    "bridge check prediction": "The bridge check's prediction, worded as the tangled roof on Dan's test print A: a prediction, not a recorded print",
    "no record": "No recorded print decides this, so the person can't say",
    "build error": "The part's code didn't build",
    "tripod plate record": "Dan's recorded tripod plate prints",
    "Estoa record": "Dan's recorded Estoa test prints",
    "Dan's calipers": "Dan's caliper measurement",
    "geometry": "Read from the design's geometry",
}
CANT_TELL = "can't tell"  # the phrase scorecard.rows() looks for in a test print's answer

@dataclass(frozen=True)
class Group:
    """One set of trials the reader can pick, in words for a public reader; the raw ids stay in `runs`."""
    label: str
    description: str
    category: str  # headline, control or pilot, infrastructure check, or replay study
    runs: tuple[str, ...]
    condition_key: str | None  # the runner's condition id, e.g. can_ask; None for replays


HEADLINE, PILOT, INFRA, REPLAY = "headline", "control or pilot", "infrastructure check", "replay study"
HEADLINE_GROUPS = {
    "first": Group("First print", "The model can ask the person for measurements, then hands in one design. It can't "
                   "ask for test prints.", HEADLINE, ("pilot-tripod", "pilot-wheel", "pilot-nut-knob", "pilot-nut-knob-2",
                                                       "pilot-estoa"), "can_ask"),
    "second": Group("Second print, after hearing how the first came out", "The same conversation, continued with one "
                    "more message in which the simulated person says how everything in the first design came out, "
                    "using only Dan's recorded prints. The model then hands in a revised design, graded with its test "
                    "prints left out.", HEADLINE, ("loop-all", "loop-estoa"), None),
    "test_first": Group("Can ask for test prints first", "The model can ask the person to print small test pieces "
                        "before its final design, and hears how each came out, using only Dan's recorded prints.",
                        HEADLINE, ("test-first",), "can_test"),
}
# the groups outside the three headline conditions: a one-line, honest label each
OTHER_GROUPS = {
    "first-unlisted": Group("Grok 4.7's first prints", "First prints on the scored tasks from Grok 4.7, which has one "
                            "trial per task: too few to list in the scorecard (it was too expensive to run ten).",
                            PILOT, ("pilot-tripod", "pilot-nut-knob"), "can_ask"),
    "pilot-spacer": Group("M5 spacer (control)", "A simple control task every model is expected to pass: up to five "
                          "first prints per model. Not in the four-task totals.", PILOT, ("pilot-spacer",), "can_ask"),
    "pilot-tripod-given": Group("Tripod plate, every measurement given", "One trial per model where every recorded "
                                "measurement was stated up front instead of the model having to ask for it.",
                                PILOT, ("pilot-tripod-given",), "all_given"),
    "pilot-code": Group("Tripod plate, model can run code", "Three trials per model where the model could run Python "
                        "in a sandbox before handing in, and a design whose code didn't run was sent back.",
                        PILOT, ("pilot-code",), "can_run_code"),
    "pilot-code-smoke": Group("Running code: setup check", "One Haiku 5.5 spacer trial to check the sandbox that lets "
                              "a model run code.", INFRA, ("pilot-code-smoke",), "can_run_code"),
    "cloud-smoke": Group("Cloud machine check", "One Haiku 5.5 spacer trial to check a new cloud machine; not a result.",
                         INFRA, ("cloud-smoke",), "can_ask"),
    "cloud-smoke-2": Group("Cloud machine check 2", "One Haiku 5.5 spacer trial to check a second cloud machine; not "
                           "a result.", INFRA, ("cloud-smoke-2",), "can_ask"),
    "pilot-estoa-carbon": Group("Estoa light box on Gemini 4 Carbon", "One trial on a model released after the lineup "
                                "was fixed, and the first run told the printer has no supports; not comparable with "
                                "the other Estoa trials.", PILOT, ("pilot-estoa-carbon",), "can_ask"),
    "pilot-test-first": Group("Test prints first: pilot", "The first 12 trials where the model could ask for test "
                              "prints (6 models, M3 knob and wheel), run before the full set and kept apart from it.",
                              PILOT, ("pilot-test-first",), "can_test"),
    "pilot-test-first-neutral": Group("Test prints first: pilot with neutral wording", "6 trials whose prompt didn't "
                                      "say test prints save time and filament; kept apart and out of the tables.",
                                      PILOT, ("pilot-test-first-neutral",), "can_test"),
    "crash-replay": Group("Retry after a build error", "Each of the 10 designs whose code crashed, sent back once with "
                          "its build error, and the design that came back graded.", REPLAY, ("crash-replay",), None),
    "loop-sample": Group("Second print study, first sample", "12 knob and wheel trials with a test print, each "
                         "continued twice: once told how its prints came out, once only asked to take another look.",
                         REPLAY, ("loop-sample",), None),
    "loop-sample-2": Group("Second print study, second sample", "The same 12 trials as the first sample, continued "
                           "afresh both ways.", REPLAY, ("loop-sample-2",), None),
    "loop-tripod": Group("Second print study, tripod plates", "24 tripod plates with a roof the bolt's hole cuts "
                         "through, each continued twice: once told how the printed plate came out, once only asked to "
                         "take another look.", REPLAY, ("loop-tripod",), None),
    "loop-estoa-neutral": Group("Estoa light box: second look without a report", "The comparison for the Estoa second "
                                "prints: the model is only asked to take another look, not told how the box came out.",
                                REPLAY, ("loop-estoa",), None),
}
CONDITION_LABELS = {"can_ask": "can ask for measurements", "can_test": "can ask for test prints first",
                    "all_given": "every measurement given", "can_run_code": "can run code"}

INDEX_CAP_SUMMARY = 240  # characters of the one-line summary in index.json
CAP = {"code": 12000, "manual": 3000, "note": 2000, "first_user": 6000, "user": 2500, "content": 2500,
       "reasoning": 1500, "tool": 1500, "args": 1500, "transcript_code": 3000, "submit_code": 600, "detail": 1200}
MAX_EXCERPT_MESSAGES = 90  # a longer transcript keeps its first 60 and last 30 entries
REDACTIONS = [(re.compile(r"/(Users|home)/[^/\s\"']+"), "~"),
              (re.compile(r"sk-(or|ant)-[A-Za-z0-9_-]{10,}"), "[redacted key]"),
              # a provider's error text can name the account that made the call
              (re.compile(r"\buser_[A-Za-z0-9]{12,}"), "[redacted account id]")]


# ---- what a trial or replay is ----

@dataclass
class Graded:
    """A loop arm or a crash replay as results_page.issues_of reads a trial: findings, but no declined verdict."""
    task: str
    model: str
    trial: int
    findings: list[CheckResult]
    declined: str | None = None

    @property
    def counted_findings(self) -> list[CheckResult]:
        return [finding for finding in self.findings if not finding.test_print]


@dataclass
class Entry:
    """One row of the site: a trial (grades.json), a loop arm (loop.json) or a crash replay (replay.json)."""
    id: str  # its folder, relative to results/runs
    kind: str  # trial, loop_arm or crash_replay
    group: str
    run: str
    task: str
    condition: str
    model: str
    trial: int
    verdict: str
    summary: str
    counted: bool
    excluded_reason: str | None
    folder: Path
    record: object  # TrialRecord, LoopRecord or ReplayRecord
    replays: str | None = None  # the trial a loop arm or crash replay replays
    arm: str | None = None
    after_feedback: dict | None = None  # a first print: the verdict the scorecard counts after its second print
    second_print: str | None = None  # a first print: the id of its second print, if replayed
    cant_tell: bool = False  # some answer the simulated person gave was "I can't tell you how that one came out"
    extra: dict = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return slug_of(self.id)


def slug_of(entry_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", entry_id.replace("/", "--"))


def group_label(key: str) -> str:
    found = HEADLINE_GROUPS.get(key) or OTHER_GROUPS.get(key)
    return found.label if found else key


def short_name(model: str) -> str:
    return scorecard.SHORT.get(model) or EXTRA_SHORT.get(model) or model


def trial_key(run: str, task: str, condition: str, model: str, trial: int) -> str:
    """The key results_page_audit.json and holed_roofs.json use."""
    return f"{run}|{task}|{condition}|{model}|{trial}"


def site_verdict(saved: str) -> str:
    """A record's verdict in the site's words."""
    return {"no_submission": "no design", "token_limit": "no design", "saved": "not graded"}.get(saved, saved)


def short_error(error: str | None) -> str:
    if not error:
        return "no error text saved"
    if "HTTP 402" in error:
        return "out of OpenRouter credit (HTTP 402)"
    return clip(error.splitlines()[0], 160)


def checks_text(checks: list[str]) -> str:
    return ", ".join(dict.fromkeys(checks))


def check_state(finding: CheckResult) -> str:
    """pass, fail, not graded, or not reached: ungraded only because an earlier failure blocked it (results_page's
    CONSEQUENCE phrases, such as "didn't build"). Reader wording only: the verdict and every count stay as they are."""
    if finding.ok is True:
        return "pass"
    if finding.ok is False:
        return "fail"
    if any(phrase in finding.detail for phrase in results_page.CONSEQUENCE):
        return "not reached"
    return "not graded"


def undecided_text(findings) -> str:
    """The checks no recorded print decides, leaving out those an earlier failure blocked (unless that's all there is)."""
    undecided = [f for f in findings if f.ok is None]
    genuine = [f.check for f in undecided if check_state(f) == "not graded"]
    return checks_text(genuine or [f.check for f in undecided]) or "a check"


def trial_summary(record: TrialRecord) -> str:
    verdict = site_verdict(record.verdict)
    if verdict == "pass":
        return "pass: every counted check passes on the recorded prints"
    if verdict == "fail":
        return f"fail: {checks_text(record.failed_checks)}"
    if verdict == "not graded":
        return f"not graded: no recorded print decides {undecided_text(record.counted_findings)}"
    if verdict == "declined":
        return reader_words(f"declined: {record.declined}")
    if verdict == "error":
        return f"error: {short_error(record.error)}"
    return f"no design: {record.turns} turns and no design handed in" + (f" ({short_error(record.error)})" if record.error else "")


def arm_verdict(record) -> str:
    """A loop arm's or crash replay's verdict, read from its summary as scorecard.second_print reads it."""
    summary = coupon_loop.LoopRecord.summary(record)  # uses only outcome, findings and all_pass, which both records have
    word = next((word for word in ("pass", "fail", "not graded") if summary.startswith(word)), summary)
    if word == "submitted":  # handed in, but no check saved
        return "not graded"
    return site_verdict(word)


def arm_summary(record) -> str:
    verdict = arm_verdict(record)
    failed = [f.check for f in record.findings if f.ok is False]
    if verdict == "pass":
        return "pass: every counted check passes on the recorded prints"
    if verdict == "fail":
        return f"fail: {checks_text(failed)}"
    if verdict == "not graded":
        return f"not graded: no recorded print decides {undecided_text(record.findings)}"
    if verdict == "error":
        return f"error: {short_error(record.error)}"
    return f"no design: the turn ended ({record.outcome}) with no design handed in"


# ---- finding every trial ----

def first_print_group(run: str, record: TrialRecord, listed: set[str]) -> tuple[str, bool, str | None]:
    """(group, counted, why not counted) for a trial in a run of grades.json files."""
    if run in FIRST_PRINT_RUNS and record.condition == "can_ask" and record.task in scorecard.TASKS:
        if record.model in listed:
            return "first", True, None
        return "first-unlisted", False, f"{short_name(record.model)} has too few trials to be listed (scorecard needs {scorecard.MIN_TRIALS} per task)"
    if run == ESTOA_RUN and record.condition == "can_ask":
        return "first", True, None  # the Estoa line (scorecard.estoa_line) counts every one
    if run == scorecard.TEST_FIRST:
        if record.outcome == "error":
            return "test_first", False, f"infrastructure error, not a result: {short_error(record.error)}"
        if record.model not in listed:
            return "test_first", False, f"{short_name(record.model)} isn't listed in the scorecard"
        return "test_first", True, None
    return run, False, group_label(run) + ": not in the headline counts"


def trial_entries(listed: set[str], sliced: dict) -> list[Entry]:
    entries = []
    for run_dir in sorted(path for path in RUNS.iterdir() if path.is_dir()):
        for folder, record in TrialRecord.all_in(run_dir):
            group, counted, reason = first_print_group(run_dir.name, record, listed)
            entry = Entry(id=folder.relative_to(RUNS).as_posix(), kind="trial", group=group, run=run_dir.name,
                          task=record.task, condition=record.condition, model=record.model, trial=record.trial,
                          verdict=site_verdict(record.verdict), summary=trial_summary(record), counted=counted,
                          excluded_reason=reason, folder=folder, record=record)
            entry.cant_tell = any(CANT_TELL in line["text"] for test in record.test_prints
                                  for lines in test["reply"].values() for line in lines)
            if group == "first":
                entry.after_feedback = (after_feedback(folder, record, sliced) if record.task in scorecard.TASKS
                                        else estoa_after_feedback(folder, record))
            entries.append(entry)
    return entries


def after_feedback(folder: Path, record: TrialRecord, sliced: dict) -> dict:
    """The verdict the scorecard's "after feedback" column counts for this first print, by scorecard's own Trial."""
    first = scorecard.Print(record.verdict, record.cost_usd or 0.0, None, None)
    second, cant_tell = scorecard.second_print(folder, record, sliced)
    trial = scorecard.Trial(first, 0, second, cant_tell)
    final = trial.final(after=True)
    return {"verdict": site_verdict(final.verdict), "passed": trial.passed(after=True),
            "from": "first" if final is first else "second", "replayed": second is not None}


def estoa_after_feedback(folder: Path, record: TrialRecord) -> dict:
    """The Estoa light's equivalent, from loop-estoa's feedback arm, counted as scorecard.estoa_line counts it."""
    arm = RUNS / "loop-estoa" / folder.relative_to(RUNS) / "feedback"
    replay = coupon_loop.LoopRecord.load(arm) if (arm / coupon_loop.FILE_NAME).exists() else None
    if replay is None or replay.outcome == "error" or record.verdict == "pass":
        verdict = site_verdict(record.verdict)
        return {"verdict": verdict, "passed": verdict == "pass", "from": "first", "replayed": replay is not None}
    verdict = arm_verdict(replay)
    return {"verdict": verdict, "passed": verdict == "pass", "from": "second", "replayed": True}


def loop_entries(trials_by_id: dict[str, Entry]) -> list[Entry]:
    entries = []
    for run_dir in sorted(path for path in RUNS.iterdir() if path.is_dir() and path.name.startswith("loop-")):
        for path in sorted(run_dir.rglob(coupon_loop.FILE_NAME)):
            arm_dir = path.parent
            if arm_dir.name not in LOOP_ARMS:
                continue
            record = coupon_loop.LoopRecord.load(arm_dir)
            first = trials_by_id.get(record.replayed)
            replayed = first.record if first else TrialRecord.load(RUNS / record.replayed)
            group, counted, reason = loop_group(run_dir.name, record, replayed)
            entry = Entry(id=arm_dir.relative_to(RUNS).as_posix(), kind="loop_arm", group=group, run=run_dir.name,
                          task=record.task, condition=replayed.condition, model=record.model, trial=replayed.trial,
                          verdict=arm_verdict(record), summary=arm_summary(record), counted=counted,
                          excluded_reason=reason, folder=arm_dir, record=record, replays=record.replayed, arm=record.arm)
            entry.cant_tell = coupon_loop.CANT_TELL in (record.reply or "")
            if group == "second" and first is not None:
                first.second_print = entry.id
            entries.append(entry)
    return entries


def loop_group(run: str, record, replayed: TrialRecord) -> tuple[str, bool, str | None]:
    if run in SECOND_PRINT_RUNS and record.arm == "feedback":
        if record.outcome == "error":
            return "second", False, f"infrastructure error, not a result: {short_error(record.error)}"
        if replayed.verdict == "pass":
            return "second", False, "replaced by its first print, which now passes after a regrade"
        return "second", True, None
    if run == "loop-estoa":
        return "loop-estoa-neutral", False, group_label("loop-estoa-neutral") + ": not in the headline counts"
    return run, False, group_label(run) + ": not in the headline counts"


def crash_entries() -> list[Entry]:
    entries = []
    for path in sorted((RUNS / "crash-replay").rglob(crash_replay.FILE_NAME)):
        record = crash_replay.ReplayRecord.load(path.parent)
        replayed = TrialRecord.load(RUNS / record.replayed)
        entries.append(Entry(id=path.parent.relative_to(RUNS).as_posix(), kind="crash_replay", group="crash-replay",
                             run="crash-replay", task=record.task, condition=record.condition, model=record.model,
                             trial=replayed.trial, verdict=arm_verdict(record), summary=arm_summary(record),
                             counted=False, excluded_reason=group_label("crash-replay") + ": not in the headline counts",
                             folder=path.parent, record=record, replays=record.replayed))
    return entries


def collect() -> list[Entry]:
    """Every trial, loop arm and crash replay saved under results/runs, with its group and whether it's counted."""
    listed = {row.model for row in scorecard.rows()}
    sliced = scorecard.slice_rows()
    trials = trial_entries(listed, sliced)
    by_id = {entry.id: entry for entry in trials}
    return trials + loop_entries(by_id) + crash_entries()


# ---- numbers per trial ----

def tokens_of(calls: list[ModelCall]) -> dict:
    """Token totals over the calls, as the providers counted them; reasoning and cached where they said."""
    def total(key):
        return sum((call.usage or {}).get(key) or 0 for call in calls)
    reasoning = sum(((call.usage or {}).get("completion_tokens_details") or {}).get("reasoning_tokens") or 0 for call in calls)
    return {"prompt": total("prompt_tokens"), "completion": total("completion_tokens"), "reasoning": reasoning,
            "cached": sum(call.cached_tokens for call in calls), "total": total("total_tokens"), "calls": len(calls)}


def slice_key(entry: Entry) -> tuple:
    if entry.kind == "loop_arm":
        return (entry.run, entry.task, f"{entry.condition}/{entry.arm}", entry.model, entry.trial)
    return (entry.run, entry.task, entry.condition, entry.model, entry.trial)


@cache
def slice_parts() -> dict[tuple, list[dict]]:
    found = defaultdict(list)
    for path in sorted(RUNS.glob("*/slice_estimates_parts.csv")):
        with path.open() as handle:
            for row in csv.DictReader(handle):
                found[(row["run"], row["task"], row["condition"], row["model"], int(row["trial"]))].append(row)
    return found


def number(text) -> float | None:
    return scorecard.number(text) if text is not None else None


def slicing(entry: Entry, sliced: dict) -> dict | None:
    """The slicer's estimate for everything the design handed in (scripts/slice_estimates.py), or None if not sliced."""
    row = sliced.get(slice_key(entry))
    if not row:
        return None
    parts = [{"part": p["part"], "role": p["role"], "status": p["status"], "est_print_s": number(p["print_s"]),
              "est_filament_g": number(p["filament_g"]), "error": p["error"] or None, "warning": p["warning"] or None}
             for p in slice_parts().get(slice_key(entry), [])]
    return {"est_final_print_s": number(row["final_print_s"]), "est_final_filament_g": number(row["final_filament_g"]),
            "est_test_print_s": number(row["test_print_s"]), "est_test_print_filament_g": number(row["test_print_filament_g"]),
            "est_print_s": number(row["all_print_s"]), "est_filament_g": number(row["all_filament_g"]),
            "parts_not_sliced": int(row["parts_not_sliced"] or 0), "plate_error": row["plate_error"] or None, "parts": parts}


# ---- diagnoses and check meanings ----

@cache
def audit_notes() -> dict:
    return json.loads(results_page.AUDIT.read_text())


@cache
def holed_roofs() -> dict:
    return json.loads(HOLED.read_text()) if HOLED.exists() else {}


def reader_words(text: str) -> str:
    """Prose a reader sees says test print, not coupon (Dan's term); saved records keep the old word."""
    for old, new in (("test coupon", "test print"), ("coupon loop", "test-print loop"), ("coupon's", "test print's"),
                     ("coupons", "test prints"), ("coupon", "test print")):
        text = text.replace(old, new).replace(old.capitalize(), new.capitalize())
    return text


UNKNOWN_ROOF_KEY = UNKNOWN_ROOF = "A roof or ledge too wide to bridge (whether the bolt's hole runs through it isn't recorded for this design)"


def raw_issues(entry: Entry) -> list[dict]:
    """results_page.issues_of for any entry: each counted check that didn't pass, with its diagnosis family. Whether a
    failed bridge check is a holed roof comes from results/holed_roofs.json, as failure_tables.py --check reads it."""
    record = entry.record
    if entry.kind != "trial":
        record = Graded(entry.task, entry.model, entry.trial, record.findings)
    key = trial_key(entry.run, entry.task, entry.condition, entry.model, entry.trial)
    issues = results_page.issues_of(entry.run, record, audit_notes().get(key) if entry.kind == "trial" else None,
                                    set(holed_roofs().get(key, [])))
    if key not in holed_roofs():
        for issue in issues:
            if issue["family"] == "A roof or ledge too wide to bridge, with no hole through it":
                issue["family"] = UNKNOWN_ROOF
    return issues


REASON_GROUPS = {  # near-duplicate reasons shown as one bucket; any other reason is a group of its own
    "A roof with the bolt's hole cut through it": ("holed-roof", "A roof with the bolt's hole cut through it"),
    "A roof or ledge too wide to bridge, with no hole through it": ("wide-roof", "A roof or ledge too wide to bridge"),
    UNKNOWN_ROOF_KEY: ("wide-roof", "A roof or ledge too wide to bridge"),
    "Not graded: a nut pocket tighter than any printed": ("nut-pocket-size", "A nut pocket size no recorded print settles"),
    "Not graded: a nut pocket looser than any printed": ("nut-pocket-size", "A nut pocket size no recorded print settles"),
    "Not graded: a nut pocket between printed sizes": ("nut-pocket-size", "A nut pocket size no recorded print settles"),
    "Not graded: no recorded print settles this nut pocket": ("nut-pocket-size", "A nut pocket size no recorded print settles"),
    "Not graded: a nut pocket with ribs or clips, never printed": ("nut-pocket-shape", "A nut pocket shape no recorded print settles"),
    "Not graded: its test coupon's pockets are ribbed or sizes no print settled": ("nut-pocket-shape", "A nut pocket shape no recorded print settles"),
}


def reason_group(reason_key: str, reason: str) -> str:
    """The key of the bucket a reason is shown in; its label is in index.json's reason_groups."""
    return reason_bucket(reason_key, reason)["key"]


REASON_GROUP_LABELS: dict[str, str] = {}


def reason_bucket(reason_key: str, reason: str) -> dict:
    if reason_key in REASON_GROUPS:
        key, label = REASON_GROUPS[reason_key]
        REASON_GROUP_LABELS.setdefault(key, label)
    elif reason_key.startswith("Declined"):
        key, label = "declined", "Declined: handed in no final part"
        REASON_GROUP_LABELS.setdefault(key, label)
    else:
        key, label = re.sub(r"[^a-z0-9]+", "-", reason.lower()).strip("-"), reason
    REASON_GROUP_LABELS.setdefault(key, label)
    return {"key": key, "label": label}


def table_reason(family: str, task: str) -> str:
    """The reason in a reader's words: table_wording without markdown, and test print for coupon."""
    return reader_words(table_wording(family, task).replace("`", ""))


def table_wording(family: str, task: str) -> str:
    """The short reason as docs/reference.md's and README.md's tables word it (scripts/failure_tables.py), or the
    results page's own words where those tables have no entry (the Estoa light, loop arms)."""
    if family in failure_tables.NOT_GRADED:
        return failure_tables.NOT_GRADED[family][0]
    if family == "A roof with the bolt's hole cut through it":
        return failure_tables.HOLED_ROOF.get(task.split("/")[0], family)
    if family.startswith("Declined"):
        return failure_tables.DECLINED.get(task.split("/")[0], "Declined: handed in only a test print")
    if family.startswith("Not graded: "):  # an Estoa or loop-arm reason the tables don't word: drop the prefix
        family = family.removeprefix("Not graded: ")
        family = family[0].upper() + family[1:]
    return failure_tables.WRONG.get(family, family)


def not_graded_reasons() -> dict:
    """failure_tables.py's not-graded reasons, keyed by reason_key: the table's words and the print that would settle it."""
    return {key: {"reason": reader_words(reason), "settle": reader_words(settle),
                  "reason_group": reason_group(key, reader_words(reason))}
            for key, (reason, settle) in failure_tables.NOT_GRADED.items()}


def issue_rows(entry: Entry) -> list[dict]:
    """index.json's per-trial issues: every counted check that didn't pass, failed or not graded, with its short
    reason, plus one row for a trial with no design. `reason_key` is the results page's family, the key failure_tables
    counts by."""
    rows = []
    for issue in raw_issues(entry):
        kind = {"gap": "not graded", "format": "not graded", "declined": "declined"}.get(issue["kind"], "failed")
        reason = table_reason(issue["family"], entry.task)
        rows.append({"check": None if issue["check"] == "-" else issue["check"],
                     "part": None if issue["part"] == "-" else issue["part"], "kind": kind, "reason_kind": kind,
                     "reason": reason, "reason_key": issue["family"], "reason_group": reason_group(issue["family"], reason),
                     "diagnosis_kind": issue["kind"]})
    if entry.verdict in ("no design", "error"):
        reason = failure_tables.NO_DESIGN if entry.verdict == "no design" else "Didn't run: an infrastructure error"
        rows.append({"check": None, "part": None, "kind": entry.verdict, "reason_kind": entry.verdict, "reason": reason,
                     "reason_key": reason, "reason_group": reason_group(reason, reason), "diagnosis_kind": None})
    return rows


def diagnoses(entry: Entry) -> dict[tuple[str, str], dict]:
    """results_page's diagnosis of each counted check that didn't pass, keyed by (check, part)."""
    found = {}
    for issue in raw_issues(entry):
        found.setdefault((issue["check"], issue["part"]), {
            "text": reader_words(issue["family"]), "reason": table_reason(issue["family"], entry.task),
            "kind": issue["kind"], "kind_label": reader_words(results_page.KIND[issue["kind"]]),
            "would_help": reader_words(results_page.HELP[issue["help"]])})
    return found


@cache
def check_meanings(task: str) -> dict[str, dict]:
    titles = CHECK_TITLES["*"] | CHECK_TITLES.get(task.split("/")[0], {})
    meanings = {check: {"title": titles[check], "text": text, "class": "C6-printability", "generic": True}
                for check, text in GENERIC_CHECKS.items()}
    try:
        requirements = task_files.load(task).requirements
    except (FileNotFoundError, ValueError):
        return meanings
    for requirement in requirements:
        meanings[requirement.id] = {"title": titles.get(requirement.id, requirement.id), "text": reader_words(requirement.text), "class": requirement.failure_class or None,
                                    "generic": False}
    return meanings


@cache
def views() -> dict:
    """{design path: [view entry]} from scripts/results_site_views.json, or {} without it."""
    if not VIEWS.exists():
        return {}
    try:
        return json.loads(VIEWS.read_text()).get("designs") or {}
    except (json.JSONDecodeError, AttributeError):
        print(f"{VIEWS.name} isn't readable JSON: no drawn views on the site", file=sys.stderr)
        return {}


@cache
def view_audit() -> dict:
    """{view url: {shows_failure, p, model}} from scripts/results_site_view_audit.json (a decisions model's answer to
    whether the drawing shows its failure legibly; scripts/results_site_view_audit.py), or {} without it."""
    if not VIEW_AUDIT.exists():
        return {}
    try:
        return json.loads(VIEW_AUDIT.read_text()).get("views") or {}
    except (json.JSONDecodeError, AttributeError):
        print(f"{VIEW_AUDIT.name} isn't readable JSON: no view audit on the site", file=sys.stderr)
        return {}


NO_VIEW_SAVED = "no drawn view is saved for this check"
NO_VIEW_DECLINED = "the trial declined, so its checks aren't counted and no view was drawn"
NO_VIEW_TEST_PRINT = "an ungraded check on a test print isn't drawn"


def view_of(entry: Entry, finding: CheckResult, declined: str | None = None) -> dict:
    """{"view": {url, kind, caption, state, test_print, width, height} | None, "no_view_reason": str | None} for a check that failed or
    couldn't be graded, matched in the views manifest on (check, part, test print) within the design's own folder. A
    passing or not-reached check gets neither key."""
    state = check_state(finding)
    if state not in ("fail", "not graded"):
        return {}
    for found in views().get(entry.id, []):
        if (found["check"] == finding.check and bool(found["test_print"]) == bool(finding.test_print)
                and (found["part"] == finding.part or same_part(str(found["part"]), str(finding.part)))):
            if found["view"]:
                view = {"url": found["view"], "kind": found["kind"], "caption": found["caption"],
                        "state": found["state"], "test_print": bool(found["test_print"]),
                        "width": found.get("width"), "height": found.get("height")}  # pixels, so a page can reserve the shape
                if found["view"] in view_audit():
                    view["audit"] = view_audit()[found["view"]]
                return {"view": view, "no_view_reason": None}
            return {"view": None, "no_view_reason": found["no_view_reason"]}
    if declined:
        return {"view": None, "no_view_reason": NO_VIEW_DECLINED}
    if finding.test_print and state == "not graded":
        return {"view": None, "no_view_reason": NO_VIEW_TEST_PRINT}
    return {"view": None, "no_view_reason": NO_VIEW_SAVED}


def view_counts(entry: Entry) -> dict:
    """How many counted failed checks have a drawn view, and how many don't."""
    failed = [finding for finding in counted_of(entry) if finding.ok is False]
    drawn = sum(bool(view_of(entry, finding).get("view")) for finding in failed)
    return {"views": drawn, "views_missing": len(failed) - drawn}


def finding_rows(entry: Entry, findings: list[CheckResult], declined: str | None = None) -> list[dict]:
    diagnosed = diagnoses(entry)
    meanings = check_meanings(entry.task)
    rows = []
    for finding in findings:
        counted = not finding.test_print and not declined
        rows.append(view_of(entry, finding, declined) | {"check": finding.check, "part": finding.part, "ok": finding.ok, "detail": clip(finding.detail, CAP["detail"]),
                     "test_print": finding.test_print, "counted": counted, "state": check_state(finding),
                     "title": meanings.get(finding.check, {}).get("title", finding.check),
                     "meaning": meanings.get(finding.check, {}).get("text"),
                     "diagnosis": diagnosed.get((finding.check, finding.part)) if counted and finding.ok is not True else None})
    return rows


# ---- the design, test prints and transcript ----

def clip(text, limit: int) -> str:
    text = "" if text is None else str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f" … [{len(text) - limit} more characters in the full file]"


def submission_of(folder: Path) -> dict | None:
    path = folder / "submission.yaml"
    if not path.exists():
        return None
    saved = yaml.safe_load(path.read_text()) or {}
    parts = [{"id": part.get("id"), "role": part.get("role"),
              "role_label": "test print" if part.get("role") == "coupon" else "final part",
              "material": part.get("material"), "print_orientation": part.get("print_orientation"),
              "use_orientation": part.get("use_orientation"), "code": clip(part.get("code"), CAP["code"])}
             for part in saved.get("parts") or []]
    return {"note": clip(saved.get("note"), CAP["note"]), "questions": saved.get("questions") or [],
            "params": saved.get("params") or {}, "hardware": saved.get("hardware") or [],
            "criteria": saved.get("criteria") or [], "manual": clip(saved.get("manual") if isinstance(saved.get("manual"), str)
                                                                    else json.dumps(saved.get("manual")), CAP["manual"]),
            "has_assembly": "assembly" in saved, "parts": parts}


def tool_arguments(call: dict) -> tuple[str, dict | str]:
    function = call.get("function") or {}
    raw = function.get("arguments") or ""
    try:
        return function.get("name") or "?", json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return function.get("name") or "?", raw


def compact_args(name: str, args) -> dict | str:
    """A tool call's arguments, with code cut down: a final design's code is in the submission section."""
    if not isinstance(args, dict):
        return clip(args, CAP["args"])
    if name in ("submit_design", "print_test"):
        limit = CAP["submit_code"] if name == "submit_design" else CAP["transcript_code"]
        shown = {key: value for key, value in args.items() if key != "parts"}
        text = json.dumps(shown, ensure_ascii=False)
        shown = shown if len(text) <= CAP["args"] else clip(text, CAP["args"])
        parts = [{key: (clip(value, limit) if key == "code" else value) for key, value in part.items()}
                 for part in args.get("parts") or [] if isinstance(part, dict)]
        return {"parts": parts, "other": shown}
    if name == "run_python":
        return {key: clip(value, CAP["transcript_code"]) if isinstance(value, str) else value for key, value in args.items()}
    text = json.dumps(args, ensure_ascii=False)
    return args if len(text) <= CAP["args"] else clip(text, CAP["args"])


def message_text(content) -> str:
    if isinstance(content, list):  # a message with images (a datasheet page): its text, with a marker per image
        return "\n".join(item.get("text", "") if item.get("type") == "text" else f"[{item.get('type', 'item')}]"
                         for item in content if isinstance(item, dict))
    return content or ""


HARNESS_REPLIES = ("Received.", "Noted.", "Please use", "That isn't a valid submission", "I can't print that yet")
VALIDATION = ("That isn't a valid submission", "I can't print that yet")


def tool_summary(name: str, args) -> str:
    """One line a reader can take in: what the model asked for with this call."""
    if not isinstance(args, dict):
        return f"calls {name}"
    parts = [part.get("id", "?") for part in args.get("parts") or [] if isinstance(part, dict)]
    if name == "measure":
        return clip(f"asks to measure: {args.get('item', '')} {('(' + args['what'] + ')') if args.get('what') else ''}".strip(), 200)
    if name == "submit_design":
        return f"hands in a design: {len(parts)} part{'s' if len(parts) != 1 else ''} ({', '.join(parts)})"
    if name == "print_test":
        return reader_words(f"asks for test prints: {', '.join(parts)}")
    if name == "report_limitation":
        return clip("reports a limitation: " + " ".join(str(v) for v in args.values()), 200)
    if name == "run_python":
        code = args.get("code") or ""
        return f"runs Python ({code.count(chr(10)) + 1} lines)"
    return f"calls {name}"


def validation_summary(text: str) -> str:
    """One line for a format error the harness sent back, e.g. "Design sent back: 1 format error (parts.0.role: Field
    required)". Pydantic's message is a field line followed by an indented reason line."""
    what = "Design" if text.startswith("That isn't") else "Test print request"
    lines = text.splitlines()
    count = next((re.match(r"(\d+) validation error", line).group(1) for line in lines if re.match(r"\d+ validation error", line)), None)
    first = next(((lines[i], lines[i + 1].strip()) for i in range(1, len(lines) - 1)
                  if lines[i] and not lines[i].startswith((" ", "-")) and not re.match(r"\d+ validation error", lines[i])
                  and lines[i + 1].startswith("  ")), None)
    if count and first:
        reason = first[1].split(" [type=")[0]
        return clip(f"{what} sent back: {count} format error{'s' if count != '1' else ''} ({first[0]}: {reason})", 200)
    if count:  # a whole-design error: the indented line after the count says what's wrong
        reason = next((line.strip().split(" [type=")[0] for line in lines if line.startswith("  ")), "")
        return clip(f"{what} sent back: {reason.removeprefix('Value error, ')}", 200)
    detail = next((line.strip("- ").strip() for line in lines[1:] if line.strip()), "")
    return clip(f"{what} sent back: {detail}" if detail else lines[0], 200)


def harness_entry(role: str, text: str) -> dict:
    """A message from the eval itself, not the person: an acknowledgement, a nudge or a validation error. A validation
    error is shown as a one-line summary, with the full text kept."""
    entry = {"role": role, "speaker": "harness", "text": clip(text, 4000)}
    if text.startswith(VALIDATION):
        entry["summary"] = validation_summary(text)
    return entry


def excerpt(messages: list[dict], prompts: dict[str, str]) -> list[dict]:
    """The conversation in order, each message tagged with who speaks: the model, the simulated person, or the
    harness (the eval's own acknowledgements, nudges and validation errors). Tool calls get a one-line summary."""
    out, first_user, calls_by_id = [], True, {}
    for message in messages:
        role = message.get("role")
        text = message_text(message.get("content"))
        if role == "system":
            ref = hashlib.sha1(text.encode()).hexdigest()[:12]
            prompts[ref] = text
            out.append({"role": "system", "speaker": "harness", "ref": ref})
        elif role == "user":
            if not first_user and text.startswith(HARNESS_REPLIES):
                out.append(harness_entry("user", text))
            else:
                out.append({"role": "user", "speaker": "person (simulated)",
                            "text": clip(text, CAP["first_user" if first_user else "user"])})
            first_user = False
        elif role == "assistant":
            shown = {"role": "assistant", "speaker": "model"}
            if message.get("content"):
                shown["text"] = clip(text, CAP["content"])
            if message.get("reasoning"):
                shown["reasoning"] = clip(message["reasoning"], CAP["reasoning"])
            calls = []
            for call in message.get("tool_calls") or []:
                name, args = tool_arguments(call)
                calls_by_id[call.get("id")] = name
                calls.append({"tool": name, "summary": tool_summary(name, args), "args": compact_args(name, args)})
            if calls:
                shown["tool_calls"] = calls
            out.append(shown)
        elif role == "tool":
            tool = calls_by_id.get(message.get("tool_call_id"))
            if tool in ("measure", "print_test") and not text.startswith(HARNESS_REPLIES):
                out.append({"role": "tool", "speaker": "person (simulated)", "tool": tool, "text": clip(text, CAP["tool"])})
            else:
                out.append(harness_entry("tool", text) | {"tool": tool})
    if len(out) > MAX_EXCERPT_MESSAGES:
        dropped = len(out) - 90  # 60 kept from the start and 30 from the end
        out = out[:60] + [{"role": "omitted", "speaker": "harness",
                           "text": f"{dropped} messages left out here; see the full transcript"}] + out[-30:]
    return out


def transcript_of(folder: Path, prompts: dict[str, str]) -> dict | None:
    path = folder / "transcript.json"
    if not path.exists():
        return None
    messages = json.loads(path.read_text())
    return {"url": transcript_base() + path.relative_to(RUNS).as_posix(), "messages": len(messages),
            "excerpt": excerpt(messages, prompts)}


def print_test_code(folder: Path) -> list[dict]:
    """The parts of each print_test call the person printed, with their code, in order (from the transcript)."""
    path = folder / "transcript.json"
    if not path.exists():
        return []
    messages = json.loads(path.read_text())
    results = {m.get("tool_call_id"): message_text(m.get("content")) for m in messages if m.get("role") == "tool"}
    printed = []
    for message in messages:
        for call in message.get("tool_calls") or []:
            name, args = tool_arguments(call)
            if name == "print_test" and results.get(call.get("id"), "").startswith("I printed") and isinstance(args, dict):
                printed.append({part.get("id"): clip(part.get("code"), CAP["transcript_code"])
                                for part in args.get("parts") or [] if isinstance(part, dict)})
    return printed


def answer_line(line: dict) -> dict:
    return {"text": line["text"], "basis": line["basis"], "basis_label": BASIS_LABELS.get(line["basis"], line["basis"]),
            "cant_tell": CANT_TELL in line["text"], "prediction": line["basis"] == "bridge check prediction"}


def test_prints_of(entry: Entry) -> list[dict]:
    record = entry.record
    if not getattr(record, "test_prints", None):
        return []
    code = print_test_code(entry.folder)
    code = code if len(code) == len(record.test_prints) else [{} for _ in record.test_prints]  # unmatched: leave code out
    rounds = []
    for number_, (test, parts_code) in enumerate(zip(record.test_prints, code), 1):
        rounds.append({"round": number_, "parts": [{"id": part, "code": parts_code.get(part)} for part in test["parts"]],
                       "params": test.get("params") or {},
                       "answers": {part: [answer_line(line) for line in lines] for part, lines in test["reply"].items()}})
    return rounds


@cache
def person_facts(task: str) -> dict:
    try:
        return task_files.load(task).hidden_facts
    except (FileNotFoundError, ValueError):
        return {}


def measure_match(task: str, asked) -> dict:
    """Whether the reply answers what was asked, read by running the person's lookup (pbe/runner/measure.py) again on
    the question. "whole item": the question named none of the item's recorded measurements, so the person read out
    everything recorded about the item. "unknown": today's lookup doesn't give the ids the record saved (the task's
    facts changed since, or a replay gave the person fewer facts), so it can't be told honestly."""
    if asked.reply == measure.NO_ANSWER:
        return {"match": "nothing recorded", "match_note": "The person has no record of this, and said so."}
    person = measure.Person(person_facts(task))
    request = f"{asked.item} {asked.what}"
    things = person._things_named(asked.item, request)
    found = [f"{thing}.{name}" for thing in things for name in person._measurements_asked_for(thing, request)]
    if sorted(found) != sorted(asked.revealed):
        return {"match": "unknown", "match_note": "Can't be told from the record: the lookup's facts differ from the run's."}
    whole = [thing for thing in things if not any(measure._mentions(request, measure._names(name, recorded))
                                                  for name, recorded in person.things[thing].measurements.items())]
    if whole:
        names = ", ".join(t.replace("_", " ") for t in whole)
        return {"match": "whole item", "match_note": f"The question named none of what's recorded about the {names}, so "
                f"the person read out everything recorded about it: the nearest recorded answer, not an answer to what "
                f"was asked."}
    return {"match": "answered", "match_note": None}


def measures_of(entry: Entry) -> list[dict]:
    return [{"item": m.item, "what": m.what, "revealed": m.revealed, "reply": m.reply} | measure_match(entry.task, m)
            for m in getattr(entry.record, "measures", [])]


@cache
def media() -> dict:
    if not MEDIA.exists():
        return {}
    try:
        return json.loads(MEDIA.read_text()).get("designs") or {}
    except (json.JSONDecodeError, AttributeError):
        print(f"{MEDIA.name} isn't readable JSON: no renders on the site", file=sys.stderr)
        return {}


def same_part(a: str, b: str) -> bool:
    """A part id as the record spells it and as the media manifest does (it may change _ to -)."""
    return re.sub(r"[^a-z0-9]", "", a.lower()) == re.sub(r"[^a-z0-9]", "", b.lower())


def volume(part: dict) -> float:
    size = part.get("size_mm") or [0, 0, 0]
    return size[0] * size[1] * size[2] if len(size) == 3 else 0.0


def ordered_parts(entry: Entry, design: dict | None) -> list[dict]:
    """The design's rendered parts, picture first: the part carrying the first failed counted check (if it has a
    render), then final parts by bounding volume, largest first, then test prints the same way."""
    parts = [part for part in (design or {}).get("parts") or [] if part.get("thumb")]
    by_size = sorted(parts, key=lambda part: (part.get("role") == "coupon", -volume(part)))
    failed = next((f.part for f in counted_of(entry) if f.ok is False and f.part != "-"
                   and any(same_part(f.part, part["id"]) for part in parts)), None)
    if failed is None:
        return by_size
    first = next(part for part in by_size if same_part(failed, part["id"]))
    return [first] + [part for part in by_size if part is not first]


def thumb_fields(entry: Entry) -> dict:
    """The default picture of a trial and why it was chosen, or why there's none."""
    design = media().get(entry.id)
    parts = ordered_parts(entry, design)
    if parts:
        part = parts[0]
        return {"thumb": part["thumb"], "thumb_part": part["id"],
                "thumb_role": "test print" if part.get("role") == "coupon" else "final"}
    if entry.verdict == "error":
        reason = "The trial stopped before a design (an infrastructure error)"
    elif entry.verdict == "no design":
        reason = "No design was handed in"
    elif not part_count(entry.folder):
        reason = "The design handed in had no parts"
    elif design and (not design.get("built") or design.get("error")):
        reason = "The design's code didn't run, so nothing was built"
    else:
        reason = "No render of this design is saved"
    return {"thumb": None, "thumb_part": None, "thumb_role": None, "thumb_none_reason": reason}


def part_count(folder: Path) -> int:
    path = folder / "submission.yaml"
    return len((yaml.safe_load(path.read_text()) or {}).get("parts") or []) if path.exists() else 0


def media_detail(entry: Entry) -> dict | None:
    """The media manifest's entry, parts in picture order, each with a reader's role label."""
    design = media().get(entry.id)
    if not design:
        return None
    order = ordered_parts(entry, design)
    rest = [part for part in design.get("parts") or [] if part not in order]
    parts = [part | {"role_label": "test print" if part.get("role") == "coupon" else "final part"} for part in order + rest]
    return design | {"parts": parts}


def earlier_verdicts(record: TrialRecord) -> list[dict]:
    """Each verdict a regrade replaced, so a changed result stays visible."""
    shown = []
    for earlier in record.regrades:
        counted = [] if earlier.declined else [f for f in earlier.findings if not f.test_print]
        if earlier.declined:
            verdict = "declined"
        elif earlier.all_pass:
            verdict = "pass"
        else:
            verdict = "fail" if any(f.ok is False for f in counted) else "not graded"
        shown.append({"date": earlier.date, "commit": earlier.commit, "verdict": verdict,
                      "failed": checks_text([f.check for f in counted if f.ok is False]),
                      "not_graded": checks_text([f.check for f in counted if f.ok is None])})
    return shown


# ---- the two files per trial ----

def index_row(entry: Entry, sliced: dict, by_id: dict[str, Entry]) -> dict:
    record = entry.record
    estimate = slicing(entry, sliced) or {}
    row = {"id": entry.id, "slug": entry.slug, "kind": entry.kind, "group": entry.group, "run": entry.run,
           "task": entry.task, "condition_key": entry.condition, "title": title_of(entry),
           "model": entry.model, "model_short": short_name(entry.model),
           "trial": entry.trial, "verdict": entry.verdict, "summary": clip(entry.summary, INDEX_CAP_SUMMARY),
           "counted": entry.counted, "excluded_reason": entry.excluded_reason,
           "cost_usd": round(record.cost_usd or 0.0, 6), "turns": record.turns, "elapsed_s": record.elapsed_s,
           "tokens_total": tokens_of(record.calls)["total"],
           "est_print_s": estimate.get("est_print_s"), "est_filament_g": estimate.get("est_filament_g"),
           "test_print_rounds_asked": len(getattr(record, "test_prints", []) or []), "measures_asked": len(getattr(record, "measures", [])),
           "cant_tell": entry.cant_tell, **thumb_fields(entry),
           "failed_checks": sorted({f.check for f in counted_of(entry) if f.ok is False}),
           "not_graded_checks": sorted({f.check for f in counted_of(entry) if check_state(f) == "not graded"}),
           "not_reached_checks": sorted({f.check for f in counted_of(entry) if check_state(f) == "not reached"}),
           "check_counts": dict(Counter(check_state(f) for f in counted_of(entry))), **view_counts(entry),
           "issues": issue_rows(entry)}
    if entry.after_feedback is not None:
        row["after_feedback"] = after_feedback_row(entry)
    if entry.replays:
        first = by_id.get(entry.replays)
        row["replays"] = entry.replays
        row["replays_slug"] = slug_of(entry.replays)
        row["first_verdict"] = first.verdict if first else None
    if entry.group == "second":
        row["counts_in_scorecard"] = entry.counted
        first = by_id.get(entry.replays)
        if first is not None and first.verdict == "pass":
            row["note"] = SUPERSEDED
    if entry.arm:
        row["arm"] = entry.arm
        row["arm_label"] = ("told how the first print came out" if entry.arm == "feedback"
                            else "only asked to take another look")
    return row


SUPERSEDED = ("This replay ran when the first print didn't pass. The first print was regraded afterwards on newer "
              "recorded test prints and now passes, so the scorecard counts the first print and not this one.")


def title_of(entry: Entry) -> str:
    if entry.kind == "crash_replay":
        return f"Retry of trial {entry.trial} after its build error"
    if entry.arm == "feedback":
        return f"Second print of trial {entry.trial}"
    if entry.arm == "neutral":
        return f"Second look at trial {entry.trial}, without a report"
    return f"Trial {entry.trial}"


def after_feedback_row(entry: Entry) -> dict:
    """What the scorecard's "after feedback" cell needs: whether this first print is in it, the verdict it counts, and
    whether that verdict is the first print's own (it passed, or wasn't replayed) or its second print's."""
    found = entry.after_feedback
    return {"counted": entry.counted, "verdict": found["verdict"], "passed": found["passed"], "via": found["from"],
            "replayed": found["replayed"], "second_print": entry.second_print,
            "second_slug": slug_of(entry.second_print) if entry.second_print else None,
            **({"note": SUPERSEDED} if entry.second_print and entry.verdict == "pass" else {})}


def counted_of(entry: Entry) -> list[CheckResult]:
    if entry.kind == "trial":
        return entry.record.counted_findings
    return [finding for finding in entry.record.findings if not finding.test_print]


def detail(entry: Entry, sliced: dict, by_id: dict[str, Entry], prompts: dict[str, str]) -> dict:
    record = entry.record
    out = index_row(entry, sliced, by_id)
    out |= {"task_name": TASK_NAMES.get(entry.task, entry.task), "request": gallery.brief_of(entry.task)["request"], "date": record.date, "commit": record.commit,
            "platform": record.platform, "error": clip(record.error, 600) if record.error else None,
            "tokens": tokens_of(record.calls), "slicer_estimate": slicing(entry, sliced),
            "findings": finding_rows(entry, record.findings, getattr(record, "declined", None)),
            "measures": measures_of(entry), "submission": submission_of(entry.folder),
            "transcript": transcript_of(entry.folder, prompts), "media": media_detail(entry)}
    out |= dates_of(entry) | parts_built(entry, record) | handed_in(out["submission"])
    if entry.kind == "trial":
        out |= trial_detail(entry, record)
    elif entry.kind == "loop_arm":
        out |= loop_detail(entry, record, by_id)
    else:
        out |= {"message": record.message, "saved_verdict": record.saved_verdict}
    return out


def dates_of(entry: Entry) -> dict:
    """run_date: the first time the trial was graded, which the runner does right after the model's turn (no separate
    run timestamp is kept). graded_date: the grading behind today's verdict. regrades: the gradings in between, oldest
    first. code_version: the commit the trial's code ran at, as recorded."""
    record = entry.record
    earlier = sorted(getattr(record, "regrades", []), key=lambda earlier: earlier.date)
    gradings = [earlier_one.date for earlier_one in earlier] + [record.date]
    commits = [earlier_one.commit for earlier_one in earlier] + [record.commit]
    ran_at, graded_at = commits[0] or None, record.commit or None
    return {"run_date": gradings[0] or None, "graded_date": record.date or None, "regrade_dates": gradings[1:],
            "code_version": ran_at, "graded_code_version": graded_at,
            "code_version_note": dirty_note(ran_at, graded_at)}


def dirty_note(ran_at: str | None, graded_at: str | None) -> str | None:
    """A reader's gloss on a recorded "-dirty" commit: the runner records it when the checkout had uncommitted changes."""
    dirty = [label for label, commit_ in (("ran", ran_at), ("was last graded", graded_at)) if commit_ and commit_.endswith("-dirty")]
    if not dirty:
        return None
    return (f"The commit is recorded with -dirty when the code that decides results had changes not yet committed; this trial {' and '.join(dirty)} "
            "on such code.")


def handed_in(sub: dict | None) -> dict:
    """What the design contained, in one line: "Handed in: 1 test print, no final part"."""
    if not sub:
        return {"handed_in": None}
    finals = sum(part["role"] != "coupon" for part in sub["parts"])
    tests = len(sub["parts"]) - finals
    def count(n, word):
        return f"{n} {word}{'s' if n != 1 else ''}" if n else f"no {word}"
    return {"handed_in": {"final_parts": finals, "test_prints": tests,
                          "text": f"Handed in: {count(finals, 'final part')}, {count(tests, 'test print')}"}}


def parts_built(entry: Entry, record) -> dict:
    """Which parts' code ran and which didn't (the builds check), when any didn't."""
    builds = [f for f in record.findings if f.check == "builds"]
    failed = [f for f in builds if f.ok is False]
    if not failed:
        return {"parts_not_built": []}
    return {"parts_built": [f.part for f in builds if f.ok], "parts_not_built": [
        {"part": f.part, "test_print": f.test_print, "error": clip(f.detail, 300)} for f in failed]}


UNPROMPTED = ("The model added test prints to this design without being offered them. Nobody prints them before the "
              "final part here: their own printability checks are reported but don't count, though the knob's and "
              "wheel's fit checks give credit for a test print that would have found a size that works.")


def trial_detail(entry: Entry, record: TrialRecord) -> dict:
    key = trial_key(entry.run, entry.task, entry.condition, entry.model, entry.trial)
    assumed = Assumed.load_if_saved(entry.folder)
    found = {"declined": record.declined, "repairs": record.repairs, "limitations": record.limitations,
             "test_prints": test_prints_of(entry), "regrades": earlier_verdicts(record),
             "audit": audit_of(key),
             "assumed": assumed.model_dump() if assumed else None,
             "settings": record.settings.model_dump(exclude_none=True)}
    sub = submission_of(entry.folder)
    if record.condition != "can_test" and sub and any(part["role"] == "coupon" for part in sub["parts"]):
        found["unprompted_test_prints"] = UNPROMPTED
    if record.declined:
        found["declined_diagnosis"] = diagnoses(entry).get(("-", "-"))
    if entry.second_print:
        found["second_print"] = entry.second_print
        found["second_print_slug"] = slug_of(entry.second_print)
    return found


def audit_of(key: str) -> dict | None:
    """Dan's or Claude's audit note on the trial (scripts/results_page_audit.json), in a reader's words."""
    note = audit_notes().get(key)
    return note | {"note": reader_words(note["note"])} if note else None


def loop_detail(entry: Entry, record, by_id: dict[str, Entry]) -> dict:
    baseline_dir = entry.folder.parent / "baseline"
    baseline = coupon_loop.LoopRecord.load(baseline_dir) if (baseline_dir / coupon_loop.FILE_NAME).exists() else None
    first = by_id.get(entry.replays)
    return {"reply": record.reply, "report": {part: [answer_line(line.model_dump()) for line in lines]
                                              for part, lines in record.report.items()},
            "first_print": {"id": entry.replays, "slug": slug_of(entry.replays), "verdict": first.verdict if first else None,
                            "summary": first.summary if first else None},
            "baseline": {"verdict": arm_verdict(baseline), "summary": arm_summary(baseline),
                         "note": "the replayed design, regraded with its test prints left out, as the second print is"}
            if baseline else None}


# ---- index.json's shared parts ----

def groups(entries: list[Entry]) -> list[dict]:
    seen = Counter(entry.group for entry in entries)
    found = [{"key": key, "label": group.label, "description": group.description, "category": group.category,
              "kind": "headline" if group.category == HEADLINE else "other", "runs": list(group.runs),
              "condition_key": group.condition_key, "trials": seen.get(key, 0)}
             for key, group in (*HEADLINE_GROUPS.items(), *OTHER_GROUPS.items()) if key in HEADLINE_GROUPS or seen.get(key)]
    unknown = sorted(set(seen) - set(HEADLINE_GROUPS) - set(OTHER_GROUPS))
    found += [{"key": key, "label": key, "description": "A saved run with no label yet.", "category": PILOT,
               "kind": "other", "runs": [key], "condition_key": None, "trials": seen[key]} for key in unknown]
    return found


def task_info(entries: list[Entry]) -> dict:
    info = {}
    for task in sorted({entry.task for entry in entries}):
        brief = gallery.brief_of(task)
        info[task] = {"label": TASK_NAMES.get(task, task), "name": TASK_NAMES.get(task, task),
                      "short": TASK_SHORT.get(task, task), "scored": task in scorecard.TASKS, "harder": task == scorecard.HARDER[0],
                      "request": brief["request"], "why": brief["why"], "checks": check_meanings(task)}
    return info


def models(entries: list[Entry], listed: list) -> dict:
    order = [row.model for row in listed]
    return {model: {"short": short_name(model), "listed": model in order,
                    "scorecard_rank": order.index(model) + 1 if model in order else None,
                    "frontier": model in gallery.FRONTIER}
            for model in sorted({entry.model for entry in entries})}


def counts(entries: list[Entry]) -> dict:
    """{group: {task: {verdict: trials}}} over every entry, and over counted entries only."""
    every, counted = defaultdict(lambda: defaultdict(Counter)), defaultdict(lambda: defaultdict(Counter))
    for entry in entries:
        every[entry.group][entry.task][entry.verdict] += 1
        if entry.counted:
            counted[entry.group][entry.task][entry.verdict] += 1
    return {"all": plain_counts(every), "counted": plain_counts(counted)}


def plain_counts(table: dict) -> dict:
    return {group: {task: dict(verdicts) for task, verdicts in by_task.items()} for group, by_task in table.items()}


def tally(trials, after: bool = False) -> dict:
    found = {"passes": sum(t.passed(after) for t in trials), "trials": len(trials),
             "not_graded": sum(t.not_graded(after) for t in trials)}
    if after:  # how the after-feedback passes got there: "32 of 40: 20 passed first time, 12 after feedback"
        found |= {"passed_first": sum(t.passed() for t in trials),
                  "passed_after_feedback": sum(t.passed(True) and not t.passed() for t in trials)}
    return found


def excluded(entries: list[Entry], group: str, model: str) -> dict:
    """Saved trials of this model and condition that the scorecard leaves out, by reason and task."""
    left_out = [e for e in entries if e.group == group and e.model == model and not e.counted]
    reasons = Counter(e.excluded_reason for e in left_out)
    return {"count": len(left_out), "by_reason": [{"reason": r, "count": n} for r, n in reasons.most_common()],
            "by_task": dict(Counter(e.task for e in left_out))}


def cant_tell_tally(trials) -> dict:
    """Trials (and their passes) in which the person answered some test piece "I can't tell you how that one came out"."""
    told = [t for t in trials if t.told_cant_tell]
    return {"trials": len(told), "passes": sum(t.passed() for t in told)}


def rate(passes: int, trials: int) -> dict:
    return {"passes": passes, "trials": trials, "rate": passes / trials if trials else None}


def matched(entries: list[Entry], tested: list) -> dict:
    """First print against test-first over the same model, task and trial numbers only: the trials both conditions
    have. Trial n in one condition has nothing to do with trial n in the other; this only evens out how many trials each
    model and task contributes (test-first lost some to out-of-credit errors). Not a scorecard.py statistic."""
    models_ = {row.model for row in tested}
    first = {(e.model, e.task, e.trial): e.verdict == "pass" for e in entries
             if e.group == "first" and e.counted and e.task in scorecard.TASKS and e.model in models_}
    tested_ = {(e.model, e.task, e.trial): e.verdict == "pass" for e in entries
               if e.group == "test_first" and e.counted and e.task in scorecard.TASKS and e.model in models_}
    both = sorted(set(first) & set(tested_))
    per_model = {}
    for model in sorted(models_):
        keys = [key for key in both if key[0] == model]
        per_model[model] = {"first": rate(sum(first[k] for k in keys), len(keys)),
                            "test_first": rate(sum(tested_[k] for k in keys), len(keys))}
    return {"note": " ".join(matched.__doc__.split()),
            "first": rate(sum(first[k] for k in both), len(both)), "test_first": rate(sum(tested_[k] for k in both), len(both)),
            "per_model": per_model}


def task_names() -> dict:
    return {task: {"label": TASK_NAMES[task], "short": TASK_SHORT[task]} for task in HEADLINE_TASKS}


def scorecard_block(listed: list, entries: list[Entry]) -> dict:
    """The README's aggregates, from scorecard.py's own Row and Trial methods, keyed by task id."""
    tested = scorecard.tested_order(listed)
    rows = []
    for row in listed:
        trials = row.all_trials()
        tested_trials = row.tested_trials()
        rows.append({
            "model": row.model, "short": short_name(row.model), "replayed": row.replayed(),
            "first": {"by_task": {task: tally(row.by_task[task]) for task in scorecard.TASKS},
                      "passes": row.passes(), "trials": len(trials), "rate": row.pass_rate(), "not_graded": row.not_graded(),
                      "excluded": excluded(entries, "first", row.model)},
            "after_feedback": {"by_task": {task: tally(row.by_task[task], True) for task in scorecard.TASKS},
                               "passes": row.passes(True), "trials": len(trials), "passed_first": row.passes(),
                               "passed_after_feedback": row.passes(True) - row.passes(),
                               "rate": row.pass_rate(True), "not_graded": row.not_graded(True),
                               "replays_replaced_by_regrade": sum(1 for e in entries if e.group == "second" and e.model == row.model
                                                                  and not e.counted and e.verdict != "error" and e.task in scorecard.TASKS),
                               "cost_usd": row.cost(True), "cost_per_pass": row.cost(True) / row.passes(True) if row.passes(True) else None,
                               "est_print_s_per_pass": row.per_pass("print_s", True), "est_grams_per_pass": row.per_pass("grams", True)},
            "test_first": {"by_task": {task: tally(row.tested.get(task, [])) | {"cant_tell": cant_tell_tally(row.tested.get(task, []))}
                                       for task in HEADLINE_TASKS},
                           "passes": sum(t.passed() for t in tested_trials), "trials": len(tested_trials),
                           "rate": row.tested_rate(), "cost_per_pass": row.tested_per_pass("cost"),
                           "est_print_s_per_pass": row.tested_per_pass("print_s"), "est_grams_per_pass": row.tested_per_pass("grams"),
                           "cant_tell": cant_tell_tally(tested_trials), "excluded": excluded(entries, "test_first", row.model)}
            if tested_trials else None,
            "tokens_per_trial": sum(t.tokens for t in trials) / len(trials),
            "change_points": round(100 * (row.tested_rate() - row.pass_rate())) if tested_trials else None})
    told = [t for row in tested for t in row.tested_trials()]
    first_n = sum(r.passes() for r in tested), sum(len(r.all_trials()) for r in tested)
    return {
        "note": "Computed by scripts/scorecard.py's functions from the saved runs: the same numbers as the README's "
                "Results section.",
        "order": {"models": "pass rate after feedback (the second print), highest first, then lower total cost "
                            "(scorecard.rows())",
                  "test_first_order": "test-first pass rate on the four tasks, highest first, then lower cost per pass "
                                      "(scorecard.tested_order(); the README's ranking and its picture use this order)",
                  "not_tested_order": "first-print pass rate, highest first"},
        "tasks": task_names(), "scored_tasks": list(scorecard.TASKS), "harder_task": scorecard.HARDER[0],
        "min_trials": scorecard.MIN_TRIALS, "skipped": scorecard.SKIPPED, "models": rows,
        "test_first_order": [row.model for row in tested],
        "not_tested_order": [row.model for row in sorted((r for r in listed if not r.tested_trials()), key=lambda r: -r.pass_rate())],
        "pooled": {"models": len(tested), "model_ids": [row.model for row in tested],
                   "first": rate(*first_n),
                   "after_feedback": rate(sum(r.passes(True) for r in tested), first_n[1]),
                   "test_first": rate(sum(sum(t.passed() for t in r.tested_trials()) for r in tested),
                                      sum(len(r.tested_trials()) for r in tested)),
                   "first_rate": first_n[0] / first_n[1],
                   "test_first_rate": sum(sum(t.passed() for t in r.tested_trials()) for r in tested) / sum(len(r.tested_trials()) for r in tested)},
        "matched_trial_numbers": matched(entries, tested),
        "cant_tell": {"trials": len(told), "told": sum(t.told_cant_tell for t in told),
                      "passes": sum(t.passed() for t in told), "passes_after_cant_tell": sum(t.passed() and t.told_cant_tell for t in told)},
        "estoa_line": scorecard.estoa_line(),
    }


DEFINITIONS = {
    "pass": "Every counted check passes on Dan's recorded test prints.",
    "fail": "At least one counted check fails.",
    "not graded": "No recorded print decides at least one check, and none fails. Never counted as a pass.",
    "not reached": "A check that couldn't be read because an earlier failure blocked it (for example the part didn't "
                   "build). Shown apart from not graded; the trial's verdict and every count are unchanged.",
    "declined": "The model handed in no final part on purpose. Neither a pass nor a fail; never counted as a pass.",
    "no design": "The model never handed in a design.",
    "error": "The trial stopped for an infrastructure reason (for example out of API credit), so it says nothing "
             "about the model and is left out of the counts.",
    "not counted": "Shown for completeness but left out of the scorecard, with the reason beside it.",
    "cost per passing design": "What the API provider charged for all of the model's trials in that condition, test "
                               "prints and second prints included, divided by the number of passes.",
    "print time and filament": "Estimates from the slicer (Bambu Studio) for everything the model handed in, final "
                               "parts and test prints, as if each were printed once. Nothing was actually printed.",
    "Dan": "The eval's author. He printed the test pieces whose recorded results the graders and the simulated person use.",
    "simulated person": "The person the model talks to is a program, not a human: it answers measurements from a fixed "
                        "list and says how a print came out only from Dan's recorded test prints.",
    "test print": "A small piece the model asks for to settle a size before its final design.",
}


def scorecard_file(index: dict) -> dict:
    """data/scorecard.json: enough to paint the scorecard before index.json arrives."""
    return {"schema_version": SCHEMA_VERSION, "scorecard": index["scorecard"], "definitions": DEFINITIONS,
            "tasks": {task: {"label": info["label"], "short": info["short"], "scored": info["scored"], "harder": info["harder"]}
                      for task, info in index["tasks"].items()},
            "models": index["models"], "notes": index["notes"],
            "groups": [g for g in index["groups"] if g["category"] == HEADLINE]}


# ---- writing ----

def redact(text: str, hits: Counter, where: str) -> str:
    for pattern, replacement in REDACTIONS:
        text, found = pattern.subn(replacement, text)
        if found:
            hits[where] += found
    return text


def write_json(path: Path, value, hits: Counter, where: str, indent=None) -> int:
    text = redact(json.dumps(value, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":")), hits, where)
    path.write_text(text)
    return len(text.encode())


@cache
def pinned_ref() -> str:
    """The commit links point at: $GITHUB_SHA in CI, else HEAD if the tree is clean, else main."""
    import os
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "main"
    return commit() or "main" if not dirty else "main"


def transcript_base() -> str:
    return f"{REPO}{pinned_ref()}/results/runs/"


def commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def index_of(entries: list[Entry], listed: list, sliced: dict) -> dict:
    by_id = {entry.id: entry for entry in entries}
    rows = [index_row(entry, sliced, by_id) for entry in entries]  # first: it fills REASON_GROUP_LABELS
    reasons = not_graded_reasons()
    return {
        "schema_version": SCHEMA_VERSION, "commit": commit(), "transcript_base": transcript_base(), "links_pinned_to": pinned_ref(),
        "notes": {
            "printing": "Nothing a model designed was printed. Each design is graded by code against Dan's recorded "
                        "test prints; the simulated person's answers come from those records only.",
            "not_graded": "Not graded means no recorded print decides a check. It is never a pass.",
            "test_print": "A test print is a small piece the model asks for to settle a size before its final design.",
        },
        "condition_labels": CONDITION_LABELS, "reason_groups": dict(sorted(REASON_GROUP_LABELS.items())),
        "verdicts": VERDICTS, "basis_labels": BASIS_LABELS, "not_graded_reasons": reasons, "groups": groups(entries), "tasks": task_info(entries),
        "models": models(entries, listed), "counts": counts(entries), "scorecard": scorecard_block(listed, entries), "definitions": DEFINITIONS,
        "trials": rows,
    }


def placeholder_page() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Print Build Eval results</title>
<style>:root{--bg:#fff;--fg:#1f262b}@media (prefers-color-scheme: dark){:root{--bg:#15191c;--fg:#e4e9ec}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;margin:0 16px}</style>
</head><body><h1>Results</h1><p id="out">Loading data/index.json...</p>
<script>
fetch("data/index.json").then(r => r.json()).then(index => {
  const by = {};
  for (const t of index.trials) by[t.group] = (by[t.group] || 0) + 1;
  document.getElementById("out").textContent = index.trials.length + " trials: " +
    Object.entries(by).map(([g, n]) => g + " " + n).join(", ");
});
</script></body></html>
"""


def build(out: Path = OUT, details: bool = True) -> dict:
    """Write the site's data under out and copy the frontend; return what was written."""
    entries = collect()
    listed = scorecard.rows()
    sliced = scorecard.slice_rows()
    data = out / "data"
    shutil.rmtree(data, ignore_errors=True)
    (data / "trials").mkdir(parents=True)
    hits = Counter()
    index = index_of(entries, listed, sliced)
    sizes = {"index": write_json(data / "index.json", index, hits, "index.json"),
             "scorecard": write_json(data / "scorecard.json", scorecard_file(index), hits, "scorecard.json")}
    if details:
        by_id, prompts, trial_sizes = {entry.id: entry for entry in entries}, {}, []
        for entry in entries:
            trial_sizes.append(write_json(data / "trials" / f"{entry.slug}.json", detail(entry, sliced, by_id, prompts),
                                          hits, entry.id))
        sizes |= {"trials": len(trial_sizes), "trials_total": sum(trial_sizes), "trial_largest": max(trial_sizes),
                  "system_prompts": write_json(data / "system_prompts.json", prompts, hits, "system_prompts.json")}
    if not (FRONTEND / "index.html").exists():
        FRONTEND.mkdir(exist_ok=True)
        (FRONTEND / "index.html").write_text(placeholder_page())
    for path in FRONTEND.rglob("*"):
        if path.is_file():
            target = out / path.relative_to(FRONTEND)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    return {"entries": len(entries), "sizes": sizes, "redactions": dict(hits), "index": index}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--index-only", action="store_true", help="write index.json only, no per-trial files")
    args = parser.parse_args()
    written = build(args.out, details=not args.index_only)
    by_group = Counter(row["group"] for row in written["index"]["trials"])
    print(f"{written['entries']} entries ({', '.join(f'{g} {n}' for g, n in by_group.items())}); sizes {written['sizes']}; "
          f"{args.out}", file=sys.stderr)
    if written["redactions"]:
        print(f"redacted home-folder paths or keys in: {written['redactions']}", file=sys.stderr)


if __name__ == "__main__":
    main()
