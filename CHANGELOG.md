# Changelog

Each entry: what changed, why, and the evidence (a run, a failure, a measurement).

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
