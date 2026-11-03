# Tripod plate

What the model is given. These are Dan's own words, the first message of the session that made the real
plate (c941d075, 2026-10-12). Dan approved this wording for model runs on 2026-11-02.

> I borrowed my friend's tripod, and I can't seem to find the part that connects the camera to the tripod. How hard would it be to 3D print it, both the flat part and the part that screws in? Just as a temporary thing until I find the real one. I know it's metal normally.

The request states a problem and leaves the mechanism to the model. The hardware list, which every task
gets, includes the bolt Dan used (`salvaged:webcam-mount-bolt`), with its head and length left blank.

## Why it's hard

The numbers that decide the fit are on the person's desk, not in any datasheet. The real session's model
asked for the bolt's length but not its head, drew the head recess 13 x 4 mm, and the head didn't fit
(seed `arca-counterbore-guessed`, class C1-unmeasured). A model has to notice that the plate depends on a
bolt it hasn't seen and on a clamp it hasn't seen, and ask. The bolt head can't be looked up: it's a
salvaged part with no standard.

Second, the bolt has to go through the plate and still reach into the camera, so the recess's depth and
the plate's thickness trade off against a length the person has to supply.

## What class each check belongs to

The task is one example of class C1, sizing a real object from a guess instead of asking. Only R2 knows about a tripod; the rest run on any flat part with a bolt through it (`pbe/bolted.py`).

| Check | Class | Runs on |
|---|---|---|
| R1 there's a plate | | any flat part |
| R2 fits the clamp | C5 mating envelopes | this task |
| R3 bolt hole | C2 fit clearance | any bolted flat part |
| R4 head recess | C1 unmeasured, C5 | any bolted flat part |
| R5 bolt reach | C3 fastener stack-up | any bolted flat part |
| `bridges` on the recess's roof | C6 printability | any part |
| `connected_bodies`, `bed_fit` | C6 printability | any part |

Whether a model asked is recorded for every trial, and `scripts/digest.py` shows which params claim a measurement that nobody gave it.

## What the records decide

Nothing here was measured for this task, and no model's design gets printed. Every limit comes from the
one plate Dan printed (`~/Source/local-lights/private/tripod_plate/arca_plate.scad`) and that session's
record. What they can't decide is "not graded", which is never a pass.

| Check | Fails | Passes | Not graded | Source |
|---|---|---|---|---|
| R2 clamp: plate width | | 37 to 39 mm | anything else | 38 mm fit a knob clamp. **Estimate:** ±1 mm, because the knob's jaws have travel. How far they travel isn't recorded, so a further-off plate isn't failed. |
| R2 clamp: angled edges | straight sides | narrows by 1 mm a side | | The clamp has angled lips (the session's reading of Dan's photos). The real bevel was 45°; other angles aren't failed. |
| R3 bolt hole | under 6.35 mm, or 15 mm and over | 6.8 to 7 mm, or wider up to 13 mm | 6.35 to 6.8, 13 to 15 | 1/4"-20 is 6.35 mm. 6.8 and 7 were printed. A head that fit a 15 mm recess could pull through a 15 mm hole; 13 stopped it. |
| R3 which face | a simple dovetail with the head's recess on its narrow, camera side | the recess on the wide side | a part with a groove in its side: the outline can't say which face goes down | The head goes under the plate, and a simple dovetail's wide face sits in the clamp. Gemini 3.8 Flash's correct grooved plate showed the outline alone can't always decide. |
| R4 head recess: width | 13 mm or less | 15 mm or more | between | Seed `arca-counterbore-guessed`: 13 too tight, 15 fit. |
| R4 head recess: depth | | 5 mm or more | under 5, or no recess at all | 5 fit. A head standing 1 mm proud was never tried. |
| R5 bolt reach | under 3.81 mm into the camera | 3.81 mm or more | | **Assumption:** the bolt's length, see below. Three full threads of 1/4"-20. |

**Bolt length is an assumption, not a record.** The session asked and no answer was saved. `hidden_facts.yaml`
says 10 mm: the real plate's 5 mm of plastic over the recess plus the "about 5 mm" into the camera that the
session's model called for. R5 is only as good as that number, and the report must say so. There's no
upper limit, because how deep a camera's socket goes isn't recorded.

If a model asks, the person says "about 15 mm across, about 5 mm tall". The true head is somewhere over
13 mm, and those are the numbers Dan's plate ended up with.

## Which checks run

The checks look at the mechanism the design chose:
- **The salvaged bolt through a printed plate:** R2 to R5.
- **A printed screw, as the request literally asks:** R2 runs. R3 to R5 report not graded, because no print
  has measured a printed 1/4"-20 thread holding a camera. The real session's model advised against one, but
  the records don't show one failing.
- **Any other bolt in the hardware list:** R3 fails. A camera's socket is 1/4"-20, and the only other
  1/4"-20 item in the list is a nut.

Slots, stepped bridges and test prints are all left to the model. `bridges` reports on the recess's roof like
any other overhang (seed `arca-roof-not-stepped`).
