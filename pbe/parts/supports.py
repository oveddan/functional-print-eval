"""Which parts a design's own instructions say to print with supports.

Dan, 2026-11-12: "I would say if an existing design said to do supports, then it's fine." So a part whose
instructions ask for supports passes the bridge check (pbe/graders/checks.py). New runs are told there are none
(pbe/runner/agent.py, NO_SUPPORTS), so this mostly matters for the trials saved before that.

Where a submission says how to print: the note, each part's print_orientation, and the manual's steps.
Claude's call on which part an instruction covers: a part's own print_orientation covers that part; a step
that lists parts covers those parts; a step that lists none, and the note, cover every part, since nothing
says which part they mean.
"""
import re
from dataclasses import dataclass

from pbe.parts.submission import Submission

SUPPORT_WORD = re.compile(r"\bsupports?\b", re.I)  # not "supporting", "supported" or "self-supporting"
ASKS = re.compile(
    r"\bprint\w*\b[^.;]*?\bwith\s+supports?\b"                  # print it with supports
    r"|\b(use|using|add|enable|enabled|tree|organic|auto)\s+supports?\b"  # enable supports, tree supports
    r"|\bturn\s+(on\s+supports?|supports?\s+on)\b"                 # turn supports on
    r"|\bsupports?\s*([:=]\s*(on|enabled)\b|\s(on|enabled)\s*([.;,(-]|$))"  # Support: ON, supports on.
    r"|\bsupports?\s+(under|beneath|below|inside)\b",              # supports under the roof
    re.I)
# a refusal, or a condition that leaves it to the slicer or the other orientation ("only if your slicer asks")
REFUSES = re.compile(r"\b(no|not|never|none|without|off|zero|disabled?|avoid|if|unless|otherwise)\b|n't\b|-free\b"
                     r"|\bother way\b", re.I)
CLAUSE_END = re.compile(r"(?<=[.;!?])\s+|\n")


def asks_for_supports(text: str) -> bool:
    """Does any sentence ask for supports, without saying not to use them? "Print with supports" and "tree
    supports under the roof" do; "no supports", "supports: none" and "doesn't need supports" don't. Claude's
    call: crediting supports needs a plain request, so a sentence that also says no, or makes them conditional
    ("only if your slicer asks", "if the roof is still loopy, reprint with supports"), doesn't count."""
    return bool(sentence_asking_for_supports(text))


def sentence_asking_for_supports(text: str) -> str:
    """The first sentence that asks for supports, or "" if none does."""
    for clause in CLAUSE_END.split(text):
        if SUPPORT_WORD.search(clause) and ASKS.search(clause) and not REFUSES.search(clause):
            return clause.strip()
    return ""


@dataclass
class Instruction:
    text: str
    parts: list[str]  # the part ids it covers


def _instructions(sub: Submission) -> list[Instruction]:
    every_part = [part.id for part in sub.parts]
    found = [Instruction(sub.note, every_part)]
    found += [Instruction(part.print_orientation, [part.id]) for part in sub.parts]
    found += [Instruction(step.text, step.parts or every_part) for step in sub.manual]
    return found


def printed_with_supports(sub: Submission) -> dict[str, str]:
    """Part id to the first sentence asking for supports for it, for the parts that have one."""
    asked = {}
    for instruction in _instructions(sub):
        sentence = sentence_asking_for_supports(instruction.text)
        if not sentence:
            continue
        for part_id in instruction.parts:
            asked.setdefault(part_id, sentence)
    return asked
