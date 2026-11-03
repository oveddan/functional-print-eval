"""Validate a submission, build its parts and run the checks.

    uv run python -m pbe.run examples/arca-plate/original.yaml
"""
import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from pbe import checks, submission
from pbe.build import build_parts


def run(path, out_root="results/local"):
    path = Path(path)
    try:
        sub = submission.load(path)
    except ValidationError as e:
        print(f"{path}: not a valid submission\n{e}")
        return None
    built = build_parts(sub, Path(out_root) / path.parent.name / path.stem)
    findings = [f for check in checks.ALL for f in check(built)]
    return sub, built, findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    args = ap.parse_args()
    failed = False
    for p in args.paths:
        res = run(p)
        if res is None:
            failed = True
            continue
        sub, built, findings = res
        print(f"\n{p}  ({sub.task})")
        for f in findings:
            print(f"  {'pass' if f.ok else 'not graded' if f.ok is None else 'FAIL':10}  {f.check:18} {f.part:12} {f.detail}")
            failed |= f.ok is False
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
