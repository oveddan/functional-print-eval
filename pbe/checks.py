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
    ok: bool | None  # None: not graded, which is never a pass
    detail: str
    failure_class: str


@cache
def bed():
    return yaml.safe_load((ROOT / "catalog/printer.yaml").read_text())["bed_mm"]


def connected_bodies(built):
    """Each printed part must be one connected body (the tripod's floating hex peg). A sealed
    void in a part is a shell of its own too, but inside out, so its volume is negative. A test
    coupon may be several pieces on the bed, such as three separate pockets; each must rest on it."""
    out = []
    for b in built.values():
        if not b.ok:
            continue
        pieces = [shell for shell in b.mesh.split(only_watertight=False) if shell.volume > 0]
        n = len(pieces)
        if b.role == "coupon":
            bed = b.mesh.bounds[0][2]
            ok = all(piece.bounds[0][2] <= bed + 0.01 for piece in pieces)
            out.append(Finding("connected_bodies", b.part, ok, f"{n} pieces, {'all' if ok else 'not all'} on the bed", "C6-printability"))
            continue
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
        out.append(Finding("bed_fit", b.part, bool(fits), f"{ex:.1f} x {ey:.1f} x {ez:.1f} mm on a {bx} x {by} x {bz} bed", "C6-printability"))
    return out


def builds(built):
    """The part's code runs and produces a solid."""
    return [Finding("builds", b.part, b.ok, "built" if b.ok else b.error, "C6-printability") for b in built.values()]


def bridges(built):
    """Every overhang that needs a bridge can be bridged: in some direction, its
    strands land on solid at both ends (the Arca plate's tangled roof). A narrow ledge
    that fails this but that no print has measured is not graded."""
    from pbe.bridges import overhangs

    out = []
    for b in built.values():
        if not b.ok:
            continue
        found = overhangs(b.mesh)
        bad = [o for o in found if not o.ok and not o.narrow]
        unmeasured = [o for o in found if not o.ok and o.narrow]
        if bad:
            o = bad[0]
            ok, detail = False, (f"{len(bad)} unbridgeable overhang(s); first at z = {o.z} mm, {o.region.area:.0f} mm²: "
                                 f"best direction {o.best_angle}°, {o.anchored:.0%} of strands land on solid at both ends")
        elif unmeasured:
            o = unmeasured[0]
            ok, detail = None, (f"not measured: a {o.region.area:.0f} mm² ledge at z = {o.z} mm, too wide to be an "
                                "ordinary overhang and narrower than any roof seen to tangle")
        else:
            ok, detail = True, "every overhang can be bridged"
        out.append(Finding("bridges", b.part, ok, detail, "C6-printability"))
    return out


ALL = [builds, connected_bodies, bed_fit, bridges]
