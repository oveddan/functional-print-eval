# Changelog

Each entry: what changed, why, and the evidence (a run, a failure, a measurement).

## 2026-11-04: In `can_run_code`, `submit_design` builds every part and sends build errors back (issue 26)

Dan, on a test print that crashed on a code bug: "the model should be able to know about the bug and attempt to fix it". In `can_ask` and `all_given`, parts are first built during grading, so a model never hears about a build error: `builds` fails 11 of the saved trials, and the audit on #15 found 9 of those are code errors, such as a `NameError` on `math`. Opt-in with `can_run_code`, and no run uses it yet: no model was called.

- `pbe/runner/build_on_submit.py`: in `can_run_code`, `submit_design` builds every part, final parts and test prints alike, before it accepts a design. If a part doesn't build, the reply names the part and gives its error (the traceback from the part's own code, at most 2,000 characters, with the end kept), the design isn't handed in, and the call counts as a repair, as a schema error does. A design whose parts all build gets "Received." and ends the conversation as before. Nothing from the graders comes back: no check, verdict or measurement.
- The build runs in run_python's sandbox, not `pbe.parts.build`'s, because the error text now reaches the model and its provider, and the macOS build sandbox can read files anywhere. Each part builds alone in a fresh folder holding only its code and the params, as grading builds it, so it can't lean on files the model wrote with `run_python`. The exported mesh is read back inside the sandbox too, so parsing a huge STL stays within its memory cap and the trial's code time and never runs in the runner's own process (Codex's review of PR 21). 120 s per part, as in grading. If the sandbox can't start, the trial ends as an infrastructure error (`outcome: error`) instead of telling the model its part didn't build.
- Building draws on the trial's code time, the 20 minutes `run_python`'s calls share, so a submission with many slow parts, or several submissions in one reply, can't hold a worker longer than that (Codex's review of PR 21). Once it's used up, the parts still to build aren't built. If no part built so far has an error, the design is accepted as in the other conditions, and the record lists the parts left unbuilt in `build_on_submit.accepted_unbuilt`. A part cut short by the code time isn't reported as a build error.
- Grading still builds every part itself with `pbe.parts.build`, so this build can't change a verdict. The two builds can differ only where their limits do: on submit a part has run_python's caps (4 GB memory, 256 MB per file), and grading has neither.
- The record gets `build_on_submit` in `can_run_code` only: `sent_back`, the parts that didn't build for each call sent back, and `out_of_turns_while_fixing`, true when a call was sent back and turns ran out before a design built. The turn limit still applies. Whether a fix followed is `sent_back` with outcome `submitted`. The run's progress line shows both.
- The `can_run_code` system prompt and `submit_design` description say that every part is built first and errors come back to fix.

`can_ask` and `all_given` are byte-identical: a test hashes their tools and system prompt against the values taken before this change, and checks that they accept a design without building it. The saved trials (106 records under `results/runs/`, 11 of them failing `builds`) stay valid as the runs with no build feedback: their `builds` failures happened with no chance to fix them. Every saved `grades.json` loads and saves back to the same fields.

Evidence, from a Linux cloud session, in both sandboxes (bwrap and the container):
- `tests/test_build_on_submit.py`, 50 passed. A part that raises the contents of `tasks/m5-spacer/hidden_facts.yaml`, by absolute or relative path, gets `FileNotFoundError` back and none of the file. A part sees only its own `part.json`, not the model's working folder. A `NameError` comes back with the part's id and the line in its code. A test print is built too. Code with no `build(p)`, code that exits early, a `build` that returns something other than a shape, and a part that runs past its time each come back as an error. A long error is cut. The mesh is read back inside the sandbox: a part whose code breaks `trimesh.load` there gets the mesh error. Building is charged to the trial's code time; a part cut short by it is left unbuilt, not reported; with the time used up nothing runs and the design is accepted, with `accepted_unbuilt` recorded; an error found before the time ran out is still sent back.
- With a fake model: a design that doesn't build is sent back, the fix is accepted and graded as usual, with `repairs` 1 and `sent_back` `[["spacer"]]`. Two failing designs with two turns end as `no_submission` with `out_of_turns_while_fixing`. A sandbox that can't start ends the trial as an error.
- The spacer's reference builds on submit in 1.8 s, the same as grading's build.

Not tested: the macOS container (Docker Desktop), as for `run_python`.

## 2026-11-04: A hub standing in a recess no longer leaks its bore into the recess; one wheel verdict changes

`pbe/graders/sections.py`, `holes()` (its loop is in `holes_in` since the audit fixes below): something solid standing inside a hole was cut out with `hole.difference(other)`, which leaves the solid's own holes behind. A tube standing in a cavity left its bore as a piece of the cavity's "hole", a MultiPolygon. Every caller follows a hole from layer to layer by overlap or reads its shape (`wheel.py`'s seats and coupons, `nuts.py`'s pockets and bolt path, `bolted.py`'s bores, `requirements.py`'s through hole), so each could follow the cavity instead of the bore inside it. Now the solid's whole outline is cut out, `Polygon(other.exterior)`, and the ring is mended with `.buffer(0)`. This is the same fix the Estoa light grader's `_hole_around_axis` got. The number of holes in a section doesn't change, only the shape of the outer one. `tests/test_sections.py` (a box with a cavity and a tube standing in it) failed before and passes now.

Evidence:
- A probe ran both versions of `holes()` side by side on every call while grading all 106 saved trials. Only one trial ever meets the case: Gemini 4 Argon's wheel in `pilot-wheel` t2, 40 calls, all in the top 2 mm along z. There, its own code cuts an "annular relief groove between hub and outer tire rim", leaving the hub that holds the 22 mm bearing seat standing free. The old groove "hole" took in the seat: 902 mm², the seat's 383 plus the groove's 518. The wheel grader followed it as part of the seat, and `_is_round` called that not plain.
- Regrading every run under `results/runs/` changes one verdict. **`pilot-wheel` Gemini 4 Argon t2, R3: not graded ("ribs, lobes or a slot in the seat") → pass ("22.09 mm: it presses in and holds upside down")**. The seat is plain and round: its area matches a 22.09 mm circle in every layer. `all_pass` stays false and its verdict stays not graded, because R4 is still not graded, so the counts stay 27 pass, 50 fail, 22 not graded, 5 declined. The record's `commit` stamp is this branch's pre-squash commit.
- Regraded again after restacking onto the audit fixes, with the same result (the `crash-replay`, `loop-sample` and `loop-sample-2` runs keep no `grades.json`, so `--regrade` has nothing in them to read; they aren't regraded): the one R3 change, and `bridges` detail text rewritten in the same 9 trials the audit fixes left as they were (Linux's CAD kernel vs the Mac's). No `ok` value changed in those, so they aren't committed. The probe's run predates the restack, but it compares `holes()` on the same meshes, and the restack didn't change `holes()` apart from moving its loop.
- `uv run pytest`, after restacking onto the audit fixes at `2278ce7`: 278 passed. `--reference`: every check passes for m5-spacer, tripod-plate, bearing-wheel and nut-knob M3, M5 and M8. phone-stand has no reference.

Scoring walk:
- Real-world relevance: unchanged. A hub boss in a recessed wheel face is a normal design, and a model chose it unprompted.
- Task design: unchanged. The bearing-wheel brief's table already says plain seats are graded, and this seat is plain.
- Grader reliability: a false "not graded" removed. It was found only because the Estoa light grader hit the same pattern. Nothing yet tests a solid with a hole standing inside a hole for `nuts.py` or `bolted.py` on their own, only through `holes()`.
- Evidence of model limitations: unchanged. Argon t2 still can't be fully graded, because no print measured its 8.3 mm bore (R4).
- Reproducibility: the regrade needs no key. `bridges` details still differ in the last digits between Linux and the Mac.
- Human expertise and review: Dan hasn't reviewed this change.
- Insight: none new. The lesson is about the eval: a geometry helper shared by graders can hide a mistake that only one design in 106 trips.

## 2026-11-04: Audit fixes from issue 15; regraded: 27 pass, 50 fail, 22 not graded, 5 declined

The decided calls from the audit of the 104 pilot trials (issue 15), applied as one change and regraded with `--regrade` (no model calls). Who made each call, as recorded on issue 15:
- **Dan:** a test print can't fail a trial on its own (fix 1 below); declining gets its own category, never counted as a pass (fix 2); holed recess roofs keep failing `bridges` (unchanged).
- **Claude**, after Dan handed over the last two calls on 2026-11-04 ("do what you think is best"): M3 at +0.1 counts as unsettled (fix 3), and the test print labelled `final` (DeepSeek V4.1 Flash, M5 t1) stays a fail on R1 (unchanged). These are not Dan's expert judgement.
- **No decision needed:** the pocket-reader bug (fix 4) and the detection rule for declining.

Changes:
1. **Test prints.** `checks.py` marks each generic check (`builds`, `connected_bodies`, `bed_fit`, `bridges`) on a part with `role: coupon` as `test_print`. They stay in `grades.json` and in the new `test_print_failed` column of `summary.csv`, but don't count toward `all_pass`, `failed_checks` or `not_graded`. A generic check that crashes now runs again part by part, so a crash on a test print is marked as one too. No saved trial has a check crash.
2. **Declined** (`pbe/graders/declined.py`), neither a pass nor a fail. Two rules, read from what was handed in and never from the model's prose: no final part (nothing, or only test prints); or a final part that didn't build because a `raise` in its own code fired under an `if` that reads a param handed in with no value. The build keeps only the error's text, so the error must come from exactly one `raise` in the code; then that one fired, and its `if` was true (from Codex's review, which showed a skipped guard sharing its message with an unguarded `raise`). Across all 106 saved trials the first rule catches exactly the 4 `can_ask` trials and the second only GPT-6.1 Sol's `all_given` t1. No ordinary crash matches: the other 10 trials with a failed build (on a final part or a test print) stopped on a NameError, TypeError, AttributeError or CAD kernel error, which no `raise` in their code produced. Limits: a model that labelled its only real part `coupon` would read as declined, and a stop with an f-string message isn't recognized. `TrialRecord` has `declined` (the reason) and a `verdict` property; A declined trial's findings stay in `grades.json`, but none count by check or class: its `failed_checks` and `not_graded` are empty, so a declined trial's R1 "no final part built" isn't tallied as a failure. `summary.csv` gains `verdict` and `declined` columns after the existing ones; `digest.py` and `gallery.py` show it. Older records load unchanged.
3. **M3 +0.1.** `round1-coupons.yaml` codes it `won't go in`, with Dan's note "really struggles to go in". The record is unchanged; `nuts.READ_AS` reads that row as "struggles to go in", which settles nothing either way.
4. **Pocket reader.** `_read_pocket` counted open air outside the part's outline as blocking a nut, so any feature standing higher than a pocket's mouth closed every pocket. Now a layer where the nut's place is outside the outline doesn't block. The same bug was in R5's bolt reader (`_clear_around`): a raised feature made the layers above the knob's top read as solid. Fixed the same way; it flips no saved trial.
5. **`--regrade`** replaces a verdict only when what decides it changes: a finding's check, part, `ok` or detail, which findings count, or `declined`. Otherwise every one of the 56 trials whose test prints all pass would be rewritten just to add the `test_print` mark to passing findings. In those trials the mark is missing, which changes nothing they report.

Evidence: a baseline of `digest --why` and `summary.csv` for every run, taken before any change; `--regrade` of every run at code commit `dfc2860` (the stamp in each regraded `grades.json`; it was squashed into this commit with no code change); `digest --why` and `summary.csv` compared trial by trial. All tests pass (274 after restacking onto #31), and every `--reference` passes. After a code review, the crash and declined changes above went in; a second full regrade with them changed no `grades.json`.

**Counts on the 104 pilot trials: 27 pass, 50 fail, 22 not graded, 5 declined** (from 27 / 58 / 19). Issue 15 expected 27 / 51 / 21 / 5. The difference is one trial no fix's estimate covered:

| Trial | Was | Now | Why |
|---|---|---|---|
| nut-knob M5, DeepSeek V4 Pro, t1 | fail | not graded | fix 1: its only failure was `builds` on its test print |
| tripod `can_ask`, GPT-6.1 Sol, t1, t2, t3 | fail | declined | fix 2: test prints only (t1's `bridges` failure is on its test print) |
| tripod `can_ask`, GPT-6 Luna, t2 | fail | declined | fix 2: no parts |
| tripod `all_given`, GPT-6.1 Sol, t1 | fail | declined | fix 2: `temporary_plate` stops until `socket_usable_depth` has a value |
| nut-knob M3, Gemini 4 Argon, t1 | fail | not graded | fix 3: +0.05 lies between "won't go in" and the unsettled +0.1 |
| **nut-knob M3, DeepSeek V4.1 Flash, t1** | fail | not graded | **not expected: fixes 3 and 4 together.** Its test print's 1.5 mm marker nub made all 4 pockets read closed (the audit's example of the bug), so no test print counted. Read correctly, they open to the top, and one is 5.60 (+0.1), now unsettled. So R4's rule applies: a test print that could find a size that holds, with the knob's pocket following a param, is not graded. The audit's "no flips" for fix 4 assumed the old +0.1 coding, and each fix's count was worked out on its own. Its knob (5.42, −0.08) still reads "won't go in" |

Other regraded trials, verdict unchanged:
- The test print's failure no longer counts in `failed_checks` in 11 trials, each still failing on its final part: Qwen 3.8 Flash M5 t1, M3 t1, tripod t1, t2, t3, `all_given` t1; GLM 5.3 Flash tripod t1, t3, wheel t1; Gemini 4 Argon tripod t2; Gemini 3.8 Flash tripod `all_given` t1.
- Haiku 5.5 M3 t1: R4 at +0.10 goes from fail to not graded; it still fails R3 (a closed pocket).
- Opus 5.5 and GPT-6.1 Sol M3 t1: observations only. A test-print pocket at +0.1 now "struggles to go in"; Sol's two test-print pockets are also listed in the other order.

Linux detail text: regrading on Linux rewrites `bridges` detail in some trials (issue 15 documents this). A baseline regrade of the untouched code changed detail text in 14 trials, with no verdict change. 9 of those have nothing else changed, so their files are left as they were. 5 are regraded anyway for the reasons above, and keep the Linux text. In each, only the best strand angle changes, to its mirror image, except Qwen's overhang count: Gemini 3.8 Flash `all_given` t1 test print 150° → 30°; Qwen 3.8 Flash `all_given` t1 plate 13 → 9 unbridgeable overhangs; Gemini 4 Argon tripod t2 plate 150° → 30°; GPT-6.1 Sol tripod t1 test print 115° → 65°; GLM 5.3 Flash wheel t1, wheel and test print 160° → 20°.
Scoring criteria (`docs/scoring.md` and the guide's 100-point rubric), one line each:
- **Real-world relevance:** unchanged by this. Declining now shows as its own result, which is the behaviour a careful designer should have when a size is missing. Weak: all 5 declines trace to the tripod task having no clamp width on record.
- **Task design:** weak, as before. The tripod's lookup answers every size question with the clamp's style, so the declines say as much about the task as about the models.
- **Grader reliability:** two reader bugs fixed (pocket and bolt), each with a test. A test print can no longer fail a trial, even through a crash. Each rule has a right and a wrong case in `tests/test_verdicts.py`. Weak: the declined rule is a code pattern with known misses (an `else:` branch, an f-string), and M3 R4 still rests on one print per size.
- **Evidence of model limitations:** the 5 declines are backed by the transcripts quoted on issue 15. Weak: one to three trials per model.
- **Reproducibility:** the regrade needs no model calls, and every changed verdict is listed above. Weak: `bridges` detail text still depends on the platform, and 5 kept files carry Linux text.
- **Human expertise and review:** calls 1 and 2 are Dan's; the M3 reading and the R1 label are Claude's, delegated, and are labelled so here and on issue 15. The extra DeepSeek flip was accepted on the PR. The rest is reviewed by Claude, with a Codex review requested; nobody else has read it independently.
- **Insight:** fixes that each flip nothing on their own can flip a trial together. So counts were checked trial by trial against a baseline, not taken from each fix's estimate.

## 2026-11-04: Crash replay (issue 27): one retry builds 5 of 10 saved crashes, and none of them passes

Run `crash-replay`: the 10 saved trials that failed `builds` from a real crash, each continued once with its saved build error and nothing else, then graded with the normal checks, test prints in. Code in `pbe/runner/crash_replay.py` and `scripts/crash_replay.py` (reusing `coupon_loop.second_turn`), tests in `tests/test_crash_replay.py`. The measures in `docs/crash-replay.md` were committed and pushed before any model call (`d749302`). $0.3309, no infrastructure stop.
- **5 of 10 now pass `builds`**: Qwen 3.8 Flash's M3 knob and plate t2, DeepSeek V4 Pro's M5 knob and wheel t1, Gemini 3.8 Flash's wheel.
- Of those 5, **none passes every check**: 4 fail another check (`bridges` in 3, R2, R3 or R4 in 2) and DeepSeek's M5 knob is not graded on R4.
- The other 5 all got past the error they were shown, and none repeated it, but each crashed on a different error behind it.
- So on these trials one build error sent back fixed half the crashes but none of the pass count. No existing result changes: the saved trials and their verdicts stay as they are.
- After Codex's review, the script saves a paid retry before grading it and keeps an earlier attempt's cost on a retry, as `scripts/coupon_loop.py` does. Neither case came up in the run, and regrading through the new path reproduces all 10 verdicts.

## 2026-11-04: Coupon loop script hardened after Codex review

No result changes. From Codex's review of PR #19, each finding checked against the code first:
- `scripts/coupon_loop.py` saves a paid second turn before grading it, and a rerun finishes the grading without a new model call. A retry after an infrastructure error keeps what the failed attempt cost: all 10 retried arms in `loop-sample-2` had cost $0, so the recorded spend was already right. A selected trial with no submission is skipped. The script's own uncommitted changes now mark a record's code version dirty. Tests in `tests/test_loop.py`.
- `docs/coupon-loop.md` says roofs are reported only when the bridge check predicts a tangle, which is how both samples ran. It also gives the evidence that each sample's rule was committed before its run (7b30192, a46c56f), since the squash merge keeps only the final commit.
- Three findings were already fixed by the restack onto the refactor: the sandbox opt-out in the usage line, `null` tool arguments, and retrying errored arms.

## 2026-11-04: Coupon loop, second sample complete

Run `loop-sample-2` finished after credit was added: the 10 arms stopped by HTTP 402 were re-run, nothing else. $1.03 in all.
- Passes: 1 of 12 in every arm, the same trial as before. No improvement on the pre-registered measure, as in the first sample.
- Checks fixed: 3 after the report (DeepSeek's two wheel seats, GLM's wheel roof), 0 after a second look, which made two designs worse.
- Both fixes held: 8 second turns had a call stop at the token limit and all still handed in a design; the "tighter than a record" answers are what DeepSeek's wheel t1 acted on.
- Write-up in `docs/coupon-loop.md`.

## 2026-11-04: Coupon loop: two fixes before a second sample

`pbe/runner/coupon_loop.py`, from the first sample's findings, approved by Dan:
- A coupon pocket or seat tighter than the tightest printed size, which wouldn't take the nut or bearing, is now reported as "won't go in", as the checks already read it. In the first sample these got "I can't tell you" in 4 trials.
- The second turn gets up to 8 calls, as a first turn does, instead of 3. A second turn with no design whose every call stopped at the 32,000-token limit is now `token_limit`, reported apart from pass and fail. In the first sample GLM's wheel t1 lost its most informative report that way.

Tests in `tests/test_loop.py`. The second sample's measures are in `docs/coupon-loop.md`, committed before it ran.

Run `loop-sample-2` stopped when the OpenRouter account ran out of credit: 7 of 12 trials complete, 10 arms ended in HTTP 402. `scripts/coupon_loop.py` now re-runs arms that ended in an infrastructure error, as `pbe/eval.py` does. Status in `docs/coupon-loop.md`.

## 2026-11-03: Coupon loop sample: no improvement on the pre-registered measure

Run `loop-sample`: 12 saved knob and wheel trials from Sonnet 5.5, DeepSeek V4.1 Flash and GLM 5.3 Flash, each replayed with the person's report on its test coupons and with a neutral "take another look". $0.98. Measures were committed before the run (`docs/coupon-loop.md`).
- Passes: 1 of 12 in every arm (baseline, feedback, neutral), the same trial. Nothing broke.
- One check fixed by the report: DeepSeek V4.1 Flash's wheel t2 moved its seat from 21.89 to 22.18 mm after being told the 22.19 seat held, and passed R3. It still fails `bridges`. The neutral arm left it at 21.89.
- In 5 of 12 trials every line of the report was "I can't tell you"; in 2 more the only answer was about a seat that already passed. One feedback replay (GLM wheel t1) produced no design: all three calls hit the 32,000-token limit.
- A flaw in the report's rules: sizes tighter than a recorded "won't go in" got no answer, though the checks count them as won't go in.
- The replays ran on commit 7b30192 before the restack. Their records were converted to `loop.json`, and the restacked code reproduces every report and verdict.

## 2026-11-03: Audit of the saved failures (issue 15); no result changes

Every saved trial was rebuilt and regraded on Linux in a scratch copy, with no change to `results/`, `pbe/` or `tasks/` (the audit itself is the comment on issue 15). Evidence:
- All 106 verdicts reproduce on Linux as recorded on macOS. That answers the open question from the cloud sessions: verdicts match, though detail text doesn't always (13 tied strand angles come out mirrored, one exception has another class name, and Qwen 3.8 Flash's all-given plate counts 9 bad overhangs instead of 13).
- None of the 24 suspected false failures, or the other trials examined alongside them, came from a check misreading the geometry.
- The 17 trials that fail only `bridges` all have a roof with the bolt's hole cut through it, the shape that tangled on the Arca plate and coupon A's H cell. Dan decided they fail. Pass count unchanged at 27 of 104.
- Five trials declined to design a plate because the clamp's width isn't recorded; one of them (GPT-6.1 Sol, all given) is reported as a `builds` crash. Whether declining fails, whether a coupon can fail a trial, a coupon marked `final`, and how M3 +0.1 is coded are still Dan's to decide (issue 15).
- One reader bug found, not yet fixed, which flips no verdict: in `pbe/graders/nuts.py`, a raised feature above a pocket's mouth makes every pocket read as closed.

Docs: `docs/limitations.md` now opens with the eval's shortcomings by rubric criterion, the assumptions current verdicts rest on, and what prints would settle each. `docs/coupon-loop.md` holds the decided design for letting a model learn from its test coupon. `PLAN.md` records both decisions.

## 2026-11-03: Estoa light task started: its datasheet, and one seed corrected

`tasks/estoa-light/files/datasheet.png`: the LED disk's one-page datasheet (Adafruit 2477, Soya LED SY-C255-102), rendered at 150 dpi from the PDF Dan attached, saved with no metadata. It gives no dimensions: no mounting holes and no diameter. Dan: the datasheet was used to understand what the disk was, and for the LED positions. Dan measured the board's two 3.3 mm holes with calipers in Estoa session 602ba611 (2026-09-28). The task itself isn't written yet. Committing an image is an exception to the publishing rule, which Dan allowed for vendor drawings (`PLAN.md`).

`seeds/estoa-failures.yaml`, `usb-opening-sized-to-receptacle`: the entry read as if the agent narrowed the opening on its own. Dan asked for it "more to the right, and narrower" (c8cfd18c, 2026-10-04T18:33:02); the agent chose 11.5 mm (18:36:05). The entry still counts against the agent, since the size was its design, but now says who asked. Found by the session that read the Estoa transcripts for this task (issue 17).

## 2026-11-03: A third condition, `can_run_code`: models can run Python before handing in (issue 17)

Opt-in, and no run uses it yet: no model was called. The 106 saved trials stay the "no code" baseline. `can_ask` and `all_given` send the same prompt and tools as before: a test checks the prompt against pilot-wheel's saved transcript, and the tool list for both conditions, byte for byte, before and after the change.

- `pbe/runner/python_tool.py`: `run_python(code)` returns the exit code, stdout, stderr and the names of files the code wrote, with output capped at 8,000 characters per call (head and tail kept) and 120 s per call. All calls in a trial share 20 minutes of code time, because one reply can hold several calls and the turn limit counts replies (Codex's review of PR 21); a call never gets more than what's left, and once it's used up, run_python says so and runs nothing. Recorded in `settings.run_python.trial_s`. The working folder is capped at 1 GB and 10,000 files in all, checked while the code runs, because a per-file limit doesn't stop many files filling the disk (Codex's review of PR 21). `/tmp` is capped at 512 MB in both sandboxes. A crash or timeout comes back as text and the trial goes on. Files persist in the trial's `workspace/` between calls (not committed). A task can hand the code files through `tasks/<family>/files/`. No task has any yet.
- `pbe/runner/code_sandbox.py`: the code sees only its own folder and the installed libraries. There are two sandboxes, and if neither works it refuses to run. `PBE_NO_SANDBOX` doesn't apply, because even a throwaway container holds this repository's hidden facts.
  - `container`: `docker/run-python.Dockerfile`, built by `scripts/build_run_python_image.sh`, with `--network none`, a read-only root, no capabilities and `env -i`. The image holds uv.lock's libraries and none of this repository, and the runner refuses an image built from a different uv.lock. Each run's container is created before it starts, and removed with `docker rm --force` when stopped: killing a `docker run` while the daemon was still creating its container left it running with nobody attached, which parallel tests caught.
  - `bwrap`: Linux only. A new mount namespace holding only `/usr`, the Python install, site-packages and a few `/etc` files, with no network and running as nobody.
  - Resources are capped by the kernel in both, after Codex's review of PR 21 found four ways to exhaust the host under bwrap: a fork through ctypes (past the audit hook), a loop of threads, folders or links the folder cap didn't count, and memory multiplied across forked processes. The container has cgroups (`--pids-limit 256`, `--memory 4g`). bwrap has none, so it gets the same totals another way: a seccomp filter (`pbe/runner/no_new_processes.py`) lets the code start threads but no other process, so its one process's `RLIMIT_AS` (4 GB) caps memory in all; and `pbe/runner/task_limit.py` caps its threads at 256, with a pids cgroup when running as root (the kernel doesn't apply `RLIMIT_NPROC` to root) and `RLIMIT_NPROC` otherwise. Where either can't be set up, bwrap refuses. Every folder entry counts against the folder's cap, and a folder the count can't read (code could chmod one to hide what's in it) stops the run. Each entry counts as its size or the disk blocks it holds, whichever is more, because `fallocate` with `FALLOC_FL_KEEP_SIZE` holds blocks while the size stays 0 (Codex's review of PR 21); without that, preallocated files reached 7.5 GB before the file-count cap stopped them. Thread pools are pinned to 4 threads (`OMP_NUM_THREADS` and others). The audit hook stays, for a readable error.
- `agent.DEFAULT_MAX_TURNS`: 20 for `can_run_code`, 8 as before for the others. `--max-turns` still overrides it. The record saves `settings.max_turns`, and for `can_run_code` also `settings.run_python` (which sandbox and image, the timeout and the output cap). Records without it save exactly as before.
- `opencv-python-headless` added to the dependencies.

Evidence, from a Linux cloud session:
- `tests/test_run_python.py` passes in both sandboxes. The code can't read `tasks/m5-spacer/hidden_facts.yaml`, the reference, `pbe/`, `results/`, the folder beside its own or any file in the home folder. It also can't import `pbe`, resolve or reach the network, see this process's environment (a planted `OPENROUTER_API_KEY`), write outside its folder, start a process past the audit hook, or write a file over the limit. A fork bomb through ctypes starts nothing under bwrap and stops at the cap in the container. A thread bomb stops at the task cap (as root here, so through the pids cgroup; `RLIMIT_NPROC` is only unit-tested here, and CI, which isn't root, runs it for real). A 2 GB allocation fails under a 1 GB cap. Threads still work. Timeouts, output caps and the folder's size and entry caps (files, folders, links) hold. OpenCV, CadQuery and trimesh run.
- A fake-model trial runs code, gets a crash back, then submits and is graded as usual.
- On top of main (the issue 11 refactor, #18, and CI, #20), the full suite passes with parts built under bubblewrap and no `PBE_NO_SANDBOX`: 319 passed, none skipped. Every `--reference` passes. `can_ask` and `all_given` send byte-identical prompts and tools to that branch, for four tasks.
- CI (#20) gets a step that fails unless run_python's sandbox works, so the isolation tests can't quietly skip. Not run yet: it runs on a pull request.

What wasn't tested:
- The Dockerfile's `apt-get` line, because Debian's servers are blocked from the cloud session. The container was tested with those libraries copied from the host instead.
- Docker Desktop on macOS, and building the image on arm64. uv.lock has arm64 Linux wheels for CadQuery's OCP, VTK, OpenCV and manifold3d.

## 2026-11-03: Second cloud session; the smoke test passes with no hand fixes

A fresh session in the updated environment. `bwrap`, `openscad` and `xvfb-run` were already installed and the `SessionStart` hook had synced `.venv`, so nothing was installed by hand.
- `build.sandbox()` is `bwrap`.
- `uv run pytest`: 236 passed, none skipped, in 4 min 23 s on 4 cores.
- `--reference`: every check passes for bearing-wheel, m5-spacer, tripod-plate and nut-knob M3, M5 and M8, as in the first session. phone-stand has no reference.
- Run `cloud-smoke-2`: Haiku 5.5 on m5-spacer, one trial, all checks pass, $0.0014, `platform` Linux-x86_64. The proxy-injected key worked.

Still unchecked: maximum session length, and whether Linux and Mac measure the references to the same digits.

## 2026-11-03: First cloud session; the smoke test passes once bubblewrap is installed

The smoke test from `docs/overnight-runs.md`, run in a Claude cloud session (Linux x86_64, Python 3.12.13):
- CadQuery imports. **`bwrap` was missing**: the environment's setup script installed `openscad` and `xvfb` but not `bubblewrap`, so `build.sandbox()` returned `None` and model code would have refused to run. After `apt-get install -y bubblewrap` in the session, the VM allows its namespaces and `build.sandbox()` is `bwrap`. The environment's setup script needs `bubblewrap` added, or every new session has to install it first.
- `uv run pytest`: 236 passed, none skipped, in 6 minutes.
- `--reference`: every check passes for bearing-wheel, m5-spacer, tripod-plate and nut-knob M3, M5 and M8. phone-stand has no reference. Whether the measured numbers match the Mac to the last digit isn't checked: no Mac reference output is saved to compare against.
- Run `cloud-smoke`: Haiku 5.5 on m5-spacer, one trial, all checks pass, $0.0014. The proxy replaced the placeholder key; no key appears in the saved files.

## 2026-11-03: Runs can move to Linux; records say which platform

`pbe/build.py`: model code now runs under bubblewrap on Linux, with no network and writes only to its own two folders, as under `sandbox-exec` on macOS. If bubblewrap is missing or the VM refuses it, code doesn't run unless `PBE_NO_SANDBOX=1`. The runner also refuses child processes and network connections itself, so a part can't pass on one platform for doing what the other blocks. On Linux that hook is the only thing refusing child processes, and ctypes could get round it. A part that tries these now fails with "is not permitted here" instead of the OS's wording; it failed before too.

`pbe/eval.py`: `grades.json` now records `platform`, because geometry comes from each platform's own CAD kernel wheel. Records from before this have none.

Added `.claude/settings.json` and `scripts/cloud_session_start.sh` to install dependencies in cloud sessions. `CLAUDE.md` now carries the rules a cloud session wouldn't otherwise get. `docs/overnight-runs.md` has the checked setup and a smoke test.

Evidence: the test suite passes on macOS. **Nothing has run on Linux yet**: the bubblewrap command is only checked as a command line, and the smoke test decides whether references grade the same there.

## 2026-11-03: Second wheel round; two more verdicts the records didn't back

`pilot-wheel` now has t2 for 11 models: 22 trials, $2.07 in all. 3 pass, 13 fail, 6 not graded. Without `bridges`, 9 pass, 7 fail, 6 not graded. Seats and coupons of both rounds measured from the saved meshes. Spend stops here: $8.74 used of the $9.00 limit.

`pbe/wheel.py`, both the eval's fault:
- Depth is read in whole layers, so Opus's 6.5 mm seat read 6.4 and just missed the 0.5 mm allowance. The allowance now takes a layer's rounding into account. 0.5 mm is itself my choice, not a record.
- "Nothing stops the bearings" failed Qwen's and GLM's through bores. Round 2's seats had floors, so no print speaks to a through bore. Now not graded. The brief's table has the row.

## 2026-11-03: Bearing wheel pilot; a bearing a little proud isn't a failure

Run `pilot-wheel`, 11 models, one trial each, $0.93, wording unreviewed. Pass: Opus, Sol. Not graded: Argon (22.05 mm seat, 8.2 mm hole). 8 fail. Every seat and coupon measured from the saved meshes.

`pbe/wheel.py`: GPT-6 Luna's R2 failed for 6.8 mm seats, which leave the bearing 0.2 mm proud. No record says that's wrong, so up to 0.5 mm short is now not graded: the eval's fault. On regrade Luna fails only `bridges`, with R2 not graded and R3 passing.

## 2026-11-03: Tripod with the facts given; a bearing wheel task, wording unreviewed

Run `pilot-tripod-given`, `all_given`, one trial each, $1.11 in all. The $1.10 cap stopped it before DeepSeek Pro. Pass: Argon. Not graded: Sonnet. 8 fail, 6 of them on `bridges`. Every failure read: none is the check's fault. Gemini 3.8 Flash's and GLM's "no hole" are real (its extrude moved the plate 40 mm away from the cuts; GLM's pocket stops short of the far face). The facts given hold the bolt's and socket's numbers only, since nobody recorded the clamp's size.

`tasks/bearing-wheel/`, `pbe/wheel.py`: a printed wheel for two 608 bearings on an M8 bolt, graded against round 2's seats. 22.0 won't go in, 22.1 to 22.3 hold, above 22.3 and between 22.0 and 22.1 aren't graded. **The request is mine and Dan hasn't seen it**, so the runs are exploratory. Checks work on a seat each side, a stack from one side, two halves, hub bosses, and a coupon of through or blind seats. A review by Sonnet found 6 things: fixed trimmed hub bosses, a skipped printed sleeve, and blind coupons; the other 3 are written down as known limits in the brief.

`pbe/catalog.py`: `resolve` now reads "608ZZ" and "608". A submission naming the bearing would otherwise have been rejected. The prompt isn't changed.

`tasks/nut-knob/brief.md`: removed "until Dan does", a leftover physical ask. No verdict changes.

## 2026-11-03: Tripod repeats on 11 models; the review's fixes to the tripod checks

`pilot-tripod` now has t2 and t3 for every model but Grok: 34 trials, $3.18 in all. 6 pass, 27 fail, 1 not graded. Without `bridges`, 12 pass, 18 fail, 4 not graded. I read every failure and measured the doubtful ones: none is the check's fault, including Gemini 3.8 Flash t2's 12 mm recess (its code asks for 17, but swapped `slot2D`'s arguments).

Fixes from the code review, in `pbe/bolted.py`, each with a test:
- A recess is the width held over its depth, up to a tapered or stepped roof, and it's the widest real seat of the two ends, not the deepest.
- R5 reads the bolt's path through the plate's main thickness, so a lip or pad elsewhere doesn't count; pads, lips and marks are trimmed from the end layers.
- The plate's main hole is the closed hole the bolt fits, else the open gap it fits.
- A bevel on one edge fails R2 (both edges must narrow). A plate may be shorter than it is wide. R2's message uses the width range, not 38.
- A final part that didn't build isn't replaced by another: `exists` says not graded, because `builds` has already failed.
- With no plate, R3 to R5 say so rather than blaming a screw.
- R3's and R4's limits allow for reading depth in whole layers; R4 and R5 now get `bolt_across: 6.35`.

Verdicts that changed on regrade: Haiku t3 no longer fails R5; Qwen t2 no longer fails R1 and Qwen t3 no longer fails R3 on top of `builds` (one mistake counts once); GLM t2 goes from failed (R2, R4) to not graded. No pass changed.

Known limits: a raised pad around the hole on the camera side overstates reach. A side notch can read as a bore if no closed hole fits. A large counterbored lightening hole could be picked over the bolt's. A sealed recess the head can't reach (Haiku t3) reads as a recess, though `bridges` fails it.

## Tripod plate on all 12 models; the bolt check follows a recess open at the side
- Run `pilot-tripod`, one trial each, `can_ask`, $1.41 in all: pass Gemini 3.8 Flash, Gemini 4 Argon, Grok 4.7; 9 fail, 8 of them on `bridges`. All 12 read by hand or through the digest, and each failure below checked against the part's code.
- `pbe/bolted.py`: if no closed hole runs through a plate, the bolt check now follows gaps in the outline. GPT-6 Luna's plate has a 6.8 mm hole with a channel so the head slides in from the end, and it read "no hole runs through the plate". The eval's fault. Regraded: Luna's R3, R4, R5 now pass, and it still fails `bridges`. Every other trial keeps its verdict. Test in `tests/test_tripod_plate.py`.
- Message only, no verdict changes: the which-face failure now says "the head is on the camera's side, or the dovetail is upside down". Opus's and Sonnet's heads are on the clamp side, as they should be; their dovetails are upside down compared with `arca_plate.scad`.
- Checked and left alone: Qwen's "no hole" is correct (its cuts went away from the part, so the plate is solid). DeepSeek Pro's "straight sides" is correct (its bevel cuts missed the plate). Sol shipped only a coupon, so R1 fails. Haiku and Gemini 3.8 Flash's t1 ran before the person knew the camera's socket thread.

## Tripod plate task, from Dan's real first prompt; a coupon can be several pieces
- `tasks/tripod-plate/`, `pbe/bolted.py`: Dan's first message from session c941d075, approved by him for model runs on 2026-11-02. The request states the problem and leaves the mechanism open. Checks grade the plate's clamp fit, bolt hole, head recess and bolt reach. Every limit comes from the plate he printed (`arca_plate.scad`, seed `arca-counterbore-guessed`): a 13 mm recess fails, 15 passes, in between is not graded. Plate width (37 to 39 mm around the printed 38) is a labelled estimate. The bolt's 10 mm length is a labelled assumption, because no record gives it. A printed screw isn't graded on the bolt checks. See the brief's table.
- `catalog/hardware.yaml`: the webcam bolt's description no longer says "(the Arca plate, Oct 12)". It told every model the answer to the tripod task, and it's in the prompt every task gets. Nothing else in the prompt changed.
- `connected_bodies`: a test coupon may be separate pieces, as long as each rests on the bed. Opus's M3 t2 was failed for a coupon of three separate pockets, which prints fine: the eval's fault. Test in `tests/test_runner.py`; `pilot-nut-knob` and `pilot-nut-knob-2` regraded.
- `scripts/digest.py` (one screen per run, with each failure's reason) and `scripts/gallery.py` (a page of renders beside verdicts). Neither calls a model or affects a grade.
- Constraint recorded in `PLAN.md`: nothing physical before publishing. Not graded is final for this release and is reported as a limitation of the eval.

## Nut-knob task family (M3, M5, M8): tests, checks hardened over four review rounds
- Runs `pilot-nut-knob` and `pilot-nut-knob-2`: M5 on 12 models and M3 on 11, one trial each, $1.64. Passes: M5 Opus, Sonnet, Gemini 3.8 Flash; M3 Opus and GPT-6.1 Sol, both through a coupon. The M3 failures haven't been read yet, so those verdicts are unverified.
- `tasks/nut-knob/`, `pbe/nuts.py`: a hand knob with a hex nut pressed in, graded against what held on coupon B. No clearance suits all three nuts, and the right one can't be looked up, so a design passes on landing where the prints say it holds, or on a test coupon that would have found a size that holds, with a pocket that follows a param. `tests/test_nut_knob.py`: all three references pass, 24 wrong designs fail only their check (or report not graded where no print can say), and 15 correct designs unlike the reference pass (coupons, bed-opening pockets, chamfers, relief, cone roof, drill-out). Two sentences added to the request so everything graded is stated: "It's one printed piece" and "can't be pushed out through the far side".
- **"Not graded" (`ok = None`, never a pass) now has three more uses, and `summary.csv` has a `not_graded` column.**
  - Coupon B's "loose" rows were never turned upside down, and the request asks whether the nut stays in upside down. So M5 +0.2, M8 +0.1 and +0.2 are not graded, and for this release that's a limitation of the eval. +0.3 fails because nuts fell out there on the tripod build (`FELL_OUT`, a different filament, so evidence rather than proof).
  - A plain nut pocket opening at the bed: its roof is a ring 1.7 to 2.9 mm wide around the bolt hole. It fails the strand test, but the narrowest roof seen to tangle is the Arca plate's at 3.1 mm (`narrowest_tangled_mm`, rounded down to 3.0; coupon A's H reached 7.8), and the 1.5 mm overhang allowance is unmeasured. So `bridges` reports not measured. A one-sided shelf that narrow does too: no print measured that either, and coupon C's 10.7 mm cantilever still fails.
  - A check that needs a part or pocket that isn't there reports not graded, so one mistake counts once in failures by class. On the spacer, two parts now reads R1 failed and the rest not graded, where it was four failures. `all_pass` is unchanged.
- **Grader fixes from code review, each with a test.** False passes: a filleted square and a pentagon read as hexagons, because the shape test was area only (it now asks whether a nut's corners fit, using ISO 4032's minimum across-corners, about 95% of a sharp hexagon); a round collar a nut can't pass counted as the pocket's mouth; a hex lightening cell was taken for the pocket; a sleeve inside a pocket vanished, because `holes()` ignored solids standing in a hole; a hex right through the knob passed; a coupon a nut can't get into or can barely enter rescued a design; any mention of "drill" or "clear" counted as an instruction to open a closed layer (it now needs a verb and a hole or layer in one sentence, with no negation just before, and quotes the sentence, since it's a text match). False fails: a 45 degree cone roof and a round relief under the pocket were read as "not a hexagon"; a deeper round hole elsewhere failed R3; a 1 mm chamfered mouth was subtracted from the depth; a knob on its side failed where the check can't read it (now not graded); a coupon sized between measured steps counted as a failure (now not graded). `connected_bodies` counted a sealed void as a second body.
- Spacer R3's upper limit now applies over a quarter of the hole's length, not at its single tightest slice: an 8 mm bore with one 0.4 mm neck passed. A 60% counterbore still passes. Regraded `pilot-spacer`: all 12 still pass every check; only the detail text changed.
- **The runner.** Part code written by models inherited the environment holding the API key. It now gets none, and on macOS it runs under `sandbox-exec` (no network, no child processes, writes only to its own folders; it can still read files). Without a sandbox it refuses to run unless `PBE_NO_SANDBOX=1`. A part id can no longer be a path (`../../x` wrote outside the run); the schema's `id` description says so, which is a change to what models see. Also: a dropped connection, a cut-off body, tool arguments that aren't a JSON object, undecodable output, or a crash in a check no longer stops a run; a trial stopped while grading finishes on resume without paying again; a rerun counts the failed attempt's cost; `-dirty` now means the code or the coupon table changed, not the run's own output. `--regrade` accepts a family name.
- Tests go through `agent.grade`, the real pipeline, and run in parallel (`pytest-xdist`, `-n auto`): 4 minutes down to about 35 s.
- **The fit table now speaks only for plain hex pockets.** Coupon B measured plain pockets, and models use crush ribs, clips, snap rings and lips too (run `pilot-nut-knob-2`). On M3 the table read those as "won't go in", with nothing to back that up. A pocket that isn't plain is now not graded, and so is a coupon pocket that isn't. Corner relief counts as not plain: it's the same test, and no print measured it. Also found in that run: GPT-6 Luna's slits ran out through the wall, leaving no closed hole at that height, and it read "no hex pocket" (now not graded).
- **The hexagon test aimed the nut at a slot.** Found reading run `pilot-nut-knob`: GPT-6.1 Sol's spring fingers read "no hex pocket" and Grok 4.7's spring clips read "+0.50, falls out". Both have a real hex socket, with slots behind the fingers or clips. The test pointed the nut's corner at the hole's farthest point, which was a slot's end, so the nut didn't fit, and the clip layers were skipped. It now tries every 5 degrees, centred where the widest circle fits. Both were the eval's fault; both now read as not measured, because no print has measured a clip.
- **A coupon left without a role counted as a printed part.** Found in the same run: DeepSeek V4.1 Flash left `role` out, it defaulted to `final`, and its design read as two printed parts, which failed R1 and left the rest not graded. `role` is now required, so a schema error goes back for repair. A change to what models see. That trial can't be regraded, because the saved `role` is wrong, so it's rerun in `pilot-nut-knob-2`.
- **A count reached part code as a float.** Found reading run `pilot-nut-knob`: GPT-6 Luna set `lobe_count` to 8 and wrote `range(p.lobe_count)`, the schema's `value: float` turned it into 8.0, and the build failed with a `TypeError`. The eval's fault. `value` now keeps an int as an int, which changes the tool schema models see (integer or number, not only number), and a whole-numbered `count` param is an int however it was saved.

## Spacer on 12 models: all pass; every repair was a format problem
- Run `pilot-spacer`, one trial each, `can_ask`, $0.26 in all: Claude Haiku 5.5, Sonnet 5.5 and Opus 5.5; GPT-6 Luna and GPT-6.1 Sol; Gemini 3.8 Flash and 4 Argon; Grok 4.7; DeepSeek V4.1 Flash and V4 Pro; Qwen 3.8 Flash; GLM-5.3 Flash. All 12 pass every check after the R3 fix below (Opus, Qwen and GLM failed the first version, all for chamfered hole ends). Cost per trial ranged from $0.0017 (GPT-6 Luna) to $0.059 (Grok 4.7). All six providers' tool calls worked through OpenRouter.
- Repairs (schema errors sent back): GPT-6 Luna, GPT-6.1 Sol and Grok 4.7 two each, all from the param field `kind`, which had no description (they left it out, then filled it with a `source` value). `kind` and `source` are now described in the schema. GLM's one repair was a hardware reference to "the user's own M5 bolt": the catalog can't name hardware the person already has, which the real tasks will need.
- Prompt change after this run: the setup now states "Nozzle: 0.4 mm" and "Filament: PLA (high-speed PLA, black)", from Bambu Studio's saved settings (machine preset "Bambu Lab X1 Carbon 0.4 nozzle", filament "Generic PLA High Speed @BBL X1C"), which Dan confirmed were the coupon settings. Runs before this point didn't have the nozzle line.
- Every trial now records observations, never scored: the hole's tightest width, how much each end flares, and which printing know-how its text mentions (`pbe/agent.py` `observe`). Three of twelve chamfered the hole's ends (Opus, Qwen, GLM), DeepSeek V4.1 Flash told the person to trim elephant's foot instead, Sonnet mentioned hole shrinkage but drew 5.5. `pbe/render.py` renders each part headlessly with OpenSCAD for reports.
- Three models used `measure` though nothing was withheld: Sonnet asked for the plates' thickness, DeepSeek V4.1 Flash and Qwen for the bolt's shank diameter. All got "I can't measure that" and went on.

## R3 false fail found in transcripts: lead-in chamfers
- In run `pilot-spacer`, `qwen/qwen3.8-flash`, `z-ai/glm-5.3-flash` and `anthropic/claude-opus-5.5` drew correct holes (5.5, 5.5 and 5.6 mm) with chamfers at the mouths (0.6, 0.5 and 0.4 mm; Qwen's note: a lead-in that "also keeps the first layer from bulging into the hole"). R3 failed all three, at 6.50, 6.30 and 6.20 mm "at its widest". Chamfering a hole's ends is good printing practice, so these were the grader's errors, not the models'.
- Fix: the bolt must still pass every 0.2 mm slice (clear width at least d_min), but the upper limit now applies where the hole is tightest, since that's where the fit is set. Chamfers and counterbores at the ends pass; an oversized or slotted bore still fails. New tests: Qwen's chamfered spacer passes, a 5.5 x 8 mm slot fails (29 pass).
- `pbe.eval --regrade` grades saved submissions again with the current checks and keeps the earlier verdicts in `grades.json` under `regrades`. Regraded `pilot-spacer`: Qwen, GLM and Opus went from fail to pass; no other verdict changed.

## Runner works end to end: first spacer run on Claude Haiku 5.5
- `pbe/eval.py` runs tasks against OpenRouter models and saves each trial under `results/runs/<run>/<task>/<condition>/<model>/t<n>/` (transcript, submission, grades with cost, turns, repairs, measurements asked for and limitations reported). `--reference` grades each task's reference solution. `pbe/agent.py` holds the prompt and the tools (`measure`, `submit_design`, `report_limitation`); `pbe/measure.py` is the person as a lookup table; `pbe/llm.py` the OpenRouter client (key from 1Password, or `OPENROUTER_API_KEY`).
- Run `pilot-spacer`: `anthropic/claude-haiku-5.5`, one trial, `can_ask`: passed every check (a 12 x 20 mm cylinder with a 5.5 mm hole, printed upright), 3 turns, $0.0042, 15 s. Its 2 schema repairs were both one confusion ours, not the model's: it named hardware by catalog reference where the schema wants the id from its own hardware list, and nothing said so. The schema now says which fields take ids, and the error lists the valid ids.
- Bugs found before or during the run: two checks returned numpy booleans, so `ok is True` was false and a passing trial would have been marked failed (now plain bools, with a test); a 1Password timeout was saved as a finished trial and would have been skipped on rerun (infrastructure errors now rerun, and the key is fetched once per run).

## M5 spacer control task, its graders, and the person as a lookup table
- `tasks/m5-spacer/`: a control task every frontier model should pass (one round part, every dimension stated, nothing withheld). If models fail it, the harness, prompt or format is broken. Reference solution in `reference.yaml`.
- `pbe/requirements.py`: requirement graders named in `requirements.yaml`: part count, bounding box, a through-hole (exactly one hole in a cross-section every 0.2 mm, at least d_min clear by its largest inscribed circle, at most d_max at its widest), and roundness. A grader that crashes on a submission now records a failure instead of stopping the run. `pbe/tasks.py` takes only the brief's first blockquote as the request, so quotes in the notes can't leak into the prompt.
- Evidence the graders work: the reference passes at the hole's ISO 273 fine, medium and coarse sizes (5.3, 5.5, 5.8), and ten wrong designs each fail exactly the check aimed at them: 5.0, 5.81 and 6.5 mm holes, an oval hole with the area of a 5.5 hole but 4.9 clear, a blind hole, a 1 mm plug across the bore, a square block, 18 and 10 mm lengths, and two parts (`tests/test_spacer.py`, 27 tests pass).
- Found by a code review before any model ran: the first version sampled three cross-sections (a plugged bore passed), took the longest side as the hole's axis (a 10 mm spacer failed the hole check for the wrong reason), and had no roundness check (a square block passed). Also two false fails at the range edges, both fixed with stated tolerances: mesh facets make a 5.3 hole read 5.2989 (0.01 mm allowed below d_min), and single-precision STL reads 5.8 as 5.80000022 (0.0001 mm allowed above d_max). Not checked, on purpose: whether the hole is centred, because the request doesn't say so.
- PLAN (Dan): the model talks to no person and no model playing one. A `measure(item, what)` tool looks up the task's recorded measurements, so answers can't be invented and reruns are identical. τ2-bench measured LLM-played users erring in 16-47% of conversations. Main condition: measurements withheld, the model can ask; control: all measurements given.

## 1/4-20 nut measured: 10.92 mm across flats
- Dan's nut is 10.92, not the 11.11 the pockets assumed (7/16 in). So round 1's Q pockets were 0.19 to 0.49 mm over the real nut, which explains why it was loose in all four and only held without snapping at +0.0. Recorded as `af_measured` in `catalog/hardware.yaml`; the nominal stays for designs that don't have the nut in hand.

## Round 2 printed: span limit raised to 50 mm; tunnel blind spot repeats
- Outcomes from Dan's hand tests and photos (indexed in `docs/media/photos.md`), filled into `results/predictions/round2-coupons.yaml` beside the unchanged predictions.
- A2: the 40 and 50 mm roofs both printed clean (IMG_5442; faint ripples, more on the 50). Round 1's rough 40 didn't repeat, and the 50 is clean for the second time. `catalog/printer.yaml` `max_span_mm` 40 -> 50, the longest span seen clean; the true limit is above 50 and unmeasured. The 60 x 70 mm span test still fails; 11 tests pass. Scored against the predictions made before printing, the check was 1 of 2 on A2 (50 was predicted to fail).
- C2: tunnel 2 printed clean, strands across, and the 10 x 6 bar slides loose (Estoa's fixed leg pocket, as expected). Tunnel 1 failed again with strands along the tunnel (IMG_5445-7), with the broken wall from round 1 fixed. The check passes that roof, so its "slicer picks the best direction" assumption is now a repeated miss, recorded in `docs/limitations.md` and the seed.
- D: seated from underneath (shaft first, tabs on the plate), both servos go in and their tab holes line up with the slots, so the tab-hole pitch read from inner edges was right (MG90S 28.01, MG996R 49.19). MG90S snug at 0.15 per side; MG996R slightly loose at 0.25, and a feature between each tab's two holes stops its tabs sitting flush: seed `servo-tab-feature-not-cleared` (C5, near-miss). An earlier cable-exit seed is withdrawn: it came from Claude's test instruction, which had Dan push the servos all the way through (IMG_5449-50).
- E: spline bores: MG90S (4.57 mm) won't go on at +0.0 or +0.1, hard push at +0.2, snug at +0.3; MG996R (5.84 mm) hard push at +0.1, snug at +0.2, loose at +0.3. Smaller features need more clearance, as with the nuts. 608 seats: won't go in at 22.0, snug at 22.1, easier at 22.2 and 22.3, holding upside down in all three; this also shows the bearing's outer diameter is about 22, not the 21.22 reading. 8 mm pegs: only 8.0 is snug; 7.8 and 7.9 a bit loose.

## Round 2 coupons, predictions logged before printing
- Printed in round 2: D-servos, E-splines-bearings, C2-tunnels (C-fits without the square holes) and A2-bridges (only the 40 and 50 mm pockets, the pair that contradicted the span limit). Full A-bridges and B2-nuts were cut for time (Dan); their predictions stay in the file, unprinted.
- New: B2-nuts (each size at 0.05 mm steps around its round-1 best: M3 +0.10 to +0.25, M5 +0.00 to +0.15, M8 and 1/4-20 -0.10 to +0.05), D-servos (MG90S body cutouts at 0.15 and 0.30 per side, MG996R at 0.25, slotted tab screws) and E-splines-bearings (spline bores at +0.0 to +0.3 over the measured outer diameter, 608 seats at 22.0 to 22.3, 8 mm pegs at 7.8 to 8.0). Repeated: A-bridges unchanged, C-fits with the tunnel fix.
- D and E are built from `catalog/hardware.yaml`, where Dan's caliper readings for MG90S, MG996R and 608ZZ now live (video IMG_5438). Two readings were interpreted, not taken as is: the tab-hole pitch was read between inner edges (centres = reading + hole diameter: MG90S 28.01, MG996R 49.19, both near the datasheets), and the 608's 21.22 mm outer diameter looks like an angled reading (nominal 22.000), so the seats use 22.0. D's slots test the first interpretation.
- The bridge check ran on every coupon this time (round 1 only ran it on A): A flags H and the 50 mm roof as before; C's two roofs pass; B2, D and E have no overhangs. Tunnel 1 already failed once, so its prediction isn't blind.
- Predictions: `results/predictions/round2-coupons.yaml`, written by `coupons/predict2.py`. B2, D and E expectations are Claude's, from round 1's fits, not a grader.

## Seeds from the eval's own coupons
- `seeds/coupon-failures.yaml`: two real C6 failures in coupons Claude designed for this project: a tunnel that cut through the outer wall (roof left as a cantilever, which the bridge check catches), and a tunnel roof that printed lengthwise and failed (which the check misses). Evidence: the round 1 print, photos IMG_5405 and IMG_5409. The atlas now includes them; 56 seeds in all.

## Coupon A printed: bridge check 4 of 6 by eye
- Printed in round 1 on the X1C, 0.20 mm, black high-speed PLA, 4 walls, 15% infill, no supports. Outcomes recorded by eye from top-down photos (indexed in `docs/media/photos.md`) beside the predictions committed before printing (`results/predictions/round1-coupons.yaml`, predictions unchanged).
- Hits: 20 and 30 mm clean; the plain hole (H) tangled; the stepped hole (S) clean with the hole open. This is the first blind support for the anchoring rule, one pair on one print.
- Misses: the 40 mm roof came out rough (loose, wavy strands) though predicted clean; the 50 mm roof printed flat though predicted to fail (Dan saw no sag by eye; a caliper couldn't reach to measure it). Read plainly, span alone didn't decide roof quality on this print, so the 40 mm limit is unconfirmed. Next: reprint to see whether 40 vs 50 repeats.
- Coupon C bug: tunnel 2 cut through the back wall, leaving its roof a one-sided cantilever (Bambu's "floating cantilever" warning), and it printed as spaghetti. Run on C-fits after the print with unchanged code, the bridge check flags exactly that roof (4% anchored). It wasn't run on C before printing, so that isn't a blind result. Fixed in `coupons/coupons.py` (block 6 mm deeper; both tunnel roofs now pass the check). The coupon predictions should run the check on every coupon, not only A.
- Square holes for the 10 mm peg (C): snug at 0.1 mm per side, slides easily at 0.2, 0.3 and 0.4. First measurement of a sliding fit on this setup (Dan). Tunnel 1's roof also failed (IMG_5409): strands run along the tunnel, not across it, though the check passes that roof (anchored on both sides, 10.4 mm). Likely the slicer bridged lengthwise; not yet confirmed in Bambu Studio's preview. Not a scored prediction (the check wasn't run on C beforehand), but it shows the check's assumption that the slicer picks the best direction can be wrong.
- Settings: 4 walls, 15% infill (Dan).
- Nut pockets (B), M8: snaps in at +0.0 mm and holds; loose at +0.1, +0.2 and +0.3. Matches the tripod prior (held at +0.0, fell out at +0.3) and fills in +0.1 and +0.2. M5: tight push-in at +0.0, easier at +0.1, loose at +0.2 and +0.3; consistent with the tripod prior (held at +0.15, fell out at +0.30). M3 (first data): won't go in at +0.0, barely at +0.1, snug push-in at +0.2, slight push at +0.3. Smaller nuts need more clearance on this setup, so one clearance for all sizes doesn't work. 1/4-20: loose in all four, though at +0.0 it stays in upside down without snapping in (the tripod prior expected it to fall out everywhere); the pocket assumes 7/16 in (11.11 mm) across flats and the nut used wasn't measured, so it may be smaller.

## What the model is told: setup facts always, techniques as a condition
- PLAN: setup facts (printer, nozzle, filament, layer height, bridge limit, hardware) are always given. Techniques are given only in a design-guide condition, so failures split into knowledge gaps and judgment gaps. Checks grade outcomes, never a specific technique. Dan's question; the Arca agent knowing stepped bridging and not using it is the evidence that judgment gaps are the interesting case.

## Limits of the bridge test written down
- `docs/limitations.md`: what the bridge check and coupon A can and can't claim (geometry only, one printer setup, guessed thresholds, one blind pair, one print judged by eye), and how to extend it (more materials and nozzles, repeats, measured sag, slicer cross-check, blind runs on Estoa). Prompted by Dan asking whether print settings and nozzle size change the result: they do, mainly the span limit.

## Bridge check: predicts the Arca plate's tangled roof
- `pbe/bridges.py`: slices the part in 0.2 mm layers from the bed up; every region with nothing under it must have a strand direction where at least 95% of strands land on the layer below at both ends, within 40 mm. Regions within 1.5 mm of the layer below are treated as small overhangs. Starting values in `catalog/printer.yaml`, to calibrate with a test print.
- Evidence: the Arca original is flagged at z = 4.0 mm (the roof over the 4 mm recess; 220 mm² unsupported, best direction 31% anchored). The fix passes (each stepped layer 100% anchored). Shape tests: a closed pocket roof passes, the same roof with a hole fails, a 60 x 70 mm roof fails on span, a 45° chamfer needs no bridge. 11 tests pass.
- Not a blind test: the rule was written knowing how the Arca plate failed. Blind tests still to run: Estoa's sealed leg-pocket hole (from the `local-lights` history), and new test prints with the check's prediction logged before printing.

## Day 1: environment, submission format, hardware catalog, first build
- `uv` project on Python 3.12 with CadQuery 2.8.0 and trimesh 5.2.0.
- `pbe/submission.py`: the submission format as pydantic models (params with sources, parts, hardware, joints, typed acceptance criteria, manual, questions), with cross-reference validation.
- `catalog/hardware.yaml`: ISO 4762 screws (with the partial-thread rule), ISO 4032 and ISO 10511 nuts, a 1/4-20 nut, ISO 7089 washers, the Estoa heat-set insert, and the salvaged webcam bolt with unknown dimensions. The threaded-to-head cut-offs are marked to verify.
- `pbe/build.py` runs part code in a separate process with a time limit; `pbe/checks.py` has the first checks (builds, one connected body, bed fit).
- `examples/arca-plate/`: the original design and the fix, ported from the agent's OpenSCAD in session c941d075. Evidence the port is faithful: volumes match OpenSCAD's export within 0.02% (17495.5 vs 17497.3 mm³ original, 16793.5 vs 16796.1 mm³ fix), with identical bounds. Both pass the first checks, as expected: their failures (head fit, roof) need the Day 3 simulation and the bridged-hole check.
- 7 tests pass (`uv run pytest`).

## Hardware-fit invariant and metamorphic check planned
- PLAN: hardware-receiving features must be derived from named hardware params; a metamorphic check varies each param and re-simulates, flagging hard-coded features and reporting a working range. This removes the Arca backtest's dependence on the bolt head's true size. Dan's idea, after the backtest needed a measurement we don't have.

## Blind backtest planned; Arca plate seeds; base-joint seed corrected
- Two seeds from the first print of the tripod project, the Arca plate: a guessed bolt-head recess (13 x 4 mm; the head didn't fit) and a roof bridge that wasn't stepped (printed stringy). Evidence: Dan's photo IMG_5045 and session c941d075, 2026-10-13T02:08. The fix (15 x 5, stepped roof) fit and worked, per Dan, so it's the first `control:` marked built-worked.
- `base-joint-reach`: the observed failure was the joint slipping on smooth cheeks. The 0.4 mm short bolt came from a later audit and isn't known to have caused it (source: the tripod mistakes list).
- PLAN: a blind backtest of real pre-print designs, starting with the Arca plate and moving to harder cases.

## Seeds from Estoa and two side projects; general failure classes
- `seeds/classes.yaml`: ten task-independent failure classes (C1–C10), each mapped to planned graders. Every seed now carries a `class:`. Electronics and power failures are out of scope and left out.
- `seeds/estoa-failures.yaml` (34 seeds: 22 failed, 11 near-miss, 1 unconfirmed) and `seeds/side-project-failures.yaml` (8: a lamp mount and a Gridfinity organizer). Mined from 37 archived agent-session transcripts in `~/claude-archive` by four reader agents. Eight key quotes were checked against the transcripts by hand, and all matched.
- Evidence: the most common class across all three projects is C1, designing from unmeasured dimensions (12 of 52 seeds, by primary class). In both the tripod and Estoa, the agent asked for measurements only after a failed print.

## Repo created
- README, PLAN, the first task (`tasks/phone-stand/`), the seed failure list, and stub catalogs. No grader or runner code yet.
- Source notes copied from the explorations KB into `docs/context/`.
