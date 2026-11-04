"""Declining: the model hands in a design but holds back the part itself, because something it
needs isn't known. That's neither a pass nor a fail, and it never counts as a pass (Dan, issue 15).

Two signs, both read from what was handed in, never from the model's prose:
- No final part at all: nothing, or only test prints.
- A final part whose own code stops it on purpose: it didn't build because a `raise` in its
  code fired, and that `raise` sits under an `if` that reads a param handed in with no value.
  So the model wrote "don't build this until that's known" and left it unknown. The build keeps
  only the error's text, not where it was raised, so the error has to come from exactly one
  `raise` in the code: then that one fired, and its `if` was true.

An ordinary crash (a NameError, a CadQuery error, a guard on params that all have values) is
none of these, and stays a `builds` failure. A raise whose message isn't a plain string, such as
an f-string, isn't recognized.
"""
import ast
from typing import Iterator

from pbe.graders.checks import Finding
from pbe.parts.submission import Part, Submission


def _final_parts(sub: Submission) -> list[Part]:
    return [part for part in sub.parts if part.role == "final"]


def _build_errors(findings: list[Finding]) -> dict[str, str]:
    """Each part that didn't build, by id, with the error it stopped on."""
    return {finding.part: finding.detail for finding in findings if finding.check == "builds" and finding.ok is False}


def _raised(node: ast.Raise) -> str | None:
    """The error a `raise Name('message')` gives, as the build records it: "Name: message"."""
    call = node.exc
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.args):
        return None
    message = call.args[0]
    if not (isinstance(message, ast.Constant) and isinstance(message.value, str)):
        return None
    return f"{call.func.id}: {message.value}"


def _params_read(test: ast.expr) -> set[str]:
    """The params an `if` test reads, as p.<name>."""
    return {node.attr for node in ast.walk(test)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "p"}


def _parsed(code: str) -> ast.Module | None:
    try:
        return ast.parse(code)
    except SyntaxError:
        return None


def _raises_of(tree: ast.Module, error: str) -> int:
    """How many `raise` statements in the code give this error."""
    return sum(isinstance(node, ast.Raise) and _raised(node) == error for node in ast.walk(tree))


def _guards(tree: ast.Module) -> Iterator[tuple[set[str], str]]:
    """Each `if` in the code with a `raise` directly under it: (params its test reads, the error raised)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        for statement in node.body:
            if isinstance(statement, ast.Raise) and (error := _raised(statement)):
                yield _params_read(node.test), error


def _held_back_until(part: Part, error: str, sub: Submission) -> list[str]:
    """The params with no value that the `raise` this part stopped on waits for, or [] if it stopped some other way."""
    tree = _parsed(part.code)
    if tree is None or _raises_of(tree, error) != 1:  # with two, the guarded one may not be the one that fired
        return []
    unknown = {name for name, param in sub.params.items() if param.value is None}
    for read, raised in _guards(tree):
        if raised == error and read & unknown:
            return sorted(read & unknown)
    return []


def reason(sub: Submission, findings: list[Finding]) -> str | None:
    """Why this trial counts as declined, or None if it doesn't."""
    finals = _final_parts(sub)
    if not finals:
        test_prints = [part.id for part in sub.parts]
        return f"no final part: only test prints ({', '.join(test_prints)})" if test_prints else "no parts at all"
    errors = _build_errors(findings)
    for part in finals:
        waits_for = _held_back_until(part, errors[part.id], sub) if part.id in errors else []
        if waits_for:
            return f"{part.id}'s code stops on purpose until {', '.join(waits_for)} has a value ({errors[part.id]})"
    return None
