"""The crash replay (issue 27, docs/crash-replay.md): continue each saved trial whose code crashed with
one more message, the saved build error for each part that failed, then grade the design that comes back.

Only the error text saved in the trial's grades.json goes to the model. A build this replay runs is graded
but its error is never sent back, so the replay is one retry, not a loop. The design is graded with the
normal checks, its test prints kept in. The saved trial and its verdict stay as they are.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

from pbe.runner import agent, coupon_loop, llm
from pbe.runner.trial_record import CheckResult, Measurement, ModelCall, Saved, TrialRecord

FILE_NAME = "replay.json"  # not grades.json, so tools that read every trial record skip these
BUILDS = "builds"

# Every saved trial that failed `builds` from a real crash in its code, from results/runs. Left out:
# GPT-6.1 Sol's all-given plate, whose code stops itself on purpose (ValueError: STOP), so it isn't a bug.
CRASHED_TRIALS = (
    "pilot-nut-knob-2/nut-knob/M3/can_ask/deepseek__deepseek-v4-pro-0813/t1",
    "pilot-nut-knob-2/nut-knob/M3/can_ask/qwen__qwen3.8-flash/t1",
    "pilot-nut-knob-2/nut-knob/M5/can_ask/deepseek__deepseek-v4-pro-0813/t1",
    "pilot-nut-knob/nut-knob/M5/can_ask/qwen__qwen3.8-flash/t1",
    "pilot-tripod-given/tripod-plate/all_given/qwen__qwen3.8-flash/t1",
    "pilot-tripod/tripod-plate/can_ask/qwen__qwen3.8-flash/t2",
    "pilot-tripod/tripod-plate/can_ask/qwen__qwen3.8-flash/t3",
    "pilot-wheel/bearing-wheel/can_ask/deepseek__deepseek-v4-pro-0813/t1",
    "pilot-wheel/bearing-wheel/can_ask/deepseek__deepseek-v4-pro-0813/t2",
    "pilot-wheel/bearing-wheel/can_ask/google__gemini-3.8-flash/t1",
)
DECLINED_ON_PURPOSE = "pilot-tripod-given/tripod-plate/all_given/openai__gpt-6.1-sol/t1"

OPENING = "I tried to build your design, and it didn't build. Here's the error for each part that failed:"
ENDING = "Please fix it and send me the design again with submit_design."

# What a replayed design comes to, for the measures written before the run (docs/crash-replay.md)
Result = Literal["passes every check", "fails another check", "not graded", "still crashes", "no design"]


@dataclass
class BuildError:
    """One part that failed `builds` in the saved trial, with the error saved for it."""
    part: str
    error: str


def saved_build_errors(record: TrialRecord) -> list[BuildError]:
    return [BuildError(part=result.part, error=result.detail) for result in record.findings
            if result.check == BUILDS and result.ok is False]


def retry_text(errors: list[BuildError]) -> str:
    """The one message the model gets: each failed part's saved error, and the request to fix it. No verdict."""
    lines = [f"- {error.part}: {error.error}" for error in errors]
    return "\n".join([OPENING, *lines, "", ENDING])


def builds_now(findings: list[CheckResult]) -> bool:
    """Every part built. No findings means no design was graded."""
    build_results = [result for result in findings if result.check == BUILDS]
    return bool(build_results) and all(result.ok is True for result in build_results)


def result_of(findings: list[CheckResult]) -> Result:
    """A design that fails any check fails, even if another isn't graded; not graded only if nothing fails."""
    if not findings:
        return "no design"
    if not builds_now(findings):
        return "still crashes"
    if any(result.ok is False for result in findings):
        return "fails another check"
    if any(result.ok is None for result in findings):
        return "not graded"
    return "passes every check"


class ReplayRecord(Saved):
    """One replayed trial, saved as replay.json beside the retry's transcript and submission."""
    task: str
    model: str
    condition: str
    replayed: str  # the saved trial's folder, under results/runs
    saved_verdict: str  # the saved trial's failing checks, as it was graded; it isn't changed
    message: str  # what the model was sent
    outcome: Literal["submitted", "no_submission", "token_limit", "error"]
    error: str | None = None
    turns: int = 0
    repairs: int = 0
    measures: list[Measurement] = []
    cost_usd: float = 0.0
    elapsed_s: float = 0.0
    calls: list[ModelCall] = []
    findings: list[CheckResult] = []
    all_pass: bool = False
    date: str = ""
    commit: str = ""
    platform: str | None = None

    @classmethod
    def load(cls, folder: Path) -> Self:
        return cls.model_validate_json((folder / FILE_NAME).read_text())

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / FILE_NAME).write_text(self.model_dump_json(indent=1))

    def set_verdict(self, findings) -> None:
        self.findings = [CheckResult.from_finding(finding) for finding in findings]
        self.all_pass = coupon_loop.passed(findings)

    @property
    def result(self) -> Result:
        return result_of(self.findings)

    @property
    def is_infrastructure_stop(self) -> bool:
        """A provider error or no credit: not a result, so the trial runs again."""
        return self.outcome == "error"

    @property
    def stopped_while_grading(self) -> bool:
        """Saved after its paid turn but before grading finished: a rerun grades the saved design, with no model call."""
        return self.outcome == "submitted" and not self.findings

    @property
    def failed_checks(self) -> list[str]:
        return [result.check for result in self.findings if result.ok is False]

    @property
    def not_graded_checks(self) -> list[str]:
        return [result.check for result in self.findings if result.ok is None]


def saved_verdict(record: TrialRecord) -> str:
    return "fail " + " ".join(dict.fromkeys(record.failed_checks))


@dataclass
class Retry:
    """A replayed trial before it's stamped: its record, and the conversation and design to save beside it."""
    record: ReplayRecord
    messages: list[dict]  # only the ones the retry added
    submission: object  # a Submission, or None


def ask(task, saved: TrialRecord, saved_messages: list[dict], replayed: str, already_paid=0.0, chat=llm.chat) -> Retry:
    """Send the saved build errors as one more turn. `already_paid`: what an earlier attempt that stopped on an
    infrastructure error was charged, which still counts."""
    text = retry_text(saved_build_errors(saved))
    turn = coupon_loop.second_turn(task, saved.model, saved_messages, text, chat=chat)
    record = ReplayRecord(
        task=saved.task, model=saved.model, condition=saved.condition, replayed=replayed, saved_verdict=saved_verdict(saved),
        message=text, outcome=turn.outcome, error=turn.error, turns=len(turn.calls), repairs=turn.repairs,
        measures=turn.measures, cost_usd=round(sum(call.cost_usd for call in turn.calls) + already_paid, 6),
        elapsed_s=turn.elapsed_s, calls=turn.calls)
    return Retry(record=record, messages=turn.messages, submission=turn.submission)


def grade(task, record: ReplayRecord, sub, out_dir: Path) -> None:
    """Every check, test prints in."""
    record.set_verdict(agent.grade(task, sub, out_dir))


def replay(task, saved: TrialRecord, saved_messages: list[dict], replayed: str, out_dir: Path, chat=llm.chat) -> Retry:
    """Ask, then grade what comes back."""
    retry = ask(task, saved, saved_messages, replayed, chat=chat)
    if retry.submission is not None:
        grade(task, retry.record, retry.submission, out_dir)
    return retry
