"""pbe.live: the eval's agent on a real part. The person answers measure and print_test, at the terminal or from a
file, and the saved session runs again without them."""
import json

import pytest
import yaml

from pbe import live as live_command
from pbe.parts import submission
from pbe.runner import agent, live, sketch, tasks
from pbe.runner.measure import NO_ANSWER

REQUEST = "I need a spacer for an M5 bolt, to go between two plates on my shelf."
TUBE = "20 mm, give or take"
CAME_OUT = "the bolt slides through, a little loose"


def spacer():
    return submission.parse(tasks.load("m5-spacer").reference).model_dump()


def scripted(calls):
    """A model that makes these tool calls, one a turn, and keeps what it was sent."""
    calls, sent = iter(calls), []

    def chat(model, messages, tools=None, max_tokens=None, **params):
        sent.append({"messages": list(messages), "tools": tools})
        name, arguments = next(calls)
        call = {"id": name, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [call]}}], "usage": {"cost": 0.01}}
    return chat, sent


def a_session():
    """Measure the gap, print the spacer as a test piece, then hand it in."""
    design = spacer()
    test_piece = [{**part, "id": "spacer_test"} for part in design["parts"]]
    return [("measure", {"item": "gap between the plates", "what": "height"}),
            ("print_test", {"params": design["params"], "parts": test_piece}),
            ("submit_design", {key: value for key, value in design.items() if key != "task"})]


def person_saying(*answers):
    answers, asked = iter(answers), []

    def ask(question):
        asked.append(question)
        return next(answers)
    return ask, asked


def tool_replies(folder):
    transcript = json.loads((folder / "transcript.json").read_text())
    return {message["tool_call_id"]: message["content"] for message in transcript if message["role"] == "tool"}


def test_a_live_session_asks_the_person_and_saves_what_they_said(tmp_path):
    chat, sent = scripted(a_session())
    ask, asked = person_saying(TUBE, CAME_OUT)
    task = tasks.from_request(REQUEST)
    record, folder, session = live_command.run(task, "fake", tmp_path, ask=ask, chat=chat)

    # the eval's own prompt and tools, unchanged
    assert sent[0]["messages"][0]["content"] == agent.system_prompt(agent.DEFAULT_MAX_TURNS["can_test"], can_test=True)
    assert sent[0]["messages"][1] == {"role": "user", "content": REQUEST} and sent[0]["tools"] == agent.tools("can_test", sketch=True)
    # the person was asked both, and shown where the test piece's file is
    piece = folder / "test_prints/1/spacer_test.stl"
    assert asked[0] == "The agent asks you to measure: gap between the plates, height"
    assert piece.exists() and str(piece) in asked[1]
    replies = tool_replies(folder)
    assert replies["measure"] == TUBE
    assert replies["print_test"] == f"{agent.TEST_PRINTED}\nspacer_test:\n- {CAME_OUT}"
    # the record marks the test print's reply as the person's, not a recorded print's
    assert record.outcome == "submitted" and record.measures[0].reply == TUBE
    assert record.test_prints[0]["reply"] == {"spacer_test": [{"text": CAME_OUT, "basis": "live answer"}]}
    assert (folder / "parts/spacer.stl").exists() and (folder / "grades.json").exists()
    saved = yaml.safe_load((folder / live.SESSION_FILE).read_text())
    assert saved["request"] == REQUEST and saved["task"] == tasks.OWN_REQUEST
    assert saved["answers"]["measures"] == [{"item": "gap between the plates", "what": "height", "answer": TUBE, "source": "terminal"}]
    printed = saved["answers"]["test_prints"]
    assert [told["pieces"] for told in printed] == [{"spacer_test": CAME_OUT}] and list(printed[0]["shapes"]) == ["spacer_test"]
    printed = live_command.report(record, folder, session)
    assert "Pre-print check" in printed and "It is not a print simulation" in printed and str(folder / live.SESSION_FILE) in printed


def test_a_saved_session_runs_again_without_the_person(tmp_path):
    chat, _ = scripted(a_session())
    ask, _ = person_saying(TUBE, CAME_OUT)
    task = tasks.from_request(REQUEST)
    _, first, _ = live_command.run(task, "fake", tmp_path / "first", ask=ask, chat=chat)

    chat, _ = scripted(a_session())
    answers = live.load_answers(first / live.SESSION_FILE)
    _, again, session = live_command.run(task, "fake", tmp_path / "again", answers=answers, chat=chat)
    assert tool_replies(again) == tool_replies(first)
    assert [told.source for told in session.answers.measures] == ["answers file"]


def test_measurements_taken_beforehand_answer_through_the_evals_lookup_and_the_rest_goes_unanswered(tmp_path):
    (tmp_path / "measured.yaml").write_text(yaml.safe_dump(
        {"things": {"gap": {"aliases": ["gap between the plates"], "measurements": {"height": {"value": 20, "unit": "mm"}}}}}))
    person = live.LivePerson(live.load_answers(tmp_path / "measured.yaml"))
    assert person.measure("gap between the plates", "height") == "gap height: 20 mm"
    assert person.revealed == ["gap.height"] and person.measured[0].source == "things"
    assert person.measure("the bolt", "length") == NO_ANSWER and person.measured[1].source == "nobody answered"

    design = spacer()
    pieces = submission.Submission.model_validate({"task": "t", "params": design["params"],
                                                   "parts": [{**part, "role": "coupon"} for part in design["parts"]]})
    report = live.LiveTestPrints(tmp_path)(tasks.from_request(REQUEST), pieces)
    assert [(line.text, line.basis) for line in report["spacer"]] == [(live.DIDNT_PRINT, agent.NOT_PRINTED_BASIS)]


def test_an_eval_task_can_be_run_live_with_its_own_request_and_requirements(tmp_path):
    """--task: the person answers instead of the task's table, and the task's requirements still grade the hand-in."""
    design = spacer()
    chat, sent = scripted([("submit_design", {key: value for key, value in design.items() if key != "task"})])
    task = live_command.session_task(None, "m5-spacer")
    record, folder, session = live_command.run(task, "fake", tmp_path, chat=chat, condition="can_ask")
    assert sent[0]["messages"][1]["content"] == task.request and record.verdict == "pass"
    assert {requirement.id for requirement in task.requirements} <= {finding.check for finding in record.findings}


# --- a sketch with a measurement: numbered dimensions the person answers by number -------------------------------

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 60"><rect x="10" y="10" width="100" height="30" fill="none" stroke="black"/>'
       '<line x1="10" y1="50" x2="110" y2="50" stroke="black"/><text x="60" y="58" text-anchor="middle">1</text>'
       '<text x="116" y="28">2</text></svg>')
DIMENSIONS = [{"number": 1, "what": "the plate's length"}, {"number": 2, "what": "the plate's thickness"}]
BY_NUMBER = "1: 60 mm, 2: 4.1 mm"
CHECKED_SVG = sketch.checked({"svg": SVG, "dimensions": DIMENSIONS}).svg  # as saved: written out again from what was checked


def measure_with(svg=SVG, dimensions=DIMENSIONS):
    return ("measure", {"item": "plate", "what": "the numbered dimensions", "sketch": {"svg": svg, "dimensions": dimensions}})


def hand_in():
    return ("submit_design", {key: value for key, value in spacer().items() if key != "task"})


def test_a_sketch_is_shown_to_the_person_and_saved_with_the_transcript(tmp_path):
    chat, sent = scripted([measure_with(), hand_in()])
    ask, asked = person_saying(BY_NUMBER)
    shown = []
    task = tasks.from_request(REQUEST)
    record, folder, session = live_command.run(task, "fake", tmp_path, ask=ask, chat=chat, show=lambda path: shown.append(path) or True)

    saved = folder / "sketches/1.svg"
    assert saved.read_text() == CHECKED_SVG and shown == [saved]
    assert asked == [f"The agent asks you to measure: plate, the numbered dimensions\nSketch: {saved} (opened in your browser)\n"
                     "  1: the plate's length\n  2: the plate's thickness\nAnswer by number, e.g. \"1: 25.2 mm, 2: 40 mm\"."]
    assert tool_replies(folder)["measure"] == BY_NUMBER
    told = yaml.safe_load((folder / live.SESSION_FILE).read_text())["answers"]["measures"][0]
    assert told["sketch"] == "sketches/1.svg" and told["dimensions"] == DIMENSIONS and told["answer"] == BY_NUMBER
    assert str(saved) in live_command.report(record, folder, session)
    # the transcript keeps the call as the model made it, drawing and all
    transcript = json.loads((folder / "transcript.json").read_text())
    assert json.loads(transcript[2]["tool_calls"][0]["function"]["arguments"])["sketch"]["svg"] == SVG

    # replayed from the saved session: the same answer, the sketch saved again, and nobody shown anything
    chat, _ = scripted([measure_with(), hand_in()])
    answers = live.load_answers(folder / live.SESSION_FILE)
    _, again, _ = live_command.run(task, "fake", tmp_path / "again", answers=answers, chat=chat, show=lambda path: shown.append(path))
    assert tool_replies(again)["measure"] == BY_NUMBER and (again / "sketches/1.svg").read_text() == CHECKED_SVG and len(shown) == 1


def refused(tmp_path, svg=SVG, dimensions=DIMENSIONS):
    """What the model hears about a sketch, from a person who would answer anything; nothing may be saved or shown."""
    shown = []
    person = live.LivePerson(ask=lambda question: "40 mm", folder=tmp_path, show=shown.append)
    reply = person.measure("plate", "the numbered dimensions", sketch={"svg": svg, "dimensions": dimensions})
    assert not shown and not (tmp_path / live.SKETCHES).exists() and person.measured[0].source == "sketch refused"
    assert reply.startswith("I couldn't open your sketch: ") and reply.endswith("Call measure again with a fixed sketch, or without one.")
    return reply


def test_a_sketch_that_isnt_a_plain_drawing_is_refused_with_the_reason(tmp_path):
    inside = SVG.removesuffix("</svg>")
    assert "doesn't parse as SVG" in refused(tmp_path, svg="<svg>not closed")
    assert 'one <svg xmlns="http://www.w3.org/2000/svg"> element' in refused(tmp_path, svg="<html><body>1 2</body></html>")
    assert f"at most {sketch.MAX_CHARS}" in refused(tmp_path, svg=inside + "<desc>" + "x" * sketch.MAX_CHARS + "</desc></svg>")
    assert "<script> isn't allowed" in refused(tmp_path, svg=inside + "<script>alert(1)</script></svg>")
    assert "<foreignObject> isn't allowed" in refused(tmp_path, svg=inside + "<foreignObject><p>1</p></foreignObject></svg>")
    assert "<image> isn't allowed" in refused(tmp_path, svg=inside + '<image href="https://example.com/a.png"/></svg>')
    assert "the attribute onload on <svg> isn't allowed" in refused(tmp_path, svg=SVG.replace("<svg ", '<svg onload="alert(1)" ', 1))
    assert "the attribute style" in refused(tmp_path, svg=SVG.replace("<rect ", '<rect style="fill:url(x)" ', 1))
    assert "points at something outside the drawing" in refused(tmp_path, svg=SVG.replace('fill="none"', 'fill="url(https://example.com/x)"'))
    assert "DOCTYPE or entity" in refused(tmp_path, svg='<!DOCTYPE svg [<!ENTITY a "aaaa">]>' + SVG)
    assert "processing instruction" in refused(tmp_path, svg='<?xml-stylesheet type="text/css" href="https://example.com/x.css"?>' + SVG)
    assert "dimension 3 isn't labelled" in refused(tmp_path, dimensions=[*DIMENSIONS, {"number": 3, "what": "the hole"}])
    assert "at least one of `dimensions`" in refused(tmp_path, dimensions=[])


def test_a_refused_sketch_isnt_replayed_as_the_persons_answer(tmp_path):
    first = live.LivePerson(ask=lambda question: "40 mm", folder=tmp_path)
    first.measure("plate", "length", sketch={"svg": "<svg>", "dimensions": DIMENSIONS})
    first.measure("plate", "length")
    again = live.LivePerson(live.Answers(measures=first.measured))
    assert again.measure("plate", "length") == "40 mm"


def test_the_evals_conditions_dont_offer_or_read_a_sketch():
    """Saved results stay comparable: every eval condition's measure tool is what it was, and a sketch sent anyway
    is ignored, as any unknown argument is."""
    measure = {"type": "function", "function": {
        "name": "measure", "description": "Ask the person to measure one of their own things. They answer with what they measured, or say they can't.",
        "parameters": {"type": "object", "properties": {
            "item": {"type": "string", "description": "What to measure, e.g. 'desk'"},
            "what": {"type": "string", "description": "Which dimension, e.g. 'thickness at the edge'"}},
            "required": ["item", "what"]}}}
    for condition in agent.CONDITIONS:
        offered = agent.tools(condition)
        assert offered[0] == measure and offered == agent.tools(condition, False, False)
        assert "sketch" not in json.dumps(offered)
    live_measure = agent.tools("can_ask", sketch=True)[0]["function"]["parameters"]
    assert live_measure["properties"]["sketch"] == sketch.SCHEMA and live_measure["required"] == ["item", "what"]
    assert agent.tools("can_ask", sketch=True)[1:] == agent.tools("can_ask")[1:]

    chat, _ = scripted([measure_with(), hand_in()])
    record, _, _ = agent.run_trial(tasks.load("m5-spacer"), "fake", chat=chat)
    assert record.measures[0].reply == NO_ANSWER


def test_what_is_saved_is_the_checked_drawing_not_the_text_that_was_sent(tmp_path):
    """An XML declaration is allowed, and a comment is dropped: the file the browser opens holds only checked elements."""
    sent = '<?xml version="1.0"?>' + SVG.replace("<rect ", "<!-- <script>alert(1)</script> --><rect ", 1)
    person = live.LivePerson(ask=lambda question: BY_NUMBER, folder=tmp_path)
    assert person.measure("plate", "the numbered dimensions", sketch={"svg": sent, "dimensions": DIMENSIONS}) == BY_NUMBER
    assert (tmp_path / "sketches/1.svg").read_text() == CHECKED_SVG


# --- replaying a session: an answer is only for what it was given about --------------------------------------------

def pieces(od):
    design = spacer()
    design["params"]["od"]["value"] = od
    return submission.Submission.model_validate({"task": "t", "params": design["params"],
                                                 "parts": [{**part, "id": "spacer_test", "role": "coupon"} for part in design["parts"]]})


def test_a_test_prints_answer_is_replayed_only_for_the_same_shape(tmp_path):
    task = tasks.from_request(REQUEST)
    first = live.LiveTestPrints(tmp_path / "first", ask=lambda question: CAME_OUT)
    first(task, pieces(12))
    answers = live.Answers(test_prints=first.printed)

    same = live.LiveTestPrints(tmp_path / "same", answers)(task, pieces(12))
    assert [(line.text, line.basis) for line in same["spacer_test"]] == [(CAME_OUT, "live answer")]
    # the same part id, 2 mm wider: nobody printed that, so with nobody to ask it wasn't printed
    wider = live.LiveTestPrints(tmp_path / "wider", answers)(task, pieces(14))
    assert [(line.text, line.basis) for line in wider["spacer_test"]] == [(live.DIDNT_PRINT, agent.NOT_PRINTED_BASIS)]
    # an answers file written by hand has no shapes, and the part id decides
    by_hand = live.Answers(test_prints=[live.PiecesPrinted(pieces={"spacer_test": CAME_OUT})])
    assert live.LiveTestPrints(tmp_path / "hand", by_hand)(task, pieces(14))["spacer_test"][0].text == CAME_OUT


def test_a_sketched_answer_is_replayed_only_for_the_same_sketch(tmp_path):
    first = live.LivePerson(ask=lambda question: BY_NUMBER, folder=tmp_path)
    first.measure("plate", "the numbered dimensions", sketch={"svg": SVG, "dimensions": DIMENSIONS})
    again = live.LivePerson(live.Answers(measures=first.measured))
    assert again.measure("plate", "the numbered dimensions", sketch={"svg": SVG, "dimensions": DIMENSIONS}) == BY_NUMBER
    swapped = [{"number": 1, "what": "the plate's thickness"}, {"number": 2, "what": "the plate's length"}]
    assert again.measure("plate", "the numbered dimensions", sketch={"svg": SVG, "dimensions": swapped}) == NO_ANSWER
    assert again.measure("plate", "the numbered dimensions") == NO_ANSWER  # an answer by number, with no sketch to number


def test_what_nobody_answered_is_asked_again_on_a_rerun(tmp_path):
    task = tasks.from_request(REQUEST)
    alone = live.LivePerson()
    alone.measure("the bolt", "length")
    unprinted = live.LiveTestPrints(tmp_path / "alone")
    unprinted(task, pieces(12))
    answers = live.Answers(measures=alone.measured, test_prints=unprinted.printed)

    ask, asked = person_saying("30 mm", CAME_OUT)
    assert live.LivePerson(answers, ask).measure("the bolt", "length") == "30 mm"
    assert live.LiveTestPrints(tmp_path / "again", answers, ask)(task, pieces(12))["spacer_test"][0].text == CAME_OUT
    assert len(asked) == 2


def test_a_reply_about_pieces_nobody_printed_doesnt_say_they_were_printed(tmp_path):
    chat, _ = scripted(a_session())
    record, folder, _ = live_command.run(tasks.from_request(REQUEST), "fake", tmp_path, chat=chat)  # nobody at the terminal
    reply = tool_replies(folder)["print_test"]
    assert reply == f"{agent.NONE_PRINTED}\nspacer_test:\n- {live.DIDNT_PRINT}" and not reply.startswith(agent.TEST_PRINTED)
    transcript = json.loads((folder / "transcript.json").read_text())
    assert agent.asked_test_prints(tasks.OWN_REQUEST, transcript) == []  # so it isn't counted as a printed test


def test_an_interrupted_session_keeps_what_the_person_answered(tmp_path):
    chat, _ = scripted(a_session())
    answers = iter([TUBE])

    def ask(question):
        try:
            return next(answers)
        except StopIteration:
            raise KeyboardInterrupt from None  # Ctrl-C at the second question
    task = tasks.from_request(REQUEST)
    with pytest.raises(KeyboardInterrupt):
        live_command.run(task, "fake", tmp_path, ask=ask, chat=chat)
    kept = live.load_answers(next(tmp_path.rglob(live.SESSION_FILE)))
    assert [(told.item, told.answer) for told in kept.measures] == [("gap between the plates", TUBE)]
