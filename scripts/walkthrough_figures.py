"""The README's walkthrough pictures: one trial that failed its first print and passed its second, after the person
said how the first came out. No model calls.

    uv run python scripts/walkthrough_figures.py

Writes docs/media/walkthrough/: a four-panel storyboard, a render of each design and the bridge check's strand picture of the roof that
failed, with the failed roof drawn in red on the first design. The example is Gemini 4 Argon's Estoa box (pilot-estoa t2, replayed in loop-estoa). Parts are built from
the saved designs if this machine doesn't have them (parts/ isn't committed).

Also a second storyboard, test-print-storyboard.png, for the loop the results table comes from (can_test): Sonnet 5.5's M3
knob (test-first t2) asks for a test print of four nut pockets, hears how each came out, and builds its knob at the size that held.
"""
import json
import math
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import failure_figures  # noqa: E402  the knob cut across with its nut drawn in
import gallery  # noqa: E402  the gallery's renderer, so these match the results page

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402
from shapely.geometry import Point, Polygon  # noqa: E402

from pbe.graders import bridges, sections  # noqa: E402
from pbe.parts import submission  # noqa: E402
from pbe.parts.build import build_parts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/media/walkthrough"
FIRST = ROOT / "results/runs/pilot-estoa/estoa-light/can_ask/google__gemini-4-argon/t2"
SECOND = ROOT / "results/runs/loop-estoa/pilot-estoa/estoa-light/can_ask/google__gemini-4-argon/t2/feedback"
PART = "wall_box"


def mesh_of(folder: Path) -> trimesh.Trimesh:
    stl = folder / "parts" / f"{PART}.stl"
    if not stl.exists():
        build_parts(submission.load(folder / "submission.yaml"), folder / "parts")
    return trimesh.load(stl, force="mesh")


def around(mesh: trimesh.Trimesh, centre, half: float) -> trimesh.Trimesh:
    """The part of the mesh within `half` mm of `centre` in x and y, so a close-up shows the opening."""
    cx, cy = centre
    for normal, origin in (((1, 0, 0), (cx - half, 0, 0)), ((-1, 0, 0), (cx + half, 0, 0)),
                           ((0, 1, 0), (0, cy - half, 0)), ((0, -1, 0), (0, cy + half, 0))):
        mesh = mesh.slice_plane(origin, normal, cap=True)
    return mesh


def shaded(mesh: trimesh.Trimesh, failed=None, toward=None):
    """Every face, lit from above left as in the gallery, with the plastic printed over the failed roof in red: every face
    above the roof's height whose centre lies over the region the bridge check found unsupported."""
    light = np.array([0.45, -0.35, 0.82])  # the gallery's light, without its cap on how many faces are drawn
    faces, normals = mesh.triangles, mesh.face_normals
    if toward is not None:  # drop faces turned away from the camera: matplotlib sorts them in front of nearer ones
        facing = normals @ toward > 0
        faces, normals = faces[facing], normals[facing]
    shade = 0.32 + 0.6 * np.clip(normals @ light, 0, 1)
    colours = np.column_stack([shade * 0.86, shade * 0.9, shade * 0.98, np.ones(len(shade))])
    if failed is None:
        return faces, colours
    over = failed.region.buffer(0.5)
    centres = faces.mean(axis=1)
    for index, (x, y, z) in enumerate(centres):
        if z >= failed.z - 0.2 and over.contains(Point(x, y)):
            shade = colours[index][2] / 0.98
            colours[index] = [min(1.0, shade * 1.05), shade * 0.38, shade * 0.32, 1.0]
    return faces, colours


def render(mesh: trimesh.Trimesh, png: Path, azim: float, failed=None, elev: float = 24) -> None:
    """Seen from outside the wall that holds the USB opening, the failed roof in red."""
    toward = np.array([math.cos(math.radians(elev)) * math.cos(math.radians(azim)),
                       math.cos(math.radians(elev)) * math.sin(math.radians(azim)), math.sin(math.radians(elev))])
    faces, colours = shaded(mesh, failed, toward)
    fig = plt.figure(figsize=(4.4, 3.6), dpi=240)
    fig.patch.set_alpha(0)
    ax = fig.add_axes([0, 0, 1, 1], projection="3d")
    ax.patch.set_alpha(0)
    # each face's edge in its own colour hides the seams between neighbouring triangles
    ax.add_collection3d(Poly3DCollection(faces, facecolors=colours, edgecolors=colours, linewidths=0.4))
    low, high = mesh.bounds
    middle, reach = (low + high) / 2, float((high - low).max()) * 0.5
    ax.set_xlim(middle[0] - reach, middle[0] + reach)
    ax.set_ylim(middle[1] - reach, middle[1] + reach)
    ax.set_zlim(middle[2] - reach, middle[2] + reach)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    fig.savefig(png, transparent=True, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


# the request's own words (tasks/estoa-light/brief.md), cut with ellipses
REQUEST = ("I'm making a round light to hang on my wall: an Adafruit DotStar LED disc, the 255-LED one. \u2026 "
           "for now I only need that box, with the disc screwed onto it. Inside it is an ESP32 on a perfboard \u2026 "
           "I power it with a USB-C charger plugged straight into the ESP32, so I need to reach its port from "
           "outside once it's all closed up.")


def reply_text() -> str:
    """The line the person said after the first print, from the saved replay."""
    record = json.loads((SECOND / "loop.json").read_text())
    lines = [line.strip("- ").strip() for line in record["reply"].splitlines() if line.startswith("- ")]
    return "I printed what you sent. " + " ".join(lines)


def text_panel(ax, title: str, body: str, colour: str) -> None:
    ax.set_axis_off()
    ax.add_patch(FancyBboxPatch((0.02, 0.04), 0.96, 0.9, boxstyle="round,pad=0.01,rounding_size=0.03",
                                transform=ax.transAxes, facecolor=colour, edgecolor="#c9cfcc", linewidth=0.8))
    ax.text(0.07, 0.86, title, transform=ax.transAxes, fontsize=12, fontweight="bold", va="top", color="#1d2421")
    ax.text(0.07, 0.72, textwrap.fill(f"\u201c{body}\u201d", 42), transform=ax.transAxes, fontsize=10.5, va="top",
            color="#2c3431", linespacing=1.45)


def image_panel(ax, title: str, png: Path, caption: str, caption_colour: str) -> None:
    ax.set_axis_off()
    ax.text(0.5, 0.97, title, transform=ax.transAxes, fontsize=12, fontweight="bold", ha="center", va="top", color="#1d2421")
    picture = plt.imread(png)
    rows, cols = (picture[..., 3] > 0).any(axis=1).nonzero()[0], (picture[..., 3] > 0).any(axis=0).nonzero()[0]
    picture = picture[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]  # trimmed to the part
    box_w, box_h = ax.get_position().width * ax.figure.get_figwidth(), ax.get_position().height * ax.figure.get_figheight()
    width = 0.86
    height = width * box_w / box_h * picture.shape[0] / picture.shape[1]
    ax.imshow(picture, extent=(0.5 - width / 2, 0.5 + width / 2, 0.52 - height / 2, 0.52 + height / 2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("auto")
    ax.text(0.5, 0.06, caption, transform=ax.transAxes, fontsize=10.5, ha="center", color=caption_colour)


def storyboard(png: Path) -> None:
    """The trial in four panels: the request, the first print, what the person said, the second print."""
    fig, axes = plt.subplots(2, 2, figsize=(10, 7.4), dpi=130)
    fig.patch.set_facecolor("white")
    text_panel(axes[0][0], "1. The person asks", REQUEST, "#f3f5f4")
    image_panel(axes[0][1], "2. First print (simulated)", OUT / "first-design.png",
                "Fails: the strip over the USB window (red) has nothing under it", "#b0392b")
    text_panel(axes[1][0], "3. The person says how it came out", reply_text(), "#fbf0e6")
    image_panel(axes[1][1], "4. Second print (simulated)", OUT / "second-design.png",
                "Passes every check: the window is now an open channel", "#2f7a4f")
    fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.02, wspace=0.06, hspace=0.08)
    fig.savefig(png, facecolor="white")
    plt.close(fig)


def whole_and_close_up(whole: Path, close: Path, out: Path) -> None:
    """The whole part beside its close-up, trimmed to the parts and set at the same height, with a label over each."""
    pictures = []
    for png in (whole, close):
        picture = plt.imread(png)
        rows, cols = (picture[..., 3] > 0).any(axis=1).nonzero()[0], (picture[..., 3] > 0).any(axis=0).nonzero()[0]
        pictures.append(picture[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1])
    widths = [pic.shape[1] / pic.shape[0] for pic in pictures]
    fig, axes = plt.subplots(1, 2, figsize=(sum(widths) * 2.2 + 0.4, 2.6), dpi=200,
                             gridspec_kw={"width_ratios": widths})
    for ax, pic, label in zip(axes, pictures, ("The whole box", "Close-up: the USB opening")):
        ax.imshow(pic)
        ax.set_axis_off()
        ax.set_title(label, fontsize=9, color="#2c3431")
    fig.savefig(out, facecolor="white", bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


TEST_TRIAL = ROOT / "results/runs/test-first/nut-knob/M3/can_test/anthropic__claude-sonnet-5.5/t2"


def test_trial_record() -> dict:
    return json.loads((TEST_TRIAL / "grades.json").read_text())


def test_request() -> str:
    """The person's request, as the model read it."""
    messages = json.loads((TEST_TRIAL / "transcript.json").read_text())
    return next(message["content"] for message in messages if message["role"] == "user")


def test_reply() -> str:
    """What the person said about each test piece, from the saved trial."""
    lines = [line["text"] for test in test_trial_record()["test_prints"] for piece in test["reply"].values() for line in piece]
    return "I printed the test pieces. " + " ".join(lines)


def test_piece_png() -> Path:
    """The test piece cut straight across 1 mm up, through its four nut pockets, each labelled with its width across
    flats as measured on the cut (a regular hexagon's area is sqrt(3)/2 times that width squared)."""
    stl = TEST_TRIAL / "parts/test1/nut-coupon.stl"
    if not stl.exists():
        build_parts(submission.load(TEST_TRIAL / "submission.yaml"), TEST_TRIAL / "parts")  # the coupon is built with it
    mesh = trimesh.load(stl, force="mesh")
    plate = max(sections.section_at(mesh, 2, mesh.bounds[0][2] + 1.0), key=lambda polygon: polygon.area)
    fig, ax = plt.subplots(figsize=(4.6, 1.9), dpi=200)
    ax.add_patch(failure_figures._patch(plate, facecolor=failure_figures.PART, edgecolor=failure_figures.EDGE, lw=0.8))
    for pocket in sorted(plate.interiors, key=lambda ring: ring.centroid.x):
        hexagon = Polygon(pocket)
        if hexagon.area < 15:  # the bolt's round hole through a pocket, not a pocket
            continue
        across = math.sqrt(2 * hexagon.area / math.sqrt(3))
        ax.text(hexagon.centroid.x, plate.bounds[3] + 1.2, f"{across:.2f}", ha="center", fontsize=8, color="#2c3431")
    ax.set_xlim(plate.bounds[0] - 1, plate.bounds[2] + 1)
    ax.set_ylim(plate.bounds[1] - 1, plate.bounds[3] + 3.5)
    ax.set_aspect("equal")
    ax.set_axis_off()
    png = OUT / "test-print-piece.png"
    fig.savefig(png, bbox_inches="tight", facecolor="white", metadata={"Software": None})
    plt.close(fig)
    return png


def final_knob_png() -> Path:
    """The final knob cut straight across at its pocket, with the M3 nut and both widths labelled."""
    trial = TEST_TRIAL.relative_to(ROOT / "results/runs").as_posix()
    drawn = failure_figures.draw(failure_figures.Figure("test-print-final-knob", trial, "knob", "across",
                                                        nut="ISO 4032 M3", dimensions=True))
    png = OUT / "test-print-final-knob.png"
    png.write_bytes(drawn.read_bytes())
    drawn.unlink()
    return png


def test_print_storyboard(png: Path) -> None:
    """The test-print loop in four panels: the request, the test print the model asked for, what the person said, the
    final design."""
    fig, axes = plt.subplots(2, 2, figsize=(10, 7.4), dpi=130)
    fig.patch.set_facecolor("white")
    text_panel(axes[0][0], "1. The person asks", test_request(), "#f3f5f4")
    image_panel(axes[0][1], "2. The model asks for a test print", test_piece_png(),
                "Cut across its four nut pockets, widths in mm", "#2c3431")
    text_panel(axes[1][0], "3. The person says how each came out", test_reply(), "#fbf0e6")
    image_panel(axes[1][1], "4. Final design (simulated)", final_knob_png(),
                "Passes every check: the pocket is 5.70 mm, the size that held", "#2f7a4f")
    fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.02, wspace=0.06, hspace=0.08)
    fig.savefig(png, facecolor="white")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    test_print_storyboard(OUT / "test-print-storyboard.png")
    first, second = mesh_of(FIRST), mesh_of(SECOND)
    failed = [found for found in bridges.overhangs(first) if not found.ok]
    (OUT / "first-roof.svg").write_text(bridges.svg(failed[0]))
    centre = failed[0].region.centroid
    azim = math.degrees(math.atan2(centre.y - first.bounds.mean(axis=0)[1], centre.x - first.bounds.mean(axis=0)[0]))
    render(around(first, (centre.x, centre.y), 34.0), OUT / "first-design.png", azim, failed[0])
    render(around(second, (centre.x, centre.y), 34.0), OUT / "second-design.png", azim)
    render(first, OUT / "first-whole.png", azim, failed[0], elev=38)
    render(second, OUT / "second-whole.png", azim, elev=38)
    for name in ("first", "second"):
        whole_and_close_up(OUT / f"{name}-whole.png", OUT / f"{name}-design.png", OUT / f"{name}-whole-and-close-up.png")
    storyboard(OUT / "storyboard.png")
    print(f"wrote {', '.join(sorted(path.name for path in OUT.iterdir()))} to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
