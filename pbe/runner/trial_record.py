"""What a trial saves in grades.json, typed, so code reads record.cost_usd and not r["cost_usd"].

A field that's missing, misspelled or of the wrong type stops at load, where it can't quietly
change a result.
"""
import json
from pathlib import Path
from typing import Iterator, Literal, Self

from pydantic import BaseModel, ConfigDict

FILE_NAME = "grades.json"
# What a trial came to. "declined" is neither a pass nor a fail, and never counts as a pass (issue 15).
# A trial that didn't submit keeps its outcome.
Verdict = Literal["pass", "fail", "not graded", "declined", "no_submission", "error"]


class Saved(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CheckResult(Saved):
    check: str
    part: str
    ok: bool | None  # None: not graded, which is never a pass
    detail: str
    test_print: bool = False  # reported, but doesn't count toward the verdict; older records have none

    @classmethod
    def from_finding(cls, finding) -> Self:
        return cls(check=finding.check, part=finding.part, ok=finding.ok, detail=finding.detail, test_print=finding.test_print)

    def as_saved(self) -> dict:
        """Its fields, with test_print only where it's true, so a record saved before it existed reads back unchanged."""
        fields = self.model_dump()
        if not self.test_print:
            del fields["test_print"]
        return fields


class Measurement(Saved):
    """One thing the model asked the person to measure, and the reply."""
    item: str
    what: str
    revealed: list[str]
    reply: str


class ModelCall(Saved):
    """One request to the model. The provider may leave any of these out."""
    model: str | None
    provider: str | None
    finish_reason: str | None
    usage: dict | None  # its keys differ by provider
    elapsed_s: float | None

    @classmethod
    def from_reply(cls, reply) -> Self:
        return cls(model=reply.model, provider=reply.provider, finish_reason=reply.finish_reason,
                   usage=reply.usage, elapsed_s=reply.elapsed_s)

    @property
    def cost_usd(self) -> float:
        """What the call was charged, or 0 if the provider didn't say."""
        return (self.usage or {}).get("cost") or 0


class Settings(Saved):
    max_turns: int
    max_tokens: int
    temperature: str


class EarlierVerdict(Saved):
    """The verdict a regrade replaced, kept so a changed result stays visible."""
    date: str
    commit: str
    platform: str | None = None  # see TrialRecord.platform
    findings: list[CheckResult]
    all_pass: bool
    declined: str | None = None  # see TrialRecord.declined


class TrialRecord(Saved):
    task: str
    model: str
    condition: str
    outcome: Literal["submitted", "no_submission", "error"]
    error: str | None
    turns: int
    repairs: int
    measures: list[Measurement]
    revealed: list[str]
    hidden: list[str]
    limitations: list[dict]  # whatever the model passed to report_limitation
    cost_usd: float
    elapsed_s: float
    settings: Settings
    calls: list[ModelCall]
    trial: int = 0
    date: str = ""
    commit: str = ""
    platform: str | None = None  # geometry comes from each platform's own CAD kernel wheel; older records have none
    findings: list[CheckResult] = []
    observations: dict = {}  # not scored, and different for each task
    all_pass: bool = False
    declined: str | None = None  # why the trial counts as declined (pbe/graders/declined.py); older records have none
    regrades: list[EarlierVerdict] = []

    @classmethod
    def load(cls, folder: Path) -> Self:
        return cls.model_validate_json((folder / FILE_NAME).read_text())

    @classmethod
    def load_if_saved(cls, folder: Path) -> Self | None:
        return cls.load(folder) if (folder / FILE_NAME).exists() else None

    @classmethod
    def all_in(cls, run_dir: Path) -> Iterator[tuple[Path, Self]]:
        """Every trial saved under a run, in path order, each with its folder."""
        for path in sorted(run_dir.rglob(FILE_NAME)):
            yield path.parent, cls.load(path.parent)

    def save(self, folder: Path) -> None:
        (folder / FILE_NAME).write_text(json.dumps(self.as_saved(), indent=1))

    def as_saved(self) -> dict:
        """The fields grades.json keeps. Only a regraded trial has `regrades`, only a declined one
        has `declined`, and a record or an earlier verdict saved before `platform` was recorded
        stays without one."""
        fields = self.model_dump()
        if not self.regrades:
            del fields["regrades"]
        if "platform" not in self.model_fields_set:
            del fields["platform"]
        _drop_unset(fields, self)
        for earlier, saved in zip(self.regrades, fields.get("regrades", [])):
            if "platform" not in earlier.model_fields_set:
                del saved["platform"]
            _drop_unset(saved, earlier)
        return fields

    @property
    def counted_findings(self) -> list[CheckResult]:
        """The findings that decide the verdict: all but the generic checks on test prints. None for a
        declined trial, which is neither a pass nor a fail, so no failure of it counts by check or class."""
        if self.declined:
            return []
        return [finding for finding in self.findings if not finding.test_print]

    @property
    def failed_checks(self) -> list[str]:
        return [finding.check for finding in self.counted_findings if finding.ok is False]

    @property
    def not_graded_checks(self) -> list[str]:
        return [finding.check for finding in self.counted_findings if finding.ok is None]

    @property
    def test_print_failed_checks(self) -> list[str]:
        """Checks that failed on a test print: reported, never counted."""
        return [finding.check for finding in self.findings if finding.test_print and finding.ok is False]

    @property
    def verdict(self) -> Verdict:
        if self.outcome != "submitted":
            return self.outcome
        if self.declined:
            return "declined"
        if self.all_pass:
            return "pass"
        return "fail" if self.failed_checks else "not graded"

    @property
    def stopped_during_grading(self) -> bool:
        return self.outcome == "submitted" and not self.findings

    def set_verdict(self, findings, declined: str | None = None) -> None:
        """Test prints' generic checks are kept but not counted, and a declined trial never passes."""
        self.findings = [CheckResult.from_finding(finding) for finding in findings]
        self.declined = declined
        counted = self.counted_findings
        self.all_pass = not declined and bool(counted) and all(finding.ok is True for finding in counted)

    def keep_verdict_as_earlier(self) -> None:
        self.regrades.append(EarlierVerdict(date=self.date, commit=self.commit, platform=self.platform,
                                            findings=self.findings, all_pass=self.all_pass, declined=self.declined))


def _drop_unset(saved: dict, verdict: TrialRecord | EarlierVerdict) -> None:
    """Leave out `declined` and each finding's `test_print` where they say nothing, as records saved before them did."""
    if verdict.declined is None:
        del saved["declined"]
    saved["findings"] = [finding.as_saved() for finding in verdict.findings]
