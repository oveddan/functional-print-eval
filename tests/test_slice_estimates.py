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


@pytest.mark.parametrize("text, seconds", [("45s", 45), ("8m 46s", 526), ("1h 2m 3s", 3723), ("1d 2h 3m 4s", 93784),
                                            ("2h", 7200)])
def test_durations(text, seconds):
    assert se.duration_s(text) == seconds


@pytest.mark.parametrize("text", ["", "soon", "8 minutes"])
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


def test_a_trial_adds_its_final_parts_and_test_prints_separately():
    trial = se.trial_estimate([a_part(), a_part(), a_part("coupon", print_s=300, filament_g=1.0)])
    assert (trial.final_parts, trial.test_print_parts, trial.parts_not_sliced) == (2, 1, 0)
    assert (trial.final_print_s, trial.final_filament_g) == (1000, 9.0)
    assert (trial.test_print_s, trial.test_print_filament_g) == (300, 1.0)
    assert (trial.all_print_s, trial.all_filament_g) == (1300, 10.0)


def test_a_trial_with_a_part_that_didnt_slice_has_no_totals():
    """A sum missing a part would read as the whole design's cost."""
    trial = se.trial_estimate([a_part(), a_part("coupon", status="not_built")])
    assert trial.parts_not_sliced == 1
    assert trial.final_print_s is None and trial.all_filament_g is None


def test_trials_are_kept_apart():
    second = a_part(trial=2)
    assert [trial.trial for trial in se.trial_estimates([a_part(), second, a_part()])] == [1, 2]


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
