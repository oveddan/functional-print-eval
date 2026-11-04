# Crash replay: what one retry fixes

Issue 27, approved by Dan on 2026-11-04. In the saved runs `submit_design` ended the conversation, so a model never heard that its code crashed. This replays each saved crash once, with its saved build error, and grades what comes back. It gives a number for whether these failures are the model's limit or the eval's.

Code: `pbe/runner/crash_replay.py` (reuses `second_turn` from `pbe/runner/coupon_loop.py`), run by `scripts/crash_replay.py`, tested in `tests/test_crash_replay.py`.

## Trials

All 10 saved trials that failed `builds` from a real crash, listed from `results/runs` (`crash_replay.CRASHED_TRIALS`; a test checks the list against the saved records):

| Run | Task | Model | Trial | Saved error (ending) |
|---|---|---|---|---|
| pilot-nut-knob-2 | nut-knob/M3 | DeepSeek V4 Pro | t1 | `NameError: name 'p' is not defined` |
| pilot-nut-knob-2 | nut-knob/M3 | Qwen 3.8 Flash | t1 | `TypeError: Solid.makeLoft()...` |
| pilot-nut-knob-2 | nut-knob/M5 | DeepSeek V4 Pro | t1 | `NameError` on `math`, test print only |
| pilot-nut-knob | nut-knob/M5 | Qwen 3.8 Flash | t1 | `NameError` on `sqrt` |
| pilot-tripod-given | tripod-plate, `all_given` | Qwen 3.8 Flash | t1 | `TypeError`: float as integer |
| pilot-tripod | tripod-plate | Qwen 3.8 Flash | t2 | `AttributeError`: `getAngle`, `cone` |
| pilot-tripod | tripod-plate | Qwen 3.8 Flash | t3 | `NameError` on `tan` |
| pilot-wheel | bearing-wheel | DeepSeek V4 Pro | t1 | OCC: no suitable edges for chamfer or fillet |
| pilot-wheel | bearing-wheel | DeepSeek V4 Pro | t2 | `NameError: name 'p' is not defined` |
| pilot-wheel | bearing-wheel | Gemini 3.8 Flash | t1 | OCC: `BRep_API: command not done` |

Left out: GPT-6.1 Sol's `all_given` t1, the eleventh `builds` failure. Its code stops itself on purpose (`ValueError: STOP: missing measurements or verification.`), so it isn't a bug.

## Method

- Each saved conversation is continued with one message from the person, then the model gets up to 8 calls to resubmit, as in the test print loop's second turn.
- The message is the saved `builds` error for each part that failed, word for word from the trial's `grades.json`, and the request to fix it. No verdict and no other check's result. Its exact form:

  ```
  I tried to build your design, and it didn't build. Here's the error for each part that failed:
  - <part id>: <saved error>
  ...

  Please fix it and send me the design again with submit_design.
  ```
- **One error message only.** No new build's error goes back to the model: the design that comes back is built and graded, and that's the end. Schema repairs still go back as usual, as in any trial.
- The design is graded with the normal checks, test prints kept in. Each saved trial and its verdict stay as they are.
- Part code runs in the eval's normal build sandbox (bubblewrap on Linux), without `PBE_NO_SANDBOX`.
- Saved under `results/runs/crash-replay/<saved trial's folder>/`: `replay.json`, the retry's `transcript.json` (only the messages it added) and `submission.yaml`, and the parts it built. `summary.csv` has one row per trial.

## Written before the run

Committed with the code, before any model call.

- **Primary measure:** of the 10, how many now pass `builds`. Report it as X of 10, with each trial listed.
- **Secondary:** of those, how many pass every check, how many are not graded, and how many now fail another check. A crash can hide other faults, so a fixed build doesn't mean a good design.
- **What it can't show:** 10 trials, one replay each, three models, no neutral arm, and Qwen alone is 5 of them. It shows that a retry can fix these crashes, not a rate for any model.

How the code sorts each trial (`crash_replay.result_of`), fixed here before the run:
- *passes `builds`*: the retry handed in a design and every one of its parts built, test prints included.
- Of those: *fails another check* if any check fails, even when another is not graded; *not graded* if none fails and at least one is not graded; *passes every check* otherwise.
- A retry with no design (`no_submission`, `token_limit`) does not pass `builds`. Nor does a design with any part that crashes, the same part or another.

## Limits

- Budget: stop at $1.50 of model spend, checked before each trial.
- A stop for lack of credit or a provider error (`outcome: error`) is an infrastructure stop, not a result. The run stops there, and running the script again retries just those trials.
- No existing file under `results/`, and no check, is changed.

## Result

Run 2026-11-04 on Linux in the bubblewrap sandbox, all 10 trials complete, no infrastructure stop. **$0.3309** in all, against the originals' $0.35. Every record is in `results/runs/crash-replay/` (`summary.csv` has one row per trial; each trial's `replay.json`, `transcript.json` and `submission.yaml` beside it).

**Primary: 5 of 10 now pass `builds`.**

| Run | Task | Model | Trial | Saved verdict | After one retry | Cost |
|---|---|---|---|---|---|---|
| pilot-nut-knob-2 | nut-knob/M3 | DeepSeek V4 Pro | t1 | fail builds | still crashes: `ValueError: Cannot find a solid on the stack or in the parent chain` | $0.1472 |
| pilot-nut-knob-2 | nut-knob/M3 | Qwen 3.8 Flash | t1 | fail builds | **builds**; fails R3 (no hex pocket about 5.5 mm across) | $0.0178 |
| pilot-nut-knob-2 | nut-knob/M5 | DeepSeek V4 Pro | t1 | fail builds | **builds**; not graded R4 (pocket 7.85 across flats, 0.15 under the nut: no print) | $0.0091 |
| pilot-nut-knob | nut-knob/M5 | Qwen 3.8 Flash | t1 | fail builds | still crashes: knob, `polarArray()` missing `count`; its test print builds | $0.0145 |
| pilot-tripod-given | tripod-plate, `all_given` | Qwen 3.8 Flash | t1 | fail builds, connected_bodies, bridges | still crashes: cap, `polarArray()` missing arguments; plate still fails connected_bodies and bridges | $0.0187 |
| pilot-tripod | tripod-plate | Qwen 3.8 Flash | t2 | fail builds | **builds**; fails connected_bodies (test print) and bridges | $0.0181 |
| pilot-tripod | tripod-plate | Qwen 3.8 Flash | t3 | fail builds, connected_bodies | still crashes: test print only, `Workplane.center()` arguments; also fails bridges and R2 | $0.0280 |
| pilot-wheel | bearing-wheel | DeepSeek V4 Pro | t1 | fail builds | **builds**; fails bridges, R2 and R4 (7.00 mm bore: the M8 bolt won't pass) | $0.0082 |
| pilot-wheel | bearing-wheel | DeepSeek V4 Pro | t2 | fail builds | still crashes: wheel, OCC `GC_MakeArcOfCircle` no result | $0.0097 |
| pilot-wheel | bearing-wheel | Gemini 3.8 Flash | t1 | fail builds | **builds**; fails bridges only | $0.0596 |

**Secondary: of the 5 that build, none passes every check, 1 is not graded and 4 fail another check.** The four fail `bridges` (3) and the task's own requirements: Qwen's M3 knob has no hex pocket at all, DeepSeek's wheel has no bearing seats and a bore too small for its bolt. Gemini's wheel fails only `bridges`, one unbridgeable overhang on the wheel.

**The 5 that still crash all fixed the error they were told about.** In none of them does a saved error come back. Each hit a different error behind it, in the same part or another one, which one message can't reach. Two of these crash in one part only: Qwen's plate t3 in its test print, with the final parts built, and Qwen's M5 knob in the knob, with its test print built.

**Notes.** All 10 retries handed in a design. Qwen's plate t3 needed one schema repair. DeepSeek's M3 knob cost $0.147, 44% of the total: its first call stopped at the 32,000-token limit with no tool call, and its second call submitted. Each model: Qwen 2 of 5 build, DeepSeek V4 Pro 2 of 4, Gemini 1 of 1.

**What it shows.** One retry fixed half of these crashes, and no retry repeated the error it was shown. But fixing the crash didn't produce a passing design: 4 of the 5 that now build fail another check, and the fifth is not graded. On this sample the crashes weren't hiding passes, they were hiding more faults: with one retry, the pass count on these 10 trials stays at 0. Within the limits above (10 trials, one replay each, Qwen 5 of them), these failures look like the models' limit more than the eval's. A second retry with the new error might build more of them, but this replay can't say whether any would then pass.

**Code version.** The records say commit `d749302`, the code and these measures as pushed before any model call. The branch was then rebased onto #19's new head, which changed no file that decides results (`pbe`, `tasks`, `catalog`, `results/predictions`, `pyproject.toml`, `uv.lock`), and squashed into one commit, so `d749302` isn't in the branch's history.

After Codex's review, `scripts/crash_replay.py` saves a paid retry before grading it, so a rerun grades the saved design without another model call. A retry after an infrastructure error also keeps the earlier attempt's cost. Neither case came up in this run. Regrading each saved retry's design through the new path, in a scratch copy, reproduces all 10 verdicts.
