"""What happened in a run, short enough to read in one go, with no model calls.

    uv run python scripts/digest.py pilot-nut-knob-2                # one line per trial
    uv run python scripts/digest.py pilot-nut-knob-2 --why          # plus each failure's evidence
    uv run python scripts/digest.py pilot-nut-knob-2 --why --task nut-knob/M3 --model opus

--why prints, for each trial that didn't pass: what failed and wasn't graded with the check's
reason, what the model asked the person, what it reported as a limitation, its own note, and
which params it guessed. That settles most failures. Open transcript.json only for the rest.
"""
import argparse
from collections import Counter
from pathlib import Path

from pbe.parts import submission
from pbe.runner.trial_record import TrialRecord

ROOT = Path(__file__).resolve().parents[1]
CUT = 220


def short(text, n=CUT):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n] + "..."


def trials(run, task, model):
    for folder, record in TrialRecord.all_in(ROOT / "results/runs" / run):
        if (not task or record.task == task) and (not model or model in record.model):
            yield folder, record


def verdict(record):
    if record.outcome != "submitted":
        return record.outcome
    if record.all_pass:
        return "pass"
    if record.failed_checks:
        return "failed " + " ".join(dict.fromkeys(record.failed_checks))
    return "not graded " + " ".join(dict.fromkeys(record.not_graded_checks))


def tally_key(verdict_text):
    """The verdict without the checks it names: "pass", "failed", "not graded" or an outcome."""
    return "not graded" if verdict_text.startswith("not") else verdict_text.split()[0]


def finding_mark(finding):
    return "FAIL" if finding.ok is False else "n/g "


def params_from(sub, sources):
    return [name for name, param in sub.params.items() if param.source in sources]


def print_submission(sub, record):
    """The model's note, which params it guessed, and what it handed in."""
    print(f"    note: {short(sub.note)}")
    guessed = params_from(sub, ("guessed", "unknown"))
    if guessed:
        print(f"    guessed: {', '.join(guessed)}")
    claimed = params_from(sub, ("measured", "asked"))
    if claimed and not record.revealed:
        print(f"    says measured or asked, but nobody told it anything: {', '.join(claimed)}")
    parts = ", ".join(f"{part.id}:{part.role}" for part in sub.parts)
    hardware = ", ".join(item.ref for item in sub.hardware) or "none"
    print(f"    parts: {parts}; hardware: {hardware}")


def why(folder, record):
    for finding in record.findings:
        if finding.ok is not True:
            print(f"    {finding_mark(finding)} {finding.check} {finding.part}: {short(finding.detail)}")
    if record.error:
        print(f"    error: {short(record.error)}")
    for measurement in record.measures:
        print(f"    asked {short(measurement.item, 40)} / {short(measurement.what, 50)} -> {short(measurement.reply, 90)}")
    for limitation in record.limitations:  # whatever the model passed, so any key may be missing
        print(f"    limitation: {short(limitation.get('wanted', ''), 110)} / {short(limitation.get('blocked_by', ''), 60)}")
    sub_path = folder / "submission.yaml"
    if sub_path.exists():
        print_submission(submission.load(sub_path), record)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--why", action="store_true")
    ap.add_argument("--task")
    ap.add_argument("--model", help="part of a model's name")
    args = ap.parse_args()
    tally, cost = Counter(), 0.0
    for folder, record in trials(args.run, args.task, args.model):
        verdict_text = verdict(record)
        tally[tally_key(verdict_text)] += 1
        cost += record.cost_usd
        model_name = record.model.split("/")[-1]
        print(f"{record.task} {record.condition} {model_name} t{record.trial}: {verdict_text} (asked {len(record.measures)}, ${record.cost_usd:.3f})")
        if args.why and verdict_text != "pass":
            why(folder, record)
    print(f"{sum(tally.values())} trials: {dict(tally)}, ${cost:.2f}")


if __name__ == "__main__":
    main()
