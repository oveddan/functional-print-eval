"""Run the coupon loop's sample (docs/coupon-loop.md): replay saved trials with one more turn, in two arms.

    uv run python scripts/coupon_loop.py --run loop-sample-2 --budget 3.00
    uv run python scripts/coupon_loop.py --run loop-tripod --budget 3.00

loop-sample and loop-sample-2 replay knob and wheel trials with a test coupon, and report on the coupons.
loop-all replays every can_ask trial on the four scored tasks that didn't pass: the person prints everything
sent and says how it came out, then grades the final design (feedback arm only).
loop-tripod replays the tripod designs whose final part fails on a holed roof, and reports on everything
printed, the plate included (docs/coupon-loop.md, "Tripod sample"). A can_run_code trial keeps run_python
and its turn limit in the second turn.

Each replayed trial gets three folders under results/runs/<run>/<its folder under results/runs>/:
baseline (the saved design, graded with its coupons left out), feedback and neutral, each with a
loop.json, and the two second turns with their transcript.json and submission.yaml. A folder
already saved is skipped, so a stopped run resumes; one that ended in an infrastructure error runs again. summary.csv has one row per trial.
"""
import argparse
import csv
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pbe.eval import PLATFORM, code_version, git, save_conversation  # noqa: E402
from pbe.parts import submission  # noqa: E402
from pbe.parts.build import build_parts  # noqa: E402
from pbe.graders.bridges import is_holed_roof, overhangs  # noqa: E402
from pbe.runner import agent, coupon_loop, python_tool, tasks  # noqa: E402
from pbe.runner.python_tool import PythonTool  # noqa: E402
from pbe.runner.trial_record import TrialRecord  # noqa: E402

MODELS = ["anthropic/claude-sonnet-5.5", "deepseek/deepseek-v4.1-flash", "z-ai/glm-5.3-flash"]
FAMILIES = ("nut-knob", "bearing-wheel")
RUNS = ROOT / "results/runs"
LOOP_RUNS = ("loop-sample", "loop-sample-2", "loop-tripod", "loop-estoa", "loop-all")  # replays, not trials to replay
TRIPOD_RUNS = ("pilot-tripod", "pilot-tripod-given", "pilot-code")
# the bridge check fails these on a broken shape, not a roof (scripts/results_page.py, BROKEN_ROOFS)
BROKEN_ROOFS = {("pilot-tripod-given", "qwen/qwen3.8-flash", 1), ("pilot-tripod", "qwen/qwen3.8-flash", 1)}


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


def fails_on_holed_roof(folder, record, sub):
    """Does a final part fail `bridges` on a roof with a hole cut through it (bridges.is_holed_roof)?"""
    failed = {finding.part for finding in record.counted_findings if finding.check == "bridges" and finding.ok is False}
    finals = [part for part in sub.parts if part.role == "final" and part.id in failed]
    if not finals or (folder.relative_to(RUNS).parts[0], record.model, record.trial) in BROKEN_ROOFS:
        return False
    with tempfile.TemporaryDirectory() as out:
        built = build_parts(sub.model_copy(update={"parts": finals}), out)
        return any(built[part.id].ok and any(is_holed_roof(found) for found in overhangs(built[part.id].mesh)) for part in finals)


def tripod_sample():
    """The saved tripod designs whose final part fails on a holed roof, in every condition: (folder, record, submission)."""
    for run in TRIPOD_RUNS:
        for folder, record in TrialRecord.all_in(RUNS / run):
            if record.task != "tripod-plate" or not (folder / "submission.yaml").exists():
                continue
            sub = submission.load(folder / "submission.yaml")
            if fails_on_holed_roof(folder, record, sub):
                yield folder, record, sub


def estoa_sample():
    """The saved Estoa light designs that fail a check on the records (docs/coupon-loop.md, "Estoa sample")."""
    for folder, record in TrialRecord.all_in(RUNS / "pilot-estoa"):
        if record.task == "estoa-light" and record.failed_checks and (folder / "submission.yaml").exists():
            yield folder, record, submission.load(folder / "submission.yaml")


ALL_RUNS = ("pilot-tripod", "pilot-wheel", "pilot-nut-knob", "pilot-nut-knob-2")


def all_sample():
    """Every saved can_ask trial on the four scored tasks that didn't pass and handed in a design (loop-all): the person
    prints what was sent, says how it came out, and the model sends its final design. A trial that passed needs no
    second print."""
    for run in ALL_RUNS:
        for folder, record in sorted(TrialRecord.all_in(RUNS / run), key=lambda pair: (pair[1].model, pair[1].task, pair[1].trial)):
            if record.condition != "can_ask" or record.verdict == "pass" or not (folder / "submission.yaml").exists():
                continue
            yield folder, record, submission.load(folder / "submission.yaml")


SAMPLES = {"loop-sample": sample, "loop-sample-2": sample, "loop-tripod": tripod_sample, "loop-estoa": estoa_sample,
           "loop-all": all_sample}
FEEDBACK_ONLY = ("loop-all",)  # the neutral arm was measured on the samples; loop-all runs only the printed reply
PRINTS_THE_PLATE = ("loop-tripod",)


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


def run_arm(task, saved, arm, text, report, saved_messages, folder, replayed, max_turns):
    already_paid = earlier_cost(folder)
    python = PythonTool.for_trial(task.id, folder / "workspace") if saved.condition == python_tool.CONDITION else None
    turn = coupon_loop.second_turn(task, saved.model, saved_messages, text, max_turns=max_turns,
                                   condition=saved.condition, python=python,
                                   facts=coupon_loop.facts_as_saved(task, saved.hidden))
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
    if out_root.name == "loop-estoa":  # print it all and put it together: the report follows the baseline's failures
        if not (out / "baseline" / coupon_loop.FILE_NAME).exists():
            grade_baseline(task, saved, sub, out / "baseline", replayed)
        baseline = coupon_loop.LoopRecord.load(out / "baseline")
        report = coupon_loop.estoa_report(baseline.findings, out / "baseline" / "parts")
        printed, max_turns = coupon_loop.printed_text(report), agent.DEFAULT_MAX_TURNS[saved.condition]
    elif out_root.name == "loop-all":  # print everything sent, then the final design
        built = build_parts(sub, out / "parts")
        report = coupon_loop.printed_parts_report(task, sub, built)
        if saved.task == "tripod-plate":
            report = coupon_loop.coupon_report(task, sub, built) | coupon_loop.plate_report(task, sub, built)
        printed, max_turns = coupon_loop.printed_text(report), agent.DEFAULT_MAX_TURNS[saved.condition]
    elif out_root.name in PRINTS_THE_PLATE:
        built = build_parts(sub, out / "parts")
        report = coupon_loop.coupon_report(task, sub, built) | coupon_loop.plate_report(task, sub, built)
        printed, max_turns = coupon_loop.printed_text(report), agent.DEFAULT_MAX_TURNS[saved.condition]
    else:
        coupons_only = sub.model_copy(update={"parts": [part for part in sub.parts if part.role == "coupon"]})
        report = coupon_loop.coupon_report(task, sub, build_parts(coupons_only, out / "parts"))
        printed, max_turns = coupon_loop.feedback_text(report), coupon_loop.SECOND_TURN_CALLS
    if not (out / "baseline" / coupon_loop.FILE_NAME).exists():
        grade_baseline(task, saved, sub, out / "baseline", replayed)
    saved_messages = json.loads((folder / "transcript.json").read_text())
    arms = (("feedback", printed),) if out_root.name in FEEDBACK_ONLY else (("feedback", printed), ("neutral", coupon_loop.NEUTRAL))
    for arm, text in arms:
        if is_settled(out / arm):
            continue
        if (out / arm / coupon_loop.FILE_NAME).exists() and stopped_while_grading(coupon_loop.LoopRecord.load(out / arm)):
            finish_grading(task, out / arm)
            continue
        if spent(out_root) >= budget:
            print(f"budget reached: ${spent(out_root):.4f}; stopping")
            return False
        run_arm(task, saved, arm, text, report, saved_messages, out / arm, replayed, max_turns)
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
    parser.add_argument("--model", action="append", help="only these models' trials (repeatable), so one process per model can run side by side")
    args = parser.parse_args()
    out_root = RUNS / args.run
    folders = []
    for folder, saved, sub in SAMPLES[args.run]():
        if args.model and saved.model not in args.model:
            continue
        folders.append(folder)
        if not replay(folder, saved, sub, args.budget, out_root):
            break
        print(summary_row(folder, out_root), flush=True)
    write_summary(folders, out_root)
    print(f"spent ${spent(out_root):.4f}")


if __name__ == "__main__":
    main()
