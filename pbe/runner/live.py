"""A live session: the same agent, with a person answering its tools in a real build.

In the eval, measure is answered from the task's table and print_test from the recorded prints. Here both are
answered by the person: at the terminal, or from a file of answers written beforehand. The prompt, the tools
and the hand-in format don't change (agent.run_trial takes the two answerers as arguments).

Every question and answer is kept in session.yaml beside the transcript. That file is itself a valid answers
file, so a session can be run again without the person, on the same model or another one:

    things:                      # optional: measurements taken beforehand, in a task's hidden_facts.yaml format
      desk:
        measurements:
          thickness: {value: 38, unit: mm, note: at the edge}
    measures:                    # what was asked and answered, word for word
      - {item: desk, what: thickness at the edge, answer: 38 mm}
                                 # a session's own entries also keep the sketch shown, if the agent sent one
    test_prints:                 # one entry per print_test call, in order: what the person said of each piece
      - pieces: {pocket_test: the nut pressed in at 5.7 and stayed in when I shook it}
                                 # a session's own entries also keep each piece's shape, and an answer is replayed
                                 # only for a piece of the same shape

A recorded answer is found by the same item and wording, then by `things` through the eval's own lookup
(runner/measure.py), then the person is asked. With nobody at the terminal, an unanswered measurement gets the
eval's "I can't measure that" and an unanswered test piece "I didn't print that one".

A live session's measure also takes an optional sketch: an SVG with numbered dimensions, which the person is shown
and answers by number (runner/sketch.py). It's checked before it's saved or opened, and kept in sketches/ beside
the transcript, so a replay shows exactly what was asked. The eval's scripted conditions don't offer it.
"""
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from pbe.parts.build import build_parts
from pbe.parts.submission import Submission
from pbe.runner import sketch as sketches
from pbe.runner.coupon_loop import ReportLine
from pbe.runner.agent import NOT_PRINTED_BASIS
from pbe.runner.measure import NO_ANSWER, Person, Thing
from pbe.runner.sketch import BadSketch, Dimension, Sketch
from pbe.runner.trial_record import Measurement

SESSION_FILE = "session.yaml"
DIDNT_PRINT = "I didn't print that one."
DIDNT_BUILD = "it didn't come out: the file wouldn't open."  # as the eval's person says of a piece that didn't build
SKETCHES = "sketches"  # the folder, beside the transcript, that keeps each sketch a measure call sent
Ask = Callable[[str], str]  # a question put to the person; "" if they don't answer
Show = Callable[[Path], bool]  # open a saved sketch for the person; False if it couldn't be opened
MeasureSource = Literal["answers file", "things", "terminal", "nobody answered", "sketch refused"]
NOT_ANSWERS = ("nobody answered", "sketch refused")


class Measured(BaseModel):
    """One measure call, and what the person answered."""
    model_config = ConfigDict(extra="forbid")
    item: str
    what: str = ""
    answer: str
    source: MeasureSource = "answers file"
    sketch: str | None = None  # the sketch shown with the question, as a file beside session.yaml
    sketch_sha: str | None = None  # which drawing and numbering the answer is for; a replay uses it only for the same one
    dimensions: list[Dimension] = []  # what each number in the sketch asked for


class PiecesPrinted(BaseModel):
    """One print_test call: what the person said of each piece, by part id."""
    model_config = ConfigDict(extra="forbid")
    pieces: dict[str, str]
    shapes: dict[str, str] = {}  # each piece's code and params, hashed: a replay answers only for the same piece.
    # An answers file written by hand has none, and then the part id alone decides.


class Answers(BaseModel):
    """A file of answers, and the answers a session collected."""
    model_config = ConfigDict(extra="forbid")
    things: dict[str, Thing] = {}
    measures: list[Measured] = []
    test_prints: list[PiecesPrinted] = []


class Session(BaseModel):
    """session.yaml: what was asked for, who designed it, and every answer the person gave."""
    model_config = ConfigDict(extra="forbid")
    request: str
    task: str
    model: str
    condition: str
    answers: Answers

    def as_saved(self) -> dict:
        """The fields session.yaml keeps: a measurement asked without a sketch has no sketch fields."""
        fields = self.model_dump(exclude_none=True)
        for told in fields["answers"]["measures"]:
            if not told["dimensions"]:
                del told["dimensions"]
        return fields

    def save(self, folder: Path) -> None:
        text = yaml.safe_dump(self.as_saved(), sort_keys=False, allow_unicode=True, width=1000)
        (Path(folder) / SESSION_FILE).write_text(text)


def load_answers(path) -> Answers:
    """A file of answers, or the answers of a saved session.yaml."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    return Session.model_validate(data).answers if "answers" in data else Answers.model_validate(data)


def _wording(text: str) -> str:
    return " ".join(text.lower().split())


def _sha(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def piece_shape(part, params: dict) -> str:
    """What decides a test piece's shape: its code and the values it's built from."""
    return _sha(part.code, {name: param.value for name, param in params.items()})


def sketch_sha(sketch: Sketch) -> str:
    return _sha(sketch.svg, [(dimension.number, dimension.what) for dimension in sketch.dimensions])


def measure_question(item: str, what: str) -> str:
    return f"The agent asks you to measure: {item}" + (f", {what}" if what else "")


def sketch_question(item: str, what: str, sketch: Sketch, path: Path | None, opened: bool) -> str:
    """The question with its sketch: where the drawing is, what each number asks for, and how to answer."""
    where = "Sketch: not saved" if path is None else f"Sketch: {path}" + (" (opened in your browser)" if opened else " (open it to see the numbers)")
    numbered = [f"  {dimension.number}: {dimension.what}" for dimension in sketch.dimensions]
    return "\n".join([measure_question(item, what), where, *numbered, 'Answer by number, e.g. "1: 25.2 mm, 2: 40 mm".'])


def print_question(part_id: str, stl: Path) -> str:
    return f"Test piece {part_id}: {stl}\nHow did it come out? (Enter if you didn't print it)"


class LivePerson:
    """The person in a live session. It has what agent.run_trial reads of runner/measure.py's Person."""

    def __init__(self, answers: Answers | None = None, ask: Ask | None = None, folder: Path | None = None,
                 show: Show | None = None):
        answers = answers or Answers()
        self.ask = ask  # None: nobody at the terminal
        self.folder = Path(folder) if folder else None  # where sketches are kept; None: they aren't
        self.show = show  # None: a sketch is saved and its path given, not opened
        self.lookup = Person({name: thing.model_dump() for name, thing in answers.things.items()})
        self.things = self.lookup.things
        # only what the person answered is replayed: a refused sketch's reply was to the model, and a question
        # nobody answered is asked again
        self.recorded = {(_wording(told.item), _wording(told.what)): told for told in answers.measures
                         if told.source not in NOT_ANSWERS}
        self.log: list[Measurement] = []
        self.revealed: list[str] = []
        self.measured: list[Measured] = []  # this session's answers, in order

    def _from_things(self, item, what) -> tuple[str, list[str]] | None:
        """The eval's lookup on the measurements taken beforehand, or None if it finds none."""
        reply = self.lookup.measure(item, what)
        return None if reply == NO_ANSWER else (reply, self.lookup.log[-1].revealed)

    def _recorded_answer(self, item, what, drawing: str | None) -> str | None:
        """The answer recorded for this wording, if it was given for this drawing: an answer by number says
        nothing about a sketch numbered differently, or about no sketch at all."""
        told = self.recorded.get((_wording(item), _wording(what)))
        if told is None or (told.sketch_sha is not None and told.sketch_sha != drawing):
            return None
        return told.answer

    def _answer(self, item, what, question, drawing: str | None = None) -> tuple[str, MeasureSource, list[str]]:
        """A recorded answer, then the measurements taken beforehand, then the person. `question` is only made,
        and a sketch only opened, if it comes to asking them."""
        recorded = self._recorded_answer(item, what, drawing)
        if recorded is not None:
            return recorded, "answers file", []
        if found := self._from_things(item, what):
            return found[0], "things", found[1]
        said = self.ask(question()).strip() if self.ask else ""
        return (said, "terminal", []) if said else (NO_ANSWER, "nobody answered", [])

    def _keep(self, item, what, reply, source, revealed, sketch_file=None, sketch: Sketch | None = None):
        self.revealed += [name for name in revealed if name not in self.revealed]
        self.log.append(Measurement(item=item, what=what, revealed=revealed, reply=reply))
        self.measured.append(Measured(item=item, what=what, answer=reply, source=source, sketch=sketch_file,
                                      sketch_sha=sketch_sha(sketch) if sketch else None,
                                      dimensions=list(sketch.dimensions) if sketch else []))
        return reply

    def _saved(self, sketch: Sketch) -> Path | None:
        """The sketch as a file beside the transcript, numbered by the measure call it came with."""
        if self.folder is None:
            return None
        return sketches.save(sketch, self.folder / SKETCHES / f"{len(self.measured) + 1}.svg")

    def _measure_with_sketch(self, item, what, arguments) -> str:
        try:
            sketch = sketches.checked(arguments)
        except BadSketch as e:  # nothing of it is saved or opened; the model hears why and can send it again
            return self._keep(item, what, sketches.sent_back(e), "sketch refused", [])
        path = self._saved(sketch)

        def question():
            opened = bool(path and self.show and self.show(path))
            return sketch_question(item, what, sketch, path, opened)
        reply, source, revealed = self._answer(item, what, question, sketch_sha(sketch))
        sketch_file = f"{SKETCHES}/{path.name}" if path else None
        return self._keep(item, what, reply, source, revealed, sketch_file, sketch)

    def measure(self, item: str, what: str = "", sketch=None) -> str:
        """`sketch` is the measure call's sketch argument, as the model sent it, or None."""
        if sketch is not None:
            return self._measure_with_sketch(item, what, sketch)
        reply, source, revealed = self._answer(item, what, lambda: measure_question(item, what))
        return self._keep(item, what, reply, source, revealed)

    def every_measurement(self):
        return self.lookup.every_measurement()

    def all_measurements(self) -> str:
        return self.lookup.all_measurements()


class LiveTestPrints:
    """print_test in a live session: each piece is built and saved as an STL to print, and the person says how
    it came out. Whether to print it is theirs to decide."""

    def __init__(self, folder: Path, answers: Answers | None = None, ask: Ask | None = None):
        self.folder = Path(folder)
        self.recorded = list((answers or Answers()).test_prints)
        self.ask = ask
        self.printed: list[PiecesPrinted] = []  # this session's answers, in order

    def _recorded_answer(self, part_id, shape, recorded: PiecesPrinted | None) -> str | None:
        """What the person said of this piece before, if it was this shape and they printed it. A piece with the
        same name and another shape wasn't printed, and one they didn't print is asked about again."""
        if recorded is None or recorded.pieces.get(part_id, DIDNT_PRINT) == DIDNT_PRINT:
            return None
        if recorded.shapes.get(part_id, shape) != shape:
            return None
        return recorded.pieces[part_id]

    def _said(self, part_id, shape, stl, recorded: PiecesPrinted | None) -> str:
        said_before = self._recorded_answer(part_id, shape, recorded)
        if said_before is not None:
            return said_before
        said = self.ask(print_question(part_id, stl)).strip() if self.ask else ""
        return said or DIDNT_PRINT

    def __call__(self, task, pieces: Submission) -> dict[str, list[ReportLine]]:
        call = len(self.printed)
        recorded = self.recorded[call] if call < len(self.recorded) else None
        built = build_parts(pieces, self.folder / "test_prints" / str(call + 1))
        report, said_of, shapes = {}, {}, {}
        for part in pieces.parts:
            piece = built.get(part.id)
            if piece is None or not piece.ok:
                report[part.id] = [ReportLine(DIDNT_BUILD, "build error")]
                continue
            shapes[part.id] = piece_shape(part, pieces.params)
            said = said_of[part.id] = self._said(part.id, shapes[part.id], piece.stl, recorded)
            report[part.id] = [ReportLine(said, NOT_PRINTED_BASIS if said == DIDNT_PRINT else "live answer")]
        self.printed.append(PiecesPrinted(pieces=said_of, shapes=shapes))
        return report


def collected(person: LivePerson, test_prints: LiveTestPrints) -> Answers:
    """What the session answered, with the measurements taken beforehand carried over, as a file of answers."""
    return Answers(things=person.things, measures=person.measured, test_prints=test_prints.printed)
