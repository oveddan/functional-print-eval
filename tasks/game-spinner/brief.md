# Game spinner

**DRAFTED, NOT APPROVED.** Claude wrote this request for issue 41, and Dan has reviewed it but not approved its final words. The part is synthetic: nobody has built it or test printed it. The game, the board and the wheel's size are invented. The bearing, the nuts and how each one fits on this printer come from real test prints. Until Dan approves the request, results from it are a first look, reported apart from the headline numbers.

> I'm making a spinner for a board game my kids made up: a wheel about 70 mm across that I'll mount on a board and spin by hand. It should spin smoothly. It needs a handle near the edge to spin it with, and the handle has to come off so the game packs flat in its box. Once the wheel is on the board I can't reach behind it, and nothing should fall out if it's turned upside down. I'd like to put it together by hand, no glue. It's one printed piece. I've got some skateboard bearings, and M3, M5 and M8 bolts and nuts in a few lengths.

The request states the problem and what the person has, and leaves the design to the model: whether to use a bearing, which nut and bolt, which lengths, which face goes down. The hardware list every task gets has all of these, so the prompt is unchanged. The person names only parts that have test prints (Dan, 2026-11-05): the 608 (round 2) and the M3, M5 and M8 hex nuts (coupon B).

The "comes off" and "can't reach behind it" lines are what call for a nut held in the wheel. A handle printed as part of the wheel can't come off.

## The request's first version

The first look ran on a version that named the 608, an M8 axle, and an M5 bolt into an M5 nut held at the back (`results/first-look/game-spinner/`). Dan's review: it specified too much; the model should choose the hardware. That version's trials stay as they were graded, as a record of the first wording.

## Why this part, and not a spool holder hub

Issue 41 asks for one printed part combining a recorded 608 seat and a recorded nut pocket, and suggests a spool holder hub. On a hub that turns on its bearing, a single nut has no job: the spool turns with the hub, and a hub held down by one bolt off its centre would turn around that bolt. So the part was changed to one where each piece of hardware has a job and the records can grade the result:

- **Each fit can meet its record the way it was printed.** Coupon E's 608 seats and coupon B's nut pockets were both cut into the top face of a solid block, and the parts were pressed in from above. Here the seat and the pocket can both open on the back face and print on top, so a design needs no bridge.
- **The two fits sit apart.** On a 70 mm wheel, the handle's nut is well away from the bearing. That's the case where assuming the fits don't affect each other is easiest to defend (see "Assumptions").
- **One of each.** The nut reader grades the hex pocket nearest the middle, so a part with two nuts would leave one unread.
- **About 70 mm across.** That's big enough for thick walls round both fits, and small enough that a window 20 to 26 mm across, which the wheel reader could mistake for the bearing's bore, hardly fits.
- **A plausible request.** A skateboard bearing is what people use when they want something to spin smoothly. A nut held in the part is the usual answer when you can't reach the back of it.

## Why it's hard

- **C2, fit.** The catalog's 22.0 mm won't take the bearing on this printer (round 2). The right nut clearance changes with the nut, and against the usual rule of thumb: an M3 needs +0.2, an M5 holds at +0.0 and +0.1, and an M8 only at +0.0 (coupon B). A model that picks its nut has to know that clearance for that nut, and can't know it without a test print.
- **C6, printing.** If the seat opens at the bed, its floor is a roof with the bolt's hole through it: the bridged hole the Arca plate's first print tangled on. A model has to choose which face goes down.
- **C3 and C5.** Both bolts have to get through, the bearing needs 7 mm of depth and something to stop it, and the nut needs a closed hex reached from one face.

## Every check, its record and its limits

Between two test prints that agree, a size counts as what they agree on, as in the bearing wheel and nut knob tasks (22.15 mm is between two seats that held, so it holds). Tighter than a size that wouldn't go in, or looser than one the nuts fell out of, fails. Between two that disagree, or beyond the last size printed in a direction no print settles, a size is not graded, which is never a pass.

The checks are the existing ones (`wheel.*`, `nut.*`), called through `pbe/graders/combined.py`. It reads the design's hardware list to pick the record that applies, and adds no geometry.

| Check | Class | Record | Fails | Passes | Not graded |
|---|---|---|---|---|---|
| R1 one printed part | C6 | The request | Two or more final parts | One final part; a test print doesn't count | — |
| R2 about 70 mm across | C5 | The request (invented, like the bearing wheel's 50 mm) | Under 56 or over 84 mm | 56 to 84 mm | — |
| R3 room for the bearing | C5 | The 608 is 7 mm wide (`catalog/hardware.yaml`); round 2's seats were 7.2 mm deep with floors | No seat-sized hole at all | At least 6.9 mm deep, with the bore narrowing past it | A seat shallower than the bearing, so it stands proud; a bore with no shoulder. No test print tried either. A design with no 608 |
| R4 the bearing presses in and stays | C2 | Round 2, coupon E's 608 seats (`results/predictions/round2-coupons.yaml`) | 22.0 mm or under: won't go in | 22.1 to 22.3 mm, plain and round: each held upside down. Or a test print in the manual has a seat in that range and a param moves the wheel's seat | Over 22.0 and under 22.1; over 22.3; ribs, lobes or slots; a design with no 608 |
| R5 the M8 bolt gets through the bearing | C3 | The 608's bore is 8 mm; ISO 273's fine clearance hole for M8 is 8.4 | Under 8.0 mm at the bore's tightest | 8.4 mm or more | 8.0 to 8.4 mm; a design with no 608 |
| R6 a pocket for the handle's nut | C5 | ISO 4032 (`catalog/hardware.yaml`) | No hex pocket about the nut's size; one closed on both faces; one open on both, so the nut can go out the far side; one shallower than the nut by more than a layer | A hex pocket deep enough, reached from one face | A pocket along x or y (the part printed on its side); a nut other than ISO 4032 M3, M5 or M8, a lock nut or a heat-set insert |
| R7 the handle's nut presses in and stays | C2 | Coupon B, round 1, that nut's row (`results/predictions/round1-coupons.yaml`); nuts fell out at +0.3 on the tripod build (`catalog/printer.yaml`, in PETG) | M3: +0.0 or tighter. M5: +0.3 or more. M8: +0.3 or more | M3: +0.2 to +0.3. M5: +0.0 to +0.1. M8: +0.0. Plain pockets only. Or a test print in the manual has a pocket that holds and a param moves the wheel's pocket | M3: over +0.0 and under +0.2, including +0.1 (Dan: "really struggles to go in"); over +0.3. M5: under +0.0; over +0.1 and under +0.3. M8: under +0.0; over +0.0 and under +0.3 (coupon B's "loose" rows were never turned upside down). Ribs, clips or relief. Other nuts, as R6 |
| R8 the handle's bolt gets through | C3 | ISO 273's fine clearance hole: 3.2, 5.3 and 8.4 mm | Narrower than the bolt (3, 5 or 8 mm) anywhere along the handle's axis; a closed layer the manual doesn't say to clear | The fine clearance hole or more all the way; a drill-out layer up to 0.6 mm the manual says to clear | Between the bolt's size and its fine clearance hole: no print of a hole that size. Other nuts, as R6 |
| `bridges` (every task) | C6 | The Arca plate's first roof and coupon A's H cell tangled; coupon A's S cell, the stepped roof, printed clean (`round1-coupons.yaml`) | A roof with a hole in it, reaching more than 3 mm from its walls, such as the seat opening at the bed over its floor | Every overhang has a direction where its strands land on solid at both ends | A ring 1.5 to 3 mm wide, such as a plain nut pocket opening at the bed round its bolt hole |

If the hardware list names two of the recorded nuts, the one the wheel has a pocket for is graded; if that doesn't settle it, R6 to R8 are not graded.

The `bridges` verdicts rest on what `docs/limitations.md` states: a holed roof of any shape 3.1 to 7.8 mm from its walls is assumed to tangle, as the two that were printed did (Dan, 2026-11-03), and anything within 1.5 mm of the layer below is taken as an ordinary overhang, which is a guess.

## Assumptions

Each of these is treated as true without a test print that shows it for this part. The report states them beside its results.

- **The two fits don't affect each other.** The seat's fit comes from coupon E and the pocket's from coupon B, each printed alone. Together in one part, each is assumed to fit as it did on its own coupon. This is likeliest to hold when they're far apart, as on a 70 mm wheel. If a design puts the nut right against the seat, the assumption is stretched, and the checks don't detect it.
- **Walls don't change a fit.** From `coupons/coupons.py`: coupon E's seats had 5.7 mm or more of plastic beside them, except the 22.3 mm seat, which had 2.9 mm on one side, and coupon B's M5 pockets that held had at least 12.6 mm. The reference leaves 7.2 mm between its seat and its pocket and 7.3 mm from the pocket to the rim. The checks don't read wall thickness. The nut knob makes the same assumption (its M5 reference leaves about 9 mm), and so does the bearing wheel.
- **A bolt hole under the nut doesn't change its fit.** Coupon B's pockets had solid floors. The knob task makes the same assumption.
- **One setup, one print.** Every limit is for the X1C with black high-speed PLA at 0.2 mm, and each size was printed once.

## Not checked

- **Bolt lengths.** The model picks them from the hardware list. Whether the handle's bolt reaches through its nut depends on where its head sits (on the face, on a raised boss, under a sleeve), and a reach check that misread that would give false verdicts. The axle bolt's length depends on the board, whose thickness the person doesn't know.
- Whether the handle comes off: a handle with no nut, printed as part of the wheel, is graded only as R6 to R8 not graded.
- Whether the middle of the wheel presses on the bearing's inner ring, which would stop it turning once the bolt is tight, as in the bearing wheel.
- Which face the pocket opens on. The handle bolt comes in from the front, so a pocket opening on the front lets tightening pull the nut out of it. Nothing in the part shows which face is the front.
- Whether a wheel with no bearing spins smoothly, and whether the wheel is strong enough.

## Known limits

Found by reading the first look's designs (`CHANGELOG.md`, 2026-11-05), and not fixed in this task's files because they're in the shared wheel reader:
- A seat with crush ribs under about 0.3 mm high reads as a plain seat the size of the ribs' circle, because `wheel._is_round` allows 6% more area than the circle. Sonnet 5.5's 0.2 mm ribs were failed this way.
- A raised boss taller than the wheel hides the bearing's bore, because `wheel._bore_stacks` wants a hole in every slice of the part's full height. Gemini 4 Argon's 20 mm handle boss was failed this way, and the 5.3 mm handle hole was read as the M8 bore.

Others, as in the bearing wheel and the knob:
- A through window 20 to 26 mm across, with more seat-sized layers than the real seat, would be read as the bearing's bore. At 70 mm across there's little room for one.
- A second hex pocket nearer the middle than the handle's would be read instead of it.
- A wheel printed on its side isn't graded on R6 to R8.
