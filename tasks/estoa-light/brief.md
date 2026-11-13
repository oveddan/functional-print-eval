# Estoa light: the box behind the disk

What the model is given. **Drafted from Dan's answers and approved by him on 2026-11-04.**
The second sentence is Dan's (2026-11-04, replacing "I think there'd be frosted sides, and you just see the
LED disc" from the Estoa session 73c93171, 2026-09-27T21:08): no glass, the front and sides printed in
transparent PLA so the diodes are hard to see, and the back box in matte white, as he printed it. The rest follows what he asked
for on the review page: the ESP32 sits on a perfboard with four wires to the disk, the disk has two holes
that don't show on its datasheet, and the charger plugs straight into the ESP32.

> I'm making a round light to hang on my wall: an Adafruit DotStar LED disc, the 255-LED one. I'll 3D print the front and sides in transparent PLA, so they look frosted and you can't make out the diodes, and the box behind the disc in matte white. The front and sides come later: for now I only need that box, with the disc screwed onto it. Inside it is an ESP32 on a perfboard, with four wires from the perfboard to the disc. The disc screws onto the front of the box with M3 screws, through two small holes near its centre. The holes aren't on its datasheet. The box hangs flat against the wall on two screws, and I power it with a USB-C charger plugged straight into the ESP32, so I need to reach its port from outside once it's all closed up.

The prompt also lists the person's own parts (`format.yaml`): the disk, the perfboard, the ESP32 on it and
M2 self-tapping screws, each with how its frame sits on it so the design can say where it goes. None of
their dimensions is listed. They come from `measure`, which answers with Dan's readings
(`hidden_facts.yaml`), including the perfboard's four corner holes.

## Why it's hard

Every number that decides whether the box works is on the person's bench, and the disk's datasheet
(`files/datasheet.png`, given to the model only in `can_run_code`) shows none of them: it has the LED layout
and the wiring, no mounting holes and no diameter. The Estoa agent concluded "The disk has no mounting
holes. Its datasheet shows none." (73c93171, 2026-09-27T22:12), designed a rim-held tray, and then, once Dan
pointed the holes out, guessed them "very roughly 30 mm apart" from a photo before asking him to measure
(602ba611, 20:17). Dan's calipers put them 33.5 to 33.9 mm apart. Here the request says there are two holes
that the datasheet doesn't show, so the test is whether a model asks where they are or guesses. The ESP32's
USB opening is the other Estoa failure this task carries: an 11.5 mm opening at the end of a recess stopped
ordinary plugs reaching that very port.

## Decisions and notes

Dan answered the review questions on 2026-11-04:
- **Wording:** changed as above. No glass: the front and sides are printed in transparent PLA to hide the
  diodes, and the back box in matte white. No check reads the material. This version still asks only for the box behind the disk; the frosted front and sides
  are skipped for time.
- **The holes:** mention that there are two and that the datasheet doesn't show them. The request names
  M3 screws because R1 and R2 grade an M3 through each hole, and Estoa's disk screws were M3 x 20
  (`seeds/estoa-failures.yaml`). The length is left to the model, since R2 grades it.
- **Power:** the simplest: a charger plugged straight into the ESP32's own USB-C port. No USB-C breakout
  ("ignore the USB-C breakout for the simplicity of this task"), no battery, no radar.

Other notes:
- **Scope (decided).** This version is only the box behind the disk. A later version could add the printed
  front and sides on the same `assembly` layout. At Estoa's 283 mm they don't fit the 256 mm bed. The Estoa
  records that would grade them (issue 17's comment and `seeds/estoa-failures.yaml`) come from the
  glass-fronted build, so the glass ones only apply if glass comes back:
  - the wall and the top ring printed in quarters;
  - leg pocket fit: 0.2 mm per side wouldn't seat, 0.35 mm worked (`leg-pocket-too-tight`);
  - a leg screw under the glass ledge: only an angled hex key reached it; moved 6.4 mm inward, a straight
    driver did (`leg-screw-under-lip`);
  - a 50 mm cutter broke through the ledge, leaving 0.2 mm of plastic (`hole-cut-through-ledge`);
  - the glass, 4 mm thick and cut to 283 mm (about ±0.5 mm), on a 4 mm ledge with 0.75 mm clearance,
    dropped in flat;
  - the top ring's quarters held with eight M3 x 6 countersunk screws into inserts.
- **The breakout is gone,** and with it the check on its screws (M3 x 8 bottoming out in blind inserts). That
  record stays in the seeds for a later task.
- **The four wires** run from the perfboard to the disk's connector. Where the connector sits on the disk isn't
  recorded, so the wire path isn't graded. The reference leaves a 12 mm hole for them.
- **The datasheet** is shown only to `can_run_code`, as a file. Putting it in the first message as an image
  for every condition is a follow-up. It would put a 570 KB image in every saved transcript.

## What class each check belongs to

The checks don't know about a light. They read a box that holds bought boards and hangs on a wall
(`pbe/graders/enclosure.py`), from the design's `assembly`: where each printed part, each of the person's
boards and each screw goes in the finished piece (`pbe/graders/placed.py`).

| Check | Class | Runs on |
|---|---|---|
| R1 a screw through each of the disk's holes goes into the box | C1 unmeasured | any board held by its own holes |
| R2 the disk's screws hold, don't bottom out, don't reach the electronics | C3 fastener stack-up | any board held by its own holes |
| R3 a USB-C plug reaches the ESP32's port from outside | C5 mating envelopes | any socket inside a box |
| R4 every heat-set insert sits in a post like the ones that held | C3 | any part with inserts |
| R5 the perfboard is inside the box, and the ESP32 has room | C5 | any board with parts on it |
| R6 the box hangs on keyholes whose slots run the same way | C7 use orientation | anything hung on wall screws |
| R7 no screw stands out of the back | C5 | anything hung on a wall |
| `builds`, `connected_bodies`, `bed_fit`, `bridges` | C6 printability | any part |

## What the records decide

Nothing here was measured for this task, and no model's design gets printed. Every limit comes from the
Estoa build (its prints, Dan's measurements, its session records, relayed on issue 17) or from geometry
alone. What they can't decide is "not graded", which is never a pass. Where a check uses a range estimated
from a recorded print, the table says **estimate**, and the report lists it as a limitation of the eval. A
design that tests first, with a printed template or test print and a param it can change, also passes where
a record says what the test would have shown, as the nut pockets do (`pbe/graders/nuts.py`).

| Check | Fails | Passes | Not graded | Source |
|---|---|---|---|---|
| R1 disk holes | a screw through either hole can't go into the box anywhere the hole could be, and no template or test print would catch it; no plastic behind a hole; the disk doesn't rest on the box (first plastic more than 0.6 mm behind it); plastic where the board is; the disk facing the wall | a screw through each hole goes into the box wherever in its range the hole really is; **or** the design checks the hole pattern against the disk with a template or test print (a criterion whose check method is `template` or `coupon`, the schema's name for a test print), and one of that criterion's params moves the box's holes when changed and rebuilt | the screw goes in for only part of the range; pins through the holes | Dan's calipers (602ba611, 2026-09-28): holes 3.3 mm, 30.2 mm between their inner edges, 102.54 and 102.24 mm from their outer edges to the disk's edge, on a line through the centre. That puts each centre 16.60 to 17.11 mm from the centre, the spread between the direct reading (33.5 apart) and the edge readings (33.9 on a 242 mm disk, the positions Estoa printed and that worked). A 3 mm screw has 0.15 mm of play in a 3.3 mm hole; a clearance hole lets the screw move, an insert or pilot holds it at the hole's centre. The second path: Estoa placed the holes from a printout of the pattern, and they fit ("They put it where the two holes go, based on the printout. We're good.", ead22945, 2026-10-03T19:46). |
| R2 disk screws | bottoms out even on the thickest disk; tip out of the back; tip in the ESP32 (over where it certainly stands, below 12.55 mm); a clearance hole and no nut; too short to get through the plastic | a whole nut on it past the plastic, or 3 mm or more of thread, for any disk thickness in the range | may bottom out, or a nut only partly on, depending on the disk's thickness; tip over the rest of the perfboard below 16 mm | Thickness never measured (Estoa assumed 1.6). **Estimate:** 1.2 to 2.0 mm, the usual board thicknesses either side. 3 mm of thread held in Estoa's lid inserts. Estoa's M3 x 20 would have stuck 4 mm into the box and pressed on the battery; there's no battery here, so a long screw that hits nothing passes. |
| R3 plug opening | 4 mm or more out from the port, the way in doesn't take Dan's measured plug head (11.58 x 6.44 mm), so the head stops there and its 7.5 mm of bare metal can't seat, and no test print would catch it; anything right in front of the port; plastic inside the receptacle's first mm; the ESP32 not inside the box | the way in holds that head with 0.2 mm a side (11.98 x 6.84 mm, read as a slot shape) from the port all the way out; **or** a test print the manual uses has an opening that holds 11.98 x 6.84 mm, right through a wall at least as thick as the final part's at the port, and a param moves the final opening's width when changed and rebuilt | anything between: openings that take the bare head but not with 0.2 mm a side, and openings too small for the head only nearer than 4 mm to the port, where the bare metal may reach | **Dan's plug, measured (2026-11-12, `catalog/connectors.yaml`):** head 11.58 wide and 6.44 thick, about 7.5 mm of bare metal in front of it. **Claude's scoring call (2026-11-12):** 0.2 mm a side for printed holes coming out small, the allowance round 1's holes and round 3's bearing seats suggest; the head's corners weren't measured, so it's read as a slot shape, like the openings. The failure line comes from Estoa, at this ESP32's port: 11.5 x 8.5 at the end of a 9 mm recess, about 4 mm out from the port (Estoa's tunnel was made to end 4 mm short of it): "ordinary USB-C plug heads don't reach the ESP32's port" (`FIXES.md`, section 2). 11.5 is narrower than the head, so it still fails. 14 x 8.5, where "both the Belkin's right-angle plug and a laptop's straight plug seat fully" (`TEST-PRINTS.md`, 2026-10-02, at the power bank's port), still passes. A pass line of "head and margin within 7.5 mm of the port" was considered and dropped: it would pass Estoa's opening, which stopped plugs 4 mm out. The receptacle's 10.67 x 3.2 mm outside is from the Estoa model. |
| R4 insert posts | none | 1.85 mm of plastic or more at the thinnest, halfway down the insert, in a 4.2 to 4.4 mm hole | thinner; any other hole size; no inserts | Seed `insert-bosses-bulged`: posts about 8 mm across with 4.3 mm holes, freestanding and 26 mm tall, bulged: (8 - 4.3) / 2 = 1.85. They were printed at 100% infill, and Dan's call (2026-11-08) is that the infill made them bulge and that at 20% they'd hold, so posts are graded as printed at 20% and those 8 mm posts count as holding. 12 mm posts webbed to the wall, printed at 20%, held: 3.85. Until 2026-11-08 a post of 1.85 mm or less failed and one under 3.85 wasn't graded. **Estimate:** the hole range around the 4.3 mm that inserts were set in. No test-print path: no test print of an insert was made in Estoa. |
| R5 perfboard | not enclosed on some side; plastic in the board (top 1 mm, less 2 mm at its edges); plastic less than 12.55 mm over the middle strip the ESP32 always covers | 16 mm clear over the board less 3 mm at each edge | plastic between 12.55 and 16 mm, or over the board outside the strip | The ESP32 in its headers stands about 16 mm (seed `esp32-headers-vs-lid`: only just cleared the lid; the box was made 3 mm deeper). 11.05 mm to its board's underside was measured, plus its 1.5 mm board: 12.55. Its tallest part wasn't. Board 50 x 70 (Dan); the ESP32 is 28.25 x 63.17 (Dan), so a 6.5 x 56.3 mm strip down the middle is under it wherever it sits. **Estimate:** the perfboard is at least 1 mm thick (never measured). |
| R6 keyholes | a slot more than 60 degrees from the way the slots run on average, so no way of hanging it drops it onto both screws; an entry under 9.9 mm; a slot under 4.17 mm or 6.5 mm and over; the screw resting inside the entry; plastic at the slot 3.5 mm thick or more; nothing in the back at all | each slot within 30 degrees of that way, entry 9.9 mm or more, slot 4.5 to 6.0 mm, running past the entry, so the head rests on the lip even if part of it is still over the entry (Dan, 2026-11-13: "that would hang fine") | slot 4.17 to 4.5 or 6.0 to 6.5; fewer than two keyholes found | **Any common wall screw (Dan, 2026-11-11),** so the limits come from screw sizes, not from the one keyhole that hung. **Claude's scoring call:** #6 to #10 pan or round heads. The largest head, a #10 pan head, is 0.373 in (9.47 mm) at most; the entry takes it with 0.2 mm a side, since printed holes come out small (round 1's square holes). The slot must pass a #8 shank, 0.164 in (4.17 mm), and hold a #6 pan head, 0.256 in (6.5 mm) at least. A #10 shank (4.83 mm) isn't required: Estoa's own slots were 4.8 mm and hung it on #8 screws, so the range is #6 to #8 shanks with heads up to a #10's. Head sizes are from supplier listings that cite ASME B18.6.3 and B18.16.3, not the standard's own table. **Which way up (Dan, 2026-11-11):** it doesn't matter. The disc is round and the USB-C port can come out of any side, so the box hangs whichever way up its slots run, upside down included. Seed `keyholes-point-down` is no longer a failure on its own. Estoa's own keyholes (10.5 entry, 4.8 slot running 12) pass. |
| R7 nothing proud | any screw's head or tip below the back | nothing below it | | Seed `lid-screw-heads-proud`: six button heads 1.65 mm proud of the lid would have jammed on the wall screws. Geometry: anything below the back holds the box off the wall. |

## Known limits

- **Hidden values the model can't get.** The disk's diameter and thickness and the perfboard's thickness were
  never measured, and the person says so. The plug's boot was measured only on 2026-11-12, after the runs, for R3's
  limits; the person in the runs still says it wasn't measured. Checks that
  depend on them use the estimated ranges above or say not graded. Nothing invents them.
- **Values from the Estoa model, not Dan's messages.** The ESP32 port's height above the perfboard and its
  receptacle's size, the perfboard's hole grid and the ESP32's header columns are in `disk_puck.scad`, some
  marked measured, but the relay didn't find Dan's message for them. `measure` gives them with that note. R3
  uses the receptacle's size only to fail plastic inside its first millimetre.
- **Where the port sits relative to the perfboard** is only partly recorded (Dan's 4.80 and 7.53 mm readings
  are ambiguous), so the design places the perfboard and the ESP32's port separately and nothing checks that
  the two agree. R3 reads the port where the design says it is, and R5 the perfboard. A design that claims its
  port pokes out through the wall isn't caught.
- **The screws are where the design says.** R2, R4 and R7 trust the `assembly`'s screw positions. A screw
  declared where the geometry has no hole for it isn't caught yet.
- **Keyholes only.** R6 recognises closed keyholes. A box hung another way (open slots at the bottom edge, a
  cleat) gets not graded, never a pass. One with nothing in its back at all fails.
- **Disks on pins** through their holes are recognised and get not graded: no print has tried them.
- **Inserts behind the disk** get not graded on R1 unless a template checks the pattern first: an insert holds
  the screw at one spot, and Dan's readings leave each hole's centre within about half a millimetre, more than
  the 0.15 mm of play a 3.3 mm hole gives. The Estoa build used clearance holes and nuts, which is what the
  reference does.
- **The ESP32's position on the perfboard** is partly recorded. R5 and R2 read only the strip it covers
  wherever it sits, and say not graded over the rest of the board.
- **Testing first.** The template and test-print paths trust that the person runs the test the manual names
  and changes the param it says. They check that the test could find the answer and that the param moves the
  feature, not how clearly the manual says so. Checking a param means rebuilding the final parts once per
  param tried, up to 8, so those cases take longer to grade.
- **Kinematic only.** No check models weight, a screw's pull-out strength or how a post flexes. The wall
  screws' real heads, the wall itself and the finished weight weren't recorded.
