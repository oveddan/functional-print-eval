"""Headless pictures of a built part, for reports: a cutaway rendered by OpenSCAD (PNG)
and the exact section through the part's middle (SVG path data, from the mesh).

    uv run python -m pbe.render results/runs/<run>/.../parts/spacer.stl out.png
"""
import io
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

BACKGROUND = (248, 248, 248)  # OpenSCAD's "Tomorrow" colour scheme; made transparent after


def _cutaway_scad(stl):
    """OpenSCAD source for the part with everything in front of its centre (lower y) cut away."""
    centre_x, centre_y, centre_z = trimesh.load(stl, force="mesh").bounds.mean(axis=0)
    return (f'difference() {{ import("{stl}"); '
            f'translate([{centre_x - 500:.3f}, {centre_y - 1000:.3f}, {centre_z - 500:.3f}]) cube([1000, 1000, 1000]); }}\n')


def _openscad_png(scad, size):
    """OpenSCAD's render of `scad`, seen from the front left and above, orthographic."""
    with tempfile.TemporaryDirectory() as tmp:
        source, png = Path(tmp) / "cut.scad", Path(tmp) / "cut.png"
        source.write_text(scad)
        subprocess.run(["openscad", "-o", str(png), f"--imgsize={size[0]},{size[1]}", "--projection=o",
                        "--camera=0,0,0,62,0,325,100", "--viewall", "--autocenter", "--colorscheme=Tomorrow",
                        "--render=true", str(source)], check=True, capture_output=True, timeout=120)
        return Image.open(png).convert("RGBA")


def _clear_background(image):
    """The image with OpenSCAD's background made transparent, cropped to what's left."""
    pixels = np.asarray(image).copy()
    is_background = np.abs(pixels[..., :3].astype(int) - BACKGROUND).sum(axis=-1) <= 6
    pixels[is_background, 3] = 0
    cleared = Image.fromarray(pixels)
    return cleared.crop(cleared.getbbox())


def render_png(stl, size=(880, 720)) -> bytes:
    """The part with its front half (y below the centre) cut away, seen from the front
    left and above, orthographic. Cropped to the part, transparent background."""
    stl = Path(stl).resolve()
    image = _clear_background(_openscad_png(_cutaway_scad(stl), size))
    png = io.BytesIO()
    image.save(png, "PNG", optimize=True)
    return png.getvalue()


def section_path(mesh: trimesh.Trimesh, scale=9.0, pad=14.0):
    """The section through the centre in the x-z plane (the cutaway's cut face), as SVG
    path data in px with z up. Returns (path, width, height)."""
    centre = mesh.bounds.mean(axis=0)
    cut = mesh.section(plane_origin=centre, plane_normal=[0, 1, 0])
    if cut is None:
        return "", 0, 0
    (x0, _, z0), (x1, _, z1) = mesh.bounds
    width, height = (x1 - x0) * scale + 2 * pad, (z1 - z0) * scale + 2 * pad

    def to_px(point):
        return pad + (point[0] - x0) * scale, height - pad - (point[2] - z0) * scale
    loops = []
    for loop in cut.discrete:
        points = [to_px(point) for point in loop]
        loops.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points) + " Z")
    return " ".join(loops), width, height


if __name__ == "__main__":
    Path(sys.argv[2]).write_bytes(render_png(sys.argv[1]))
