"""Geometry checks on built parts. Each returns a list of Finding."""
from dataclasses import dataclass
from typing import NamedTuple

from pbe.parts.printer import printer


@dataclass
class Finding:
    check: str
    part: str
    ok: bool | None  # None: not graded, which is never a pass
    detail: str
    failure_class: str
    test_print: bool = False  # a generic check on a test print: reported, but it can't fail the trial (issue 15)


class Verdict(NamedTuple):
    """What a requirement's grader returns."""
    ok: bool | None  # None: not graded
    detail: str


def verdict_word(ok):
    if ok is None:
        return "not graded"
    return "pass" if ok else "FAIL"


def _built_parts(built):
    """The parts whose code ran: the other checks have nothing to read in one that didn't."""
    return [part for part in built.values() if part.ok]


def _printability(check, part, ok, detail):
    return Finding(check=check, part=part.part_id, ok=ok, detail=detail, failure_class="C6-printability",
                   test_print=part.role == "coupon")


def connected_bodies(built):
    """Each printed part must be one connected body (the tripod's floating hex peg). A sealed
    void in a part is a shell of its own too, but inside out, so its volume is negative. A test
    coupon may be several pieces on the bed, such as three separate pockets; each must rest on it."""
    findings = []
    for part in _built_parts(built):
        pieces = [shell for shell in part.mesh.split(only_watertight=False) if shell.volume > 0]
        count = len(pieces)
        if part.role != "coupon":
            findings.append(_printability("connected_bodies", part, count == 1, f"{count} bodies"))
            continue
        bed_z = part.mesh.bounds[0][2]
        all_on_bed = all(piece.bounds[0][2] <= bed_z + 0.01 for piece in pieces)
        how_many = "all" if all_on_bed else "not all"
        findings.append(_printability("connected_bodies", part, all_on_bed, f"{count} pieces, {how_many} on the bed"))
    return findings


def bed_fit(built):
    """The part, as oriented for printing, fits the build volume."""
    findings = []
    bed_x, bed_y, bed_z = printer().bed_mm
    for part in _built_parts(built):
        longer, shorter = sorted(part.mesh.extents[:2], reverse=True)
        height = part.mesh.extents[2]
        fits = longer <= max(bed_x, bed_y) and shorter <= min(bed_x, bed_y) and height <= bed_z
        detail = f"{longer:.1f} x {shorter:.1f} x {height:.1f} mm on a {bed_x} x {bed_y} x {bed_z} bed"
        findings.append(_printability("bed_fit", part, bool(fits), detail))
    return findings


def builds(built):
    """The part's code runs and produces a solid."""
    findings = []
    for part in built.values():
        detail = "built" if part.ok else part.error
        findings.append(_printability("builds", part, part.ok, detail))
    return findings


def _bridging_verdict(found):
    """(ok, detail) for one part's overhangs."""
    unbridgeable = [overhang for overhang in found if not overhang.ok and not overhang.narrow]
    unmeasured = [overhang for overhang in found if not overhang.ok and overhang.narrow]
    if unbridgeable:
        first = unbridgeable[0]
        return False, (f"{len(unbridgeable)} unbridgeable overhang(s); first at z = {first.z} mm, {first.region.area:.0f} mm²: "
                       f"best direction {first.best_angle}°, {first.anchored:.0%} of strands land on solid at both ends")
    if unmeasured:
        first = unmeasured[0]
        return None, (f"not measured: a {first.region.area:.0f} mm² ledge at z = {first.z} mm, too wide to be an "
                      "ordinary overhang and narrower than any roof seen to tangle")
    return True, "every overhang can be bridged"


def _with_declared_supports(ok, detail, supports):
    """A part the design's own instructions say to print with supports passes whatever its overhangs (Dan,
    2026-11-12: "if an existing design said to do supports, then it's fine"), saying what it would get without them."""
    if ok is True or not supports:
        return ok, detail
    return True, f'prints with supports, as the design\'s instructions say ("{supports}"); without them: {detail}'


def bridges(built):
    """Every overhang that needs a bridge can be bridged: in some direction, its
    strands land on solid at both ends (the Arca plate's tangled roof). A narrow ledge
    that fails this but that no print has measured is not graded. A part the design
    says to print with supports passes (pbe/parts/supports.py)."""
    from pbe.graders.bridges import overhangs

    findings = []
    for part in _built_parts(built):
        ok, detail = _with_declared_supports(*_bridging_verdict(overhangs(part.mesh)), part.supports)
        findings.append(_printability("bridges", part, ok, detail))
    return findings


ALL = [builds, connected_bodies, bed_fit, bridges]
