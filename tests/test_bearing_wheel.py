"""The bearing wheel: the reference passes every check, wrong designs fail the check aimed at them
and no other, and designs unlike the reference still pass. Not graded (ok = None) isn't failed: it's
what a check says when no recorded print can decide the case."""
from pbe.parts import submission
from pbe.runner import measure, tasks

from helpers import checked, failed, grade, not_graded, not_passing

REFERENCE = tasks.load("bearing-wheel").reference


def design(code=None, parts=None, **params):
    """The reference, changed only where a test says. New parts replace its parts and its criteria,
    and every step of the manual names all of them but a coupon."""
    sub = submission.parse(REFERENCE)
    for name, value in params.items():
        sub.params[name].value = value
    if code is not None:
        sub.parts[0].code = code
    if parts is not None:
        sub.parts = parts
        sub.criteria = []
        printed = [part.id for part in parts if part.id != "coupon"]
        for step in sub.manual:
            step.parts = list(printed)
    return checked(sub)


def part(part_id, code, role="final"):
    return submission.Part(id=part_id, role=role, material="PLA", print_orientation="flat", use_orientation="any", code=code)


# One bearing seat each side of a shoulder, the obvious design. Its lower seat's roof has a hole in it.
TWO_SEATS = '''
def build(p):
    body = cq.Workplane("XY").circle(p.across / 2).extrude(p.width)
    low = cq.Workplane("XY").circle(p.seat / 2).extrude(p.seat_h / 2)
    high = cq.Workplane("XY").workplane(offset=p.width - p.seat_h / 2).circle(p.seat / 2).extrude(p.seat_h / 2)
    return body.cut(low).cut(high).cut(cq.Workplane("XY").circle(p.relief / 2).extrude(p.width))
'''

# The same, with the roof stepped so each layer bridges from both sides.
STEPPED = TWO_SEATS.replace("    return body.cut(low)", '''    z = p.seat_h / 2
    strip = cq.Workplane("XY").workplane(offset=z).rect(p.relief, p.seat).extrude(0.4)
    box = cq.Workplane("XY").workplane(offset=z).rect(p.relief, p.relief).extrude(0.8)
    return body.cut(strip).cut(box).cut(low)''')

HALF = '''
def build(p):
    body = cq.Workplane("XY").circle(p.across / 2).extrude(p.width / 2)
    seat = cq.Workplane("XY").workplane(offset=p.width / 2 - p.seat_h / 2).circle(p.seat / 2).extrude(p.seat_h / 2)
    return body.cut(seat).cut(cq.Workplane("XY").circle(p.relief / 2).extrude(p.width))
'''

RIBS = '''
def build(p):
    import math
    body = cq.Workplane("XY").circle(p.across / 2).extrude(p.width)
    seat = cq.Workplane("XY").workplane(offset=p.width - p.seat_h).circle(p.seat / 2 + 0.5).extrude(p.seat_h)
    part = body.cut(seat).cut(cq.Workplane("XY").circle(p.relief / 2).extrude(p.width))
    for i in range(6):
        a = i * math.pi / 3
        r = p.seat / 2 + 0.75
        part = part.union(cq.Workplane("XY").workplane(offset=p.width - p.seat_h).center(r * math.cos(a), r * math.sin(a)).circle(0.75).extrude(p.seat_h))
    return part
'''

# Six crush ribs standing only 0.2 mm into a 22.2 mm seat, as Sonnet 5.5 drew them on the game spinner's
# first look: they add 3.4% to the hole's area, under PLAIN, so only the widest span shows them
SMALL_RIBS = '''
def build(p):
    import math
    body = cq.Workplane("XY").circle(p.across / 2).extrude(p.width)
    seat = cq.Workplane("XY").workplane(offset=p.width - p.seat_h).circle(p.seat / 2).extrude(p.seat_h)
    part = body.cut(seat).cut(cq.Workplane("XY").circle(p.relief / 2).extrude(p.width))
    for i in range(6):
        a = i * math.pi / 3
        r = p.seat / 2 + 1.0 - 0.2
        part = part.union(cq.Workplane("XY").workplane(offset=p.width - p.seat_h).center(r * math.cos(a), r * math.sin(a)).circle(1.0).extrude(p.seat_h))
    return part
'''

COUPON = '''
def build(p):
    body = cq.Workplane("XY").rect(32, 90).extrude(5)
    for i, d in enumerate([22.0, 22.1, 22.2]):
        body = body.cut(cq.Workplane("XY").center(0, 28 * (i - 1)).circle(d / 2).extrude(5))
    return body
'''


def test_reference_passes(tmp_path):
    findings = grade(design(), tmp_path)
    assert all(f.ok is True for f in findings), not_passing(findings)


def test_a_seat_each_side_with_a_plain_roof_fails_only_the_bridge_check(tmp_path):
    findings = grade(design(code=TWO_SEATS), tmp_path)
    assert failed(findings) == {"bridges"} and not not_graded(findings)


def test_a_stepped_roof_doesnt_fail(tmp_path):
    # the square step leaves small corners at the round hole, whose strands are short
    findings = grade(design(code=STEPPED), tmp_path)
    assert all(f.ok is True for f in findings), not_passing(findings)


def test_two_halves_pass(tmp_path):
    findings = grade(design(parts=[part("half_a", HALF), part("half_b", HALF)]), tmp_path)
    assert all(f.ok is True for f in findings), not_passing(findings)


def test_a_seat_too_tight_or_too_loose_fails_fit_only(tmp_path):
    # 22.0: round 2, won't go in; 22.05: round 3's H1, won't go in; 22.4: round 3's H2, too loose
    for d in (22.0, 22.05, 22.4):
        assert failed(grade(design(seat=d), tmp_path / str(d))) == {"R3"}


def test_a_seat_at_the_edges_of_what_held_passes(tmp_path):
    for d in (22.1, 22.3):
        findings = grade(design(seat=d), tmp_path / str(d))
        assert not failed(findings) and not not_graded(findings), not_passing(findings)


def test_a_seat_between_prints_takes_the_nearest_within_the_tolerance(tmp_path):
    # between 22.3, which held, and 22.4, which fell out: the nearer print decides, the tighter on a tie (assumed.py)
    findings = grade(design(seat=22.34), tmp_path / "a")
    assert not failed(findings) and not not_graded(findings), not_passing(findings)
    assert failed(grade(design(seat=22.37), tmp_path / "b")) == {"R3"}


def test_too_shallow_for_two_bearings_fails_room_only(tmp_path):
    findings = grade(design(seat_h=13), tmp_path)
    assert failed(findings) == {"R2"}


def test_a_bore_with_nothing_to_stop_the_bearings_passes(tmp_path):
    # round 3's H8, a 22.2 seat with no shoulder, held its bearing upside down
    findings = grade(design(relief=22.2), tmp_path)
    assert all(f.ok is True for f in findings), not_passing(findings)


def test_oversize_wheel_fails_size_only(tmp_path):
    assert failed(grade(design(across=80), tmp_path)) == {"R1"}


def test_too_wide_a_wheel_fails_size_only(tmp_path):
    assert failed(grade(design(width=24, seat_h=14.2), tmp_path)) == {"R1"}


def test_bolt_hole_too_small_fails_only_that(tmp_path):
    assert failed(grade(design(relief=7.8), tmp_path)) == {"R4"}


def test_a_bolt_hole_between_printed_holes_takes_the_nearest(tmp_path):
    # between round 3's 8.0, which the M8 only screwed through, and 8.1, which it went through by hand (assumed.py)
    assert failed(grade(design(relief=8.03), tmp_path / "a")) == {"R4"}
    assert "R4" not in failed(found := grade(design(relief=8.08), tmp_path / "b")) | not_graded(found)
    assert "R4" not in failed(found := grade(design(relief=8.3), tmp_path / "c")) | not_graded(found)


def test_bolt_hole_reads_round_3(tmp_path):
    # the M8 only screwed through 8.0, so the wheel would grip it; it went through 8.2 by hand
    assert failed(grade(design(relief=8.0), tmp_path / "8.0")) == {"R4"}
    findings = grade(design(relief=8.2), tmp_path / "8.2")
    assert all(f.ok is True for f in findings), not_passing(findings)


def test_ribs_arent_graded_on_fit(tmp_path):
    findings = grade(design(code=RIBS), tmp_path)
    assert "R3" in not_graded(findings) and "R3" not in failed(findings)


def test_small_crush_ribs_arent_graded_on_fit(tmp_path):
    findings = grade(design(code=SMALL_RIBS), tmp_path)
    assert not failed(findings) and not_graded(findings) == {"R3"}, not_passing(findings)


def test_coupon_rescues_a_wrong_seat(tmp_path):
    wheel = submission.parse(REFERENCE).parts[0]
    sub = design(parts=[wheel, part("coupon", COUPON, role="coupon")], seat=22.0)
    sub.manual[0].text = "Print coupon first, then the wheel at the size that holds."
    assert "R3" not in failed(grade(sub, tmp_path))


def test_coupon_not_in_the_manual_rescues_nothing(tmp_path):
    wheel = submission.parse(REFERENCE).parts[0]
    sub = design(parts=[wheel, part("coupon", COUPON, role="coupon")], seat=22.0)
    assert "R3" in failed(grade(sub, tmp_path))


def test_a_final_part_that_fails_isnt_read(tmp_path):
    findings = grade(design(code="def build(p):\n    raise ValueError('no')\n"), tmp_path)
    assert failed(findings) == {"builds"}


BOSSES = """
def build(p):
    body = cq.Workplane("XY").workplane(offset=3).circle(p.across / 2).extrude(10)
    boss = cq.Workplane("XY").circle(15).extrude(16)
    low = cq.Workplane("XY").circle(p.seat / 2).extrude(7.1)
    high = cq.Workplane("XY").workplane(offset=8.9).circle(p.seat / 2).extrude(7.1)
    return body.union(boss).cut(low).cut(high).cut(cq.Workplane("XY").circle(p.relief / 2).extrude(16))
"""

SLEEVE = """
def build(p):
    return cq.Workplane("XY").circle(6).extrude(14).cut(cq.Workplane("XY").circle(3).extrude(14))
"""

BLIND_COUPON = COUPON.replace(".circle(d / 2).extrude(5))", ".workplane(offset=1).circle(d / 2).extrude(4))")


def test_seats_running_into_hub_bosses_are_read_whole(tmp_path):
    findings = grade(design(code=BOSSES), tmp_path)
    assert failed(findings) == {"bridges"} and not not_graded(findings)


def test_a_printed_sleeve_too_small_for_the_bolt_fails(tmp_path):
    wheel = submission.parse(REFERENCE).parts[0]
    assert failed(grade(design(parts=[wheel, part("sleeve", SLEEVE)]), tmp_path)) == {"R4"}


def test_a_coupon_of_blind_pockets_rescues_too(tmp_path):
    wheel = submission.parse(REFERENCE).parts[0]
    sub = design(parts=[wheel, part("coupon", BLIND_COUPON, role="coupon")], seat=22.0)
    sub.manual[0].text = "Print coupon first, then the wheel at the size that holds."
    assert "R3" not in failed(grade(sub, tmp_path))


def test_the_person_can_answer_about_the_bearing():
    person = measure.Person(tasks.load("bearing-wheel").hidden_facts)
    assert "22" in person.measure("608 bearing", "outside diameter")


def test_a_bearing_a_little_proud_passes(tmp_path):
    # round 3's H5 to H7 held a 608 standing 0.2 to 0.6 mm proud of its seat
    findings = grade(design(seat_h=13.8), tmp_path)
    assert all(f.ok is True for f in findings), not_passing(findings)

