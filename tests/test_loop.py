"""The coupon loop: the report comes only from recorded prints, and a design is graded without coupon credit."""
import json
from pathlib import Path

from pbe.parts import submission
from pbe.parts.build import build_parts
from pbe.runner import coupon_loop, tasks

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs"
SONNET_M3 = RUNS / "pilot-nut-knob-2/nut-knob/M3/can_ask/anthropic__claude-sonnet-5.5/t1"
DEEPSEEK_M3 = RUNS / "pilot-nut-knob-2/nut-knob/M3/can_ask/deepseek__deepseek-v4.1-flash/t1"
GLM_WHEEL = RUNS / "pilot-wheel/bearing-wheel/can_ask/z-ai__glm-5.3-flash/t1"
DEEPSEEK_WHEEL = RUNS / "pilot-wheel/bearing-wheel/can_ask/deepseek__deepseek-v4.1-flash/t2"


def report_for(trial, tmp_path):
    task = tasks.load(json.loads((trial / "grades.json").read_text())["task"])
    sub = submission.load(trial / "submission.yaml")
    coupons_only = sub.model_copy(update={"parts": [part for part in sub.parts if part.role == "coupon"]})
    return coupon_loop.coupon_report(task, sub, build_parts(coupons_only, tmp_path))


def texts(lines):
    return [line.text for line in lines]


def test_a_printed_size_gets_dans_own_words(tmp_path):
    report = report_for(SONNET_M3, tmp_path)
    assert texts(report["nut-coupon"]) == ["5.50 mm pocket: does not go in."]
    assert report["nut-coupon"][0].basis == "coupon B record"


def test_a_pocket_tighter_than_one_that_wont_go_in_wont_either(tmp_path):
    lines = report_for(DEEPSEEK_M3, tmp_path)["coupon"]
    assert texts(lines) == ["5.30 mm pocket: won't go in.", "5.40 mm pocket: won't go in.",
                            "5.50 mm pocket: does not go in.", "5.60 mm pocket: really struggles to go in."]
    assert [line.basis for line in lines] == ["tighter than a record", "tighter than a record", "coupon B record", "coupon B record"]


def test_a_seat_between_printed_sizes_gets_no_answer_and_a_tighter_one_wont_go_in(tmp_path):
    lines = report_for(DEEPSEEK_WHEEL, tmp_path)["coupon"]
    assert texts(lines) == ["21.59 mm seat: won't go in.", "21.74 mm seat: won't go in.", "21.89 mm seat: won't go in.",
                            "22.04 mm seat: I can't tell you how that one came out.", "22.19 mm seat: goes in; holds upside down."]


def test_a_holed_roof_gets_the_bridge_checks_prediction(tmp_path):
    lines = report_for(GLM_WHEEL, tmp_path)["coupon_bearing_fit"]
    assert texts(lines) == ["21.99 mm seat: won't go in.",
                            f"the roof over the pocket: {coupon_loop.ROOF_NOTE}."]
    assert [line.basis for line in lines] == ["coupon E record", "bridge check prediction"]


def test_the_neutral_turn_differs_only_in_the_report():
    feedback = coupon_loop.feedback_text({"c": [coupon_loop.ReportLine("5.50 mm pocket: does not go in.", "coupon B record")]})
    assert feedback.endswith(coupon_loop.ENDING) and coupon_loop.NEUTRAL.endswith(coupon_loop.ENDING)
    assert "does not go in" not in coupon_loop.NEUTRAL


def test_the_second_turn_continues_the_conversation_and_takes_a_submission():
    task = tasks.load("m5-spacer")
    sub = submission.load(RUNS / "pilot-spacer/m5-spacer/can_ask/anthropic__claude-haiku-5.5/t1/submission.yaml")
    arguments = json.dumps({key: value for key, value in sub.model_dump().items() if key != "task"})
    sent = []

    def chat(model, messages, tools=None, max_tokens=None):
        sent.append(messages[-1])
        call = {"id": "1", "type": "function", "function": {"name": "submit_design", "arguments": arguments}}
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [call]}}], "usage": {"cost": 0.01}}
    turn = coupon_loop.second_turn(task, "fake", [{"role": "user", "content": "hi"}], coupon_loop.NEUTRAL, chat=chat)
    assert sent[0]["content"] == coupon_loop.NEUTRAL
    assert turn.outcome == "submitted" and turn.submission is not None
    assert sum(call.cost_usd for call in turn.calls) == 0.01


def test_grading_after_the_coupon_is_printed_leaves_the_coupon_out():
    sub = submission.load(SONNET_M3 / "submission.yaml")
    assert [part.role for part in coupon_loop.without_coupons(sub).parts] == ["final"]


def test_no_design_after_every_call_hit_the_token_limit_is_its_own_outcome():
    def chat(model, messages, tools=None, max_tokens=None):
        return {"choices": [{"message": {"role": "assistant", "content": None}, "finish_reason": "length"}]}
    turn = coupon_loop.second_turn(tasks.load("m5-spacer"), "fake", [], coupon_loop.NEUTRAL, chat=chat)
    assert turn.outcome == "token_limit"
    assert len(turn.calls) == coupon_loop.SECOND_TURN_CALLS


def test_no_design_for_any_other_reason_is_no_submission():
    def chat(model, messages, tools=None, max_tokens=None):
        return {"choices": [{"message": {"role": "assistant", "content": "I'd rather not."}, "finish_reason": "stop"}]}
    turn = coupon_loop.second_turn(tasks.load("m5-spacer"), "fake", [], coupon_loop.NEUTRAL, chat=chat)
    assert turn.outcome == "no_submission"


# ---- scripts/coupon_loop.py: resuming a stopped sample ----
import importlib.util

from pbe.runner.trial_record import ModelCall


def run_script():
    spec = importlib.util.spec_from_file_location("coupon_loop_script", ROOT / "scripts/coupon_loop.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_turn(sub, cost):
    def second_turn(task, model, messages, text, **kwargs):
        call = ModelCall(model="fake", provider=None, finish_reason="tool_calls", usage={"cost": cost}, elapsed_s=0.1)
        return coupon_loop.SecondTurn(outcome="submitted", error=None, messages=[{"role": "user", "content": text}],
                                      submission=sub, calls=[call], repairs=0, measures=[], elapsed_s=0.1)
    return second_turn


def spacer():
    return submission.load(RUNS / "pilot-spacer/m5-spacer/can_ask/anthropic__claude-haiku-5.5/t1/submission.yaml")


def test_a_retry_after_an_error_keeps_what_the_failed_attempt_cost(tmp_path, monkeypatch):
    script = run_script()
    failed = coupon_loop.LoopRecord(task="m5-spacer", model="fake", arm="neutral", replayed="x", outcome="error", cost_usd=0.25)
    failed.save(tmp_path)
    assert not script.is_settled(tmp_path)
    monkeypatch.setattr(script.coupon_loop, "second_turn", fake_turn(spacer(), 0.10))
    saved = type("Saved", (), {"task": "m5-spacer", "model": "fake", "condition": "can_ask", "hidden": []})()
    script.run_arm(tasks.load("m5-spacer"), saved, "neutral", coupon_loop.NEUTRAL, {}, [], tmp_path, "x", coupon_loop.SECOND_TURN_CALLS)
    record = coupon_loop.LoopRecord.load(tmp_path)
    assert record.cost_usd == 0.35 and record.findings and script.is_settled(tmp_path)


def test_an_arm_stopped_while_grading_is_finished_without_a_new_model_call(tmp_path):
    script = run_script()
    (tmp_path / "submission.yaml").write_text((RUNS / "pilot-spacer/m5-spacer/can_ask/anthropic__claude-haiku-5.5/t1/submission.yaml").read_text())
    paid = coupon_loop.LoopRecord(task="m5-spacer", model="fake", arm="feedback", replayed="x", outcome="submitted", cost_usd=0.10)
    paid.save(tmp_path)
    assert not script.is_settled(tmp_path) and script.stopped_while_grading(paid)
    script.finish_grading(tasks.load("m5-spacer"), tmp_path)
    record = coupon_loop.LoopRecord.load(tmp_path)
    assert record.findings and record.cost_usd == 0.10 and script.is_settled(tmp_path)


# --- the tripod sample: printing the final plate ---

OPUS_PLATE = RUNS / "pilot-tripod/tripod-plate/can_ask/anthropic__claude-opus-5.5/t2"
HAIKU_PLATE = RUNS / "pilot-tripod/tripod-plate/can_ask/anthropic__claude-haiku-5.5/t1"
ARGON_PASS = RUNS / "pilot-tripod/tripod-plate/can_ask/google__gemini-4-argon/t1"


def plate_report_for(trial, tmp_path):
    sub = submission.load(trial / "submission.yaml")
    return coupon_loop.plate_report(tasks.load("tripod-plate"), sub, build_parts(sub, tmp_path))


def test_a_printed_plate_reports_the_clamp_the_head_and_a_holed_roof(tmp_path):
    (lines,) = plate_report_for(OPUS_PLATE, tmp_path).values()
    assert texts(lines) == ["the clamp: it fits.", "the bolt's head: it fits in its recess.",
                            f"the roof the hole goes through: {coupon_loop.ROOF_NOTE}."]
    assert [line.basis for line in lines] == ["tripod plate record", "tripod plate record", "bridge check prediction"]


def test_a_plate_that_prints_cleanly_says_nothing_about_its_roof(tmp_path):
    (lines,) = plate_report_for(ARGON_PASS, tmp_path).values()
    assert not any("roof" in text for text in texts(lines))


def test_only_the_printed_width_is_said_to_fit_the_clamp():
    def r2(ok, detail):
        return [type("F", (), {"check": "R2", "ok": ok, "detail": detail})()]
    assert coupon_loop.clamp_line(r2(True, "38.0 mm wide, narrowing by 1.0 mm on both edges")).text == "the clamp: it fits."
    assert coupon_loop.clamp_line(r2(True, "38.40 mm wide, narrowing by 1.0 mm on both edges")).text == "the clamp: it fits."
    # 37 to 39 passes R2 on an estimate of the jaws' travel; only 38 was printed
    assert coupon_loop.clamp_line(r2(True, "37.00 mm wide, narrowing by 1.0 mm on both edges")).basis == "no record"
    assert coupon_loop.clamp_line(r2(False, "straight sides: it narrows by only 0.00 mm")).basis == "no record"


def test_the_head_line_follows_the_two_printed_recesses():
    def r4(ok):
        return [type("F", (), {"check": "R4", "ok": ok, "detail": ""})()]
    assert coupon_loop.head_line(r4(True)).text == "the bolt's head: it fits in its recess."
    assert coupon_loop.head_line(r4(False)).text == "the bolt's head: it didn't fit in its recess."
    assert coupon_loop.head_line(r4(None)).basis == "no record"


def test_the_printed_reply_names_no_cause_or_fix(tmp_path):
    text = coupon_loop.printed_text(plate_report_for(HAIKU_PLATE, tmp_path))
    for word in ("stepped", "sacrificial", "bridge", "support", "flip", "layer"):
        assert word not in text.lower()


def test_a_can_run_code_trial_keeps_run_python_in_its_second_turn():
    offered = []

    def chat(model, messages, tools=None, max_tokens=None):
        offered.append({tool["function"]["name"] for tool in tools})
        return {"choices": [{"message": {"role": "assistant", "content": "ok"}}], "usage": {"cost": 0.0}}
    coupon_loop.second_turn(tasks.load("tripod-plate"), "fake", [], coupon_loop.NEUTRAL, max_turns=1, chat=chat, condition="can_run_code")
    coupon_loop.second_turn(tasks.load("tripod-plate"), "fake", [], coupon_loop.NEUTRAL, max_turns=1, chat=chat)
    assert "run_python" in offered[0] and "run_python" not in offered[1]


def test_a_replay_answers_with_the_facts_its_first_turn_had():
    """The clamp's width was added on 2026-11-06; a tripod trial saved before then must not hear it in a replay."""
    from pbe.runner.measure import Person
    from pbe.runner.trial_record import TrialRecord
    task = tasks.load("tripod-plate")
    saved = TrialRecord.load(RUNS / "pilot-tripod/tripod-plate/can_ask/anthropic__claude-opus-5.5/t2")
    then = Person(coupon_loop.facts_as_saved(task, saved.hidden))
    assert "38 mm" not in then.measure("tripod clamp", "how wide a plate does it take")
    assert "angled lips" in then.measure("tripod clamp", "what kind is it")
    assert "about 15" in then.measure("webcam bolt", "head diameter")
    assert "38 mm" in Person(task.hidden_facts).measure("tripod clamp", "how wide a plate does it take")
