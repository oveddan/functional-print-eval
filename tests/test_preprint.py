"""pbe.preprint: the eval's checks on a design before it's printed, from a hand-in or an exported STL or STEP file.
Every prediction names the recorded print it rests on, or says nothing recorded is near."""
import math

import pytest
import trimesh
from shapely.geometry import Polygon

from pbe import preprint
from pbe.graders import nuts
from pbe.runner import tasks

ROOT = preprint.Path(__file__).resolve().parents[1]
M5_AF = 8.0


def _hexagon(across):
    radius = across / 2 / math.cos(math.radians(30))
    return Polygon([(radius * math.cos(math.radians(60 * corner)), radius * math.sin(math.radians(60 * corner))) for corner in range(6)])


def _cut(block, cutter):
    return trimesh.boolean.difference([block, cutter], engine="manifold")


def _block(size, height):
    block = trimesh.creation.box((size, size, height))
    block.apply_translation((0, 0, height / 2))
    return block


def _save(mesh, tmp_path, name):
    path = tmp_path / name
    mesh.export(path)
    return path


def nut_block(tmp_path, across, name="knob.stl"):
    """A 20 mm block, 8 tall, with a plain hex pocket 5 deep open to the top."""
    pocket = trimesh.creation.extrude_polygon(_hexagon(across), 6)
    pocket.apply_translation((0, 0, 3))
    return _save(_cut(_block(20, 8), pocket), tmp_path, name)


def seat_block(tmp_path, seat_d):
    """A 40 mm block, 10 tall, with a round seat 7 deep open to the top."""
    seat = trimesh.creation.cylinder(radius=seat_d / 2, height=8, sections=256)
    seat.apply_translation((0, 0, 7))
    return _save(_cut(_block(40, 10), seat), tmp_path, "wheel.stl")


def holed_roof(tmp_path):
    """A 30 mm block with a 20 mm room open to the bed and a 5 mm hole through its roof: the Arca plate's first roof."""
    room = trimesh.creation.box((20, 20, 6))
    room.apply_translation((0, 0, 3))
    hole = trimesh.creation.cylinder(radius=2.5, height=30, sections=64)
    return _save(_cut(_cut(_block(30, 10), room), hole), tmp_path, "plate.stl")


def by_check(predictions):
    return {prediction.check: prediction for prediction in predictions}


def test_an_stl_nut_pocket_is_read_against_the_pocket_test_print_b_printed(tmp_path):
    design, predictions = preprint.check(nut_block(tmp_path, M5_AF), labels=("M5",))
    found = by_check(predictions)
    assert design.sub is None and set(found) == {"builds", "connected_bodies", "bed_fit", "bridges", "nut pocket"}
    pocket = found["nut pocket"]
    assert pocket.ok is True and "8.00 mm across flats, +0.00 over the 8.0 mm nut: prints say holds" in pocket.detail
    assert pocket.basis == 'the M5 plain pocket test-printed at +0.00 mm (test print B: "push to insert, tight")'
    assert all(found[check].ok is True and found[check].basis for check in ("connected_bodies", "bed_fit", "bridges"))
    assert "printing clean" in found["bridges"].basis


def test_a_pocket_that_wasnt_printed_says_which_prints_it_rests_on():
    """Each way nuts.reading can decide a size nobody printed gets its own basis, so none claims a print that isn't there."""
    sizes = [printed for printed, _ in nuts._measured()["M3", "plain"]]
    basis = lambda clearance: preprint._pocket_basis("M3", "plain", clearance, *nuts.reading("M3", clearance))  # noqa: E731
    assert "tighter than the tightest of them" in basis(min(sizes) - 0.5)
    assert "looser than the loosest of them" in basis(max(sizes) + 1.0) or basis(max(sizes) + 1.0) == preprint.NOTHING_NEAR
    for clearance in (size + 0.03 for size in sizes[:-1]):
        outcome, assumed_from = nuts.reading("M3", clearance)
        if assumed_from is not None:
            assert f"at {assumed_from:+.2f} mm, the nearest size printed" in basis(clearance)
        elif outcome is not None:
            assert basis(clearance).endswith("either side of this size, which agree")


def closed_nut_block(tmp_path):
    """The same block with its M5 pocket sealed inside: nothing can be pressed into it."""
    pocket = trimesh.creation.extrude_polygon(_hexagon(M5_AF), 4)
    pocket.apply_translation((0, 0, 2))
    return _save(_cut(_block(20, 8), pocket), tmp_path, "sealed.stl")


def test_a_pocket_no_nut_can_reach_fails_whatever_its_size(tmp_path):
    """A sealed hex void and a hex that runs right through are both the right size, and both fail on geometry."""
    _, sealed = preprint.check(closed_nut_block(tmp_path), labels=("M5",))
    pocket = by_check(sealed)["nut pocket"]
    assert pocket.ok is False and "can't be pressed in from either face" in pocket.detail and pocket.basis == preprint.GEOMETRY
    through = trimesh.creation.extrude_polygon(_hexagon(M5_AF), 20)
    through.apply_translation((0, 0, -5))
    _, open_both = preprint.check(_save(_cut(_block(20, 8), through), tmp_path, "through.stl"), labels=("M5",))
    assert by_check(open_both)["nut pocket"].ok is False and "runs right through" in by_check(open_both)["nut pocket"].detail


def test_a_check_that_crashes_on_a_shape_is_not_graded_and_the_others_still_run(tmp_path, monkeypatch):
    def broken(mesh):
        raise ValueError("bad polygon")
    monkeypatch.setattr(preprint, "overhangs", broken)
    design, predictions = preprint.check(nut_block(tmp_path, M5_AF), labels=("M5",))
    found = by_check(predictions)
    assert found["bridges"].ok is None and "ValueError: bad polygon" in found["bridges"].detail
    assert found["bed_fit"].ok is True and found["nut pocket"].ok is True
    assert "not graded  bridges" in preprint.report(design, predictions)


def test_hex_pockets_are_only_read_for_a_nut_someone_named(tmp_path):
    """A hexagon is also a bolt head's recess, so a mesh's pockets aren't guessed at."""
    design, predictions = preprint.check(nut_block(tmp_path, M5_AF))
    assert "nut pocket" not in by_check(predictions)
    assert "--nut" in preprint.report(design, predictions)


def test_a_seat_is_read_against_the_printed_608_seats(tmp_path):
    """The wheel task's own limits: too tight fails, the sizes that held pass, and from the size that fell out it fails."""
    limits = preprint.seat_limits()
    held = sum(limits["holds"]) / 2
    _, printed = preprint.check(seat_block(tmp_path, held), bearing=True)
    seat = by_check(printed)["bearing seat"]
    assert seat.ok is True and "the 608 seats test-printed" in seat.basis and str(limits["too_loose"]) in seat.basis
    _, tight = preprint.check(seat_block(tmp_path, limits["too_tight"] - 0.5), bearing=True)
    assert by_check(tight)["bearing seat"].ok is False
    _, loose = preprint.check(seat_block(tmp_path, limits["too_loose"] + 1.0), bearing=True)
    assert by_check(loose)["bearing seat"].ok is False and "too loose" in by_check(loose)["bearing seat"].detail
    _, unasked = preprint.check(seat_block(tmp_path, held))
    assert "bearing seat" not in by_check(unasked)


def test_a_seat_no_print_is_near_is_not_graded(tmp_path):
    """A seat with a slot cut across it: only plain round seats were printed, so nothing recorded is near."""
    held = sum(preprint.seat_limits()["holds"]) / 2
    slot = trimesh.creation.box((30, 6, 8))
    slot.apply_translation((0, 0, 7))
    plain = trimesh.load(seat_block(tmp_path, held), force="mesh")
    _, slotted = preprint.check(_save(_cut(plain, slot), tmp_path, "slotted.stl"), bearing=True)
    seat = by_check(slotted)["bearing seat"]
    assert seat.ok is None and seat.basis == preprint.NOTHING_NEAR and "not graded" in preprint.report(*preprint.check(tmp_path / "slotted.stl", bearing=True))


def test_the_seat_limits_are_the_wheel_tasks_own():
    fit = next(requirement for requirement in tasks.load("bearing-wheel").requirements if requirement.grader == "wheel.fit")
    assert preprint.seat_limits() == {name: fit.args[name] for name in ("too_tight", "holds", "too_loose")}


def test_a_part_the_design_says_to_print_with_supports_passes_on_that_instruction(tmp_path):
    """As a trial's bridge check reads it since 2026-11-12, and the basis says no print is behind it."""
    part = preprint.mesh_part(holed_roof(tmp_path))
    part.supports = "Print the plate with supports under the roof."
    prediction = preprint.bridge_prediction(part)
    assert prediction.ok is True and "prints with supports" in prediction.detail and "no print is behind it" in prediction.basis


def test_a_holed_roof_fails_on_the_prints_that_tangled_and_the_command_exits_1(tmp_path, capsys):
    path = holed_roof(tmp_path)
    _, predictions = preprint.check(path)
    bridges = by_check(predictions)["bridges"]
    assert bridges.ok is False and "Arca plate" in bridges.basis and "cell H" in bridges.basis
    with pytest.raises(SystemExit) as exit_:
        preprint.main([str(path)])
    assert exit_.value.code == 1
    printed = capsys.readouterr().out
    assert "It is not a print simulation" in printed and "geometry" in printed and "recorded" in printed
    assert "FAIL        bridges" in printed and "based on: the Arca plate's first roof" in printed


def test_the_agents_hand_in_gets_its_tasks_requirements(tmp_path):
    """The spacer's reference, saved as a trial saves a hand-in: the general checks and the task's own, all passing."""
    (tmp_path / "submission.yaml").write_text(tasks.load("m5-spacer").reference)
    design, predictions = preprint.check(tmp_path, out_dir=tmp_path / "parts")
    task = tasks.load("m5-spacer")
    assert design.sub is not None and design.task.id == "m5-spacer"
    assert {prediction.check for prediction in predictions} >= {requirement.id for requirement in task.requirements}
    assert all(prediction.ok is True and prediction.basis for prediction in predictions)
    assert (tmp_path / "parts/spacer.stl").exists()
    assert "--nut" not in preprint.report(design, predictions)  # the mesh note is for designs with no task behind them


def test_a_hand_ins_requirements_are_read_on_its_final_parts_as_a_can_test_trial_is(tmp_path):
    """Opus's M3 knob with its four-pocket test piece: the check agrees with the grade of the design without its
    test pieces, check by check, and reads the parts a build already left behind instead of building them again."""
    from pbe.runner import agent
    saved = ROOT / "results/runs/pilot-nut-knob-2/nut-knob/M3/can_ask/anthropic__claude-opus-5.5/t1"
    sub = preprint.submission.load(saved / "submission.yaml")
    assert any(part.role == "coupon" for part in sub.parts)
    graded = agent.grade(tasks.load("nut-knob/M3"), agent.graded_design("can_test", sub), tmp_path / "graded")
    wanted = {finding.check: finding.ok for finding in graded if finding.part == "-"}

    monkey_built = []
    real = preprint.build_parts
    try:
        preprint.build_parts = lambda sub, out_dir: monkey_built.append([part.id for part in sub.parts]) or real(sub, out_dir)
        design, predictions = preprint.check(saved, built_in=tmp_path / "graded/parts")
    finally:
        preprint.build_parts = real
    assert {prediction.check: prediction.ok for prediction in predictions if prediction.part == "-"} == wanted
    assert monkey_built == [[part.id for part in sub.parts if part.role == "coupon"]]  # only what grading left out
    assert "final parts only" in preprint.report(design, predictions)


def test_a_hand_in_with_no_task_reads_the_nuts_its_hardware_lists(tmp_path):
    """The Arca plate example isn't one of the eval's tasks: its roof fails, and no nut it lists was printed."""
    design, predictions = preprint.check(ROOT / "examples/arca-plate/original.yaml")
    assert design.task is None and by_check(predictions)["bridges"].ok is False
    assert preprint.nuts_listed(design.sub) == tuple(label for label, ref in preprint.NUT_REFS.items()
                                                     if ref in {item.ref for item in design.sub.hardware})


def test_a_step_file_is_read_as_a_mesh(tmp_path):
    import cadquery as cq
    path = tmp_path / "block.step"
    cq.exporters.export(cq.Workplane("XY").box(20, 30, 10), str(path))
    design, predictions = preprint.check(path)
    assert by_check(predictions)["bed_fit"].detail.startswith("30.0 x 20.0 x 10.0 mm")
    assert not preprint.any_failed(predictions)


def test_a_file_that_isnt_a_design_is_refused_not_passed(tmp_path):
    (tmp_path / "broken.stl").write_text("not a mesh")
    _, predictions = preprint.check(tmp_path / "broken.stl")
    assert by_check(predictions)["builds"].ok is False
    with pytest.raises(preprint.NotADesign):
        preprint.check(tmp_path / "missing.stl")
    (tmp_path / "notes.yaml").write_text("task: x\n")
    with pytest.raises(preprint.NotADesign):
        preprint.check(tmp_path / "notes.yaml")
