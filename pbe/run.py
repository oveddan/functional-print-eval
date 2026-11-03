"""Validate a submission, build its parts and run the checks.

    uv run python -m pbe.run examples/arca-plate/original.yaml
"""
import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from pbe.graders import checks
from pbe.graders.checks import verdict_word
from pbe.parts import submission
from pbe.parts.build import build_parts


def run(path, out_root="results/local"):
    path = Path(path)
    try:
        sub = submission.load(path)
    except ValidationError as e:
        print(f"{path}: not a valid submission\n{e}")
        return None
    built = build_parts(sub, Path(out_root) / path.parent.name / path.stem)
    findings = [finding for check in checks.ALL for finding in check(built)]
    return sub, built, findings


def check_one(path):
    """Print one submission's findings. True if none failed."""
    result = run(path)
    if result is None:
        return False
    sub, _, findings = result
    print(f"\n{path}  ({sub.task})")
    for finding in findings:
        print(f"  {verdict_word(finding.ok):10}  {finding.check:18} {finding.part:12} {finding.detail}")
    return not any(finding.ok is False for finding in findings)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    args = ap.parse_args()
    all_ok = [check_one(path) for path in args.paths]  # every path, not stopping at the first failure
    sys.exit(0 if all(all_ok) else 1)


if __name__ == "__main__":
    main()
