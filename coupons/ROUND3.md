# Round 3 test prints

Built by `coupons/round3.py`; predictions written before printing in `results/predictions/round3-coupons.yaml`
(`coupons/predict3.py`). Each piece answers a row of "What we couldn't grade" in the README.

## Print

- X1C, 0.20 mm layers, the same PLA as rounds 1 and 2, 4 walls, 15% infill, no supports.
- Every STL in `coupons/out/` whose name starts F, G, H, I, L, M or N, all on one plate (auto-arrange fits them).
- Print each one as it is modeled: z = 0 on the bed, no flipping.
- `L-post-8-solid`: set this one object to 100% infill (rectilinear, since the slicer refuses cubic at 100%).

## Printed

- 2026-11-11: every piece except `L-post-8-solid` on one plate, 0.20mm Standard @BBL X1C, 4 walls, 15% infill,
  the preset's own infill pattern, no supports, black high-speed PLA. The slicer estimated almost 3 hours.
- `L-post-8-solid`: to print on its own at 100% infill (not yet).
- 2026-11-11, round 3b (`coupons/roof_crops.py`, predictions in `results/predictions/round3b-roofs.yaml`): the six
  `P-*` roof crops and the thin bridges `Q-span-60`, `-80` and `-100`, on one plate, same settings, printed as modeled.

## Try each piece and say what happened

| Piece | What to do | What to report |
|---|---|---|
| F bolt holes | Push the M8 bolt through each hole in the M8 row, the 1/4-20 bolt through each in the Q row. Dots on the near edge count up from the smallest hole (no dot). | Per hole: won't go, screws in only, goes through with drag, slides |
| G ring roofs | Look at each roof from underneath. | Per cell 1 to 10: clean, sagging, or loose strands |
| H bearings | Press a 608 into each seat, turn the block over, shake. For 5 to 7, how far the bearing stands out of the top, if you can see it. | Per seat 1 to 8: won't go in, presses in and holds, falls out; for 8, whether a push moves it through |
| I nuts | Press each nut in (M5 for U1 to U3, R1 to R3, L1, L2; M3 for R4, R5), turn over, shake. | Per pocket: won't go in, pressed in and holds, falls out; anything cracked |
| M servo mount | Push the MG996R up from underneath, shaft first, through each frame (0.0 and 0.1 a side, dots = tenths) and plate. On M1 and M2, check both tabs sit flat, and try an M3 screw through each of the four holes. M2's dotted end has the narrower rib channel. | Frames: goes through or not. Plates: tabs flat or rocking (which end), all four screws line up or not |
| N horn pockets | Set the 25T aluminium horn's hub into each pocket (dots: 0 = 0.1 over, 1 = 0.5, 2 = 1.0). | Per pocket: won't go in, tight, a little play, loose |
| L insert posts | Set an M3 x 4 x 5 insert in each post with the chisel tip, as on Estoa. | Per post (5.5, 6, 7, 8, 8 solid): held straight, bulged, flared, insert off-centre |

A sentence per piece is enough, and a photo where something failed. Answers go into the `outcome` fields of the
predictions file without changing any prediction.

## What each answers

| Piece | Not graded today | Trials |
|---|---|---|
| I (R1 to R5, L1, L2) | Nut pockets with crush ribs or a lip, the commonest shapes the models drew | 111 in the current runs |
| G (1 to 6) | Roof ledges 1.5 to 3 mm wide | 45 |
| F (M8) | Wheel bolt holes 8.0 to 8.4 mm | 21 |
| H (5 to 8) | Bearings a little proud, and a bore with no shoulder | 19 |
| F (Q) | Tripod bolt holes 6.35 to 6.8 mm | 18 |
| I (U1 to U3) | M5 pockets under the nut's size | 10 |
| H (1 to 4) | Bearing seats between and past round 2's sizes | 7 |
| M | servo-mount: a cutout 0 to 0.25 a side, whether a channel clears the tab's rib, and the 10 mm across a tab | its R1 to R3 (branch claude/servo-mount) |
| N | servo-arm: an arm sitting on the aluminium horn's hub | its R4 for horn designs (branch claude/servo-arm) |
| L | Whether Estoa's 8 mm posts bulged because of 100% infill (Dan, 2026-11-08), which the estoa task now assumes | the assumption behind R4 |

Not covered: keyholes, because the light should hang on any common wall screw and one screw can't show that; the tripod clamp's plate widths and head recesses (10 and 32 trials), because the clamp isn't to hand; snap-finger pockets (19 trials; each model's fingers differ too much for one print), lips on pockets
that open at the bed, and split collars.
