"""What a trial saves in grades.json, typed, so code reads record.cost_usd and not r["cost_usd"].

A field that's missing, misspelled or of the wrong type stops at load, where it can't quietly
change a result.
"""
import json
from pathlib import Path
from typing import Iterator, Literal, Self

from pydantic import BaseModel, ConfigDict

FILE_NAME = "grades.json"


class Saved(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CheckResult(Saved):
    check: str
    part: str
    ok: bool | None  # None: not graded, which is never a pass
    detail: str

    @classmethod
    def from_finding(cls, finding) -> Self:
        return cls(check=finding.check, part=finding.part, ok=finding.ok, detail=finding.detail)


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
        """The fields grades.json keeps. Only a regraded trial has `regrades`, and a record or an
        earlier verdict saved before `platform` was recorded stays without one."""
        fields = self.model_dump()
        if not self.regrades:
            del fields["regrades"]
        if "platform" not in self.model_fields_set:
            del fields["platform"]
        for earlier, saved in zip(self.regrades, fields.get("regrades", [])):
            if "platform" not in earlier.model_fields_set:
                del saved["platform"]
        return fields

    @property
    def failed_checks(self) -> list[str]:
        return [finding.check for finding in self.findings if finding.ok is False]

    @property
    def not_graded_checks(self) -> list[str]:
        return [finding.check for finding in self.findings if finding.ok is None]

    @property
    def stopped_during_grading(self) -> bool:
        return self.outcome == "submitted" and not self.findings

    def set_verdict(self, findings) -> None:
        self.findings = [CheckResult.from_finding(finding) for finding in findings]
        self.all_pass = bool(findings) and all(finding.ok is True for finding in findings)

    def keep_verdict_as_earlier(self) -> None:
        self.regrades.append(EarlierVerdict(date=self.date, commit=self.commit, platform=self.platform,
                                            findings=self.findings, all_pass=self.all_pass))
