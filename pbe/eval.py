"""Run tasks against models and save everything under results/runs/<run>/.

    uv run python -m pbe.eval --run pilot --task m5-spacer --model anthropic/claude-haiku-5.5 --trials 1 --budget 0.50
    uv run python -m pbe.eval --reference --task m5-spacer   # the reference must pass every check
    uv run python -m pbe.eval --regrade --run pilot --task m5-spacer   # saved submissions, current checks
    uv run python -m pbe.eval --run pilot-code --condition can_run_code --task m5-spacer --model ... --budget 0.50

Each trial saves transcript.json, submission.yaml, grades.json (and parts/, not committed;
in can_run_code also workspace/, run_python's working folder, not committed).
A trial already saved is skipped, so a stopped run resumes; one that ended in an
infrastructure error is run again. The budget is checked before
each trial against what the run has spent so far, so the last trial can overshoot it.
"""
import argparse
import csv
import itertools
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from pbe.graders import declined
from pbe.graders.checks import verdict_word
from pbe.parts import build, submission
from pbe.runner import agent, code_sandbox, llm, python_tool, tasks
from pbe.runner.trial_record import TrialRecord

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = f"{platform.system()}-{platform.machine()}"  # geometry comes from a platform's own CAD kernel wheel

# only what decides a result: the run's own saved files would mark every trial after the first
RESULT_DECIDING_PATHS = ["pbe", "tasks", "catalog", "results/predictions", "pyproject.toml", "uv.lock"]

SUMMARY_COLUMNS = {
    "task": lambda record: record.task,
    "condition": lambda record: record.condition,
    "model": lambda record: record.model,
    "trial": lambda record: record.trial,
    "outcome": lambda record: record.outcome,
    "all_pass": lambda record: record.all_pass,
    "failed_checks": lambda record: " ".join(record.failed_checks),
    "not_graded": lambda record: " ".join(record.not_graded_checks),
    "repairs": lambda record: record.repairs,
    "turns": lambda record: record.turns,
    "measured": lambda record: " ".join(record.revealed),
    "limitations": lambda record: len(record.limitations),
    "cost_usd": lambda record: record.cost_usd,
    "elapsed_s": lambda record: record.elapsed_s,
    # added after the columns above, so a reader that goes by position still finds them
    "verdict": lambda record: record.verdict,
    "test_print_failed": lambda record: " ".join(record.test_print_failed_checks),
    "declined": lambda record: record.declined or "",
}


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def code_version():
    """The short commit hash, marked -dirty if code that decides results has uncommitted changes."""
    has_changes = git("status", "--porcelain", "--", *RESULT_DECIDING_PATHS)
    return git("rev-parse", "--short", "HEAD") + ("-dirty" if has_changes else "")


def stamp_version(record):
    record.date = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record.commit = code_version()
    record.platform = PLATFORM


def spent(run_dir):
    return sum(record.cost_usd for _, record in TrialRecord.all_in(run_dir))


def trial_folder(run_dir, task, condition, model, trial):
    model_name = model.replace("/", "__").replace(":", "_")
    return run_dir / task.id / condition / model_name / f"t{trial}"


def save_conversation(folder, messages, sub):
    (folder / "transcript.json").write_text(json.dumps(messages, indent=1))
    if sub:
        (folder / "submission.yaml").write_text(yaml.safe_dump(sub.model_dump(), sort_keys=False, allow_unicode=True))


def grade_and_save(task, sub, folder, record):
    findings, record.observations = agent.evaluate(task, sub, folder)
    record.set_verdict(findings, declined.reason(sub, findings))
    stamp_version(record)
    record.save(folder)
    return record


def finish_saved_trial(task, saved, folder):
    """A saved trial needs no new model call: at most, finish grading it."""
    if saved.stopped_during_grading:
        return grade_and_save(task, submission.load(folder / "submission.yaml"), folder, saved)
    return saved


def run_one(task, model, condition, trial, run_dir, args):
    folder = trial_folder(run_dir, task, condition, model, trial)
    saved = TrialRecord.load_if_saved(folder)
    if saved and saved.outcome != "error":  # an infrastructure error isn't a result; run it again
        return finish_saved_trial(task, saved, folder)
    already_paid = saved.cost_usd if saved else 0.0  # the failed attempt was still paid for

    folder.mkdir(parents=True, exist_ok=True)
    max_turns = args.max_turns or agent.DEFAULT_MAX_TURNS[condition]
    record, messages, sub = agent.run_trial(task, model, condition, max_turns=max_turns, max_tokens=args.max_tokens,
                                            workdir=folder / "workspace")
    record.cost_usd = round(record.cost_usd + already_paid, 6)
    record.trial = trial
    stamp_version(record)
    # saved before grading with no findings, so if grading breaks the paid conversation and its
    # cost are kept, and rerunning finishes the grading instead of paying for the trial again
    save_conversation(folder, messages, sub)
    record.save(folder)
    return grade_and_save(task, sub, folder, record) if sub else record


def summarize(run_dir):
    records = [record for _, record in TrialRecord.all_in(run_dir)]
    with open(run_dir / "summary.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(SUMMARY_COLUMNS)
        for record in records:
            writer.writerow(column(record) for column in SUMMARY_COLUMNS.values())
    return records


def is_selected(task_id, task_ids):
    family = task_id.split("/")[0]  # naming a family regrades all its variants
    return task_id in task_ids or family in task_ids


def what_decides(record):
    """What a trial's verdict is made of: each finding as the checks read it, which of them count,
    and whether it declined. A passing test print's finding gaining its mark changes none of these."""
    read = [(finding.check, finding.part, finding.ok, finding.detail) for finding in record.findings]
    return read, record.failed_checks, record.not_graded_checks, record.declined


def regrade_one(record, sub, folder):
    findings, observations = agent.evaluate(tasks.load(record.task), sub, folder)
    regraded = record.model_copy(deep=True)
    regraded.set_verdict(findings, declined.reason(sub, findings))
    verdict_changed = what_decides(regraded) != what_decides(record)
    if not verdict_changed and observations == record.observations:
        return
    record.observations = observations
    if verdict_changed:
        was = record.verdict
        record.keep_verdict_as_earlier()
        record.set_verdict(findings, regraded.declined)
        stamp_version(record)
        print(f"{record.task} {record.condition} {record.model} t{record.trial}: {was} -> {record.verdict}")
    record.save(folder)


def regrade(run_dir, task_ids):
    """Grade saved submissions again with the current checks, without calling a model.
    The earlier verdicts stay in grades.json under `regrades`, so a changed result is visible."""
    for folder, record in TrialRecord.all_in(run_dir):
        sub_path = folder / "submission.yaml"
        if is_selected(record.task, task_ids) and sub_path.exists():
            regrade_one(record, submission.load(sub_path), folder)


def check_references(task_ids):
    all_ok = True
    for task_id in task_ids:
        task = tasks.load(task_id)
        if task.reference is None:
            print(f"{task_id}: no reference.yaml")
            all_ok = False
            continue
        findings = agent.grade(task, submission.parse(task.reference), ROOT / "results/local/reference" / task_id)
        for finding in findings:
            print(f"{task_id:14} {verdict_word(finding.ok):10} {finding.check:16} {finding.detail}")
            all_ok &= finding.ok is True
    return all_ok


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", action="append", required=True)
    ap.add_argument("--model", action="append", default=[])
    ap.add_argument("--condition", action="append", choices=agent.CONDITIONS)
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--run", default="scratch")
    ap.add_argument("--budget", type=float, default=1.0, help="USD for the whole run")
    ap.add_argument("--max-turns", type=int, help="default: 8, or 20 for can_run_code (agent.DEFAULT_MAX_TURNS)")
    ap.add_argument("--max-tokens", type=int, default=32000)
    ap.add_argument("--reference", action="store_true", help="grade each task's reference solution instead")
    ap.add_argument("--regrade", action="store_true", help="grade the run's saved submissions again with the current checks")
    args = ap.parse_args()
    if not (args.model or args.reference or args.regrade):
        ap.error("--model is required unless --reference or --regrade")
    return args


def exit_unless_able_to_run(conditions):
    """Fail now, not once per trial."""
    try:
        llm._key()
        build.require_sandbox()
        if python_tool.CONDITION in conditions:
            code_sandbox.find()
    except (llm.LLMError, RuntimeError) as e:
        sys.exit(str(e))


def progress_line(record):
    line = (f"{record.task} {record.condition} {record.model} t{record.trial}: {record.outcome}, "
            f"{record.verdict}, failed={record.failed_checks}, repairs={record.repairs}, "
            f"turns={record.turns}, ${record.cost_usd:.4f}, {record.elapsed_s} s")
    if built := record.build_on_submit:
        line += f", sent back unbuilt {len(built.sent_back)}x" + (", out of turns while fixing" if built.out_of_turns_while_fixing else "")
    return f"{line}\n  error: {record.error[:300]}" if record.error else line


def run_all_trials(args, run_dir):
    trial_numbers = range(1, args.trials + 1)
    for task_id, condition, model, trial in itertools.product(args.task, args.condition, args.model, trial_numbers):
        if (so_far := spent(run_dir)) >= args.budget:
            print(f"budget reached: ${so_far:.4f} of ${args.budget:.2f}; stopping")
            return
        print(progress_line(run_one(tasks.load(task_id), model, condition, trial, run_dir, args)))


def main():
    args = parse_args()
    if args.reference:
        sys.exit(0 if check_references(args.task) else 1)
    run_dir = ROOT / "results/runs" / args.run
    if args.regrade:
        regrade(run_dir, args.task)
        summarize(run_dir)
        return
    args.condition = args.condition or ["can_ask"]
    exit_unless_able_to_run(args.condition)
    run_all_trials(args, run_dir)
    summarize(run_dir)
    print(f"spent ${spent(run_dir):.4f}; summary in {run_dir / 'summary.csv'}")


if __name__ == "__main__":
    main()
