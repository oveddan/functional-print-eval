# Test-print planning log

The test prints Claude proposed, what Dan said, the steps that followed, and the fix. Kept as material for a later
eval of test-print planning: did the plan cover what could fail, did it spend filament on pieces that couldn't
change a verdict, and did it print where a measurement would do? Nothing here is scored yet. Dan's words are
quoted from the session transcript, with times in UTC. Print outcomes live in `results/predictions/`, not here.

Add a case whenever Dan cuts, questions or corrects a proposal, and whenever a piece prints but its result can't
settle the question.

## Flows

| Flow | Steps | Cases |
|---|---|---|
| A. Purpose questioned, piece cut or slimmed | Claude proposes a sweep of variants. Dan asks why so many. Claude finds the piece settles few trials, costs a lot, or asks a question no print can answer. The piece is removed or shrunk and the gap recorded; where a grade depended on it, the check changes and trials are regraded. | 2, 4, 7 |
| B. Dan supplies a fact the plan got wrong | A proposal rests on an assumption (hardware to hand, a catalog note). Claude asks him to check. Dan states the fact. The plan or catalog is corrected, linked sessions are told, and pieces that depend on it are cut or confirmed. | 2, 3 |
| C. Coverage question, plan grows | Claude narrows to one piece or task. Dan asks "is that all". Claude surveys the not-graded rows in the saved runs and adds pieces. | 1 |
| D. Cost pushback, trimmed but scope defended | Dan flags filament or time. Claude tightens the geometry without changing feature sizes or predictions, weighs the cost against the trials it settles, and offers optional trims. Dan prints it all. | 5 |
| E. Slicer warning that is the test | Dan relays a slicer warning. Claude explains it's the behaviour under test. Print as modeled. | 6 |
| F. Dan proposes a change, Claude keeps the test | Dan suggests a change to a piece. Claude explains why it would stop the piece testing anything. The piece is unchanged. | 8 |
| G. A measurement replaces a print | Claude asks the session that owns a task what it needs printed. The answer is calipers, not prints. | 9 |
| H. Printed, still can't tell | A test print's result doesn't settle the question. | 10 |

Setting questions answered from earlier rounds with no change (black PLA, 4 walls, infill pattern, the purpose of
the servo plates) aren't cases. They're in the transcript.

## Cases, round 3 and 3b, 2026-11-11

Context: at 18:55 Dan said "Yes, build the plate". By 19:04 `coupons/round3.py` had F bolt holes, G ring roofs,
H bearings, I nuts, J clamp plates (7 widths, 34–45 mm), K head recesses (3/4/4.5 mm), L insert posts (6/7/8 mm)
and L-post-8-solid.

### 1. Estoa's open checks not surveyed (flow C)
- **Failure:** the plate had Estoa's insert posts but nothing else from Estoa. Claude hadn't checked which Estoa
  checks were still not graded.
- **Trigger (19:17):** "is that all we need to test from all of our runs?", then "so add the estoa stuff too".
- **Steps:**
  1. Opened only `I-nuts` for "the small knob thing".
  2. Listed every not-graded row and the piece that settles it.
  3. Surveyed the open checks across Estoa's 48 trials.
  4. Added a 5.5 mm post and an `O-keyholes` plate, then regenerated predictions.
  5. Listed the Estoa gaps no piece covers: disk holes, USB-C opening.
- **Fix:** L posts became 5.5/6/7/8 mm and O-keyholes was added (later cut, case 4).

### 2. Tripod-clamp plate widths (flows A and B)
- **Failure:** 7 clamp plates, about 41 cm³ and the most of any piece, to settle 10 trials. They and the K recesses
  needed a clamp Dan doesn't have.
- **Trigger (19:07):** "Why are we printing so many tripod mount widths?", then "Unfortunately, I don't have the clamp".
- **Steps:**
  1. Explained that only a 38 mm plate had been tried, while the models drew 33.8–45 mm.
  2. Proposed measuring the clamp instead and keeping only 36 and 40.
  3. After "no clamp", removed J and K.
  4. Edited round3.py, the predictions and ROUND3.md, and recorded them under "Not covered".
- **Fix:** J and K cut, and their 42 trials stay not graded. Dan then steered the freed space to the servo pieces
  (M, N).

### 3. Horn assumed to have a clamp screw (flow B)
- **Failure:** the catalog called the 25T horn a "clamped split hub" and read 3.13 mm as a clamp-screw hole. Claude
  repeated this and put the clamp screw on the must-check list before printing.
- **Trigger (19:31):** "there is no clamp screw", after Claude's six-item horn diagram.
- **Steps:**
  1. Corrected `catalog/hardware.yaml`.
  2. Told the servo-arm session.
  3. Kept N as plain round pockets.
  4. Recorded the hub readings from Dan's photos: 14.68 and 14.63 mm.
  5. Diagram item 4 came back ambiguous ("about 5mm"), which led to an optional numbered sketch for live-mode
     `measure` in the making-system PR.
- **Fix:** catalog note only, no geometry change.

### 4. Keyhole sweep (flow A)
- **Failure:** `O-keyholes` swept entry sizes against one screw, but the requirement is any common wall screw, which
  one screw can't show.
- **Trigger (19:36):** "do we need all those keyhole prints? lets just say its a generic wall screw, shoudl work with
  diff kinds of screws".
- **Steps:**
  1. Removed O-keyholes.
  2. Rewrote R6 from screw standards, as Claude's scoring call.
  3. The first slot rule failed Estoa's own 4.8 mm slot, which really hung the light, so it was reset to a #8 shank.
  4. Regraded: 14 of 48 keyhole verdicts moved, and Opus `can_ask` t2 became the first Estoa pass.
  5. Dan: "Yes, update them".
- **Fix:** the print was cut and the check was replaced.

### 5. Filament and time (flow D)
- **Trigger (19:43):** "this uses a lot of filamensts, why arent the holes closer to each other?"; (19:46) "It's
  almost 3 hours. Isn't that a lot?"
- **Steps:**
  1. Admitted copying round 1/2's roomy spacing.
  2. Tightened to about 4 mm of wall between features: F 8 → 5 mm thick, I pitch 20 → 16, H pitch 28 → 26, M plates
     36 → 28 mm wide.
  3. The plate went from about 169 to 128 cm³, with feature sizes and predictions unchanged.
  4. On time, argued the plate settles about 200 not-graded trials and offered optional trims.
- **Fix:** spacing reduced, nothing cut, printed at almost 3 h.

### 6. G ring roofs "floating cantilever" warning (flow E)
- **Trigger (19:41):** "i got an error that g-string roofs has floating cantiliver"
- **Steps:**
  1. Explained that the roofs over open pockets are what G tests, and that with supports off the slicer flags them.
  2. Said to print as modeled, without flipping.
- **Fix:** none needed.

### 7. Square long-span plates (flow A)
- **Failure:** `span_block` made the 60/80/100 mm span pieces as full square roofs (8.6, 13.3, 19.0 cm³) to answer
  one question, the span limit, which decides 2 trials.
- **Trigger (20:38):** "What are these giant flat plates? Do we even need them?"
- **Steps:**
  1. Replaced the squares with thin bridges: a 10 mm wide, 1.2 mm deck between 8 mm pillars, about 41 → 5 cm³.
  2. Regenerated predictions and reopened in Bambu Studio.
  3. Offered to keep only the 100 mm bridge.
  4. Dan later asked "or is that not testing anything?"; Claude said only the 100 mm bridge can move a verdict, and
     that the roof crops are the real test.
- **Fix:** thin bridges; all three were printed.

### 8. Side walls on the bridges (flow F)
- **Trigger:** "ok for the test prints, id ont think the long ones without a side will work. shoud we add small walls"
- **Steps:**
  1. Explained that walls along the span would let the slicer bridge the 10 mm width, so the piece would test
     nothing.
  2. Said the failing trials' roofs are effectively open bridges.
  3. Asked Dan to note whether the middle or the edges sag.
- **Fix:** kept open.

### 9. Servo-arm prints (flow G)
- **Trigger:** Dan asked whether the servo-arm task needs test prints.
- **Steps:**
  1. Asked the servo-arm session.
  2. It answered that N and M plus earlier prints settle most checks, and that four open checks are better
     measured: tab hole spacing, cable exit, horn hole positions, spline length.
- **Fix:** no prints. The measurements are listed for Dan.

### 11. Nut pockets with no bolt hole (flows H and B), 2026-11-12
- **Failure:** the I nut pockets have solid floors. Pressed by thumb, every crush-rib pocket refused, and only the
  7.8 mm lip pocket took a nut. Claude then suggested the way builders actually seat nuts, pulling them in with a
  bolt from the other side, but the piece has no hole to do it through. The test print could only answer a thumb
  test.
- **Trigger:** Dan's thumb test (clip IMG_6174), then "Okay, so I should actually test using Bolt."
- **Steps:**
  1. Recorded the thumb results.
  2. Dan asked whether walls, infill, pattern or ironing could explain them; Claude answered no, and named the
     ribs printing fatter than drawn as the likely cause.
  3. Suggested the bolt pull-in.
  4. Found the floors are solid, and switched to pressing with a bolt and a clamp.
- **Fix:** none yet. A next nut test print should put a bolt hole through each pocket's floor.

### 12. Servo pieces tested the wrong way in (flow B), 2026-11-12
- **Failure:** the M plates and frames were planned, and the print sheet written, for pushing the MG996R up from
  underneath, with the rib grooves on the plate's bed face. The servo's cable leaves the side of the case below the
  tabs, so the servo can't come up through a close cutout. The servo-mount session had already named the cable
  exit as an open question; the plan didn't carry it into how the piece is used.
- **Trigger:** "also they top ones will not be able to slide in from the bottom cause of the cable"
- **Steps:**
  1. Dan dropped the servo in from the top, so the tabs met the plain face and the grooves weren't tested.
  2. Claude proposed flipping the plate grooved face up and dropping the servo in from the top, so the tabs land on
     the grooves.
- **Fix:** test from the top on the flipped plate. A next servo plate should put the grooves on the top face.

### 10. Sonnet's keyhole test print (flow H)
- **Failure:** in `results/runs/test-first/estoa-light/can_test/anthropic__claude-sonnet-5.5/t2` the model asked for
  a keyhole test print before its final design. The reply was "can't tell", so the print graded nothing. The R6
  rewrite later passed it on geometry.
