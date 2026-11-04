"""Run the coupon loop's sample (docs/coupon-loop.md): replay saved trials with one more turn, in two arms.

    uv run python scripts/coupon_loop.py --run loop-sample-2 --budget 3.00

Each replayed trial gets three folders under results/runs/<run>/<its folder under results/runs>/:
baseline (the saved design, graded with its coupons left out), feedback and neutral, each with a
loop.json, and the two second turns with their transcript.json and submission.yaml. A folder
already saved is skipped, so a stopped run resumes; one that ended in an infrastructure error runs again. summary.csv has one row per trial.
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pbe.eval import PLATFORM, code_version, git, save_conversation  # noqa: E402
from pbe.parts import submission  # noqa: E402
from pbe.parts.build import build_parts  # noqa: E402
from pbe.runner import coupon_loop, tasks  # noqa: E402
from pbe.runner.trial_record import TrialRecord  # noqa: E402

MODELS = ["anthropic/claude-sonnet-5.5", "deepseek/deepseek-v4.1-flash", "z-ai/glm-5.3-flash"]
FAMILIES = ("nut-knob", "bearing-wheel")
RUNS = ROOT / "results/runs"
LOOP_RUNS = ("loop-sample", "loop-sample-2")  # replays, not trials to replay


def sample():
    """The saved knob and wheel trials with a test coupon, for the sample's models: (folder, record, submission)."""
    for folder, record in TrialRecord.all_in(RUNS):
        if folder.relative_to(RUNS).parts[0] in LOOP_RUNS or record.model not in MODELS or record.task.split("/")[0] not in FAMILIES:
            continue
        if not (folder / "submission.yaml").exists():  # no design handed in, so no coupon
            continue
        sub = submission.load(folder / "submission.yaml")
        if any(part.role == "coupon" for part in sub.parts):
            yield folder, record, sub


def spent(out):
    return sum(coupon_loop.LoopRecord.load(path.parent).cost_usd for path in out.rglob(coupon_loop.FILE_NAME))


def loop_code_version():
    """code_version(), also marked -dirty if this script, which picks the trials and runs the arms, has uncommitted changes."""
    version = code_version()
    if git("status", "--porcelain", "--", "scripts/coupon_loop.py") and not version.endswith("-dirty"):
        version += "-dirty"
    return version


def stamp(record):
    record.date = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record.commit = loop_code_version()
    record.platform = PLATFORM


def grade_baseline(task, saved, sub, folder, replayed):
    record = coupon_loop.LoopRecord(task=saved.task, model=saved.model, arm="baseline", replayed=replayed, outcome="saved")
    record.set_verdict(coupon_loop.grade(task, sub, folder))
    stamp(record)
    record.save(folder)


def earlier_cost(folder):
    """What an earlier attempt at this arm was charged, so a retry after an infrastructure error doesn't drop it."""
    if not (folder / coupon_loop.FILE_NAME).exists():
        return 0.0
    return coupon_loop.LoopRecord.load(folder).cost_usd


def stopped_while_grading(record):
    return record.outcome == "submitted" and not record.findings


def finish_grading(task, folder):
    """An arm saved after its paid turn but before grading finished: grade its saved design, with no new model call."""
    record = coupon_loop.LoopRecord.load(folder)
    record.set_verdict(coupon_loop.grade(task, submission.load(folder / "submission.yaml"), folder))
    stamp(record)
    record.save(folder)


def run_arm(task, saved, arm, text, report, saved_messages, folder, replayed):
    already_paid = earlier_cost(folder)
    turn = coupon_loop.second_turn(task, saved.model, saved_messages, text)
    record = coupon_loop.LoopRecord(
        task=saved.task, model=saved.model, arm=arm, replayed=replayed, outcome=turn.outcome, error=turn.error,
        turns=len(turn.calls), repairs=turn.repairs, measures=turn.measures,
        cost_usd=round(sum(call.cost_usd for call in turn.calls) + already_paid, 6),
        elapsed_s=turn.elapsed_s, calls=turn.calls, reply=text,
        report=coupon_loop.saved_report(report) if arm == "feedback" else {})
    folder.mkdir(parents=True, exist_ok=True)
    save_conversation(folder, turn.messages, turn.submission)
    # saved before grading, so if grading breaks, the paid turn and its cost are kept and a rerun only finishes grading
    stamp(record)
    record.save(folder)
    if turn.submission is not None:
        finish_grading(task, folder)


def is_settled(arm_folder):
    """An arm with a result. One that stopped on an infrastructure error, such as the account running out of
    credit, isn't a result: it runs again, as pbe/eval.py does for a first turn."""
    if not (arm_folder / coupon_loop.FILE_NAME).exists():
        return False
    record = coupon_loop.LoopRecord.load(arm_folder)
    return record.outcome != "error" and not stopped_while_grading(record)


def replay(folder, saved, sub, budget, out_root):
    """Grade the baseline and run whichever arms aren't saved yet. False once the budget is spent."""
    replayed = str(folder.relative_to(RUNS))
    out = out_root / replayed
    task = tasks.load(saved.task)
    coupons_only = sub.model_copy(update={"parts": [part for part in sub.parts if part.role == "coupon"]})
    report = coupon_loop.coupon_report(task, sub, build_parts(coupons_only, out / "parts"))
    if not (out / "baseline" / coupon_loop.FILE_NAME).exists():
        grade_baseline(task, saved, sub, out / "baseline", replayed)
    saved_messages = json.loads((folder / "transcript.json").read_text())
    for arm, text in (("feedback", coupon_loop.feedback_text(report)), ("neutral", coupon_loop.NEUTRAL)):
        if is_settled(out / arm):
            continue
        if (out / arm / coupon_loop.FILE_NAME).exists() and stopped_while_grading(coupon_loop.LoopRecord.load(out / arm)):
            finish_grading(task, out / arm)
            continue
        if spent(out_root) >= budget:
            print(f"budget reached: ${spent(out_root):.4f}; stopping")
            return False
        run_arm(task, saved, arm, text, report, saved_messages, out / arm, replayed)
    return True


def summary_row(folder, out_root):
    replayed = str(folder.relative_to(RUNS))
    row = {"trial": replayed}
    for arm in ("baseline", "feedback", "neutral"):
        arm_folder = out_root / replayed / arm
        if not (arm_folder / coupon_loop.FILE_NAME).exists():
            continue
        record = coupon_loop.LoopRecord.load(arm_folder)
        row[arm] = record.summary()
        row[f"{arm}_cost"] = record.cost_usd
        if record.report:
            row["report_rests_on"] = " | ".join(line.basis for lines in record.report.values() for line in lines)
    return row


def write_summary(folders, out_root):
    rows = [summary_row(folder, out_root) for folder in folders]
    fields = ["trial", "report_rests_on", "baseline", "feedback", "neutral", "feedback_cost", "neutral_cost"]
    with open(out_root / "summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="loop-sample-2", choices=LOOP_RUNS, help="the folder under results/runs to save in")
    parser.add_argument("--budget", type=float, default=3.0, help="USD for the whole sample")
    args = parser.parse_args()
    out_root = RUNS / args.run
    folders = []
    for folder, saved, sub in sample():
        folders.append(folder)
        if not replay(folder, saved, sub, args.budget, out_root):
            break
        print(summary_row(folder, out_root), flush=True)
    write_summary(folders, out_root)
    print(f"spent ${spent(out_root):.4f}")


if __name__ == "__main__":
    main()
