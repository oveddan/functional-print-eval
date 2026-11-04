"""Adding a task changes nothing an existing task's model reads (issue 41).

Every existing task's opening messages and tools, in every condition, are hashed and compared with
digests taken on `claude/caching-pilot` before the spool holder was added. A change to the system
prompt, the hardware list, the tools or an existing request shows up here. If one is meant, take the
new digests with `uv run python tests/test_existing_prompts.py` and say why in CHANGELOG.md.
"""
import hashlib
import json

import pytest

from pbe.runner import agent, tasks
from pbe.runner.measure import Person
from pbe.runner.trial_record import CodeSettings

EXISTING = ["m5-spacer", "tripod-plate", "bearing-wheel", "nut-knob/M3", "nut-knob/M5", "nut-knob/M8"]
# phone-stand is left out: its hidden facts don't load on the base branch, so no trial can run on it

# taken on claude/caching-pilot at 11489b7, before tasks/spool-holder existed
DIGESTS = {
    ('m5-spacer', 'can_ask'): '388514ad7aa24673ed6157cb20213657ea7507155318ff2dd72ec040126069cb',
    ('m5-spacer', 'all_given'): '388514ad7aa24673ed6157cb20213657ea7507155318ff2dd72ec040126069cb',
    ('m5-spacer', 'can_run_code'): 'd1db35ede240b570ce666b333015647c3d862eeea2803d8e25ff633129abeead',
    ('tripod-plate', 'can_ask'): '135983f6448e698180c27fa3fa4ecfde9f7b886e6fca6a2921fe678fa813fa21',
    ('tripod-plate', 'all_given'): 'f0ab9f2a640eee587a4ab865af5c3f716cb68f6b0e630627d3ccbdbb646a9329',
    ('tripod-plate', 'can_run_code'): '5ce91e1b0b2687d0247e4cb5447ae2f807dad6478318a2dd65f847657e630d37',
    ('bearing-wheel', 'can_ask'): 'c977be9718f4eb7c04accd70f13b15d4061d2a0efd1bdf88a57afb6d3864ff24',
    ('bearing-wheel', 'all_given'): '3a5bfe20e5905d84a8569cb5303e33ed7fcf114025715f6fdd7cf65fd6de0239',
    ('bearing-wheel', 'can_run_code'): 'e14cdf64da4e417020cedb041b43f860ff350243379cf4be8a6edf080eb40b33',
    ('nut-knob/M3', 'can_ask'): 'a885c8c388baabe11298eff797ce4fb94ad3c0dfe51f22183f003742576af400',
    ('nut-knob/M3', 'all_given'): 'a885c8c388baabe11298eff797ce4fb94ad3c0dfe51f22183f003742576af400',
    ('nut-knob/M3', 'can_run_code'): '141447336d85c1683b8d140e0aedc0934c5073b6a578ba6923ac0cca4f1ad97f',
    ('nut-knob/M5', 'can_ask'): '9e779ff9cf711e924e3dba06d63bfcc8d0f242a9067bfa73becb5a74a00fbc27',
    ('nut-knob/M5', 'all_given'): '9e779ff9cf711e924e3dba06d63bfcc8d0f242a9067bfa73becb5a74a00fbc27',
    ('nut-knob/M5', 'can_run_code'): '662b918ab23036808f88ea587a000725341da780e95643476ad4e50d5f8a4648',
    ('nut-knob/M8', 'can_ask'): '81295923c4ab0752362877e4298059e82be92783b5f713984a0b73e412034532',
    ('nut-knob/M8', 'all_given'): '81295923c4ab0752362877e4298059e82be92783b5f713984a0b73e412034532',
    ('nut-knob/M8', 'can_run_code'): 'f8ad92da9baea104656ede35d836f6339163ab534eca45052824eb8833be68cc',
}


class NoCodeTool:
    """Stands in for run_python, so can_run_code's prompt is read without a sandbox (as in test_caching)."""
    settings = CodeSettings(sandbox="none (test)", timeout_s=1, trial_s=1, output_chars=1)

    def prompt_line(self):
        return "- run_python(code): run Python."


def digest(task_id, condition):
    """What a model reads at the start of a trial, and the tools it's given, as one hash."""
    task = tasks.load(task_id)
    python = NoCodeTool() if condition == "can_run_code" else None
    max_turns = agent.DEFAULT_MAX_TURNS[condition]
    messages = agent.opening_messages(task, condition, Person(task.hidden_facts), max_turns, python)
    text = json.dumps({"messages": messages, "tools": agent.tools(condition)}, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.parametrize("condition", agent.CONDITIONS)
@pytest.mark.parametrize("task_id", EXISTING)
def test_an_existing_task_reads_what_it_read_before(task_id, condition):
    assert digest(task_id, condition) == DIGESTS[task_id, condition]


if __name__ == "__main__":
    for task_id in EXISTING:
        for condition in agent.CONDITIONS:
            print(f"    ({task_id!r}, {condition!r}): {digest(task_id, condition)!r},")
