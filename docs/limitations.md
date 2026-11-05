# Limitations and future work

What each check and test can and can't claim, and how it could be extended. The report's limitations section draws from this file. The first three sections cover the eval as a whole: where it falls short against the rubric it will be scored on, the assumptions today's verdicts rest on, and what a printer could settle. Then one section per check.

## Where the eval falls short, by rubric criterion

The rubric is the 100-point one in section 5 of the hackathon's eval design guide, "Find what AI can't do yet". The report's self-assessment names these shortcomings instead of awarding points.

| Criterion | Shortcoming |
|---|---|
| Real-world relevance | The tasks come from one person's projects and mostly one agent's mistakes. The bearing wheel's request is invented and Dan hasn't reviewed it. |
| Task design | The tripod's records have no clamp width, and the person answers every size question with the clamp's style. All 5 trials that declined trace to that. The 37 to 39 mm plate width and the 10 mm bolt length are assumptions, not records. |
| Grader reliability | An audit of the saved failures (issue 15, 2026-11-03) found no verdict that came from a check misreading the geometry. But many verdicts rest on one print per size, or on the bridge check's prediction for a shape nobody printed (see the next section). The audit found one reader bug: a raised feature anywhere above a nut pocket's mouth made the pocket read as closed, and the bolt's way through read as blocked. Both readers are fixed (2026-11-04); with M3 +0.1 read as unsettled, the fix flips one trial, DeepSeek V4.1 Flash's M3 knob, from fail to not graded (`CHANGELOG.md`). |
| Evidence of model limitations | One to three trials per model, so the runs are pilots, not pass rates. Models never see a build error, so a slip they'd fix in one retry counts as a failure. The coupon loop (`docs/coupon-loop.md`) gives a test-print result back, but only in a separate condition so far, tested on 12 trials. |
| Reproducibility | Every saved verdict reproduces on Linux as on macOS (106 trials). The detail text doesn't always: tied strand angles come out mirrored, and one part counts 9 bad overhangs instead of 13. The budget allowed only pilot runs. |
| Human expertise and review | Dan wrote the tasks from his own builds and decides every open call. Claude wrote the checks and reviewed them, and the audit is another reading by Claude, not an independent expert's. |
| Insight | Drawn from pilots. Holed roofs account for 32 of the 34 trials that fail `bridges`, and at least 5 of 44 tripod trials put the dovetail upside down, but the samples are small. |

## Assumptions today's verdicts rest on

Each row is something the eval treats as true without a print that shows it for that exact case. Until a record exists, the report states the assumption beside the result.

| Assumption | Check | What rests on it |
|---|---|---|
| A holed roof of any shape between 3.1 and 7.8 mm from its walls tangles, as the Arca plate's and coupon A's H cell did. The models' roofs are round and of other sizes; H is a 20 mm square with a 6 mm hole, printed once. | `bridges` | 17 trials fail on `bridges` alone (Dan, 2026-11-03: they fail, because the first plate's roof didn't work and the stepped roof is the known fix). The coupon loop answers roofs with this prediction too. |
| One print per nut clearance, from round 1. Round 2's finer steps (B2) were never printed. | R4 knob | Every knob fit verdict. |
| M3 at +0.1 is coded won't go in, but noted "really struggles to go in". Dan, 2026-11-05: "it was very hard to put in, but i could put it in" and "with force it goes in". So it counts as holding, from his memory of one print. Nobody recorded turning it over; it's tighter than +0.2, which holds (Claude's reading). The record is unchanged. | R4 knob | Sonnet 5.5's M3 knob t2 and t3 and DeepSeek V4.1 Flash's t1 pass because of a test print pocket at this size, and 2 test-print loop trials per sample pass. Gemini 4 Argon's M3 knobs (+0.05) stay not graded. |
| A test print only rescues a design if it includes a size known to hold and a param moves the final part to match. A test print that would only show the size is wrong earns nothing, even though a person would likely keep adjusting until one worked. This is a rule, not something a print showed (Claude's call, which Dan reviewed on 2026-11-05). | R3 wheel, R4 knob | 5 trials fail a fit check with a test print in their manual, and on 2 of them, Sonnet's M3 knob t1 and DeepSeek V4 Pro's M3 knob t3, it's the only failed check. |
| Coupon B's "loose" rows were never turned upside down, so they're not graded, except +0.3, which fails because nuts fell out there on the tripod build, in PETG. | R4 knob | M5 at +0.2 and M8 at +0.1 and +0.2 are not graded. |
| Bearing seats hold from 22.1 to 22.3 and 22.0 won't go in. Nothing between 22.0 and 22.1 or above 22.3 was printed. | R3 wheel | Seats outside that range are not graded. |
| One plate, 38 mm wide, fit the clamp. 37 to 39 passes on an estimate of the jaws' travel. | R2 tripod | Every plate width verdict. |
| The bolt is 10 mm long under its head. Nobody recorded it. | R5 tripod | Every reach verdict. |
| A ring-shaped roof narrower than 3 mm, such as a plain nut pocket opening at the bed, isn't graded, and anything within 1.5 mm of the layer below is an ordinary overhang. The 1.5 mm is a guess. | `bridges` | Plain M5 and M8 pockets opening at the bed are not graded; M3 passes on the 1.5 mm guess. |
| The slicer picks the best bridge direction. Coupon C's tunnel 1 shows it sometimes doesn't. | `bridges` | Roofs the check passes. |

## With a printer: more sources of truth

These prints would turn the assumptions above into records. The check counts are from the saved runs as of 2026-11-04: 19 trials end up not graded overall, 18 of them for want of one of these records. None is planned before publishing (Dan, 2026-10-30), so they're future work, and until then the report lists the rows above as assumptions or not graded.

| Print | What it settles |
|---|---|
| Round holed roofs at the models' sizes, plain and stepped: about Ø16 with a Ø6.8 hole, and Ø22 with a Ø8.4 hole | Whether the models' roofs really tangle, so `bridges` and the coupon loop's roof replies stop being predictions |
| Ring roofs 1.5 to 3 mm wide around a bolt hole | Plain nut pockets opening at the bed, and the 1.5 mm overhang guess |
| Coupon B2 (M3 +0.10 to +0.25, M5 +0.00 to +0.15, M8 and 1/4-20 -0.10 to +0.05) | Clearances between round 1's steps, including how much force +0.1 really takes |
| Coupon B turned upside down | The "loose" rows, which are not graded today |
| Bearing seats at 22.05, 22.4 and 22.5 mm, and lobed seats | Seats between and beyond the round 2 sizes, and seats with ribs or lobes (3 checks) |
| Dovetail plates at 34, 36, 37, 39, 40, 42 and 45 mm in the clamp | How far the clamp's jaws travel, so R2's width limits become records. Models' plates ranged from 33.8 to 45 mm (6 checks not graded) |
| Nut pockets with crush ribs, clips or relief beside plain ones | The largest single gap: 8 knob trials are not graded only because their pockets, or their test print's, have ribs. Each model's ribs differ, so one print settles only designs like it |
| M5 pockets at -0.15, -0.10 and -0.05 mm | Pockets under the nut's size, which round 1 never tried (3 checks) |
| Tripod head recesses 3, 4 and 4.5 mm deep for the 5 mm head | Recesses shallower than the one printed (8 checks) |
| Tripod bolt holes at 6.5 and 6.6 mm | Holes between 6.35 and 6.8 mm (5 checks) |
| Wheel bolt holes at 8.1, 8.2 and 8.3 mm on an M8 | Holes between 8.0 and the 8.4 mm clearance hole (5 checks) |
| Wheels whose bearings stand 0.2 to 0.6 mm proud, and a bore with no shoulder | Wheels slightly thinner than two bearings, and bores where only the press fit places them (4 checks) |
| The salvaged bolt, measured | The 10 mm length R5 assumes |
| Each test print printed three times | How much one setup varies print to print, so limits can be ranges |
| A slicer comparison (Bambu Studio's command line) | Which direction the slicer bridges, for the tunnel case |

With records like these, the coupon loop's replies would come from prints for most features instead of from "didn't print that" or the bridge check's prediction.

## Coupon loop (`docs/coupon-loop.md`)

- It can answer only plain pockets and seats at printed sizes or tighter than one that wouldn't go in, and roofs by the bridge check's prediction. Most tripod test prints test the clamp's fit, which no record covers, so they'd get "didn't print that".
- Of the 31 trials whose final part fails `bridges`, only 4 had a test print with the same roof, so for roofs the loop can help in few cases.
- One extra turn only (up to 8 calls), and the reply is a lookup, so it can't answer a follow-up question.
- Gains are measured against a neutral second turn on a matched set of trials. Without that, feedback and a second look can't be told apart.
- A roof answer and the grade of the revised roof come from the same check.
- Tested on two samples of the same 12 knob and wheel trials from three cheaper models (Sonnet 5.5, DeepSeek V4.1 Flash, GLM 5.3 Flash). Neither raised the pass rate (1 of 12 in every arm); the report fixed 3 checks in the second sample and a second look none. Too few trials and models to generalize.


## Bridge check (`pbe/graders/bridges.py`) and its test print (coupon A)

### What it claims

From a part's 3D file alone, the check predicts whether each bridged region (plastic laid over air) will print cleanly: in some direction, strands must land on solid plastic at both ends and stay within the printer's longest clean span. Coupon A tests that prediction against a real print, with the predictions committed before printing (`results/predictions/round1-coupons.yaml`).

### Constraints

- **Geometry only.** The check models where strands are anchored and how long they are. It knows nothing about the things that also decide how a bridge prints: nozzle size, layer height, material, cooling, bridge speed and flow, the slicer's bridge settings and the direction it picks, temperature and wet filament.
- **One setup.** The span limit is a property of a printer, nozzle, material and profile together, not of bridges in general. The first measurement is for one setup: a Bambu Lab X1C, Bambu's standard 0.2 mm profile, and whatever nozzle and filament the print used (recorded with the outcome). Predictions for any other setup are untested.
- **Starting thresholds are guesses.** 40 mm longest span, 95% of strands anchored, 1.5 mm small-overhang allowance (`catalog/printer.yaml`). Coupon A measures the first; the other two are untested.
- **The anchoring rule was written knowing one answer.** It was built after the Arca plate's tangled roof, so the Arca result isn't blind. Coupon A's plain-hole against stepped-hole pair is the first blind test of the rule, and it's one pair.
- **One print, one sample per feature.** No repeats, so no measure of how much the same roof varies print to print.
- **Judged by eye.** "Clean, sagging or tangled" is a person looking at the underside. There's no measured sag.
- **The stepped geometry assumes 0.2 mm layers** (two layers per step). At another layer height the steps no longer line up with layers.
- **It assumes the slicer picks the best direction.** The check passes a roof if any direction works. The slicer picks its own, and on coupon C's tunnel 1 (10 mm across, 76 mm long) the strands ran lengthwise and failed, on both prints (round 1 and, as C2, round 2). Tunnel 2 beside it, 0.4 mm taller with a step at the bed, bridged across and printed clean. A roof the check passes can still fail if the slicer bridges it the long way; why the slicer chose differently for the two isn't known yet.
- **It answers "can this be bridged", not "will it be accurate".** A bridge that prints cleanly still sags a little, which shrinks the space under it. That's a fit question for the printer model (failure class C2), not this check.

### Future work

- **More setups.** Reprint coupon A in PETG, with a 0.6 mm nozzle and at a 0.28 mm layer height, and store a span limit per setup in the printer profile. If the limits differ a lot, the eval states its predictions per setup.
- **Repeats.** Print each setup at least three times to see how much results vary, and report the limit as a range.
- **Measure, don't eyeball.** Measure the sag at mid-span with calipers or a depth gauge, or score photos against a fixed scale, so outcomes are numbers.
- **Cover the other thresholds.** Add roofs where only part of an edge is anchored, holes of several sizes, and narrow ledges, to test the 95% and 1.5 mm values.
- **Slicer as a second opinion.** This is now the top extension: coupon C's tunnel showed the slicer's bridge direction can differ from the best one. Slice with Bambu Studio's command line and compare where it lays bridge infill with what the check predicts.
- **Other designs.** Run the check blind on Estoa's sealed leg-pocket hole, from the `local-lights` git history, and on any new design before it's printed.
- **A model-facing task.** Show a model a part and ask which overhangs will print cleanly, scored against real prints. That tests whether a model understands printing, separately from whether it applies that when designing.
