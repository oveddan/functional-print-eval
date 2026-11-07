"""Building on submit (issue 26): in can_run_code, submit_design builds every part first and
sends build errors back for the model to fix. The error text reaches the model, so the
build runs in run_python's sandbox and must not be able to carry a hidden file out.

Each sandbox test runs in the sandbox a trial would use here (`conftest.sandbox`), and in
every sandbox with --all-sandboxes."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from pbe.parts.submission import Submission
from pbe.runner import agent, build_on_submit, code_sandbox, tasks
from pbe.runner.code_sandbox import Limits, Ran
from pbe.runner.python_tool import PythonTool

ROOT = Path(__file__).resolve().parents[1]
HIDDEN = ROOT / "tasks/m5-spacer/hidden_facts.yaml"
DOES_NOT_BUILD = "def build(p):\n    return cq.Workplane().box(math.pi, 2, 3)\n"  # no import math

# sha256 of the can_ask and all_given tools and of their system prompt, taken before this change
TOOLS_BEFORE = "6b7e33adfe134cbc79e1f48f87b77e00e26a454960e39aa030f0f7ccee0a613d"
PROMPT_BEFORE = "043a6f16e3b32577b6c7c56da8c377919a4068a815e4019f740111487288ec73"


@pytest.fixture
def python(sandbox, tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    return PythonTool(sandbox, workdir)


def errors_of(python, sub):
    built = build_on_submit.build(python, sub)
    assert not built.unbuilt
    return built.errors


def reference_design():
    """The spacer's reference design, as a model would send it: the runner fills in `task`."""
    design = yaml.safe_load(tasks.load("m5-spacer").reference)
    del design["task"]
    return design


def with_code(code, role="final"):
    design = reference_design()
    design["parts"][0].update(code=code, role=role)
    return design


def submission(design):
    return Submission.model_validate({**design, "task": "m5-spacer"})


def tool_call(call_id, name, arguments):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def scripted(*designs):
    """A fake chat that calls submit_design with each design in turn."""
    sent = []

    def chat(model, messages, tools=None, max_tokens=None):
        sent.append(tools)
        call = tool_call(f"c{len(sent)}", "submit_design", designs[len(sent) - 1])
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [call]}}], "usage": {"cost": 0.001}}
    return chat, sent


def run(condition, *designs, max_turns=5, tmp_path=None):
    chat, sent = scripted(*designs)
    workdir = tmp_path / "work" if tmp_path else None
    record, messages, sub = agent.run_trial(tasks.load("m5-spacer"), "fake", condition=condition,
                                            max_turns=max_turns, chat=chat, workdir=workdir)
    return record, [m["content"] for m in messages if m["role"] == "tool"], sub


# the build itself

def test_a_part_that_builds_gets_no_comment(python):
    assert errors_of(python, submission(reference_design())) == {}


def test_a_build_error_comes_back_with_the_part_and_its_traceback(python):
    errors = errors_of(python, submission(with_code(DOES_NOT_BUILD)))
    assert list(errors) == ["spacer"]
    assert 'File "spacer", line 2, in build' in errors["spacer"] and "NameError: name 'math'" in errors["spacer"]
    assert "main.py" not in errors["spacer"]  # the traceback starts in the part's own code


def test_test_prints_are_built_too(python):
    errors = errors_of(python, submission(with_code(DOES_NOT_BUILD, role="coupon")))
    assert list(errors) == ["spacer"]


@pytest.mark.parametrize("code, expected", [
    ("x = 1\n", "doesn't define build(p)"),
    ("def build(p):\n    import sys\n    sys.exit(0)\n", "nothing was exported"),
    ("def build(p):\n    return 'not a shape'\n", "Error"),
], ids=["no build", "exits early", "not a shape"])
def test_other_ways_of_not_building(python, code, expected):
    assert expected in errors_of(python, submission(with_code(code)))["spacer"]


def test_the_mesh_is_read_back_inside_the_sandbox(python):
    """Reading the STL is part of the sandboxed run, so its memory and time are capped and charged
    (Codex's review of PR 21); the runner itself never parses it."""
    code = ("import trimesh\ndef refuse(*args, **kwargs):\n    raise ValueError('unreadable')\n"
            "def build(p):\n    trimesh.load = refuse\n    return cq.Workplane().box(1, 1, 1)\n")
    error = errors_of(python, submission(with_code(code)))["spacer"]
    assert error == "It exported, but the mesh can't be read (ValueError)."
    assert not hasattr(build_on_submit, "trimesh")


def test_a_part_that_runs_too_long_is_stopped(python, monkeypatch):
    monkeypatch.setattr(build_on_submit, "TIMEOUT_S", 3)
    errors = errors_of(python, submission(with_code("def build(p):\n    while True: pass\n")))
    assert errors["spacer"] == "Stopped: it ran longer than 3 s."


@pytest.mark.parametrize("path", [str(HIDDEN), "../" * 12 + "tasks/m5-spacer/hidden_facts.yaml"], ids=["absolute", "relative"])
def test_a_hidden_file_cannot_come_back_in_an_error(python, path):
    secret = HIDDEN.read_text().splitlines()[-1].strip()
    assert secret and secret in HIDDEN.read_text()  # a line that would show the file was read
    code = f"def build(p):\n    raise ValueError(open({path!r}).read())\n"
    error = errors_of(python, submission(with_code(code)))["spacer"]
    assert "FileNotFoundError" in error and secret not in error


def test_a_part_sees_only_its_own_code_not_the_models_working_folder(python):
    code = "import os\ndef build(p):\n    raise ValueError(sorted(os.listdir('.')))\n"
    error = errors_of(python, submission(with_code(code)))["spacer"]
    assert "ValueError: ['part.json']" in error


def test_a_long_error_is_cut(python):
    code = "def build(p):\n    raise ValueError('x' * 100_000)\n"
    error = errors_of(python, submission(with_code(code)))["spacer"]
    assert len(error) < build_on_submit.ERROR_CHARS + 100 and "characters cut" in error


# the trial's code time

LOOPS = "def build(p):\n    while True: pass\n"


def two_parts(first_code, second_code):
    design = reference_design()
    second = {**design["parts"][0], "id": "second", "code": second_code}
    design["parts"][0]["code"] = first_code
    design["parts"].append(second)
    return design


def test_building_is_charged_to_the_trials_code_time(python):
    build_on_submit.build(python, submission(reference_design()))
    assert 0 < python.seconds_used < 60


def test_a_part_cut_short_by_the_code_time_is_left_unbuilt_not_reported(sandbox, tmp_path):
    python = PythonTool(sandbox, tmp_path, Limits(trial_s=4))
    built = build_on_submit.build(python, submission(with_code(LOOPS)))
    assert built.errors == {} and built.unbuilt == ["spacer"]
    assert python.seconds_left() == 0


def test_once_code_time_is_used_up_nothing_is_built(sandbox, tmp_path, monkeypatch):
    python = PythonTool(sandbox, tmp_path, Limits(trial_s=10))
    python.seconds_used = 10
    monkeypatch.setattr(code_sandbox, "run", lambda *args, **kwargs: pytest.fail("nothing runs"))
    built = build_on_submit.build(python, submission(two_parts(DOES_NOT_BUILD, LOOPS)))
    assert built.errors == {} and built.unbuilt == ["spacer", "second"]


def test_an_error_found_before_code_time_ran_out_is_still_sent_back(sandbox, tmp_path):
    python = PythonTool(sandbox, tmp_path, Limits(trial_s=8))
    built = build_on_submit.build(python, submission(two_parts(DOES_NOT_BUILD, LOOPS)))
    assert list(built.errors) == ["spacer"] and built.unbuilt == ["second"]


def test_a_design_left_unbuilt_is_accepted_and_recorded(sandbox, tmp_path, monkeypatch):
    real = PythonTool.for_trial

    def spent(task_id, workdir=None, limits=Limits()):
        tool = real(task_id, workdir, limits)
        tool.seconds_used = tool.limits.trial_s
        return tool
    monkeypatch.setattr(PythonTool, "for_trial", spent)
    record, replies, sub = run("can_run_code", with_code(DOES_NOT_BUILD), tmp_path=tmp_path)
    assert replies == ["Received."] and record.outcome == "submitted" and record.repairs == 0
    assert record.build_on_submit.accepted_unbuilt == ["spacer"] and record.build_on_submit.sent_back == []


# in a trial

def test_a_build_error_is_sent_back_and_a_fix_is_accepted(sandbox, tmp_path):
    record, replies, sub = run("can_run_code", with_code(DOES_NOT_BUILD), reference_design(), tmp_path=tmp_path)
    assert replies[0].startswith("Not handed in: 1 part didn't build. Fix it and call submit_design again.")
    assert "NameError" in replies[0]
    assert replies[1] == "Received."  # a part that builds gets no comment
    assert record.outcome == "submitted" and sub is not None and record.turns == 2 and record.repairs == 1
    assert record.build_on_submit.sent_back == [["spacer"]] and not record.build_on_submit.out_of_turns_while_fixing
    assert record.as_saved()["build_on_submit"] == {"sent_back": [["spacer"]], "out_of_turns_while_fixing": False,
                                                    "accepted_unbuilt": []}


def test_running_out_of_turns_while_fixing_is_recorded(sandbox, tmp_path):
    record, replies, sub = run("can_run_code", with_code(DOES_NOT_BUILD), with_code(DOES_NOT_BUILD),
                               max_turns=2, tmp_path=tmp_path)
    assert record.outcome == "no_submission" and sub is None and record.repairs == 2
    assert record.build_on_submit.sent_back == [["spacer"], ["spacer"]]
    assert record.build_on_submit.out_of_turns_while_fixing


def test_a_design_that_builds_first_time_records_no_build_error(sandbox, tmp_path):
    record, replies, sub = run("can_run_code", reference_design(), tmp_path=tmp_path)
    assert replies == ["Received."] and record.repairs == 0
    assert not record.build_on_submit.hit_a_build_error and not record.build_on_submit.out_of_turns_while_fixing


def test_a_sandbox_that_cannot_start_is_an_infrastructure_error(sandbox, tmp_path, monkeypatch):
    monkeypatch.setattr(code_sandbox, "run", lambda *args, **kwargs: Ran(
        exit_code=None, stdout="", stderr="", stopped=f"{code_sandbox.COULD_NOT_START}: daemon gone"))
    record, replies, sub = run("can_run_code", reference_design(), tmp_path=tmp_path)
    assert record.outcome == "error" and "daemon gone" in record.error and record.repairs == 0


def test_the_model_is_told_that_submit_design_builds_first(sandbox, tmp_path):
    chat, sent = scripted(reference_design())
    record, messages, sub = agent.run_trial(tasks.load("m5-spacer"), "fake", condition="can_run_code",
                                            max_turns=2, chat=chat, workdir=tmp_path / "work")
    submit = next(tool for tool in sent[0] if tool["function"]["name"] == "submit_design")
    assert "Every part is built first" in submit["function"]["description"]
    assert agent.SUBMIT_LINE_BUILDS_FIRST in messages[0]["content"] and agent.SUBMIT_LINE not in messages[0]["content"]


def test_grading_builds_the_parts_itself():
    """A design accepted after a repair is graded from its own code, built again by pbe.parts.build."""
    import inspect
    assert "build_parts(sub" in inspect.getsource(agent.evaluate)
    assert "build_on_submit" not in inspect.getsource(agent.evaluate)


# the conditions with no run_python are unchanged

@pytest.mark.parametrize("condition", ["can_ask", "all_given"])
def test_the_other_conditions_send_the_same_tools_and_prompt(condition):
    tools = json.dumps(agent.tools(condition), sort_keys=True).encode()
    assert hashlib.sha256(tools).hexdigest() == TOOLS_BEFORE
    assert hashlib.sha256(agent.system_prompt(8).encode()).hexdigest() == PROMPT_BEFORE


@pytest.mark.parametrize("condition", ["can_ask", "all_given"])
def test_the_other_conditions_accept_a_design_without_building_it(condition, monkeypatch):
    monkeypatch.setattr(code_sandbox, "find", lambda: pytest.fail("no sandbox needed"))
    monkeypatch.setattr(build_on_submit, "build", lambda *args: pytest.fail("nothing is built on submit"))
    record, replies, sub = run(condition, with_code(DOES_NOT_BUILD), max_turns=1)
    assert replies == ["Received."] and record.outcome == "submitted" and record.repairs == 0
    assert record.build_on_submit is None and "build_on_submit" not in record.as_saved()


def test_saved_trials_load_and_save_unchanged():
    """Only a can_run_code record has build_on_submit, and saving any record again gives the same fields."""
    for path in sorted((ROOT / "results/runs").rglob("grades.json")):
        saved = json.loads(path.read_text())
        assert ("build_on_submit" in saved) == (saved["condition"] == "can_run_code"), path
        record = agent.TrialRecord.model_validate(copy.deepcopy(saved))
        assert record.as_saved() == saved, path
