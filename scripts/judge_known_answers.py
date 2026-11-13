"""Run OpenRouter's decisions models on four questions whose answers are known, and save every raw answer.

    uv run python scripts/judge_known_answers.py --budget 4 [--tests 1,2,3,4] [--limit N] [--data-root PATH]

Tests (docs/decisions-api.md):
  1  does a submission's text ask for supports?   key: pbe/parts/supports.py, plus results/judges/hand-labels.yaml
  2  Dan's spoken outcomes as verdicts            key: the colours coupons/fit_cards.py gives them, plus hand labels
  3  test-print photos: roof looks, and Box       key: Dan's outcomes, cells placed by pbe/judges/photo_cells.py
  3c the roof photos again, ok or failed, with   key: Dan's outcomes; examples from other cells only
     two labelled example crops of each
  4  a checklist over the 48 Estoa transcripts    key: tool calls where code decides (pbe/judges/transcripts.py)
  5  failure records into classes, and flagging    key: each record's class in seeds/; flags by holding a class out
  6  round 3 test-print clips, Gemini Decision 1:  key: round 3's records, cells placed by pbe/judges/video_cells.py;
     silent, then with the sound (6-video-silent.jsonl, 6-video-audio.jsonl), --passes times each

Answers go to results/judges/<date>/<test>.jsonl, one line per model and item, with the key beside the answer.
`--data-root` reads round 3's records and code from another checkout (they live on the round 3 branch).
The key is read from OPENROUTER_API_KEY or 1Password and never printed. Photos and clips are read from Dropbox, never
copied: each clip is made into a short H.264 MP4 in a temp folder and sent inline, never as a link.
"""
import argparse
import datetime
import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pbe.judges import decisions as dz  # noqa: E402
from pbe.judges import failures, photo_cells, transcripts, video_cells  # noqa: E402
from pbe.parts.submission import Submission  # noqa: E402
from pbe.runner.llm import api_key  # noqa: E402

HAND = yaml.safe_load((ROOT / "results/judges/hand-labels.yaml").read_text())


class Row(BaseModel):
    test: str
    item: str
    model: str
    question: str
    key: str | bool | None        # None: no key, the answer is recorded but not scored
    answer: str | bool | None     # the model's pick (choice) or p(yes) >= 0.5 (noul); None on an error
    p: float | None = None        # p(yes), or the probability of the pick
    agrees: bool | None = None
    seconds: float = 0.0
    cost: float = 0.0
    raw: dict | None = None
    error: str = ""


def module_from(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- reading answers ---

def noul_rows(decision: dz.Decision, test: str, item: str, keys: dict[str, bool | None]) -> list[Row]:
    rows = []
    for qid, key in keys.items():
        answer = decision.answers.get(qid)
        p = answer.noul if answer else None
        said = None if p is None else p >= 0.5
        rows.append(Row(test=test, item=item, model=decision.model, question=qid, key=key, answer=said, p=p,
                        agrees=None if key is None or said is None else said == key))
    return rows


def choice_row(decision: dz.Decision, test: str, item: str, qid: str, key: str | None) -> Row:
    answer = decision.answers.get(qid)
    pick = answer.choice if answer else None
    p = (answer.probabilities or {}).get(pick) if answer and pick else None
    return Row(test=test, item=item, model=decision.model, question=qid, key=key, answer=pick, p=p,
               agrees=None if key is None or pick is None else pick == key)


def with_call(rows: list[Row], decision: dz.Decision) -> list[Row]:
    """Spread one call's time and cost over its rows; keep the raw answer on the first."""
    for i, row in enumerate(rows):
        row.seconds, row.cost = decision.seconds / len(rows), decision.cost / len(rows)
        row.raw = decision.model_dump() if i == 0 else None
    return rows


def failed_row(test: str, item: str, model: str, error: Exception) -> Row:
    """test: the file the row belongs in (5-held-out, not 5-classes, for a held-out call)."""
    return Row(test=test, item=item, model=model, question="", key=None, answer=None, error=str(error))


# --- test 1: supports ---

class SupportsCase(BaseModel):
    item: str
    text: str
    plain: bool
    expects: bool


def instructions_text(sub: Submission) -> str:
    parts = [f"Note: {sub.note}"]
    parts += [f"Print orientation for {part.id}: {part.print_orientation}" for part in sub.parts]
    parts += [f"Step {i}: {step.text}" for i, step in enumerate(sub.manual, start=1)]
    return "\n".join(parts)


def supports_cases(data_root: Path) -> list[SupportsCase]:
    """The 5 submissions supports.py finds, the 10 that assume supports, and the 7 it was written to turn down."""
    supports = module_from(data_root / "pbe/parts/supports.py", "supports")
    implied = HAND["supports"]["expects_without_asking"]
    refused = HAND["supports"]["conditional_or_refused"]
    cases = []
    for path in sorted((data_root / "results/runs").glob("**/submission.yaml")):
        item = str(path.parent.relative_to(data_root / "results/runs"))
        if "support" not in path.read_text().lower():
            continue  # nothing to find; skips parsing most of the 1140
        sub = Submission.model_validate(yaml.safe_load(path.read_text()))
        plain = bool(supports.printed_with_supports(sub))
        if plain or item in implied or item in refused:
            cases.append(SupportsCase(item=item, text=instructions_text(sub), plain=plain,
                                      expects=plain or item in implied))
    return cases


def run_supports(case: SupportsCase, model: str, budget: dz.Budget) -> list[Row]:
    decision = dz.supports_questions(case.text, model, budget)
    rows = noul_rows(decision, "1-supports", case.item, {"asks_plainly": case.plain, "expects_supports": case.expects})
    return with_call(rows, decision)


# --- test 2: spoken outcomes ---

class Outcome(BaseModel):
    item: str
    job: str
    words: str
    key: str
    source: str


def outcome_cases(data_root: Path) -> list[Outcome]:
    fit_cards = module_from(data_root / "coupons/fit_cards.py", "fit_cards")
    colour_names = {fit_cards.GOOD: "good", fit_cards.LOOSE: "too_loose", fit_cards.TIGHT: "too_tight"}
    cases = []
    for card in fit_cards.cards():
        for attempt in card.tries:
            if attempt.colour == fit_cards.UNTRIED:
                continue
            key = colour_names[attempt.colour]
            if card.shape == "strand" and key == "too_tight":
                key = "failed"  # the strand card colours a messed-up roof red
            words = attempt.said.split(": ", 1)[-1] if card.shape == "strand" else attempt.said
            cases.append(Outcome(item=f"{card.title} @ {attempt.size:g}", job=card.job, words=words, key=key,
                                 source="coupons/fit_cards.py"))
    strand_said = [t.said for card in fit_cards.cards() if card.shape == "strand" for t in card.tries]
    return cases + roof_outcomes(data_root, strand_said)


def on_strand_card(item: str, strand_said: list[str]) -> bool:
    """fit_cards.py's strand card already has ring roofs 2 to 5 ("ring roof 2: ...") and GPT's roof crop."""
    if item.startswith("ring roof "):
        return any(said.startswith(item + ":") for said in strand_said)
    return "gpt" in item and any(said.startswith("GPT's roof") for said in strand_said)


def roof_outcomes(data_root: Path, strand_said: list[str]) -> list[Outcome]:
    """Every roof cell, span and crop fit_cards.py doesn't colour, keyed by hand (results/judges/hand-labels.yaml).
    One row per record, even where two records' words are the same."""
    r3 = yaml.safe_load((data_root / "results/predictions/round3-coupons.yaml").read_text())
    r3b = yaml.safe_load((data_root / "results/predictions/round3b-roofs.yaml").read_text())
    said = [(f"ring roof {c['cell']}", c["outcome"]) for c in r3["G_ring_roofs"]["cells"]]
    said += [(f"{r['span_mm']} mm span", r["outcome"]) for r in r3b["Q_spans"]["roofs"]]
    said += [(f"roof crop {c['trial']}", c["outcome"]) for c in r3b["roof_crops"]["crops"] if c.get("outcome")]
    job = "prints as a solid roof, no loose strands"
    cases = []
    for item, outcome in said:
        words = outcome.split(" (Dan")[0]
        key = "good" if words in HAND["roofs"]["good"] else "failed" if words in HAND["roofs"]["failed"] else None
        if key and not on_strand_card(item, strand_said):
            cases.append(Outcome(item=item, job=job, words=words, key=key, source="results/judges/hand-labels.yaml"))
    return cases


def run_outcome(case: Outcome, model: str, budget: dz.Budget) -> list[Row]:
    decision = dz.verdict_from_words(case.job, case.words, model, budget)
    return with_call([choice_row(decision, "2-outcomes", case.item, "verdict", case.key)], decision)


# --- test 3: photos ---

def photo_cache() -> dict[str, bytes]:
    folder = Path.home() / photo_cells.DROPBOX_PHOTOS
    return {photo: dz.photo_jpeg(folder / photo) for photo in {c.photo for c in photo_cells.CELLS}}


def run_roof(cell: photo_cells.Cell, photos: dict[str, bytes], model: str, budget: dz.Budget) -> list[Row]:
    crop = dz.crop_jpeg(photos[cell.photo], cell.edges)
    decision = dz.roof_from_photo(crop, cell.what, model, budget)
    row = choice_row(decision, "3-photos", f"{cell.photo.split()[-1]} {cell.name}", "looks", None)
    row.key, row.agrees = cell.clean, None if row.answer is None else (row.answer == "clean") == cell.clean
    return with_call([row], decision)


def run_roof_with_references(cell: photo_cells.Cell, photos: dict[str, bytes], model: str,
                             budget: dz.Budget) -> list[Row]:
    """Test 3c: ok or failed, with two example crops of each from other cells (leave one out)."""
    references = [dz.Reference(verdict="ok" if ref.clean else "failed", jpeg=dz.crop_jpeg(photos[ref.photo], ref.edges))
                  for ref in photo_cells.references_for(cell)]
    crop = dz.crop_jpeg(photos[cell.photo], cell.edges)
    decision = dz.roof_with_references(crop, cell.what, references, model, budget, examples_in_criteria=model == dz.JEV)
    row = choice_row(decision, "3c-references", f"{cell.photo.split()[-1]} {cell.name}", "verdict",
                     "ok" if cell.clean else "failed")
    return with_call([row], decision)


def run_box(photo: str, photos: dict[str, bytes], budget: dz.Budget) -> list[Row]:
    """Jev's Box, one question per cell placed by position; a hit when the box's centre is inside Claude's box."""
    cells = [c for c in photo_cells.CELLS if c.photo == photo and c.where]
    questions = {f"c{i}": dz.Box(instructions=f"Find {c.where} on this test print.") for i, c in enumerate(cells)}
    decision = dz.decide(dz.Request(model=dz.JEV, state=[dz.Image.jpeg(photos[photo])], questions=questions), budget)
    rows = []
    for i, cell in enumerate(cells):
        answer = decision.answers.get(f"c{i}")
        hit = None
        if answer and answer.box:
            x, y = answer.box.centre()
            e = cell.edges
            hit = e.left <= x <= e.right and e.top <= y <= e.bottom
        rows.append(Row(test="3-box", item=f"{photo.split()[-1]} {cell.name}", model=decision.model, question="where",
                        key=True, answer=hit, agrees=hit, p=answer.confidence if answer else None))
    return with_call(rows, decision)


# --- test 4: Estoa transcripts ---

def run_checklist(path: Path, runs: Path, model: str, budget: dz.Budget) -> list[Row]:
    messages = transcripts.load(path)
    item = str(path.parent.relative_to(runs))
    keys = transcripts.code_keys(messages, can_test="/can_test/" in str(path))
    questions = {i.id: i.question for i in transcripts.ITEMS}
    decision = dz.checklist(transcripts.render(messages), questions, model, budget)
    rows = noul_rows(decision, "4-checklist", item, {i.id: keys.get(i.id) for i in transcripts.ITEMS})
    return with_call(rows, decision)


# --- test 5: failure classes ---

def run_failure(failure: failures.Failure, classes: list[failures.FailureClass], model: str, budget: dz.Budget,
                hold_out: bool) -> list[Row]:
    """With every class (the key is the record's class), or with its class held out (the key is "none")."""
    options = failures.criteria(classes, leave_out=failure.cls if hold_out else None)
    decision = dz.failure_class(failure.text, options, model, budget)
    test = "5-held-out" if hold_out else "5-classes"
    row = choice_row(decision, test, f"{failure.source}:{failure.id}", "class", failures.NONE if hold_out else failure.cls)
    if not hold_out and row.answer is not None:
        row.agrees = failure.accepts(row.answer)  # a record's second class (`also:`) counts too
    return with_call([row], decision)


# --- test 6: video ---

def footage_cache() -> dict[tuple[str, bool], dz.Footage]:
    """Each clip twice, silent and with its sound, made once before the threads start."""
    folder = Path.home() / video_cells.DROPBOX_FOOTAGE
    return {(c.file, audio): dz.video_mp4(folder / c.file, audio) for c in video_cells.CLIPS for audio in (False, True)}


def clip_rows(decision: dz.Decision, test: str, item: str, clip: video_cells.Clip) -> list[Row]:
    rows = []
    for asked in clip.asked:
        if isinstance(asked.key, bool):
            rows += noul_rows(decision, test, item, {asked.id: asked.key})
        else:
            rows.append(choice_row(decision, test, item, asked.id, asked.key))
    return rows


def run_clip(clip: video_cells.Clip, footage: dz.Footage, audio: bool, n: int, budget: dz.Budget) -> list[Row]:
    test = "6-video-audio" if audio else "6-video-silent"
    decision = dz.about_clip(footage, clip.shows, {a.id: a.question for a in clip.asked}, budget)
    return with_call(clip_rows(decision, test, f"{clip.short} pass {n}", clip), decision)


def video_jobs(passes: int, limit: int | None, budget: dz.Budget):
    footage = footage_cache()
    jobs = []
    for audio in (False, True):
        test = "6-video-audio" if audio else "6-video-silent"
        for clip in video_cells.CLIPS[:limit]:
            for n in range(1, passes + 1):
                jobs.append((test, f"{clip.short} pass {n}", dz.GEMINI,
                             lambda c=clip, a=audio, n=n: run_clip(c, footage[(c.file, a)], a, n, budget)))
    return jobs


# --- running ---

class Stop(Exception):
    """The cap, or a 402: no more calls."""


def one(job) -> list[Row]:
    test, item, model, thunk = job
    try:
        return thunk()
    except dz.OverBudget as error:
        raise Stop(str(error)) from None
    except dz.DecisionsError as error:
        if error.status == 402:
            raise Stop(str(error)) from None
        return [failed_row(test, item, model, error)]
    except Exception as error:  # a bug in reading an answer: keep it on record, keep what was paid for
        return [failed_row(test, item, model, error)]


def run_all(jobs, workers: int) -> list[Row]:
    """jobs: (test file, item, model, thunk). A failure becomes a row and the rest go on. A 402 or the cap
    cancels the calls not yet started; every call that finished is kept."""
    rows: list[Row] = []
    with ThreadPoolExecutor(workers) as pool:
        futures = [pool.submit(one, job) for job in jobs]
        for future in as_completed(futures):
            try:
                rows.extend(future.result())
            except Stop as stop:
                print(f"stopped: {stop}")
                for waiting in futures:
                    waiting.cancel()
    return rows


def jobs_for(test: str, data_root: Path, limit: int | None, budget: dz.Budget, passes: int = 1):
    if test == "1":
        cases = supports_cases(data_root)[:limit]
        return [("1-supports", c.item, m, lambda c=c, m=m: run_supports(c, m, budget)) for c in cases for m in dz.MODELS]
    if test == "2":
        cases = outcome_cases(data_root)[:limit]
        return [("2-outcomes", c.item, m, lambda c=c, m=m: run_outcome(c, m, budget)) for c in cases for m in dz.MODELS]
    if test == "3":
        photos = photo_cache()
        cells = photo_cells.CELLS[:limit]
        jobs = [("3-photos", c.name, m, lambda c=c, m=m: run_roof(c, photos, m, budget)) for c in cells for m in dz.MODELS]
        boxed = sorted({c.photo for c in photo_cells.CELLS if c.where})
        return jobs + [("3-box", p, dz.JEV, lambda p=p: run_box(p, photos, budget)) for p in boxed]
    if test == "3c":
        photos = photo_cache()
        cells = photo_cells.CELLS[:limit]
        return [("3c-references", c.name, m, lambda c=c, m=m: run_roof_with_references(c, photos, m, budget))
                for c in cells for m in dz.MODELS]
    if test == "4":
        runs = data_root / "results/runs"
        paths = transcripts.estoa_trials(runs)[:limit]
        return [("4-checklist", str(p.parent.relative_to(runs)), m, lambda p=p, m=m: run_checklist(p, runs, m, budget)) for p in paths for m in dz.MODELS]
    if test == "5":
        seeds = ROOT / "seeds"
        classes, cases = failures.load_classes(seeds), failures.load_failures(seeds)[:limit]
        return [("5-held-out" if h else "5-classes", f"{c.source}:{c.id}", m,
                 lambda c=c, m=m, h=h: run_failure(c, classes, m, budget, h))
                for h in (False, True) for c in cases for m in dz.MODELS]
    if test == "6":
        return video_jobs(passes, limit, budget)
    raise ValueError(f"no test {test}")


def save(rows: list[Row], out: Path):
    out.mkdir(parents=True, exist_ok=True)
    by_test: dict[str, list[Row]] = {}
    for row in rows:
        by_test.setdefault(row.test, []).append(row)
    for test, test_rows in by_test.items():
        with open(out / f"{test}.jsonl", "w") as f:
            for row in test_rows:
                f.write(row.model_dump_json() + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=float, required=True, help="dollars, a hard cap: a call starts only if its most possible cost fits")
    parser.add_argument("--tests", default="1,2,3,4")
    parser.add_argument("--limit", type=int, default=None, help="items per test, for a trial run")
    parser.add_argument("--data-root", type=Path, default=ROOT)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--passes", type=int, default=3, help="test 6: times each clip is asked, to see how answers vary")
    parser.add_argument("--out", type=Path, default=ROOT / "results/judges" / datetime.date.today().isoformat())
    args = parser.parse_args()
    budget = dz.Budget(args.budget)
    api_key()  # once, before the threads, so 1Password asks once
    rows = []
    try:
        for test in args.tests.split(","):
            rows += run_all(jobs_for(test, args.data_root.resolve(), args.limit, budget, args.passes), args.workers)
            print(f"test {test}: {len(rows)} rows so far, ${budget.spent:.4f} spent")
    finally:
        save(rows, args.out)  # whatever finished, even if a test crashed
    print(f"saved to {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}")


if __name__ == "__main__":
    main()
