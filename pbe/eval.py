"""Run tasks against models and save everything under results/runs/<run>/.

    uv run python -m pbe.eval --run pilot --task m5-spacer --model anthropic/claude-haiku-5.5 --trials 1 --budget 0.50
    uv run python -m pbe.eval --reference --task m5-spacer   # the reference must pass every check
    uv run python -m pbe.eval --regrade --run pilot --task m5-spacer   # saved submissions, current checks

Each trial saves transcript.json, submission.yaml, grades.json (and parts/, not committed).
A trial already saved is skipped, so a stopped run resumes; one that ended in an
infrastructure error is run again. The budget is checked before
each trial against what the run has spent so far, so the last trial can overshoot it.
"""
import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from pbe import agent, llm, submission, tasks

ROOT = Path(__file__).resolve().parents[1]


def slug(model):
    return model.replace("/", "__").replace(":", "_")


def spent(run_dir):
    return sum(json.loads(p.read_text())["cost_usd"] for p in run_dir.rglob("grades.json"))


def findings_json(findings):
    return [{"check": f.check, "part": f.part, "ok": f.ok, "detail": f.detail} for f in findings]


def commit():
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return r.stdout.strip() + ("-dirty" if dirty else "")


def run_one(task, model, condition, trial, run_dir, args):
    out = run_dir / task.id / condition / slug(model) / f"t{trial}"
    if (out / "grades.json").exists():
        done = json.loads((out / "grades.json").read_text())
        if done["outcome"] != "error":  # an infrastructure error isn't a result; run it again
            return done
    out.mkdir(parents=True, exist_ok=True)
    record, messages, sub = agent.run_trial(task, model, condition, max_turns=args.max_turns, max_tokens=args.max_tokens)
    findings, observations = agent.evaluate(task, sub, out) if sub else ([], {})
    record.update(trial=trial, date=datetime.now(timezone.utc).isoformat(timespec="seconds"), commit=commit(),
                  findings=findings_json(findings), observations=observations,
                  all_pass=bool(sub) and bool(findings) and all(f.ok is True for f in findings))
    (out / "transcript.json").write_text(json.dumps(messages, indent=1))
    if sub:
        (out / "submission.yaml").write_text(yaml.safe_dump(sub.model_dump(), sort_keys=False, allow_unicode=True))
    (out / "grades.json").write_text(json.dumps(record, indent=1))
    return record


def summarize(run_dir):
    rows = [json.loads(p.read_text()) for p in sorted(run_dir.rglob("grades.json"))]
    with open(run_dir / "summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["task", "condition", "model", "trial", "outcome", "all_pass", "failed_checks", "repairs",
                    "turns", "measured", "limitations", "cost_usd", "elapsed_s"])
        for r in rows:
            failed = [x["check"] for x in r["findings"] if x["ok"] is False]
            w.writerow([r["task"], r["condition"], r["model"], r["trial"], r["outcome"], r["all_pass"], " ".join(failed),
                        r["repairs"], r["turns"], " ".join(r["revealed"]), len(r["limitations"]), r["cost_usd"], r["elapsed_s"]])
    return rows


def regrade(run_dir, task_ids):
    """Grade saved submissions again with the current checks, without calling a model.
    The earlier verdicts stay in grades.json under `regrades`, so a changed result is visible."""
    for path in sorted(run_dir.rglob("grades.json")):
        r = json.loads(path.read_text())
        sub_path = path.parent / "submission.yaml"
        if r["task"] not in task_ids or not sub_path.exists():
            continue
        sub = submission.Submission.model_validate(yaml.safe_load(sub_path.read_text()))
        findings, observations = agent.evaluate(tasks.load(r["task"]), sub, path.parent)
        new = findings_json(findings)
        if observations != r.get("observations"):
            r["observations"] = observations
            path.write_text(json.dumps(r, indent=1))
        if new != r["findings"]:
            r.setdefault("regrades", []).append({"date": r["date"], "commit": r["commit"], "findings": r["findings"], "all_pass": r["all_pass"]})
            r.update(findings=new, all_pass=bool(findings) and all(f.ok is True for f in findings),
                     date=datetime.now(timezone.utc).isoformat(timespec="seconds"), commit=commit())
            path.write_text(json.dumps(r, indent=1))
            print(f"{r['model']}: all_pass {r['regrades'][-1]['all_pass']} -> {r['all_pass']}")


def check_references(task_ids):
    ok = True
    for tid in task_ids:
        task = tasks.load(tid)
        if task.reference is None:
            print(f"{tid}: no reference.yaml")
            ok = False
            continue
        sub = submission.load(task.reference)
        findings = agent.grade(task, sub, ROOT / "results/local/reference" / tid)
        for f in findings:
            print(f"{tid:12} {'pass' if f.ok else 'not graded' if f.ok is None else 'FAIL':10} {f.check:16} {f.detail}")
            ok &= f.ok is True
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", action="append", required=True)
    ap.add_argument("--model", action="append", default=[])
    ap.add_argument("--condition", action="append", choices=agent.CONDITIONS)
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--run", default="scratch")
    ap.add_argument("--budget", type=float, default=1.0, help="USD for the whole run")
    ap.add_argument("--max-turns", type=int, default=8)
    ap.add_argument("--max-tokens", type=int, default=32000)
    ap.add_argument("--reference", action="store_true", help="grade each task's reference solution instead")
    ap.add_argument("--regrade", action="store_true", help="grade the run's saved submissions again with the current checks")
    args = ap.parse_args()
    if args.reference:
        sys.exit(0 if check_references(args.task) else 1)
    if args.regrade:
        run_dir = ROOT / "results/runs" / args.run
        regrade(run_dir, args.task)
        summarize(run_dir)
        return
    if not args.model:
        ap.error("--model is required unless --reference")
    try:
        llm._key()  # fail now, not once per trial
    except llm.LLMError as e:
        sys.exit(str(e))
    run_dir = ROOT / "results/runs" / args.run
    for tid in args.task:
        task = tasks.load(tid)
        for condition in args.condition or ["can_ask"]:
            for model in args.model:
                for trial in range(1, args.trials + 1):
                    if (s := spent(run_dir)) >= args.budget:
                        print(f"budget reached: ${s:.4f} of ${args.budget:.2f}; stopping")
                        break
                    r = run_one(task, model, condition, trial, run_dir, args)
                    failed = [x["check"] for x in r["findings"] if x["ok"] is False]
                    print(f"{tid} {condition} {model} t{trial}: {r['outcome']}, all_pass={r['all_pass']}, "
                          f"failed={failed}, repairs={r['repairs']}, turns={r['turns']}, ${r['cost_usd']:.4f}, {r['elapsed_s']} s"
                          + (f"\n  error: {r['error'][:300]}" if r["error"] else ""))
    summarize(run_dir)
    print(f"spent ${spent(run_dir):.4f}; summary in {run_dir / 'summary.csv'}")


if __name__ == "__main__":
    main()
