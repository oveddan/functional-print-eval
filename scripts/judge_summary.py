"""Agreement, latency and cost per test and model, from the rows scripts/judge_known_answers.py saved.

    uv run python scripts/judge_summary.py results/judges/2026-11-12   # writes summary.json and summary.md there

Two agreements: with the key the run recorded (code, or fit_cards' colours), and with the key after Claude's hand
check of every disagreement (results/judges/hand-labels.yaml, `hand_checked`). The baseline is what always giving
the commonest answer in the checked key would score. Latency is per call; cost is what OpenRouter reported.
"""
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

import yaml
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
HAND = yaml.safe_load((ROOT / "results/judges/hand-labels.yaml").read_text())["hand_checked"]


class Line(BaseModel):
    test: str
    model: str
    keyed: int
    agree: int
    checked: int
    agree_checked: int
    baseline: int
    calls: int
    median_seconds: float
    cost: float
    errors: int


def short(model: str) -> str:
    if "gemini-decision" in model:
        return "Gemini Decision 1"
    return "Jev 1.14" if "jev" in model else "GPT-6 Luna" if "luna" in model else model


def checked_key(row: dict):
    """The key after the hand check: an override, a sample label, or the recorded key."""
    override = HAND.get(row["test"], {}).get(row["item"], {}).get(row["question"])
    if override is not None:
        return override["key"]
    sample = HAND.get(f"{row['test']}-sample", {}).get(row["item"], {}).get(row["question"])
    return sample if sample is not None else row["key"]


def said_matches(row: dict, key) -> bool:
    if row["test"] == "5-classes":
        return bool(row["agrees"])  # the record's class or its second class (`also:`)
    if row["test"] == "3-photos":
        return (row["answer"] == "clean") == key
    return row["answer"] == key


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "no key"


def line_for(test: str, model: str, rows: list[dict]) -> Line:
    answered = [r for r in rows if r["answer"] is not None]
    keyed = [r for r in answered if r["key"] is not None]
    checked = [(r, checked_key(r)) for r in answered if checked_key(r) is not None]
    commonest = Counter(str(k) for _, k in checked).most_common(1)
    calls = [r["raw"] for r in rows if r["raw"]]
    return Line(test=test, model=model, keyed=len(keyed), agree=sum(bool(r["agrees"]) for r in keyed),
                checked=len(checked), agree_checked=sum(said_matches(r, k) for r, k in checked),
                baseline=commonest[0][1] if commonest else 0, calls=len(calls),
                median_seconds=statistics.median(c["seconds"] for c in calls) if calls else 0.0,
                cost=sum(r["cost"] for r in rows), errors=sum(bool(r["error"]) for r in rows))


def rows_of(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def lines_for(path: Path) -> list[Line]:
    rows = rows_of(path)
    models = sorted({short(r["model"]) for r in rows})
    return [line_for(path.stem, m, [r for r in rows if short(r["model"]) == m]) for m in models]


def question_lines(path: Path) -> list[str]:
    rows = rows_of(path)
    out = []
    for question in sorted({r["question"] for r in rows if r["question"]}):
        for model in sorted({short(r["model"]) for r in rows}):
            mine = [r for r in rows if r["question"] == question and short(r["model"]) == model]
            line = line_for(path.stem, model, mine)
            if line.checked:
                out.append(f"| {path.stem} | {question} | {model} | {pct(line.agree, line.keyed)} | "
                           f"{pct(line.agree_checked, line.checked)} | {pct(line.baseline, line.checked)} |")
    return out


def box_overlaps(folder: Path) -> list[str]:
    """Jev's boxes against Claude's (pbe/judges/photo_cells.py): intersection over union, per cell."""
    sys.path.insert(0, str(ROOT))
    from pbe.judges.photo_cells import CELLS
    path = folder / "3-box.jsonl"
    if not path.exists():
        return []
    rows = rows_of(path)
    out = ["| Cell | IoU with Claude's box |", "|---|---|"]
    for photo in sorted({c.photo for c in CELLS if c.where}):
        cells = [c for c in CELLS if c.photo == photo and c.where]
        raw = next(r["raw"] for r in rows if r["raw"] and r["item"].startswith(photo.split()[-1]))
        for i, cell in enumerate(cells):
            out.append(f"| {photo.split()[-1]} {cell.name} | {iou(raw['answers'][f'c{i}']['box'], cell.edges):.2f} |")
    return out


def iou(box: dict, e) -> float:
    across = max(0.0, min(box["right"], e.right) - max(box["left"], e.left))
    down = max(0.0, min(box["bottom"], e.bottom) - max(box["top"], e.top))
    inter = across * down
    union = (box["right"] - box["left"]) * (box["bottom"] - box["top"]) + (e.right - e.left) * (e.bottom - e.top) - inter
    return inter / union


def flag_rules(folder: Path) -> list[str]:
    """Test 5: how often a rule flags a failure whose class was held out (caught) against one whose class was
    offered (a false flag). The last rule's 0.7 was picked after seeing this run, so it's tuned on this data."""
    def by_item(name):
        path = folder / f"{name}.jsonl"
        return {(r["item"], short(r["model"])): r for r in rows_of(path)} if path.exists() else {}
    held, offered = by_item("5-held-out"), by_item("5-classes")
    if not held:
        return []
    items = sorted({item for item, _ in offered})

    def none(d, i, m):
        return d[(i, m)]["answer"] == "none_of_these"

    def weak(d, i, m, below):
        return none(d, i, m) or (d[(i, m)]["p"] or 0) < below

    def answered(d, i, models):
        """A failed call is no answer: it's neither a flag nor a pass, and leaves the denominator."""
        return all(d.get((i, m), {}).get("answer") is not None for m in models)

    luna, jev = "GPT-6 Luna", "Jev 1.14"
    rules = {
        "GPT-6 Luna says none": ((luna,), lambda d, i: none(d, i, luna)),
        "Jev 1.14 says none": ((jev,), lambda d, i: none(d, i, jev)),
        "Jev 1.14 says none or its pick is under 0.5": ((jev,), lambda d, i: weak(d, i, jev, 0.5)),
        "Luna says none and Jev's pick is under 0.7 (tuned on this run)":
            ((luna, jev), lambda d, i: none(d, i, luna) and weak(d, i, jev, 0.7)),
    }
    out = ["| Flag rule | Held-out class flagged | Offered class flagged (false flag) |", "|---|---|---|"]
    for name, (models, rule) in rules.items():
        cells = []
        for d in (held, offered):
            counted = [i for i in items if answered(d, i, models)]
            cells.append(pct(sum(rule(d, i) for i in counted), len(counted)))
        out.append(f"| {name} | {cells[0]} | {cells[1]} |")
    return out


def clip_of(row: dict) -> str:
    return row["item"].split(" pass ")[0]


def video_lines(folder: Path) -> list[str]:
    """Test 6, per clip: agreement silent and with sound, each against that clip's commonest-answer baseline, and
    how many questions got the same answer on every pass."""
    out = ["| Clip | Sound | Agrees | Baseline | Questions answered the same on every pass | Median latency | "
           "Input tokens per call |", "|---|---|---|---|---|---|---|"]
    for sound in ("silent", "audio"):
        path = folder / f"6-video-{sound}.jsonl"
        if not path.exists():
            continue
        rows = rows_of(path)
        for clip in sorted({clip_of(r) for r in rows}):
            mine = [r for r in rows if clip_of(r) == clip]
            line = line_for(path.stem, "Gemini Decision 1", mine)
            answers: dict[str, set] = {}
            for r in mine:
                answers.setdefault(r["question"], set()).add(str(r["answer"]))
            steady = sum(len(a) == 1 for a in answers.values())
            tokens = statistics.median(r["raw"]["usage"]["input_tokens"] for r in mine if r["raw"])
            out.append(f"| {clip} | {sound} | {pct(line.agree_checked, line.checked)} | {pct(line.baseline, line.checked)} "
                       f"| {steady}/{len(answers)} | {line.median_seconds:.2f} s | {tokens:.0f} |")
    return out


def main():
    folder = Path(sys.argv[1])
    paths = sorted(folder.glob("*.jsonl"))
    lines = [line for path in paths for line in lines_for(path)]
    table = ["| Test | Model | Agrees with recorded key | After hand check | Commonest-answer baseline | Calls | "
             "Median latency per call | Cost | Failed calls |", "|---|---|---|---|---|---|---|---|---|"]
    table += [f"| {l.test} | {l.model} | {pct(l.agree, l.keyed)} | {pct(l.agree_checked, l.checked)} | "
              f"{pct(l.baseline, l.checked)} | {l.calls} | {l.median_seconds:.2f} s | ${l.cost:.4f} | {l.errors} |"
              for l in lines]
    detail = ["| Test | Question | Model | Recorded key | After hand check | Baseline |", "|---|---|---|---|---|---|"]
    for path in paths:
        if path.stem.startswith(("1-", "4-")):
            detail += question_lines(path)
    total = sum(l.cost for l in lines)
    text = "\n".join(table) + f"\n\nTotal reported cost: ${total:.4f}\n\n" + "\n".join(detail) + "\n\n" + "\n".join(box_overlaps(folder)) + "\n\n" + "\n".join(flag_rules(folder)) + "\n\n" + "\n".join(video_lines(folder)) + "\n"
    (folder / "summary.md").write_text(text)
    (folder / "summary.json").write_text(json.dumps([l.model_dump() for l in lines], indent=1))
    print(text)


if __name__ == "__main__":
    main()
