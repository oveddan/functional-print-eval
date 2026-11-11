"""Use the eval's designer agent on a real part: a live session.

    uv run python -m pbe.live "I need a clamp for a 25 mm tube..." --model anthropic/claude-sonnet-5.5 --budget 0.50
    uv run python -m pbe.live "..." --model ... --answers measured.yaml      # measurements taken beforehand
    uv run python -m pbe.live --task nut-knob/M5 --model ... --answers results/local/live/<session>/.../session.yaml

The agent's prompt and hand-in format are the eval's, and so are its tools but for one optional addition, a
sketch on measure. What changes is who answers: measure and print_test
go to you at the terminal, or to a file of answers (pbe/runner/live.py has its format). The agent may send a
numbered sketch with a measurement, which opens in your browser so you can answer by number. Each test piece is
saved as an STL for you to print, or not: that's your call. The session is saved under results/local/live/
(not committed): transcript.json, session.yaml (every question and your answer, itself a valid --answers file,
so the session can be run again without you), the hand-in, its parts as STL, and the pre-print check's
predictions, which this prints at the end.
"""
import argparse
import sys
import webbrowser
from functools import partial
from pathlib import Path

from pbe import eval as pbe_eval
from pbe import preprint, try_request
from pbe.runner import agent, live, llm, tasks
from pbe.runner.live import Answers, Ask, LivePerson, LiveTestPrints, Session, Show
from pbe.runner.trial_record import TrialRecord

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/local/live"
DEFAULT_CONDITION = agent.TEST_CONDITION  # the agent may ask for test prints before its final design


def at_terminal(question: str) -> str:
    """Put a question to the person at the terminal. An empty line, or no terminal, is no answer."""
    print(f"\n{question}", file=sys.stderr)
    try:
        return input("> ")
    except EOFError:
        return ""


def in_browser(path: Path) -> bool:
    """Open a saved sketch in the default browser. False if there's none to open it with."""
    try:
        return webbrowser.open(path.resolve().as_uri())
    except (webbrowser.Error, OSError):
        return False


def session_task(request, task_id):
    """One of the eval's tasks, with its request and requirements, or a throwaway task from the person's own words."""
    return tasks.load(task_id) if task_id else tasks.from_request(request or "")


def run_folder(task, now=None) -> Path:
    """A new folder for this session, named as pbe.try_request names a try: when it ran and the request's first words."""
    return OUT / try_request.run_folder(task.request, now).name


def run(task, model, run_dir, answers: Answers | None = None, ask: Ask | None = None, condition=DEFAULT_CONDITION,
        budget=0.50, max_turns=None, max_tokens=32000, chat=llm.chat, show: Show | None = None) -> tuple[TrialRecord, Path, Session]:
    """One live session on the task, saved under run_dir: (its record, its folder, what the person answered)."""
    folder = pbe_eval.trial_folder(run_dir, task, condition, model, 1)
    if folder.exists():
        raise FileExistsError(f"{folder} already holds a session: save this one somewhere new")
    person = LivePerson(answers, ask, folder, show)
    test_prints = LiveTestPrints(folder, answers, ask)
    run_trial = partial(agent.run_trial, person=person, print_tests=test_prints, measure_sketch=True)
    settings = argparse.Namespace(max_turns=max_turns, max_tokens=max_tokens)
    session = Session(request=task.request, task=task.id, model=model, condition=condition, answers=Answers())
    try:
        record = pbe_eval.run_one(task, model, condition, 1, run_dir, settings, chat=try_request.within_budget(budget, chat),
                                  run_trial=run_trial)
    finally:  # Ctrl-C at a question, or grading that breaks: what the person answered so far is still kept
        session.answers = live.collected(person, test_prints)
        folder.mkdir(parents=True, exist_ok=True)
        session.save(folder)
    return record, folder, session


def preprint_report(folder) -> str:
    """The pre-print check on the session's hand-in, which a real build always gets. It reads the parts grading
    has just built, and builds only what grading left out."""
    design, predictions = preprint.check(folder, built_in=Path(folder) / "parts")
    return preprint.report(design, predictions)


def report(record: TrialRecord, folder, session: Session) -> str:
    lines = [f"{record.model}, {record.condition}, live: {record.outcome}"]
    if record.error:
        lines.append(f"  error: {record.error}")
    for told in session.answers.measures:
        lines.append(f"  measured ({told.source}): {told.item}, {told.what} -> {told.answer}")
        if told.sketch:
            lines.append(f"    with the sketch {folder / told.sketch}")
    for number, printed in enumerate(session.answers.test_prints, start=1):
        lines += [f"  test print {number}, {part_id}: {said}" for part_id, said in printed.pieces.items()]
    for limitation in record.limitations:
        lines.append(f"  limitation: wanted {limitation.get('wanted')}; blocked by {limitation.get('blocked_by')}")
    files = try_request.part_files(folder)
    if files:
        lines.append("Parts:")
        lines += [f"  {part_id} ({role}): {path}" for part_id, role, path in files]
    lines.append(f"Cost: ${record.cost_usd:.4f} over {record.turns} turn(s), {record.elapsed_s} s")
    lines.append(f"Saved in {folder}; run it again without answering with --answers {folder / live.SESSION_FILE}")
    if record.outcome == "submitted":
        lines += ["", preprint_report(folder)]
    return "\n".join(lines)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Use the eval's designer agent on a real part, answering its questions yourself.")
    ap.add_argument("request", nargs="?", help="what you want printed, in your own words")
    ap.add_argument("--task", help="one of the eval's tasks instead of your own request, e.g. nut-knob/M5")
    ap.add_argument("--model", required=True, help="an OpenRouter model id, e.g. anthropic/claude-sonnet-5.5")
    ap.add_argument("--answers", type=Path, help="a file of answers, or an earlier session's session.yaml")
    ap.add_argument("--answers-only", action="store_true", help="never ask at the terminal: what the file doesn't answer goes unanswered")
    ap.add_argument("--condition", choices=agent.CONDITIONS, default=DEFAULT_CONDITION)
    ap.add_argument("--budget", type=float, default=0.50,
                    help="USD for the session; no call starts once it's spent, so the last call can run over")
    ap.add_argument("--max-turns", type=int, help="default: agent.DEFAULT_MAX_TURNS for the condition")
    ap.add_argument("--max-tokens", type=int, default=32000)
    ap.add_argument("--out", type=Path, help="the folder to save the session in; default: a new one under results/local/live/")
    args = ap.parse_args(argv)
    if bool(args.request) == bool(args.task):
        ap.error("give your request in words, or --task, not both")
    return args


def main(argv=None):
    args = parse_args(argv)
    pbe_eval.exit_unless_able_to_run([args.condition])
    task = session_task(args.request, args.task)
    answers = live.load_answers(args.answers) if args.answers else None
    ask = None if args.answers_only or not sys.stdin.isatty() else at_terminal
    run_dir = args.out or run_folder(task)
    try:
        record, folder, session = run(task, args.model, run_dir, answers, ask, args.condition, args.budget,
                                      args.max_turns, args.max_tokens, show=in_browser if ask else None)
    except FileExistsError as e:
        sys.exit(str(e))
    print(report(record, folder, session))


if __name__ == "__main__":
    main()
