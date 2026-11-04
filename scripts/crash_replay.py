"""Run the crash replay (issue 27, docs/crash-replay.md): each saved crashed trial gets one retry with its saved build error.

    uv run python scripts/crash_replay.py --budget 1.50

Each trial is saved under results/runs/crash-replay/<its folder under results/runs>/ with replay.json, the
retry's transcript.json (only the messages it added) and submission.yaml, and the parts it built. A trial
already saved is skipped, so a stopped run resumes; one that ended in an infrastructure error runs again, and
its cost still counts. A trial is saved before it's graded, so one that stopped while grading is graded on the
rerun with no new model call. summary.csv has one row per trial.
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pbe.eval import PLATFORM, code_version, save_conversation  # noqa: E402
from pbe.parts import submission  # noqa: E402
from pbe.runner import crash_replay, llm, tasks  # noqa: E402
from pbe.runner.crash_replay import ReplayRecord  # noqa: E402
from pbe.runner.trial_record import TrialRecord  # noqa: E402

RUNS = ROOT / "results/runs"
OUT = RUNS / "crash-replay"
SUMMARY_FIELDS = ["trial", "model", "saved_verdict", "outcome", "builds_now", "result", "failed", "not_graded", "turns", "repairs", "cost_usd"]


def spent(out_root: Path) -> float:
    return sum(ReplayRecord.load(path.parent).cost_usd for path in out_root.rglob(crash_replay.FILE_NAME))


def is_settled(folder: Path) -> bool:
    if not (folder / crash_replay.FILE_NAME).exists():
        return False
    record = ReplayRecord.load(folder)
    return not record.is_infrastructure_stop and not record.stopped_while_grading


def stopped_while_grading(folder: Path) -> ReplayRecord | None:
    """The saved retry in this folder, if it was paid for but not graded."""
    if not (folder / crash_replay.FILE_NAME).exists():
        return None
    record = ReplayRecord.load(folder)
    return record if record.stopped_while_grading else None


def stamp(record: ReplayRecord) -> None:
    record.date = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record.commit = code_version()
    record.platform = PLATFORM


def earlier_cost(folder: Path) -> float:
    """What an earlier attempt that stopped on an infrastructure error was charged."""
    if not (folder / crash_replay.FILE_NAME).exists():
        return 0.0
    return ReplayRecord.load(folder).cost_usd


def finish_grading(task, folder: Path) -> ReplayRecord:
    """Grade a saved retry's design, with no model call."""
    record = ReplayRecord.load(folder)
    crash_replay.grade(task, record, submission.load(folder / "submission.yaml"), folder)
    stamp(record)
    record.save(folder)
    return record


def run_one(replayed: str, out_root: Path, chat=llm.chat) -> ReplayRecord:
    saved_folder = RUNS / replayed
    saved = TrialRecord.load(saved_folder)
    saved_messages = json.loads((saved_folder / "transcript.json").read_text())
    task = tasks.load(saved.task)
    folder = out_root / replayed
    folder.mkdir(parents=True, exist_ok=True)
    retry = crash_replay.ask(task, saved, saved_messages, replayed, already_paid=earlier_cost(folder), chat=chat)
    # saved before grading, so if grading breaks, the paid turn and its cost are kept and a rerun only finishes grading
    save_conversation(folder, retry.messages, retry.submission)
    stamp(retry.record)
    retry.record.save(folder)
    if retry.submission is None:
        return retry.record
    return finish_grading(task, folder)


def summary_row(replayed: str, out_root: Path) -> dict:
    folder = out_root / replayed
    if not (folder / crash_replay.FILE_NAME).exists():
        return {"trial": replayed, "outcome": "not run"}
    record = ReplayRecord.load(folder)
    return {"trial": replayed, "model": record.model, "saved_verdict": record.saved_verdict, "outcome": record.outcome,
            "builds_now": crash_replay.builds_now(record.findings), "result": record.result,
            "failed": " ".join(dict.fromkeys(record.failed_checks)), "not_graded": " ".join(dict.fromkeys(record.not_graded_checks)),
            "turns": record.turns, "repairs": record.repairs, "cost_usd": record.cost_usd}


def write_summary(out_root: Path) -> None:
    with open(out_root / "summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summary_row(replayed, out_root) for replayed in crash_replay.CRASHED_TRIALS)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=float, default=1.50, help="USD of model spend for the whole replay")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for replayed in crash_replay.CRASHED_TRIALS:
        if is_settled(OUT / replayed):
            continue
        if paid := stopped_while_grading(OUT / replayed):
            finish_grading(tasks.load(paid.task), OUT / replayed)
            continue
        if spent(OUT) >= args.budget:
            print(f"budget reached: ${spent(OUT):.4f}; stopping")
            break
        record = run_one(replayed, OUT)
        print(summary_row(replayed, OUT), flush=True)
        if record.is_infrastructure_stop:
            print(f"infrastructure stop: {record.error}; stopping")
            break
    write_summary(OUT)
    print(f"spent ${spent(OUT):.4f}")


if __name__ == "__main__":
    main()
