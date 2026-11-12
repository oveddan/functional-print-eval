"""The runner's own faults: model code stays contained, and nothing a model or the network
does stops a run or loses a paid trial."""
import http.client
import json
import shutil
import urllib.request

import pytest
from pydantic import ValidationError

from pbe import eval as runner
from pbe.graders import checks
from pbe.parts import build, submission
from pbe.parts.build import build_parts
from pbe.runner import agent, llm, tasks
from pbe.runner.trial_record import TrialRecord

from helpers import a_record


def one_part(code, part_id="p"):
    part = submission.Part(id=part_id, role="final", material="PLA", code=code, print_orientation="flat", use_orientation="flat")
    return submission.Submission(task="t", params={}, parts=[part])


def code_that(line):
    """Part code that runs `line`, then builds a block, so the build fails only if `line` does."""
    return f'import os, socket, subprocess\n\ndef build(p):\n    {line}\n    return cq.Workplane("XY").box(5, 5, 5)\n'


def test_part_code_cannot_see_the_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-key")
    built = build_parts(one_part(code_that('assert "OPENROUTER_API_KEY" not in os.environ')), tmp_path)
    assert built["p"].ok, built["p"].error


def test_with_no_key_and_no_1password_cli_the_error_says_how_to_get_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))  # no `op` to run
    llm._key.cache_clear()
    with pytest.raises(llm.LLMError, match="export OPENROUTER_API_KEY=") as error:
        llm._key()
    llm._key.cache_clear()
    assert "openrouter.ai" in str(error.value) and "isn't installed" in str(error.value)


@pytest.mark.skipif(not build.sandbox(), reason="no sandbox here")
@pytest.mark.parametrize("line", [
    'socket.create_connection(("1.1.1.1", 443), timeout=3)',
    'subprocess.run(["true"])',
], ids=["network", "child-process"])
def test_part_code_cannot_reach_out_of_the_sandbox(tmp_path, line):
    built = build_parts(one_part(code_that(line)), tmp_path)
    assert not built["p"].ok and "not permitted" in built["p"].error


@pytest.mark.skipif(not build.sandbox(), reason="no sandbox here")
def test_part_code_can_write_only_to_its_own_folders(tmp_path):
    elsewhere = tmp_path / "elsewhere.txt"  # a folder that exists, next to the parts folder
    built = build_parts(one_part(code_that(f'open({str(elsewhere)!r}, "w")')), tmp_path / "parts")
    assert not built["p"].ok and not elsewhere.exists()


def test_ordinary_part_code_still_works_in_the_sandbox(tmp_path):
    # text needs the system's fonts, and a label on a part is ordinary
    built = build_parts(one_part('def build(p):\n    return cq.Workplane("XY").box(30, 30, 5).faces(">Z").workplane().text("M5", 8, -1)\n'), tmp_path)
    assert built["p"].ok, built["p"].error


@pytest.mark.parametrize("part_id", ["../../x", "a b"])
def test_a_part_id_has_to_be_safe_as_a_file_name(part_id):
    with pytest.raises(ValidationError, match="letters, digits"):
        one_part("", part_id=part_id)


@pytest.mark.parametrize("param", [
    {"value": 8, "unit": "count", "kind": "design", "source": "design"},
    {"value": 8.0, "unit": "count", "kind": "design", "source": "design"},  # as a saved submission can have it
    {"value": 8, "kind": "design", "source": "design"},                     # with no unit, an int is still an int
], ids=["count", "count-saved-as-float", "no-unit"])
def test_a_count_param_works_in_range(tmp_path, param):
    # GPT-6 Luna's knob (run pilot-nut-knob): lobe_count 8 reached its code as 8.0, and range()
    # raised TypeError. The eval's fault, not the model's.
    sub = one_part('def build(p):\n    for i in range(p.n):\n        pass\n    return cq.Workplane("XY").box(5, 5, 5)\n')
    sub = submission.Submission.model_validate({**sub.model_dump(), "params": {"n": param}})
    built = build_parts(sub, tmp_path)
    assert built["p"].ok, built["p"].error


def test_a_part_has_to_say_whether_its_a_coupon():
    # DeepSeek V4.1 Flash's coupon (run pilot-nut-knob) left role out. It defaulted to "final",
    # so its design read as two printed parts. A schema error goes back for repair instead.
    sub = one_part("").model_dump()
    del sub["parts"][0]["role"]
    with pytest.raises(ValidationError, match="role"):
        submission.Submission.model_validate(sub)


def test_two_parts_cannot_share_an_id():
    sub = one_part("").model_dump()
    sub["parts"].append(sub["parts"][0])
    with pytest.raises(ValidationError, match="same id"):
        submission.Submission.model_validate(sub)


def tool_call(name, arguments):
    return {"id": "1", "type": "function", "function": {"name": name, "arguments": arguments}}


# every tool once and every kind of JSON that isn't an object once
@pytest.mark.parametrize("name, arguments", [("measure", "null"), ("submit_design", "[1]"), ("report_limitation", "3")])
def test_arguments_that_arent_an_object_go_back_to_the_model(name, arguments):
    def chat(model, messages, tools=None, max_tokens=None):
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [tool_call(name, arguments)]}}]}
    record, messages, sub = agent.run_trial(tasks.load("m5-spacer"), "fake", max_turns=1, chat=chat)
    assert sub is None and record.outcome == "no_submission"
    assert "JSON object" in messages[-1]["content"]
    assert record.repairs == (name == "submit_design")


class Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, *a):
        return self.body


OK = json.dumps({"choices": [{"message": {"role": "assistant", "content": "hi"}}]}).encode()


@pytest.mark.parametrize("fault", [
    ConnectionResetError("dropped"),
    http.client.RemoteDisconnected("dropped"),
    http.client.IncompleteRead(b"{"),
    Response(b'{"cut off'),
], ids=["reset", "disconnected", "incomplete", "bad-json"])
def test_a_broken_response_is_retried_then_an_llm_error(monkeypatch, fault):
    def urlopen(attempts):
        def call(req, timeout=None):
            answer = attempts.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        return call
    monkeypatch.setattr(llm, "_key", lambda: "fake")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen([fault, Response(OK)]))
    assert llm.chat("fake", [], retries=1)["choices"]
    monkeypatch.setattr(urllib.request, "urlopen", urlopen([fault, fault]))
    with pytest.raises(llm.LLMError):
        llm.chat("fake", [], retries=1)


class Args:
    max_turns = 1
    max_tokens = 10




def test_every_saved_trial_reads_back_unchanged():
    saved = sorted((runner.ROOT / "results/runs").rglob("grades.json"))
    assert saved
    for path in saved:
        as_saved = json.loads(path.read_text())
        record = TrialRecord.load(path.parent)
        assert record.as_saved() == as_saved, path


def test_a_record_with_an_unknown_field_doesnt_load(tmp_path):
    a_record().save(tmp_path)
    fields = json.loads((tmp_path / "grades.json").read_text())
    (tmp_path / "grades.json").write_text(json.dumps({**fields, "cost": 1}))
    with pytest.raises(ValidationError):
        TrialRecord.load(tmp_path)


def test_a_record_sorts_its_checks_into_failed_and_not_graded():
    record = a_record()
    record.set_verdict([checks.Finding("a", "-", True, "", ""), checks.Finding("b", "-", False, "", ""), checks.Finding("c", "-", None, "", "")])
    assert record.failed_checks == ["b"] and record.not_graded_checks == ["c"] and record.all_pass is False


def test_a_rerun_counts_what_the_failed_attempt_cost(tmp_path, monkeypatch):
    task = tasks.Task("t", "x", {}, [], None)
    trial = tmp_path / "t" / "can_ask" / "m" / "t1"
    trial.mkdir(parents=True)
    a_record(outcome="error", cost_usd=0.25).save(trial)
    monkeypatch.setattr(agent, "run_trial", lambda *a, **k: (a_record(cost_usd=0.5), [], None))
    assert runner.run_one(task, "m", "can_ask", 1, tmp_path, Args).cost_usd == 0.75
    assert runner.spent(tmp_path) == 0.75


def test_no_sandbox_means_no_model_code_unless_someone_chose_that(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.delenv("PBE_NO_SANDBOX", raising=False)
    with pytest.raises(RuntimeError, match="sandbox"):
        build_parts(one_part(""), tmp_path)
    monkeypatch.setenv("PBE_NO_SANDBOX", "1")
    build.require_sandbox()


def test_a_bubblewrap_the_kernel_refuses_is_no_sandbox(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    monkeypatch.setattr(build, "_bwrap_runs", lambda: False)
    assert build.sandbox() is None
    monkeypatch.setattr(build, "_bwrap_runs", lambda: True)
    assert build.sandbox() == "bwrap"


def test_bubblewrap_cuts_the_network_and_writes_everywhere_but_the_two_folders(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "sandbox", lambda: "bwrap")
    command, env = build._isolated(["python", "runner.py"], tmp_path / "parts", tmp_path / "tmp")
    assert command[:5] == ["bwrap", "--ro-bind", "/", "/", "--dev"] and "--unshare-net" in command
    parts, scratch = str((tmp_path / "parts").resolve()), str((tmp_path / "tmp").resolve())
    assert ["--bind", parts, parts, "--bind", scratch, scratch] == command[-8:-2]
    assert command[-2:] == ["python", "runner.py"] and "OPENROUTER_API_KEY" not in env


@pytest.mark.parametrize("line", [
    'socket.create_connection(("127.0.0.1", 9), timeout=3)',
    'subprocess.run(["true"])',
    'os.system("true")',
], ids=["network", "subprocess", "system"])
def test_the_runner_refuses_the_same_things_on_every_platform(tmp_path, line, monkeypatch):
    monkeypatch.setenv("PBE_NO_SANDBOX", "1")
    monkeypatch.setattr(build, "sandbox", lambda: None)  # the hook alone, without the OS's sandbox
    built = build_parts(one_part(code_that(line)), tmp_path)
    assert not built["p"].ok and "is not permitted here" in built["p"].error


def test_a_family_needs_a_variant():
    with pytest.raises(ValueError, match="name a variant"):
        tasks.load("nut-knob")


def test_output_that_isnt_text_doesnt_stop_a_build(tmp_path):
    code = 'import sys\n\ndef build(p):\n    sys.stdout.buffer.write(b"\\xff\\xfe")\n    return cq.Workplane("XY").box(5, 5, 5)\n'
    assert build_parts(one_part(code), tmp_path)["p"].ok


def test_the_conversation_is_saved_even_if_grading_breaks(tmp_path, monkeypatch):
    task = tasks.load("m5-spacer")
    sub = submission.parse(task.reference)
    monkeypatch.setattr(agent, "run_trial", lambda *a, **k: (a_record(cost_usd=0.5, outcome="submitted"), [{"role": "user", "content": "hi"}], sub))

    def broken(*a):
        raise RuntimeError("grader")
    monkeypatch.setattr(agent, "evaluate", broken)
    with pytest.raises(RuntimeError):
        runner.run_one(task, "m", "can_ask", 1, tmp_path, Args)
    saved = tmp_path / "m5-spacer" / "can_ask" / "m" / "t1"
    assert (saved / "transcript.json").exists() and (saved / "submission.yaml").exists()
    assert runner.spent(tmp_path) == 0.5  # its cost counts

    def finds_it_fine(*a):
        return [agent.checks.Finding("R1", "-", True, "", "")], {}
    monkeypatch.setattr(agent, "evaluate", finds_it_fine)
    monkeypatch.setattr(agent, "run_trial", lambda *a, **k: pytest.fail("a resume mustn't pay for the trial again"))
    assert runner.run_one(task, "m", "can_ask", 1, tmp_path, Args).all_pass is True  # a rerun finishes the grading


def test_a_check_that_crashes_is_a_failure_not_a_crash(tmp_path, monkeypatch):
    def boom(built):
        raise ValueError("bad geometry")
    monkeypatch.setattr(agent.checks, "ALL", [boom])
    task = tasks.Task("t", "x", {}, [], None)
    findings, _ = agent.evaluate(task, one_part('def build(p):\n    return cq.Workplane("XY").box(5, 5, 5)\n'), tmp_path)
    assert [(f.check, f.ok) for f in findings] == [("boom", False)]


def _pucks(role, gap=0):
    code = f'''
def build(p):
    a = cq.Workplane("XY").circle(5).extrude(3)
    b = cq.Workplane("XY").workplane(offset={gap}).center(15, 0).circle(5).extrude(3)
    return a.union(b)
'''
    return submission.Submission.model_validate({
        "task": "t", "note": "", "params": {}, "hardware": [], "criteria": [], "manual": [],
        "parts": [{"id": "p", "role": role, "material": "PLA", "print_orientation": "flat", "use_orientation": "flat", "code": code}]})


@pytest.mark.parametrize("role, gap, ok", [("final", 0, False), ("coupon", 0, True), ("coupon", 2, False)])
def test_a_coupon_can_be_separate_pieces_on_the_bed(tmp_path, role, gap, ok):
    # Opus's M3 t2 was failed for a coupon of three separate pockets, which prints fine
    built = build_parts(_pucks(role, gap), tmp_path)
    assert checks.connected_bodies(built)[0].ok is ok


def test_regrading_a_run_without_grades_keeps_its_own_summary(tmp_path):
    # issue 32: the crash replay and coupon loop samples keep their own summary.csv and no grades.json
    run_dir = tmp_path / "crash-replay"
    run_dir.mkdir()
    own = "trial,model,saved_verdict\nsome/trial,m,fail builds\n"
    (run_dir / "summary.csv").write_text(own)
    runner.regrade(run_dir, ["nut-knob"])
    assert runner.summarize(run_dir) == []
    assert (run_dir / "summary.csv").read_text() == own


def _saved_trials(run_dir, count):
    """`count` saved m5-spacer trials, each the task's reference saved with no findings, so a regrade changes every verdict."""
    task = tasks.load("m5-spacer")
    for trial in range(1, count + 1):
        folder = runner.trial_folder(run_dir, task, "can_ask", "m", trial)
        folder.mkdir(parents=True)
        (folder / "submission.yaml").write_text(task.reference)
        record = a_record(task=task.id, outcome="submitted", trial=trial)
        record.set_verdict([])
        record.save(folder)


def _saved_files(run_dir):
    return {path.relative_to(run_dir): path.read_bytes() for path in sorted(run_dir.rglob("*"))
            if path.name in ("grades.json", "summary.csv")}


def test_a_regrade_with_two_workers_saves_what_a_serial_one_does(tmp_path):
    stamp = runner.VersionStamp("2026-11-12T00:00:00+00:00", "abc1234")
    for workers in (1, 2):
        run_dir = tmp_path / f"workers-{workers}"
        _saved_trials(run_dir, 2)
        runner.regrade(run_dir, ["m5-spacer"], workers, stamp)
        runner.summarize(run_dir)
    serial, parallel = _saved_files(tmp_path / "workers-1"), _saved_files(tmp_path / "workers-2")
    assert len(serial) == 3 and parallel == serial
    assert all(TrialRecord.load(folder).regrades for folder, _ in TrialRecord.all_in(tmp_path / "workers-2"))
