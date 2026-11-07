# servo-arm with an assembly: plan

Status: plan only, nothing built or run. 2026-11-07. Answers "Assembly and motion: never tackled for mechanisms" (`docs/limitations.md` on `claude/magical-einstein-kg47qw`). Built on Dan's call of the same day: follow main's format as closely as possible, so `prompt.yaml` goes and its fields move into `format.yaml` (being done on `claude/servo-mount` and `claude/servo-arm`).

## What the first look says this has to handle

All 8 first-look submissions (`results/first-look/servo-arm-first-look`) were read for this:

| Design | Printed parts | 608 | Arm on |
|---|---|---|---|
| Haiku `all_given` | bracket, arm, post | in the arm, M8 bolt | horn pocket |
| Opus `all_given` | base, arm, bracket over the shaft | still bracket, coaxial, floats 1.5 mm | horn pocket + 8 mm stub |
| Haiku `can_ask` | plate, arm | not listed | bore |
| Opus `can_ask` | frame, bearing upright, arm (shaft horizontal) | still upright, coaxial, slots ±4 mm | horn pocket + pin |
| Sonnet `can_ask` | base, 2 straps over the tabs, arm | roller at the arm's tip | horn, M3 |
| DeepSeek `can_ask` | bracket, arm, pivot sleeve | in the arm, coaxial, on a still M8 axle (not listed) | printed spline |
| Gemini `can_ask` | base, bearing bridge, arm | still bridge, coaxial, slots in X and Z (not listed) | horn pocket, M3 |
| GPT `can_ask` (declined) | base, arm, horn keeper, bridge, ring | still bridge, coaxial | horn, keeper bolted to the arm |

Three things follow. A second support comes in two shapes (the 608 in a still part around a stub on the arm, or in the arm around a still axle). Some parts turn with the arm without being the arm (GPT's keeper). And `joints` can't say what turns: Gemini's and DeepSeek's pivot joints list the arm and the still part on one fastener.

**The servo frame doesn't remove the shaft estimate.** The design places the shaft where it thinks it is, but the mount holds the case, so on the real servo the shaft lands wherever 10.3 ±1 mm from the case end puts it (`catalog/datasheet_estimates.yaml`). The assembly buys three things: where every other part sits relative to the mount, which end and which way up the design means, and which parts turn. The ±1 mm stays in every check that needs the shaft.

## 1. format.yaml (prompt.yaml absorbed)

One `tasks/servo-arm/format.yaml`: `assembly: true`, `own_hardware` (below), `hardware_left_out: [servos]`, `datasheet`, `datasheet_line`. Two small additions, both gated so every other task's prompt and tools stay byte-identical (`tests/test_prompt_rule.py`, estoa included):

- `OwnPart.optional: bool | None = None`. `_own_parts_missing` skips optional parts. `own_parts_text` already drops `None`, so estoa's list prints as before.
- `TaskFormat.turning: bool = False`. When it's true, `_design_schema` adds `turns_with` to `PartPlacement`: "the id of one of their own parts in `hardware` whose frame's +z this part turns about, with it, such as the servo; leave it out for parts that stay still". The field defaults to `None` and is dropped from `dump()` when it's empty, so saved estoa submissions don't change. This is the one thing main lacks: a joint that moves, given as an axis (the servo's frame) and the parts on it. The range is the requirement's 120°, not something the design states.

## 2. own_hardware (draft wording, for Dan)

```yaml
own_hardware:
  - id: mg996r
    kind: servo
    description: "their MG996R servo"
    frame: "origin where the output shaft's centre line meets the top of the case (the face the shaft comes out of); +z out along the shaft; +x along the case's length, towards the end farther from the shaft"
  - id: horn
    kind: horn
    optional: true
    description: "the 25-tooth aluminium single-arm horn they bought for the MG996R; its holes are threaded for M3"
    frame: "origin at the centre of the hub's face that sits towards the servo; +z out along the shaft, away from the servo; +x along the horn's arm, towards its tip"
```

- **Origin at the case top, not the spline's tip** (a change from the proposal): with it the case and tabs are exact in the servo frame from Dan's readings (body, `tab_to_top`, `tab_t`), apart from the ±1 mm, and only the spline's height is uncertain. A tip origin would put the 0–10 mm band on the case itself, so every overlap check would carry it.
- **Leak:** "the end farther from the shaft" tells a `can_ask` model the shaft is off-centre, which `shaft_position` makes a question today (Sonnet and Gemini asked it). The horn's line tells it the horn exists (all 8 asked about the horns anyway). Its readings stay in `hidden_facts.yaml`, which also gets "threaded for M3" in the `horns` note.
- **The 608 gets no frame.** Its seat already says where it is: R5's reader finds it in a part, and the part's placement carries it into the piece. Giving it a frame would mean either `hardware.yaml` (every prompt's hash changes) or an `own:608` alongside the catalog's `608ZZ`, plus a check that the two agree.

## 3. The checks

Each check reads `placed.piece()`. The servo's case is placed by geometry, not by the design's word. `servo.find_mount` and `arm._poses` give where the mount holds the case, and the mount's placement puts that into the piece. The design's servo placement then picks which end and which way up (the nearest pose) and has to agree with that pose. The shaft is at 9.3, 10.3 and 11.3 mm from the chosen end.

| Check | Reads | Record / estimate | Fails | Passes | Not graded |
|---|---|---|---|---|---|
| **R8 (new, C5): it goes together as placed** | every placed part's mesh, a case-and-tabs solid in the servo frame, the turning parts' hub axis | geometry; the 0.25 a-side seat (test print D) as the overlap tolerance | two still parts overlap by more than 0.3 mm; the servo's placement is over 1 mm and 2° beyond the band from every pose its mount gives; a turning part's bore or horn pocket misses the shaft line (off by more than its radius) or lies wholly outside 0–10 mm above the case | none of those, at every shaft offset | a part isn't a closed mesh (`placed.NotReadable`); overlaps only at some offsets |
| **R7 (changed): the swing** | turning parts plus the horn's hub (14.66 × 5.95) as one body, turned about the shaft in 1° steps; obstacles: every still part plus case and tabs | the datasheet's 120°; shaft ±1 mm; arm 0–10 mm above the case | under 120° clear at every offset and height | 120° clear at every one | depends on them. Heights where the turning body meets a still part at every angle are dropped: the stack stops it there, it doesn't swing there |
| **A (new, reported, C5): bearing alignment** | the 608 seat (R5's reader), in a still part or in a turning part on the hub's axis; then the still axle (a placed screw through the seat, from `assembly.screws`) | none: no print shows how much misalignment binds | the shaft line misses the 608's 8 mm bore at the seat (more than 3.97 mm off), so nothing on the shaft's axis can pass through it | never: no record says what's close enough | everything else. The detail gives the offset and angle. A seat that isn't on the shaft's axis (a tip seat for the next joint, Sonnet's roller) is "not a second support" |
| **R2, R3 (changed)** | `_maybe_elsewhere` | as servo-mount | a miss under a tab when no placed part has plastic within the tab's footprint (`placed.plastic_in` with a column at each tab hole) | unchanged | a miss where another placed part is under the tab (screwing into that part isn't graded yet) |
| R4, R6 | the turning part's bore or pocket, not a guess by bore size | unchanged | unchanged | unchanged | R6 measured from the placed shaft line |

Clear at every offset and height means clear wherever the ±1 mm and the 0–10 mm band fall. R1 and R5 stay on the printed geometry alone.

- **No assembly, no `turns_with`, or R8 failed:** R7, A and R2/R3 fall back to today's geometry-only reading (all poses and ends, and an unplaced third part means fail or not graded), and say why. A run can't skip the assembly (`submit_design` sends it back), but a hand-graded or regraded old submission can. Falling back keeps each mistake failing only its own check: a wrong coordinate fails R8 and nothing else.
- **R8 grades the assembly as written, not only the parts.** A model that types a wrong offset fails R8 even if the printed parts would go together. That's the design's own word (main's rule in `docs/limitations.md`, "Box-and-boards checks"), but Dan should agree to score it.

## 4. Code, tests, reference

- **Reused:** `placed.piece/matrix/into/plastic_in/column/box`; `arm._cylinder/_mask/_arcs/_clear_arc/_case_points/_poses`; `servo.find_mount/_seat`; `wheel`'s seat reader through `arm.bearing_seat`.
- **New:** in `placed.py`, `overlap(meshes, tolerance)`, a pairwise manifold intersection, generic and in its style. In `submission.py`, `turns_with` and its validation (it has to name a placed own part with a frame). The `OwnPart.optional` and `TaskFormat.turning` flags, and the format move. In `arm.py`, a placed path for `swing`, `fits_together` (R8) and `alignment` (A), about 150 lines. In `servo.py`, the change to `_maybe_elsewhere`.
- **Reference:** today's plate and arm, plus a placed `own:mg996r` (+z up through the cutout, +x towards the far end) and the arm with `turns_with: mg996r`. Add a second reference fixture for the support shape: a bracket over the shaft holding the 608 around a stub on the arm.
- **Tests** (`tests/test_servo_arm.py`): both references pass R8 and R7, and A comes back not graded with an offset of 0. Then one mistake each, each failing only its own check: bracket 6 mm off the axis (A fails, R8 and R7 hold); bracket dropped onto the arm's path (R7 fails); bracket overlapping the base (R8 fails, R7 falls back); servo placed in the middle of its cutout (R8 fails); arm placed 5 mm off the shaft (R8 fails); a keeper with `turns_with` (no false collision) and without it (R7 reads it as an obstacle); no part under a tab with a strap placed elsewhere (R2 fails, not not-graded); the same without an assembly (today's verdicts). Add the prompt hashes for servo-arm, and keep the estoa hashes unchanged.

## 5. The rerun

12 trials: Haiku, Opus, Sonnet, DeepSeek, Gemini and GPT in `can_ask` and `all_given`, one trial each, as a new run (`servo-arm-assembly`). The old 8 can't be reused or regraded as a comparison: the prompt (own parts, assembly rule, the M3 horn fact) and the tools (`assembly`, `turns_with`) both change.

**Cost estimate.** From the first look's per-trial costs (`summary.csv`), using `can_ask` where `all_given` never ran: Haiku $0.04, Opus $1.49, Sonnet $1.39, DeepSeek $1.64, Gemini $1.16, GPT $0.26, which comes to **about $6.00**. The assembly adds output tokens and repair turns, so each model gets about twice its estimate as its `--budget` (Haiku 0.25, Opus 3, Sonnet 3, DeepSeek 3.5, Gemini 2.5, GPT 1), **$13.25 at most**. The OpenRouter credit needs topping up first: the first look stopped on HTTP 402.

**Running it.** One process per model, in parallel, each with both conditions and its own budget: `uv run python -m pbe.eval --task servo-arm --model <m> --condition can_ask --condition all_given --trials 1 --budget <b> --run servo-arm-assembly-<short>`. Each model gets its own run folder unless the runner is first shown to be safe sharing one. Commit results as each model finishes.

## 6. Risks and what stays not graded

- **The ±1 mm still decides.** A design built close to its own guess of the shaft will often get not graded on R7 and A. Slots that let a bracket line itself up (Opus `can_ask`, Gemini) aren't read: a part sits where it's placed.
- **R8 can fail a sound part set over a typed coordinate** (above). The fallback keeps the other checks honest.
- **The horn's arm isn't in the swing:** its width was never measured. Only its hub turns with the arm.
- **Alignment never passes,** for lack of a record. It fails only when the geometry rules the joint out.
- **Not graded, as before:** load and stiffness; the cable as an obstacle; screwing into a part other than the mount under the tabs; how the arm holds the horn (R4 on the horn); whether the arm's stub binds in the bearing; the order parts go in (no assembly simulation).
- **Main's frame sentence** says z is away from "the wall, the desk" and +y is up. On a desk those disagree. No servo-arm check uses gravity or the piece's own axes, only relative positions, so grades don't depend on it. Fixing the sentence would change estoa's tool hash.
