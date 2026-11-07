# Servo arm

**Wording approved by Dan on 2026-11-07** ("I approve this message"). The request is his, from 2026-11-07, with the 90° he first gave loosened to "swing both ways" at his suggestion.

> I want to prototype the first version of a robot arm. I have an MG996R servo and a 608 bearing to work with. It should swing both ways, and the arm should be about 100 mm long.

The person has a real MG996R, and every reading is Dan's. Results from this task are a first look, outside the headline numbers, like servo-mount's. Nothing here has been run on a model yet.

## Why it's hard

It's the next step from servo-mount: the servo still has to be held (with the same rib between each tab's holes, class C5), and now something has to turn on it. The fits all come from Dan's test prints, so a design that sizes them from nominal values or guesses misses (class C2):

- The arm presses onto a 5.84 mm spline. Test print E: 5.94 was a hard push, 6.04 snug, 6.14 loose. A bore at the reading itself, or a typical "+0.4 for printing", is wrong on this printer.
- The 608 goes into a seat. Round 2: 22.0, its nominal outside diameter, wouldn't take it; 22.1 to 22.3 held it upside down.
- The arm has to turn without hitting the base it's mounted on, or the servo's own case (C5). Nothing measured says where the shaft is on the servo; the person, asked, says "near one end of the case, in the middle side to side". A designer has to ask, look it up, or leave room.

## What the person knows

`prompt.yaml` leaves the `servos` section out of the hardware list, as servo-mount does, so the servo's readings come from `hidden_facts.yaml`: servo-mount's (body, tabs, rib, cable exit) plus the spline (5.84), where the shaft is in words, the range the listing gives (about 120°, 60 each way) and the horns in the box. The aluminium horn's hole positions were only estimated from a photo, so the person doesn't give them. The 608 is in the hardware list every prompt shows.

**The horn's holes (Dan, 2026-11-07):** assume they're threaded for M3, so an arm can bolt to the horn with M3 screws, which are on the hardware list. Their 2.55 mm reading fits an M3 tap drill, but nobody checked. This isn't in `hidden_facts.yaml` yet: the first-look run (`results/first-look/servo-arm-first-look`) went without it, and its last four trials still have to be run the same way. It goes in before the next run.

`can_ask_datasheet` hands over servo-mount's two datasheet pages. Its drawing is the only source for where the shaft sits, and its text gives the 120°.

## The checks, and what the records decide

R1 to R3 are servo-mount's checks with the same arguments; see `tasks/servo-mount/brief.md` for their records and limits. The arm's checks read the parts' own geometry: the arm is the final part (not the one the servo mounts in) with a plain round bore the shaft's size; the bearing's seat is any plain round hole 20 to 26 mm across and at least the bearing's 7 mm deep.

| Check | Class | Asks | Record | Fails | Passes | Not graded |
|---|---|---|---|---|---|---|
| R4 | C2 | The arm presses onto the shaft and grips | Test print E, MG996R row: 5.94 a hard push, 6.04 snug, 6.14 loose | A plain bore 6.14 or wider | 5.94 to 6.04 | Tighter than 5.94 (5.84 wasn't reported); 6.04 to 6.14; teeth or slots in the bore; an arm on the aluminium horn; neither a bore nor a horn pocket |
| R5 | C2 | The 608 presses into its seat and stays | Round 2's 608 seats: 22.0 wouldn't go in; 22.1, 22.2, 22.3 went in and held upside down | 22.0 or tighter | 22.1 to 22.3 | 22.0 to 22.1; over 22.3; ribs or slots in the seat; no seat; no 608 in the hardware list |
| R6 | C5 | The arm is about 100 mm long | The request | Reaches under 85 or over 115 mm from the shaft (or the horn pocket's axis) | 85 to 115 | No shaft bore or horn pocket to measure from |
| R7 | C5 | It swings both ways, through the servo's range | The datasheet: about 120°, 60 each way. Shaft position estimated from its drawing (below) | Under 120° clear, whatever way the uncertain heights fall | 120° clear, whatever way they fall | Depends on them; another final part the design doesn't place; no shaft bore |
| `builds`, `connected_bodies`, `bed_fit`, `bridges` | C6 | Generic checks, on every task | | | | |

### R4: the shaft

Only plain round bores were printed, so a bore with flats, teeth or a clamping slot is not graded.

**On the aluminium horn.** With no bore on the spline, a pocket in the arm whose clear circle is the horn's 14.66 mm hub (up to 1.5 over, at least 1 mm deep, round or horn-shaped) stands in for the shaft's axis, so R6 and R7 grade the arm the same way. R4 is not graded for it: no pocket for the horn was printed, and where its screw holes are was only estimated from a photo (`horn_25t_aluminium.hole_centres_from_hub`, about ±1 mm). A shaft-sized hole on the pocket's axis is for the horn's screw, not a loose bore. Added after the first look: four of its eight designs used the horn, and Opus's and Sonnet's failed R4 on the screw hole before. A hole in the arm that's a clearance hole for a screw in the design's hardware list (up to 0.7 mm over the screw) isn't taken for the hub. If the arm has more than one shaft-sized bore, it passes if one grips. How deep the bore must be wasn't tested: test print E's bores went through an 8.4 mm block, and the spline's length was never measured, so any bore 3 mm or deeper is read.

### R5: the bearing

The same records and rule as bearing-wheel's R3. The request offers the 608 ("to work with") without saying what it's for, so where it goes is left to the design, and a design that doesn't use it isn't failed: R5 is not graded, with nothing to grade. Whether the bearing lines up with the shaft, if it's meant to, isn't checked.

### R6: the length

Read from the arm's own geometry: the farthest point of the part with the shaft's bore, from the bore's axis. "About 100 mm" is read as 85 to 115. That band is a reading of the request, not a print record: Dan can change it.

### R7: the swing

The arm can go onto the 25-tooth spline at any angle, so it passes if there's a clear arc of 120° somewhere around the shaft, wherever it starts: no rest position is needed. "Clear" means no part of the arm, turned through that arc, meets the part the servo mounts in or the servo's own case and tabs.

Where the shaft is comes from the datasheet drawing, measured in pixels on 2026-11-07 (`catalog/datasheet_estimates.yaml`): on the case's centre line, 10.3 mm from one end by the 40.3 dimension in both the side and top views. The drawing isn't to scale (its 40.3 and 53.6 give scales 10% apart), so 9.3 to 11.3 is used. Its heights disagree with Dan's readings by about 2 mm, so how high the arm sits above the case top is taken anywhere from 0 to 10 mm. The check tries every combination: the shaft at 9.3, 10.3 and 11.3, and the arm at each 0.5 mm from 0 to 10.

The person chooses some things, and the check gives them every choice: which end of the cutout the shaft goes at, which way up the servo seats (any way both tabs meet the mount, as R3 reads it), and, for a bore open at both ends, which way up the arm goes on. It passes if some choice is clear at every shaft position and height, fails if no choice is clear at any, and otherwise isn't graded.

Everything is read on a 0.5 mm grid, in 1° steps, so gaps under about a millimetre can read as contact: a near miss can only come back not graded or failed, not passed. The parts aren't placed relative to each other by the submission format, so a third final part, such as a bracket for the bearing, can't be placed: with one, R7 can fail but not pass.

## Known limits

- Load isn't graded: there's no torque or strength data, and an arm that's too heavy or too flexible can't be found.
- Where the shaft sits is an estimate from a drawing that's not to scale, labelled as such. Nobody measured it, and no one will: it's a limit of the eval.
- Height clearance rests on a 10 mm band, so an obstacle a few millimetres above the case top makes R7 not graded, even when a person could see it's clear.
- Whether the bearing lines up with the shaft, when a design uses it as a second support, isn't checked.
- How an arm holds the horn, clamping hubs and splined bores aren't graded: only plain round bores were printed.
- The servo's cable isn't in R7's obstacles; R3 handles it where the servo seats.
