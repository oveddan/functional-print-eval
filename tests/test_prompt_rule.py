"""What servo-mount's format.yaml adds to its prompt leaves every other task's prompt as it was.

servo-mount leaves the servos out of the hardware list, so the MG996R's tab rib is something to ask
about. The hashes below are of every existing task's opening messages (system prompt and request)
and tools, per condition, taken on main at c3cec82, before format.yaml could leave hardware out.
"""
import hashlib
import json

import pytest

from pbe.runner import agent, python_tool, tasks
from pbe.runner.measure import Person

BEFORE_PROMPT_RULES = {
    "m5-spacer can_ask": "1aff3fcca3a65f2ef2c72ea2c4944cdc5bf1bdb87a4a093abc740198b138c00d",
    "m5-spacer all_given": "1aff3fcca3a65f2ef2c72ea2c4944cdc5bf1bdb87a4a093abc740198b138c00d",
    "m5-spacer can_run_code": "7ebebfe02c76b84389b6eb46290f4b8da1b8cd99e479ead0e8036a258f0bb06e",
    "tripod-plate can_ask": "b6f61734b3ebba54b9b538705efe5c734cc1ae7704a6a97fea127d4eec4cb4e0",
    "tripod-plate all_given": "1cd8b1dde01799979e95dd7d96fcdf8d4837b59ecb812d5ef6acbf50a27b5bec",
    "tripod-plate can_run_code": "177aa3955976298d5e8041962086e724dcbf39fdcef75cd016099f5b29f5d137",
    "bearing-wheel can_ask": "05a3869169a46e2cbdaaa21cf48cd293592392385ec0b51e7e7eb978d49113b5",
    "bearing-wheel all_given": "4f3941acacafbc02336861480a4ed4a7641ab99128cfd1deed3d1ae1d677d100",
    "bearing-wheel can_run_code": "1be7139d4e35b3055b49f45f81a03d8b7d24b93ebcb542129bebe4d80dd65774",
    "nut-knob/M3 can_ask": "99a18b04bf31477c83ae35634572e2968b7eac3cdff1823da7505480baac76ff",
    "nut-knob/M3 all_given": "99a18b04bf31477c83ae35634572e2968b7eac3cdff1823da7505480baac76ff",
    "nut-knob/M3 can_run_code": "cfab731aab5049f5afcebdeee1cb7c7bc3fe605d7fbc608cffbae68afcf27e60",
    "nut-knob/M5 can_ask": "768a457d2393420b3d48e6b10dfab6c714584eb8488e32e2656edb36af349158",
    "nut-knob/M5 all_given": "768a457d2393420b3d48e6b10dfab6c714584eb8488e32e2656edb36af349158",
    "nut-knob/M5 can_run_code": "405eab970846fe91b32e5f234b3872d1881f7d950a7b3d1f64df132dad522802",
    "nut-knob/M8 can_ask": "1547d6d06b9f15bd6c21691eb4a58ec6c1f7cb51a4c41d39b41d84fef7ad1b4f",
    "nut-knob/M8 all_given": "1547d6d06b9f15bd6c21691eb4a58ec6c1f7cb51a4c41d39b41d84fef7ad1b4f",
    "nut-knob/M8 can_run_code": "3933179ef9b03eddf8530474f0bea1319173c38741a7a042e28e80d96a45f6cc",
    "estoa-light can_ask": "af6dccd9bc9213334321815d4d9d0b3283a50f2c3e728cb88a9ede5c9cc69fcd",
    "estoa-light all_given": "972c30d61e19d9d3eb8a4f6fc69f80794b97ec29c24d16ded72fe7e54e52715c",
    "estoa-light can_run_code": "048cd0242cc1989b10be0c8adfed8bce21954b043e8ed682cd6105e94f6a2f2d",
}


def opening_hash(task_id, condition, tmp_path):
    task = tasks.load(task_id)
    python = None
    if condition == python_tool.CONDITION:  # its prompt names the task's files; no sandbox is needed to write it
        python = python_tool.PythonTool(None, python_tool._fresh_workdir(task_id, tmp_path / "work"))
    messages = agent.opening_messages(task, condition, Person(task.hidden_facts), agent.DEFAULT_MAX_TURNS[condition], python)
    return hashlib.sha256(json.dumps([messages, agent.tools(condition, task.format.assembly)], sort_keys=True).encode()).hexdigest()


@pytest.mark.parametrize("task_condition", sorted(BEFORE_PROMPT_RULES))
def test_every_existing_task_is_sent_the_same_prompt_and_tools(task_condition, tmp_path):
    task_id, condition = task_condition.split()
    assert opening_hash(task_id, condition, tmp_path) == BEFORE_PROMPT_RULES[task_condition]


def test_every_condition_and_runnable_task_is_covered():
    runnable = {"m5-spacer", "tripod-plate", "bearing-wheel", "nut-knob/M3", "nut-knob/M5", "nut-knob/M8", "estoa-light"}
    assert {key.split()[0] for key in BEFORE_PROMPT_RULES} == runnable
    # every condition but can_ask_datasheet, which came after and is refused for a task with no datasheet,
    # and can_test, which also came after
    assert {key.split()[1] for key in BEFORE_PROMPT_RULES} == set(agent.CONDITIONS) - {agent.DATASHEET, agent.TEST_CONDITION}


def test_only_servo_mount_leaves_hardware_out():
    for task_id in {key.split()[0] for key in BEFORE_PROMPT_RULES}:
        assert tasks.load(task_id).format.hardware_left_out == []
    assert tasks.load("servo-mount").format.hardware_left_out == ["servos"]


def test_no_rule_shows_the_whole_catalog():
    assert agent.hardware_text() == agent.hardware_text(())
    assert "tab_notch" in agent.hardware_text()


def test_a_rule_naming_no_catalog_section_is_refused():
    with pytest.raises(ValueError, match="no section"):
        agent.hardware_text(("servo",))


def test_only_a_task_with_a_datasheet_can_run_with_one():
    for task_id in {key.split()[0] for key in BEFORE_PROMPT_RULES}:
        task = tasks.load(task_id)
        assert task.format.datasheet == []
        with pytest.raises(agent.NoDatasheet):
            agent.first_message(task, agent.DATASHEET, Person(task.hidden_facts))
