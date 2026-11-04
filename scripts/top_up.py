"""Top up the can_ask pilot runs to 3 trials per lineup model and task (issue 34).

    uv run python scripts/top_up.py --cap 4.00
    uv run python scripts/top_up.py --dry-run   # what would run, nothing called

Each model and task gets its new trials in the run folder that already holds its saved ones,
numbered after them; saved trials are skipped, never changed. Models go cheapest first, and
the cap is checked before each trial against what this top-up has spent across all its run
folders, so the last trial can overshoot it, as with pbe.eval's --budget.
"""
import argparse
from dataclasses import dataclass
from pathlib import Path

from pbe import eval as runner
from pbe.runner import agent, tasks
from pbe.runner.trial_record import TrialRecord

CONDITION = "can_ask"
TRIALS = 3
# cheapest first, by cost per trial in the saved runs, so the cap stops the dearest
LINEUP = [
    "anthropic/claude-haiku-5.5",
    "deepseek/deepseek-v4-pro-0813",
    "openai/gpt-6.1-sol",
    "anthropic/claude-sonnet-5.5",
    "google/gemini-4-argon",
    "anthropic/claude-opus-5.5",
]
TASKS = ["m5-spacer", "nut-knob/M3", "nut-knob/M5", "tripod-plate", "bearing-wheel"]
# the run folders that hold these tasks' can_ask pilot trials; where two hold the same task,
# a model's trials go to the one already holding them (folder_for)
RUNS = ["pilot-spacer", "pilot-nut-knob", "pilot-nut-knob-2", "pilot-tripod", "pilot-wheel"]


@dataclass(frozen=True)
class Slot:
    """One model on one task, and the run folder its trials go in."""
    run: str
    task: str
    model: str

    @property
    def run_dir(self) -> Path:
        return runner.ROOT / "results/runs" / self.run

    def on_disk(self) -> dict[int, TrialRecord]:
        """Every trial saved in the slot's folder, by number, infrastructure errors included."""
        model_dir = runner.trial_folder(self.run_dir, tasks.load(self.task), CONDITION, self.model, 1).parent
        records = {int(folder.name[1:]): TrialRecord.load_if_saved(folder) for folder in model_dir.glob("t*")}
        return {trial: record for trial, record in sorted(records.items()) if record is not None}

    def saved_trials(self) -> list[int]:
        """The trials that count: an infrastructure error isn't a result."""
        return [trial for trial, record in self.on_disk().items() if record.outcome != "error"]


class RunSettings:
    """What pbe.eval.run_one reads from its command-line arguments: the conditions' defaults."""
    max_turns = None
    max_tokens = 32000


def trials_held(run, task, model) -> int:
    return len(Slot(run, task, model).saved_trials())


def folder_for(task, model) -> str:
    """The run folder with the most saved trials of this model on this task."""
    held = {run: trials_held(run, task, model) for run in RUNS}
    run = max(held, key=held.get)
    if held[run] == 0:
        raise SystemExit(f"no saved {CONDITION} trial of {model} on {task} in {RUNS}")
    return run


def plan() -> list[Slot]:
    return [Slot(folder_for(task, model), task, model) for model in LINEUP for task in TASKS]


def missing_trials(slot) -> list[int]:
    """The trial numbers to run so the slot holds TRIALS: any that ended in an infrastructure error
    (run_one runs those again), then new numbers after every saved one."""
    on_disk = slot.on_disk()
    needed = max(0, TRIALS - len(slot.saved_trials()))
    retried = [trial for trial, record in on_disk.items() if record.outcome == "error"][:needed]
    first_new = max(on_disk, default=0) + 1
    return retried + list(range(first_new, first_new + needed - len(retried)))


def out_of_credit(record) -> bool:
    """OpenRouter answers 402 when the key's credit runs out: an infrastructure stop, not a result."""
    return record.outcome == "error" and "HTTP 402" in (record.error or "")


def spent_in(runs) -> float:
    return sum(runner.spent(runner.ROOT / "results/runs" / run) for run in runs)


def run_slot(slot, spent_before, cap) -> bool:
    """Run the slot's missing trials. False once the cap is reached."""
    for trial in missing_trials(slot):
        if (so_far := spent_in(RUNS) - spent_before) >= cap:
            print(f"cap reached: ${so_far:.4f} of ${cap:.2f}; stopping")
            return False
        record = runner.run_one(tasks.load(slot.task), slot.model, CONDITION, trial, slot.run_dir, RunSettings)
        print(f"{slot.run}: {runner.progress_line(record)}")
        if out_of_credit(record):
            print("out of credit: stopping (an infrastructure stop, not a result)")
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=float, default=4.0, help="USD this top-up may spend, across its run folders")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    slots = plan()
    for slot in slots:
        print(f"{slot.run:18} {slot.task:14} {slot.model:32} saved {slot.saved_trials()} new {missing_trials(slot)}")
    print(f"{sum(len(missing_trials(slot)) for slot in slots)} new trials")
    if args.dry_run:
        return
    runner.exit_unless_able_to_run([CONDITION])
    spent_before = spent_in(RUNS)
    for slot in slots:
        if not run_slot(slot, spent_before, args.cap):
            break
    for run in RUNS:
        runner.summarize(runner.ROOT / "results/runs" / run)
    print(f"top-up spent ${spent_in(RUNS) - spent_before:.4f}")


if __name__ == "__main__":
    main()
