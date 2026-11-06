# Coupon loop: letting a model learn from its test print

Status: built and tested on two samples of 12 knob and wheel trials, and on 24 tripod plates where the person prints the plate itself (results at the end of this file). Decided by Dan on 2026-11-03, with the changes a second review asked for (issue 15). The second sample stopped part way when the OpenRouter account ran out of credit and was finished once Dan added more. An illustrated version of the review is at https://claude.ai/artifact/Xt9j8NAaA46ASA2e9gJ6BJ, and every replay is on the results page, https://claude.ai/artifact/8FoztxxrwV6ioveQhz8gY6.

**Correction, 2026-11-05: the report gained 2 passes in each sample.** Dan said of the M3 +0.1 print, "it was very hard to put in, but i could put it in" and "with force it goes in", so that size now counts as holding. Sonnet's 5.60 and DeepSeek V4.1 Flash's 5.65 M3 knobs now pass. Each sample's feedback arm passes 3 of 12 trials against the neutral arm's 1. This is still a small sample of 12 trials, replayed twice, and those two passes rest on one print Dan called very hard. The M3 replays were regraded; the results below are updated to match.

## The idea

Today `submit_design` ends the conversation, so a model never hears how its test coupon would have come out. With the loop, when a model hands in a design with coupons:

1. The eval builds each coupon and reads its features: nut pockets, bearing seats, holed roofs.
2. It replies as the person would, from the recorded prints only. For example: "5.50 pocket: does not go in. 5.70 pocket: goes in with pushing, snug. Held."
3. The model gets one more turn to revise and resubmit.
4. Both designs are graded (Dan: "grade both").

Nobody prints anything. Every reply comes from `results/predictions/` and the bridge check.

## Rules

**What the reply can say**
- Nut pockets and bearing seats: only plain ones, at a size that was printed. The reply quotes the recorded note word for word, with no explanation of the cause.
- A row nobody turned upside down (coupon B's "loose" rows) is reported as "loose, didn't check upside down", never as held or fell out.
- No guessing between printed sizes. A size between two records gets "didn't print that size".
- Holed roofs: when the bridge check predicts a holed roof will tangle, the reply says so in cell H's recorded words ("loose loops and tangles around the hole; hole partly closed"). A roof it predicts will print cleanly isn't mentioned. That's how both samples ran; reporting clean roofs too would be a change to make before a later sample, not after. It agreed with both holed roofs on record (the Arca plate and coupon A's H cell), and every model roof seen so far lies between those two. The results mark each roof answer "predicted by the bridge check", because no print backs that exact shape.
- Everything else: "didn't print that". That includes clamp-fit gauges, plate widths other than 38 mm, ribbed pockets and seats outside 22.0 to 22.3.
- The model may always resubmit unchanged.
- Dan reviews the reply template as text.

**Grading**
- Turn 1 is the headline and doesn't change. Its tool text still says the design ends the conversation, so models don't design differently expecting a second turn.
- Turn 2 is its own condition, "after test prints", with its own pass^k. The better of the two turns is never the score.
- Trials with no coupon get no second turn, and their turn 1 grade carries over. That rewards planning a coupon (class C8) without a special rule.
- In turn 2 the coupon counts as printed, so the coupon credit in `nut.fit` and `wheel.fit` switches off: the final part has to land on a size that held. Otherwise a design that already passed on its coupon would show a gain of zero by construction.
- Turn 2 is graded by the same checks. For roofs that means the same check that wrote the reply. That's accepted: a model that steps the roof or flips the part passes.

**Control**
- A matched set of trials gets a neutral second turn instead: "take another look and resubmit if you want". The gain from feedback minus the gain from the neutral turn is what the test print taught.

**What to report beside the grades**
- the share of trials with a coupon;
- the share of coupon features the records could answer;
- how many answered features were fixed, and how many designs got worse.

## Order

| Step | Cost | What it tells us |
|---|---|---|
| Count, over the saved runs, how often a coupon tests what its final part failed | $0 | Whether the loop can help at all. Roofs: 4 of the 31 trials whose final part fails `bridges` had a coupon with the same roof; 19 had a coupon that tested something else, 8 had none. Nut pockets and bearing seats not counted yet |
| Replay a sample first: three models' saved knob and wheel trials with coupons (Sonnet 5.5, DeepSeek V4.1 Flash, GLM 5.3 Flash; 12 trials), each replayed twice, once with the feedback reply and once with the neutral one | About $0.40 to $0.80 | Whether the replies, the feature matching and the grading work, before spending more. Fix the method, then expand |
| Expand the replay to every model's knob and wheel trials with coupons | About $2 to $4.50 more | How much a test print teaches, per model |
| Fresh runs with the loop, three trials each | Several times that | Pass^k after test prints |

The cost estimates assume a replay costs 30 to 60% of the original trial (the reviewer's estimate: the conversation is resent and a new design written), doubled for the two replies. The three sample models were picked because they're cheap and their coupons cover what the records can answer: nut pockets (Sonnet's and DeepSeek's M3 coupons), bearing seats, and one coupon with the same holed roof as its wheel (GLM t1). $8.74 of the $9.00 limit is spent and the account has $10 of credit, so even the sample needs the limit raised.

Limits of the loop are in `docs/limitations.md`.

## Sample run: what counts as improving, written before the run

Written 2026-11-03, before any model call for the loop, and committed before the run so the rule can't be fitted to the outcome. Evidence, since the squash merge keeps only the final commit: this section was in commit 7b30192 on the PR branch (2026-11-03 21:17 UTC), pushed before the run; every replay record in `results/runs/loop-sample/` names 7b30192 as its code version, and the first was saved a minute later. 7b30192 is still reachable on GitHub by its hash.

**Trials.** Every saved knob and wheel trial with a test coupon from Sonnet 5.5, DeepSeek V4.1 Flash and GLM 5.3 Flash: 12 trials (`scripts/coupon_loop.py` lists them). Each one is replayed from its saved conversation twice: once with the feedback reply, once with the neutral one. Saved in `results/runs/loop-sample/`.

**Three grades per trial, all with coupons left out** (the coupon counts as printed, so its credit is off):
- *baseline*: the saved turn 1 design;
- *feedback*: the design after the coupon report;
- *neutral*: the design after "take another look".

**Primary measure.** Trials that pass every check: feedback against neutral. The loop improves results on this sample if the feedback arm passes more trials than the neutral arm and doesn't break more trials that passed at baseline.

**Secondary measure.** For each trial whose report answered something from a record or the bridge check, whether the check that feature bears on (R4 for nut pockets, R3 for seats, `bridges` for roofs) went from not passing at baseline to passing, in each arm.

**What it can't show.** 12 trials, one replay per arm, provider-default sampling: a difference of one or two trials could be chance. A positive sample result is a reason to expand to every model, not proof. Every count and every reply is reported, including trials that got worse.

## Sample run: result

Run 2026-11-03, $0.98 for 24 replays, all 12 trials complete. Every record is in `results/runs/loop-sample/` (`summary.csv` has one row per trial). The replays ran on the code at commit 7b30192, before the restack onto the refactor. Their records were then converted to `loop.json`, and the restacked code reproduces every report word for word and every verdict.

**Primary measure: the report gained 2 passes on this sample.** The feedback arm passes 3 of 12 trials and the neutral arm 1. All of them pass Sonnet 5.5's M5 knob, which already passed, and neither second turn broke it. The 2 gained are the M3 knobs from Sonnet 5.5 and DeepSeek V4.1 Flash (see the correction above).

**Secondary measure: one fix, from the report.** Five trials got a report line from a record or the bridge check that bears on a check they weren't passing:

| Trial | The report said | Feedback | Neutral |
|---|---|---|---|
| DeepSeek V4.1 Flash, wheel t2 | "22.19 mm seat: goes in; holds upside down." | **R3 fixed**: seat 21.89 → 22.18 mm. Still fails `bridges` | Unchanged, R3 fails |
| Sonnet 5.5, M3 knob | "5.50 mm pocket: does not go in." | Moved to 5.60 ("really struggles", which goes in with force): passes | Moved to a ribbed 4.90 pocket: not graded |
| DeepSeek V4.1 Flash, M3 knob | "5.50 mm pocket: does not go in." "5.60 mm pocket: really struggles to go in." | Moved to 5.65, between two sizes that hold: passes | Pocket unchanged at 5.42 (knob made shorter): R4 fails |
| GLM 5.3 Flash, wheel t1 | "21.99 mm seat: won't go in." "The roof over the pocket: loose loops and tangles around the hole; hole partly closed." (the check's prediction) | No design: all three calls hit the 32,000-token limit while reasoning | Unchanged |
| GLM 5.3 Flash, wheel t2 | "22.09 mm seat: goes in, pretty snug; holds upside down." | Unchanged, not graded | Worse: fails `bridges` and R3 |

**Why there was so little to work with.**
- In 5 of 12 trials every line of the report was "I can't tell you how that one came out": coupons with ribbed pockets, sizes nobody printed, and coupons that test something no record covers. In 2 more (Sonnet's wheels) the only answer was about a seat that already passed, not the roof that failed. 23 of the report's 32 lines rest on no record.
- The wheels failing `bridges` mostly had coupons without the roof, so the report couldn't mention it. Only GLM's wheel t1 had the roof in its coupon, and that replay produced no design.
- The report was stricter than the grader. A pocket or seat tighter than one recorded as "won't go in" got "I can't tell you", although the checks count it as won't go in. That hid information in 4 trials (DeepSeek's M3 and both wheels, GLM's M3).
- The 32,000-token limit stopped calls in 4 arms (DeepSeek's M3 neutral and M5 feedback, GLM's wheel t1 feedback and wheel t2 neutral). Only GLM's wheel t1 ended with no design.

**What it shows.** On this sample the loop doesn't improve results by the rule set before the run. Where the report gave a usable size, one model in three applied it correctly. Two moved in the right direction but not far enough to land on a size that held. The bottleneck is the eval's records and the report's rules, more than the models.

**Before expanding to every model:**
1. Answer sizes tighter than a "won't go in" record as won't go in, as the checks already do.
2. Raise the second turn's token limit or turn count, or count a run of length-limited calls as an infrastructure stop rather than "no design".
3. Accept that knob coupons with ribs, and most tripod coupons, will stay unanswered until more prints exist (`docs/limitations.md`, "With a printer").
4. Run the next sample on those changes, with the measures fixed in advance again.

## Second sample: what counts as improving, written before the run

Written 2026-11-04, before any model call for it, and committed before the run. Dan approved the two changes. Evidence: this section was in commit a46c56f on the PR branch (2026-11-04 10:43 UTC), pushed before the run, and the run's first replay record was saved a minute later. The records name a46c56f's successors (7e70285, c9a601d, ad08a07), because each record stamps the branch head when it's saved and the branch was amended during the run to commit records as they came in; every one of those commits contains this section unchanged. a46c56f is still reachable on GitHub by its hash.

**What changed from the first sample.** Nothing else changes: the same 12 trials and models, the same reply wording, and the same grading with coupons left out.
1. A pocket or seat tighter than the tightest printed size gets "won't go in", if that printed size wouldn't take the nut or bearing (M3 at +0.0, the 22.0 mm seat). The checks already read it that way. Its basis is "tighter than a record".
2. The second turn gets up to 8 model calls instead of 3, as many as a whole first turn. The token limit stays at 32,000 per call, as in every first turn. If a second turn ends with no design and every one of its calls stopped at the token limit, its outcome is `token_limit`. That outcome is reported apart from pass and fail, in both arms.

**Trials.** The same 12 as the first sample, replayed afresh from their saved first turns, in both arms. Saved in `results/runs/loop-sample-2/`. The first sample's records stay as they are.

**Measures.** The same as the first sample.
- Primary: trials that pass every check, feedback against neutral. The loop improves results on this sample if the feedback arm passes more trials than the neutral arm and doesn't break more trials that passed at baseline.
- Secondary: for each trial whose report answered something from a record, a tighter size or the bridge check, whether the check that feature bears on went from not passing at baseline to passing, in each arm.
- `token_limit` trials count as not passing in the primary measure, as any trial without a design does. Their number is reported for each arm.

**What it can't show.** It's still 12 trials with one replay per arm. Because the replays are fresh, trials whose report didn't change also show how much a second replay varies by chance. Report every count, including trials that got worse and how they differ from the first sample.

## Second sample: status, 2026-11-04

**Stopped part way: the OpenRouter account ran out of credit.** 7 of 12 trials have both arms. The other 5 ended in HTTP 402 ("requires more credits") on every arm: Sonnet 5.5's three trials, DeepSeek V4.1 Flash's wheel t2 and GLM 5.3 Flash's wheel t2. Those are infrastructure stops, not results. `scripts/coupon_loop.py` re-runs exactly those arms once credit is added. $0.42 was spent before the stop.

No result is drawn until all 12 are done. Among the 7 that finished, the feedback arm changed two wheels and the neutral arm changed none:
- **DeepSeek V4.1 Flash, wheel t1:** told its four coupon seats, 21.69 to 21.94 mm, won't go in (all four from the new "tighter than a record" rule), it moved its seat from 21.84 to 22.19 mm. R3 now passes; `bridges` still fails.
- **GLM 5.3 Flash, wheel t1:** told its 21.99 seat won't go in and its roof's strands tangle (the check's prediction), it fixed the roof, so `bridges` passes, and moved the seat to 22.04, between printed sizes, so R3 is not graded. Its first call hit the token limit; with up to 8 calls it went on to submit.

**Why the trials still fail** (each trial's latest design, both samples, read from the saved records):
- *The records can't decide* (5 trials, all not graded): GLM's M5 knob (ribbed pocket), DeepSeek's M5 knob (a pocket 0.15 mm under the nut, where the tightest print, +0.0, held), DeepSeek's M3 knob (5.65 mm, between printed sizes), GLM's wheel t1 (a 22.04 mm seat, between printed sizes) and GLM's wheel t2 (a ribbed seat in a bore with no shoulder).
- *The coupon didn't test what failed* (4): Sonnet's and DeepSeek's wheels fail `bridges` on the roof over the bearing seat, and their coupons had only a seat.
- *The report had nothing to say* (1): GLM's M3 knob, whose coupon pockets all have ribs.
- *Sonnet's M3 knob* (1): told 5.50 doesn't go in, it chose 5.60, recorded as "really struggles". This was counted as not going far enough until the 2026-11-05 correction above; it now passes.
- *Passes* (1): Sonnet's M5 knob.

So only 3 of the 11 failing trials could turn into a pass from anything the report can say, and the pass count can barely move on this sample whatever the models do. Checks fixed is the more sensitive measure here. A larger test should choose trials whose coupon tests the feature that failed. Changing the measure for a future sample is Dan's call, and would be written down before that run.

## Second sample: result

Finished 2026-11-04 once credit was added: all 12 trials, both arms, $1.03 in all. The 10 arms that had stopped on the credit error were re-run; nothing else was. Records in `results/runs/loop-sample-2/`.

**Primary measure: the report gained 2 passes on this sample.** The feedback arm passes 3 of 12 trials and the neutral arm 1, the same Sonnet 5.5 M5 knob that already passed in every arm. Neither second turn broke it. This matches the first sample.

**Secondary measure: the report fixed 3 checks; "take another look" fixed none and made 2 trials worse.**

| Trial | The report said | After the report | After a second look |
|---|---|---|---|
| DeepSeek V4.1 Flash, wheel t1 | Its four seats, 21.69 to 21.94 mm: "won't go in" (all tighter than a record) | **R3 fixed**: seat 21.84 → 22.19 mm. Still fails `bridges` | Unchanged |
| DeepSeek V4.1 Flash, wheel t2 | 21.59 to 21.89: "won't go in" (tighter than a record); 22.04: no record; 22.19: "goes in; holds upside down" | **R3 fixed**: seat → 22.19 mm, as in the first sample. Still fails `bridges` | Unchanged |
| GLM 5.3 Flash, wheel t1 | 21.99: "won't go in"; the roof: "loose loops and tangles around the hole" (the check's prediction) | **`bridges` fixed**; seat moved to 22.04, between printed sizes, so R3 is not graded | Unchanged |
| Sonnet 5.5, M3 knob | 5.50: "does not go in" | Moved to 5.60, "really struggles", which goes in with force: passes (the same move as in the first sample) | Unchanged at 5.50 |
| DeepSeek V4.1 Flash, M3 knob | 5.30 and 5.40: "won't go in"; 5.50: "does not go in"; 5.60: "really struggles to go in" | Moved to 5.65, between two sizes that hold: passes | Unchanged, R4 fails |
| GLM 5.3 Flash, wheel t2 | 22.09: "goes in, pretty snug; holds upside down" | Unchanged, not graded | **Worse**: seat 21.97, R3 fails |
| Sonnet 5.5, wheel t1 | 22.09: "goes in, pretty snug; holds upside down" (a seat that already passed) | Unchanged | **Worse**: room for only one bearing, R2 fails |

**The two fixes worked as intended.** 8 second turns had a call stop at the 32,000-token limit; with up to 8 calls, every one went on to hand in a design, and no turn ended `token_limit`. GLM's wheel t1, lost to the limit in the first sample, fixed its roof. The "tighter than a record" answers are what DeepSeek's wheel t1 acted on.

**What the two samples show together.** Across both samples, 6 trials got a usable size or the roof's outcome in the report. In 5 the model moved the right way, and in all 5 it fixed the check (Sonnet's and DeepSeek's M3 pockets, DeepSeek's two wheel seats, GLM's roof). GLM's wheel t2 didn't change. No neutral turn fixed a check, and neutral turns made a design worse three times. The M3 knobs are the 2 passes gained in each sample. The other fixes leave the trial failing elsewhere: the DeepSeek wheels still have a holed roof their coupon never tested, and GLM's seat landed between printed sizes.

**For a larger run (Dan's call, written down before it runs):** count checks fixed as the main measure, choose trials whose coupon tests the feature that failed, and add models beyond these three.

## Tripod sample: printing the final plate, written before the run

Written 2026-11-06, before any model call for this sample, and pushed before the run, so the rule can't be fitted to the outcome. Every replay record in `results/runs/loop-tripod/` names the commit it ran from.

**Why.** This is the loop Dan actually ran. In Estoa (session 602ba611, 2026-10-02), a screw hole through a bridged roof printed closed on the test wall, and the model then proposed the stepped (sacrificial) hole. Dan didn't know the technique before it did. On the tripod (session c941d075, 2026-10-12), the first Arca plate's holed roof printed as a tangle, and the second plate, with a stepped roof, worked. In the eval, 24 saved tripod designs fail on a holed roof, but only 4 of the 31 tripod trials failing `bridges` had a coupon with that roof, so the coupon report can't reach most of them. Dan approved three things on 2026-11-06: the person prints the final part too; the reply's wording; and the spend.

**What the reply says.** After the saved first turn, the person prints everything in the design and replies from the records only. It never names a cause or a fix (`coupon_loop.plate_report`, `printed_text`):
- Coupons: as in the samples above (`coupon_report`).
- The clamp: "it fits" only for a plate that passes R2 within 0.5 mm of 38 mm, the one width printed. Otherwise "I can't tell you how that one came out."
- The bolt's head: "it fits in its recess" where R4 passes (15 x 5 mm or more fit), "it didn't fit in its recess" where R4 fails (13 mm or less didn't), otherwise "I can't tell you".
- A holed roof (`bridges.is_holed_roof`): "the roof the hole goes through: loose loops and tangles around the hole; hole partly closed." The words are coupon A's H cell, the same as the coupon report, marked as the bridge check's prediction. A roof the check passes isn't mentioned.
- It ends: "Send me the design again with submit_design, changed or unchanged, and I'll print it again from what you send."

**Sample.** Every saved tripod trial (`pilot-tripod`, `pilot-tripod-given`, `pilot-code`) whose final part fails `bridges` on a holed roof: 24 trials from 8 models (Haiku 5, Opus 4, Sonnet 3, DeepSeek V4.1 Flash 3, Gemini 4 Argon 3, GPT-6 Luna 3, GLM 2, DeepSeek V4 Pro 1), 4 of them `can_run_code`. Qwen's `all_given` t1 is left out: its `bridges` failure is a broken shape (`BROKEN_ROOFS`). Selection is code (`scripts/coupon_loop.py`, `tripod_sample`).

**Arms.** Each trial is replayed twice: the printed reply above, and the neutral "take another look" turn the earlier samples used. A second turn gets as many calls as the trial's first turn had: 8, or 20 for `can_run_code`, which keeps `run_python` and the build on submit. Its working folder starts fresh, so files written in turn 1 aren't there. The person answers measurements as in the saved trial; the clamp-width answer Dan approved on 2026-11-06 is added only after this run, so the replays don't change two things at once. Budget: $3.00 for the run (estimated $1.30 to $2.65).

**What counts as improving.**
- **Main measure: roofs fixed.** For each arm, how many of the 24 turn-2 designs pass `bridges` on every final part. A turn with no design counts as not fixed. The loop's effect is the printed arm's count minus the neutral arm's.
- **Secondary: whole-trial verdicts.** For each arm, pass, fail, not graded and no design, against the baseline (every trial fails at baseline).
- **Got worse:** a check that passed at baseline and fails in turn 2, counted per arm.
- **How a roof was fixed,** read from the turn-2 design: stepped or sacrificial layers, a closed roof drilled out after printing, a flipped part, a roof removed, or something else. This is a reading of the design and its notes, labelled as such, not a check.

**What it can't show.** 24 trials, one replay per arm, provider-default sampling: a difference of one or two trials could be chance. The bridge check grades the fix to the roof it predicted, and only one stepped roof has been printed (the second Arca plate), so a pass is the check's call, not a print's. The trials are designs that already failed, so the result says what a failed print teaches, not how often a first design fails.

## Tripod sample: result

Run `loop-tripod`, 2026-11-06, from fda7554 (the rule above, pushed before the first model call). It stopped at the $3.00 budget after spending $3.03: 23 trials got both arms, and Gemini 4 Argon's `can_run_code` t3 got only the printed arm. Its neutral arm ran later the same day, from 8c1a4f8, with the person cut back to the facts its first turn had (`coupon_loop.facts_as_saved`). It cost $0.14, bringing the run to $3.16: $1.74 on the printed arm and $1.43 on the neutral one. The estimate was $1.30 to $2.65; the `can_run_code` turns, with up to 20 calls, cost more than the 30 to 60% of a first turn the estimate assumed. Every replay is in `results/runs/loop-tripod/`, with its reply, transcript, design and grades.

**Main measure: roofs fixed.** After the printed reply, 14 of 24 designs pass `bridges` on every final part. After the neutral turn, 2 of 24 do, so the printed reply fixed 12 more roofs than a second look. (Before Argon `can_run_code` t3's neutral arm ran, it was 14 of 24 against 2 of 23, or 13 against 2 on the 23 matched trials. That arm didn't fix its roof.)

**Secondary: whole-trial verdicts.** Every trial failed at baseline.

| Arm | Trials | Pass | Fail | Not graded | No design |
|---|---|---|---|---|---|
| Printed reply | 24 | 3 | 18 | 3 | 0 |
| Neutral turn | 24 | 2 | 22 | 0 | 0 |

The printed arm's passes are Sonnet 5.5 t2, Gemini 4 Argon t2 and Argon's `can_run_code` t1. The neutral arm's are Argon's `can_run_code` t1 (which passed both ways) and DeepSeek V4.1 Flash t1. Most fixed roofs still fail elsewhere, on what failed at baseline as well: the dovetail upside down (Sonnet t1 and t3, Luna's two) or straight sides (Haiku, GLM t3).

**Got worse:** 4 printed-arm designs and no neutral ones failed a check that passed at baseline.
- Gemini 4 Argon `can_run_code` t3 stepped its roof, but the revised plate lost the head's recess below it, so no hole runs through (R3).
- DeepSeek V4.1 Flash t1 came apart (`connected_bodies`).
- GPT-6 Luna t3 thickened its deck to carry a cone roof, so the bolt no longer reaches 3.81 mm into the camera (R5).
- Opus 5.5 t3 is a check's mistake, not the model's: see below.

**How the roofs were fixed** (a reading of each turn-2 design and its note, not a check). Of the 14:
- **8 flipped the plate** so the recess opens upward and nothing bridges: Sonnet t1, t2 and t3, Haiku `can_run_code` t3 and `all_given` t1, DeepSeek V4.1 Flash t2, GLM t3 and Argon `can_run_code` t1.
- **3 replaced the flat roof with a cone or funnel:** Luna t3 and `all_given` t1, and DeepSeek V4.1 Flash `all_given` t1.
- **2 stepped the roof** the way the Estoa model did (a slot, then a square, then the round hole): Argon t2 and `can_run_code` t3.
- **1 left a drill-out skin** and told the person to push it out: Opus t3.

One more tried the stepped roof and still fails the check: Opus t2 bridged "in two one-layer steps", with no square step. Its bolt slot's round ends sit in the second step, so 42% of the strands there end in the hole. Whether that would print is unmeasured. Coupon A's stepped hole printed with "a few loose strands near the hole" and counted as clean.

Every one of these came from the reply's single line about the roof ("loose loops and tangles around the hole; hole partly closed"), which names no cause or fix. Most turn-2 notes explain the cause correctly. GLM t3 wrote: "the through-hole sat in that bridged roof and got tangled".

**Two check findings, fixed after the run.**
- **R3 failed a drill-out layer.** Opus t3 closed the slot with a 0.4 to 0.6 mm skin, and its manual says to "push the skin out". `PLAN.md` says a drill-out layer passes, and the knob's bolt path already allowed one (`nuts.MAX_DRILL_OUT`, 3 layers, with a manual sentence saying to clear it). The tripod's bolt-hole reader didn't. `bolted._bores` now lets up to 3 closed layers through when the manual says to clear them, and `nuts.OPENS_A_HOLE` also accepts "push, cut, knock, pop or punch ... out" when the thing pushed out is a skin, layer, membrane, film, web or diaphragm. Graded again with the fix, Opus t3's printed arm passes every check, so the printed arm has 4 passes and 3 designs that got worse. No other arm in this run changes, and no saved trial's verdict changes (regrading the tripod, knob and wheel runs on a copy left every `summary.csv` the same). The numbers above are as the run graded them; `loop.json` keeps those grades.
- **The width the person gives.** Several turn-2 notes say the clamp's width is still a guess. The person now answers it (the next CHANGELOG entry), but only for runs after this one.

**What it shows, and what it can't.** In 24 matched trials, being told how the roof printed fixed 14 roofs, and a second look fixed 2. That's a large gap for a sample this size, but it's one replay per arm of trials chosen because they failed, graded by the same check that wrote the reply. It says that these models, told the outcome, nearly always know at least one fix for a holed roof. It doesn't say how often a first design avoids the problem: that's the main eval's 24 failures out of 62 tripod trials.
