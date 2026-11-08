"""Run the agent on a print request you write yourself, instead of one of the repo's tasks.

    uv run python -m pbe.try_request "I want a hook for my bike helmet..." --model anthropic/claude-sonnet-5.5 --budget 0.50

The request becomes a throwaway task (tasks.from_request): nothing hidden for the model to measure and no
requirements of its own, so only the general checks grade the design: builds, connected_bodies, bed_fit and
bridges. Whether the part does its job, fits what it's meant for or holds up is not checked: no recorded test
print decides that for a request nobody has printed. One trial runs through pbe.eval's save path and is saved
under results/local/try/ (not committed), apart from the eval's own runs in results/runs/.
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from pbe import eval as pbe_eval
from pbe.graders.checks import verdict_word
from pbe.parts import submission
from pbe.runner import agent, llm, tasks
from pbe.runner.trial_record import TrialRecord

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/local/try"
DEFAULT_CONDITION = agent.TEST_CONDITION  # the model may ask for test prints before its final design
GENERAL_CHECKS_ONLY = ("Only the general checks ran: the parts build, each is one piece, each fits the bed, and every "
                       "overhang can be bridged. Nothing checks that the design fits or does what you asked. "
                       "\"not graded\" means no recorded test print decides that check for this geometry.")


def within_budget(budget, chat=llm.chat):
    """`chat`, refusing the next call once the trial's calls have cost `budget` in USD. The call that
    crosses it still completes, so a trial can run over by one call."""
    spent = 0.0

    def limited(model, messages, **kwargs):
        nonlocal spent
        if spent >= budget:
            raise llm.LLMError(f"budget reached: ${spent:.4f} of ${budget:.2f}")
        response = chat(model, messages, **kwargs)
        spent += (response.get("usage") or {}).get("cost") or 0
        return response
    return limited


def run_folder(request, now=None):
    """A new folder for this try, named by when it ran and the request's first words."""
    words = re.findall(r"[a-z0-9]+", request.lower())[:6]
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return OUT / f"{stamp}-{'-'.join(words) or 'request'}"


def run(request, model, run_dir, condition=DEFAULT_CONDITION, budget=0.50, max_turns=None, max_tokens=32000,
        chat=llm.chat):
    """One trial on the request, saved under run_dir: (the trial's record, its folder). Every request has the
    same task id, so a folder that already holds a trial is refused: run_one would hand back that trial
    as if it were this request's."""
    task = tasks.from_request(request)
    folder = pbe_eval.trial_folder(run_dir, task, condition, model, 1)
    if folder.exists():
        raise FileExistsError(f"{folder} already holds a trial, maybe of another request: save this one somewhere new")
    settings = argparse.Namespace(max_turns=max_turns, max_tokens=max_tokens)
    record = pbe_eval.run_one(task, model, condition, 1, run_dir, settings, chat=within_budget(budget, chat))
    return record, folder


def part_files(folder):
    """Each built part's STL, by part id, with its role (final or coupon, a test print)."""
    sub_path = folder / "submission.yaml"
    if not sub_path.exists():
        return []
    parts = submission.load(sub_path).parts
    return [(part.id, part.role, folder / "parts" / f"{part.id}.stl") for part in parts
            if (folder / "parts" / f"{part.id}.stl").exists()]


def report(record: TrialRecord, folder) -> str:
    lines = [f"{record.model}, {record.condition}: {record.outcome}. Verdict: {record.verdict}"]
    if record.error:
        lines.append(f"  error: {record.error}")
    for finding in record.findings:
        test_print = " (test print, not counted)" if finding.test_print else ""
        lines.append(f"  {verdict_word(finding.ok):10}  {finding.check:16} {finding.part:14} {finding.detail}{test_print}")
    for asked in record.measures:
        lines.append(f"  asked to measure: {asked.item}, {asked.what} -> {asked.reply}")
    for limitation in record.limitations:
        lines.append(f"  limitation: wanted {limitation.get('wanted')}; blocked by {limitation.get('blocked_by')}")
    files = part_files(folder)
    if files:
        lines.append("Parts:")
        lines += [f"  {part_id} ({role}): {path}" for part_id, role, path in files]
    lines.append(f"Cost: ${record.cost_usd:.4f} over {record.turns} turn(s), {record.elapsed_s} s")
    lines.append(f"Saved in {folder}")
    lines.append(GENERAL_CHECKS_ONLY)
    return "\n".join(lines)


def parse_args():
    ap = argparse.ArgumentParser(description="Run the agent on your own print request, graded by the general checks only.")
    ap.add_argument("request", help="what you want printed, in your own words; put every measurement in it")
    ap.add_argument("--model", required=True, help="an OpenRouter model id, e.g. anthropic/claude-sonnet-5.5")
    ap.add_argument("--condition", choices=agent.CONDITIONS, default=DEFAULT_CONDITION)
    ap.add_argument("--budget", type=float, default=0.50,
                    help="USD for the trial; no call starts once it's spent, so the last call can run over")
    ap.add_argument("--max-turns", type=int, help="default: agent.DEFAULT_MAX_TURNS for the condition")
    ap.add_argument("--max-tokens", type=int, default=32000)
    ap.add_argument("--out", type=Path, help="the folder to save the trial in; default: a new one under results/local/try/")
    return ap.parse_args()


def main():
    args = parse_args()
    pbe_eval.exit_unless_able_to_run([args.condition])
    run_dir = args.out or run_folder(args.request)
    try:
        record, folder = run(args.request, args.model, run_dir, args.condition, args.budget, args.max_turns, args.max_tokens)
    except FileExistsError as e:
        sys.exit(str(e))
    print(report(record, folder))


if __name__ == "__main__":
    main()
