"""The decisions-API judge's records and helpers, without calling the API."""
import io
import json

from PIL import Image as PILImage

from pbe.judges import decisions as dz
from pbe.judges import transcripts


def test_request_has_the_documented_shape():
    request = dz.Request(model=dz.JEV, state=["text", dz.Image.jpeg(b"x")], questions={
        "a": dz.Noul(instructions="yes?"),
        "b": dz.Choice(instructions="which?", criteria={"red": "r", "blue": "b"}),
        "c": dz.Box(instructions="find it"),
    })
    body = json.loads(request.model_dump_json(exclude_none=True))
    assert body["questions"]["a"] == {"type": "noul", "instructions": "yes?"}
    assert body["questions"]["b"]["criteria"] == {"red": "r", "blue": "b"}
    assert body["questions"]["c"] == {"type": "box", "instructions": "find it"}
    assert body["state"][1] == {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,eA=="}}


def test_the_documented_response_parses():
    """The API reference's example answer, trimmed."""
    reply = {"answers": {"is_bug": {"noul": 0.96, "type": "noul"},
                         "team": {"choice": "payments", "confidence": 0.75, "type": "choice",
                                  "probabilities": {"account": 0, "frontend": 0.16, "payments": 0.84}},
                         "where": {"type": "box", "box": {"top": 0.1, "bottom": 0.3, "left": 0.2, "right": 0.6}}},
             "usage": {"cost": 0.000019992, "input_tokens": 476, "output_tokens": 70}}
    decision = dz.Decision(model="m", answers=reply["answers"], usage=reply["usage"], seconds=1.0)
    assert decision.answers["is_bug"].noul == 0.96
    assert decision.answers["team"].probabilities["payments"] == 0.84
    assert decision.answers["where"].box.centre() == (0.4, 0.2)
    assert decision.cost == 0.000019992


def _refused(budget, most):
    try:
        budget.reserve(most)
    except dz.OverBudget:
        return True
    return False


def test_budget_holds_room_for_calls_still_running():
    """Two calls side by side can't pass the cap together: the second is refused while the first is out."""
    budget = dz.Budget(0.01)
    budget.reserve(0.006)
    assert _refused(budget, 0.006)
    budget.settle(0.006, 0.001)  # the first came back costing far less than its bound
    assert not _refused(budget, 0.006)
    assert abs(budget.spent - 0.001) < 1e-12


def test_a_lost_connection_is_retried_then_reported(monkeypatch):
    import urllib.error
    calls = []

    def no_reply(body):
        calls.append(1)
        raise urllib.error.URLError("connection reset")

    monkeypatch.setattr(dz, "_post", no_reply)
    monkeypatch.setattr(dz.time, "sleep", lambda s: None)
    budget = dz.Budget(1.0)
    request = dz.Request(model=dz.JEV, state="x", questions={"a": dz.Noul(instructions="?")})
    try:
        dz.decide(request, budget, retries=2)
    except dz.DecisionsError as error:
        assert "no reply" in str(error) and len(calls) == 3
        assert budget.reserved == 0 and budget.spent == 0  # the reservation is released
        return
    raise AssertionError("no error")


def test_a_reply_without_answers_is_an_error(monkeypatch):
    monkeypatch.setattr(dz, "_post", lambda body: {"error": {"code": 400, "message": "bad"}})
    request = dz.Request(model=dz.JEV, state="x", questions={"a": dz.Noul(instructions="?")})
    try:
        dz.decide(request, dz.Budget(1.0))
    except dz.DecisionsError as error:
        assert error.status == 400
        return
    raise AssertionError("no error")


def test_a_thin_crop_stays_inside_jevs_image_limits():
    """A tall strip scaled up for Jev's 256 px floor passed its 1568 px ceiling (HTTP 400) before _widen."""
    photo = io.BytesIO()
    PILImage.new("RGB", (1125, 1500), "white").save(photo, format="JPEG")
    strip = dz.Edges(left=135 / 1125, right=230 / 1125, top=340 / 1500, bottom=830 / 1500)
    crop = PILImage.open(io.BytesIO(dz.crop_jpeg(photo.getvalue(), strip)))
    assert 256 <= min(crop.size) and max(crop.size) <= 1568


def _call(name, args):
    return {"type": "function", "function": {"name": name, "arguments": args}}


SESSION = [
    {"role": "system", "content": "the setup, the same for every trial"},
    {"role": "user", "content": "make me a box"},
    {"role": "assistant", "content": "", "reasoning": "private thoughts", "tool_calls": [
        _call("measure", '{"item": "USB-C charger plug", "what": "overmold width"}'),
        _call("measure", '{"item": "own:esp32", "what": "height of the centre of the port, with the ESP32 plugged in"}'),
        _call("print_test", '{"params": {}, "parts": "' + "x" * 3000 + ' keyhole slot"}'),
        _call("submit_design", '{"code": "' + "y" * 5000 + '"}'),
    ]},
    {"role": "tool", "content": "12 mm"},
]


def test_render_keeps_what_was_asked_and_tested_and_drops_the_rest():
    text = transcripts.render(SESSION)
    assert "the setup" not in text and "private thoughts" not in text
    assert "keyhole slot" in text                      # a test print is kept whole
    assert "more characters]" in text                  # a submitted design's code is cut
    assert text.count("y") < 3000


def _measure(item, what):
    return {"role": "assistant", "tool_calls": [_call("measure", json.dumps({"item": item, "what": what}))]}


def test_code_keys_skip_the_phrasings_the_hand_check_caught():
    """Each of these keyed yes in the 2026-11-12 run and was corrected by hand."""
    assert not transcripts.code_keys([_measure("own:esp32", "port height, with the ESP32 plugged in")], False)["plug_head"]
    assert not transcripts.code_keys([_measure("own:esp32", "width of the port mouth (the opening the plug goes into)")],
                                     False)["plug_head"]
    assert not transcripts.code_keys([_measure("own:led-disk", "input connector size and cable exit direction")],
                                     False)["plug_head"]
    assert not transcripts.code_keys([_measure("own:led-disk", "is its diameter over 20 cm, does it overhang a ruler")],
                                     False)["wall_screw_size"]
    assert transcripts.code_keys([_measure("perfboard", "maximum height of components on top")], False)["esp32_height"]
    assert transcripts.code_keys([_measure("USB-C charger cable plug", "width of the plastic grip")], False)["plug_head"]


def test_code_keys_read_the_tool_calls():
    keys = transcripts.code_keys(SESSION, can_test=True)
    assert keys["plug_head"] is True
    assert keys["esp32_height"] is False               # the port's height isn't how tall the ESP32 stands
    assert keys["keyhole_test"] is True and keys["any_test"] is True
    assert "keyhole_test" not in transcripts.code_keys(SESSION, can_test=False)


def test_failure_records_load_with_a_class_and_hold_one_out():
    from pathlib import Path
    from pbe.judges import failures
    seeds = Path(__file__).resolve().parents[1] / "seeds"
    classes = failures.load_classes(seeds)
    records = failures.load_failures(seeds)
    ids = {c.id for c in classes}
    assert len(classes) == 10 and all(r.cls in ids for r in records)
    # what went wrong and how it was found, never the fix, which would give the class away
    assert all([line.split(":")[0] for line in r.text.split("\n")] == ["What went wrong", "How it was found"]
               for r in records)
    options = failures.criteria(classes, leave_out="C4-tool-access")
    assert "C4-tool-access" not in options and failures.NONE in options and len(options) == 10


def test_reference_photos_never_include_the_cell_being_judged():
    from pbe.judges import photo_cells
    for cell in photo_cells.CELLS:
        refs = photo_cells.references_for(cell)
        assert all((r.photo, r.name) != (cell.photo, cell.name) for r in refs)
        assert [r.clean for r in refs] == [True, True, False, False]


def _transcript(folder, record_name="grades.json"):
    """A trial folder with two measure calls (one with no `what`), another tool call, and a trial record."""
    from pbe.runner.measure import NO_ANSWER
    messages = [
        {"role": "user", "content": "make me a wheel"},
        {"role": "assistant", "tool_calls": [
            {"id": "a", "type": "function", "function": {"name": "measure", "arguments": '{"item": "608 bearing", "what": "outer diameter"}'}},
            {"id": "b", "type": "function", "function": {"name": "submit_design", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "a", "content": "bearing od: about 22 mm (outside)"},
        {"role": "tool", "tool_call_id": "b", "content": "Received."},
        {"role": "assistant", "tool_calls": [
            {"id": "c", "type": "function", "function": {"name": "measure", "arguments": '{"item": "the shelf"}'}}]},
        {"role": "tool", "tool_call_id": "c", "content": NO_ANSWER},
    ]
    folder.mkdir(parents=True)
    (folder / "transcript.json").write_text(json.dumps(messages))
    (folder / record_name).write_text(json.dumps({"task": "bearing-wheel", "model": "x/designer"}))


def test_measure_calls_are_collected_with_their_replies_and_deduped(tmp_path):
    from pathlib import Path
    from pbe.judges import measure_calls
    runs = tmp_path / "runs"
    _transcript(runs / "r1/t1")
    _transcript(runs / "r2/t1/feedback", record_name="loop.json")
    (runs / "r3").mkdir(parents=True)
    (runs / "r3/transcript.json").write_text("[]")  # no trial record beside it: skipped
    tasks = Path(__file__).resolve().parents[1] / "tasks"
    requests = measure_calls.collect(runs, tasks)
    assert [(r.item, r.what) for r in requests] == [("608 bearing", "outer diameter"), ("the shelf", "")]
    bearing, shelf = requests
    assert [a.trial for a in bearing.asked] == ["r1/t1", "r2/t1/feedback"]
    assert bearing.asked[0].reply.startswith("bearing od") and bearing.answered_then
    assert bearing.lookup == ["bearing.od"]
    assert shelf.lookup == [] and not shelf.answered_then
    assert bearing.asked[0].contestant == "x/designer" and bearing.task == "bearing-wheel"


def test_a_family_variant_reads_the_familys_facts():
    from pathlib import Path
    from pbe.judges import measure_calls
    tasks = Path(__file__).resolve().parents[1] / "tasks"
    assert measure_calls.facts_for("nut-knob/M3", tasks) == {}
    assert "bearing" in measure_calls.facts_for("bearing-wheel", tasks)
