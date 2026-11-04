"""What a trial's findings come to (issue 15): a test print can't fail a trial on its own, and a
trial that holds back its part because something it needs isn't known is declined, which is
neither a pass nor a fail."""
from pbe import eval as runner
from pbe.graders import checks, declined
from pbe.parts import submission
from pbe.parts.build import Built
from pbe.runner import agent, tasks
from pbe.runner.trial_record import TrialRecord

from helpers import a_record, grade

BLOCK = 'def build(p):\n    return cq.Workplane("XY").box(20, 20, 5)\n'
STOPS_UNTIL_MEASURED = ("def build(p):\n    if p.socket_depth is None:\n        raise ValueError('STOP: measure the socket first.')\n"
                        '    return cq.Workplane("XY").box(20, 20, 5)\n')


def a_part(part_id, role, code=BLOCK):
    return submission.Part(id=part_id, role=role, material="PLA", code=code, print_orientation="flat", use_orientation="flat")


def a_design(*parts, **params):
    values = {name: submission.Param(value=value, unit="mm", kind="world", source="unknown" if value is None else "measured")
              for name, value in params.items()}
    return submission.Submission(task="t", params=values, parts=list(parts))


def finding(check, ok, part="-", test_print=False, detail=""):
    return checks.Finding(check, part, ok, detail, "", test_print=test_print)


def build_failed(part_id, error):
    return finding("builds", False, part_id, detail=error)


def test_a_broken_test_print_is_reported_but_doesnt_fail_the_trial():
    record = a_record(outcome="submitted")
    record.set_verdict([finding("builds", False, "coupon", test_print=True), finding("R1", True), finding("R4", None)])
    assert record.failed_checks == [] and record.test_print_failed_checks == ["builds"]
    assert record.verdict == "not graded" and record.all_pass is False


def test_a_test_print_cant_make_a_trial_pass_either():
    record = a_record(outcome="submitted")
    record.set_verdict([finding("bridges", True, "coupon", test_print=True), finding("R1", False)])
    assert record.verdict == "fail" and record.failed_checks == ["R1"]


def test_the_generic_checks_mark_findings_on_test_prints(tmp_path):
    sub = submission.parse(tasks.load("nut-knob/M5").reference)
    sub.parts.append(sub.parts[0].model_copy(update={"id": "coupon", "role": "coupon", "code": "def build(p):\n    return math.pi\n"}))
    findings = grade(sub, tmp_path)
    on_coupon = [f for f in findings if f.part == "coupon"]
    assert on_coupon and all(f.test_print for f in on_coupon)
    assert not any(f.test_print for f in findings if f.part != "coupon")
    record = a_record(outcome="submitted")
    record.set_verdict(findings)
    assert record.verdict == "pass" and record.test_print_failed_checks == ["builds"]


def test_handing_in_only_test_prints_or_nothing_is_declined():
    assert declined.reason(a_design(a_part("bolt_fit_coupon", "coupon")), []) == "no final part: only test prints (bolt_fit_coupon)"
    assert declined.reason(a_design(), []) == "no parts at all"


def test_a_part_whose_own_code_stops_until_a_missing_measurement_is_declined():
    sub = a_design(a_part("plate", "final", STOPS_UNTIL_MEASURED), socket_depth=None)
    reason = declined.reason(sub, [build_failed("plate", "ValueError: STOP: measure the socket first.")])
    assert reason == "plate's code stops on purpose until socket_depth has a value (ValueError: STOP: measure the socket first.)"


def test_an_ordinary_crash_is_not_declined():
    # a missing param elsewhere doesn't make an ordinary crash a decline
    sub = a_design(a_part("plate", "final", "def build(p):\n    return sqrt(2)\n"), socket_depth=None)
    assert declined.reason(sub, [build_failed("plate", "NameError: name 'sqrt' is not defined")]) is None


def test_a_stop_whose_message_another_raise_shares_is_not_declined():
    # Codex's case: the guarded raise was skipped, and an unguarded one with the same message fired
    code = ("def build(p):\n    if p.depth is not None:\n        raise ValueError('invalid dimensions')\n"
            "    raise ValueError('invalid dimensions')\n")
    sub = a_design(a_part("plate", "final", code), depth=None)
    assert declined.reason(sub, [build_failed("plate", "ValueError: invalid dimensions")]) is None


def test_a_guard_on_params_that_all_have_values_is_not_declined():
    code = "def build(p):\n    if p.socket_depth < 5:\n        raise ValueError('too shallow')\n    return None\n"
    sub = a_design(a_part("plate", "final", code), socket_depth=4.0)
    assert declined.reason(sub, [build_failed("plate", "ValueError: too shallow")]) is None


def test_a_part_that_built_is_not_declined():
    sub = a_design(a_part("plate", "final", STOPS_UNTIL_MEASURED), socket_depth=6.0)
    assert declined.reason(sub, [finding("builds", True, "plate")]) is None


def test_declined_is_neither_a_pass_nor_a_fail():
    record = a_record(outcome="submitted")
    record.set_verdict([finding("R1", True)], declined="no parts at all")
    assert record.verdict == "declined" and record.all_pass is False


def test_a_declined_record_reads_back_with_its_reason(tmp_path):
    record = a_record(outcome="submitted")
    record.set_verdict([finding("bridges", False, "coupon", test_print=True)], declined="no parts at all")
    record.keep_verdict_as_earlier()
    record.save(tmp_path)
    again = TrialRecord.load(tmp_path)
    assert again.declined == "no parts at all" and again.regrades[0].declined == "no parts at all"
    assert again.findings[0].test_print and again.as_saved() == record.as_saved()


def test_an_older_record_has_no_declined_or_test_print_fields(tmp_path):
    record = a_record(outcome="submitted")
    record.set_verdict([finding("R1", False)])
    saved = record.as_saved()
    assert "declined" not in saved and "test_print" not in saved["findings"][0]


def test_a_regrade_replaces_a_verdict_only_when_what_decides_it_changes():
    old = a_record(outcome="submitted")
    old.set_verdict([finding("bridges", True, "coupon"), finding("builds", False, "coupon"), finding("R1", True)])
    marked_pass = old.model_copy(deep=True)
    marked_pass.set_verdict([finding("bridges", True, "coupon", test_print=True), finding("builds", False, "coupon"), finding("R1", True)])
    assert runner.what_decides(marked_pass) == runner.what_decides(old)
    marked_failure = old.model_copy(deep=True)
    marked_failure.set_verdict([finding("bridges", True, "coupon", test_print=True), finding("builds", False, "coupon", test_print=True),
                                finding("R1", True)])
    assert runner.what_decides(marked_failure) != runner.what_decides(old)


def test_a_declined_trial_counts_no_failure_by_check():
    record = a_record(outcome="submitted")
    record.set_verdict([finding("R1", False)], declined="no parts at all")
    assert record.failed_checks == [] and record.not_graded_checks == []


def test_a_check_that_crashes_on_a_test_print_doesnt_fail_the_trial():
    def breaks_on_test_prints(built):
        if any(part.role == "coupon" for part in built.values()):
            raise ValueError("bad mesh")
        return [finding("bridges", True, part_id) for part_id in built]
    breaks_on_test_prints.__name__ = "bridges"
    built = {"knob": Built("knob", True, role="final"), "coupon": Built("coupon", True, role="coupon")}
    findings = agent._run_check(breaks_on_test_prints, built)
    assert [(f.part, f.ok, f.test_print) for f in findings] == [("knob", True, False), ("coupon", False, True)]
