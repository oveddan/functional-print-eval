"""Ask a decisions model whether each drawn view of a failing check shows that failure legibly, and save every answer.

    uv run python scripts/results_site_view_audit.py --limit 10            # a trial run: prints cost per call
    uv run python scripts/results_site_view_audit.py --budget 2            # every failed view not yet judged
    uv run python scripts/results_site_view_audit.py --summarise           # summary.json and the site's file only

What is judged: each image in scripts/results_site_views.json whose view has state "fail" (counted failures first,
then failed test prints), with the check's caption (its title and the finding's detail). Ungraded views are left out:
the question asks about a failure, and an ungraded check has none to show. One typed yes/no question per image
(pbe/judges/decisions.py), the image as JPEG (Jev reads PNG and JPEG only; the views are WebP).

The judge is an LLM looking at a picture. A "yes" says the picture is legible for the failure its caption names, not
that the drawing or the check is right. No result changes: the answer is a note on the site, never a verdict.

Answers go to results/judges/<date>/view-audit.jsonl, one line per image, in the row format of
scripts/judge_known_answers.py plus what identifies the view. A run skips images already judged with the same image
bytes, caption and question version, so it can be stopped and resumed. The summary (view-audit-summary.json beside it)
and scripts/results_site_view_audit.json (committed; each view's URL to its answer, for scripts/results_site.py) cover
exactly the failed views in today's manifest. Rows for images since redrawn or dropped stay in the jsonl as the record
of what ran, are counted as superseded and left out of every share; the cost covers every row.
The key is read from OPENROUTER_API_KEY or 1Password and never printed.
"""
import argparse
import datetime
import hashlib
import io
import json
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pbe.judges import decisions as dz  # noqa: E402
from pbe.runner.llm import api_key  # noqa: E402

VIEWS = ROOT / "scripts/results_site_views.json"
OBJECTS = ROOT / "results/local/site-views/objects"
SITE_FILE = ROOT / "scripts/results_site_view_audit.json"
URL_PREFIX = "https://media.danoved.xyz/print-build-eval/site/"
TASKS = {p.name for p in (ROOT / "tasks").iterdir() if p.is_dir()}
THRESHOLD = 0.5  # p(yes) at or above this: the picture shows the failure
TEST = "view-audit"

QUESTION_VERSION = "v1"
QUESTION = dz.Noul(
    instructions="Does this image show this failure clearly enough for a person to see what is wrong?",
    criteria={"true": "Looking at the image with the caption, a person can find the problem the caption names: the "
                      "spot, the part or the measurement it is about is drawn and marked so it stands out.",
              "false": "The problem the caption names can't be found in the image: it isn't drawn, is too small or "
                       "hidden to make out, or nothing marks where it is."})


def state_for(caption: str, jpeg: bytes) -> list:
    return ["A drawing made by an automated check of a 3D-printable design. The check's finding, which the drawing "
            f"is meant to show: \"{caption}\"", dz.Image.jpeg(jpeg)]


# --- the views ---

class View(BaseModel):
    """One image to judge, and every manifest view that uses it (a drawing shared by identical designs)."""
    url: str
    caption: str
    check: str
    kind: str
    test_print: bool
    designs: list[str]

    @property
    def local(self) -> Path:
        return OBJECTS / self.url.removeprefix(URL_PREFIX)

    def sha(self) -> str:
        return hashlib.sha256(self.local.read_bytes()).hexdigest()

    def key(self) -> str:
        """What a resumed run matches on: the image's bytes, the caption and the question's version."""
        caption = hashlib.sha256(self.caption.encode()).hexdigest()[:16]
        return f"{self.sha()[:32]}:{caption}:{QUESTION_VERSION}"


def task_of(design: str) -> str:
    return next((part for part in design.split("/") if part in TASKS), "?")


def failed_views() -> list[View]:
    """Each failed view's image once, counted failures first, then test prints; in manifest order within each."""
    by_url: dict[str, View] = {}
    for design, entries in json.loads(VIEWS.read_text())["designs"].items():
        for entry in entries:
            if entry["state"] != "fail" or not entry["view"]:
                continue
            found = by_url.setdefault(entry["view"], View(url=entry["view"], caption=entry["caption"],
                                                          check=entry["check"], kind=entry["kind"],
                                                          test_print=bool(entry["test_print"]), designs=[]))
            found.designs.append(design)
    return sorted(by_url.values(), key=lambda v: v.test_print)


def jpeg_of(path: Path) -> bytes:
    """The WebP drawing as JPEG on white, each side inside Jev's 256 to 1568 px."""
    from PIL import Image as PILImage
    image = PILImage.open(path)
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        white = PILImage.new("RGBA", image.size, (255, 255, 255, 255))
        image = PILImage.alpha_composite(white, image)
    image = image.convert("RGB")
    image.thumbnail((1568, 1568))
    if min(image.size) < 256:
        scale = 256 / min(image.size)
        image = image.resize((round(image.width * scale), round(image.height * scale)))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=90)
    return out.getvalue()


# --- rows ---

class Row(BaseModel):
    """scripts/judge_known_answers.py's row, plus what identifies the view."""
    test: str = TEST
    item: str                     # the image's URL
    model: str
    question: str = "shows_failure"
    key: bool | None = None       # no key: a hand check is a separate file
    answer: bool | None = None    # p(yes) >= THRESHOLD; None on an error
    p: float | None = None
    agrees: bool | None = None
    seconds: float = 0.0
    cost: float = 0.0
    raw: dict | None = None
    error: str = ""
    audit_key: str
    question_version: str = QUESTION_VERSION
    caption: str
    check: str
    kind: str
    test_print: bool
    designs: list[str]


def judge(view: View, model: str, budget: dz.Budget) -> Row:
    base = dict(item=view.url, model=model, audit_key=view.key(), caption=view.caption, check=view.check,
                kind=view.kind, test_print=view.test_print, designs=view.designs)
    try:
        request = dz.Request(model=model, state=state_for(view.caption, jpeg_of(view.local)),
                             questions={"shows_failure": QUESTION})
        decision = dz.decide(request, budget)
    except dz.DecisionsError as error:
        if error.status == 402:
            raise
        return Row(**base, error=str(error))
    except (OSError, ValueError) as error:  # a missing or unreadable local copy: on record, the run goes on
        return Row(**base, error=f"{type(error).__name__}: {error}")
    answer = decision.answers.get("shows_failure")
    p = answer.noul if answer else None
    return Row(**(base | {"model": decision.model}), answer=None if p is None else p >= THRESHOLD, p=p,
               seconds=decision.seconds, cost=decision.cost, raw=decision.model_dump(),
               error="" if p is not None else "no noul answer")


def load_rows(path: Path) -> list[Row]:
    if not path.exists():
        return []
    return [Row.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]


def judged_keys(rows: list[Row], model: str) -> set[str]:
    return {r.audit_key for r in rows if not r.error and r.model.startswith(model)}


def run(views: list[View], model: str, budget: dz.Budget, workers: int, out: Path) -> list[Row]:
    """Judge each view, appending each answer as it lands. The cap or a 402 stops new calls; finished ones stay."""
    new: list[Row] = []
    with ThreadPoolExecutor(workers) as pool, open(out, "a") as f:
        futures = [pool.submit(judge, v, model, budget) for v in views]
        for future in as_completed(futures):
            try:
                row = future.result()
            except (dz.OverBudget, dz.DecisionsError) as stop:
                print(f"stopped: {stop}")
                for waiting in futures:
                    waiting.cancel()
                continue
            f.write(row.model_dump_json() + "\n")
            f.flush()
            new.append(row)
    return new


# --- the summary and the site's file ---

def current(rows: list[Row], views: list[View]) -> dict[str, tuple[View, Row | None]]:
    """{url: (view, its answer)} for exactly the failed views in today's manifest. An answer counts only if it was
    given for the same image bytes, caption and question version (its audit_key); the last good one wins. A view
    with no such answer maps to None. Rows for images the manifest no longer has are left out (superseded())."""
    answers: dict[str, Row] = {}
    for row in rows:
        if not row.error and row.p is not None:
            answers[row.audit_key] = row
    return {v.url: (v, answers.get(v.key())) for v in views}


def superseded(rows: list[Row], views: list[View]) -> list[Row]:
    """Rows kept in the jsonl as the record of what ran, for images or captions the manifest has since replaced."""
    keys = {v.key() for v in views}
    return [r for r in rows if r.audit_key not in keys]


def share(answers: list[Row]) -> dict:
    passing = sum(bool(r.answer) for r in answers)
    return {"views": len(answers), "pass": passing, "share": round(passing / len(answers), 3) if answers else None}


def summarise(rows: list[Row], views: list[View]) -> dict:
    judged = {url: (v, r) for url, (v, r) in current(rows, views).items() if r is not None}
    per_view = [(design, v, r) for v, r in judged.values() for design in v.designs]  # identical designs share an image
    groups: dict[tuple, list[Row]] = defaultdict(list)
    kinds: dict[str, list[Row]] = defaultdict(list)
    for design, v, r in per_view:
        groups[(task_of(design), v.check, v.kind)].append(r)
        kinds[v.kind].append(r)
    paid = [r for r in rows if r.cost]
    old = superseded(rows, views)
    return {
        "question": QUESTION.instructions, "question_version": QUESTION_VERSION, "threshold": THRESHOLD,
        "manifest": f"{VIEWS.relative_to(ROOT)} version {json.loads(VIEWS.read_text()).get('version')}",
        "models": sorted({r.model for _, r in judged.values()}),
        "judge": "an LLM decisions model (OpenRouter Decisions API) looking at each drawing with its caption",
        "current_failed_images": len(views), "images_judged": len(judged),
        "images_not_judged": sorted(url for url, (_, r) in current(rows, views).items() if r is None),
        "views_covered": len(per_view), "current_failed_views": sum(len(v.designs) for v in views),
        "overall": share([r for _, _, r in per_view]),
        "counted_failures": share([r for _, v, r in per_view if not v.test_print]),
        "test_prints": share([r for _, v, r in per_view if v.test_print]),
        "by_kind": {k: share(v) for k, v in sorted(kinds.items(), key=lambda kv: (share(kv[1])["share"], kv[0]))},
        "by_task_check_kind": [{"task": t, "check": c, "kind": k} | share(v) for (t, c, k), v in sorted(groups.items())],
        "low_confidence": sum(1 for _, r in judged.values() if 0.3 <= r.p <= 0.7),
        "superseded_rows": {"count": len(old), "note": "rows in the jsonl for images or captions no longer in the "
                            "manifest (redrawn or dropped); kept as the record of what ran, left out of every share"},
        "error_rows": sum(1 for r in rows if r.error),
        "calls_all_runs": len(paid), "cost_all_runs": round(sum(r.cost for r in paid), 6),
        "cost_per_call_median": statistics.median(r.cost for r in paid) if paid else None,
    }


def site_file(rows: list[Row], views: list[View]) -> dict:
    """{view url: {shows_failure, p, model}} for the current manifest's judged failed views only: what
    scripts/results_site.py attaches as view.audit."""
    return {url: {"shows_failure": bool(r.answer), "p": round(r.p, 3), "model": r.model}
            for url, (_, r) in sorted(current(rows, views).items()) if r is not None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=float, default=2.0, help="dollars, a hard cap on this run's calls")
    parser.add_argument("--limit", type=int, default=None, help="judge at most this many new images")
    parser.add_argument("--only", default=None, help="only views whose kind, check or URL contains this")
    parser.add_argument("--model", default=dz.JEV, choices=dz.MODELS)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path, default=ROOT / "results/judges" / datetime.date.today().isoformat())
    parser.add_argument("--summarise", action="store_true", help="write the summary and the site's file, no calls")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{TEST}.jsonl"
    rows = load_rows(path)
    if not args.summarise:
        done = judged_keys(rows, args.model)
        todo = [v for v in failed_views() if not args.only or args.only in (v.kind, v.check) or args.only in v.url]
        todo = [v for v in todo if v.key() not in done][:args.limit]
        print(f"{len(todo)} images to judge with {args.model}, {len(done)} already judged")
        if todo:
            budget = dz.Budget(args.budget)
            api_key()  # once, before the threads, so 1Password asks once
            new = run(todo, args.model, budget, args.workers, path)
            paid = [r.cost for r in new if r.cost]
            if paid:
                print(f"{len(new)} calls ({sum(1 for r in new if r.error)} errors), ${sum(paid):.5f} spent, "
                      f"per call median ${statistics.median(paid):.6f}, max ${max(paid):.6f}")
                tokens = [r.raw["usage"]["input_tokens"] for r in new if r.raw]
                print(f"input tokens per call: median {statistics.median(tokens):.0f}, max {max(tokens)}")
                print(f"all {len(failed_views())} failed images at the median: ${statistics.median(paid) * len(failed_views()):.4f}")
            rows = load_rows(path)
    views = failed_views()
    summary = summarise(rows, views)
    (args.out / f"{TEST}-summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    SITE_FILE.write_text(json.dumps({"version": 1, "question": QUESTION.instructions, "threshold": THRESHOLD,
                                     "run": str(path.relative_to(ROOT)), "views": site_file(rows, views)}, indent=1) + "\n")
    if summary["images_not_judged"]:
        print(f"{len(summary['images_not_judged'])} current failed images have no answer yet")
    print(f"overall {summary['overall']}; {summary['superseded_rows']['count']} superseded rows left out; saved {path.relative_to(ROOT)} and {SITE_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
