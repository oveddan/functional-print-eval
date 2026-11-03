"""Documentation images for the coupons: OpenSCAD renders of each piece and the
bridge check's view of each pocket on coupon A.

    uv run python coupons/render.py

Writes docs/media/coupons-round1/.
"""
import subprocess
from pathlib import Path

import trimesh

from coupons import OUT, cell_spans
from pbe.graders.bridges import overhangs, svg

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "docs/media/coupons-round1"

VIEWS = {  # name: (stl, color, transform, camera rot x,y,z, distance)
    "A-bridges-top": ("A-bridges", "#d9dfdb", "", (55, 0, 25), 330),
    "A-bridges-pockets": ("A-bridges", "#d9dfdb", "rotate([180,0,0])", (55, 0, 25), 330),
    "B-nuts": ("B-nuts", "#d9dfdb", "", (50, 0, 30), 220),
    "C-fits": ("C-fits", "#d9dfdb", "", (55, 0, 35), 170),
    "C-fits-tunnels": ("C-fits", "#d9dfdb", "", (75, 0, 70), 170),
    "C-pegs": ("C-pegs", "#e3a76f", "", (55, 0, 35), 140),
}


def render(name, stl, color, transform, rot, dist):
    scad = DEST / f"_{name}.scad"
    scad.write_text(f'color("{color}") {transform} import("{OUT / (stl + ".stl")}");\n')
    rot_x, rot_y, rot_z = rot
    subprocess.run(["openscad", "-o", str(DEST / f"{name}.png"), "--imgsize=1600,1000",
                    "--colorscheme=Tomorrow", "--autocenter", "--viewall",
                    f"--camera=0,0,0,{rot_x},{rot_y},{rot_z},{dist}", "--projection=p", str(scad)],
                   check=True, capture_output=True)
    scad.unlink()


def strand_views():
    found = overhangs(trimesh.load(OUT / "A-bridges.stl"))
    spans, _ = cell_spans()
    for name, _, _, start, end in spans:
        in_cell = sorted((overhang for overhang in found if start <= overhang.region.centroid.x <= end), key=lambda overhang: overhang.z)
        for number, overhang in enumerate(in_cell, start=1):
            (DEST / f"strands-{name}-{number}-z{overhang.z}.svg").write_text(svg(overhang))


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    for name, args in VIEWS.items():
        render(name, *args)
    strand_views()
    for path in sorted(DEST.iterdir()):
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
