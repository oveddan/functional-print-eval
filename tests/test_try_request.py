"""pbe.try_request: a request someone writes themselves runs as a trial and is graded by the general checks only."""
import json

import pytest

from pbe import try_request
from pbe.graders import checks
from pbe.parts import submission
from pbe.runner import tasks

REQUEST = "I need a 20 mm spacer, 12 mm across, for an M5 bolt between two plates."


def test_an_own_request_runs_and_is_graded_by_the_general_checks_only(tmp_path):
    design = submission.parse(tasks.load("m5-spacer").reference)
    arguments = json.dumps({key: value for key, value in design.model_dump().items() if key != "task"})
    sent = []

    def chat(model, messages, tools=None, max_tokens=None, **params):
        sent.append(messages)
        call = {"id": "1", "type": "function", "function": {"name": "submit_design", "arguments": arguments}}
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [call]}}], "usage": {"cost": 0.01}}
    record, folder = try_request.run(REQUEST, "fake", tmp_path, chat=chat)

    assert sent[0][1] == {"role": "user", "content": REQUEST}
    assert record.task == tasks.OWN_REQUEST and record.outcome == "submitted" and record.verdict == "pass"
    assert {finding.check for finding in record.findings} == {check.__name__ for check in checks.ALL}
    assert (folder / "grades.json").exists() and (folder / "transcript.json").exists()
    assert try_request.part_files(folder) == [("spacer", "final", folder / "parts/spacer.stl")]
    assert "Verdict: pass" in try_request.report(record, folder) and "$0.0100" in try_request.report(record, folder)
    with pytest.raises(FileExistsError):  # a second request saved over it would get this one's verdict back
        try_request.run("A different request", "fake", tmp_path, chat=chat)
