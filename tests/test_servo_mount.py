"""The servo mount: the reference passes every check, each real mistake fails the check aimed at it
and no other, reward hacks fail, other correct designs pass, and cases between the records come back
not graded (ok = None), which is never a pass."""
import re

from pbe.parts import submission
from pbe.runner import agent, measure, tasks

from helpers import checked, failed, grade, not_graded, not_passing

TASK = tasks.load("servo-mount")
REFERENCE = TASK.reference


def plate_code(channel="bottom", holes="round", cable_notch=0.0, flange=False, on_edge=False, open_under_tabs=False):
    """A plate like the reference's, changed in one way. The rib's room: a channel on the bottom or
    top face, a slot through the plate, a wide pocket, or none. Screw holes: round through holes,
    test print D's slots, or blind holes from the top."""
    lines = [
        "def build(p):",
        "    plate = cq.Workplane('XY').rect(p.plate_l, p.plate_w).extrude(p.plate_t)",
        "    plate = plate.cut(cq.Workplane('XY').rect(p.body_l + 2 * p.clearance, p.body_w + 2 * p.clearance).extrude(p.plate_t))",
    ]
    if open_under_tabs:
        lines.append("    plate = plate.cut(cq.Workplane('XY').rect(58, p.body_w + 2 * p.clearance).extrude(p.plate_t))")
    if cable_notch:
        lines.append(f"    plate = plate.cut(cq.Workplane('XY').center(p.body_l / 2 + p.clearance, 0).rect({2 * cable_notch}, 5).extrude(p.plate_t))")
    lines += [
        "    start, end = p.body_l / 2, 28",
        "    for side in (-1, 1):",
        "        x = side * (start + end) / 2",
    ]
    rooms = {
        "bottom": "cq.Workplane('XY').center(x, 0).rect(end - start, p.channel_w).extrude(p.channel_h)",
        "top": "cq.Workplane('XY').workplane(offset=p.plate_t - p.channel_h).center(x, 0).rect(end - start, p.channel_w).extrude(p.channel_h)",
        "through": "cq.Workplane('XY').center(x, 0).rect(end - start, p.channel_w).extrude(p.plate_t)",
        "pocket": "cq.Workplane('XY').center(x, 0).rect(end - start, 5).extrude(p.channel_h)",
    }
    if channel in rooms:
        lines.append(f"        plate = plate.cut({rooms[channel]})")
    if holes == "slots":  # test print D: one slot spans each tab's hole pair and runs 1 mm either way along the servo
        lines.append("        plate = plate.cut(cq.Workplane('XY').center(side * p.pitch / 2, 0).rect(3.0 + 2 * 1.0, 10 + 4.58).extrude(p.plate_t))")
    else:
        lines.append("        for row in (-1, 1):")
        depth, offset = ("p.plate_t", "0") if holes == "round" else ("2", "p.plate_t - 2")
        lines.append(f"            plate = plate.cut(cq.Workplane('XY').workplane(offset={offset}).center(side * p.pitch / 2, row * p.pair / 2)"
                     f".circle(p.screw_hole / 2).extrude({depth}))")
    if flange:  # a wall along one long edge, to fix the plate to something
        lines.append("    plate = plate.union(cq.Workplane('XY').center(0, p.plate_w / 2 + 2).rect(p.plate_l, 4).extrude(30))")
    if on_edge:
        lines.append("    plate = plate.rotate((0, 0, 0), (1, 0, 0), 90)")
    lines.append("    return plate")
    return "\n".join(lines) + "\n"


def design(code=None, hardware=None, **params):
    """The reference, changed only where a test says."""
    sub = submission.parse(REFERENCE)
    for name, value in params.items():
        sub.params[name].value = value
    if code is not None:
        sub.parts[0].code = code
    if hardware is not None:
        sub.hardware = hardware
        for step in sub.manual:
            step.hardware = [item for item in step.hardware if item in {entry.id for entry in hardware}]
    return checked(sub)


def screws(ref):
    return [submission.HardwareItem(id="screw", ref=ref, qty=4), submission.HardwareItem(id="nut", ref="ISO 4032 M3", qty=4)]


def only_failed(sub, tmp_path, checks):
    findings = grade(sub, tmp_path)
    assert failed(findings) == checks, not_passing(findings)
    return findings


def only_not_graded(sub, tmp_path, checks):
    findings = grade(sub, tmp_path)
    assert not failed(findings) and not_graded(findings) == checks, not_passing(findings)
    return findings


def all_pass(sub, tmp_path):
    findings = grade(sub, tmp_path)
    assert all(finding.ok is True for finding in findings), not_passing(findings)
    return findings


def detail(findings, check):
    return next(finding.detail for finding in findings if finding.check == check)


# --- the reference, and the same plate built other ways ---------------------------------------------

def test_reference_passes(tmp_path):
    all_pass(design(), tmp_path)


def test_the_reference_code_and_the_test_plate_agree(tmp_path):
    findings = all_pass(design(code=plate_code()), tmp_path)
    assert "from the low face: room for the rib" in detail(findings, "R3")


def test_channels_on_the_top_face_pass(tmp_path):
    findings = all_pass(design(code=plate_code(channel="top")), tmp_path)
    assert "from the high face: room for the rib" in detail(findings, "R3")


def test_a_slot_through_the_plate_for_the_rib_passes(tmp_path):
    all_pass(design(code=plate_code(channel="through")), tmp_path)


def test_a_wide_pocket_for_the_rib_passes(tmp_path):
    all_pass(design(code=plate_code(channel="pocket")), tmp_path)


def test_a_plate_with_a_wall_on_one_edge_passes(tmp_path):
    all_pass(design(code=plate_code(flange=True)), tmp_path)


def test_a_plate_printed_on_its_edge_passes_the_servo_checks(tmp_path):
    """On its edge, the channels' roofs are ledges no print has measured: that's the bridge check's call."""
    findings = grade(design(code=plate_code(on_edge=True)), tmp_path)
    assert not failed(findings) and not_graded(findings) == {"bridges"}, not_passing(findings)


def test_a_slot_through_a_plate_thinner_than_the_rib_passes_the_servo_checks(tmp_path):
    """Past the plate's far face there's nothing for the rib to hit (Codex's review of PR 47)."""
    findings = grade(design(code=plate_code(channel="through"), plate_t=1.6), tmp_path)
    assert {"R1", "R2", "R3"}.isdisjoint(failed(findings) | not_graded(findings)), not_passing(findings)


def test_walls_either_side_of_the_case_dont_shrink_the_cutout(tmp_path):
    """Two walls standing beside the case's long sides, shorter than the case: the gap between them isn't
    a second cutout (Opus 5.5's can_ask_datasheet plate read 1.29 mm a side too small before)."""
    walls = plate_code().replace("    return plate\n", "    for s in (1, -1):\n"
        "        plate = plate.union(cq.Workplane('XY').center(0, s * (p.body_w / 2 + p.clearance + 1.25)).rect(38, 2.5).extrude(10)"
        ".translate((0, 0, p.plate_t)))\n    return plate\n")
    findings = grade(design(code=walls), tmp_path)
    assert {"R1", "R2", "R3"}.isdisjoint(failed(findings) | not_graded(findings)), not_passing(findings)


def test_test_print_d_slots_take_the_screws(tmp_path):
    all_pass(design(code=plate_code(holes="slots")), tmp_path)


def test_holes_at_the_datasheet_spacing_pass(tmp_path):
    all_pass(design(pitch=49.5), tmp_path)


def test_m4_screws_pass(tmp_path):
    all_pass(design(hardware=screws("ISO 4762 M4x12"), screw_hole=4.4), tmp_path)


# --- real mistakes fail their own check and no other ---------------------------------------------------

def test_test_print_d_fails_only_flush(tmp_path):
    """Coupon D as printed: a plain cutout at 0.25 a side, slots for the tab screws, nothing for the rib."""
    findings = only_failed(design(code=plate_code(channel=None, holes="slots"), plate_t=3), tmp_path, {"R3"})
    assert not not_graded(findings)
    assert "stopped at its cable exit" in detail(findings, "R3")


def test_no_room_for_the_rib_fails_only_flush(tmp_path):
    only_failed(design(code=plate_code(channel=None)), tmp_path, {"R3"})


def test_a_channel_too_shallow_fails_only_flush(tmp_path):
    only_failed(design(channel_h=1.0), tmp_path, {"R3"})


def test_a_channel_narrower_than_the_rib_fails_only_flush(tmp_path):
    only_failed(design(channel_w=1.2), tmp_path, {"R3"})


def test_inside_edges_read_as_centres_fail_only_screws(tmp_path):
    only_failed(design(code=plate_code(), pitch=44.61), tmp_path, {"R2"})


def test_the_datasheet_body_fails_only_the_cutout(tmp_path):
    """The datasheet's 40.7 x 19.7 is narrower than this servo's 19.82."""
    findings = only_failed(design(body_l=40.7, body_w=19.7, clearance=0), tmp_path, {"R1"})
    assert not_graded(findings) == {"R2", "R3"}


def test_screws_too_big_for_the_tab_holes_fail_only_screws(tmp_path):
    only_failed(design(hardware=screws("ISO 4762 M5x12"), screw_hole=5.5), tmp_path, {"R2"})


# --- reward hacks fail ---------------------------------------------------------------------------------

def test_an_oversized_cutout_fails(tmp_path):
    findings = grade(design(clearance=8), tmp_path)
    assert {"R2", "R3"} <= failed(findings)


def test_nothing_under_the_tabs_fails(tmp_path):
    findings = grade(design(code=plate_code(open_under_tabs=True)), tmp_path)
    assert {"R2", "R3"} <= failed(findings)


def test_recessing_the_whole_tab_doesnt_clear_the_rib(tmp_path):
    """A pocket as wide as the tab moves where the tab meets the plate; the rib still hits the pocket's floor."""
    wide = plate_code(channel="top").replace("rect(end - start, p.channel_w)", "rect(end - start, 16)")
    findings = only_failed(design(code=wide), tmp_path, {"R3"})
    assert "has 0.0 mm of room" in detail(findings, "R3")


def test_tab_supports_at_two_heights_fail_flush(tmp_path):
    """One end's underside 1 mm lower, with the channel carried through it: the tabs are one flat
    flange, so one can't sit flush, however deep each channel is (Codex's review of PR 47)."""
    step = ("    plate = plate.union(cq.Workplane('XY').workplane(offset=-1).center(30, 0).rect(12, p.plate_w).extrude(1)"
            ".cut(cq.Workplane('XY').workplane(offset=-1).center(30, 0).rect(12, p.channel_w).extrude(1 + p.channel_h)))\n")
    stepped = plate_code().replace("    return plate\n", step + "    return plate\n")
    findings = grade(design(code=stepped), tmp_path)
    assert "R3" in failed(findings), not_passing(findings)
    assert "can't sit flush" in detail(findings, "R3")


RAIL = """
def build(p):
    return cq.Workplane('XY').rect(7, 60).extrude(6)
"""


def test_separate_rails_under_the_tabs_arent_graded(tmp_path):
    """A base plate with a wide opening and two rails printed separately for the tabs (GPT-6.1 Sol's
    all_given plate): without an assembly, where the rails go isn't known."""
    sub = design(code=plate_code(open_under_tabs=True))
    rails = [submission.Part(id=f"rail_{side}", role="final", material="PLA", print_orientation="flat",
                             use_orientation="under a tab", code=RAIL) for side in ("left", "right")]
    sub = checked(sub.model_copy(update={"parts": sub.parts + rails}))
    findings = grade(sub, tmp_path)
    assert {"R2", "R3"} <= not_graded(findings) and not {"R2", "R3"} & failed(findings), not_passing(findings)
    assert "where it goes isn't recorded" in detail(findings, "R3")


def test_a_rib_with_no_room_still_fails_with_another_part(tmp_path):
    sub = design(code=plate_code(channel=None))
    rail = submission.Part(id="rail", role="final", material="PLA", print_orientation="flat", use_orientation="spare", code=RAIL)
    findings = grade(checked(sub.model_copy(update={"parts": sub.parts + [rail]})), tmp_path)
    assert "R3" in failed(findings), not_passing(findings)


# --- between the records: not graded -------------------------------------------------------------------

def test_a_cutout_tighter_than_the_test_print_isnt_graded(tmp_path):
    only_not_graded(design(clearance=0.1), tmp_path, {"R1"})


def test_a_channel_with_less_than_the_bodys_clearance_isnt_graded(tmp_path):
    findings = only_not_graded(design(channel_w=1.7), tmp_path, {"R3"})
    assert "no relieved plate was printed" in detail(findings, "R3")


def test_a_plain_cutout_looser_than_the_test_print_isnt_graded(tmp_path):
    """Seated from above, the cable has to pass; nothing measured the cable exit, so a looser plain
    cutout can't be failed on it, though it still fails from underneath."""
    findings = only_not_graded(design(code=plate_code(channel=None), clearance=0.4), tmp_path, {"R3"})
    assert "the cable exit was never measured" in detail(findings, "R3")


def test_a_cable_notch_isnt_graded(tmp_path):
    only_not_graded(design(code=plate_code(channel=None, cable_notch=3)), tmp_path, {"R3"})


def test_holes_lined_up_with_only_one_record_arent_graded(tmp_path):
    findings = only_not_graded(design(pitch=51.3), tmp_path, {"R2"})
    assert "at 49.5 mm between the ends' holes: lands" in detail(findings, "R2")


def test_no_screws_isnt_graded(tmp_path):
    only_not_graded(design(hardware=[]), tmp_path, {"R2"})


def test_blind_holes_arent_graded(tmp_path):
    only_not_graded(design(code=plate_code(holes="blind")), tmp_path, {"R2"})


def test_a_final_part_that_doesnt_build_isnt_read(tmp_path):
    findings = grade(design(code="def build(p):\n    raise ValueError('no')\n"), tmp_path)
    assert failed(findings) == {"builds"}


# --- what the model is told ----------------------------------------------------------------------------

def test_the_prompt_leaves_out_the_servos_for_this_task_only():
    person = measure.Person(TASK.hidden_facts)
    system = agent.opening_messages(TASK, "can_ask", person, 8)[0]["content"]
    assert TASK.hardware_left_out == ("servos",)
    for word in ("servos", "MG996R", "tab_notch", "rib", "notch"):
        assert not re.search(rf"\b{word}\b", system), word
    assert "bearings:" in system and "ISO 4762" in system
    assert "tab_notch" in agent.system_prompt(8)  # every other task still sees the whole catalog


def test_can_ask_gets_the_request_only():
    person = measure.Person(TASK.hidden_facts)
    assert agent.first_message(TASK, "can_ask", person) == TASK.request
    assert "rib" not in TASK.request.lower() and "notch" not in TASK.request.lower()


def test_all_given_states_the_rib():
    person = measure.Person(TASK.hidden_facts)
    first = agent.first_message(TASK, "all_given", person)
    assert "servo rib height: 1.8 mm" in first and "servo rib width: 1.51 mm" in first


def test_the_person_answers_about_the_rib_when_asked_about_the_tabs_face():
    for what in ("rib", "is anything sticking up on the mounting face", "tab shape"):
        assert "rib height: 1.8 mm" in measure.Person(TASK.hidden_facts).measure("MG996R", what)


def test_asking_for_the_hole_spacing_doesnt_give_away_the_rib():
    reply = measure.Person(TASK.hidden_facts).measure("servo", "hole spacing")
    assert "44.61" in reply and "rib" not in reply


def test_the_person_says_where_the_cable_leaves_but_not_its_size():
    """The catalog's tab_shape note: a person looking at the servo would say where the cable comes out.
    Left out of the first run, where no model could learn it."""
    for item, what in (("servo", "where does the cable come out"), ("cable", "where does it exit"), ("wire", "exit")):
        reply = measure.Person(TASK.hidden_facts).measure(item, what)
        assert "below the tabs" in reply and "didn't measure its size" in reply, (item, what, reply)
    assert "below the tabs" in agent.first_message(TASK, "all_given", measure.Person(TASK.hidden_facts))


def test_what_was_never_measured_gets_no_answer():
    assert measure.Person(TASK.hidden_facts).measure("horn", "arm length") == measure.NO_ANSWER


def test_with_the_datasheet_the_request_comes_with_its_pages():
    """can_ask_datasheet: the request, the person's line, then each page as an image. The system prompt
    and the tools are can_ask's."""
    person = measure.Person(TASK.hidden_facts)
    first = agent.first_message(TASK, agent.DATASHEET, person)
    assert first[0] == {"type": "text", "text": TASK.request + "\n\nI've attached the servo's datasheet."}
    assert [part["type"] for part in first[1:]] == ["image_url", "image_url"]
    assert all(part["image_url"]["url"].startswith("data:image/png;base64,") for part in first[1:])
    asked = agent.opening_messages(TASK, "can_ask", person, 8)
    given = agent.opening_messages(TASK, agent.DATASHEET, person, 8)
    assert given[0] == asked[0] and agent.tools(agent.DATASHEET) == agent.tools("can_ask")
