"""The results site's drawn views (scripts/results_site_views.py): the right kind of view for a check, and an honest
reason when there's nothing to draw. Synthetic meshes run anywhere; saved designs skip where their parts aren't built."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import results_site_views as views  # noqa: E402

from pbe.parts.build import Built  # noqa: E402

RUNS = Path(__file__).resolve().parents[1] / "results/runs"


@pytest.fixture(autouse=True)
def scratch(tmp_path, monkeypatch):
    monkeypatch.setattr(views, "OBJECTS", tmp_path / "objects")
    monkeypatch.setattr(views, "CACHE", tmp_path / "cache")


def design_of(mesh, family="tripod-plate", role="final"):
    sub = SimpleNamespace(parts=[SimpleNamespace(id="p", role=role)])
    built = {"p": Built(part_id="p", ok=True, mesh=mesh, role=role)}
    return views.Design(folder=Path("."), task=family, sub=sub, built=built, errors={})


def finding(check, ok=False, detail="", part="p"):
    return {"check": check, "part": part, "ok": ok, "detail": detail}


def holed_roof():
    """A block on the bed with a round cavity open underneath and a small hole through its roof: the strands across the
    roof end at the hole whichever way they run, so the bridge check fails it."""
    block = trimesh.creation.box(extents=(30, 30, 6), transform=trimesh.transformations.translation_matrix((0, 0, 3)))
    cavity = trimesh.creation.cylinder(radius=10, height=4, transform=trimesh.transformations.translation_matrix((0, 0, 1.9)))
    hole = trimesh.creation.cylinder(radius=2, height=20)
    return block.difference(cavity, engine="manifold").difference(hole, engine="manifold")


def test_a_holed_roof_gets_a_drawn_layer():
    entry = views.draw_one(design_of(holed_roof()), finding("bridges", detail="1 unbridgeable overhang(s); first at z = 4.0 mm"))
    assert entry["kind"] == "bridge-layer"
    assert entry["no_view_reason"] is None
    assert (views.OBJECTS / entry["object"]).stat().st_size > 2000


def test_the_view_says_so_when_todays_check_finds_no_roof():
    plain = trimesh.creation.box(extents=(10, 10, 5))
    entry = views.draw_one(design_of(plain), finding("bridges", detail="1 unbridgeable overhang(s); first at z = 2.0 mm"))
    assert entry["object"] is None
    assert "finds no such roof" in entry["no_view_reason"]


def test_a_build_error_has_no_view_and_says_why():
    entry = views.draw_one(design_of(trimesh.creation.box()), finding("builds", detail="NameError: name 'sqrt' is not defined"))
    assert entry["object"] is None
    assert entry["no_view_reason"] == "the code didn't run; there is no shape to draw"
    assert "NameError" in entry["caption"]


def test_an_inside_out_mesh_has_no_pieces_to_colour():
    inside_out = trimesh.creation.box(extents=(10, 10, 5))
    inside_out.invert()
    entry = views.draw_one(design_of(inside_out), finding("connected_bodies", detail="0 bodies"))
    assert entry["object"] is None
    assert "no piece with positive volume" in entry["no_view_reason"]


def test_two_loose_bodies_are_coloured():
    one = trimesh.creation.box(extents=(10, 10, 5))
    two = trimesh.creation.box(extents=(3, 3, 3), transform=trimesh.transformations.translation_matrix((20, 0, 0)))
    entry = views.draw_one(design_of(trimesh.util.concatenate([one, two])), finding("connected_bodies", detail="2 bodies"))
    assert entry["kind"] == "pieces" and entry["object"]


def test_each_check_has_its_view_kind_or_none():
    assert views.choose("estoa-light", "R6") is views.view_estoa_r6
    assert views.choose("nut-knob", "R4") is views.view_knob_r4
    assert views.choose("bearing-wheel", "bridges") is views.view_bridges
    assert views.choose("estoa-light", "R4") is None  # never failed; not drawn yet
    entry = views.draw_one(design_of(trimesh.creation.box(), family="estoa-light"), finding("R4", ok=None, part="-"))
    assert entry["no_view_reason"] == "no drawn view exists for this check yet"


def test_checks_not_reached_and_declined_trials_are_left_out():
    findings = [finding("R3", ok=False), finding("R4", ok=None, detail="no hex pocket for a nut to fit"),
                finding("R5", ok=None, detail="pocket 5.6: no print has measured that"), finding("bridges", ok=False) | {"test_print": True}]
    wanted = views.wanted_findings(findings, declined=False)
    assert [f["check"] for f in wanted] == ["R3", "bridges", "R5"]  # failed counted, failed test print, then not graded
    assert views.wanted_findings(findings, declined=True) == []


def saved(rel):
    folder = RUNS / rel
    if not (folder / "submission.yaml").exists():
        pytest.skip(f"{rel} isn't saved here")
    parts = folder / "parts"
    if not parts.exists() or not any(parts.glob("*.stl")):
        pytest.skip(f"{rel}: parts aren't built here")
    return folder


@pytest.mark.parametrize("rel, check, kind", [
    ("pilot-estoa/estoa-light/can_ask/anthropic__claude-opus-5.5/t4", "bridges", "bridge-layer"),
    ("loop-all/pilot-nut-knob/nut-knob/M5/can_ask/deepseek__deepseek-v4.1-flash/t4/feedback", "R4", "pocket-fit"),
    ("loop-all/pilot-tripod/tripod-plate/can_ask/anthropic__claude-opus-5.5/t1/feedback", "R3", "plate-bolt-cut"),
])
def test_saved_designs_get_the_view_for_their_failure(rel, check, kind):
    folder = saved(rel)
    record = views.process(folder, failed_only=True)
    entries = [entry for entry in record["views"] if entry["check"] == check]
    assert entries, f"{rel} has no failed {check}"
    assert entries[0]["kind"] == kind
    assert entries[0]["object"] and entries[0]["no_view_reason"] is None


def test_the_legend_names_only_what_is_drawn():
    """A legend entry whose mark isn't anywhere in the figure is dropped (the audit found keyholes and a wheel listed
    that weren't drawn)."""
    fig, (ax,) = views.new_figure("one")
    views.fill(ax, views.box_of((0, 0, 10, 5)), fc=views.PART, ec=views.EDGE)
    ax.plot([0, 10], [6, 6], color=views.OK)
    views.frame(ax, (0, 0, 10, 6))
    legend = [views.patch_key(views.PART, "drawn fill", views.EDGE), views.line_key(views.OK, "drawn line"),
              views.patch_key(views.FAIL, "fill never drawn"), views.line_key(views.HARDWARE, "line never drawn", "--"),
              views.Line2D([], [], marker="o", color=views.BOARD, ls="", label="marker never drawn")]
    kept = [handle.get_label() for handle in views.drawn_entries(fig, legend)]
    assert kept == ["drawn fill", "drawn line"]


def test_an_empty_cut_has_no_view():
    flat = trimesh.Trimesh(vertices=[[0, 0, 0], [50, 0, 0], [50, 0, 50], [0, 0, 50]], faces=[[0, 1, 2], [0, 2, 3]])
    entry = views.draw_one(design_of(flat, family="bearing-wheel"), finding("R4", detail="no hole runs through the wheel", part="-"))
    assert entry["object"] is None
    assert entry["no_view_reason"]
