# Changelog

Each entry: what changed, why, and the evidence (a run, a failure, a measurement).

## 2026-11-13: README's "What we couldn't grade" section removed (no result changed)

- With round 3 most of the not-graded trials were settled, so the section went. Round 3's photos and a two-sentence note moved to "The test prints behind the checks", Limits says what's still not graded and links the full list in `docs/reference.md`, and `scripts/failure_tables.py` no longer writes a copy into the README.

## 2026-11-13: README edited to open with the problem; results table in markdown (no result changed)

- The problem, the three questions and what the repo does come straight after the opening paragraph, with a link to the `hackathon-submission` tag; the Estoa story follows under "How this started". "How the agent works" got a heading and links to `pbe/runner/agent.py`, `measure.py`, `coupon_loop.py` and `pbe/graders/`.
- Removed: "The takeaway", the pseudocode for two checks, "How we used AI", the AI tools in "Tools used", and the hackathon-travel and ZIP wording.
- `scripts/scorecard.py` writes the test-first results as a markdown table (a row per model, best first, the best in each column bold, compared as shown) in place of `docs/media/results-table.svg`, which is deleted.

## 2026-11-12: Main's tests green again after round 3's review fixes

- PR #7's last two fixes (the short-strand rule checks every direction, with at least 24% anchored; the test-print loop's person answers from coupon B only) went in without a regrade, and main's CI failed two tests on it. Every run and loop replay is regraded on main's code, `tests/test_servo_mount.py`'s on-edge plate now passes (its channel ledges are short-strand roofs), and two trials that no longer fail on roofs alone are dropped from `NOT_HOLED_ROOFS` (Qwen 3.8 Flash knob t5, Gemini 4 Argon wheel t5 clears on regrade).

## 2026-11-12: Decisions models tried as judges on five known-answer tests (no grade changed)

- **What.** OpenRouter's Decisions API (`pbe/judges/decisions.py`): Jev 1.14 and GPT-6 Luna Decisions answered five questions whose answers are known (`scripts/judge_known_answers.py`, raw answers in `results/judges/2026-11-12/`, table from `scripts/judge_summary.py`). Gemini Decision 1 was dropped at Dan's request. Total $0.064. Write-up: `docs/decisions-api.md`.
- **Results after Claude's hand check of every disagreement** (`results/judges/hand-labels.yaml`):
  - supports asked for in a design's text: 98% for both judges (baseline 52%);
  - Dan's spoken outcomes as verdicts: Luna 90%, Jev 82% (baseline 40%); every miss was a stated word call in the code;
  - roof photos, clean or not: 68% for both, no better than always saying "not clean". With two labelled example crops of each verdict, taken from other cells only: Luna 53%, Jev 47%, worse than without. The bridge strips' failure (strands that break when touched) doesn't show in the photo;
  - Jev's Box put all 13 cell centres inside Claude's boxes (IoU 0.18 to 0.91);
  - Estoa transcript checklist: 97 to 98% (baseline 70%);
  - failure records into the 10 classes in `seeds/classes.yaml`: Jev 86%, Luna 67% (baseline 23%). With a record's class held out, Luna answered "none of these" for 70% of them, with 11% false flags; Jev did so for only 19%. 4 of Jev's 8 misses are defensible under C5's own wording, which overlaps C1.
- **Found on the way:** `pbe/parts/supports.py` misses "Support is needed under the roof inside the box" (Haiku 5.5 Estoa can_ask t5, loop feedback arm). Not fixed here. Test 4's own keyword keys were wrong 10 times where the judges were right. The judges missed keyhole tests that code found in the `print_test` calls.
- **After review:** the client retries lost connections and timeouts, and records them as failed calls instead of crashing. `--budget` is a hard cap. Finished calls are kept when a run stops. Test 4's keyword keys are corrected at the source and agree with all 246 hand-checked keys. Test 2 keeps one row per record (rerun: 40 outcomes, same disagreements).
- **No trial was graded by a judge.** Recommendation: Jev as the default judge for narrow labels, with Luna as a second opinion only, never alone on runs where GPT-6 Luna competes. Neither is to be used on roof photos.
## 2026-11-12: One Estoa trial on Gemini 4 Carbon (`pilot-estoa-carbon`)

- Gemini 4 Carbon (`google/gemini-4-carbon`, released 2026-11-10, priced as Gemini 4 Argon), one `can_ask` trial on the light box, the first run with "Supports: none" in every condition's prompt (Dan asked for one run, 2026-11-12). $1.50, 33 minutes.
- Outcome: no design. Turns 1 to 4 asked 22 measurements in batches of 8, 5, 5 and 4 (the disc, perfboard, ESP32's port, wall screws, wires; $0.11). Turns 5 to 8 each spent the whole 32,000-token reply cap on reasoning (31,997 reasoning tokens, finish reason `length`, about 8 minutes and $0.35 each) and were cut off before any text or tool call, so it never called `submit_design`. The cap is the same for every model, so it stands as Gemini 4 Carbon's failure: it couldn't fit its design work into one reply. Like most Opus and Sonnet trials, it asked for the USB-C plug's moulded head (width, thickness, length), the gap Estoa's own build fell into.
- One trial; Argon's eight Estoa trials ran without the supports line, so this isn't a like-for-like comparison.

## 2026-11-12: Supports a design asks for pass the bridge check; every condition is told there are none

Dan, 2026-11-12: "I would say if an existing design said to do supports, then it's fine. Also, for new runs, we say no supports."

- **Declared supports pass the bridge check** (`pbe/parts/supports.py`, `checks.bridges`, `Built.supports`). `docs/plan.md` already said they should; the check ignored them. A part whose design says to print it with supports passes, and the finding says so: "prints with supports, as the design's instructions say (...)", followed by what it would get without them. Claude's calls: the instructions read are the note, each part's `print_orientation` and the manual's steps; a `print_orientation` covers its own part, a step that lists parts covers those, and a step that lists none, or the note, covers every part. A sentence counts only when it plainly asks ("print with supports", "tree supports", "supports under the roof", "enable supports", "Support: ON"); one that also says no ("no supports", "without supports", "supports: none", "doesn't need supports", "support-free") or makes them conditional ("only if your slicer asks", "if the roof is still loopy, reprint with supports") doesn't. One function decides it (`asks_for_supports`), with a test of each phrasing.
- **How many saved designs it touches:** 5 of the 1145 saved submissions under `results/runs` ask for supports: DeepSeek V4.1 Flash `loop-all` tripod can_ask t1 feedback (plate and screw, from the note: "Support: ON (auto)"), Claude Haiku 5.5 Estoa can_ask t5 in `pilot-estoa` and in `loop-estoa` neutral (box: "front wall needs support inside the cavity"), and GPT-6.1 Sol bearing wheel can_ask t3 and t8 in `pilot-wheel` (wheel, plus t3's spacers and t8's fit coupon from their manual steps: "build-plate-only support inside lower pocket"). In each, a part the supports cover fails or isn't graded on bridges today. Not regraded: the published results stay as they ran until a regrade.
- **Every condition is told there are no supports** (`agent.system_prompt`, `NO_SUPPORTS`): the line "- Supports: none. Every part has to print without them." now sits under "Longest bridge seen to print cleanly" for every condition, not only `can_test`. Saved trials keep the prompt they ran with. The tests that compare today's prompt with a saved trial's (`test_can_ask_has_the_same_prompt_as_the_saved_trials`, `test_the_other_conditions_send_the_same_tools_and_prompt`) now apply the documented changes since (`tests/helpers.PROMPT_CHANGES_SINCE_SAVED`) and expect nothing else to differ: this line, and the 25T aluminium horn's entry in `catalog/hardware.yaml` (Dan, 2026-11-11: no clamp screw, hub measured 14.66, 14.68 and 14.63), which reaches every prompt through the hardware list.

## 2026-11-12: Round 3 and 3b outcomes in the graders

Dan's outcomes for round 3 (`results/predictions/round3-coupons.yaml`), the 3b roof crops and long spans (`round3b-roofs.yaml`) and his measured USB-C plug (`catalog/connectors.yaml`, `usb_c_plug_overmold.measured`) now decide checks that were not graded for want of them. No prediction or outcome was changed. Every rule below that reads a record a particular way is **Claude's scoring call**, labelled as such in the code and the briefs.

- **Bridges** (`pbe/graders/bridges.py`, `catalog/printer.yaml` `short_strand_mm: 6.8`). Claude's call: a roof whose longest strand is 6.8 mm or less passes, whatever share of strands is anchored; otherwise the old rule (95% anchored, at most 50 mm). Evidence: GPT-6.1 Sol's roof crop (44% anchored, longest 6.8) printed clean; ring roof 5 (hex 8.1 round a 5.5 hole, 24%, longest 6.0) printed mostly ok and held a tightened M5 nut, slightly proud; ring roofs 2 to 4 (longest 7.5 to 9.9) and every other crop failed. The 60, 80 and 100 mm spans all failed, so `max_span_mm` stays 50. Ring roofs came out 9 of 10 as predicted; cell 5 was the miss. Knock-on: narrow ledges round a bolt hole that were "not measured" now pass (the nut knob's bed pocket and second hex recess, the wheel's stepped roof corners), and the test-print loop's roof reply follows the same check.
- **Nut pockets** (`pbe/graders/nuts.py`). Pockets are read as plain, ribbed or lipped, at their tightest across-flats, against prints of the same shape (`ROUND3_READS`, one reading per cell, quoting the record). Claude's call: a pocket passes when the nut goes in pressed on a bolt and holds upside down; thumb-only isn't required. Holds: R3 (M5, 3 round ribs, bite 0.2), R2 (M5, 6 flat ribs, bite 0.1), U3 (M5, -0.05), L1 (M5, lip 7.8, in by thumb; the lip keeps it in). Won't go in: R5 (M3, 3 ribs, bite 0.2), L2 (M5, lip 7.6), U2 (-0.1), U1 (-0.15). R4 (M3, 6 ribs, bite 0.1) went in but its hold wasn't reported, and no other M3 rib print is near enough to settle it, so it stays not graded. R1 is left out (its rib sheared). Matching keeps round 1's rule: a printed step within 0.01 mm, two agreeing steps either side, or beyond the last step only where the trend settles it. `tests/test_nut_knob.py` checks the records' clearance and bite give the same shape and width the pocket reader reads from the printed cells.
- **Bolt holes** (new `pbe/graders/bolt_fits.py`, read by `bolted.bolt_hole` and `wheel.bolt_passes`). From F: M8 screws through 8.0, goes through 8.1 pushed, slides through 8.2; 1/4"-20 screws into 6.35 only, goes through 6.5 with slight grip, 6.6 loose (8.3, 8.4 and 6.8 not reported, not read). A hole the bolt passes by hand is a clearance pass. Claude's calls on "screws in": it fails the tripod plate's R3 (the plate's thread holds the bolt, so once the head seats it can't pull the camera down) and the wheel's R4 for the wheel itself (the wheel would grip the bolt and not spin), but passes for a spacer, which doesn't spin. Tripod R3 is now: under 6.35 or 6.35 itself fails, 6.5 to 13 passes, between 6.35 and 6.5 not graded. Wheel R4: 8.0 fails, 8.1 and over passes, between not graded.
- **Bearing seats** (`pbe/graders/wheel.py`, `tasks/bearing-wheel/requirements.yaml`). From H: 22.05 won't go in, so R3 fails at 22.05 and under (was 22.0); 22.4, 22.5 and 22.7 were too loose, so R3 fails from 22.4 (was not graded above 22.3). 22.2 held flush and 0.2, 0.4 and 0.6 mm proud: Claude's call, R2 passes a seat up to 0.6 mm short of the bearings (was not graded). 22.2 with no shoulder held upside down; whether a push moves it through wasn't reported. Claude's call: R2 passes a bore with no shoulder, since the width is R3's question.
- **USB-C opening** (`enclosure.plug_reaches`, estoa-light R3 and its brief row). Dan's plug head is 11.58 x 6.44 with 7.5 mm of bare metal. Claude's call: the way in passes when it holds that head with 0.2 mm a side (11.98 x 6.84, read as a slot shape, since the head's corners weren't measured) from the port all the way out; it fails when the bare head doesn't get through 4 mm or more out from the port, Estoa's recorded failure; anything between is not graded. The proposed pass line, "head plus margin up to within 7.5 mm of the port", was dropped: it would pass Estoa's 11.5 mm opening, which stood 4 mm out and stopped plugs. The reference (14 x 8.5) passes, Estoa's 11.5 x 8.5 still fails, and 13 x 8.5 and 12 x 7.5 openings now pass. Dan kept the 0.2 mm margin (2026-11-12): a tight opening isn't necessarily a failure, since the plug can be forced in, or the opening opened up with a Dremel at worst.
- **With `main`'s assumption tolerance** (`pbe/graders/assumed.py`, 2026-11-08), merged in after the regrade below, so its numbers predate it and the saved results are to be regraded. Every round 3 rule keeps the tolerance: where round 3 leaves a gap, the nearest print within 0.2 mm decides, the tighter on a tie, and the finding says which print it was assumed from. So nothing between two recorded prints stays not graded: wheel R3 between 22.3 (held) and 22.4 (too loose) takes the nearer, the too-loose print joining `assumed.nearest`'s list; bolt holes between 8.0 and 8.1 (M8) or 6.35 and 6.5 (1/4"-20) take the nearer through `bolt_fits.reading`; a lip midway between L2 and L1, like GLM's 7.7 mm one, reads as L2's "won't go in"; and Grok's and GPT-6.1 Sol's spring clips, 0.05 tighter than R3's ribs, read as holding from R3. The test-print loop's coupon B replies say "can't tell" for a pocket only round 3 printed, since its person printed coupon B alone.
- **Not wired:** the servo mount (M) and horn (N) tasks live on other branches, and no grader here reads them. Insert posts (L) aren't printed yet.
- **Regrade** of every saved trial the changed checks read (11 runs, 848 trials, in place, `--regrade`), plus the loop replays (`coupon_loop.grade` over `results/runs/loop-*`). 97 trial outcomes moved:
  - nut knob (356): 48 not graded to pass, 28 not graded to fail, 1 fail to pass, 1 fail to not graded (GLM's 7.7 mm lip sits between the 7.6 that failed and the 7.8 that held). 64 R4 verdicts were decided: Sonnet and Opus pockets mostly pass, Haiku and GPT-6 Luna mostly fail tighter than anything that went in.
  - bearing wheel (184): 15 not graded to pass, 3 not graded to fail (seats of 22.4 mm and over). 23 R2 and 23 R4 verdicts went from not graded to pass.
  - Estoa (48): 1 fail to not graded (GPT-6.1 Sol `test-first` can_test t2: its roof printed clean and now passes, and its unclosed mesh leaves R2, R3, R5 and R6 not graded). 7 R3 verdicts were decided, 4 pass and 3 fail.
  - tripod plate (204) and M5 spacer (56): no outcome moved. 20 tripod R3 verdicts went from not graded to pass, and 4 roofs from fail to pass, on trials that fail elsewhere.
  - Loop replays: tripod Opus 5.5 t3 feedback goes from fail to pass on R3; the rest move with the checks above. Every change is in the run's `grades.json`, `summary.csv` or `loop.json`.
  - Then `narrowest_tangled_mm` went from 3.0 to 2.0 (ring roof 2's 2.0 mm ledge tangled; it had been left at the Arca plate's 3.1 mm), and declared supports count (the entry above). Regraded again, on top of the numbers above, 16 more moved: 14 not graded to fail (11 bearing wheels, 2 tripod plates, 1 knob, all ledges 2 to 3 mm wide) and 2 fail to pass (GPT-6.1 Sol `pilot-wheel` can_ask t3 and t8, whose instructions ask for supports inside the lower pocket). Estoa is unchanged: 1 pass, 39 fail, 5 not graded, 3 no design (Haiku t5's box declares supports and its roof now passes, but it fails elsewhere).
  - Restacked onto main, which had added the 0.2 mm assumption tolerance (`pbe/graders/assumed.py`), and regraded once more. Against main's published results, 127 of 802 trial outcomes moved: nut knob 64 not graded to pass, 24 not graded to fail, 10 pass to fail (pockets tighter than round 3's tightest that took a nut), 1 fail to pass; bearing wheel 12 not graded to fail, 6 fail to pass, 3 not graded to pass; tripod plate 2 not graded to fail; Estoa 1 not graded to pass, 2 not graded to fail, 2 fail to not graded, leaving it at 1 pass, 39 fail, 5 not graded, 3 no design. Verdicts the tolerance decides name the print they were assumed from.

## 2026-11-12: Regrade trials side by side (`--workers`)

- `uv run python -m pbe.eval --regrade ... --workers N` grades saved trials in N processes at once; the default, 1, grades them one after another here as before. Each trial still writes only its own `grades.json`, and `summary.csv` is written once at the end from the saved trials in path order, so the saved files don't depend on the worker count (`test_a_regrade_with_two_workers_saves_what_a_serial_one_does`: two m5-spacer trials regraded with one worker and with two save byte-identical `grades.json` and `summary.csv`). No verdict changes: this only changes how fast a regrade runs.
- One date and commit stamp per regrade now, taken when it starts, instead of one per changed trial; trials regraded together say so. Verdict-changed lines print in path order as trials finish; a trial that raises stops the regrade, as before. `--workers` without `--regrade` is an error.
- Not done for the coupon loop's replays (`scripts/coupon_loop.py`): each replay calls a model and checks the shared budget before each arm, so running them side by side would let the budget overshoot. `--model` already lets one process per model run side by side.

## 2026-11-11: Round 3 test prints, and Estoa's keyholes for any wall screw, any way up

- **Physical work reopened (Dan, 2026-11-11),** back at his printer: `CLAUDE.md` now allows test prints and measurements when he offers them, with predictions written before printing.
- **Round 3 test prints** (`coupons/round3.py`, `coupons/ROUND3.md`), predictions in `results/predictions/round3-coupons.yaml` written before printing: bolt holes (F), ring roofs (G), bearing seats (H), nut pockets under size and with the commonest rib and lip shapes the models drew (I; shapes counted from 111 trials not graded for them, more than the README's 98), Estoa's insert posts at 5.5 to 8 mm with one 8 mm post at 100% infill (L), the servo-mount plate and cutout frames (M), and pockets for the 25T horn's hub (N). Printed 2026-11-11, everything but the 100% post; outcomes not yet recorded. Dropped before printing: tripod clamp plates and head recesses (no clamp to hand) and keyholes (below).
- **Estoa's R6, any way up (Dan, 2026-11-11):** the disc is round and the USB-C port can come out of any side, so the box hangs whichever way its slots run. Slots are measured against their own average direction instead of the design's +y (`enclosure._hanging_up`). Slots running opposite ways still fail.
- **Estoa's R6, any common wall screw (Dan, 2026-11-11: "a generic wall screw, should work with different kinds of screws").** Claude's scoring call: the entry must pass a 9.9 mm head (a #10 pan head, 0.373 in, plus 0.2 a side for printed holes coming out small) and the slot must carry it clear of the entry; the slot passes a #8 shank (4.17) and holds a #6 pan head (6.5 mm). Not a #10 shank: Estoa's own 4.8 mm slots hung it. Head sizes are from supplier listings citing ASME B18.6.3 and B18.16.3, not the standard's table.
- **Regrade of the 48 saved Estoa trials on a copy** (published results unchanged): 14 R6 verdicts moved, 9 not graded to fail (slots too short to carry a #10 head clear, or wider than a #6 head), 4 not graded to pass, 1 fail to pass (slots that ran down). Trials: Opus 5.5 `pilot-estoa` can_ask t2 goes from not graded to the first Estoa pass (entry 10.0 against the 9.9 limit, so it rests on the 0.2 mm margin); Opus t1 and Sonnet t2 from not graded to fail; Haiku t4 from fail to not graded.

## 2026-11-12: servo R3 fails a plate with no gap for the rib, whichever way it's seated

Dan, 2026-11-12: "if there's no gap printed for the rib (no slot), then it's a failure." Until now R3 took the best of three routes, and a plate with no room for the rib on either face, seated from above with more than test print D's 0.25 past the case end, came back not graded, since the cable exit was never measured. Six saved servo-mount plates were not graded that way (GPT-6.1 Sol four times, Sonnet 5.5 twice; 0.30 to 0.50 past the case end), all designs that forgot the rib, the miss the task is built to catch. A page drawing all eight not-graded plates from their STLs showed it.

- **The rule** (`servo.flush`): if neither face gives the rib room, R3 fails, with the cable route's detail kept. A plate with rib room is unchanged, and so is a miss under the tabs where another part's place isn't recorded. Applies to servo-arm's R3 too, which uses the same grader.
- **Regraded** offline: servo-mount, 29 trials, 4 pass, 17 fail, 8 not graded became 4 pass, 23 fail, 2 not graded. The two left are Gemini 4 Argon's `can_ask_datasheet` plate (R2, blind screw holes) and GPT-6.1 Sol's `all_given` plate in `servo-first-look-2` (R2 and R3, separate rails whose place isn't recorded). servo-arm's first look: Sonnet 5.5 `can_ask` went from not graded to fail on R3; 6 fail, 1 not graded (DeepSeek). Other R3 details changed wording only.
- **What it rests on:** Dan's rule, not a print. Seated from above the rib faces away from the plate, and what stops that route is the cable, never measured; the brief says so under known limits. `docs/servo-arm-horn-request.md`'s cable-exit gap row now says it decides no saved trial.

Evidence: `tests/test_servo_mount.py` (no rib room fails with a 0.4 plain cutout and with a cable notch, both not graded before), 72 passing in the servo files.

**Restacked on main after #7:** servo-arm's R5 takes round 3's H records as bearing-wheel's R3 does (22.05 too tight, 22.4 and up too loose; `wheel._holds` gained `too_loose`). A 22.6 seat now fails instead of being not graded. Saved servo-arm trials not regraded for it (a follow-up); round3-coupons.yaml is main's copy.

**Codex review fix** (PR 4, `arm.py`): R7 counted an end of the arm's bore as open if its centre was clear, so a horn pocket under a 3.4 mm screw hole could go on from the screw's side too, which the hub can't. An end now counts as open only if the hub's whole circle clears it. Test: `test_a_horn_pocket_under_a_screw_hole_goes_on_one_way_only` (fails before the fix). Regraded servo-arm's first look: no finding changed.

Scoring walk:
- **Real-world relevance:** unchanged.
- **Task design:** the trap now catches what it was built for; weak: most models still seat from above, where the rib only fails by rule.
- **Grader reliability:** six not-graded verdicts settled; weak: by Dan's rule rather than a printed record of the cable.
- **Evidence of model limitations:** R3 now fails in 21 of the 29 servo-mount trials; models that leave a rib channel are still rare (4 passes).
- **Reproducibility:** regrade needs no key.
- **Human expertise and review:** the rule is Dan's.
- **Insight:** a picture of the plates made the call obvious that a table of "not graded" didn't.

## 2026-11-12: round 3's servo test prints settle servo-mount's R1 band, its rib channel, and servo-arm's horn pocket

Dan recorded round 3's M and N pieces on 2026-11-12 (`results/predictions/round3-coupons.yaml`, copied unchanged from branch `claude/test-first-ten`, where it's uncommitted; whichever lands second takes the other's copy).

- **R1, the cutout** (servo-mount and servo-arm): M3's frames went over the MG996R's body at 0.0 a side ("fits very snugly") and 0.1 ("fits snugly, but not as snug"). The band between the body's size and test print D's 0.25, not graded until now, passes: `fits: [0.0, 0.1]`. Under 0 a side still fails.
- **R3, the rib's channel:** M1 (0.295 a side) and M2 (0.05 and 0.15 a side), channels 2.2 deep, plate grooved face up: every channel took the rib and the tabs sat flush. The pass moves from the rib plus 0.25 a side (carried over from R1, no relieved plate printed) to the rib plus 0.05 (`rib.room`), and narrower down to the rib's own width passes as assumed from 0.05, within the assumption tolerance. The depth rule is unchanged: 1.8, the rib's height.
- **R2, the 10 mm across a tab:** M's 3.4 holes at 10 showed clear through all four tab holes with the servo seated ("visually it is a clear hole, there is no obstruction"). That confirms 10 to about ±0.6 mm, not exactly; no screw was tried. No verdict moves: R2 already used 10.
- **R4 on the horn** (servo-arm): N's 14.76 pocket "fits nicely: cozy, a bit loose but doesn't fall out" (Dan: "a bit loose is fine"); 15.16 and 15.66 "too big". The outcome words gain "fits" (works, read before "loose"), "too big" (too loose) and "too small" (too tight), Claude's call. A pocket from the hub's 14.66 to 14.96 passes (14.76 printed, the rest assumed from it); 15.0 and up fails (assumed from 15.16 below it).
- **Planning miss, from round 3:** the cable leaves the case below the tabs, so a close cutout only takes the servo shaft end first from the side the tabs land on. The brief now says so; R3's "from underneath" is that seating, named for the plate.

Regraded every saved servo-mount and servo-arm trial offline. servo-mount, 29 trials: 1 pass, 17 fail, 11 not graded became 4 pass, 17 fail, 8 not graded. The three new passes are `servo-first-look` `all_given` Gemini 4 Argon, and `servo-first-look-2` `all_given` Opus 5.5 and `can_ask` Gemini 4 Argon, all on R1, with cutouts 0.12 to 0.19 a side. R1 went from not graded to pass in 13 of the 29. No R3 verdict changed. servo-arm's first look: no trial's outcome changed; R1 passed in three more trials, and Haiku `all_given`'s 15.06 horn pocket went from not graded to fail on R4, too loose, assumed from 15.16. `docs/reference.md`'s servo-mount row is updated.

Evidence: `tests/test_servo_mount.py` (a 0.0 and a 0.1 cutout pass; 1.7 and 1.55 channels pass, the second as assumed) and `tests/test_servo_arm.py` (the recorded pockets: 14.8 passes, 15.0 fails), 73 passing in those files; full suite 639 passed, 52 skipped.

Scoring walk (`docs/scoring.md`, and section 5 of the hackathon's eval design guide):
- **Real-world relevance:** Dan's own servo and horn, on the printer he uses. Weak: one servo and one horn.
- **Task design:** unchanged; only the limits moved.
- **Grader reliability:** two not-graded bands closed from printed records, with three trials moving to pass. Weak: the horn's pass below 14.76 and R3 under 0.05 a side rest on the assumption tolerance, not prints; the outcome words are matched by keyword.
- **Evidence of model limitations:** most models chose a cutout 0.1 to 0.2 a side, tighter than D's 0.25, and that band now passes, so the R1 trap mostly didn't catch anyone; failures left on servo-mount are R2 and R3.
- **Reproducibility:** the records are a committed file; the regrade needs no key.
- **Human expertise and review:** Dan's outcomes; reading "fits nicely ... a bit loose" as works, and the frame orientation as R3's "from underneath", are Claude's.
- **Insight:** a test print planned around one direction of assembly can be answered in the other: round 3's frames were meant to be pushed up from underneath, the cable stopped that, and the result still settled R1 because sliding a frame over the body is the same fit.

## 2026-11-11: servo-arm brought onto the current history; R4 grades an arm on the horn from round 3's pockets once they're recorded

servo-arm was built on the history before 2026-11-08's rewrite and never merged. Its files are ported by hand onto main (branch `claude/servo-arm-horn`); the old branches (`claude/servo-arm`, `claude/servo-arm-assembly-plan`) aren't rebased or pushed. servo-mount was already on main (#47), identical to `claude/servo-mount`, so nothing of it is ported.

- **Ported:** `tasks/servo-arm/`, `pbe/graders/arm.py`, `catalog/datasheet_estimates.yaml`, `docs/servo-arm-assembly-plan.md`, `tests/test_servo_arm.py`, the first look (`results/first-look/servo-arm-first-look`), and its two changes to `servo.py` (the cutout reader's run ends where the overlap can't take the body; the closest fit wins), with their two servo-mount tests. The task's `prompt.yaml` is now `format.yaml`, as main moved prompt rules there; the datasheet paths and the servos left out are the same. CI's reference loop includes servo-arm.
- **R4 follows main's assumption tolerance** (`assumed.py`, 2026-11-08), as every other fit check does: a bore within 0.2 mm of test print E's 5.94, 6.04 or 6.14 takes that print's result, so 5.74 to 6.13 passes and 6.14 and up fails. R5 already had it through `wheel._holds`. Two tests changed with it: the spline's own 5.84 and 6.09 now pass, labelled as assumed; the not-graded cases moved to 5.70 and a 22.6 seat.
- **R4 for an arm on the aluminium horn** (`arm.horn_records`, `arm.horn_fit`): the arm's hub pocket is graded from round 3's piece N (14.76, 15.16, 15.66 mm pockets, 2 mm deep), read from `results/predictions/round3-coupons.yaml`. That file isn't on this branch yet and its outcomes are empty, so every horn arm stays not graded, saying round 3 has no recorded outcome. Which words mean what is Claude's call, in `requirements.yaml`: the hub has to go in and centre the arm, so "won't go in" reads as too tight and "loose" as too loose; "tight" and "play" work. A failure keeps which way it failed: no bigger than a too-tight pocket, or no smaller than a too-loose one, fails; a size on a pocket that worked, or between two that did, passes; otherwise the nearest within 0.2 mm decides. Horn-shaped pockets and pockets under 1.8 mm deep aren't graded: only round 2 mm pockets were printed. The horn's two screw holes weren't on the piece, and nothing reads them.
- **Regraded** the first look offline with both: no trial's outcome changed. Two R4 findings went from not graded to pass under the tolerance: Haiku `can_ask` (5.90 bore) and DeepSeek `can_ask` (5.75), both assumed from 5.94's hard push. The earlier verdicts stay in each `grades.json` under `regrades`.
- **Codex review fixes** (PR 4), each with a test: a pocket's failure no longer rules out the other side (with only the loose 15.66 recorded, a 14.76 pocket had failed as "tighter than a pocket that didn't work"); a bore with a narrow slot or small teeth isn't plain (area alone missed a 0.5 mm slot, so the widest-span check `wheel._is_round` uses is added); and R5 passes if any seat holds the 608, since the design uses one, instead of letting another opening its size, such as a servo cutout, make it not graded. Regraded: no trial's outcome changed; R5 went from not graded to pass for Haiku `all_given` (22.29 seat) and Opus `all_given` (22.24).
- **Proposed request** (`docs/servo-arm-horn-request.md`): the arm driven through the horn, and what changes in the checks. Not run; no run until the wording is approved.

Evidence: `tests/test_servo_arm.py`, 29 tests, including a horn arm not graded with round 3 unrecorded and passing with a fixture where 15.16 worked, and pocket sizes against the fixture's records. `tests/test_servo_mount.py` and `tests/test_prompt_rule.py` pass: 95 in those three files. Full suite: 635 passed, 52 skipped before the review fixes; the servo and bearing-wheel files (95) after. `--reference --task servo-arm` passes every check.

Scoring walk (`docs/scoring.md`, and section 5 of the hackathon's eval design guide):
- **Real-world relevance:** Dan's own horn, on the arm he's building. Weak: one person's hardware.
- **Task design:** unchanged until the new wording is approved; the proposal keeps the function in the person's words and leaves the mechanism open.
- **Grader reliability:** the horn pocket's limits will come from a print record, read by code; until then not graded, never a pass. Weak: the screw holes aren't graded, the outcome words are matched by keyword, and horn-shaped pockets are left out.
- **Evidence of model limitations:** no new runs.
- **Reproducibility:** the grader reads a committed file; no key needed.
- **Human expertise and review:** the outcome words, the "loose fails" call and the 1.8 mm depth floor are Claude's, for Dan to review.
- **Insight:** a test print only settles what it has on it: piece N decides the hub but not the screw holes, so R4 on the horn can pass on centring while whether the arm turns with the horn stays open.

## 2026-11-08: The game spinner task removed

- Dan's call, for the submission: the game spinner (PR 44) is taken out whole: its task, grader (`pbe/graders/combined.py`), first-look runs and tests. It was written before the assumption tolerance and broke against it (20 failing tests, one a crash in its grader); none of the scored results used it.

## 2026-11-08: The assumption tolerance, test-print replies that answer, and PR 60's README and results

- **Assumption tolerance** (`pbe/graders/assumed.py`, 0.2 mm). A size within 0.2 mm of a printed size takes that print's result, and the finding says which print it was assumed from; midway between two prints that disagree, the tighter decides. Only for sizes close to something tested (Dan: \"similar to a test that we already did, not something completely different\"): crush ribs and clips, proud bearings or a bore with no shoulder, narrow ring ledges, recesses far from the 5 mm printed, and the Estoa assumptions that aren't tests (board thickness, a 9 mm head) stay not graded. Applied in `nuts`, `wheel`, `bolted` and Estoa's insert posts.
- **Regraded offline** (no model calls) with it, every run and replay. Not graded fell from 200 to 35 trials across the scored runs; the rest are mostly M5 knobs whose crush ribs are 0.25 to 0.8 mm tighter than the nut.
- **Insert posts** (Estoa R4): the only bulge on record was printed at 100% infill (Dan, 2026-11-08), so posts are graded as printed at 20%: 1.85 mm or more of plastic holds; thinner isn't graded.
- **Test-print replies** (`pbe/runner/coupon_loop.py`) use the same tolerance: a pocket or seat between printed sizes gets the nearest printed result, labelled as the nearest; a plain roof over air gets the bridge check's answer; Estoa's test pieces are answered from Estoa's records (keyholes against the one that hung, USB openings against 14 x 8.5 and 11.5 mm, insert holes against 4.3 mm and 1.85 mm walls, disk-hole spacing against Dan's calipers). These came after the test-first runs, so those runs heard the stricter replies.
- **test-first** includes the 10-trial top-up's finished trials (uneven counts per model; its strict-reply run was stopped). An Estoa run with the new replies (24 trials, 0 pass) is kept out of this PR: we ran out of time to make the loop work on Estoa.
- **Scorecard**: the results table in the eval's own look (Dan: not the reference's), a before-and-after table of first print against test prints, and the Estoa note.
- **README**: the test-print section rebuilt from the records (`coupons/coupons.py`, `results/predictions/`) in Dan's words; a test-print storyboard and flowchart for the test-print loop; Estoa's example failures; the neutral OpenRouter key wording, the try-your-own-request note and `can_test` as `pbe.try_request`'s default (from the skill session, Dan's request).
- **Submission ZIP**: `results/runs/**/transcript.json` is left out (143 MB of the repo's 165), so the ZIP is under 50 MB; the transcripts stay in the repository.

## 2026-11-07: New task `servo-arm`, an arm on the MG996R that swings both ways, graded from the test prints and an estimate off the datasheet drawing

A second task on Dan's servo, after he asked for something more mechanical than a plate. The request is his own wording, approved on 2026-11-07: "I want to prototype the first version of a robot arm. I have an MG996R servo and a 608 bearing to work with. It should swing both ways, and the arm should be about 100 mm long." He first asked for 90° either way, and loosened it to "swing both ways" once the swing turned out to need the shaft's position, which no one measured. No model has been run on it.

- **Task** (`tasks/servo-arm/`): servo-mount's prompt rule (the `servos` section left out, the readings in `hidden_facts.yaml`) and its datasheet pages for `can_ask_datasheet`. The hidden facts add the spline (5.84), where the shaft is in words, the listing's 120° and the horns in the box. The reference is servo-mount's plate plus a flat arm with a 6.0 bore on the spline and a 22.2 seat for the 608, 100 mm to its tip.
- **Checks**: R1 to R3 are servo-mount's. New in `pbe/graders/arm.py`: R4 the bore on the shaft (test print E: 5.94 a hard push, 6.04 snug, 6.14 loose), R5 the 608's seat (round 2: 22.0 too tight, 22.1 to 22.3 held), R6 the length (85 to 115, a reading of "about 100", for Dan to change), R7 the swing: a clear 120° arc around the shaft (the datasheet's "approximately 120 degrees (60 in each direction)"), past the mount's part and the servo's case, at every shaft position and arm height the estimates allow.
- **Estimates** (`catalog/datasheet_estimates.yaml`, new): the shaft 10.3 mm from one case end, on the centre line, measured in pixels off the datasheet drawing, used as 9.3 to 11.3 because the drawing isn't to scale; the arm anywhere 0 to 10 mm above the case top, because the drawing's heights disagree with Dan's readings by about 2 mm. In a separate file because `hardware.yaml` is in every task's prompt: adding them there changed all 18 recorded prompt hashes.
- `servo.Mount` records the plate's axis and where its layers start, so R7 can place the servo's case. No servo-mount verdict changes.

**First look** (`results/first-look/servo-arm-first-look`, 2026-11-07, Dan asked for it): the six lineup models in `can_ask` and `all_given`, one trial each, $3.75. OpenRouter's credits ran out after 8 of the 12 trials; Sonnet, DeepSeek, Gemini and GPT in `all_given` errored with HTTP 402 before a call was made and still have to be run. Of the 8, after the fixes below: no pass, 5 fail (2 on R3, 3 only on `bridges`), 2 not graded, 1 declined (GPT-6.1 Sol: final parts stop on `raise` until shaft_x and the horn are measured).
- Four of the eight arms use Dan's aluminium horn rather than a printed bore. The checks found the arm only by a bore on the spline, so they read the horn's screw hole as a loose bore: Opus's and Sonnet's `can_ask` arms failed R4 on it. Dan pointed out the horn wasn't being used (2026-11-07), and asked to assume its holes are threaded for M3 (not yet in the hidden facts: the run's last four trials have to see the same facts).
- **Horn route** (`arm._horn_pocket`): with no bore on the spline, a pocket whose clear circle is the horn's 14.66 hub stands in for the shaft's axis, so R6 and R7 grade the arm; R4 is not graded for it. A hole on the pocket's axis is the horn's. Tests: an arm on the horn, a 6.5 hole on its axis, and an arm with neither.
- **servo-mount's cutout reader** (`servo._runs`) intersected a run's opening with any overlapping opening in the next layer, however little overlapped, so a gap behind the servo's window shrank the window to the overlap: Opus's `can_ask` frame, a wall with a 41.2 x 20.4 window, read 2.94 mm a side too small and failed R1. Now a run ends where the overlap can't take the body. That exposed a second fault: of several body-sized openings, `find_mount` took the roomiest, and Gemini's `can_ask` frame has a 2.3 a side gap with nothing for the tabs beside its 0.29 a side window. Now the servo goes in the closest fit the body passes (`servo._preference`). Tests: a gap behind the window, and a roomier window beside the cutout. Regrading every servo-mount trial (`servo-first-look`, `servo-first-look-2`, `servo-datasheet`, 29 trials) after both changed no verdict; Opus's frame now reads 0.29 a side and passes R1 and R2.
- After both fixes, regraded: Sonnet `can_ask` fail → not graded; Opus `can_ask` loses R1 and R4, keeps a `bridges` fail. Multi-part designs dominate: 6 of the 7 that built have a part the format can't place, so R7 passed only for Haiku's two-part design.

Evidence: `tests/test_servo_arm.py`, 20 tests: the reference passes everything; a loose bore, a 22.0 seat and a short arm each fail only their own check; posts around the shaft fail R7 when they stand past any arm height, pass when two leave room, and are not graded when they're low enough that the arm's height decides; a third part the format can't place makes R7 not graded; a blind bore goes on one way only. The prompt hashes in `tests/test_prompt_rule.py` still match.

Scoring walk (`docs/scoring.md`, and section 5 of the hackathon's eval design guide):
- **Real-world relevance:** Dan's own servo and bearing, in his own words, for the arm he's building. Weak: one person's hardware.
- **Task design:** the request names the function and leaves the mechanism to the model. Weak: the swing rests on estimates, so many designs will come back not graded on R7, and horn-mounted arms aren't graded on R4, R6 or R7 at all.
- **Grader reliability:** every fit limit cites a print record; the shaft position and height are labelled estimates with their bands; tests cover each mistake alone and the gaps. Weak: bearing alignment, load and horn fits aren't graded, and a 0.5 mm grid reads near misses as contact (never as a pass).
- **Evidence of model limitations:** none yet: no runs.
- **Reproducibility:** grading needs no key; the reference grades in about a minute.
- **Human expertise and review:** the request is Dan's and he approved it; the limits, the 85 to 115 band and the estimate's ±1 mm are Claude's calls, for Dan to review.
- **Insight:** with "swing both ways" instead of 90°, the servo's published range sets the bar, and the spline lets the arm start at any angle, so the check needs no rest position from the model.

## 2026-11-07: Test prints before the final design (`can_test`), and the README rebuilt around it

- **Why.** In every earlier run the model never learned how its test print came out: test prints were handed in with the final design, and the Nov 3 loop replayed a saved trial with one report afterwards. Dan: a test print is for the model to decide it doesn't know something, hear how the test came out, and then design the final. That measures whether it knows what it doesn't know.
- **New condition `can_test`** (`pbe/runner/agent.py`). The model may call `print_test` any number of times within 12 turns; the person answers each piece from the recorded prints only (`coupon_loop.printed_parts_report`), or "I can't tell you how that one came out" where no print decides it. Only the final design is graded (`agent.graded_design`), with test pieces stripped. Optional, in Dan's words: "If you need to know whether something is going to work but you're not sure, ask the person to print a test of it before you hand in the final design, so you both save time and filament." Its setup also says "Supports: none. Every part has to print without them", which the other conditions didn't until 2026-11-12 (see that entry), so trials saved before then differ between `can_test` and `can_ask` in that line as well as the tool.
- **Pilots.** `pilot-test-first`: 12 trials (6 models, M3 knob and wheel), 6 pass, $1.35. `pilot-test-first-neutral`: 6 trials with a neutral wording that didn't mention saving time, 2 pass, $0.68; kept apart and out of the tables.
- **`test-first`**: 6 models (Opus 5.5, Sonnet 5.5, Gemini 4 Argon, Gemini 3.8 Flash, GPT-6.1 Sol, DeepSeek V4.1 Flash) × 5 trials × the four scored tasks, $12.61. Pass rates: Argon 70% (14/20), Flash 60%, Sol 45%, Opus 45%, Sonnet 30%, DeepSeek V4.1 Flash 19% (3/16; 4 M5 trials still to run, stopped by the shared budget). The same models pass 15 to 28% of first prints in `can_ask`. 111 of 116 trials asked for a test print. 91 got at least one "can't tell" reply, and 37 of the 53 passes came after one, which the README states as a limit. One OpenRouter credit stop (HTTP 402) was rerun after Dan topped up.
- **Estoa in `test-first`**: the same 6 models × 3 trials, $9.51, 0 of 18 pass (2 no submission within 12 turns). It's its own row in the results table.
- **Grading changes for the tables:** seven bridges-only failures in newer trials are listed in `results_table.NOT_HOLED_ROOFS` with what the mesh shows (ledges and flutes with no hole, checked by `test_a_bridges_alone_trial_is_a_holed_roof_unless_listed`). Slicer estimates cover the test pieces a model asked for (`parts/test<n>/`).
- **Scorecard.** The README's results are now a table picture (`docs/media/results-table.svg`, Dan's chosen layout: a column per model, best cell in each row shaded, the winner outlined, a 0% tie shades nothing), a best-to-worst ranking that notes Grok 4.7 was skipped for cost, and the can't-tell line. The wide table and chart moved to `docs/reference.md`.
- **README.** Restructured with Dan's dictated sections and a contents list; examples for each not-graded reason (`scripts/not_graded_figures.py`); a legend on the wheel cross-sections; failed knobs cut through with the nut drawn in; the knob Pass picture is now Sonnet 5.5's test-first knob (it tested 5.40 to 5.70 mm and built at 5.70). `PLAN.md` moved to `docs/plan.md`.

## 2026-11-07: Ten trials per model, the test-print loop on every unpassed trial, and a shorter README

- **Ten `can_ask` trials** per model on the four scored tasks (`scripts/top_up.py --trials 10 --task ...`), except Qwen 3.8 Flash, stopped at 35 (Dan, 2026-11-07). Two stops for the OpenRouter account's credit (HTTP 402) were retried after Dan topped it up; errors are infrastructure stops, never results.
- **`loop-all`**: the rule in `docs/coupon-loop.md` ("Every unpassed trial"), pushed before the run. 186 feedback replays for six models (Opus 5.5, Sonnet 5.5, Gemini 4 Argon, Gemini 3.8 Flash, GPT-6.1 Sol, DeepSeek V4.1 Flash), $14.06 of the $15 budget, no errors left after retries. The scorecard counts a replay that ended in an error as not replayed.
- **Scorecard** (`scripts/scorecard.py`): verified pass rate on the first print and after feedback, not graded, pass^k, tokens, cost per pass, and slicer print hours and filament per pass, both prints included; a chart; and a generated note on passes that came after an "I can't tell" reply.
- **Tables from scripts**: `scripts/update_tables.sh` rewrites or checks the scorecard, the full results, the failure classes (now including estoa-light's checks; C7's example is Estoa's keyholes) and the failure counts (`scripts/failure_tables.py`).
- **README** cut to Dan's sections, the walkthrough, the failure classes with build photos, a section per task with its ground truth and examples (`scripts/task_figures.py`, `scripts/walkthrough_figures.py`), what couldn't be graded, prior work and tools. The rest, and the build story, moved word for word to `docs/reference.md`.

## 2026-11-07: Slicer estimates for the Estoa light and its test-print sample

`uv run python scripts/slice_estimates.py pilot-estoa loop-estoa` on Dan's Mac, from 1dc450e, with Bambu Studio 02.08.02.61 and the fixed setup (X1 Carbon 0.4 nozzle, 0.20mm Standard @BBL X1C, Generic PLA High Speed @BBL X1C, no start or end sequence). Offline: nothing went to a printer, no model was called and no grade changed. The Estoa session asked for it once PR 57 merged, and Dan approved the PR.
- **Sliced:** `pilot-estoa` 29 of 29 parts (17 trials). `loop-estoa` 47 of 49 parts (28 arms). The 2 not sliced are DeepSeek V4 Pro t1's box in both arms, whose code doesn't build, matching its saved verdict.
- **First print against second**, the sample's rule of at most two prints (`docs/coupon-loop.md`, "Estoa sample"). The 14 replayed designs' first print comes to 42.9 h and 1.98 kg, a median of 3.4 h a box. Over the 13 trials whose second design builds, the first print is 40.1 h and 1.85 kg. The second print is 43.2 h and 1.95 kg after the printed reply (3.1 h and 100 g more), and 40.3 h and 1.86 kg after the neutral turn. The replies that changed the most grew the box: GPT-6.1 Sol t3 went from 4.0 to 5.5 h and Sol t2 from 3.8 to 4.7 h.
- **The one pass**, Gemini 4 Argon t2 after the printed reply, takes 3.9 h and 179 g on the first print and 3.8 h and 176 g on the second: about 7.7 h and 355 g of filament to a box that passes on the records.
- These are slicer estimates, not prints. 6 of 17 first designs and 12 of 28 second designs include test prints (1.4 h and 2.9 h of them in all). Written beside each run's `summary.csv`: `slice_estimates.csv` per trial (per arm in `loop-estoa`, condition `can_ask/feedback` or `can_ask/neutral`) and `slice_estimates_parts.csv` per part.

## 2026-11-07: The test suite trimmed to one test per behaviour; 54 old bugs put back to show nothing was lost

Dan: the suite "sounds like AI slop". It grew a case for every fix, repeated cases across nut sizes and sandboxes, and was never pruned. Tests and test helpers only: no grader, runner, task or saved result changes, so no verdict can move. Audited on main after #23, #56 and #57.

**Counts.** 623 tests to 512, with 3 skipped instead of 58. Run time barely moves: on the main before #23, at `-n 4` in this Linux cloud session, timed alternately twice each, main took 351 s and 376 s and the trimmed suite 339 s and 347 s, about 6% less. Most of what went was cheap (Docker copies that skip here, lookup rows), and the time is in grading parts for the tests that stay (below).

| file | before | after | what went |
|---|---|---|---|
| `test_nut_knob.py` | 117 | 91 | the reference graded at M3 and M8 (`pbe.eval --reference` grades every size, and a new test checks each size loads with its catalog nut); the 3 R4 "says why" cases merged into the matching wrong-design cases they rebuilt; M8 copies of the stepped roof, the plain-hole bed pocket and the between-steps coupon; the M3 copy of a coupon rescuing a failing size; the design-level "loose" case (`_holds` covers it); the print table's lookup tests cut to one row per rule (23 to 14, and 16 to 6) |
| `test_run_python.py` | 75 | 37 | the 33 Docker copies, which skip without Docker; 6 repository paths read in one test, as 3 paths in one call |
| `test_build_on_submit.py` | 50 | 28 | the 22 Docker copies |
| `test_runner.py` | 45 | 37 | non-object tool arguments: 3 kinds × 3 tools to each tool once with a different kind; unsafe part ids 4 to 2 |
| `test_caching.py` | 14 | 6 | 3 conditions × 3 models to each once; the request body checked for one other model |
| `test_tripod_plate.py` | 36 | 34 | the channel plate and the no-recess plate, each a strict subset of a test kept (the channel and the no-recess plate with a pin hole) |
| `test_slice_estimates.py` | 32 | 29 | durations 5 to 3, unreadable ones 3 to 2 |
| `test_spacer.py`, `test_build_submission.py` | 20, 32 | 19, 31 | a second "too wide" hole (6.5 beside 5.81); a third video extension |
| `test_bearing_wheel.py` | 22 | 22 | none; two tests graded each design twice, now once |
| `test_estoa_light.py` | 65 | 63 | the blind-insert and sliver tests' no-template cases: `test_inserts_behind_the_disk_need_a_template` covers no template |
| `test_loop.py`, `test_results_table.py` and the rest | 22, 38, ... | unchanged | each test checks something different |

**Sandbox tests.** `tests/conftest.py` runs each sandbox test once, in the sandbox `code_sandbox.find()` picks, which is the one a trial would use: the container where Docker runs (Dan's Mac), else bubblewrap (Linux, CI). `uv run pytest --all-sandboxes` runs them in every sandbox, as before. CI's step that asserts `find()` is bubblewrap still stops a run whose sandbox tests would skip.

**Nothing lost: 54 old bugs put back.** Each grader fault in this changelog that a model's design or a review found, and a core check per task, was put back as a minimal patch to `pbe/` (`git checkout` restored it after each). For 50, the trimmed suite fails, naming the test that catches it. That includes everything the cut tests were for: area-only hex shapes, the nut at one angle, READ_AS, loose read as a failure, between-steps verdicts, every way a coupon can't rescue, the round collar, chamfer depth, the lightening cell, the raised nub (issue 15), drill-out layers on the knob and the tripod, the sleeve and the hub bore in `holes()`, sealed voids and coupon pieces, bridge strands, narrow ledges, holed roofs, Luna's channel, one bevel, pads in the thickness, R4's whole layers, the head on the camera side, the spacer's quarter-length rule and chamfers, a proud bearing, a through bore, counts as floats, the repository mounted into run_python's jail, and from #23 the blind insert pocket's bottom, a disk screw's whole shank, a nut that fits the screw, and the loop's second turn offering `assembly`.

Four aren't caught, and main's untrimmed suite doesn't catch them either, so they were gaps before this change:
- the knob's "a hole runs sideways" guard: the "walls split" guard after it also says not graded for a knob on its side. With both off, the tests fail;
- the tripod's pick of the bolt's bore by its recess, then its narrowness: the tests have no design with two holes the bolt fits;
- the tripod's head seat chosen as the widest end rather than the deepest: no test has a seat at each end;
- the wheel's seat depth read in whole layers: no test sits on a layer boundary.

They're written down here rather than fixed: closing them means new grader tests, not pruning.

**Cache of built parts: tried, not kept.** A per-session cache of built parts, keyed on code and params, cut the knob, wheel and spacer files from 124 s to 112 s. Builds are a small share: grading the tripod reference takes 17.5 s, 12 s of it in shapely's `maximum_inscribed_circle` (`sections.clear_width`), with `bolted._bores` run three times on the same mesh (R3, R4, R5). Caching those is a grader change, outside this audit.

**Scoring walk.**
- Real limitation: unchanged. No task changed.
- Clear task, defensible answer: unchanged.
- Reliable grader, no false passes or fails: the regression suite keeps one test per known fault and per check, shown by putting each fault back. Weak: the 4 uncaught mutations above. The list of mutations and the test catching each is in #58.
- Meaningful failures: unchanged.
- Original and reproducible: the suite is faster to rerun, and `--all-sandboxes` keeps the Docker copies.

## 2026-11-07: Five can_ask trials per model on every pilot task

Dan asked for 5 trials per cell across 11 models (2026-11-07), so the pilots say a little more about how much one model varies. `scripts/top_up.py` gained `--trials`, `--all-models` and `--model`; it ran one process per model side by side overnight on Dan's Mac, from f7273e7, each with a $10 cap across all of them. Grok 4.7 was left out: at about $0.47 a trial it would cost more than the other 11 together.
- **The run:** 145 new trials on m5-spacer, nut-knob M3 and M5, tripod-plate and bearing-wheel (`can_ask`), numbered after the saved ones in the same run folders. They cost $7.90. No infrastructure errors; 2 ended with no submission (Gemini 3.8 Flash's tripod t4 and Qwen 3.8 Flash's M5 t3, both after 8 turns). Saved trials are unchanged.
- **Totals now:** 326 trials, 94 pass, 144 fail, 73 not graded, 12 declined, 3 other, $27.83, with the `estoa-light` trials from PR 23 (the README's results table, from `scripts/results_table.py`). Without them: 308 trials, 94 pass, 130 fail, 70 not graded, 12 declined, 2 other, $21.80.
- **The tripod's new trials aren't like its old ones.** t4 and t5 ran after the person started giving the clamp's width as 38 mm (entry of 2026-11-06), so they can't be pooled with t1 to t3 on R2 or on declining. The README's `can_run_code` comparison keeps to t1 to t3. GPT-6.1 Sol was told the width and still declined both: "A nominal 38 mm width does not ensure dovetail retention".
- **The spacer mostly stays a control:** 55 of 57 pass. Both failures are Qwen 3.8 Flash's: t3's code didn't run, and t5's spacer is in pieces (`connected_bodies`, then R2 to R4). The README's "Every trial passes" no longer holds.
- **Updated:** the README's results table and assumptions, its "Pilots" limit and the counts in "What went wrong, task by task" and the not-graded table (recounted with `scripts/results_page.py`'s diagnoses over the same trials, from the meshes saved on this Mac); `docs/limitations.md`, `docs/lessons.md` (Sol's declines, 28 of 84 holed roofs) and `docs/coupon-loop.md`. Holed roofs now account for 53 of the 58 trials that fail `bridges`.

## 2026-11-07: Slicer estimates read test-print replays

`scripts/slice_estimates.py` read only runs of trials (`grades.json`), so a replay such as `loop-estoa`, saved as
`loop.json`, gave nothing. It now reads each replay arm with a design as a trial, its arm joined to the condition
(`can_ask/feedback`), so the two prints' hours and filament can be compared: the first print from the replayed run
(`pilot-estoa`), the second from each arm. The `-schema-bug` originals aren't sliced again. A test reads `loop-estoa`'s
28 arms with designs. No estimate has been run yet: it needs Bambu Studio, on Dan's Mac.

## 2026-11-06: R2 checks a disk screw's whole shank against the ESP32, and needs a nut that fits it

Two Codex findings on PR 23, left open on 2026-11-04 because they could move saved verdicts; Dan asked on
2026-11-06 to fix every open finding.
- **The whole shank:** R2 tested only the screw's tip against the ESP32's envelope, so an M3 x 30 that ran right
  through the ESP32 and ended below it passed where an M3 x 20 ending in it failed. It now tests points every
  0.25 mm from the board's back face to the tip (`enclosure._among_electronics`).
- **A nut that fits:** R2 accepted any nut in the hardware for a clearance hole, so an M5 nut held M3 screws. It
  now needs a nut of the screw's size and takes that nut's height and width from the catalog (`enclosure._nut_for`).
- Tests: `m3x30-runs-right-through-the-esp32` and `m5-nuts-on-m3-disk-screws`, both failing before the fix.
- **Saved verdicts:** none move. Regrading `pilot-estoa` and every design in `loop-estoa` (baselines and both arms)
  gives the same verdict on every check.

## 2026-11-06: The test-print loop on the Estoa light (`loop-estoa`): the person prints it all and says what went wrong

Dan asked (2026-11-06) to replay the Estoa failures with the failure described, so the model can send a new design.
The protocol was written and pushed before any model call (`docs/coupon-loop.md`, "Estoa sample"), including at
most two prints, at Dan's suggestion.
- **The reply** (`coupon_loop.ESTOA_LINES`): one line per failing check, in a person's words, never a cause or fix,
  each naming what it rests on (an Estoa record, Dan's calipers, plain geometry, or the bridge check).
- **Result, 14 trials, $7.14:** of 32 failing checks, the printed reply fixed 10 and the neutral turn 1.
  Gemini 4 Argon t2 passes every check on the records after the reply. Keyholes that point down (R6) are the
  failure the reply fixes least: all three Haiku designs send them pointing down again. Dan grouped it under C7
  (works in the orientation it's used), not a class of its own. GPT-6.1 Sol's arms first stopped on the
  OpenRouter key's $30 limit and ran after Dan raised it.
- **A harness bug, found by Codex:** the second turn's tools left `assembly` out of the design schema
  (`coupon_loop.second_turn` now passes `task.format.assembly`; a test). Six arms that left it out were told
  "assembly is required", and DeepSeek V4 Pro's four ended with no design. Those six ran again with the same replies;
  the originals are kept as `<arm>-schema-bug/`. Now DeepSeek t1's designs don't build (its own CadQuery errors)
  and t3's printed arm fixes two checks and breaks one.
- **Reply wording Dan changed after the run** (for later runs): R2's "bottom out" line in plainer words, and R3
  split by reason: the opening doesn't line up with the port, the plug's head doesn't fit through, or the plastic
  runs into the port.

## 2026-11-06: The tripod test-print sample's last neutral arm

The `loop-tripod` run had stopped at its $3.00 cap before Gemini 4 Argon's `can_run_code` t3 got its neutral arm. Dan asked to finish it. `scripts/coupon_loop.py --run loop-tripod --budget 3.25` skipped every saved arm and ran that one, from 8c1a4f8, with the person cut back to the facts its first turn had, so it didn't get the clamp-width answer. It cost $0.14, so the run cost $3.16 in all.
- **Result:** after "take another look" it still fails `bridges`, so it fixed nothing and broke nothing. Its printed arm had stepped the roof but lost the recess, failing R3.
- **The sample, now complete:** after the printed reply 14 of 24 roofs are fixed, against 2 of 24 after the neutral turn. That's 12 more roofs fixed by being told how the roof printed. Whole-trial passes are unchanged: 3 against 2, or 4 against 2 with the R3 drill-out fix.
- **Updated:** `docs/coupon-loop.md`, and the "2 of 23" in the README, `docs/lessons.md` and `docs/limitations.md`. `loop-tripod/summary.csv` gains that trial's neutral verdict.

## 2026-11-05: New task `servo-mount`, the MG996R plate, with the rib left out of its prompt, and its first three runs (issue 40)

A new task from Dan's own hardware, the start of a robot arm: a printed plate that holds an MG996R servo by its tabs. Its trap is test print D's real mistake (`seeds/coupon-failures.yaml`, `servo-tab-feature-not-cleared`): the mount was modeled from the body and the hole positions, and a 1.8 mm rib between each tab's two holes stopped the tabs sitting flush. Dan approved the request's wording on 2026-11-05. Results are a first look, outside the headline numbers.

- **The rib was in every prompt.** `hardware_text()` put all of `catalog/hardware.yaml` in the system prompt, including `tab_notch`. A task's `format.yaml` can now name top-level catalog sections to leave out (`hardware_left_out` in `TaskFormat`, `pbe/runner/tasks.py`; first written as a separate `prompt.yaml`, folded into main's format file on Dan's call, 2026-11-07, to keep one format). Only `servo-mount` has one, leaving out `servos`; `hidden_facts.yaml` has the same MG996R readings, so `measure` answers them in `can_ask` and `all_given` states them up front. A section name that isn't in the catalog is refused.
- **Every existing task's prompt is byte-identical.** `tests/test_prompt_rule.py` hashes the opening messages and tools of every runnable task (m5-spacer, tripod-plate, bearing-wheel, nut-knob M3, M5 and M8) under `can_ask`, `all_given` and `can_run_code`: 18 hashes taken on `claude/caching-pilot` at 11489b7 before the change, and all 18 still match at 9e15468 and on this branch.
- **A fourth condition, `can_ask_datasheet`** (Dan, 2026-11-05): `can_ask`, with the task's datasheet handed over with the request as page images and the person saying "I've attached the servo's datasheet." The system prompt and tools are `can_ask`'s. Only a task whose `format.yaml` names a datasheet can run it; any other is refused. `servo-mount`'s is the MG996R datasheet Dan attached, rendered at 150 dpi with no metadata (`tasks/servo-mount/datasheet/`, a vendor drawing, as for Estoa's). It shows the rib in its photo and top view without sizing it, gives a 53.6 mm tab span, and gives body sizes that differ from Dan's readings (40.7 x 19.7 in its specs, 40.3 and 20 on its drawing, against 40.58 x 19.82). It contains neither the 49.5 mm hole spacing nor the 10 mm across a tab that the catalog calls datasheet values. Three shared tests that list the conditions were updated.
- **Graders** (`pbe/graders/servo.py`, three new names in `requirements.GRADERS`; no existing grader or shared helper changed). The servo's place comes from the plate's own cutout, not from #23's unmerged `assembly` format. R1 (C2): the body goes through, from D_servos' 0.25 a side. R2 (C3): a screw through each tab hole lands in a plate hole at both 49.19 (measured) and 49.5 (the catalog's datasheet value). R3 (C5): the tabs sit flush, seated from underneath (the rib needs room) or from above (the cable has to pass the cutout). Limits, records and what they don't establish are in `tasks/servo-mount/brief.md`.
- **What isn't graded, and why:** from above, the plate can never pass on the records, because the cable exit's size was never measured; so a plain cutout looser than D's 0.25 is not graded on R3, not failed. The rib's room is geometry, since no relieved plate was printed; its pass limit carries R1's 0.25 a side over to the rib, labelled as an extension. Dan's 8.31 rib reading isn't used, since it disagrees with a 10 mm hole spacing however it's read. A miss under the tabs on a design with more than one printed part is not graded, since where the other parts go isn't recorded. Load, the manual's direction, blind screw holes and the optional arm aren't graded.

Runs (every failure was checked against its design):
- **`servo-first-look`**, `can_ask` and `all_given`, $1.50: run without the cable's location. The catalog's `tab_shape` note says where the cable leaves the case, but the hidden facts didn't carry it, so `measure` couldn't answer and `all_given` didn't state it, and R3 failed 7 trials on test print D's cable record, a fact no model could learn. The eval's fault; kept as the record (`results/first-look/servo-first-look/README.md`).
- **The fix:** `hidden_facts.yaml` gains `cable_exit`, "out of one end of the case, below the tabs", with its size marked as never measured. Dan later said it leaves near the bottom of the end; the hidden fact still says "below the tabs", and the datasheet's side view agrees with him.
- **`servo-first-look-2`**, the same 12 trials with the cable fact, $2.16: 1 pass, 6 fail, 5 not graded. The pass is Gemini 4 Argon in `all_given`: seated from underneath, tabs in a 1.8 mm recess, a 2.71 mm channel for the rib, slots wide enough for a 10 to 12 mm hole spacing, and a fit-test print. Room for the rib: 1 of 6 in `can_ask` (Gemini), 2 of 6 in `all_given` (Gemini, Opus). Every other plate that built seats the servo from above with a plain cutout, where the rib is out of the way and the cable decides R3: at 0.25 or less past the case end it fails on D's record, looser it's not graded.
- **`servo-datasheet`**, `can_ask_datasheet` on five models, $1.15 (DeepSeek V4 Pro reads text only, so it isn't run): 0 pass, 2 fail, 3 not graded. Room for the rib: 1 of 5 (Gemini again). No model took the datasheet's 19.7 mm width; all used the measured 19.82. At one trial per model, the datasheet shows no effect on R3.
- **Grader faults the runs found**, each fixed with a test that fails before the fix and the three runs regraded: two walls standing either side of the case read as a second, shorter cutout (Opus's datasheet plate failed R1 at -1.29 mm a side; now R1 and R2 pass and R3 fails on the cable); and separate rails under the tabs read as nothing under the tabs (GPT-6.1 Sol's `all_given` plate failed R2 and R3; now not graded). No other verdict changed.

Evidence:
- `--reference` passes for servo-mount and every existing task.
- `tests/test_servo_mount.py`, 41 passed: the reference and other correct designs pass (channels on top, a slot through the plate, a wide pocket, D's slots, the datasheet spacing, M4 screws, a wall on one edge, walls either side of the case, a slot through a 1.6 mm plate); test print D fails only R3; each real mistake fails only its own check; reward hacks fail (an oversized cutout, nothing under the tabs, recessing the whole tab, stepped tab supports); cases between the records are not graded (including separate rails); the datasheet condition sends the request, the line and both pages.
- After Codex's review of PR 47, two R3 fixes with tests: both tabs must meet the plate at one height, and room past the plate's far face counts.
- `--regrade` of every saved trial outside the servo runs, on a copy of the tree: no `ok` value changed in any of the 153; a copy without this change gives identical findings. The servo grader is used by no other task.
- The three runs are saved in `results/first-look/`, as the game spinner's are, so they stay out of the README's results table and the headline numbers.
- `uv run pytest`, locally (CI is off for lack of Actions credits): 474 passed, 55 skipped (the container sandbox tests: no Docker on the machine). Every `--reference` passes.

Scoring walk (`docs/scoring.md`, and section 5 of the hackathon's eval design guide):
- **Real-world relevance:** a real mistake on Dan's own servo, and a mount is the first part of the robot arm he named. Weak: one person's servo and one agent's mistake.
- **Task design:** the request leaves the mechanism and the way of seating it to the model. Weak, and shown by the runs: most models seat the servo from above, the usual way, where the rib doesn't matter, so the trap rarely comes into play; and from above can't pass on the records, so those plates fail or come back not graded on the cable.
- **Grader reliability:** every limit cites a record; the tests cover the reference, each real mistake alone, reward hacks, other correct designs and the gaps between records. The runs found two false failures in 29 trials, both fixed. Weak: "rib cleared" is geometry, not a test print; a looser plain cutout escapes to not graded; multi-part designs can't be placed.
- **Evidence of model limitations:** knowing the rib's size isn't enough: in `all_given` 4 of 6 models were told it and left no room. One trial per model and condition, so no differences between models are claimed.
- **Reproducibility:** each run's command is on issue 40; grading needs no key.
- **Human expertise and review:** every reading is Dan's, and he approved the request and asked for the datasheet condition. On 2026-11-07 Dan reviewed the 3D page: the servo drawn from his readings looks like his MG996R, and Gemini 4 Argon's passing `all_given` plate "looks like a good print". He hasn't reviewed the other designs or the four grading calls below. The limits, the carried-over 0.25 and the reading of 8.31 are Claude's calls, for Dan to review.
- **Insight:** a fact in every prompt can't be a trap; and a trap only measures the mistake when the design route that meets it is the one models choose.

## 2026-11-05: Estoa light: stated assumptions for what the records can't decide, more trials, and own parts required

Dan asked (2026-11-05) to grade the checks the records leave open under assumptions, said plainly to be
assumptions. The verdicts from the records don't change.
- **`assume` in requirements.yaml**: a sentence, its source, and the grader arguments it replaces.
  `python -m pbe.assumptions --run RUN` grades only a trial's undecided checks with it and writes `assumed.json`
  beside `grades.json`. The README lists each one with what it decides, and gives a per-check table for the
  task on the records and with the assumptions; the results page shows both on each trial.
- The four (`tasks/estoa-light/requirements.yaml`):
  - R1: each disk hole at the middle of Dan's readings, 16.85 mm out;
  - R2: the disk 1.6 mm thick (the standard board, and the Estoa model's value);
  - R4: an insert holds with at least 2.85 mm of plastic, halfway between the 1.85 that bulged and the 3.85 that
    held (halfway itself holds: Opus t2's 10 mm posts leave exactly 2.85);
  - R6: wall-screw heads 9 mm across (Dan bought them at most that), so a keyhole works if its entry passes the
    head and its slot carries it clear of the entry; `enclosure.keyholes` takes `head` for it.
  - R3 and R5 get none: the only open cases fail elsewhere, and R3's would lean on the USB-C spec, which Dan set
    aside as a pass mark.
- On the first seven trials, the assumptions decided 11 open checks and no design passed: Sonnet t2 (nothing failed
  on the records) fails R4 at 2.35 mm; Opus fails R6 (an 8 mm slot doesn't carry a 9 mm head clear); Argon fails
  R2 (an M3 x 8 bottoms out 6.0 mm behind a 1.6 mm disk).
- **The person's own parts are required in an assembly task's hardware.** DeepSeek left them out in t1 and again in
  t2, so nothing made it place them and six checks couldn't read either design. `submit_design` now sends such a
  design back for repair (`TrialTools._own_parts_missing`; a test). Trials before this keep their verdicts.
- **Two more trials per lineup model** (Dan, 2026-11-05): `pilot-estoa` now holds 18 trials, three per model,
  $6.03 in all. A first attempt stopped when the OpenRouter credit ran out (HTTP 402); those trials were saved as
  infrastructure errors and run again once Dan topped it up. Two killed mid-call left empty folders, removed.
  On the records: 0 pass, 14 fail, 3 not graded (Opus t2, Sonnet t2, DeepSeek t2), 1 no submission (Sol t1).
  With the assumptions: **1 pass (Opus t2)**, 15 fail, 1 not graded (DeepSeek t2, which placed none of the person's
  parts). Opus t2 failed nothing on the records: 10 mm lid posts leave 2.85 mm of plastic (R4, halfway, so it holds
  under the assumption), and its 10 mm entry and 11 mm slot carry a 9 mm head clear (R6).
- Per check over the 17 graded designs (README): `bridges` fails 11; R4 fails 6 on the records and 7 with the
  assumptions; R6 fails 6 and 7. R1 fails once (DeepSeek t3 put the disk inside plastic), and R7 once.
- **Two more grader faults the new trials found**, each checked against the design, fixed, with a test that fails
  before the fix:
  - R7 counted GPT 6.1 Sol t2's declared wall screws as standing 17 mm out of the back. A screw standing in one of
    the back's keyholes is now taken as a wall screw. Sol t2 R7: fail -> pass.
  - R2 looked for a nut only past the end of the plastic, and failed Gemini 4 Argon t3's captive nuts, slid into
    slots across its pillars 3.5 to 6.3 mm behind the disk. A void along the screw as wide as the nut across flats
    (5.5 mm, ISO 4032 M3; new `nut_af` argument) and as deep as the nut now holds one. Argon t3 R2: fail -> pass.
- Checked and kept as the models' own: Sol t3's box has no side wall between about 3 and 36 mm up (R3, R5); Sol t2
  cut a 96 mm full-height opening in the wall (R5; the request asks for a box "all closed up"); Argon t3's
  perfboard runs 5.5 mm into its round wall (R5); Sonnet t3's keyholes have 5 mm of solid plastic beside the slot
  and no pocket for the head (R6); Opus t3's lid came out in 10 pieces.
- **The results page shows each Estoa design assembled** (Dan, 2026-11-06): the printed parts where the design
  places them (see-through), the person's parts as simple solids from their measurements (the disk, off by default,
  at the checks' estimated 120.5 mm radius and 1.6 mm), every screw, and each failed check drawn where it fails:
  red on the records, orange under an assumption. Each layer can be turned off. Built by
  `scripts/assembly_scene.py` from the reasons the checks give, so a mark shows where to look, not a second grading.
- **For Dan to decide: Argon t2 fails only `bridges`.** Its front rim bridges 40 mm over the USB opening (within
  the 50 mm the printer has bridged cleanly), but the bridge follows the round rim, so most strands end at the
  curved outer edge: 22% land on solid at both ends, against the check's 95%. No print shows whether a curved rim
  bridge like that prints. Under R4's assumption the detail text names the roomiest insert that passes rather than
  the tightest; the verdict is the same.

## 2026-11-04: First Estoa light run (`pilot-estoa`); five grader faults it found, fixed and regraded

Run `pilot-estoa`, `can_ask`, one trial each on the six lineup models plus a second Sonnet trial: 7 trials,
$2.22 in all. Dan asked for it (Sonnet first, then the rest). Final verdicts after the fixes below, regraded
with `--regrade` (no new model calls): no model passes. 5 fail, 1 not graded (Sonnet t2), 1 no submission
(GPT 6.1 Sol ran out of its 8 turns fixing schema errors in `submit_design`).

| model | verdict | fails | not graded | cost |
|---|---|---|---|---|
| Claude Haiku 5.5 | fail | bridges, R4, R6 (slot points down) | R1, R2, R3 | $0.04 |
| Claude Opus 5.5 | fail | R4 | R2, R6 | $0.45 |
| Claude Sonnet 5.5 t1 | fail | bridges, R4, R6 (slot 8.4 mm) | R1, R5 | $0.40 |
| Claude Sonnet 5.5 t2 | not graded | none | R1, R4, R6 | $0.44 |
| DeepSeek V4 Pro | fail | bridges | R1 to R6 (placed none of the person's parts) | $0.02 |
| Gemini 4 Argon | fail | bridges | R2, R6 | $0.69 |
| GPT 6.1 Sol | no submission | | | $0.19 |

What the models did, from the transcripts:
- Every model that asked anything asked for the disk's holes, and none guessed them: the request says there are
  two. Opus checked them on a template and Argon on a test print, so their R1 passes whatever the true spacing.
- Three of the six designs put the inserts in 8 mm bosses with 4.3 mm holes (R4: 1.85 mm of plastic), the posts
  that bulged in Estoa.
- No design repeated the 11.5 mm USB opening; R3 passes for four, and Haiku's 14 x 6 mm is not graded.
- Bridges fail on four of six designs.
- Every model asked the disk's diameter or thickness, which Dan never measured, and got "I can't measure that".

Grader faults the run found, each checked against the design's geometry, fixed, and given a test that fails
before the fix (`tests/test_estoa_light.py`):
- **R2, an insert behind a skin:** Sonnet t1's disk screws pass a 1 mm skin's 3.4 mm hole into inserts pressed
  in from the inside. R2 read only the hole at the surface and failed it as "a clearance hole and no nut". It now
  looks along the screw for an insert's hole and counts the thread from where it starts. Sonnet t1 R2: fail →
  pass (4.2 mm of thread).
- **R1, a blind insert pocket:** Opus and Haiku put the inserts in blind pockets. R1 read the pocket's solid
  bottom, and for Haiku a 0.36 mm sliver 4 mm away, as where the screw had to go, and failed both as missing
  the hole ("by at least inf mm" for Opus). It now stops where the hole a screw can reach ends, and leaves
  bottoming out to R2. Haiku R1: fail → not graded (inserts hold one spot, and no template checks it).
- **R2, a disk never placed:** DeepSeek listed none of the person's parts, so its assembly placed none; R2
  crashed. It's now not graded, as R1, R3 and R5 already were.
- **R6, a square-ended slot:** Sonnet t2's slots have square ends. R6 took the slot's direction towards its far
  corner, read it 11 degrees off and probed the lip beside the pocket, 10 mm instead of 3. It now runs from the
  entry through the slot's centre. Sonnet t2 R6: fail → not graded (9.6 mm of travel, short of the 12 that hung).
- **R5, a big opening in one wall:** Argon's 40 x 18 mm USB cutout let R5's one probe from the board's centre
  leave the box, and it called the perfboard outside. A side is now open only if it's open from the centre and
  all four corners. Argon R5: fail → pass.

One fault on the person's side: Sonnet t1 asked for "screws you will hang it on" and got no answer, so it
guessed 8 mm heads and cut 8.4 mm slots. `hidden_facts.yaml` now takes "hang" for the wall screws; t2 got the
answer. Sonnet t1's R6 failure stands, but part of it is the eval's.

The README's results (`scripts/results_table.py --write`) now count the run: 158 trials, $14.73, and an
`estoa-light` table, its wording "drafted from Dan's answers, approved by Dan". Trials failing on `bridges`
alone go from 21 to 23 (DeepSeek and Argon here).

The results page (`scripts/results_page.py`, https://claude.ai/artifact/8FoztxxrwV6ioveQhz8gY6) shows the run:
estoa-light diagnoses in the builder (it fell back to the tripod's wording for a task it didn't know), an audit
note per trial dated 4 November, and a card's failures listed before what no record decides. Its thumbnails are
now embedded in the page: one artifact version holds at most 512 files, and the 99 trials' meshes and renders
came to 525.

What the run shows about the format: DeepSeek left the person's own parts out of its hardware list, so nothing
required it to place them and six checks couldn't read its design. Requiring every own part in an assembly
task's hardware is a follow-up.

## 2026-11-04: Estoa light task: the box behind the disk, and an optional `assembly` in the format

A new task, `tasks/estoa-light/`, from Estoa, Dan's wall light: the box that sits behind an LED disk, holds
the perfboard with its ESP32, takes a USB-C charger straight into the ESP32's own port, and hangs on two wall
screws. No model was called for this change and nothing under `results/` changed. The request is drafted from
Dan's answers on the review page, and he approved the final wording on 2026-11-04.

- **`assembly`, optional and per task.** A design can now say where each printed part, each of the
  person's own parts and each screw goes in the finished piece (`pbe/parts/submission.py`). Only a task
  whose `format.yaml` asks for it gets the field in submit_design's schema, where it's required. Every
  other task's schema, prompt and saved submissions are unchanged: the tool lists and opening messages
  for m5-spacer, tripod-plate, bearing-wheel and nut-knob/M5, in `can_ask` and `all_given`, are
  byte-identical to the branch this starts from (compared before and after the change), and a
  submission without an assembly saves without the key. An `assembly` a model sends to a task that
  didn't ask for it is dropped, as any unknown field was before.
- **The person's own parts, per task.** `format.yaml`'s `own_hardware` lists them in that task's prompt
  only, as `own:<id>` references with the frame each is placed by and none of its dimensions.
- **Seven checks** in `pbe/graders/enclosure.py`, reading the piece through `pbe/graders/placed.py`: R1
  a screw through each of the disk's holes goes into the box wherever Dan's readings put the hole (C1);
  R2 the disk's screws hold and don't bottom out or reach the ESP32 (C3); R3 a plug reaches the ESP32's
  port from outside (C5); R4 inserts sit in posts like those that held (C3); R5 the perfboard is inside
  and the ESP32 has room (C5); R6 keyholes that run up (C7); R7 nothing proud of the back (C5). Every
  limit's record is in the brief's table; three are labelled estimates. `enclosure.post_screws`, a check
  for screws through a board into posts, stays in the module for a later task.
- **R3, refined with Dan:** it passes only the printed 14 x 8.5 mm opening, and fails only like the
  record: no roomier than 11.5 x 8.5 mm, 4 mm or more out from the port (Estoa's tunnel ended 4 mm short
  of this ESP32's port), where the plug's boot stops and its bare metal can't reach. A small opening right
  at the port is not graded. The USB-C spec's largest boot (12.35 x 6.5 mm, possibly 12.85 x 7.0) is in a
  new `catalog/connectors.yaml` to explain the gap, read through a search summary because usb.org is
  blocked from cloud sessions; it isn't a pass mark, and models don't see it.
- **A design that tests first passes too** (Dan), as the nut pockets do: R1 if a template or test print
  checks the disk's hole pattern and one of its params moves the box's holes (Estoa placed them from a
  printout, and they fit); R3 if a test print the manual uses has an opening of 14 x 8.5 mm or more in a
  wall at least as thick as the final one, and a param moves the final opening's width. Each param is
  checked by changing it and rebuilding. Inserts get no such path: no test print of an insert was made.
- **Dan's answers on the review page** (2026-11-04) changed the first draft: the USB-C breakout is gone,
  and the charger plugs straight into the ESP32 ("ignore the USB-C breakout for the simplicity of this
  task"); the request says there are two holes that the datasheet doesn't show; there's no glass: the
  front and sides are transparent PLA and the back box matte white, and the request still asks only for
  the box; it names M3 screws for the disk, because R1 and R2 grade an M3 and a review of the wording
  found the request never said so; four wires run from the perfboard to the disk. With the
  breakout went its check on screws bottoming out in blind inserts; the plug check moved to the ESP32's
  port, where the 11.5 mm record actually happened.
- `hidden_facts.yaml` holds only Dan's readings from the facts relayed on issue 17, each with its
  session and time, plus values from the Estoa model labelled as such. What he never measured (the disk's
  diameter and thickness, the perfboard's thickness) answers "I can't measure that".

Evidence:
- The reference (`reference.yaml`, a two-part CadQuery box) passes all 15 findings: the 7 checks and each part's build, connectedness, bed fit and bridges.
- `tests/test_estoa_light.py`: versions of the real Estoa mistakes each fail only the check aimed at
  them: an 11.5 mm USB opening set back from the port (R3), keyholes pointing down (R6), the disk's holes
  guessed 30 mm apart with no template (R1), 7.5 mm insert posts (R4), an M3 x 20 that reaches the ESP32
  (R2), screw heads on the back (R7). Reward hacks fail: boards declared outside the box, a disk floating
  in front, no keyholes, a port declared inside the wall. Designs unlike the reference pass, two of them by
  testing first. The cases between records come back not graded.
- Writing the tests found three faults, all fixed before commit: an early reference layout put a screw
  inside a corner post; R4 read a 3.6 mm clearance hole as an insert's (its band now starts at 3.9 mm,
  above M3's coarse clearance of 3.6 in ISO 273); and R4, reading an insert in a post standing free in the
  box, took the post's own hole for part of the cavity. The shared `sections.holes()` had the same
  pattern; it was fixed on its own in the stack below this branch.
- From a Linux cloud session, with parts built under bubblewrap and no `PBE_NO_SANDBOX`, on main
  at c064fe4: the full suite passes, 403 passed and 55 skipped, every skip a Docker variant of the
  run_python and build-on-submit tests (no Docker daemon in the VM; their bubblewrap versions pass).
  `tests/test_estoa_light.py` alone: 47 passed, in under 3 minutes on 4 cores. Every `--reference` passes:
  m5-spacer, tripod-plate, bearing-wheel, nut-knob M3, M5 and M8, and estoa-light (15 of 15). CI gets a
  job for the new tests and estoa-light in its reference loop.
- Codex's two findings on `enclosure.py`, both confirmed and fixed with a test each that fails before the fix:
  R2 now counts thread only as deep as the plastic around the hole (an insert behind a pocket that leaves
  2.5 mm of plastic fails; 3.5 mm passes), and R5's clearance over the ESP32 reads the disk as well as the
  printed parts (a window in the front with the disk 11 mm above the perfboard fails). The reference's
  verdicts don't move. `tests/test_estoa_light.py`: 50 passed.

## 2026-11-06: The person tells a model the clamp takes 38 mm plates

Asked about the clamp's width, the person in `tripod-plate` now says "38 mm (the width of plate it takes)" (`tasks/tripod-plate/hidden_facts.yaml`, `tripod_clamp.plate_width`). Dan's call, 2026-11-06: answer with the standard. Arca-Swiss-style plates are 38 mm wide with a 45° dovetail, per the vendor pages he was shown (Leofoto QP-38, Benro, Neewer; no official Arca-Swiss datasheet), and the 38 mm plate he printed fit this clamp. Only the width is given, not the angle.
- No saved trial changes: hidden facts are read only while a trial runs. Saved trials answer the width with the clamp's style alone, so new tripod runs aren't comparable with saved ones on R2 or on declining. GPT-6.1 Sol declined all 7 of its tripod trials because the width wasn't recorded.
- It was added after the tripod test-print sample below, so the replays continue conversations with the answers their first turn had. A replay now rebuilds its person from the saved trial's `hidden` list (`coupon_loop.facts_as_saved`), so resuming `loop-tripod`, for example to run Argon `can_run_code` t3's missing neutral arm, keeps the old answers too (Codex's review of PR 51). `tests/test_loop.py` checks it.
- `tests/test_tripod_plate.py` checks the answer: the width when asked, everything recorded when nothing is named, and not the width when only the kind of clamp is asked.

## 2026-11-06: R3 accepts a drill-out layer the manual says to clear

`PLAN.md` says a drill-out layer passes, and the knob's bolt path already allowed one, but the tripod's bolt-hole reader (`bolted._bores`) followed only holes open in every layer. Opus 5.5's printed-arm design in the tripod test-print sample closes the slot with a 0.4 to 0.6 mm skin, and its manual says "From the top face, run a hobby knife round the inside of the slot and push the skin out". R3 failed it with "no hole runs through the plate".
- `bolted._bores` now lets up to `nuts.MAX_DRILL_OUT` (3 layers) of closed layers through when the manual says to clear them (`nuts.sentence_saying_to_clear_it`, made public). R3's detail then quotes the sentence, and R4 and R5 read the same bore.
- `nuts.OPENS_A_HOLE` also accepts "push, cut, knock, pop or punch ... out" when its object is a skin, layer, membrane, film, web or diaphragm, so "push the bolt out of the hole" still doesn't count. It's a text match, and the check quotes the sentence it matched.
- **Evidence nothing else moved:** the tripod, knob and wheel runs regraded on a copy leave every `summary.csv` unchanged. 10 `grades.json` files differ in detail text only: tied bridge directions mirrored (the platform difference the README notes), and one knob's unscored pocket list in another order. Of the 71 records in `loop-tripod`, only Opus t3's printed arm changes, from fail R3 to pass.
- **Tests:** `tests/test_tripod_plate.py` covers a 0.4 mm skin the manual says to clear (passes R3, R4 and R5), the same skin with no instruction (fails R3) and a 1.0 mm floor (fails R3). `tests/test_nut_knob.py` adds Opus's sentence and three lookalikes.

## 2026-11-06: The test-print loop on the tripod: a printed plate, 24 holed roofs

Dan's real loop on Estoa and the Arca plate was to print it, look and fix it. The holed roof, the most common tripod failure (24 of 62 trials), is what that loop caught. Dan approved three things on 2026-11-06:
- the person prints the final plate too, not only the model's coupons;
- the reply's wording, which names no cause or fix;
- the spend.

The rule for what counts as improving was pushed before the run (fda7554). Code: `coupon_loop.plate_report` and `printed_text`, and `scripts/coupon_loop.py --run loop-tripod`, whose `tripod_sample` picks the trials. A `can_run_code` trial keeps `run_python` and its 20 calls in the second turn. Tests in `tests/test_loop.py`. Full write-up: `docs/coupon-loop.md`, "Tripod sample".
- **Sample:** every saved tripod design whose final part fails on a holed roof: 24 trials from 8 models.
- **Arms:** the printed reply, or the neutral "take another look". Run `loop-tripod`.
- **Cost:** $3.03, against a $3.00 cap and a $1.30 to $2.65 estimate. It stopped before Argon `can_run_code` t3's neutral arm.
- **Roofs fixed:** 14 of 24 after the printed reply, and 2 of 23 after the neutral turn. Over the 23 matched trials that's 13 against 2.
- **Whole-trial passes:** 3 against 2, or 4 against 2 once R3 accepts Opus t3's drill-out layer (entry above). Most fixed roofs still fail where they failed at baseline: the dovetail upside down, or straight sides.
- **How they fixed it:**
  - 8 flipped the plate so nothing bridges;
  - 3 put a cone where the flat roof was;
  - 2 used the stepped bridge the Estoa model invented after its test wall failed (Gemini 4 Argon t2 and `can_run_code` t3);
  - 1 left a skin to push out (Opus t3).
- **Opus t2 used a two-step roof** that the check still fails. That's unmeasured, and recorded in the write-up.
- **Got worse:** 4 printed-arm designs, 3 of them real, and no neutral one.
- **Hints:** none. Every reply said only "loose loops and tangles around the hole; hole partly closed", the words coupon A's H cell was recorded in, and `tests/test_loop.py` checks the reply names no technique.

## 2026-11-06: A failed bridge check is a holed roof only when the mesh shows a hole

`scripts/results_page.py` labelled every `bridges` failure "a roof with the bolt's hole cut through it", and `scripts/results_table.py` counted every trial that fails on `bridges` alone as resting on the holed-roof assumption. Two saved designs fail `bridges` without a holed roof. No verdict changes: the bridge check's pass, fail or not graded is untouched.
- **The test (`bridges.is_holed_roof`).** An overhang is a holed roof when it fails the strand test, isn't a narrow ledge, and at least 1 mm of its outline runs along a hole its own layer encloses. `overhangs` records the last part as `borders_hole`. The coupon loop's narrower test (a ring inside the roof) would have missed a roof cut in two by a slot. It would also have counted a ledge with something supporting its middle. `pbe/runner/coupon_loop.py` keeps its own test unchanged, because both of its samples ran with it.
- **The results page** works out each trial's holed parts from the rebuilt meshes. A failure on any other part is "A roof or ledge too wide to bridge, with no hole through it", a real failure (the strand test is backed by coupon C's cantilever) rather than Dan's call.
- **Labels that change, over every saved run:**
  - DeepSeek V4 Pro, `pilot-code` tripod t2: now a roof or ledge, not a holed roof. Its roof is a half-disc open to the plate's edge, plus side ledges (previous entry).
  - Gemini 4 Argon, `pilot-nut-knob` M5 t2: now a roof or ledge. The underside of its 30 mm grip overhangs the 16 mm boss below, and 0% of strands are anchored. The ring test read the boss under it as a hole.
  - GPT-6 Luna, `pilot-tripod` t3, keeps its holed-roof label (and its audit note), now from the mesh. A 6 mm slot cuts its recess roof in two, so the roof has no ring inside it.
- **README.** The tripod table keeps 24 holed roofs. The knob table goes from 2 to 1, with the grip ledge on its own row. The assumption row (`results_table.py`) now counts 22 trials that fail on `bridges` alone on a holed roof, down from 23. `NOT_HOLED_ROOFS` lists Argon's knob with its reason, so the README check stays fast.
- **Tests.** `tests/test_bridges.py` covers a ring hole, a slot cutting a roof in two, a closed roof, a 60 × 70 mm roof and a plate stepping out. `tests/test_results_page.py` checks the page's two labels on meshes with known answers. `tests/test_results_table.py` rebuilds each of the 23 trials that fail on `bridges` alone and checks that only the listed one isn't a holed roof (about 35 s with xdist; skipped where parts can't be built).

## 2026-11-06: Two more `can_run_code` tripod trials per lineup model (issue 34)

Pilot data. With one `can_run_code` trial per model, fewer code designs had a holed roof (1 of 4, against 12 of 19 without code). These trials test whether that holds. Dan approved the run on 2026-11-06 against an estimate of about $2.30. No check, task wording, prompt or earlier trial changes: `git diff` on `results/` shows only 12 new trial folders and 12 added `pilot-code/summary.csv` rows.

**The run.** `pbe.eval --run pilot-code --condition can_run_code --task tripod-plate --trials 3 --budget 4.00` on the six lineup models, in bubblewrap 0.9.0 with the default 20 turns. Each t1 was already saved and was skipped, so this added t2 and t3. The 12 new trials cost $1.39: Argon $0.63, Opus $0.32, Sonnet $0.24, DeepSeek V4 Pro $0.11, Sol $0.09 and Haiku $0.01. That brings `pilot-code` to $2.55.
- New verdicts: 1 pass, 7 fail, 1 not graded and 3 declined. The pass is Gemini 4 Argon's t2.
- No design was sent back for a build error. In all 18 `can_run_code` trials, `build_on_submit` has nothing sent back, nothing accepted unbuilt and no trial out of turns while fixing.
- DeepSeek V4 Pro didn't repeat t1's cost. Its t2 and t3 used 115,000 and 69,000 prompt tokens (t1 used 404,000) and cost $0.084 and $0.027. Its three code trials average $0.17, 10 times its `can_ask` mean of $0.017. Haiku never called `run_python` in any of its three trials, and Sol called it in two of three.

**Code against no code, per model.** The no-code trials are `can_ask` in `pilot-tripod` (t1 to t3) and `all_given` in `pilot-tripod-given` (DeepSeek V4 Pro has no `all_given` trial). Holed roof means the verdict fails `bridges`, and a final part rebuilt from `submission.yaml` has a failing, non-narrow overhang with a hole through it. That's the test `coupon_loop.roof_lines` uses.

| model | `can_run_code` t1, t2, t3 | holed roofs, with code | `can_ask` t1, t2, t3; `all_given` | holed roofs, without code |
|---|---|---|---|---|
| Haiku 5.5 | declined, declined, fail (`bridges` R2) | 1 of 1 design | fail, fail, fail; fail | 4 of 4 |
| DeepSeek V4 Pro | fail (R5), fail (`bridges` R3 R4), not graded | 0 of 3 | fail, fail, fail; none | 1 of 3 |
| GPT-6.1 Sol | declined, declined, declined | no design | declined ×3; declined | no design |
| Sonnet 5.5 | fail (R3) ×3 | 0 of 3 | fail, fail, fail; not graded | 3 of 4 |
| Gemini 4 Argon | fail (`bridges`), pass, fail (`bridges`) | 2 of 3 | pass, fail, pass; pass | 1 of 4 |
| Opus 5.5 | pass, fail (R3), fail (`bridges`) | 1 of 3 | fail, fail, fail; fail | 3 of 4 |
| **all** | 2 pass of 18 | **4 of 13** | 3 pass of 23 | **12 of 19** |

- The gap held, at a smaller size: 4 of 13 code designs (31%) have a holed roof, against 12 of 19 without code (63%). Fisher's exact test gives p = 0.15 on those counts, and designs from one model aren't independent, so it's a hint, not a finding. Most of the gap is Sonnet: none of its three code plates has a holed roof, but all three have the dovetail upside down (R3 on the narrow face). Argon goes the other way, with 2 holed roofs in 3 against 1 in 4.
- Passes are about the same: 2 of 18 with code (Opus t1, Argon t2) and 3 of 23 without (all Argon).
- One more code design fails `bridges` without a holed roof: DeepSeek t2, a geometry slip. Its bolt hole and head recess are centred on the plate's edge (the plate spans y = -55 to 0 mm and the cuts sit at y = 0), so half of each is off the plate (R3 reads 3.30 mm clear). The roof over the recess is a half-disc open to the outside, and the plate steps from 30 to 40 mm wide at z = 3 mm, which leaves 5 × 55 mm ledges along its sides. The next entry gives this its own label on the results page.

The README's results tables are regenerated (`scripts/results_table.py --write`): 163 trials, 47 pass, 71 fail, 35 not graded, 10 declined. The tripod's "What went wrong" table (now 62 trials), the tripod rows of "What wasn't graded" and the `can_run_code` lines are updated by hand from `results_page.issues_of` over the three tripod runs. The script's counts on the earlier 50 trials matched the old table.

Commit stamps: the new trials are stamped `26963c3` (Haiku's) or with work-in-progress commits on this branch that add only saved trials. This PR's squashed commit replaces them.

## 2026-11-06: Slicer estimates: a trial's parts sliced together, and presets found beside any install (codex review)

A Codex review of #52 and #53 found two problems, both checked before fixing.
- **Totals were sums of parts sliced alone.** Slicing four wheel trials' final parts together took 27 to 80 s less (3 to 8%) than the sum, with the same filament: the PLA preset slows any layer under 4 s to let it cool, and several parts on a plate share each layer's time. `scripts/slice_estimates.py` now slices each trial's final parts together on one plate and its test prints on another, and the trial's totals come from those plates. Part rows are unchanged (still each part alone). A new `plate_error` column says why a plate didn't slice; none failed. On the five runs, 25 trials with several final parts drop 1 to 10% (median 4.5%) and 2 with several test prints drop 4 and 15%; filament moves at most 0.05 g. No verdict changes.
- **`BAMBU_STUDIO` pointing at the program failed.** The presets folder was always looked for inside a `.app`. It's now found beside the program (macOS, or a `resources` folder on Linux and Windows), also when the program is named by a relative path such as `./bambu-studio` or sits at the file system's root (later Codex reviews caught both), or named with `BAMBU_STUDIO_PROFILES`.
- **Parts that don't fit on one bed** (a third Codex review): the slicer moves them to `plate_2.gcode` and on with no error, and only plate 1 was read. Every plate is now added up, and a new `plates` column counts them. Checked with two 180 mm boxes, which landed on 2 plates. No trial on these runs spills (29 need 1 plate, 76 need 2).
- Slicing again showed part times vary by up to 3 s between runs (18 of 231 parts), not 1 s; the doc says so.

## 2026-11-06: Slicer estimates leave out the printer's start and end sequences

Dan: the X1C's start-up (homing, nozzle cleaning, calibration, purge line) depends on the printer, not the design, so it shouldn't count. `scripts/slice_estimates.py` now empties the machine preset's `machine_start_gcode` and `machine_end_gcode` before slicing, and drops the `total_s` columns that carried about 7 minutes of start per plate. The per-trial columns are now `final_print_s`, `test_print_s` and `all_print_s`. The estimates for the five runs are regenerated.
- Against the first version, each sliced part's `print_s` moved by a median −11 s (−19 to +15 s; the increases are all on parts over 12 minutes, at most 1%), and `filament_g` fell by 0.32 to 0.33 g, the purge line. Layer counts are unchanged, and the same 231 of 252 parts sliced.
- New reading: a test print adds a median 4 to 7 minutes per task. The doc's earlier "about 0.2 g" for the purge came from one cube sliced before the presets were fully resolved; it is 0.32 to 0.33 g on every part.
- `tests/test_slice_estimates.py` tests that only the start and end G-code are emptied.

## 2026-11-06: Slicer estimates of print time and filament per design

The README asks which model reaches a working print fastest and with the least material, and nothing was sliced. `scripts/slice_estimates.py` rebuilds each saved design's parts as the results page does and slices each one offline with Bambu Studio's command line (02.08.02.61, installed here), using the setup Dan's test prints used: X1 Carbon 0.4 nozzle, 0.20mm Standard @BBL X1C, Generic PLA High Speed @BBL X1C. It writes `slice_estimates_parts.csv` and `slice_estimates.csv` beside each run's `summary.csv`. These are slicer estimates, not measured prints; no verdict, `grades.json` or `summary.csv` changes, and nothing talks to a printer. Method, research into other options and limits: `docs/slice-estimates.md`.
- **Presets resolved in full.** Loaded as they are, Bambu's stock presets slice with filament density 0 (every part 0 g), because the command line doesn't follow `inherits`. The script writes each preset out with its parents and `include` templates. The resolved machine preset matches a project Dan saved from the app on 2026-10-14 setting for setting, start G-code included; the process preset differs only in number formatting.
- **Run on** `pilot-tripod`, `pilot-tripod-given`, `pilot-nut-knob`, `pilot-nut-knob-2` and `pilot-wheel`: 119 trials, 252 parts, 231 sliced. The 21 not sliced are parts whose code doesn't build, each matching its saved verdict. Slicing `pilot-tripod` twice gave the same grams for every part and times within 1 s.
- **First reading:** each plate carries about 7 minutes of start sequence, so for these small parts a test print adds a median 12 to 14 minutes before the final part, 1.5 to 2 times the final part's own time.
- `tests/test_slice_estimates.py`: reading the G-code header, resolving presets, per-trial totals (blank when a part didn't slice), and a 20 mm cube sliced end to end where Bambu Studio is installed.

## 2026-11-05: M3 at +0.1 counts as holding, from Dan's memory of the print; 3 trials and 2 replays per sample now pass

Dan, reviewing Gemini 4 Argon's M3 knob, on the print noted "really struggles to go in": "it was very hard to put in, but i could put it in", and "with force it goes in". `nuts.READ_AS` now reads that size as holding, which replaces Claude's earlier call that it was unsettled. The print record stays word for word. Nobody recorded turning it over, so that part is Claude's reading: it's tighter than +0.2, which holds.

- **Saved trials, 3 verdicts change, all in `pilot-nut-knob-2`:** Sonnet 5.5's M3 t2 and t3 and DeepSeek V4.1 Flash's M3 t1 go from not graded to pass, each because its test print has a pocket that now holds. Haiku's M3 t1 stays a fail, with R4 no longer among its not graded checks. Totals: 46 pass, 64 fail, 34 not graded, 7 declined.
- **Coupon loop:** the M3 replays were regraded in both samples. Sonnet's 5.60 and DeepSeek's 5.65 feedback designs now pass, so each sample's feedback arm passes 3 of 12 against the neutral arm's 1. Before this it was 1 of 12 each. `docs/coupon-loop.md` is corrected.
- Gemini 4 Argon's two M3 knobs at +0.05 stay not graded, between +0.0 and +0.1.

## 2026-11-05: The fit checks say why a test print doesn't rescue a design

"No test coupon in the manual would catch it" was wrong on designs whose test print would show the size is wrong, such as Sonnet's M3 knob t1: its one 5.50 mm pocket wouldn't take the nut, so printing it finds the problem. Dan raised this while reviewing that verdict. R3 and R4 now say what's true: no test print in the manual, no size known to hold, or no param to apply the size with. The rule stays, and `docs/limitations.md` lists it as an assumption: at most 2 trials would change if it were relaxed. No verdict changes: regrading the knob and wheel runs left every `summary.csv` unchanged, and 31 saved trials took the new text, with the earlier text under `regrades`. The coupon loop samples keep the old wording.

## 2026-11-05: The seat reader catches small crush ribs; no saved verdict changes

`pbe/graders/wheel.py`, `_is_round`: a seat was plain if its area was within 6% (`PLAIN`) of its clear circle's. Crush ribs 0.2 mm high add only 3.4%, so a ribbed 22.2 mm seat read as a plain 21.8 mm one, the circle its ribs touch, and failed R3 as too tight. Ribbed seats aren't in the records (round 2 printed plain seats only), so they should be not graded. Now a seat is plain only if, as well, its widest span is within 0.1 mm (`RIBS_MM`) of its clear circle. A plain printed seat reads within 0.01 mm.

Found by reading the game spinner's first look (issue 41, PR 44): Sonnet 5.5's 22.2 mm seat with six 0.2 mm ribs was failed at 21.80 mm. Gemini 4 Argon's 0.12 mm ribs (2.1% more area) would have read the same way, but there a tall boss hid the seat first.

Evidence:
- `tests/test_bearing_wheel.py`, a new test: a 22.2 mm seat with six 0.2 mm ribs is not graded on R3. It fails before this change and passes after.
- Sonnet 5.5's saved first-look design: `wheel.fit` gave fail ("21.80 mm: a 22.0 mm seat wouldn't take the bearing") before and not graded ("ribs, lobes or a slot in the seat") after.
- A regrade of all 153 saved trials under `results/runs/`, on scratch copies with the base code and with this change, gave identical `grades.json` in all 153: no verdict, finding or detail moves, because no saved design has ribs this small. Nothing under `results/` changes.
- `uv run pytest` and every `--reference`: see the PR.

Scoring walk (`docs/scoring.md` and section 5 of the eval design guide):
- Real-world relevance: crush ribs are a common way to press-fit a bearing; a model drew them unprompted.
- Task design: unchanged.
- Grader reliability: one false fail removed, with a test that fails before the change. Weak: the 0.1 mm threshold is a reading of printed-seat geometry, not of a print.
- Evidence of model limitations: unchanged; this changes no saved verdict.
- Reproducibility: unchanged.
- Human expertise and review: Claude found and fixed it; Dan approved making it a follow-on PR.
- Insight: a check that reads shapes needs a test for the smallest version of each feature it means to catch.

## 2026-11-04: The lineup at 3 runs on the `can_ask` pilot tasks, and the first `can_run_code` trials (issue 34)

Pilot data: one to three trials per model, task and condition. The code these runs used merged as #39. No check, task wording, prompt or saved trial changes.

**`can_ask` top-up.** `scripts/top_up.py --cap 4.00` gave each lineup model (Haiku 5.5, DeepSeek V4 Pro, GPT-6.1 Sol, Sonnet 5.5, Gemini 4 Argon, Opus 5.5) 3 trials on m5-spacer, nut-knob/M3, nut-knob/M5 and bearing-wheel, counting the saved ones. tripod-plate already had 3 each. That made 40 new trials in `pilot-spacer`, `pilot-nut-knob`, `pilot-nut-knob-2` (DeepSeek's M5 and every M3) and `pilot-wheel`, for $2.75, against a $2.60 estimate made before caching. `git diff` on `results/runs/` showed only new trial folders and 40 added `summary.csv` rows.
- New trials: 14 pass, 11 fail, 15 not graded, 0 declined. m5-spacer 12 pass; nut-knob/M3 4 fail and 6 not graded; nut-knob/M5 2 pass, 3 fail and 7 not graded; bearing-wheel 4 fail and 2 not graded.
- Every not graded is a gap in the print records, reported as a limitation (`docs/limitations.md`). R4 accounts for 12: pockets with ribs, clips or relief (6), plain M3 pockets at +0.05 between the printed +0.0 and +0.1 (3), and plain M5 pockets 0.2 to 0.3 under the nut (2). `bridges` accounts for 3 (ledges of 32 to 157 mm²), and one bearing-wheel trial has a 22.04 mm seat and an 8.20 mm bore that no print measured.
- Caching worked. Each Claude model read 57 to 69% of its prompt tokens from the cache. Against each model's own earlier cost per trial on the same tasks, Haiku's new trials cost 54% less, Sonnet's 15% and Opus's 12%. Sol's and Argon's, whose caching didn't change, cost 7 to 9% less, so for Sonnet and Opus the saving is within trial-to-trial variation: output tokens are most of the cost.
- DeepSeek V4 Pro (served by Wafer) wrote until the 32,000-token output limit in 3 of its 4 new nut-knob trials, repeating "I'll write it now. Done. Final." It submitted on the next turn each time. Those trials cost about $0.16 each, against its usual $0.01.

**`can_run_code` pilot.** A smoke test (`pilot-code-smoke`: Haiku on m5-spacer, pass, $0.0023), then one trial per lineup model on tripod-plate (`pilot-code`), in bubblewrap 0.9.0 with the default 20 turns. Together they cost $1.16 against a $6 cap.

| model | verdict | turns | run_python calls | cost | its `can_ask` tripod trials | their mean cost |
|---|---|---|---|---|---|---|
| Haiku 5.5 | declined (only a test print) | 8 | 0 | $0.006 | 3 fail | $0.008 |
| GPT-6.1 Sol | declined (only a test print) | 9 | 1 | $0.080 | 3 declined | $0.083 |
| Sonnet 5.5 | fail (R3) | 5 | 1 | $0.140 | 3 fail | $0.140 |
| Opus 5.5 | pass | 7 | 3 | $0.255 | 3 fail | $0.225 |
| Gemini 4 Argon | fail (`bridges`) | 10 | 5 | $0.275 | 2 pass, 1 fail | $0.154 |
| DeepSeek V4 Pro | fail (R5) | 11 | 6 | $0.404 | 3 fail | $0.017 |

- No design was sent back for a build error: every part built when first handed in.
- Cost grows with code runs, because each run's output stays in the conversation. DeepSeek's prompt grew from 5,500 to 75,000 tokens over 11 turns, and two of its turns wrote 25,600 and 16,900 tokens, so it cost 24 times its `can_ask` mean. Sonnet, Sol, Haiku and Opus cost within 0.7 to 1.1 times theirs, and Argon 1.8 times.
- Projected cost of 3 `can_run_code` runs per lineup model on the same five tasks, from these single trials: $17 if every trial costs what its model's tripod trial did, $23 if each model's `can_ask` cost on every task is scaled by its tripod ratio. DeepSeek alone is $6 to $15 of that, the rest $8 to $11. One trial per model is a weak basis, so treat it as a range, not an estimate to budget to.

Two tests had frozen the set of saved trials, so they're narrowed to what they were written for. `tests/test_build_on_submit.py` now expects `build_on_submit` in exactly the `can_run_code` records, not in none. `tests/test_crash_replay.py` compares the replay's fixed list (issue 27) with the crashes saved before issue 34, because three new DeepSeek trials fail `builds`. The replay's list is unchanged: those three are new crashes, not part of it.

The README's results table is regenerated (`scripts/results_table.py --write`). It counts `pilot-code-smoke` as a `can_run_code` trial, because it's an ordinary graded trial, not a cloud machine check like `cloud-smoke`.

Commit stamps: the trials are stamped with commits on `claude/caching-pilot` from `492575a` to `2289969`, the branch head when each was saved. The commits after `492575a` add only saved trials and scripts. None of them is on `main`: #39 and this PR's squashed commit replace them. Their `pbe/`, `catalog/`, `pyproject.toml` and `uv.lock` match #39's, and `tasks/` differs only by the Estoa datasheet from #22, which these runs don't use. #42 later changed `pbe/eval.py` only in how `summarize` treats a run with no trials and in a `--runs-dir` flag, neither of which touches grading.

## 2026-11-04: The submission ZIP, and machine-local citations rewritten (issue 6)

No verdict changes, no model calls, and the prompt models see is byte-identical (checked by hashing the hardware list, the setup facts and a request before and after).
- **`scripts/build_submission.py <ref>`** packages the files tracked at a git ref into a ZIP written outside the repo, with README.md at its root. It writes nothing, and exits 1 with every reason, if the ZIP would be 50 MB or more, or has no README.md at its root, or holds a video, `docs/context/`, `.git`, a secret (API keys, AWS and GitHub tokens, private keys, bearer tokens) or a machine-local path (home folders, LAN and tailnet addresses). Image metadata isn't checked: Dan said EXIF is fine. `tests/test_build_submission.py` has a test for each refusal and for lookalikes that must pass (an `sk-` inside an encrypted blob, a three-part version number), and builds a ZIP from the commit under test.
- **Left out of the ZIP**, each with its reason in `LEFT_OUT`: `docs/context/` (private), the two overnight logs (whether they ship is Dan's call, issue 36; `docs/overnight-runs.md` names the home network), `report/atlas/` (it builds only on Dan's Mac from local photos), and the Estoa datasheet (estoa-public doesn't ship the vendor's drawing either; fetch it from Adafruit, product 2477, at setup).
- **Citations rewritten to name the source** instead of a local path or a file in `docs/context/`: `PLAN.md`, `CLAUDE.md`, `CHANGELOG.md` (one line), `docs/lessons.md`, `docs/limitations.md`, the three seed files' headers, `tasks/tripod-plate/brief.md` (a provenance note, not the request), and comments or unread fields in `catalog/printer.yaml` and `catalog/hardware.yaml`. Nothing under `docs/context/` or `results/` was edited.

## 2026-11-04: README rewritten to match `main`; results from a script; regrading a replay run keeps its summary (issues 35, 32)

No verdict changes and no model calls.
- **README** rewritten from the saved runs and the repo (issue 35): how to run everything from a clean clone without a key, each step's expected result and time on a clean Ubuntu 24.04 container, the tasks and their wording status, how grading works, the limits, what's built and what isn't, a map to the guide's folders, provenance and AI use. Claims about things that don't exist (the hidden-error printer score, design for assembly, a hand ranking, the assembly simulation) are gone. The parts only Dan can write are marked `TODO(Dan):`.
- **Results from a script.** `scripts/results_table.py` writes the README's results (pass, fail, not graded, declined and cost per task, condition and model) and the counts behind the three leading assumptions, from every `grades.json` under `results/runs/` (smoke tests left out). `tests/test_results_table.py` fails when the README and the saved runs disagree, so CI catches drift. Counts on `main`: 104 trials, 27 pass, 50 fail, 22 not graded, 5 declined, the same as the issue 15 regrade.
- **`scripts/reproduce.sh`** runs install, tests, every reference, a regrade of every saved trial on a copy (comparing each run's `summary.csv`), the results page and the README check.
- **`--runs-dir`** lets `pbe.eval --regrade` work on a copy of `results/runs/`.
- **Issue 32:** `summarize` leaves a run's `summary.csv` alone when the run has no `grades.json` (the crash replay and the two test-print loop samples), so `--regrade` no longer wipes it. Test: `test_regrading_a_run_without_grades_keeps_its_own_summary`.
- "Test print" replaces generic "coupon" in `PLAN.md`, `docs/limitations.md`, `docs/scoring.md` and `docs/lessons.md`. Names keep the old word (coupon A, the coupon loop, `role: coupon`), and `docs/coupon-loop.md` is left as written, since it records measures committed before its runs.
## 2026-11-04: Prompt caching for Claude models (issue 34)

Every saved Claude call showed 0% cached, because `pbe/runner/llm.py` never asked for it. Most other providers cache on their own, so the saved runs compared Claude's uncached cost with everyone else's cached cost.

- `llm.caching_params(model)`: calls to `anthropic/` models only get OpenRouter's top-level `cache_control: {"type": "ephemeral"}`, its "automatic caching" (its prompt-caching docs, read 2026-11-04). It's one field on the request, so the messages and tools stay byte-identical to what every other model gets. The 5-minute default TTL suits these trials, since every saved Claude turn came back in under 75 s. In `can_run_code`, a reply whose `run_python` calls run past 5 minutes would make the next turn miss the cache and write it again. That costs more, but changes nothing the model reads.
- Each trial saved from now on records `settings.prompt_caching` (true or false). Records saved earlier have no such field and load as before. The provider's `cached_tokens` and `cache_write_tokens` were already saved in each call's `usage`; `ModelCall` now reads them as `cached_tokens` and `cache_write_tokens`, alongside `prompt_tokens`.
- Only `pbe.runner.agent.run_trial` asks for caching. The coupon loop and crash replay call `llm.chat` without it, as before.
- New scripts: `scripts/caching_check.py` (the check below), `scripts/top_up.py` (tops the `can_ask` pilot runs up to 3 trials per lineup model and task, cheapest model first, under one spending cap across the run folders; it never changes a saved trial, retries one that ended in an infrastructure error, and stops on an out-of-credit HTTP 402) and `scripts/cost_report.py` (per model, from saved trials only: verdicts, cost per trial and per turn, and the cached and written shares of prompt tokens).

Evidence:
- `tests/test_caching.py`, 14 passed: in every condition, Haiku 5.5 and each of GPT-6.1 Sol, Gemini 4 Argon and DeepSeek V4 Pro get the same messages and tools, byte for byte, over a three-turn scripted trial. The request body posted to OpenRouter differs only by `model` and the top-level `cache_control`. Only Claude models ask for caching.
- The rest of the suite, apart from the three slow task files CI runs on their own: 206 passed and 55 skipped (the Docker-container variants of the sandbox tests, since there's no Docker daemon in this session; the bwrap variants ran).
- `results/caching-check/anthropic__claude-haiku-5.5.json`: the m5-spacer opening request sent twice to Haiku 5.5, served by Claude Platform on AWS (the provider behind every saved Claude call). Call 1: 6,738 prompt tokens, 0 cached, 6,734 written, $0.00099. Call 2: 6,734 cached, 0 written, $0.00022.
- The check, and the issue 34 trials run from `claude/caching-pilot`, are stamped with commits on that branch from `492575a` on: a trial's stamp is the branch head when it was saved, and the commits after `492575a` add only saved trials and scripts. None of those commits will be on `main`, because this squashed commit replaces them. Their `pbe/`, `catalog/`, `pyproject.toml` and `uv.lock` are identical to this commit's. `tasks/` differs only by `tasks/estoa-light/files/datasheet.png`, from #22, which none of those runs uses.

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
- `seeds/estoa-failures.yaml` (34 seeds: 22 failed, 11 near-miss, 1 unconfirmed) and `seeds/side-project-failures.yaml` (8: a lamp mount and a Gridfinity organizer). Mined from 37 agent-session transcripts in Dan's private session archive by four reader agents. Eight key quotes were checked against the transcripts by hand, and all matched.
- Evidence: the most common class across all three projects is C1, designing from unmeasured dimensions (12 of 52 seeds, by primary class). In both the tripod and Estoa, the agent asked for measurements only after a failed print.

## Repo created
- README, PLAN, the first task (`tasks/phone-stand/`), the seed failure list, and stub catalogs. No grader or runner code yet.
- Source notes copied from the explorations KB into `docs/context/`.
