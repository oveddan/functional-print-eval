# servo-arm on the 25T horn: proposed request and check changes

Status: proposed 2026-11-11, wording not yet approved. Nothing has been run on it; under the plan's rule (`docs/plan.md`), no model runs on a request until its wording is approved. The task on this branch still uses the approved 2026-11-07 request; the R4 horn reader below is already in the code, because it applies to both.

Why (Dan, 2026-11-11): the better task is a servo arm that rotates another thing back and forth using the 25T aluminium horn.

## The request

Today's, approved 2026-11-07:

> I want to prototype the first version of a robot arm. I have an MG996R servo and a 608 bearing to work with. It should swing both ways, and the arm should be about 100 mm long.

**Request A** (recommended: the same person and the same arm, now driven through the horn, so R5 to R7 carry over):

> I want to prototype the first version of a robot arm. I have an MG996R servo with a 25-tooth aluminium horn on it, and a 608 bearing to work with. The servo should swing the arm back and forth using the horn, and the arm should be about 100 mm long.

**Request B** (the "another thing" reading, with a paddle as the thing):

> I want my MG996R servo to wave a paddle back and forth. I've got a 25-tooth aluminium horn for it, and a 608 bearing if that helps. The paddle should stick out about 100 mm from the servo.

Both say what it should do and leave the mechanism to the model: how the arm or paddle attaches to the horn, whether the 608 is used, and how the servo is held. "Using the horn" is Dan's phrase (2026-11-11); with it in the request, a design that presses straight onto the spline isn't doing what was asked (see R4 below). Without it, the horn is just hardware on hand, and the spline bore stays a valid route.

## What changes in the checks

| Check | Today | With request A or B |
|---|---|---|
| R1 to R3 (the servo's mount) | servo-mount's | Unchanged |
| R4 (the arm on the drive) | A plain bore on the spline, from test print E; an arm on the horn not graded | **On the horn's hub pocket**, from round 3's piece N (14.76, 15.16, 15.66 mm pockets, 2 mm deep), read from `results/predictions/round3-coupons.yaml`. Built on this branch and recorded 2026-11-12: 14.76 fits, the other two too big, so 14.66 to 14.96 passes and 15.0 and up fails. A plain bore on the spline, ignoring the horn, **fails** with "using the horn" in the request; it is graded from test print E as now if Dan drops that phrase |
| R8, new (the arm turns with the horn) | none | The arm is fixed to the horn so it turns with it: screws through the horn's two holes (taken as threaded M3, Dan 2026-11-07) or a horn-shaped pocket. **Not graded** while the holes' centres are only estimated from a photo (20.4 to 24.1 mm from the hub, about ±1 mm). Fails only when nothing can stop the arm turning on the hub: a round pocket with no hole anywhere 15 to 30 mm from its axis and no slot for the horn's arm. Claude's call |
| R5 (the 608's seat) | round 2's seats | Unchanged |
| R6 (about 100 mm) | from the shaft bore or the horn pocket's axis | Unchanged for A. For B, the paddle's reach from the pocket's axis, the same 85 to 115 band |
| R7 (swings both ways) | a clear 120° arc past the mount and the case | Unchanged, except that the horn's hub (14.66 across, 5.95 thick) turns with the arm and counts as part of it. The horn's own arm isn't added: its width was never measured |

Hidden facts gain "its holes are threaded for M3" in the `horns` note (Dan's 2026-11-07 assumption, held back so the first look's last four trials saw the same facts), and the person still says they didn't measure where the holes are. Under request A or B the first look's eight trials can't be compared: the request changes, so it's a new run.

## What the records can't settle yet

These are limits of the eval as it stands. Each is listed with the reading that would close it, as information, not a request:

| Gap | What it leaves not graded | The reading that would settle it |
|---|---|---|
| The horn's screw-hole centres | R8 (screws lining up with the horn) | Each hole's centre distance from the hub's centre |
| Whether the holes take an M3 screw | R8's screw size; today it's an assumption (2.55 mm reading fits an M3 tap drill) | Whether an M3 screw threads into them |
| The spline's length | How deep a bore must be to grip, and how far the horn's hub sits on the spline; R4 reads any bore 3 mm or deeper | Spline length above the case top |
| The cable exit's size | R3 for a servo dropped in from above. Since 2026-11-12 it decides no saved trial: a plate with no rib gap fails (Dan's rule), and one with a gap passes from underneath | The cable's width and thickness where it leaves the case, and how far it sticks out |

Round 3's N piece settles the hub pocket only: it has a hole for the horn's centre screw but none for its two arm holes. Its M plates settled the 10 mm across a tab to about ±0.6 mm (3.4 holes clear through the 4.58 tab holes, Dan 2026-11-12), so that gap is closed.
