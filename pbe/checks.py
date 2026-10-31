"""Geometry checks on built parts. Each returns a list of Finding."""
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Finding:
    check: str
    part: str
    ok: bool
    detail: str
    failure_class: str


@cache
def bed():
    return yaml.safe_load((ROOT / "catalog/printer.yaml").read_text())["bed_mm"]


def connected_bodies(built):
    """Each printed part must be one connected body (the tripod's floating hex peg)."""
    out = []
    for b in built.values():
        if not b.ok:
            continue
        n = len(b.mesh.split(only_watertight=False))
        out.append(Finding("connected_bodies", b.part, n == 1, f"{n} bodies", "C6-printability"))
    return out


def bed_fit(built):
    """The part, as oriented for printing, fits the build volume."""
    out = []
    bx, by, bz = bed()
    for b in built.values():
        if not b.ok:
            continue
        ex, ey, ez = sorted(b.mesh.extents[:2], reverse=True) + [b.mesh.extents[2]]
        fits = ex <= max(bx, by) and ey <= min(bx, by) and ez <= bz
        out.append(Finding("bed_fit", b.part, fits, f"{ex:.1f} x {ey:.1f} x {ez:.1f} mm on a {bx} x {by} x {bz} bed", "C6-printability"))
    return out


def builds(built):
    """The part's code runs and produces a solid."""
    return [Finding("builds", b.part, b.ok, "built" if b.ok else b.error, "C6-printability") for b in built.values()]


def bridges(built):
    """Every overhang that needs a bridge can be bridged: in some direction, its
    strands land on solid at both ends (the Arca plate's tangled roof)."""
    from pbe.bridges import overhangs

    out = []
    for b in built.values():
        if not b.ok:
            continue
        bad = [o for o in overhangs(b.mesh) if not o.ok]
        if bad:
            o = bad[0]
            detail = (f"{len(bad)} unbridgeable overhang(s); first at z = {o.z} mm, {o.region.area:.0f} mm²: "
                      f"best direction {o.best_angle}°, {o.anchored:.0%} of strands land on solid at both ends")
        else:
            detail = "every overhang can be bridged"
        out.append(Finding("bridges", b.part, not bad, detail, "C6-printability"))
    return out


ALL = [builds, connected_bodies, bed_fit, bridges]
