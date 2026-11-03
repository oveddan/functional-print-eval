# Limitations and future work

What each check and test can and can't claim, and how it could be extended. The report's limitations section draws from this file. One section per check.

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
