"""The Estoa light's box: the reference passes every check, versions of the real Estoa mistakes fail the
check aimed at them and no other, simple reward hacks fail, and designs unlike the reference still pass.
Not graded (ok = None) is kept apart from failed: it's what a check says when no record can decide."""
import json
import re

import pytest
from pydantic import ValidationError

from pbe.parts import submission
from pbe.runner import agent, tasks
from pbe.runner.measure import Person

from helpers import checked, failed, grade, not_graded, not_passing

TASK = tasks.load("estoa-light")
REFERENCE = TASK.reference


def screws_of(sub, item):
    return [screw for screw in sub.assembly.screws if screw.item == item]


def placement_of(sub, item):
    return next(placement for placement in sub.assembly.items if placement.item == item)


def design(screw_refs=None, **params):
    """The reference, changed only where a test says: param values, and which screw a hardware id is."""
    sub = submission.parse(REFERENCE)
    for name, value in params.items():
        sub.params[name].value = value
    for item_id, ref in (screw_refs or {}).items():
        next(item for item in sub.hardware if item.id == item_id).ref = ref
    return sub


def disk_holes_apart(spacing, template=False):
    """The disk's holes guessed `spacing` apart, as the Estoa agent read them from a photo: plate holes and screws
    both. Without `template`, the design doesn't check them against the disk first."""
    sub = design(disk_hole_x=spacing / 2)
    if not template:
        sub.criteria = [criterion for criterion in sub.criteria if criterion.check.method != "template"]
    for screw, side in zip(screws_of(sub, "disk-screw"), (1, -1)):
        screw.head = (screw.head[0], side * spacing / 2, screw.head[2])
    return checked(sub)


def perfboard_under_the_disk_screws(disk_screw):
    """The perfboard moved across so the ESP32 sits right under one of the disk's screws."""
    sub = design(screw_refs={"disk-screw": disk_screw}, pb_x=0)
    placement_of(sub, "perfboard").origin = (0, -38, 10)
    for screw in screws_of(sub, "pb-screw"):
        screw.head = (screw.head[0] + 35, screw.head[1], screw.head[2])
    return checked(sub)


def without_nuts():
    sub = design()
    sub.hardware = [item for item in sub.hardware if item.id != "disk-nut"]
    for step in sub.manual:
        step.hardware = [item for item in step.hardware if item != "disk-nut"]
    return checked(sub)


def boss_over_the_esp32(depth):
    """A block standing `depth` mm in from the front plate's inside, right over the ESP32."""
    sub = design()
    front = next(part for part in sub.parts if part.id == "front")
    old = "    return plate.cut(wires)\n"
    assert front.code.count(old) == 1
    front.code = front.code.replace(old, f"    boss = cq.Workplane(\"XY\").workplane(offset=p.plate).center(35, -38).rect(10, 30).extrude({depth})\n"
                                         "    return plate.cut(wires).union(boss)\n")
    return checked(sub)


def socket_set_back(extra, **params):
    """The ESP32's port moved `extra` mm further into the box (or out, if negative), so the opening in the wall
    stands that far out from it, as Estoa's did behind its recess."""
    sub = design(port_in=2 + extra, **params)
    port = placement_of(sub, "esp32")
    port.origin = (port.origin[0], port.origin[1] + extra, port.origin[2])
    return checked(sub)


def corner_posts(size):
    """The front plate's insert posts drawn `size` mm square, with the plate's screws moved to their new centres."""
    sub = design(corner_post=size)
    corner = 160 / 2 - 3 - size / 2
    for screw in screws_of(sub, "plate-screw"):
        screw.head = (corner * (1 if screw.head[0] > 0 else -1), corner * (1 if screw.head[1] > 0 else -1), screw.head[2])
    return checked(sub)


TEST_PRINT = """
def build(p):
    plate = cq.Workplane("XY").rect(60, 20).extrude(p.test_print_t)
    for x, width in ((-18, 12), (0, 13), (18, 14)):
        plate = plate.cut(cq.Workplane("XY").center(x, 0).slot2D(width, p.usb_h, 0).extrude(p.test_print_t))
    return plate
"""


def with_opening_test_print(sub, thickness=3.0):
    """A test print of three openings, 12, 13 and 14 mm wide, that the manual has the person try the plug in first."""
    sub.params["test_print_t"] = submission.Param(value=thickness, kind="design", source="design", note="the test print's wall")
    sub.parts.append(submission.Part(id="usb-test-print", role="coupon", material="PLA", code=TEST_PRINT,
                                     print_orientation="flat", use_orientation="held in the hand"))
    sub.manual.insert(0, submission.Step(n="0", parts=["usb-test-print"], text=(
        "Print usb-test-print first and push the charger's plug through each opening; set usb_w to the narrowest it seats in.")))
    return checked(sub)


def rectangular_opening(width, height):
    """The plug's opening cut square-cornered instead of as a slot."""
    sub = body_code('return cq.Workplane("XZ").slot2D(width, height, 0)', 'return cq.Workplane("XZ").rect(width, height)')
    sub.params["usb_w"].value, sub.params["usb_h"].value = width, height
    return checked(sub)


def screws_on_the_back():
    """Two socket head screws whose heads sit on the back, as Estoa's lid's button heads did (1.65 mm proud)."""
    sub = design()
    sub.hardware.append(submission.HardwareItem(id="back-screw", ref="ISO 4762 M3x8", qty=2))
    sub.assembly.screws += [submission.ScrewPlacement(item="back-screw", head=(side * 20, 60, 0), direction=(0, 0, 1)) for side in (1, -1)]
    return checked(sub)


def moved_item(item, origin=None, x_axis=None, z_axis=None):
    sub = design()
    placement = placement_of(sub, item)
    placement.origin = origin or placement.origin
    placement.x_axis = x_axis or placement.x_axis
    placement.z_axis = z_axis or placement.z_axis
    return checked(sub)


def hard_coded_disk_holes(sub):
    """The front plate's disk holes drawn at a fixed spot, so no param moves them."""
    front = next(part for part in sub.parts if part.id == "front")
    spot = f"side * {sub.params['disk_hole_x'].value}"
    assert front.code.count("side * p.disk_hole_x") == 2
    front.code = front.code.replace("side * p.disk_hole_x", spot)
    return checked(sub)


def body_code(old, new):
    return body_code_on(design(), old, new)


def body_code_on(sub, old, new):
    body = next(part for part in sub.parts if part.id == "body")
    assert body.code.count(old) == 1
    body.code = body.code.replace(old, new)
    return checked(sub)


def test_reference_passes_every_check(tmp_path):
    findings = grade(submission.parse(REFERENCE), tmp_path)
    assert all(f.ok is True for f in findings), not_passing(findings)


@pytest.mark.parametrize("sub, want_failed, want_not_graded", [
    # the real Estoa mistakes
    pytest.param(socket_set_back(4, usb_w=11.5), {"R3"}, set(), id="usb-opening-11.5-wide-set-back-from-the-port"),
    pytest.param(design(key_up=-1), {"R6"}, set(), id="keyholes-point-down"),
    pytest.param(disk_holes_apart(30), {"R1"}, {"R2"}, id="disk-holes-30-apart"),
    pytest.param(disk_holes_apart(30, template=True), set(), {"R2"}, id="disk-holes-30-apart-but-checked-on-a-template"),
    pytest.param(hard_coded_disk_holes(disk_holes_apart(30, template=True)), {"R1"}, {"R2"}, id="template-but-the-holes-are-hard-coded"),
    pytest.param(corner_posts(7.5), {"R4"}, set(), id="insert-posts-under-8"),
    pytest.param(perfboard_under_the_disk_screws("ISO 4762 M3x20"), {"R2"}, set(), id="m3x20-reaches-the-esp32"),
    pytest.param(screws_on_the_back(), {"R7"}, set(), id="screw-heads-proud-of-the-back"),
    # more ways to get them wrong
    pytest.param(without_nuts(), {"R2"}, set(), id="clearance-holes-and-no-nut"),
    pytest.param(perfboard_under_the_disk_screws("ISO 4762 M3x30"), {"R2"}, set(), id="m3x30-runs-right-through-the-esp32"),
    pytest.param(design(screw_refs={"disk-nut": "ISO 4032 M5"}), {"R2"}, set(), id="m5-nuts-on-m3-disk-screws"),
    pytest.param(moved_item("esp32", x_axis=(0, 0, -1), z_axis=(0, -1, 0)), {"R3"}, set(), id="port-facing-the-wall"),
    pytest.param(boss_over_the_esp32(10), {"R5"}, set(), id="front-too-close-to-the-esp32"),
    pytest.param(boss_over_the_esp32(6), set(), {"R5"}, id="front-close-enough-to-touch-the-esp32s-top"),
    pytest.param(disk_holes_apart(33.0), set(), {"R1"}, id="disk-holes-33-between-the-readings"),
    pytest.param(with_opening_test_print(socket_set_back(4, usb_w=11.5), thickness=1.5), {"R3"}, set(), id="opening-test-print-thinner-than-the-wall"),
    pytest.param(with_opening_test_print(body_code_on(socket_set_back(4, usb_w=11.5), "stadium(p.usb_w, p.usb_h)", "stadium(11.5, p.usb_h)")),
                 {"R3"}, set(), id="opening-test-print-but-the-width-is-hard-coded"),
    pytest.param(perfboard_under_the_disk_screws("ISO 4762 M3x12"), set(), {"R2"}, id="screw-tip-over-the-perfboard"),
    pytest.param(design(usb_w=13, usb_h=8.5), set(), {"R3"}, id="usb-opening-13-between-records"),
    pytest.param(rectangular_opening(12, 7.5), set(), {"R3"}, id="usb-opening-12-under-the-largest-plug-head"),
    pytest.param(rectangular_opening(13, 7.5), set(), {"R3"}, id="usb-opening-holds-the-bare-plug-head-only"),
    pytest.param(socket_set_back(-1.5, usb_w=11.5), set(), {"R3"}, id="small-opening-in-a-thin-wall-at-the-port"),
    pytest.param(design(key_entry=9.5), set(), {"R6"}, id="keyhole-entry-9.5-never-hung"),
    pytest.param(corner_posts(10), set(), {"R4"}, id="insert-posts-10-between-records"),
])
def test_wrong_or_undecided_designs(tmp_path, sub, want_failed, want_not_graded):
    findings = grade(sub, tmp_path)
    assert failed(findings) == want_failed, [f for f in findings if f.ok is False]
    assert not_graded(findings) == want_not_graded, [f for f in findings if f.ok is None]


@pytest.mark.parametrize("sub, want_failed, want_not_graded", [
    pytest.param(moved_item("perfboard", origin=(0, -200, 10)), {"R5"}, set(), id="perfboard-declared-outside-the-box"),
    pytest.param(moved_item("esp32", origin=(-35, -95, 24.14)), {"R3"}, set(), id="port-declared-outside-the-box"),
    pytest.param(moved_item("disk", origin=(0, 0, 56)), {"R1"}, {"R2"}, id="disk-declared-floating-in-front"),
    pytest.param(body_code("    for side in (-1, 1):\n        body = body.cut(keyhole(p, side))\n", ""), {"R6"}, set(), id="no-keyholes"),
    pytest.param(moved_item("esp32", origin=(-35, -78.5, 12)), {"R3"}, set(), id="port-declared-inside-the-wall"),
])
def test_reward_hacks_fail(tmp_path, sub, want_failed, want_not_graded):
    findings = grade(sub, tmp_path)
    assert failed(findings) == want_failed, [f for f in findings if f.ok is False]
    assert not_graded(findings) == want_not_graded, [f for f in findings if f.ok is None]


@pytest.mark.parametrize("sub", [
    pytest.param(design(usb_w=16, usb_h=10), id="roomier-usb-opening"),
    pytest.param(design(key_slot=5.5, key_entry=11), id="other-keyhole-sizes"),
    pytest.param(design(screw_refs={"disk-screw": "ISO 4762 M3x20"}), id="m3x20-disk-screws-hit-nothing"),
    pytest.param(design(disk_hole_d=3.6), id="roomier-disk-holes"),
    pytest.param(socket_set_back(4), id="port-set-back-behind-a-roomy-opening"),
    pytest.param(with_opening_test_print(socket_set_back(4, usb_w=11.5)), id="narrow-opening-but-a-test-print-finds-the-size"),
])
def test_other_correct_designs_pass(tmp_path, sub):
    findings = grade(sub, tmp_path)
    assert all(f.ok is True for f in findings), not_passing(findings)


def inserts_behind_the_disk(template):
    sub = design(disk_hole_d=4.3, nut_pockets=0)
    if not template:
        sub.criteria = [criterion for criterion in sub.criteria if criterion.check.method != "template"]
    return checked(sub)


@pytest.mark.parametrize("template, want", [(False, None), (True, True)], ids=["no-template", "checked-on-a-template"])
def test_inserts_behind_the_disk_need_a_template(tmp_path, template, want):
    # an insert holds a screw at one spot, and Dan's readings put each hole within half a millimetre: no record
    # says whether the screw meets the disk's hole, unless a template checks the pattern first
    findings = {f.check: f.ok for f in grade(inserts_behind_the_disk(template), tmp_path)}
    assert findings["R1"] is want
    assert findings["R2"] is True and findings["R4"] is True


def inserts_behind_a_skin(skin):
    """Sonnet's layout in pilot-estoa: the disk's screws pass a clearance hole in a `skin` mm skin, then thread
    into inserts pressed in from the inside, in place of the reference's nuts."""
    sub = design()
    sub.hardware = [item for item in sub.hardware if item.id != "disk-nut"]
    for step in sub.manual:
        step.hardware = [item for item in step.hardware if item != "disk-nut"]
    front = next(part for part in sub.parts if part.id == "front")
    for old, new in ((".workplane(offset=p.plate - p.nut_deep)", f".workplane(offset={skin})"),
                     (".polygon(6, p.nut_af / 0.8660254).extrude(p.nut_deep)", f".circle(p.insert_hole / 2).extrude(p.plate - {skin})")):
        assert front.code.count(old) == 1
        front.code = front.code.replace(old, new)
    return checked(sub)


@pytest.mark.parametrize("skin, want", [(1.0, True), (3.0, False)], ids=["4-mm-of-insert", "2-mm-of-insert"])
def test_inserts_behind_a_skin_hold_if_long_enough(tmp_path, skin, want):
    # once failed R2 as "a clearance hole and no nut": the check read only the hole at the surface
    findings = {f.check: f for f in grade(inserts_behind_a_skin(skin), tmp_path)}
    assert findings["R2"].ok is want, findings["R2"].detail


def blind_inserts_behind_the_disk(template):
    """Opus's layout in pilot-estoa: inserts in blind pockets straight behind the disk, 0.6 mm of plastic under
    each. The reference's M3 x 10s reach past that."""
    sub = inserts_behind_the_disk(template)
    front = next(part for part in sub.parts if part.id == "front")
    old = ".circle(p.disk_hole_d / 2).extrude(p.plate)"
    assert front.code.count(old) == 1
    front.code = front.code.replace(old, ".circle(p.disk_hole_d / 2).extrude(p.plate - 0.6)")
    return checked(sub)


def with_a_sliver_beside_the_disk_holes(sub):
    """Haiku's front in pilot-estoa had a 0.36 mm gap 4 mm from each insert pocket, between a boss and a wall."""
    front = next(part for part in sub.parts if part.id == "front")
    old = "    return plate.cut(wires)\n"
    assert front.code.count(old) == 1
    front.code = front.code.replace(old, "    for side in (-1, 1):\n"
                                         "        plate = plate.cut(cq.Workplane(\"XY\").center(0, side * (p.disk_hole_x + 4.2)).rect(6, 0.36).extrude(p.plate))\n"
                                         + old)
    return checked(sub)


@pytest.mark.parametrize("template, want_r1", [(False, None), (True, True)], ids=["no-template", "checked-on-a-template"])
def test_blind_inserts_beside_a_sliver(tmp_path, template, want_r1):
    findings = {f.check: f for f in grade(with_a_sliver_beside_the_disk_holes(blind_inserts_behind_the_disk(template)), tmp_path)}
    assert findings["R1"].ok is want_r1, findings["R1"].detail


@pytest.mark.parametrize("template, want_r1", [(False, None), (True, True)], ids=["no-template", "checked-on-a-template"])
def test_blind_inserts_are_read_to_their_bottom(tmp_path, template, want_r1):
    # R1 once read the pocket's solid bottom as "no room for the screw" and failed it as a miss by inf mm
    findings = {f.check: f for f in grade(blind_inserts_behind_the_disk(template), tmp_path)}
    assert findings["R1"].ok is want_r1, findings["R1"].detail
    assert findings["R2"].ok is False and "bottoms out" in findings["R2"].detail, findings["R2"].detail


def test_a_disk_never_placed_is_not_graded_rather_than_a_crash(tmp_path):
    # DeepSeek in pilot-estoa listed none of the person's parts, so its assembly placed none of them
    sub = design()
    sub.hardware = [item for item in sub.hardware if item.ref != "own:led-disk"]
    sub.assembly.items = [placement for placement in sub.assembly.items if placement.item != "disk"]
    for step in sub.manual:
        step.hardware = [item for item in step.hardware if item != "disk"]
    findings = {f.check: f for f in grade(checked(sub), tmp_path)}
    assert findings["R2"].ok is None and "isn't placed" in findings["R2"].detail, findings["R2"].detail


def test_a_square_ended_slot_reads_straight_up(tmp_path):
    # Sonnet's keyholes in pilot-estoa had square-ended slots; R6 once took the slot's direction towards its far
    # corner, read it 11 degrees off, and probed the lip beside the pocket behind it
    sub = design()
    body = next(part for part in sub.parts if part.id == "body")
    old = ".slot2D(abs(run) + p.key_slot, p.key_slot, 90)"
    assert body.code.count(old) == 1
    body.code = body.code.replace(old, ".rect(p.key_slot, abs(run) + p.key_slot)")
    findings = {f.check: f for f in grade(checked(sub), tmp_path)}
    assert findings["R6"].ok is True and "0 degrees from up" in findings["R6"].detail, findings["R6"].detail


def test_a_big_opening_in_one_wall_still_encloses_the_board(tmp_path):
    # Gemini 4 Argon's 40 mm USB cutout in pilot-estoa (here 40 x 26, low enough to reach the probe): R5 once
    # probed only from the board's centre, went out through the opening and called the board outside the box
    findings = {f.check: f for f in grade(design(usb_w=40, usb_h=26), tmp_path)}
    assert findings["R5"].ok is True, findings["R5"].detail


def test_an_assumption_grades_only_what_the_records_leave_undecided(tmp_path):
    from pbe.assumptions import with_assumption
    from pbe.graders.requirements import _run_grader
    from pbe.parts.build import build_parts
    sub = inserts_behind_the_disk(template=False)  # inserts hold the screws at one spot: R1 not graded on the records
    findings = {f.check: f.ok for f in grade(sub, tmp_path)}
    assert findings["R1"] is None
    built = build_parts(sub, tmp_path / "assumed")
    r1 = next(requirement for requirement in TASK.requirements if requirement.id == "R1")
    ok, detail = _run_grader(with_assumption(r1), sub, built)  # the holes at the middle of Dan's readings
    assert ok is True, detail
    assert all(requirement.assume.source and requirement.assume.text for requirement in TASK.requirements if requirement.assume)


def test_wall_screws_in_the_keyholes_are_not_proud(tmp_path):
    # GPT 6.1 Sol t2 in pilot-estoa declared its two wall screws; R7 once read them as standing 17 mm out of the back
    sub = design()
    sub.hardware.append(submission.HardwareItem(id="wall-screw", ref="ISO 4762 M4x20", qty=2))
    sub.assembly.screws += [submission.ScrewPlacement(item="wall-screw", head=(side * 50, 46, 3.5), direction=(0, 0, -1))
                            for side in (-1, 1)]
    findings = {f.check: f for f in grade(checked(sub), tmp_path)}
    assert findings["R7"].ok is True, findings["R7"].detail


def test_a_captive_nut_in_a_slot_holds(tmp_path):
    # Gemini 4 Argon t3 in pilot-estoa slid its nuts into slots across its pillars, partway down the bore; R2 once
    # looked for a nut only past the end of the plastic and failed it
    sub = design(nut_pockets=0)
    front = next(part for part in sub.parts if part.id == "front")
    old = "    return plate.cut(wires)\n"
    assert front.code.count(old) == 1
    front.code = front.code.replace(old, "    for side in (-1, 1):\n"
                                         "        slot = cq.Workplane(\"XY\").workplane(offset=1.0).center(7, side * p.disk_hole_x).rect(20, 5.75).extrude(2.8)\n"
                                         "        plate = plate.cut(slot)\n" + old)
    findings = {f.check: f for f in grade(checked(sub), tmp_path)}
    assert findings["R2"].ok is True and "captive nut" in findings["R2"].detail, findings["R2"].detail


def test_the_person_answers_what_the_records_say():
    person = Person(TASK.hidden_facts)
    holes = person.measure("LED disk", "mounting holes")
    assert "3.3" in holes
    assert "30.2" in person.measure("disk", "distance between the holes")
    assert "3 o'clock" in person.measure("disk", "where are the holes")
    assert "102.54" in person.measure("disk", "hole to the edge")
    assert "can't measure" in person.measure("disk", "thickness")
    # pilot-estoa: Sonnet's wording for the wall screws, which once matched nothing
    assert "9 mm" in person.measure("screws you will hang it on", "head diameter, head thickness, shank diameter")
    assert "can't measure" in person.measure("led disk", "outer diameter")
    assert "12.54" in person.measure("esp32", "usb port height")
    assert "4.80" in person.measure("esp32", "usb port")
    assert "16 mm" in person.measure("esp32", "height above the perfboard")
    assert "2.4 mm" in person.measure("perfboard", "corner holes")
    assert "3.5 mm" in person.measure("wall screws", "how far they stick out")


# --- the format: only this task gets `assembly`, and the other tasks keep theirs exactly ---

def test_only_a_task_that_asks_gets_assembly_in_its_schema():
    plain = agent.tools("can_ask")
    assert plain == agent.tools("can_ask", False)
    design_schema = next(tool for tool in plain if tool["function"]["name"] == "submit_design")["function"]["parameters"]
    assert "assembly" not in design_schema["properties"]
    with_assembly = agent.tools("can_ask", TASK.format.assembly)
    schema = next(tool for tool in with_assembly if tool["function"]["name"] == "submit_design")["function"]["parameters"]
    assert "assembly" in schema["required"]
    assert set(schema["properties"]["assembly"]["properties"]) == {"parts", "items", "screws"}
    assert {tool["function"]["name"] for tool in with_assembly} == {tool["function"]["name"] for tool in plain}


def test_only_this_tasks_prompt_lists_the_own_parts():
    prompt = agent.system_prompt(8, task_format=TASK.format)
    assert "## Their own parts" in prompt and "own:led-disk" in prompt and "the side without LEDs" in prompt
    assert "`assembly`" in prompt
    assert prompt.replace(agent.ASSEMBLY_RULE, "").count("own:") >= 4
    other = tasks.load("tripod-plate")
    assert agent.system_prompt(8, task_format=other.format) == agent.system_prompt(8)


def test_no_unmeasured_value_is_in_the_prompt():
    # the prompt says what the person knows without measuring; Dan's readings come only from measure
    prompt = agent.system_prompt(8, task_format=TASK.format)
    for reading in ["3.3", "30.2", "102.54", "13.5", "21.76", "16.75", "33.5", "242"]:
        assert reading not in prompt


def scripted(arguments):
    """A fake chat that submits `arguments` once, and records the submit_design schema it was offered."""
    offered = []

    def chat(model, messages, tools=None, max_tokens=None):
        offered.append(next(tool for tool in tools if tool["function"]["name"] == "submit_design")["function"]["parameters"])
        call = {"id": "a", "type": "function", "function": {"name": "submit_design", "arguments": json.dumps(arguments)}}
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [call]}}], "usage": {"cost": 0}}
    chat.offered = offered
    return chat


def test_this_task_sends_a_design_without_an_assembly_back():
    arguments = submission.parse(REFERENCE).dump()
    arguments.pop("assembly")
    arguments.pop("task")
    chat = scripted(arguments)
    record, messages, sub = agent.run_trial(TASK, "fake", max_turns=1, chat=chat)
    assert sub is None and record.repairs == 1
    assert "assembly is required" in messages[-1]["content"]
    assert "assembly" in chat.offered[0]["required"]


def test_another_task_ignores_an_assembly_it_never_asked_for():
    tripod = tasks.load("tripod-plate")
    arguments = submission.parse(tripod.reference).dump()
    arguments.pop("task")
    arguments["assembly"] = {"parts": [], "items": []}
    chat = scripted(arguments)
    record, _, sub = agent.run_trial(tripod, "fake", max_turns=1, chat=chat)
    assert sub is not None and sub.assembly is None and record.repairs == 0
    assert "assembly" not in sub.dump() and "assembly" not in chat.offered[0]["properties"]


@pytest.mark.parametrize("change, message", [
    (lambda sub: sub.assembly.parts.pop(), "place final part front exactly once"),
    (lambda sub: sub.assembly.screws.pop(), "give each of the 4 pb-screw screw(s) a place"),
    (lambda sub: sub.assembly.items.append(submission.ItemPlacement(item="disk-nut", origin=(0, 0, 0), x_axis=(1, 0, 0), z_axis=(0, 0, 1))),
     "disk-nut has no frame to place"),
], ids=["a-part-not-placed", "a-screw-not-placed", "a-nut-placed"])
def test_an_incomplete_assembly_goes_back_for_repair(change, message):
    sub = submission.parse(REFERENCE)
    change(sub)
    with pytest.raises(ValidationError, match=re.escape(message)):
        checked(sub)


def test_a_design_that_leaves_out_the_persons_parts_goes_back():
    # DeepSeek in pilot-estoa listed none of them, twice, so no check could read where the boards went
    tools = agent.TrialTools(TASK, Person(TASK.hidden_facts))
    whole = submission.parse(REFERENCE).dump()
    assert tools.submit_design(whole) == "Received."
    without_disk = {**whole, "hardware": [item for item in whole["hardware"] if item["ref"] != "own:led-disk"]}
    without_disk["assembly"] = {**whole["assembly"], "items": [p for p in whole["assembly"]["items"] if p["item"] != "disk"]}
    without_disk["manual"] = [{**step, "hardware": [h for h in step["hardware"] if h != "disk"]} for step in whole["manual"]]
    reply = agent.TrialTools(TASK, Person(TASK.hidden_facts)).submit_design(without_disk)
    assert "own:led-disk missing" in reply


def test_a_placement_has_to_be_square():
    with pytest.raises(ValidationError, match="right angles"):
        submission.Placement(origin=(0, 0, 0), x_axis=(1, 0, 0.5), z_axis=(0, 0, 1))


def test_own_parts_resolve_only_for_their_task():
    sub = submission.parse(REFERENCE)
    assert sub.resolved(sub.hardware[0])["kind"] == "board"
    with pytest.raises(ValidationError, match="own:led-disk"):
        submission.Submission.model_validate({**sub.dump(), "task": "tripod-plate", "assembly": None})


def inserts_in_a_thin_plate(nut_deep):
    """Inserts behind the disk, checked on a template, with a pocket on the inside that leaves only
    5 - `nut_deep` mm of plastic around each insert: the thread is no longer than that."""
    sub = design(disk_hole_d=4.3, nut_pockets=1, nut_deep=nut_deep)
    return checked(sub)


@pytest.mark.parametrize("nut_deep, want", [(1.5, True), (2.5, False)], ids=["3.5-mm-of-plastic", "2.5-mm-of-plastic"])
def test_thread_is_only_as_long_as_the_plastic_around_it(tmp_path, nut_deep, want):
    # Codex on #23: an M3 x 10 past a 2 mm board has 8 mm to spare, but holds only in the plastic around the insert
    findings = {f.check: f for f in grade(inserts_in_a_thin_plate(nut_deep), tmp_path)}
    assert findings["R2"].ok is want, findings["R2"].detail


def disk_low_over_the_esp32():
    """A window in the front plate over the perfboard, and the perfboard moved 10 mm across (clear of the port's
    opening) and raised 15 mm, so nothing printed stands over the ESP32 but the disk, 11 mm above the board,
    lower than the ESP32's 12.55."""
    sub = design()
    front = next(part for part in sub.parts if part.id == "front")
    old = "    return plate.cut(wires)\n"
    assert front.code.count(old) == 1
    front.code = front.code.replace(old, "    window = cq.Workplane(\"XY\").center(25, -38).rect(46, 66).extrude(p.plate)\n"
                                         "    return plate.cut(wires).cut(window)\n")
    placement = placement_of(sub, "perfboard")
    placement.origin = (placement.origin[0] + 10, placement.origin[1], placement.origin[2] + 15)
    for screw in screws_of(sub, "pb-screw"):
        screw.head = (screw.head[0] + 10, screw.head[1], screw.head[2] + 15)
    return checked(sub)


def test_the_disk_counts_as_a_ceiling_over_the_esp32(tmp_path):
    # Codex on #23: the clearance over the ESP32 read printed parts only, so a low disk over an open front passed
    findings = {f.check: f for f in grade(disk_low_over_the_esp32(), tmp_path)}
    assert findings["R5"].ok is False, findings["R5"].detail
    assert "disk" in findings["R5"].detail
