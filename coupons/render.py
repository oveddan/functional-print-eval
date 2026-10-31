"""Documentation images for the coupons: OpenSCAD renders of each piece and the
bridge check's view of each pocket on coupon A.

    uv run python coupons/render.py

Writes docs/media/coupons-round1/.
"""
import subprocess
from pathlib import Path

import trimesh

from coupons import A_WALL, BRIDGE_CELLS, OUT
from pbe.bridges import overhangs, svg

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
    rx, ry, rz = rot
    subprocess.run(["openscad", "-o", str(DEST / f"{name}.png"), "--imgsize=1600,1000",
                    "--colorscheme=Tomorrow", "--autocenter", "--viewall",
                    f"--camera=0,0,0,{rx},{ry},{rz},{dist}", "--projection=p", str(scad)],
                   check=True, capture_output=True)
    scad.unlink()


def strand_views():
    found = overhangs(trimesh.load(OUT / "A-bridges.stl"))
    x = A_WALL
    for name, size, _ in BRIDGE_CELLS:
        lo, hi = x, x + size
        x += size + A_WALL
        mine = sorted((o for o in found if lo <= o.region.centroid.x <= hi), key=lambda o: o.z)
        for i, o in enumerate(mine):
            (DEST / f"strands-{name}-{i + 1}-z{o.z}.svg").write_text(svg(o))


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    for name, args in VIEWS.items():
        render(name, *args)
    strand_views()
    for p in sorted(DEST.iterdir()):
        print(p.relative_to(ROOT))


if __name__ == "__main__":
    main()
