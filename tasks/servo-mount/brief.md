# Servo mount

**Wording approved by Dan on 2026-11-05**, after reviewing it unchanged on the preview page ("looks great, lets run it"). Claude drafted it on 2026-11-04 for issue 40. The servo and every reading are Dan's real ones. The robot arm is the direction he named for these servos; the person's words are Claude's. Results from it are a first look, outside the headline numbers.

> I'm starting on a robot arm, and the first joint is an MG996R servo. Could I 3D print a plate that holds the servo with its shaft sticking up? It should screw on through the servo's mounting tabs and sit firm, with no wobble. I'll work out how the plate fixes to the base later. I've got the servo here, and the screws, nuts and washers on your list.

## Why it's hard

Test print D (`seeds/coupon-failures.yaml`, `servo-tab-feature-not-cleared`, class C5) was Claude's own MG996R mount, modeled from the body's length and width and the tab-hole positions. The servo went in and its holes lined up, but a rib on each tab's top face, between the tab's two holes, stopped the tabs sitting flush, so the servo couldn't be screwed down snug. The MG996R datasheet's photo and top view do show it, between each tab's slots, but nothing gives its size. A designer gets its size only by asking about, or looking at, the whole mounting face, not just where the holes are (C1).

Every other task's prompt lists all of `catalog/hardware.yaml`, which has the rib (`tab_notch`). This task's `prompt.yaml` leaves the `servos` section out, and `hidden_facts.yaml` holds the same readings, so in `can_ask` the model has to ask, and in `all_given` it's told everything up front. Comparing the two shows whether knowing about the rib is what helps. The MG90S's readings aren't in this task's hidden facts: the person has only the MG996R. The hidden facts also say where the cable leaves the case ("out of one end of the case, below the tabs"), from the catalog's `tab_shape` note, but not its size, which was never measured. The first run (`results/first-look/servo-first-look`) went without that note, so no model there could learn where the cable comes out; it was added after.

## With the datasheet

A third condition, `can_ask_datasheet`, is `can_ask` with the MG996R datasheet Dan attached on 2026-11-05 handed over with the request ("I've attached the servo's datasheet."), as two page images (`datasheet/`, rendered at 150 dpi, no metadata). The system prompt and the tools are `can_ask`'s. The datasheet shows the rib in its photo and top view without sizing it, gives a 53.6 mm tab span, and gives body sizes that differ from Dan's readings: 40.7 x 19.7 x 42.9 in its specs, 40.3 and 20 on its drawing, against 40.58 x 19.82 measured. A cutout drawn from the spec's 19.7 is narrower than the body and fails R1. It gives neither the 49.5 mm hole spacing nor the 10 mm across each tab that the catalog calls datasheet values, so those come from some other datasheet nobody has in hand. DeepSeek V4 Pro takes text only, so it can't read the pages and isn't run in this condition.

## Two ways to seat it

- **From underneath**, shaft first up through the plate: the tab's top face meets the plate, so the rib needs room. Test print D was seated this way, and the cable never reaches the plate.
- **From above**: the tab's underside meets the plate, so the rib is out of the way. But the cable leaves the case end below the tabs, so it has to pass through the cutout first. Test print D's servo, pushed in from above, stopped at its cable exit.

Either way passes if its record allows. The plate can be used either face up, so each face is read for each way. The request doesn't say which way the servo goes in, and that's deliberate (Dan, 2026-11-07): it matters only once the plate is part of something bigger, like the arm, and the person says they'll work out how it fixes to the base later. On its own the print can go either way. The two ways aren't graded evenly, though: from above can't pass on the records, because the cable's size was never measured.

## The checks, and what the records decide

The servo's place on the plate comes from the plate's own cutout: the opening the body fits through gives its centre and which way it runs. Nothing depends on #23's `assembly` format.

| Check | Class | Asks | Record | Fails | Passes | Not graded |
|---|---|---|---|---|---|---|
| R1 | C2 | The body goes through the cutout | D_servos, MG996R row: 0.25 a side over 40.58 x 19.82 seats, slightly loose | Smaller than the body (under 0 a side) | 0.25 a side or more | 0 to 0.25 a side: nothing printed there |
| R2 | C3 | A screw through each tab hole goes into a hole in the plate | Hole spacing end to end: 49.19 measured (inside edges 44.61 + hole 4.58), 49.5 datasheet. Across each tab: 10, datasheet only. Tab hole 4.58 | Misses a plate hole at both spacings, or the screw is wider than the tab hole | Lands at both 49.19 and 49.5 | Lands at only one; only in the open end of the U-slot; a blind hole; no screw in the hardware list |
| R3 | C5 | The tabs sit flush on the plate | Rib 1.51 wide, 1.8 proud (Dan's readings); D_servos: from above, stopped at the cable exit with 0.25 past the case end | From underneath: under 1.8 mm of room, or narrower than the rib. From above: 0.25 or less past the case end. Nothing under a tab | From underneath: room 1.8 deep and the rib's width plus 0.25 a side | Room for the rib with less than 0.25 a side; from above with more than 0.25 past the case end |
| `builds`, `connected_bodies`, `bed_fit`, `bridges` | C6 | Generic checks, on every task | | | | |

R3 takes the best of the ways to seat it: it passes if one way passes, else it's not graded if one way is, else it fails.

### R1: the cutout

Only the MG996R row applies directly. The MG90S went in snug at 0.15 and less snug at 0.3, but it's a different servo, with a different body and finish, so its rows aren't carried over: they're context, not a limit. A looser cutout isn't graded down, because the screws through the tabs locate the servo, not the cutout's sides; at 0.25 the servo was slightly loose and all four holes still lined up. A cutout so big it leaves nothing under the tabs fails R2 and R3 instead.

### R2: the screw holes

A screw's axis has to sit where the screw fits in the tab hole (a circle 4.58 across, at the spacing the records give) and where it goes into the plate: anywhere it fits in a clearance hole, or at the middle of a hole narrower than the screw, where it cuts its own thread. The screw is the thinnest one in the design's hardware list. The tab holes are U-slots open to the tab's end, but how far the tab runs past them wasn't measured, so a plate hole further out than the hole's centre is not graded.

What test print D's slots establish: they ran ±1 mm along the servo around 49.19, and all four tab holes showed through. That fits both 49.19 and 49.5, and doesn't tell them apart, so R2 asks for both. Each slot spanned both of a tab's holes, so the 10 mm across each tab was never tested; it rests on a datasheet value the catalog cites, which the datasheet Dan attached doesn't contain. It doesn't establish that a round hole at 49.19 lines up either; that's arithmetic on the readings.

### R3: the rib, and the cable

The rib is placed midway between each tab's two holes, as the catalog and the photo notes describe it ("between them", "the middle notch"). Dan's third reading, 8.31 "from the side of the holes to the middle notch", isn't used: read as running from a hole's outer edge to the rib's middle, it would put the holes about 12 mm apart, not the datasheet's 10, so which edges it runs between isn't clear. How far the rib runs along the tab wasn't measured either, so the check covers the whole stretch from the case to the far edge of the holes.

The rib's width needs room, and no relieved plate has ever been printed, so "rib cleared" is geometry, not a print result. Room narrower than the rib fails. To pass, the room has to be the rib's width plus 0.25 a side: the clearance the body itself needed in the same kind of printed opening, carried over from R1's record to the rib as a labelled extension. Between the two is not graded. Depth is read layer by layer, and 1.8 mm is nine 0.2 mm layers, so 1.8 is enough. Room out past the plate's far face counts, so a slot through a plate thinner than 1.8 clears the rib. Both tabs are one flat flange, so they have to meet the plate at the same height: supports at two heights fail, whatever room each gives the rib.

From above, the only record is a plain cutout at 0.25 past each end, and the servo stopped at its cable exit. The cable exit was never measured, so a cutout with more room past the case end, a notch for the cable or a plain cutout looser than 0.25, is not graded. So the route from above can never pass on the current records. That's a limit of the eval, reported as such: no new measurement is part of it.

## Known limits

- **A plain cutout looser than 0.25 a side isn't failed.** It fails from underneath (the rib), but from above it's not graded, since the cable exit was never measured. So the trap fails a design only if it would fail from underneath *and* matches test print D's 0.25 at the ends. Models that pick a looser cutout and forget the rib come back not graded on R3, and their detail says the rib had no room. The records can't close this gap, so it's reported as a limit of the eval.
- Whether the manual's way of seating the servo matches the face with the rib's room isn't checked: the plate is read both ways up, and the manual is text.
- Only holes clear through the plate are read for screws. A blind hole is not graded.
- Nothing below or above the plate is checked: whether a box under it is deep enough for the 40.4 mm body, or whether the shaft clears anything.
- Load isn't graded: there's no torque or strength data.
- The optional arm on the shaft (5.94 a hard push, 6.04 snug, 6.14 loose, test print E) is left out, to keep this task to the mount.
- The tab's outline beyond its holes, and the case's corner radius, weren't measured. A cutout with rounded corners reads tighter at its corners, which can only move R1 toward not graded.
