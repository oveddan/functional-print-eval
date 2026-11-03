"""What the grading tests share: grade a design against its own task, and sort the findings."""
from pbe.parts import submission
from pbe.runner import agent, tasks


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
