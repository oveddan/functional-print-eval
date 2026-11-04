"""Per model, what the trials saved since prompt caching (issue 34) cost and came to, read from saved runs only.

    uv run python scripts/cost_report.py pilot-spacer pilot-nut-knob pilot-nut-knob-2 pilot-wheel
    uv run python scripts/cost_report.py pilot-code-smoke pilot-code --all

By default only trials that record settings.prompt_caching (saved since issue 34) are counted,
and each is set beside what the same model cost per trial on the same task before caching.
--all counts every trial in the runs.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import mean

from pbe import eval as runner
from pbe.runner.trial_record import TrialRecord

VERDICTS = ["pass", "fail", "not graded", "declined", "no_submission", "error"]


@dataclass
class ModelTally:
    trials: int = 0
    turns: int = 0
    cost_usd: float = 0.0
    before_caching_usd: float = 0.0  # the same tasks at this model's mean cost per trial on each before caching
    prompt_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    verdicts: Counter = field(default_factory=Counter)

    def add(self, record: TrialRecord, before_caching_usd: float) -> None:
        self.trials += 1
        self.turns += record.turns
        self.cost_usd += record.cost_usd
        self.before_caching_usd += before_caching_usd
        self.verdicts[record.verdict] += 1
        for call in record.calls:
            self.prompt_tokens += call.prompt_tokens
            self.cached_tokens += call.cached_tokens
            self.cache_write_tokens += call.cache_write_tokens

    def share(self, tokens) -> str:
        return f"{tokens / self.prompt_tokens:.0%}" if self.prompt_tokens else "-"


def is_new(record: TrialRecord) -> bool:
    return record.settings.prompt_caching is not None


def records_in(runs) -> list[TrialRecord]:
    return [record for run in runs for _, record in TrialRecord.all_in(runner.ROOT / "results/runs" / run)]


def mean_costs_before_caching(records) -> dict[tuple[str, str], float]:
    """Each model's mean cost per trial on each task, from the trials saved before caching."""
    costs = defaultdict(list)
    for record in records:
        if not is_new(record) and record.outcome != "error":
            costs[(record.model, record.task)].append(record.cost_usd)
    return {key: mean(values) for key, values in costs.items()}


def tally(records, count_all) -> dict[str, ModelTally]:
    before = mean_costs_before_caching(records)
    tallies = defaultdict(ModelTally)
    for record in records:
        if count_all or is_new(record):
            tallies[record.model].add(record, before.get((record.model, record.task), 0.0))
    return dict(sorted(tallies.items(), key=lambda item: item[1].cost_usd / item[1].trials))


def table(tallies, count_all) -> str:
    header = ["model", "trials", *VERDICTS, "cost", "per trial", "per turn", "cached", "written"]
    if not count_all:
        header.append("before caching, same tasks")
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for model, t in tallies.items():
        row = [model, t.trials, *(t.verdicts[v] for v in VERDICTS), f"${t.cost_usd:.4f}", f"${t.cost_usd / t.trials:.4f}",
               f"${t.cost_usd / t.turns:.4f}" if t.turns else "-", t.share(t.cached_tokens), t.share(t.cache_write_tokens)]
        if not count_all:
            row.append(f"${t.before_caching_usd:.4f}")
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    total = sum(t.cost_usd for t in tallies.values())
    lines.append(f"\n{sum(t.trials for t in tallies.values())} trials, ${total:.4f}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--all", action="store_true", help="count every trial, not only those saved since caching")
    args = ap.parse_args()
    print(table(tally(records_in(args.runs), args.all), args.all))


if __name__ == "__main__":
    main()
