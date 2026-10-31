# Plan

Read this first in a new session, then `docs/scoring.md` (the quality bar and method), `seeds/classes.yaml` (the general failure classes) with the seed files beside it, and `docs/context/INDEX.md`.

Elsewhere:
- Concept page (published): https://claude.ai/artifact/6oarQD2uJMVVzDVACoU9Xt
- Ground-truth project files (OpenSCAD, STLs, fit tests, manual pages): `~/Source/local-lights/private/phone_stand/` and `~/Source/local-lights/private/tripod_plate/` (gitignored there; `phone_stand/src/` is a third-party Pork3D model, so don't copy it here)
- Estoa, the second source of seeds: `~/Source/estoa-public/enclosure/` (TEST-PRINTS, FIXES, DECISIONS) and its agent sessions in `~/claude-archive` (session ids in `seeds/estoa-failures.yaml`)

## Goal

A rigorous, reproducible eval showing where frontier models fail at consumer mechanical design: a model draws a part, but does it know what it can't know before you print? Depth, grader reliability and a clear write-up come before breadth; `docs/scoring.md` is the bar.

**Deadline: one week from day 1.** The week is scoped to what one person with coding agents can finish well. Anything not in "This week" waits; cut breadth before rigor.

## The design

- **Failure classes drive the eval.** `seeds/classes.yaml` groups 56 real failures (tripod, Estoa, two side projects, the eval's own coupons) into ten task-independent classes. Tasks are chosen to exercise several classes, and results are reported by class. The most common class is C1, designing from unmeasured dimensions: in every project the agent guessed first and asked only after a failed print.
- **The submission format makes code grading possible:** a params block (every hardware and real-world dimension as a named input, with its source: measured, datasheet or guessed); CadQuery code per part built only from those params, with print and use orientation; a BOM from the hardware bin; a joint table (bolt, stacked parts and thicknesses, nut or insert position); manual steps naming their parts; typed acceptance criteria, each with how it's checked before the full print; the questions asked.
- **Assembly simulation is the core grader (Dan's idea).** It carries out the manual's steps on the real geometry, with real hardware (bolts with their partial thread, nuts, inserts, washers) and each insertion as a move along the part's axis. A step fails if a part collides before it seats, a bolt doesn't reach its nut with enough thread, or a part was already used. Fit and reach come out of one simulation instead of rules written from past failures. It's kinematic: no forces or friction.
- **Hardware-fit invariant (Dan's idea).** Every hardware-receiving feature must be derived from the hardware's named dimensions. A metamorphic check varies each hardware param, rebuilds and re-simulates: a feature that doesn't follow its input is hard-coded and flagged, so the verdict doesn't depend on the true measurement. Every fit also has an upper bound (oversized pockets let the nut fall out, the tripod's +0.3 mm).
- **Blind backtest.** Would the eval have known, from the design alone, that it would fail? Real designs as they stood before printing go through frozen graders with no knowledge of the outcome, scored in a 2x2 table against what happened. Controls are fixes that were built and worked (`control:` in the seed files); proposed fixes that were never built don't count. Hits that need a measurement the design guessed at are counted separately from hits found in the geometry.
- **Parametric task families.** One parametric reference per family (cite BenchCAD 2.0's part-family format, a build file plus a check file), so each variation gets its reference by changing parameters. Variations come from a small explicit dimension table per family (hardware, unknown dimension, use and load, the person's request including "impossible as specified"), stratified by failure class. Every family traces to a real seed.
- **What the model is told (Dan).** Setup facts are always given, because a model can't know them and they decide whether a design prints: printer, nozzle, filament, layer height, longest clean bridge, the hardware bin (`catalog/`). Techniques are not given in the main condition: stepped holes in bridges, teardrop holes, flipping a part, nut clearances are standard printing knowledge a designer should have, and a person at home won't explain them. Each task runs under these conditions:
  - **Base:** the brief and the setup facts.
  - **Design guide:** the same, plus a short guide naming the common techniques. Failing without it but passing with it is a knowledge gap; failing with it is a judgment gap (the model knows the technique but doesn't see when it applies). The Arca agent already knew stepped bridging from Estoa and still drew a plain roof, so judgment gaps are expected.
  - **Oracle:** all hidden facts given upfront. Passing only then means the failure was information gathering (C1); failing both means design skill.
  - **Checks as a tool (after the week):** the model can run the eval's checks on its own design before handing it in. Whether it uses them and fixes what they flag is another judgment signal.
- **Grade the outcome, not the technique.** A check never demands one specific fix. The bridge check asks whether every overhang will print, so stepped layers, flipping the part, declared supports, a drill-out layer or moving the feature all pass.
- **Grader reliability, shown three ways:** the backtest; a regression suite (references pass, real failed designs fail, simple reward-hacking attempts fail); and Dan's hand ranking of about 10 designs compared with the graders'. Dan is named as the task author and domain expert.

## This week

### Day 1 (afternoon): environment and the submission format
- A `uv` environment pinned to Python 3.12 (system Python is 3.15) with CadQuery, trimesh and pyyaml.
- The submission format as a schema with one worked example (the Arca plate fix).
- `catalog/hardware.yaml` from the ISO tables: thread lengths, head sizes, nuts, heat-set inserts.

### Day 2: runner and the pilot
- Runner: OpenRouter client, a scripted user that reveals hidden facts only when asked, transcripts and costs saved under `results/`.
- Geometry checks: code runs, one connected body per part, fits the bed's usable area.
- Pilot: the phone stand and the Arca plate, 4-5 models x 2 runs. Read every transcript. Go/no-go: do models repeat the seed classes, and can they produce the format at all? Report format failures separately from design failures.
- If the OpenRouter key isn't ready, swap Days 2 and 3.

### Day 3: the assembly simulation and the first backtest
- Hardware geometry from the catalog; insertion as axis moves with collision; bolt reach and thread engagement; tracking which parts are used.
- The metamorphic check.
- Backtest: the Arca plate (original and fix), then the tripod's partly threaded clamp screw and the fork-to-clamp M5x20. Rebuild the originals from the tripod session's edits.

### Day 4: three task families
- The Arca plate, the desk-clamp phone stand, and one mechanism family that leads toward the robot arm: a servo horn coupling (real hardware, a clear fit, Dan's Presence work).
- Each with a parametric reference, a dimension table, brief templates, hidden facts and requirements.
- The design guide: one page of common printing techniques, written so it names techniques without pointing at any task's answer.
- Second-coder check: an independent agent re-classifies the seeds blind; report agreement.
- Then revisit the classes with the pilot's failures and that agreement in hand. Known weak spots: C1 and C8 are about behavior (didn't ask, didn't plan a coupon) while the rest are about the design, so the report may group them separately; C2 and C5 overlap (both are "this doesn't fit that"); C10 is mostly outside code grading.

### Day 5: printability, regression suite, reward hacking
- Printability: minimum wall, holes through bridges without stepped layers, bed fit.
- Fit clearance against a fixed printer offset from `catalog/printer.yaml`'s observed fits (no Monte Carlo yet).
- The grader regression suite as one command, including two reward-hacking attempts: oversized pockets and undeclared hardware.

### Day 6: full run
- About 5 models x the family variations x 3 runs, under the base, design-guide and oracle conditions (on a subset for the last two if the budget is tight). Read failures by hand, fix graders, log each fix in `CHANGELOG.md`.
- Dan ranks about 10 designs by hand; compare with the graders.

### Day 7: report
- **A one-page summary a reviewer reads in five minutes:** the headline; two numbers (backtest hits and false alarms; how often models build on a guessed dimension instead of asking); the Arca plate before and after; failures by class; honest limitations (one person's projects, mostly one agent's mistakes, a kinematic simulation, small samples).
- Behind it: all-pass rate, pass^k, failures by class, cost per successful task, bootstrapped confidence intervals with paired comparisons (about 18 runs per model is a small sample; no claims on small differences), grader reliability.
- README: one command to reproduce, dependencies, versions, expected results, runtime and cost.

## After the week

Per-check limits and extensions are in `docs/limitations.md`; the report's limitations section draws from it. In rough order of value:
- The backtest on Estoa, from the `local-lights` git history (a commit before each test print).
- Tool access (driver, hex key, drill) and mating envelopes (plug overmold, cable bend) in the simulation.
- The hidden-error printer as a loop: a secret offset plus noise, scripted "falls out / too tight" feedback, Monte Carlo yield.
- Scoring acceptance-criteria coverage against the simulation's failures and the task author's list.
- More families from the full dimension tuples; robot-arm families (bearing seat, arm link, gripper finger).
- Builder agent (Dan's idea) and its personas.
- Strength: a hand-calculation check, then FEA (gmsh + CalculiX).
- Judge alignment, if any check needs an LLM judge.
- Physical work: the calibration coupon, the real hardware bin, filming the failed parts.

## Before publishing

No photo is committed, and nothing in the repo should point at a file that only exists on one machine. Run this list before the first push:

1. **Images stay out of git, and out of its history.** Deleting a photo from the tree is not enough: EXIF (capture date, GPS, camera) stays recoverable from the old blob, so any image ever committed has to be purged from history. The coupon and servo photos are hosted on R2 and indexed in `docs/media/photos.md`.
2. **Atlas assets** (`report/atlas/examples.yaml`) still point at 13 files on this machine: 7 Estoa HEICs in `~/Source/local-lights/private/photos/estoa/`, 3 tripod HEICs in `~/Downloads/`, 2 images from `estoa-public`, 2 phone-stand renders. Convert, scrub the metadata, upload to R2 and replace the paths with URLs — without committing the images. The `~/Downloads/` pointers go first: that folder is the least durable place a cited file could live.
3. **`docs/context/` is private source material.** Purge it from the tree before publishing, and rewrite its citations (`PLAN.md`, `catalog/printer.yaml`, `README.md`, `seeds/tripod-failures.yaml`) to name the source instead of a local path.
4. **Other machine-local pointers**: the ground-truth and Estoa paths above, the explorations-inbox filename in `catalog/hardware.yaml`, and the `~/claude-archive` session ids — those can stay as opaque provenance, but the README should say the archive is private.
5. **`IMG_5438`**, the caliper video behind the servo measurements, was never in the repo. Upload it or drop the citation.

## Constraints

- The eval is software. Physical prints are only for grounding the printer model, validation and the demo video.
- Code with no license (CADEngBench, the BenchCAD 2.0 harness): reimplement and cite, never copy. Read BenchCAD's LICENSE before reusing anything.
- Secrets: model API keys come from 1Password at run time and are never printed, echoed or committed.
- Models are called by API through OpenRouter, not through subscriptions, so runs log versions, settings and cost.

## Working method

- A cheaper model (Sonnet) writes code, then an adversarial Opus review. Verify claims yourself.
- Dan's own ideas for the eval are in `docs/context/2026-10-24-dan-3d-print-assembly-eval-idea-dictated.md`; the builder agent, physics/strength simulation, the assembly simulation, the hardware-fit invariant and the robot-arm direction are his. Credit what is his; don't present Claude's ideas as his.

## Decisions

Decided:
- CAD language: CadQuery (matches BenchCAD; install size is no concern, Dan). OpenSCAD stays available for the tripod's ground-truth files.
- Electronics out of scope (Dan). Enclosure geometry around electronic parts stays in.
- Commit straight to `main`.

Open (Dan's):
1. The OpenRouter key (Dan is setting one up) and its credit limit.
2. Is the printer available this week?
3. How "good design" is weighted in the score, after Dan ranks a first set of designs.
