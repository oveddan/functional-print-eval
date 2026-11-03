"""What happened in a run, short enough to read in one go, with no model calls.

    uv run python scripts/digest.py pilot-nut-knob-2                # one line per trial
    uv run python scripts/digest.py pilot-nut-knob-2 --why          # plus each failure's evidence
    uv run python scripts/digest.py pilot-nut-knob-2 --why --task nut-knob/M3 --model opus

--why prints, for each trial that didn't pass: what failed and wasn't graded with the check's
reason, what the model asked the person, what it reported as a limitation, its own note, and
which params it guessed. That settles most failures. Open transcript.json only for the rest.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CUT = 220


def short(text, n=CUT):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n] + "..."


def trials(run, task, model):
    for path in sorted((ROOT / "results/runs" / run).rglob("grades.json")):
        r = json.loads(path.read_text())
        if (not task or r["task"] == task) and (not model or model in r["model"]):
            yield path.parent, r


def verdict(r):
    if r["outcome"] != "submitted":
        return r["outcome"]
    if r["all_pass"]:
        return "pass"
    bad = [f["check"] for f in r["findings"] if f["ok"] is False]
    unknown = [f["check"] for f in r["findings"] if f["ok"] is None]
    return "failed " + " ".join(dict.fromkeys(bad)) if bad else "not graded " + " ".join(dict.fromkeys(unknown))


def why(folder, r):
    for f in r["findings"]:
        if f["ok"] is not True:
            print(f"    {'FAIL' if f['ok'] is False else 'n/g '} {f['check']} {f['part']}: {short(f['detail'])}")
    if r.get("error"):
        print(f"    error: {short(r['error'])}")
    for m in r["measures"]:
        print(f"    asked {short(m['item'], 40)} / {short(m['what'], 50)} -> {short(m['reply'], 90)}")
    for lim in r["limitations"]:
        print(f"    limitation: {short(lim.get('wanted', ''), 110)} / {short(lim.get('blocked_by', ''), 60)}")
    sub_path = folder / "submission.yaml"
    if sub_path.exists():
        sub = yaml.safe_load(sub_path.read_text())
        print(f"    note: {short(sub.get('note', ''))}")
        guessed = [k for k, v in sub["params"].items() if v.get("source") in ("guessed", "unknown")]
        if guessed:
            print(f"    guessed: {', '.join(guessed)}")
        claimed = [k for k, v in sub["params"].items() if v.get("source") in ("measured", "asked")]
        if claimed and not r["revealed"]:
            print(f"    says measured or asked, but nobody told it anything: {', '.join(claimed)}")
        print(f"    parts: {', '.join(p['id'] + ':' + p['role'] for p in sub['parts'])}; hardware: {', '.join(h['ref'] for h in sub['hardware']) or 'none'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--why", action="store_true")
    ap.add_argument("--task")
    ap.add_argument("--model", help="part of a model's name")
    args = ap.parse_args()
    tally, cost = Counter(), 0.0
    for folder, r in trials(args.run, args.task, args.model):
        v = verdict(r)
        tally["not graded" if v.startswith("not") else v.split()[0]] += 1
        cost += r["cost_usd"]
        print(f"{r['task']} {r['condition']} {r['model'].split('/')[-1]} t{r['trial']}: {v} (asked {len(r['measures'])}, ${r['cost_usd']:.3f})")
        if args.why and v != "pass":
            why(folder, r)
    print(f"{sum(tally.values())} trials: {dict(tally)}, ${cost:.2f}")


if __name__ == "__main__":
    main()
