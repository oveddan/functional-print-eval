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


def render_png(stl, size=(880, 720)) -> bytes:
    """The part with its front half (y below the centre) cut away, seen from the front
    left and above, orthographic. Cropped to the part, transparent background."""
    stl = Path(stl).resolve()
    cx, cy, cz = trimesh.load(stl, force="mesh").bounds.mean(axis=0)
    scad = (f'difference() {{ import("{stl}"); '
            f'translate([{cx - 500:.3f}, {cy - 1000:.3f}, {cz - 500:.3f}]) cube([1000, 1000, 1000]); }}\n')
    with tempfile.TemporaryDirectory() as tmp:
        src, png = Path(tmp) / "cut.scad", Path(tmp) / "cut.png"
        src.write_text(scad)
        subprocess.run(["openscad", "-o", str(png), f"--imgsize={size[0]},{size[1]}", "--projection=o",
                        "--camera=0,0,0,62,0,325,100", "--viewall", "--autocenter", "--colorscheme=Tomorrow",
                        "--render=true", str(src)], check=True, capture_output=True, timeout=120)
        img = Image.open(png).convert("RGBA")
    a = np.asarray(img).copy()
    bg = (np.abs(a[..., :3].astype(int) - BACKGROUND).sum(axis=-1) <= 6)
    a[bg, 3] = 0
    img = Image.fromarray(a)
    img = img.crop(img.getbbox())
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def section_path(mesh: trimesh.Trimesh, scale=9.0, pad=14.0):
    """The section through the centre in the x-z plane (the cutaway's cut face), as SVG
    path data in px with z up. Returns (path, width, height)."""
    centre = mesh.bounds.mean(axis=0)
    sec = mesh.section(plane_origin=centre, plane_normal=[0, 1, 0])
    if sec is None:
        return "", 0, 0
    (x0, _, z0), (x1, _, z1) = mesh.bounds
    w, h = (x1 - x0) * scale + 2 * pad, (z1 - z0) * scale + 2 * pad
    loops = []
    for loop in sec.discrete:
        pts = [(pad + (p[0] - x0) * scale, h - pad - (p[2] - z0) * scale) for p in loop]
        loops.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z")
    return " ".join(loops), w, h


if __name__ == "__main__":
    Path(sys.argv[2]).write_bytes(render_png(sys.argv[1]))
