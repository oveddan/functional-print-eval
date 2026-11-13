"""The scorecard: each model's pass rate per task and overall, in the format the hackathon's eval design guide
suggests (pass rate, pass^k, cost), plus pass@k and the slicer's print time and filament. No model calls.

    uv run python scripts/scorecard.py           # print the scorecard
    uv run python scripts/scorecard.py --write   # put it in README.md, between its markers, and draw the chart
    uv run python scripts/scorecard.py --check   # exit 1 if README.md's scorecard isn't what the runs say

What it counts (Claude's calls, delegated by Dan on 2026-11-07):
- `can_ask` trials on the four scored tasks: tripod-plate, bearing-wheel, nut-knob M3 and M5. The spacer is a
  control that every model passes, and estoa-light has 3 trials for 6 models, so neither is in the totals.
- The ranking is the verified pass rate: trials where every counted check passes, over all trials. A trial
  that's not graded (no recorded print decides one of its checks) hasn't been shown to work, so it isn't a
  verified pass, and the Not graded column sits beside the rate so it's visible that it isn't a failure either
  (Dan's call, 2026-11-07, after leaving not graded out of the denominator rewarded designs nobody can check).
  Fail, declined and no design count as not passing. A task cell reads verified passes over trials.
- pass@k is the share of tasks the model passed at least once in its first k trials; pass^k the share it
  passed every time (the guide's two consistency measures). k is the fewest trials any listed model has on
  any task.
- Cost is what OpenRouter charged for all of the model's trials on these tasks. Tokens per trial is the
  provider's count of prompt and completion tokens (reasoning included); tokenizers differ between models, so it
  compares how much each model reads and writes, not what it costs.
- Print time and filament come from `slice_estimates.csv` beside each run (scripts/slice_estimates.py): every
  design the model handed in, final parts and test prints, as if each were printed once, divided by its passes.
  That's what it would take to reach one working print by printing whatever the model hands in. A trial with a
  part that didn't build or slice adds nothing, since there's nothing to print.
- A model needs 5 trials on every task to be listed; Grok 4.7 has 1 to 2.
"""

import argparse
import csv
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from pbe.runner.trial_record import TrialRecord

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs"
README = ROOT / "README.md"
CHART = ROOT / "docs/media/scorecard.svg"
REFERENCE = ROOT / "docs/reference.md"  # carries the full scorecard table and the chart
HARDER = ("estoa-light", "Estoa light box (harder)")  # in the test-first table as its own row, not in the four-task total
TEST_FIRST = "test-first"  # the run where the model may ask for test prints before its final design (agent.TEST_CONDITION)
SKIPPED = "Grok 4.7 was left out because it was too expensive to run 10 trials on."
TASKS = {"tripod-plate": "Tripod plate", "bearing-wheel": "Bearing wheel", "nut-knob/M3": "Knob M3", "nut-knob/M5": "Knob M5"}
MIN_TRIALS = 5
SHORT = {
    "anthropic/claude-opus-5.5": "Opus 5.5", "anthropic/claude-sonnet-5.5": "Sonnet 5.5",
    "anthropic/claude-haiku-5.5": "Haiku 5.5", "google/gemini-4-argon": "Gemini 4 Argon",
    "google/gemini-3.8-flash": "Gemini 3.8 Flash", "openai/gpt-6.1-sol": "GPT-6.1 Sol", "openai/gpt-6-luna": "GPT-6 Luna",
    "deepseek/deepseek-v4-pro-0813": "DeepSeek V4 Pro", "deepseek/deepseek-v4.1-flash": "DeepSeek V4.1 Flash",
    "z-ai/glm-5.3-flash": "GLM 5.3 Flash", "qwen/qwen3.8-flash": "Qwen 3.8 Flash",
}


@dataclass
class Print:
    """One print of a design: its verdict, what the model's turn cost, and the slicer's estimate."""
    verdict: str  # pass, fail, not graded, declined, or an outcome such as no_submission
    cost: float
    print_s: float | None  # None when a part didn't slice or the design wasn't sliced
    grams: float | None


@dataclass
class Trial:
    first: Print
    tokens: int  # prompt and completion tokens over the first turn's calls, as the provider counted them
    second: Print | None = None  # after the person said how the first print came out (loop-all), if replayed
    told_cant_tell: bool = False  # the person's reply said of some part "I can't tell you how that one came out"

    def final(self, after: bool) -> Print:
        """The print the trial ends on: the first if it passed or there's no replay, else the second."""
        if not after or self.second is None or self.first.verdict == "pass":
            return self.first
        return self.second

    def prints(self, after: bool) -> list[Print]:
        """Every print made: the second too, once it's counted."""
        return [self.first] if self.final(after) is self.first else [self.first, self.second]

    def passed(self, after: bool = False) -> bool:
        return self.final(after).verdict == "pass"

    def not_graded(self, after: bool = False) -> bool:
        return self.final(after).verdict == "not graded"


@dataclass
class Row:
    model: str
    by_task: dict[str, list[Trial]] = field(default_factory=lambda: defaultdict(list))
    tested: dict[str, list[Trial]] = field(default_factory=lambda: defaultdict(list))  # the test-first run, if any

    def tested_trials(self) -> list[Trial]:
        """The test-first trials on the four scored tasks (the harder task is its own row, not in the total)."""
        return [trial for task, trials in self.tested.items() if task in TASKS for trial in trials]

    def tested_rate(self, task: str | None = None) -> float | None:
        trials = self.tested.get(task, []) if task else self.tested_trials()
        return sum(t.passed() for t in trials) / len(trials) if trials else None

    def tested_per_pass(self, attribute: str) -> float | None:
        """Cost, print time or filament over every test-first trial (the test prints it asked for included), per pass."""
        passes = sum(t.passed() for t in self.tested_trials())
        values = [getattr(t.first, attribute) for t in self.tested_trials()]
        if not passes or all(value is None for value in values):
            return None
        return sum(value for value in values if value is not None) / passes

    def all_trials(self) -> list[Trial]:
        return [trial for trials in self.by_task.values() for trial in trials]

    def replayed(self) -> bool:
        return any(trial.second is not None for trial in self.all_trials())

    def passes(self, after: bool = False) -> int:
        return sum(trial.passed(after) for trial in self.all_trials())

    def not_graded(self, after: bool = False) -> int:
        return sum(trial.not_graded(after) for trial in self.all_trials())

    def pass_rate(self, after: bool = False) -> float:
        return self.passes(after) / len(self.all_trials())

    def pass_hat_k(self, k: int, after: bool = False) -> float:
        return sum(all(t.passed(after) for t in trials[:k]) for trials in self.by_task.values()) / len(TASKS)

    def cost(self, after: bool = False) -> float:
        return sum(p.cost for trial in self.all_trials() for p in trial.prints(after))

    def per_pass(self, attribute: str, after: bool = False) -> float | None:
        values = [getattr(p, attribute) for trial in self.all_trials() for p in trial.prints(after)]
        if self.passes(after) == 0 or all(value is None for value in values):
            return None
        return sum(value for value in values if value is not None) / self.passes(after)


def slice_rows() -> dict[tuple, dict]:
    """Every sliced trial, keyed by run, task, condition, model and trial number."""
    found = {}
    for path in RUNS.glob("*/slice_estimates.csv"):
        with path.open() as handle:
            for row in csv.DictReader(handle):
                found[(row["run"], row["task"], row["condition"], row["model"], int(row["trial"]))] = row
    return found


def number(text: str) -> float | None:
    return float(text) if text not in ("", None) else None


def second_print(folder: Path, record: TrialRecord, sliced: dict) -> tuple[Print | None, bool]:
    """The design sent after the person said how the first print came out (scripts/coupon_loop.py, loop-all)."""
    from pbe.runner import coupon_loop
    arm = RUNS / "loop-all" / folder.relative_to(RUNS) / "feedback"
    if not (arm / coupon_loop.FILE_NAME).exists():
        return None, False
    replay = coupon_loop.LoopRecord.load(arm)
    if replay.outcome == "error":  # an infrastructure stop (e.g. out of credit), not a result: as if not replayed yet
        return None, False
    summary = replay.summary()
    verdict = next((word for word in ("pass", "fail", "not graded") if summary.startswith(word)), summary)
    estimate = sliced.get(("loop-all", record.task, "can_ask/feedback", record.model, record.trial), {})
    return Print(verdict, replay.cost_usd, number(estimate.get("all_print_s", "")), number(estimate.get("all_filament_g", ""))), \
        coupon_loop.CANT_TELL in (replay.reply or "")


def rows() -> list[Row]:
    sliced = slice_rows()
    table: dict[str, Row] = {}
    for run_dir in sorted(path for path in RUNS.iterdir() if path.is_dir()):
        for folder, record in sorted(TrialRecord.all_in(run_dir), key=lambda pair: pair[1].trial):
            if record.condition != "can_ask" or record.task not in TASKS:
                continue
            estimate = sliced.get((run_dir.name, record.task, record.condition, record.model, record.trial), {})
            tokens = sum((call.usage or {}).get("total_tokens") or 0 for call in record.calls or [])
            first = Print(record.verdict, record.cost_usd or 0.0,
                          number(estimate.get("all_print_s", "")), number(estimate.get("all_filament_g", "")))
            second, cant_tell = second_print(folder, record, sliced)
            trial = Trial(first, tokens, second, cant_tell)
            table.setdefault(record.model, Row(record.model)).by_task[record.task].append(trial)
    for folder, record in sorted(TrialRecord.all_in(RUNS / TEST_FIRST), key=lambda pair: pair[1].trial) if (RUNS / TEST_FIRST).exists() else []:
        if (record.task not in TASKS and record.task != HARDER[0]) or record.model not in table or record.outcome == "error":
            continue  # an infrastructure stop (out of credit) isn't a result
        estimate = sliced.get((TEST_FIRST, record.task, record.condition, record.model, record.trial), {})
        tokens = sum((call.usage or {}).get("total_tokens") or 0 for call in record.calls or [])
        first = Print(record.verdict, record.cost_usd or 0.0,
                      number(estimate.get("all_print_s", "")), number(estimate.get("all_filament_g", "")))
        cant_tell = any("can't tell" in line["text"] for test in record.test_prints for lines in test["reply"].values()
                        for line in lines)
        table[record.model].tested[record.task].append(Trial(first, tokens, told_cant_tell=cant_tell))
    listed = [row for row in table.values() if all(len(row.by_task.get(task, [])) >= MIN_TRIALS for task in TASKS)]
    return sorted(listed, key=lambda row: (-row.pass_rate(after=True), row.cost(after=True)))


def percent(share: float) -> str:
    return f"{round(100 * share)}%"


def task_cell(trials: list[Trial], replayed: bool) -> str:
    first = f"{sum(t.passed() for t in trials)}/{len(trials)}"
    return f"{first} → {sum(t.passed(True) for t in trials)}/{len(trials)}" if replayed else first


def per_pass_cell(row: Row, attribute: str, scale: float, unit: str) -> str:
    if not row.passes(after=True):
        return "no pass"
    value = row.per_pass(attribute, after=True)
    if value is None:
        return "not sliced"
    return f"{value / scale:.1f} {unit}" if unit == "h" else f"{value:.0f} {unit}"


def markdown(listed: list[Row]) -> str:
    # the trial count most cells have (10); a cell with fewer (Qwen's M5, 5) counts only if all of its trials pass
    k = Counter(len(trials) for row in listed for trials in row.by_task.values()).most_common(1)[0][0]
    head = ["Model", *TASKS.values(), "First print", "After feedback", "Not graded", f"pass^{k}", "Tokens per trial",
            "Cost per pass", "Print hours per pass", "Filament per pass"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for row in listed:
        trials, replayed = row.all_trials(), row.replayed()
        after = (f"**{percent(row.pass_rate(True))}** ({row.passes(True)}/{len(trials)})" if replayed else "not run")
        first = f"{percent(row.pass_rate())} ({row.passes()}/{len(trials)})"
        cells = [SHORT.get(row.model, row.model), *(task_cell(row.by_task[task], replayed) for task in TASKS),
                 first if replayed else f"**{first}**", after, str(row.not_graded(replayed)), percent(row.pass_hat_k(k, replayed)),
                 f"{sum(t.tokens for t in trials) / len(trials) / 1000:.0f}k",
                 f"${row.cost(True) / row.passes(True):.2f}" if row.passes(True) else "no pass",
                 per_pass_cell(row, "print_s", 3600, "h"), per_pass_cell(row, "grams", 1, "g")]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def undecided_then_passed(row: Row) -> int:
    """Passes after feedback that were not graded on the first print and whose reply said "I can't tell": the model
    can switch to a shape the test prints cover, a hint a real builder, who'd see whether the part worked, wouldn't give."""
    return sum(t.passed(True) and not t.passed() and t.first.verdict == "not graded" and t.told_cant_tell
               for t in row.all_trials())


def note(listed: list[Row]) -> str:
    replayed = [row for row in listed if row.replayed()]
    gained = {row.model: row.passes(True) - row.passes() for row in replayed}
    hinted = {row.model: undecided_then_passed(row) for row in replayed}
    parts = [f"{SHORT.get(m, m)} {hinted[m]} of its {gained[m]}" for m in sorted(hinted, key=lambda m: -hinted[m]) if hinted[m]]
    if not parts:
        return "No new pass after feedback came from a design that wasn't graded on the first print."
    others = [SHORT.get(m, m) for m in hinted if not hinted[m] and gained[m]]
    sentence = ("Some of the gain after feedback comes from a gap in the simulation, not from what a builder would say. "
                "When no recorded print decides a part, such as a ribbed nut pocket, the person can only answer \"I can't "
                "tell you how that one came out\", and a model can then switch to a shape the test prints cover, which "
                "passes. The final design is verified, but a real builder would have said whether the part worked. "
                f"New passes that came this way: {', '.join(parts)}.")
    if others:
        names = others[0] if len(others) == 1 else ", ".join(others[:-1]) + " and " + others[-1]
        sentence += f" {names} had none."
    return sentence


def estoa_line() -> str:
    """The harder task in one sentence: first-print passes, and passes after the Estoa test-print loop (loop-estoa),
    from the saved runs. It isn't a scorecard column: fewer models and trials, and almost no passes to rank by."""
    from pbe.runner import coupon_loop
    records = [record for _, record in TrialRecord.all_in(RUNS / "pilot-estoa") if record.condition == "can_ask"]
    models = sorted({record.model for record in records})
    first = sum(record.verdict == "pass" for record in records)
    arms = [coupon_loop.LoopRecord.load(path.parent)
            for path in (RUNS / "loop-estoa").glob("pilot-estoa/*/can_ask/*/t*/feedback/" + coupon_loop.FILE_NAME)]
    arms = [arm for arm in arms if arm.outcome != "error"]
    after = sum(arm.summary() == "pass" for arm in arms)
    tested = [record for _, record in TrialRecord.all_in(RUNS / TEST_FIRST)
              if record.task == HARDER[0] and record.outcome != "error"]
    tested_passes = sum(record.verdict == "pass" for record in tested)
    return (f"**The Estoa light box**, the harder task, isn't in the four-task total: {len(models)} models, "
            f"{len(records)} trials. {first} of {len(records)} designs pass on the first print. After the person says "
            f"how the box came out, {after} of the {len(arms)} failures replayed {'passes' if after == 1 else 'pass'}. "
            f"Asking for test prints first, {tested_passes} of {len(tested)} pass (its row in the table). We ran out of "
            f"time to make the test-print loop work on this task ([the Estoa section](#estoa-light-box-harder-task)).")


def chart(listed: list[Row]) -> str:
    """Verified pass rate against cost per trial, one dot per model, as an SVG that follows the reader's theme. A model
    with a feedback round sits at its rate after it, with a faint line and a hollow dot where its first print was."""
    width, height, left, right, top, bottom = 720, 420, 64, 150, 24, 56
    costs = [row.cost(after=True) / len(row.all_trials()) for row in listed]
    top_cost = max(costs) * 1.1
    top_rate = max(0.5, max(row.pass_rate(after=True) for row in listed) * 1.15)
    def x(cost): return left + (width - left - right) * cost / top_cost
    floor = -0.04 * top_rate  # 0% sits a little above the axis, clear of the tick labels
    def y(rate): return top + (height - top - bottom) * (top_rate - rate) / (top_rate - floor)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
           'font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif" font-size="12">',
           "<style>text{fill:#3b4440}.axis{stroke:#9aa39f}.grid{stroke:#d9dedb}.dot{fill:#b35c1e}.was{fill:none;stroke:#b35c1e}.rise{stroke:#b35c1e;stroke-opacity:.45}"
           "@media (prefers-color-scheme: dark){text{fill:#d6dcd9}.axis{stroke:#6c7570}.grid{stroke:#2e3633}.dot{fill:#e99a5e}.was{stroke:#e99a5e}.rise{stroke:#e99a5e}}</style>"]
    for step in range(0, int(top_rate * 100) + 1, 10):
        rate = step / 100
        out.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y(rate):.1f}" y2="{y(rate):.1f}"/>')
        out.append(f'<text x="{left - 8}" y="{y(rate) + 4:.1f}" text-anchor="end">{step}%</text>')
    cents = 5 if top_cost < 0.4 else 10
    for tick in range(0, int(top_cost * 100) + 1, cents):
        out.append(f'<text x="{x(tick / 100):.1f}" y="{height - bottom + 18}" text-anchor="middle">${tick / 100:.2f}</text>')
    out.append(f'<line class="axis" x1="{left}" x2="{width - right}" y1="{height - bottom}" y2="{height - bottom}"/>')
    out.append(f'<text x="{(left + width - right) / 2}" y="{height - 12}" text-anchor="middle">Cost per trial, both prints (OpenRouter)</text>')
    out.append(f'<text transform="translate(16 {(top + height - bottom) / 2}) rotate(-90)" text-anchor="middle">Verified pass rate</text>')
    boxes = []  # label boxes already placed: (x0, y0, x1, y1)
    def free(box):
        return all(box[2] < o[0] or box[0] > o[2] or box[3] < o[1] or box[1] > o[3] for o in boxes) and box[0] >= 0 and box[2] <= width
    for row, cost in sorted(zip(listed, costs), key=lambda pair: -pair[0].pass_rate(after=True)):
        cx, cy = x(cost), y(row.pass_rate(after=True))
        if row.replayed() and row.pass_rate() != row.pass_rate(after=True):
            out.append(f'<line class="rise" x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(row.pass_rate()):.1f}" y2="{cy:.1f}" stroke-width="2"/>')
            out.append(f'<circle class="was" cx="{cx:.1f}" cy="{y(row.pass_rate()):.1f}" r="4" stroke-width="1.5"/>')
            boxes.append((cx - 6, y(row.pass_rate()) - 6, cx + 6, y(row.pass_rate()) + 6))
        name = SHORT.get(row.model, row.model)
        w = 6.6 * len(name)
        candidates = [(cx + 9, cy + 4, "start"), (cx - 9, cy + 4, "end"), (cx - w / 2, cy - 10, "start"),
                      (cx - w / 2, cy + 18, "start"), (cx + 9, cy - 10, "start"), (cx + 9, cy + 18, "start"),
                      (cx - 9, cy - 10, "end"), (cx - 9, cy + 18, "end")]
        for tx, ty, anchor in candidates:
            x0 = tx if anchor == "start" else tx - w
            box = (x0 - 2, ty - 11, x0 + w + 2, ty + 3)
            if free(box):
                break
        boxes.append(box)
        boxes.append((cx - 6, cy - 6, cx + 6, cy + 6))
        out.append(f'<circle class="dot" cx="{cx:.1f}" cy="{cy:.1f}" r="5"/>')
        out.append(f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{anchor}">{name}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def tested_order(listed: list[Row]) -> list[Row]:
    """The models with a test-first run, best first: pass rate, then cost per pass."""
    tested = [row for row in listed if row.tested_trials()]
    return sorted(tested, key=lambda row: (-row.tested_rate(), row.tested_per_pass("cost") or 1e9))


def ranking(listed: list[Row]) -> str:
    """Best to worst, in words: the test-first models by their pass rate, then the rest by their first print."""
    tested = tested_order(listed)
    lines = [f"**Best to worst, when the model can ask for test prints** ({len(tested)} models, "
             f"{min(len(row.tested.get(task, [])) for row in tested for task in TASKS)} or more trials on each of the four tasks):", ""]
    for place, row in enumerate(tested, 1):
        passes, trials = sum(t.passed() for t in row.tested_trials()), len(row.tested_trials())
        cost, hours = row.tested_per_pass("cost"), row.tested_per_pass("print_s")
        each = (f": ${cost:.2f} and {hours / 3600:.1f} print hours per working part" if cost and hours
                else f": ${cost:.2f} per working part" if cost else "")
        lines.append(f"{place}. **{SHORT.get(row.model, row.model)}**, {percent(passes / trials)} of trials pass ({passes}/{trials}){each}")
    rest = sorted((row for row in listed if not row.tested_trials()), key=lambda row: -row.pass_rate())
    if rest:
        named = ", ".join(f"{SHORT.get(row.model, row.model)} {percent(row.pass_rate())}" for row in rest)
        lines += ["", f"Not run with test prints, ranked by their first print without them: {named}. {SKIPPED}"]
    return "\n".join(lines)


def improvement(listed: list[Row]) -> str:
    """What asking for test prints changed, model by model, on the four tasks: the first print without them (can_ask),
    the second print after hearing how the first came out (the replays), and asking for test prints before the final
    design (test-first). Pooled over the six models in one sentence first."""
    tested = tested_order(listed)
    first = sum(row.passes() for row in tested) / sum(len(row.all_trials()) for row in tested)
    with_tests = sum(sum(t.passed() for t in row.tested_trials()) for row in tested) / sum(
        len(row.tested_trials()) for row in tested)
    lines = [f"**What asking for test prints changed.** Across these {len(tested)} models, {percent(first)} of first "
             f"prints pass without test prints, and {percent(with_tests)} pass when the model can ask for test prints "
             f"before its final design.", "",
             "| Model | First print, no test prints | Second print, after hearing how the first came out | "
             "Asking for test prints first | Change from the first print |", "|---|---|---|---|---|"]
    for row in tested:
        after = percent(row.pass_rate(after=True)) if row.replayed() else "not replayed"
        change = round(100 * (row.tested_rate() - row.pass_rate()))
        lines.append(f"| {SHORT.get(row.model, row.model)} | {percent(row.pass_rate())} ({row.passes()}/{len(row.all_trials())}) "
                     f"| {after} | {percent(row.tested_rate())} ({sum(t.passed() for t in row.tested_trials())}/"
                     f"{len(row.tested_trials())}) | {'+' if change > 0 else ''}{change} points |")
    return "\n".join(lines)


def results_table(listed: list[Row]) -> str:
    """The test-first results as a markdown table: a row per model, best first, so GitHub's alternate-row shading
    separates the models; a column per task, then the costs per working part. The best in each column is bold, and a
    0% tie wins nothing. (A picture with the best cell in green until 2026-11-13, when Dan asked for markdown.)"""
    tested = tested_order(listed)
    harder = [(HARDER[1], "pass", HARDER[0])] if any(row.tested.get(HARDER[0]) for row in tested) else []
    columns = [(name, "pass", task) for task, name in TASKS.items()] + [("All four tasks", "pass", None)] + harder + [
               ("Print hours per pass", "print_s", None), ("Filament per pass", "grams", None),
               ("Cost per pass", "cost", None)]

    def value(row: Row, kind: str, task):
        """As shown, so two cells that read the same tie."""
        v = row.tested_rate(task) if kind == "pass" else row.tested_per_pass(kind)
        rounding = {"print_s": lambda x: round(x / 3600, 1) * 3600, "grams": round, "cost": lambda x: round(x, 2)}
        return v if v is None or kind == "pass" else rounding[kind](v)

    def shown(row: Row, kind: str, task) -> str:
        v = value(row, kind, task)
        if kind == "pass":
            trials = row.tested.get(task, []) if task else row.tested_trials()
            return "not run" if v is None else f"{percent(v)} ({sum(t.passed() for t in trials)}/{len(trials)})"
        if v is None:
            return "no pass" if not any(t.passed() for t in row.tested_trials()) else "not sliced"
        return {"print_s": f"{v / 3600:.1f} h", "grams": f"{v:.0f} g", "cost": f"${v:.2f}"}[kind]

    def winners(kind: str, task) -> list[bool]:
        values = [value(row, kind, task) for row in tested]
        present = [v for v in values if v is not None]
        best = (max(present) if kind == "pass" else min(present)) if present else None
        return [v is not None and v == best and (kind != "pass" or v > 0) for v in values]

    bold = [winners(kind, task) for _, kind, task in columns]
    lines = ["| Model | " + " | ".join(name for name, _, _ in columns) + " |",
             "|---|" + "---|" * len(columns)]
    for r, row in enumerate(tested):
        cells = []
        for c, (_, kind, task) in enumerate(columns):
            cell = shown(row, kind, task)
            cells.append(f"**{cell}**" if bold[c][r] else cell)
        lines.append(f"| {SHORT.get(row.model, row.model)} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def headline(listed: list[Row]) -> str:
    """What the README's results section shows between its markers: the picture, its legend and the ranking."""
    if not any(row.tested_trials() for row in listed):
        return markdown(listed)
    return (results_table(listed) + "\n\n"
            "In these results the model can ask for test prints before its final design, as in [How a trial runs]"
            "(#how-a-trial-runs). Each row is a model, best first; the best in each column is bold. A pass means "
            "every check passes on my "
            "recorded test prints. Time, filament and cost per pass count everything the model printed, test prints "
            "included, divided by the parts that work.\n\n" + ranking(listed) + "\n\n" + improvement(listed) + "\n\n"
            + cant_tell_line(listed))


def cant_tell_line(listed: list[Row]) -> str:
    """How often the person couldn't answer a test print, and how many passes followed such an answer: the model may
    have moved to a size the records cover, which a real print wouldn't push it toward (README, Limits)."""
    trials = [t for row in tested_order(listed) for t in row.tested_trials()]
    told = [t for t in trials if t.told_cant_tell]
    passes = [t for t in trials if t.passed()]
    after = [t for t in passes if t.told_cant_tell]
    return (f"In {len(told)} of these {len(trials)} trials the person answered at least one test piece with \"I can't tell "
            f"you how that one came out\", for a size my test prints never tried. {len(after)} of the {len(passes)} passes "
            "came after such an answer, so some may owe part of the pass to moving to a size I did print (see Limits).")


def markers() -> tuple[str, str]:
    return ("<!-- scorecard:start (written by scripts/scorecard.py; don't edit by hand) -->", "<!-- scorecard:end -->")


def readme_with(text: str, table: str, sentence: str = "") -> str:
    for (start, end), body in ((markers(), table), (note_markers(), sentence)):
        if start not in text or end not in text:
            raise SystemExit(f"README.md has no markers {start!r} and {end!r}")
        before, rest = text.split(start, 1)
        text = f"{before}{start}\n{body}\n{end}{rest.split(end, 1)[1]}"
    return text


def note_markers() -> tuple[str, str]:
    return ("<!-- scorecard-note:start (written by scripts/scorecard.py; don't edit by hand) -->", "<!-- scorecard-note:end -->")


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    listed = rows()
    table, top = markdown(listed), headline(listed)
    pictures = {CHART: chart(listed)}
    if not (args.write or args.check):
        print(top if top != table else table)
        return
    notes = note(listed) + "\n\n" + estoa_line()
    full = table + "\n\n![Verified pass rate against cost per trial, one dot per model](media/scorecard.svg)"
    docs = {README: readme_with(README.read_text(), top, notes), REFERENCE: reference_with(REFERENCE.read_text(), full)}
    if args.check:
        stale = [doc.name for doc, text in docs.items() if text != doc.read_text()]
        stale += [path.name for path, svg in pictures.items() if not path.exists() or path.read_text() != svg]
        if stale:
            sys.exit(f"{', '.join(stale)} don't match results/runs/: run scripts/scorecard.py --write")
        print("README.md's results, the reference's scorecard and their pictures match results/runs/")
        return
    for doc, text in docs.items():
        doc.write_text(text)
    for path, svg in pictures.items():
        path.write_text(svg)
    print("README.md's results, docs/reference.md's scorecard and " + ", ".join(p.name for p in pictures) + " updated")


def reference_with(text: str, table: str) -> str:
    """The full scorecard table and the chart in docs/reference.md, between their own markers."""
    start, end = markers()
    if start not in text or end not in text:
        raise SystemExit(f"docs/reference.md has no markers {start!r} and {end!r}")
    before, rest = text.split(start, 1)
    return f"{before}{start}\n{table}\n{end}{rest.split(end, 1)[1]}"


if __name__ == "__main__":
    main()
