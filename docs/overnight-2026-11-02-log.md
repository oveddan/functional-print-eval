# Loop log

## Summary: loop stopped (2026-11-03, early morning)

**The goal changed.** Dan: build a framework for this kind of eval and learn what makes it hard, not the best final task set. Tonight is for learning from runs. Questions wait for the train review. See `docs/lessons.md`.

**Stopped: the budget.** $8.74 used of the $9.00 limit, and another round costs more than what's left. Everything below is committed on this branch, with tests passing.

**The main findings.**
- On the tripod, what separates models is printing and geometry, not finding out facts. 6 of 34 trials pass when models ask, 1 of 10 when they're handed the facts.
- One check, `bridges`, decides most of it, on both parts. Without it, the tripod goes from 6 to 12 of 34 and the wheel from 3 to 9 of 22, and the order of the models changes. It rests on one tangled print.
- A model's rank doesn't carry across parts. Opus and Sol go 0 of 3 on the tripod, and on the wheel each passes once and fails neither trial.

**Trustworthy:** the runner and sandbox, the three-way verdict (pass, fail, not graded), the nut checks and the tripod checks, within the limits written down. 231 tests pass. Each reference passes every check, and each wrong design fails only its own. I read or measured every tripod failure in both runs: since the first pilot's two faults and Luna's, no failure has turned out to be the check's fault. That's a reading by me, not an independent one.

**Not trustworthy yet:**
- One to three trials per model, so these are pilots, not pass rates. Grok has one tripod trial; DeepSeek Pro has none with the facts given (the cap stopped it).
- The bearing wheel's request is mine. Dan hasn't seen it, so its runs are exploratory. Its door and sizes are invented; only the bearing seats are recorded.
- `pbe/wheel.py` had one review, by Sonnet: 3 findings fixed, 3 written down as limits. Reading the runs then found 3 verdicts I'd invented without a record behind them (a seat a little short, Opus's layer rounding, a through bore). There may be more. The 0.5 mm allowance is my choice.
- M8 wasn't run: most of its sizes aren't settled by any record.

**Limitations for the report, not to-dos:** nothing physical comes from Dan before publishing, and no model's design is printed. What the records can't decide is not graded. That rate is reported beside the pass rate: on the tripod's 34 trials, R4 isn't graded 14 times, R2 11, R3 9.

**Results:** see [the results page](https://claude.ai/artifact/8FoztxxrwV6ioveQhz8gY6) (renders, verdicts, reasons, the loop diagram), `docs/lessons.md`, and `uv run python scripts/digest.py RUN --why`.

| Tripod, `can_ask`, passes of trials | With `bridges` | Without it |
|---|---|---|
| Gemini 3.8 Flash | 2 of 3 | 2 of 3 |
| Gemini 4 Argon | 2 of 3 | 3 of 3 |
| Grok 4.7 | 1 of 1 | 1 of 1 |
| DeepSeek 4.1 Flash | 1 of 3 | 2 of 3 |
| Opus 5.5 | 0 of 3 | 2 of 3 |
| Sonnet 5.5 | 0 of 3 | 1 of 3 |
| GPT-6 Luna | 0 of 3 | 1 of 3 |
| Haiku, DeepSeek Pro, GPT-6.1 Sol, Qwen, GLM | 0 of 3 each | 0 of 3 each |

| Wheel, `can_ask`, 2 trials each, wording unreviewed | Passes | Not graded | Failed |
|---|---|---|---|
| Opus 5.5 | 1 | 1 | 0 |
| GPT-6.1 Sol | 1 | 1 | 0 |
| Gemini 3.8 Flash | 1 | 0 | 1 (a build error) |
| Gemini 4 Argon | 0 | 2 | 0 |
| Qwen, GLM | 0 | 1 each | 1 each |
| Haiku, Sonnet, DeepSeek Flash, GPT-6 Luna | 0 | 0 | 2 each |
| DeepSeek Pro | 0 | 0 | 2 (build errors) |

**For the train:**
1. Should a plain recess roof fail `bridges`? Your first plate had one and worked, but came out messy. It's the biggest single lever on the ranking.
2. GPT-6.1 Sol wouldn't design a plate on any trial, for a stated reason: the clamp's size isn't known. Your words ask "how hard would it be". Is declining a failure?
3. Do the tripod's checks judge the right things? The brief's table has every limit. The bolt's 10 mm length and the 37 to 39 mm width are labelled assumptions.
4. A printed screw is not graded on the bolt checks. Right, given your words ask for "the part that screws in"?
5. Is an upside-down dovetail a fit fault (R2, C5) rather than the which-face check in R3 (C2)?
6. The person repeats the clamp's style to any question about its size. Should they say "I don't have calipers" instead?
7. Models can't see what they built, so CAD slips look like design errors. Should a render or measurements come back to them? That would change what's being measured.
8. Should a check's verdict be allowed at all if it isn't on the brief's table of what the records decide? I broke that three times on the wheel.
9. Is the bearing wheel's wording usable, and which classes to generalize next (no scenario generator yet)?

Newest first. The summary goes at the top when the loop stops.

## Iteration 3: bearing wheel (ladder step 2), started out of order on purpose
Why: it has the strongest record behind it, and it tests whether the bridged-hole failure carries over to a different part. The brief states which sizes the records decide before anything was built. The request is unreviewed and labelled so.
Review: one Sonnet pass. Fixed trimmed hub bosses, a skipped printed sleeve, blind coupons. Declined, in the brief as limits: nested tyre and hub, a seat-sized window, a tight ring in an over-deep seat.
Runs: `pilot-wheel`, 22 trials, $2.07. Three clever routes past the roof: a cone (Opus, Gemini 3.8 Flash), two halves (Sol), a stack from one side (Argon). Eight of 11 models thought to keep the inner ring free on t1, unasked and ungraded.
Scoring walk:
- Real-world relevance: the bearing and its seats are real, the door and sizes are invented. Weaker than the tripod.
- Task design: decent. It forces the bridged-hole problem, and has several ways through.
- Grader reliability: the fit rests on a printed record, the best of any task. But 3 verdicts of mine had no record behind them.
- Evidence of model limitations: textbook interference fits fail on this printer; coupons that only test the wrong side.
- Reproducibility: as the tripod. Two trials a model.
- Human expertise and review: none yet. Dan hasn't seen the wording.
- Insight: the same class fails on a second part, and ranks don't carry across parts.
My fault: an alias of 608 loaded as a number and crashed the first pilot on its first question. No trial was lost; a test now covers it.

## Iteration 2: tripod plate (ladder step 5)
Runs: `pilot-tripod` (34 trials, $3.18), `pilot-tripod-given` (10 trials, $1.11). Findings are in `docs/lessons.md`.
Eval's faults found: Gemini's groove read as the wrong face; the person answering camera questions with clamp facts; a closed-hole assumption (Luna); a misleading "prints its own screw" when no plate exists. 12 review fixes changed 4 of 34 verdicts and no pass.
Scoring walk:
- Real-world relevance: strong. Dan's own first message and the plate he printed. The bolt's length and width range are assumptions.
- Task design: decent. The problem is open and the mechanism isn't named, but asking doesn't separate models, so a task meant to test C1 is really testing C6 and C7.
- Grader reliability: code only, no LLM judge. Every failure read; shape coverage grew with each run. `bridges` rests on a thin record.
- Evidence of model limitations: good and specific. Print orientation against use, CAD slips the model can't see, declining to guess.
- Reproducibility: saved runs, regrade without a key, commit stamped on each trial. Three trials can't place a model.
- Human expertise and review: weak until the train. The limits come from Dan's records, but he hasn't reviewed these checks.
- Insight: the strongest part so far, in `docs/lessons.md`. Needs his rewrite.
Only Dan can supply: questions 1 to 6 above.

## Iteration 1, in progress: `tasks/nut-knob/` (M3, M5, M8)
Why it's next: step 1 of the ladder, and the only thing it depends on (the runner) is done.

Built: `tests/test_nut_knob.py` and `tests/test_runner.py`. Every wrong design on the charter's list fails its check and only its check; every design the charter says must pass does.

Code review, in four rounds at `high`. Round 1 ran on the wrong range (I passed `76260f1` and it reviewed that commit, not the diff from it), so it reviewed the runner instead. Its findings were still useful, so I kept them and counted it apart from the charter's three rounds on the real diff.

Fixed, each with a test:
- Runner: model-written part code inherited the environment holding the OpenRouter key. It now gets no environment, and on macOS it runs under `sandbox-exec` with no network, no child processes and writes only to its own folders. Without a sandbox it refuses to run unless `PBE_NO_SANDBOX=1`. This had to be fixed before any model ran.
- Runner: a dropped connection, tool arguments that aren't a JSON object, or a crash in a check could end a run and lose a paid trial. Part ids became file paths unchecked (`../../x` wrote outside the run). Reruns forgot the cost of the failed attempt. `-dirty` was set by the run's own output, so it meant nothing.
- Nut checks: false passes on a filleted square and a pentagon read as hexagons (area only), a round collar a nut's corners can't pass, a hex-shaped lightening cell taken for the pocket, a sleeve inside the pocket, a hex cut right through. False fails on a 45 degree cone roof, a round relief under the pocket, a deeper round hole elsewhere, and a 1 mm chamfered mouth.
- Spacer R3: an 8 mm bore with one 0.4 mm neck passed. `connected_bodies` counted a sealed void as a second body (found by the new tests, not the review).
- Not-graded is now honest in three places: a check needing a part or pocket that isn't there says not graded (one mistake counts once); a narrow ledge around a hole that no print measured; and "loose" rows nobody has turned over (below).

Decided, and Dan should check these:
- **"Loose" is not graded, except at +0.3.** The review pointed out that coupon B's "loose" rows were never turned upside down, and the request asks whether the nut stays in upside down. So M5 +0.2 and M8 +0.1 and +0.2 are not graded until Dan turns the coupon over; +0.3 fails, because nuts fell out at +0.3 on the tripod build (a different filament, so it's evidence, not proof). `all_pass` doesn't change either way.
- **A plain nut pocket opening at the bed is not graded for M5 and M8.** Its roof is a ring 1.7 to 2.9 mm wide around the bolt hole. The narrowest roof seen to tangle is the Arca plate's at 3.1 mm, and the allowance for an ordinary overhang (1.5 mm) is a guess. Coupon A's H reached 7.8 mm. No print measured this range, so `bridges` says not graded (`narrowest_tangled_mm` in `catalog/printer.yaml`). M3 passes as an ordinary overhang at 1.4 mm, on that unmeasured 1.5 mm guess.
- **Two sentences added to the request**, so everything graded is stated: "It's one printed piece" and "can't be pushed out through the far side". The person's words are still Dan's to approve.

Declined, and why:
- Text match for a drill-out instruction: "Reaming isn't required for the bolt hole" or "Clear any stringing from the bolt hole" still count as being told to clear it, if the design also has a closed layer across the bolt path. It's a text match, so the check quotes the sentence it matched. Read any drill-out pass by hand.
- Spacer `round_outline` samples the middle only: a square prism with a round band at mid-length passes. Nobody would draw that for a control task.
- `_in_the_manual` counts "No need to print the coupon". Shipping a coupon and saying not to print it is unlikely, and catching it would cost false fails on "print the coupon, not the knob, first".
- A resume blocked by the run's budget: `--regrade` already finishes that trial.
- A response billed but cut off in transit can't be counted, because its cost was in the part that never arrived. OpenRouter's credit figure is checked before each pilot, so the hard budget doesn't depend on it.
- `FELL_OUT` repeats `catalog/printer.yaml`'s `observed_fits`: reading it would mean parsing keys like `plus_0_30`, which is worse than a commented constant.
- An M3 pocket far too big (+1.2) is not graded rather than failed. Nothing measured M3 above +0.3 and I won't invent an upper limit. A limitation for the report.

Environment: `request_keep_awake` was denied by the auto-mode classifier at 18:09:02 CET, no reason given. I told Dan, and didn't work around it with `caffeinate`. The Mac is awake during active turns only.

## Iteration 0 (before the loop): set up
- Stacked this branch on `assembly-sim`. Added `pbe/nuts.py`, `pbe/sections.py`, `tasks/nut-knob/` and task families in `pbe/tasks.py`. All three references pass; 29 existing tests pass. No tests for the knob yet, no review yet.
- Key holder armed. Baseline: $0.2606 used of $10.00.

## For Dan
- Limitation for the report, not a to-do: coupon B's "loose" rows were never turned upside down, so M5 +0.2 and M8 +0.1 and +0.2 report not graded.
- `catalog/printer.yaml` `narrowest_tangled_mm`: a plain M5 or M8 pocket roof reports "not measured" rather than failing. The records can't decide it. Limitation for the report.
- Limitation for the report: M3 above +0.3 was never measured, so it has no upper limit and reads not graded.
- The keep-awake request was denied, so the Mac can sleep between self-paced wakeups and stall this loop. Add a permission rule for `mcp__ccd_host__request_keep_awake`, or run `caffeinate -i` yourself, if you want it held.
