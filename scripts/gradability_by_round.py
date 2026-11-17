"""How many saved trials could be graded before and after a round of test prints. No model calls.

A trial is graded when it has a pass or a fail; "not graded" means no recorded print decides it. Declined trials,
trials with no submission and errors are left out of the share. The trials are the ones saved at BEFORE, read again
at each later commit, so a share can only move because the verdicts moved, not because trials were added.

    uv run python scripts/gradability_by_round.py ddb67f17 a91400d7

The README's figures: ddb67f17 is the last commit before round 3 of test prints (2026-11-08), and a91400d7 is the
regrade after it (2026-11-12). Counting follows scripts/results_table.py (every results/runs/<run>/**/grades.json
except the smoke runs) and pbe/runner/trial_record.py (the verdict).
"""
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE_RUNS = ("cloud-smoke", "cloud-smoke-2")


@dataclass(frozen=True)
class Trial:
    path: str
    task: str
    verdict: str


@dataclass(frozen=True)
class Share:
    graded: int
    not_graded: int

    @property
    def percent(self) -> float:
        return 100 * self.graded / (self.graded + self.not_graded)


def git(*args: str, stdin: bytes | None = None) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True, input=stdin).stdout


def verdict(grades: dict) -> str:
    if grades.get("outcome") != "submitted":
        return grades.get("outcome", "error")
    if grades.get("declined"):
        return "declined"
    if grades.get("all_pass"):
        return "pass"
    counted = [finding for finding in grades.get("findings", []) if not finding.get("test_print")]
    return "fail" if any(finding["ok"] is False for finding in counted) else "not graded"


def grades_paths(commit: str) -> list[str]:
    listed = git("ls-tree", "-r", "--name-only", commit, "results/runs").decode().splitlines()
    return [path for path in listed if path.endswith("/grades.json") and path.split("/")[2] not in SMOKE_RUNS]


def trials_at(commit: str) -> dict[str, Trial]:
    paths = grades_paths(commit)
    batch = git("cat-file", "--batch", stdin="".join(f"{commit}:{path}\n" for path in paths).encode())
    trials, offset = {}, 0
    for path in paths:
        header_end = batch.index(b"\n", offset)
        size = int(batch[offset:header_end].split()[2])
        grades = json.loads(batch[header_end + 1:header_end + 1 + size])
        trials[path] = Trial(path, grades["task"], verdict(grades))
        offset = header_end + 1 + size + 1
    return trials


def share(verdicts: list[str]) -> Share:
    counts = Counter(verdicts)
    return Share(graded=counts["pass"] + counts["fail"], not_graded=counts["not graded"])


def report(before: str, later: list[str]) -> None:
    base = trials_at(before)
    for commit in [before, *later]:
        now = base if commit == before else trials_at(commit)
        same = [now[path] for path in base if path in now]
        overall = share([trial.verdict for trial in same])
        left_out = len(same) - overall.graded - overall.not_graded
        print(f"{commit}: {overall.percent:.1f}% graded, of the {overall.graded + overall.not_graded} trials that "
              f"handed in a design ({overall.graded} pass or fail, {overall.not_graded} not graded; "
              f"{left_out} of the {len(base)} saved trials declined or handed in nothing and are left out)")
        for task in sorted({trial.task for trial in same}):
            by_task = share([trial.verdict for trial in same if trial.task == task])
            if by_task.graded + by_task.not_graded:
                print(f"    {task:15s} {by_task.percent:5.1f}%")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("usage: gradability_by_round.py BEFORE LATER [LATER...]")
    report(sys.argv[1], sys.argv[2:])
