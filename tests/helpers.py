"""What the grading tests share: grade a design against its own task, and sort the findings."""
from pbe.parts import submission
from pbe.runner import agent, tasks
from pbe.runner.trial_record import TrialRecord


def grade(sub, tmp_path):
    return agent.grade(tasks.load(sub.task), sub, tmp_path)


def failed(findings):
    return {finding.check for finding in findings if finding.ok is False}


def not_graded(findings):
    return {finding.check for finding in findings if finding.ok is None}


def not_passing(findings):
    """The findings that didn't pass, for an assertion's message."""
    return [finding for finding in findings if finding.ok is not True]


def checked(sub):
    """The design checked again as a submission, after a test has changed it."""
    return submission.Submission.model_validate(sub.model_dump())


def a_record(**fields):
    """A saved trial with nothing in it, with these fields set."""
    settings = {"max_turns": 1, "max_tokens": 10, "temperature": "provider default"}
    return TrialRecord(**{"task": "t", "model": "m", "condition": "can_ask", "outcome": "no_submission", "error": None, "turns": 1,
                          "repairs": 0, "measures": [], "revealed": [], "hidden": [], "limitations": [], "cost_usd": 0.0,
                          "elapsed_s": 0.0, "settings": settings, "calls": [], **fields})


# The prompt changes made after the saved trials ran, each in CHANGELOG.md: (the saved trials' words, today's).
# A test comparing today's prompt with a saved one applies these and expects nothing else to differ.
BRIDGE_LINE = "- Longest bridge seen to print cleanly on this setup: 50 mm\n"
PROMPT_CHANGES_SINCE_SAVED = [
    # 2026-11-12: every condition is told there are no supports, not only can_test
    (BRIDGE_LINE, BRIDGE_LINE + agent.NO_SUPPORTS + "\n"),
    # 2026-11-11: the 25T aluminium horn has no clamp screw, and its hub measured three ways (Dan)
    ("      aluminium single arm with a clamped split hub and 2 holes (IMG_5457-5458). aluminium\n"
     "      arm measured below",
     "      aluminium single arm with 2 holes and no clamp screw (Dan, 2026-11-11) (IMG_5457-5458).\n"
     "      aluminium arm measured below"),
    ("    hub_od:\n      measured: 14.66\n",
     "    hub_od:\n      measured:\n      - 14.66\n      - 14.68\n      - 14.63\n"
     "      note: 14.68 along the arm and 14.63 across it (Dan, 2026-11-11, IMG_6151-6152);\n"
     "        round enough for a round pocket\n"),
    ("      note: 3.13 (likely the clamp screw hole), 1.52, 4.43, 65.88 (heard as '6.5.88');\n        features unconfirmed\n",
     "      note: '3.13 (not a clamp screw: the horn has none, Dan 2026-11-11), 1.52, 4.43,\n"
     "        65.88 (heard as ''6.5.88''); features unconfirmed'\n"),
]


def saved_prompt_as_today(saved: str) -> str:
    """A saved trial's system prompt with the documented changes since it ran, each found exactly once."""
    for before, after in PROMPT_CHANGES_SINCE_SAVED:
        assert saved.count(before) == 1, before
        saved = saved.replace(before, after)
    return saved
