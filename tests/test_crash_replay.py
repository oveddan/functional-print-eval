"""The crash replay: the model hears only the saved build error, gets one retry, and the result is graded with test prints in."""
import json
from pathlib import Path

from pbe.parts import submission
from pbe.runner import crash_replay, llm, tasks
from pbe.runner.trial_record import CheckResult, TrialRecord

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs"
QWEN_TRIPOD_T2 = "pilot-tripod/tripod-plate/can_ask/qwen__qwen3.8-flash/t2"
DEEPSEEK_M5 = "pilot-nut-knob-2/nut-knob/M5/can_ask/deepseek__deepseek-v4-pro-0813/t1"  # only its test print crashed
DEEPSEEK_WHEEL_T2 = "pilot-wheel/bearing-wheel/can_ask/deepseek__deepseek-v4-pro-0813/t2"


def saved(replayed):
    return TrialRecord.load(RUNS / replayed)


def saved_messages(replayed):
    return json.loads((RUNS / replayed / "transcript.json").read_text())


def scripted_chat(sub, sent):
    """A fake model that hands in `sub` on its first call, and records every request it gets."""
    arguments = json.dumps({key: value for key, value in sub.model_dump().items() if key != "task"})

    def chat(model, messages, tools=None, max_tokens=None):
        sent.append(messages)
        call = {"id": "1", "type": "function", "function": {"name": "submit_design", "arguments": arguments}}
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [call]}, "finish_reason": "tool_calls"}],
                "usage": {"cost": 0.02}}
    return chat


def with_import_math(sub, part_id):
    parts = [part.model_copy(update={"code": "import math\n" + part.code}) if part.id == part_id else part for part in sub.parts]
    return sub.model_copy(update={"parts": parts})


def test_the_trials_are_every_saved_crash_but_the_one_that_stops_itself():
    """Every crash saved when the replay ran (issue 27). Trials saved since issue 34 record
    settings.prompt_caching, and aren't part of it."""
    crashed = {str(folder.relative_to(RUNS)) for folder, record in TrialRecord.all_in(RUNS)
               if crash_replay.saved_build_errors(record) and record.settings.prompt_caching is None}
    assert crashed == {*crash_replay.CRASHED_TRIALS, crash_replay.DECLINED_ON_PURPOSE}
    assert len(crash_replay.CRASHED_TRIALS) == 10


def test_the_message_is_each_failed_parts_saved_error_and_nothing_else():
    text = crash_replay.retry_text(crash_replay.saved_build_errors(saved(QWEN_TRIPOD_T2)))
    assert text == "\n".join([
        crash_replay.OPENING,
        "- qr_plate: AttributeError: 'tuple' object has no attribute 'getAngle'",
        "- thumb_screw: AttributeError: 'Workplane' object has no attribute 'cone'. Did you mean: 'close'?",
        "- jaw_gauge: AttributeError: 'tuple' object has no attribute 'getAngle'",
        "",
        crash_replay.ENDING,
    ])


def test_a_fixed_test_print_builds_and_is_graded_with_test_prints_in(tmp_path):
    record = saved(DEEPSEEK_M5)
    fixed = with_import_math(submission.load(RUNS / DEEPSEEK_M5 / "submission.yaml"), "nut_fit_coupon")
    sent = []
    retry = crash_replay.replay(tasks.load(record.task), record, saved_messages(DEEPSEEK_M5), DEEPSEEK_M5, tmp_path,
                                chat=scripted_chat(fixed, sent))
    assert len(sent) == 1
    assert sent[0][:-1] == saved_messages(DEEPSEEK_M5)  # the saved conversation, continued
    assert sent[0][-1] == {"role": "user", "content": retry.record.message}
    assert "nut_fit_coupon: NameError: name 'math' is not defined" in retry.record.message
    assert retry.record.outcome == "submitted" and retry.record.cost_usd == 0.02
    assert "nut_fit_coupon" in {result.part for result in retry.record.findings if result.check == "builds"}
    assert crash_replay.builds_now(retry.record.findings)
    assert retry.record.result != "still crashes"


def test_a_design_that_crashes_again_is_graded_but_its_new_error_isnt_sent(tmp_path):
    record = saved(DEEPSEEK_WHEEL_T2)
    unchanged = submission.load(RUNS / DEEPSEEK_WHEEL_T2 / "submission.yaml")
    sent = []
    retry = crash_replay.replay(tasks.load(record.task), record, saved_messages(DEEPSEEK_WHEEL_T2), DEEPSEEK_WHEEL_T2, tmp_path,
                                chat=scripted_chat(unchanged, sent))
    assert len(sent) == 1
    assert [message["role"] for message in retry.messages] == ["user", "assistant", "tool"]
    assert retry.messages[-1]["content"] == "Received."
    assert retry.record.result == "still crashes"
    assert retry.record.saved_verdict.startswith("fail builds")


def test_an_infrastructure_error_is_not_a_result(tmp_path):
    record = saved(DEEPSEEK_WHEEL_T2)

    def chat(model, messages, tools=None, max_tokens=None):
        raise llm.LLMError("HTTP 402 from fake: requires more credits")
    retry = crash_replay.replay(tasks.load(record.task), record, saved_messages(DEEPSEEK_WHEEL_T2), DEEPSEEK_WHEEL_T2, tmp_path, chat=chat)
    assert retry.record.outcome == "error" and retry.record.is_infrastructure_stop
    assert retry.record.result == "no design" and retry.submission is None


def test_the_record_round_trips(tmp_path):
    record = crash_replay.ReplayRecord(task="m5-spacer", model="fake", condition="can_ask", replayed="x", saved_verdict="fail builds",
                                       message="m", outcome="no_submission")
    record.save(tmp_path)
    assert crash_replay.ReplayRecord.load(tmp_path) == record


def result(check, ok):
    return CheckResult(check=check, part="p", ok=ok, detail="")


def test_a_design_is_sorted_by_the_measures_written_before_the_run():
    assert crash_replay.result_of([]) == "no design"
    assert crash_replay.result_of([result("builds", True), result("builds", False)]) == "still crashes"
    assert crash_replay.result_of([result("builds", True), result("bridges", False), result("R4", None)]) == "fails another check"
    assert crash_replay.result_of([result("builds", True), result("R4", None)]) == "not graded"
    assert crash_replay.result_of([result("builds", True), result("bridges", True)]) == "passes every check"


# ---- scripts/crash_replay.py: resuming a stopped run ----
import importlib.util  # noqa: E402

import pytest  # noqa: E402


def run_script():
    spec = importlib.util.spec_from_file_location("crash_replay_script", ROOT / "scripts/crash_replay.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unchanged_chat(replayed, sent):
    return scripted_chat(submission.load(RUNS / replayed / "submission.yaml"), sent)


def test_a_retry_after_an_infrastructure_error_keeps_what_the_failed_attempt_cost(tmp_path):
    script = run_script()
    failed = crash_replay.ReplayRecord(task="bearing-wheel", model="fake", condition="can_ask", replayed=DEEPSEEK_WHEEL_T2,
                                       saved_verdict="fail builds", message="m", outcome="error", cost_usd=0.25)
    failed.save(tmp_path / DEEPSEEK_WHEEL_T2)
    assert not script.is_settled(tmp_path / DEEPSEEK_WHEEL_T2)
    record = script.run_one(DEEPSEEK_WHEEL_T2, tmp_path, chat=unchanged_chat(DEEPSEEK_WHEEL_T2, []))
    assert record.cost_usd == 0.27 and record.findings and script.is_settled(tmp_path / DEEPSEEK_WHEEL_T2)


def test_the_paid_retry_is_saved_before_grading_and_a_rerun_grades_it_without_a_model_call(tmp_path, monkeypatch):
    script = run_script()
    folder = tmp_path / DEEPSEEK_WHEEL_T2

    def grading_breaks(*args):
        raise RuntimeError("no working sandbox")
    monkeypatch.setattr(script.crash_replay, "grade", grading_breaks)
    with pytest.raises(RuntimeError):
        script.run_one(DEEPSEEK_WHEEL_T2, tmp_path, chat=unchanged_chat(DEEPSEEK_WHEEL_T2, []))
    paid = script.stopped_while_grading(folder)
    assert paid is not None and paid.cost_usd == 0.02 and (folder / "submission.yaml").exists()
    assert not script.is_settled(folder)

    monkeypatch.undo()
    record = script.finish_grading(tasks.load(paid.task), folder)
    assert record.findings and record.cost_usd == 0.02 and script.is_settled(folder)
