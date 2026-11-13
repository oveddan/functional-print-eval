"""What servo-mount's format.yaml adds to its prompt leaves every other task's prompt as it was.

servo-mount leaves the servos out of the hardware list, so the MG996R's tab rib is something to ask
about. The hashes below are of every existing task's opening messages (system prompt and request)
and tools, per condition, taken on main at c3cec82, before format.yaml could leave hardware out. Re-taken on
2026-11-12, when round 3 added the "Supports: none" line to every condition (agent.NO_SUPPORTS) and Dan's notes on
the servo horn changed catalog/hardware.yaml: a diff of each prompt against main's showed nothing else changed.
"""
import hashlib
import json

import pytest

from pbe.runner import agent, python_tool, tasks
from pbe.runner.measure import Person

BEFORE_PROMPT_RULES = {
    "m5-spacer can_ask": "efe933b2e04ba04c3fa8ee5676e5c5a734b173814555e589ef91fa156d823e18",
    "m5-spacer all_given": "efe933b2e04ba04c3fa8ee5676e5c5a734b173814555e589ef91fa156d823e18",
    "m5-spacer can_run_code": "9c7a6dd8a2ef799f9ac3f355729dbf1e071d15cd777e6debfef7a246e71fc7c9",
    "tripod-plate can_ask": "c134497af2f70eed1458630ccb9f3c4c6dc0e76e06166504d7c5ce2294139bbb",
    "tripod-plate all_given": "beb45c077c24cb736c09dcd60bd7b61045aad4c08c5fb7d0ead313afb75d3aa1",
    "tripod-plate can_run_code": "efb3240fee3fe1cc5b67bde063a2dd2dcd07a916ebe57ae8c3e324b81706727e",
    "bearing-wheel can_ask": "2e7a279e0da054cbe08f4beeffdc070b15e8e7e596596d940346a18a2b2568f4",
    "bearing-wheel all_given": "f26518d0c0811adf750c8087f567af2b5456f94113c5d83f90989a0b1151d26e",
    "bearing-wheel can_run_code": "a51dbc82642e9a11ff90249ec4617942178462553911b938780eb4b6e3af7962",
    "nut-knob/M3 can_ask": "e33af447155bc39f00307cf7bfd035b5df172d3c102f910683905f88af8d8717",
    "nut-knob/M3 all_given": "e33af447155bc39f00307cf7bfd035b5df172d3c102f910683905f88af8d8717",
    "nut-knob/M3 can_run_code": "5c9886bf9775cc9e56ae353c55c05a16969cac66a34c3c0886ae4fd33b756a46",
    "nut-knob/M5 can_ask": "2baa7c0c8cc51cd69e0b89a923a01c3ca7c37bec0531b310d7e85d026076469c",
    "nut-knob/M5 all_given": "2baa7c0c8cc51cd69e0b89a923a01c3ca7c37bec0531b310d7e85d026076469c",
    "nut-knob/M5 can_run_code": "46f3575deef3c5dd0b3d7139493aea890407088df676ccf37a721b499a15fbce",
    "nut-knob/M8 can_ask": "d39e771b1c33bbf1e3bc759f31e701c1267047dc5ba420f27518cc018cddd7b0",
    "nut-knob/M8 all_given": "d39e771b1c33bbf1e3bc759f31e701c1267047dc5ba420f27518cc018cddd7b0",
    "nut-knob/M8 can_run_code": "c5c76dc348a9e4defb9b64798799d7b80b3575dc546cb6b382aa2a6f8a8ddecf",
    "estoa-light can_ask": "5b11d989c5b17a15c73ea39092c422d22c2bb181afccf26f48b8fd020e90b090",
    "estoa-light all_given": "2d49252224fd722f2ce3e1f760c91b852fb59b14bd1c8f9f522c57a058c17a03",
    "estoa-light can_run_code": "ffb981b298201e9cf8883537fbcf442481a509766ace03929c86dcd5f9f98fe9",
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
