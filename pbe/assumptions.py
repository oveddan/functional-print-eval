"""Grade the checks the records leave undecided again, under each requirement's stated assumption. No model calls.

    uv run python -m pbe.assumptions --run pilot-estoa

A requirement's `assume` block (requirements.yaml) names one assumption: a sentence, its source, and the grader
arguments it changes. Only a check the records left not graded is graded again, and the verdict the records give
never changes: the result goes to assumed.json beside each trial's grades.json, so a reader can always tell a
verdict that rests on an assumption from one that rests on a print.
"""
import argparse
import json
import tempfile
from pathlib import Path

from pydantic import BaseModel

from pbe.graders import requirements
from pbe.parts import submission
from pbe.parts.build import build_parts
from pbe.runner import tasks
from pbe.runner.trial_record import TrialRecord

ROOT = Path(__file__).resolve().parents[1]
FILE_NAME = "assumed.json"


class AssumedFinding(BaseModel):
    check: str
    ok: bool | None  # still None if the assumption doesn't decide it either
    detail: str
    assumption: str


class Assumed(BaseModel):
    """One trial's undecided checks, graded under the task's assumptions, and the verdict that follows."""
    findings: list[AssumedFinding]
    verdict: str  # pass, fail or not graded, counting the records' verdicts and these together

    @classmethod
    def load_if_saved(cls, folder: Path) -> "Assumed | None":
        path = folder / FILE_NAME
        return cls.model_validate_json(path.read_text()) if path.exists() else None


def with_assumption(requirement: tasks.Requirement) -> tasks.Requirement:
    return requirement.model_copy(update={"args": (requirement.args or {}) | requirement.assume.args})


def verdict(record: TrialRecord, assumed: list[AssumedFinding]) -> str:
    """The records' verdicts, with each undecided check replaced by its assumed one where there is one."""
    under = {finding.check: finding.ok for finding in assumed}
    oks = [under.get(finding.check, finding.ok) if finding.ok is None else finding.ok for finding in record.counted_findings]
    if all(ok is True for ok in oks):
        return "pass"
    return "fail" if any(ok is False for ok in oks) else "not graded"


def assume(task: tasks.Task, record: TrialRecord, folder: Path) -> Assumed | None:
    """None when the task assumes nothing, or the trial has no graded design to read."""
    undecided = {finding.check for finding in record.counted_findings if finding.ok is None}
    chosen = [requirement for requirement in task.requirements if requirement.assume and requirement.id in undecided]
    if record.outcome != "submitted" or record.declined or not any(requirement.assume for requirement in task.requirements):
        return None
    findings = []
    if chosen:
        sub = submission.load(folder / "submission.yaml")
        with tempfile.TemporaryDirectory() as parts:
            built = build_parts(sub, Path(parts))
            for requirement in chosen:
                ok, detail = requirements._run_grader(with_assumption(requirement), sub, built)
                findings.append(AssumedFinding(check=requirement.id, ok=None if ok is None else bool(ok),
                                               detail=f"Under the assumption: {detail}",
                                               assumption=requirement.assume.text))
    return Assumed(findings=findings, verdict=verdict(record, findings))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="a saved run under results/runs/")
    args = parser.parse_args()
    for folder, record in TrialRecord.all_in(ROOT / "results/runs" / args.run):
        assumed = assume(tasks.load(record.task), record, folder)
        if assumed is None:
            continue
        (folder / FILE_NAME).write_text(json.dumps(assumed.model_dump(), indent=1) + "\n")
        changed = ", ".join(f"{finding.check} {'pass' if finding.ok else 'fail' if finding.ok is False else 'not graded'}"
                            for finding in assumed.findings) or "nothing undecided it covers"
        print(f"{record.task} {record.model} t{record.trial}: {record.verdict} -> {assumed.verdict} ({changed})")


if __name__ == "__main__":
    main()
