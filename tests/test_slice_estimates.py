"""Reading Bambu Studio's slicer output, resolving its presets, and adding a trial's parts up."""
import json
import sys
from pathlib import Path

import pytest
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import slice_estimates as se  # noqa: E402

# the header Bambu Studio 02.08.02.61 wrote for a 20 mm cube
CUBE_HEADER = """; HEADER_BLOCK_START
; BambuStudio 02.08.02.61
; model printing time: 8m 47s; total estimated time: 9m 7s
; total layer number: 100
; total filament length [mm] : 1226.18
; total filament volume [cm^3] : 2949.30
; total filament weight [g] : 3.66
; filament_density: 1.24
; filament_diameter: 1.75
; max_z_height: 20.00
; filament: 1
; support_material_on_wipe_tower: 0
; HEADER_BLOCK_END

; CONFIG_BLOCK_START
; layer_height = 0.2
"""


def test_the_header_gives_time_filament_and_layers():
    plate = se.parse_gcode_header(CUBE_HEADER)
    assert plate == se.SlicedPlate(print_s=527, total_s=547, filament_mm=1226.18, filament_g=3.66, layers=100)


def test_two_filaments_are_added_up():
    header = CUBE_HEADER.replace("[mm] : 1226.18", "[mm] : 1000.5,200.25").replace("[g] : 3.66", "[g] : 3.0,0.6")
    plate = se.parse_gcode_header(header)
    assert plate.filament_mm == pytest.approx(1200.75)
    assert plate.filament_g == pytest.approx(3.6)


def test_a_header_without_a_time_is_an_error_not_a_zero():
    with pytest.raises(ValueError):
        se.parse_gcode_header(CUBE_HEADER.replace("; model printing time", "; something else"))


def test_lines_after_the_header_are_not_read():
    """A config line with the same label further down must not stand in for a missing header value."""
    header = CUBE_HEADER.replace("; total filament weight [g] : 3.66\n", "") + "; total filament weight [g] : 9.99\n"
    with pytest.raises(ValueError):
        se.parse_gcode_header(header)


@pytest.mark.parametrize("text, seconds", [("45s", 45), ("1d 2h 3m 4s", 93784), ("2h", 7200)])  # one unit, all four, no seconds
def test_durations(text, seconds):
    assert se.duration_s(text) == seconds


@pytest.mark.parametrize("text", ["", "8 minutes"])
def test_a_duration_it_cant_read_is_an_error(text):
    with pytest.raises(ValueError):
        se.duration_s(text)


def test_a_preset_carries_what_it_inherits_and_includes(tmp_path):
    """Parents first, then included templates, then the preset's own keys; the template's name stays out."""
    (tmp_path / "common.json").write_text(json.dumps({"name": "common", "speed": "100", "density": "1.0"}))
    (tmp_path / "base.json").write_text(json.dumps({"name": "base", "inherits": "common", "density": "1.24"}))
    (tmp_path / "start.json").write_text(json.dumps({"name": "start", "instantiation": "false",
                                                     "start_gcode": "G28", "speed": "150"}))
    (tmp_path / "printer.json").write_text(json.dumps({"name": "printer", "inherits": "base", "include": ["start"],
                                                       "speed": "200"}))
    assert se.resolved_preset(tmp_path, "printer") == {
        "name": "printer", "speed": "200", "density": "1.24", "start_gcode": "G28"}


def a_part(role="final", status="sliced", **values):
    estimate = se.PartEstimate(run="r", task="t", condition="can_ask", model="m", trial=1, verdict="fail",
                               part=f"{role}-part", role=role, status=status, error="", warning="")
    if status == "sliced":
        estimate.print_s, estimate.filament_m, estimate.filament_g = 500, 1.5, 4.5
    for key, value in values.items():
        setattr(estimate, key, value)
    return estimate


def a_plate(print_s, filament_g):
    return se.PlateResult(se.SlicedPlate(print_s=print_s, total_s=print_s, filament_mm=filament_g * 330,
                                         filament_g=filament_g, layers=50))


def test_a_trials_final_parts_come_from_their_plate_not_a_sum():
    """Two final parts sliced together (900 s) take less than each alone (500 + 500 s)."""
    parts = [a_part(), a_part(), a_part("coupon", print_s=300, filament_g=1.0)]
    trial = se.trial_estimate(parts, {"final": a_plate(900, 8.9)})
    assert (trial.final_parts, trial.test_print_parts, trial.parts_not_sliced) == (2, 1, 0)
    assert (trial.final_print_s, trial.final_filament_g) == (900, 8.9)
    assert (trial.test_print_s, trial.test_print_filament_g) == (300, 1.0)  # one test print is its own plate
    assert (trial.all_print_s, trial.all_filament_g) == (1200, 9.9)
    assert trial.plates == 2


def test_every_plate_the_slicer_writes_is_counted(tmp_path):
    """Parts that don't fit on one bed go onto plate_2 with no error, so reading plate 1 alone would drop them."""
    (tmp_path / "plate_1.gcode").write_text(CUBE_HEADER)
    (tmp_path / "plate_2.gcode").write_text(CUBE_HEADER.replace("total layer number: 100", "total layer number: 120"))
    plate = se.combined(se.read_plates(tmp_path))
    assert (plate.print_s, plate.filament_g, plate.layers) == (2 * 527, pytest.approx(7.32), 120)


def test_a_trial_without_test_prints_spends_nothing_on_them():
    trial = se.trial_estimate([a_part()], {})
    assert (trial.test_print_s, trial.test_print_filament_g, trial.all_print_s) == (0, 0.0, 500)
    assert trial.plates == 1


def test_a_trial_with_a_part_that_didnt_slice_has_no_totals():
    """A sum missing a part would read as the whole design's cost."""
    trial = se.trial_estimate([a_part(), a_part("coupon", status="not_built")], {})
    assert trial.parts_not_sliced == 1
    assert trial.final_print_s is None and trial.all_filament_g is None


def test_a_plate_that_didnt_slice_leaves_the_totals_blank_and_says_why():
    failed = se.PlateResult(None, "Some objects are outside the plate. (code -51)")
    trial = se.trial_estimate([a_part(), a_part()], {"final": failed})
    assert trial.plate_error == "final: Some objects are outside the plate. (code -51)"
    assert trial.final_print_s is None and trial.test_print_s is None


def test_only_groups_of_several_parts_get_a_plate_and_only_when_every_part_sliced():
    def job(trial, role, name):
        return se.PartJob(run="r", folder=Path("."), task="t", condition="c", model="m", trial=trial, verdict="fail",
                          part=name, role=role, stl=Path(f"{trial}-{name}.stl"))
    jobs = [job(1, "final", "a"), job(1, "final", "b"), job(1, "coupon", "c"), job(2, "final", "a"),
            job(2, "final", "b")]
    parts = [a_part(trial=1), a_part(trial=1), a_part("coupon", trial=1), a_part(trial=2),
             a_part(trial=2, status="not_sliced")]
    plates = se.plate_jobs(jobs, parts)
    assert [(plate.key[-1], plate.group, [stl.name for stl in plate.stls]) for plate in plates] == [
        (1, "final", ["1-a.stl", "1-b.stl"])]


def test_trials_are_kept_apart():
    second = a_part(trial=2)
    assert [trial.trial for trial in se.trial_estimates([a_part(), second, a_part()], [])] == [1, 2]


def test_presets_are_found_beside_the_app_or_a_binary(tmp_path, monkeypatch):
    monkeypatch.delenv("BAMBU_STUDIO_PROFILES", raising=False)
    app = tmp_path / "BambuStudio.app"
    (app / "Contents/Resources/profiles/BBL").mkdir(parents=True)
    assert se.profiles_dir(app) == app / "Contents/Resources/profiles/BBL"
    assert se.profiles_dir(app / "Contents/MacOS/BambuStudio") == app / "Contents/Resources/profiles/BBL"
    linux = tmp_path / "squashfs-root"
    (linux / "resources/profiles/BBL").mkdir(parents=True)
    # samefile: on macOS the file system ignores case, so the .app layout's "Resources" also finds "resources"
    assert se.profiles_dir(linux / "bin/bambu-studio").samefile(linux / "resources/profiles/BBL")


def test_presets_are_found_beside_a_program_named_by_a_relative_path(tmp_path, monkeypatch):
    monkeypatch.delenv("BAMBU_STUDIO_PROFILES", raising=False)
    (tmp_path / "resources/profiles/BBL").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    assert se.profiles_dir(Path("./bambu-studio")).samefile(tmp_path / "resources/profiles/BBL")


def test_a_program_named_by_a_relative_path_is_run_by_its_absolute_path(tmp_path, monkeypatch):
    """The slicer runs in a temporary folder, where './bambu-studio' would name nothing."""
    monkeypatch.chdir(tmp_path)
    assert se.slicer_binary(Path("./bambu-studio")) == tmp_path.resolve() / "bambu-studio"


def test_a_program_at_the_root_still_gets_its_folders_looked_in():
    assert se.profile_candidates(Path("/bambu-studio"))[-1] == Path("/resources/profiles/BBL")


def test_presets_can_be_named_and_a_missing_folder_says_how(tmp_path, monkeypatch):
    monkeypatch.setenv("BAMBU_STUDIO_PROFILES", str(tmp_path / "BBL"))
    assert se.profiles_dir(tmp_path / "anything") == tmp_path / "BBL"
    monkeypatch.delenv("BAMBU_STUDIO_PROFILES")
    with pytest.raises(FileNotFoundError, match="BAMBU_STUDIO_PROFILES"):
        se.profiles_dir(tmp_path / "bin/bambu-studio")


def test_the_slicers_own_reason_is_kept(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"return_code": -51, "error_string": "Some objects are outside the plate. "}))
    assert se.slicer_complaint(result, "noise\n") == "Some objects are outside the plate. (code -51)"
    assert se.slicer_complaint(tmp_path / "missing.json", "a\nlast line\n\n") == "last line"


def test_a_part_goes_onto_the_bed_without_turning(tmp_path):
    box = trimesh.creation.box((10, 20, 30))  # centred on the origin, so half of it is under the bed
    box.export(tmp_path / "box.stl")
    height = se.on_the_bed(tmp_path / "box.stl", tmp_path / "placed.stl")
    placed = trimesh.load(tmp_path / "placed.stl")
    assert height == pytest.approx(30)
    assert placed.bounds[0][2] == pytest.approx(0)
    assert placed.extents == pytest.approx((10, 20, 30))


def test_the_printers_start_and_end_sequences_are_left_out():
    machine = {"name": "x1c", "machine_start_gcode": "G28\nG29", "machine_end_gcode": "M400", "layer_change_gcode": "M73"}
    assert se.without_printer_sequences(machine) == {
        "name": "x1c", "machine_start_gcode": "", "machine_end_gcode": "", "layer_change_gcode": "M73"}


@pytest.mark.skipif(not se.slicer_binary().exists(), reason="Bambu Studio isn't installed here")
def test_bambu_studio_slices_a_cube_with_the_fixed_presets(tmp_path):
    """End to end on this machine: a 20 mm cube at 0.20 mm, 2 walls and 15% infill in PLA is a few grams."""
    trimesh.creation.box((20, 20, 20)).export(tmp_path / "cube.stl")
    presets = se.write_presets(tmp_path)
    job = se.PartJob(run="r", folder=tmp_path, task="t", condition="c", model="m", trial=1, verdict="pass",
                     part="cube", role="final", stl=tmp_path / "cube.stl")
    estimate = se.slice_part((job, presets))
    assert estimate.status == "sliced", estimate.error
    assert estimate.layers == 100
    assert 3 < estimate.filament_g < 5
    assert 300 < estimate.print_s < 3600


@pytest.mark.skipif(not se.slicer_binary().exists(), reason="Bambu Studio isn't installed here")
def test_two_parts_on_one_plate_take_less_time_than_each_alone(tmp_path):
    """The reason a trial's totals come from its plate: the same filament, less time."""
    trimesh.creation.cylinder(radius=6, height=4).export(tmp_path / "spacer.stl")
    presets = se.write_presets(tmp_path)
    alone = se.slice_plate([tmp_path / "spacer.stl"], presets).plate
    together = se.slice_plate([tmp_path / "spacer.stl", tmp_path / "spacer.stl"], presets).plate
    assert together.print_s < 2 * alone.print_s
    assert together.filament_g == pytest.approx(2 * alone.filament_g, abs=0.02)


@pytest.mark.skipif(not se.slicer_binary().exists(), reason="Bambu Studio isn't installed here")
def test_parts_too_big_for_one_bed_are_counted_on_every_plate(tmp_path):
    trimesh.creation.box((180, 180, 2)).export(tmp_path / "big.stl")
    presets = se.write_presets(tmp_path)
    one = se.slice_plate([tmp_path / "big.stl"], presets)
    two = se.slice_plate([tmp_path / "big.stl", tmp_path / "big.stl"], presets)
    assert (one.plates, two.plates) == (1, 2)
    assert two.plate.filament_g == pytest.approx(2 * one.plate.filament_g, abs=0.05)


def test_a_replay_runs_arms_are_read_as_trials_kept_apart():
    """loop-estoa saves loop.json, not grades.json: each arm with a design is sliced, under its own key."""
    arms = list(se.loop_arms(se.RUNS / "loop-estoa"))
    with_design = [(folder, arm) for folder, arm in arms if (folder / "submission.yaml").exists()]
    assert len(with_design) == 52  # 26 trials, feedback and neutral; a baseline's design is pilot-estoa's
    assert {arm.condition for _, arm in with_design} == {"can_ask/feedback", "can_ask/neutral"}
    keys = [("loop-estoa", arm.task, arm.condition, arm.model, arm.trial) for _, arm in with_design]
    assert len(set(keys)) == len(keys)
    assert not any("schema-bug" in str(folder) for folder, _ in arms)  # the kept originals aren't sliced again
    passed = [arm for _, arm in arms if arm.verdict == "pass"]
    assert [(arm.model, arm.trial, arm.condition) for arm in passed] == [  # after Dan's review of the Estoa failures, R4 passing for now, 2026-11-13
        ("anthropic/claude-opus-5.5", 1, "can_ask/baseline"), ("anthropic/claude-opus-5.5", 1, "can_ask/feedback"),
        ("anthropic/claude-opus-5.5", 1, "can_ask/neutral"), ("anthropic/claude-opus-5.5", 4, "can_ask/feedback"),
        ("anthropic/claude-opus-5.5", 5, "can_ask/baseline"), ("anthropic/claude-opus-5.5", 5, "can_ask/feedback"),
        ("anthropic/claude-opus-5.5", 5, "can_ask/neutral"), ("anthropic/claude-sonnet-5.5", 3, "can_ask/baseline"),
        ("anthropic/claude-sonnet-5.5", 3, "can_ask/feedback"), ("anthropic/claude-sonnet-5.5", 3, "can_ask/neutral"),
        ("anthropic/claude-sonnet-5.5", 5, "can_ask/feedback"), ("google/gemini-4-argon", 2, "can_ask/feedback"),
        ("google/gemini-4-argon", 3, "can_ask/feedback"), ("google/gemini-4-argon", 4, "can_ask/feedback"),
        ("google/gemini-4-argon", 5, "can_ask/feedback"), ("openai/gpt-6.1-sol", 2, "can_ask/baseline"),
        ("openai/gpt-6.1-sol", 2, "can_ask/feedback"), ("openai/gpt-6.1-sol", 2, "can_ask/neutral"),
        ("openai/gpt-6.1-sol", 3, "can_ask/feedback"), ("openai/gpt-6.1-sol", 4, "can_ask/feedback"),
        ("openai/gpt-6.1-sol", 4, "can_ask/neutral")]
