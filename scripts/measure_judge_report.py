"""Test 7's report: how the decisions models match measure requests to recorded facts, against today's lookup.

    uv run python scripts/measure_judge_report.py results/judges/2026-11-12   # writes 7-measure.md there

Where the lookup answers, its facts are the key: a request agrees when the judge's facts (p(yes) >= 0.5) are
the same set. Where the lookup says "I can't measure that", there is no key; every request a model picked a fact
for was read by hand against the task's hidden_facts.yaml (results/judges/hand-labels.yaml, `measure_no_answer`):
the facts it plainly asks for that are recorded, or none. A real miss is a request with such a fact that the
lookup turned away. A recorded fact whose value is "I can't measure that" doesn't count: the reply is the same.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import yaml
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pbe.judges import measure_calls  # noqa: E402

LABELS = yaml.safe_load((ROOT / "results/judges/hand-labels.yaml").read_text())
HAND = LABELS.get("measure_no_answer") or {}
SAMPLE = LABELS.get("measure_disagreement_sample") or {}
RANDOM = LABELS.get("measure_random_sample") or {}


class Judged(BaseModel):
    """One model's answer to one request."""
    request: str
    model: str
    key: list[str] | None
    picks: list[str]
    p_yes: dict[str, float]
    error: str


def short(model: str) -> str:
    return "Jev 1.14" if "jev" in model else "GPT-6 Luna" if "luna" in model else \
        "Gemini Decision 1" if "gemini" in model else model


def judged_rows(path: Path) -> list[Judged]:
    rows = []
    for line in path.read_text().splitlines():
        row = json.loads(line)
        rows.append(Judged(request=row["item"], model=short(row["model"]),
                           key=row["key"].split(",") if row["key"] else None,
                           picks=row["answer"].split(",") if row["answer"] else [],
                           p_yes=(row["raw"] or {}).get("p_yes", {}), error=row["error"]))
    return rows


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "none"


def facts_agreeing(row: Judged) -> tuple[int, int]:
    """Facts the judge and the lookup put on the same side, of the facts the judge answered."""
    same = sum((fact in row.key) == (p >= 0.5) for fact, p in row.p_yes.items())
    return same, len(row.p_yes)


def answered_line(model: str, rows: list[Judged]) -> str:
    keyed = [r for r in rows if r.key is not None and not r.error]
    same = sum(set(r.picks) == set(r.key) for r in keyed)
    extra = sum(bool(set(r.picks) - set(r.key)) for r in keyed)
    missing = sum(bool(set(r.key) - set(r.picks)) for r in keyed)
    fact_same, facts = map(sum, zip(*(facts_agreeing(r) for r in keyed))) if keyed else (0, 0)
    return (f"| {model} | {pct(same, len(keyed))} | {pct(fact_same, facts)} | {pct(extra, len(keyed))} | "
            f"{pct(missing, len(keyed))} |")


def no_answer_line(model: str, rows: list[Judged]) -> str:
    """Of the requests the lookup turned away: how many the model picked a fact for, and how those read by hand."""
    unkeyed = [r for r in rows if r.key is None and not r.error]
    picked = [r for r in unkeyed if r.picks]
    checked = [r for r in picked if r.request in HAND]
    right = sum(set(r.picks) == set(HAND[r.request]["facts"]) for r in checked)
    found = sum(bool(set(r.picks) & set(HAND[r.request]["facts"])) for r in checked)
    wrong = sum(bool(set(r.picks) - set(HAND[r.request]["facts"])) for r in checked)
    real = [rid for rid, label in HAND.items() if label["facts"]]
    caught = sum(any(r.request == rid and set(r.picks) & set(HAND[rid]["facts"]) for r in picked) for rid in real)
    return (f"| {model} | {pct(len(picked), len(unkeyed))} | {len(checked)} | {right} | {found} | {wrong} | "
            f"{caught}/{len(real)} |")


def hand_key() -> dict[str, set[str]]:
    """Every request Claude keyed by hand: the turned-away ones a judge picked for, and the disagreement sample."""
    key = {rid: set(label["facts"]) for rid, label in HAND.items()}
    key.update({rid: set(label["facts"]) for rid, label in SAMPLE.items()})
    return key


def hand_keyed_line(name: str, rows: list[Judged], key: dict[str, set[str]]) -> str:
    """Against Claude's hand key: exactly right, picked a fact not asked for, left out a fact that was asked for."""
    mine = [r for r in rows if r.request in key and not r.error]
    exact = sum(set(r.picks) == key[r.request] for r in mine)
    extra = sum(bool(set(r.picks) - key[r.request]) for r in mine)
    missing = sum(bool(key[r.request] - set(r.picks)) for r in mine)
    return f"| {name} | {pct(exact, len(mine))} | {extra} | {missing} |"


def with_bar(rows: list[Judged], bar: float) -> list[Judged]:
    """Test 7 rows with picks redrawn at a higher p(yes)."""
    return [r.model_copy(update={"picks": [f for f, p in r.p_yes.items() if p >= bar]}) for r in rows]


def slot_picks(raw: dict, bar: float) -> list[str]:
    """Test 7b: the recorded facts in the slots up to the count whose pick is at least `bar` likely."""
    picks = []
    for i in range(1, (raw.get("count") or 0) + 1):
        answer = raw["slots"].get(f"ask_{i}", {})
        pick = answer.get("choice")
        if pick not in (None, "not_recorded", "nothing_more") and (answer.get("confidence") or 0) >= bar:
            picks.append(pick.replace("__", "."))
    return picks


def listed_rows(path: Path, bar: float) -> list[Judged]:
    rows = []
    for line in path.read_text().splitlines():
        row = json.loads(line)
        rows.append(Judged(request=row["item"], model="Jev 1.14", key=None, error=row["error"], p_yes={},
                           picks=slot_picks(row["raw"], bar) if row["raw"] else []))
    return rows


def lookup_line(requests: list[measure_calls.Request], key: dict[str, set[str]]) -> str:
    by_id = {r.id: set(r.lookup) for r in requests}
    picks = [Judged(request=rid, model="lookup", key=None, picks=sorted(by_id[rid]), p_yes={}, error="")
             for rid in key if rid in by_id]
    return hand_keyed_line("today's lookup", picks, key)


def pick_list(rows: list[Judged], models: list[str]) -> list[str]:
    """Every turned-away request a model picked a fact for, with each model's picks and Claude's hand check."""
    by_request: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        if row.key is None and row.picks:
            by_request.setdefault(row.request, {})[row.model] = row.picks
    out = ["| Request (task, item, what) | " + " | ".join(models) + " | Claude's hand check |",
           "|---|" + "---|" * len(models) + "---|"]
    for request in sorted(by_request):
        label = HAND.get(request)
        reading = "not checked" if label is None else (", ".join(label["facts"]) or "none recorded") + f": {label['why']}"
        picks = [", ".join(by_request[request].get(m, [])) or "-" for m in models]
        out.append(f"| {request.replace('|', '/')} | " + " | ".join(picks) + f" | {reading} |")
    return out


def real_miss_counts(requests: list[measure_calls.Request]) -> list[str]:
    """Real misses per task and per contestant: distinct requests, and the times they were asked across trials."""
    by_id = {r.id: r for r in requests}
    real = [by_id[rid] for rid, label in HAND.items() if label["facts"] and rid in by_id]
    tasks, contestants = Counter(), Counter()
    asked_tasks, asked_contestants = Counter(), Counter()
    for request in real:
        tasks[request.task] += 1
        asked_tasks[request.task] += len(request.asked)
        for contestant in {a.contestant for a in request.asked}:
            contestants[contestant] += 1
        for asked in request.asked:
            asked_contestants[asked.contestant] += 1
    calls_per_task = Counter()
    for request in requests:
        calls_per_task[request.task] += len(request.asked)
    out = ["| Task | Real misses (distinct requests) | Times asked | Measure calls in all |", "|---|---|---|---|"]
    out += [f"| {t} | {tasks[t]} | {asked_tasks[t]} | {calls_per_task[t]} |" for t in sorted(tasks)]
    out += ["", "| Contestant | Real misses (distinct requests) | Times asked |", "|---|---|---|"]
    out += [f"| {c} | {contestants[c]} | {asked_contestants[c]} |" for c in sorted(contestants)]
    return out


def versions(folder: Path, rows: list[Judged], models: list[str]) -> list[tuple[str, list[Judged]]]:
    """Every way of answering that was run, by name, with test 7's Jev at a higher bar as well."""
    out = [(f"{m}, yes/no per fact", [r for r in rows if r.model == m]) for m in models]
    jev = [r for r in rows if r.model == "Jev 1.14"]
    out.append(("Jev 1.14, yes/no per fact, p ≥ 0.8", with_bar(jev, 0.8)))
    listed_path, said_path = folder / "7b-measure-listed.jsonl", folder / "7c-measure-said.jsonl"
    if listed_path.exists():
        out.append(("Jev 1.14, count + list (7b)", judged_rows(listed_path)))
        out.append(("Jev 1.14, count + list, slot ≥ 0.9", listed_rows(listed_path, 0.9)))
    if said_path.exists():
        said = judged_rows(said_path)
        out.append(("Jev 1.14, facts as the person says them (7c)", said))
        out.append(("Jev 1.14, facts as said, p ≥ 0.8", with_bar(said, 0.8)))
    return out


def key_table(title: str, note: str, key: dict[str, set[str]], named: list[tuple[str, list[Judged]]],
              requests: list[measure_calls.Request]) -> list[str]:
    out = ["", f"### {title} ({len(key)} requests)", "", note, "",
           "| Version | Exactly the facts asked for | Picked a fact not asked for | Left out a fact asked for |",
           "|---|---|---|---|", lookup_line(requests, key)]
    return out + [hand_keyed_line(name, judged, key) for name, judged in named]


def versions_section(folder: Path, rows: list[Judged], models: list[str],
                     requests: list[measure_calls.Request]) -> list[str]:
    named = versions(folder, rows, models)
    random_key = {rid: set(label["facts"]) for rid, label in RANDOM.items()}
    text = ["", "## Every version against Claude's hand keys",
            "", "The p ≥ 0.8 and slot ≥ 0.9 bars were chosen on the hard key, after seeing its answers; the random key is "
            "the fresh check on them."]
    text += key_table("Random key", "A random 200 of the 2,688 requests (`measure_random_sample`): what ordinary use "
                      "looks like.", random_key, named, requests)
    text += key_table("Hard key", "Every turned-away request any judge picked a fact for, and the 25-request sample of "
                      "Jev's disagreements: hard cases, so it compares versions; it isn't a rate.", hand_key(), named, requests)
    listed_path = folder / "7b-measure-listed.jsonl"
    if listed_path.exists():
        unkeyed = [r for r in judged_rows(listed_path) if r.key is None and not r.error]
        text += ["", f"Turned away by the lookup: count + list (7b) picked a fact for "
                 f"{pct(sum(bool(r.picks) for r in unkeyed), len(unkeyed))}."]
    return text


NOT_RECORDED = "not_recorded"


def lookup_one(facts: dict, item: str, what: str) -> set[str]:
    return set(measure_calls.lookup(facts, item, what))


def single_ask_line(name: str, picks: list[set[str]], keys: list[str]) -> str:
    """Per ask: right means exactly the key's fact, or nothing when the key is not recorded."""
    want = [set() if k == NOT_RECORDED else {k} for k in keys]
    right = sum(p == w for p, w in zip(picks, want))
    extra = sum(bool(p - w) for p, w in zip(picks, want))
    missing = sum(bool(w - p) for p, w in zip(picks, want))
    return f"| {name} | {pct(right, len(keys))} | {extra} | {missing} |"


def same_reply(facts: dict, picks: set[str], key: str) -> bool:
    """What the designer hears is the same: the picked facts' recorded lines, or "I can't measure that" when none.
    A fact recorded as "I can't measure that" says the same as no fact."""
    def heard(ids: set[str]) -> set[str]:
        values = set()
        for fid in ids:
            thing, measurement = fid.split(".")
            value = str(facts[thing]["measurements"][measurement]["value"])
            if value != "I can't measure that":
                values.add(fid)
        return values
    return heard(picks) == heard(set() if key == NOT_RECORDED else {key})


def single_ask_section(folder: Path, named: list[tuple[str, list[Judged]]],
                       requests: list[measure_calls.Request]) -> list[str]:
    asks_path, rows_path = folder / "7d-asks.json", folder / "7d-single-asks.jsonl"
    if not (asks_path.exists() and rows_path.exists()):
        return []
    asks = json.loads(asks_path.read_text())
    answers = {int(json.loads(line)["item"].split(" | ")[0]): json.loads(line) for line in rows_path.read_text().splitlines()}
    facts = {task: measure_calls.facts_for(task, ROOT / "tasks") for task in {a["task"] for a in asks}}
    keys = [a["key"] for a in asks]
    jev = [set() if answers[n]["answer"] in (None, NOT_RECORDED) else {answers[n]["answer"]} for n in range(len(asks))]
    lookup = [lookup_one(facts[a["task"]], a["item"], a["what"]) for a in asks]
    text = ["", "## Test 7d: the random 200 as single asks", "",
            f"{len(asks)} single asks: requests Jev counted as one thing stay whole; a fresh subagent split the rest without "
            "seeing the facts, the lookup or any judge; a second fresh subagent keyed each ask from the fact list alone "
            "(`7d-asks.json`). Jev answered each with one pick: a fact, or not recorded.", "",
            "| Per single ask | Right | Picked a fact not asked for | Left out the fact asked for |", "|---|---|---|---|",
            single_ask_line("today's lookup, on the single ask", lookup, keys), single_ask_line("Jev 1.14, one pick", jev, keys)]
    same = [sum(same_reply(facts[a["task"]], p, a["key"]) for a, p in zip(asks, picks)) for picks in (lookup, jev)]
    text += ["", f"Same reply to the designer as the key's fact would give (a fact recorded as \"I can't measure that\" "
             f"says the same as no fact): lookup {pct(same[0], len(asks))}, Jev {pct(same[1], len(asks))}."]
    close = [a["close_call"] for a in asks]
    wrong = [n for n, (a, p) in enumerate(zip(asks, jev)) if not same_reply(facts[a["task"]], p, a["key"])]
    plate = sum(asks[n]["key"] == "tripod_clamp.plate_width" for n in wrong)
    text += [f"Of Jev's {len(wrong)} asks with a different reply, the keyer marked {sum(close[n] for n in wrong)} as close calls, "
             f"and {plate} are the clamp's plate width asked in other words."]
    request_key: dict[str, set[str]] = {}
    request_jev: dict[str, set[str]] = {}
    for ask, pick in zip(asks, jev):
        request_key.setdefault(ask["request"], set()).update(set() if ask["key"] == NOT_RECORDED else {ask["key"]})
        request_jev.setdefault(ask["request"], set()).update(pick)
    as_rows = [Judged(request=rid, model="Jev 1.14", key=None, picks=sorted(p), p_yes={}, error="") for rid, p in request_jev.items()]
    text += key_table("Whole requests, against the subagents' key", "Each request's key is the facts of all its single "
                      "asks. Same 200 requests as the random key.", request_key,
                      named + [("Jev 1.14, single asks (7d)", as_rows)], requests)
    mine = {rid: set(label["facts"]) for rid, label in RANDOM.items()}
    same = sum(mine[rid] == request_key[rid] for rid in request_key)
    text += ["", f"The subagents' key and Claude's key agree on {pct(same, len(request_key))} of the 200 requests."]
    return text


def main():
    folder = Path(sys.argv[1])
    rows = judged_rows(folder / "7-measure.jsonl")
    models = sorted({r.model for r in rows})
    judged = {r.request for r in rows}
    requests = [r for r in measure_calls.collect(ROOT / "results/runs", ROOT / "tasks")
                if r.id in judged]  # trials saved after the run aren't counted
    errors = Counter(r.model for r in rows if r.error)
    text = ["## Where the lookup answers: agreement with its facts", "",
            "| Model | Same set of facts | Facts on the same side | Picked a fact the lookup didn't | "
            "Left out a fact the lookup gave |", "|---|---|---|---|---|"]
    text += [answered_line(m, [r for r in rows if r.model == m]) for m in models]
    closer = Counter(label["closer"] for label in SAMPLE.values())
    text += ["", f"Hand sample of {len(SAMPLE)} Jev disagreements: nearer to what was asked, the judge {closer['judge']}, "
             f"the lookup {closer['lookup']}, neither {closer['neither']}."]
    text += ["", "## Where the lookup says \"I can't measure that\"", "",
             "| Model | Picked a fact | Read by hand | Same facts as Claude's hand check | Found a recorded fact asked for | "
             "Picked a fact not asked for | Real misses caught |", "|---|---|---|---|---|---|---|"]
    text += [no_answer_line(m, [r for r in rows if r.model == m]) for m in models]
    text += ["", f"Failed calls: {dict(errors) or 'none'}", "", "## Every turned-away request a model picked a fact for", ""]
    text += pick_list(rows, models)
    text += ["", "## Real misses", ""] + real_miss_counts(requests)
    text += versions_section(folder, rows, models, requests)
    text += single_ask_section(folder, versions(folder, rows, models), requests)
    out = "\n".join(text) + "\n"
    (folder / "7-measure.md").write_text(out)
    print(out)


if __name__ == "__main__":
    main()
