## Where the lookup answers: agreement with its facts

| Model | Same set of facts | Facts on the same side | Picked a fact the lookup didn't | Left out a fact the lookup gave |
|---|---|---|---|---|
| GPT-6 Luna | 564/2330 (24%) | 16909/19940 (85%) | 347/2330 (15%) | 1672/2330 (72%) |
| Gemini Decision 1 | 664/2330 (28%) | 16984/19940 (85%) | 691/2330 (30%) | 1329/2330 (57%) |
| Jev 1.14 | 505/2330 (22%) | 16805/19940 (84%) | 275/2330 (12%) | 1755/2330 (75%) |

Hand sample of 25 Jev disagreements: nearer to what was asked, the judge 17, the lookup 6, neither 2.

## Where the lookup says "I can't measure that"

| Model | Picked a fact | Read by hand | Same facts as Claude's hand check | Found a recorded fact asked for | Picked a fact not asked for | Real misses caught |
|---|---|---|---|---|---|---|
| GPT-6 Luna | 6/358 (2%) | 6 | 3 | 3 | 3 | 3/4 |
| Gemini Decision 1 | 54/358 (15%) | 54 | 3 | 4 | 51 | 4/4 |
| Jev 1.14 | 7/358 (2%) | 7 | 3 | 3 | 4 | 3/4 |

Failed calls: none

## Every turned-away request a model picked a fact for

| Request (task, item, what) | GPT-6 Luna | Gemini Decision 1 | Jev 1.14 | Claude's hand check |
|---|---|---|---|---|
| bearing-wheel / broken closet door wheel / diameter of the wheel's centre hole, and the diameter of any flange or lip at each end | - | bearing.bore | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / broken closet door wheel / width of the rolling tread (the flat or grooved surface that rides the track) | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / broken roller wheel / cross-section profile (is the outer rim flat, concave/grooved to ride on a track, or convex?) and the exact width and outer diameter | - | bearing.od, bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / broken roller wheel / outer profile shape (is the rim flat, concave/grooved to ride a rail, or crowned/convex?) and exact diameter and width | - | bearing.od, bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / broken roller wheel / rim shape (flat, concave U-groove, or V-groove) and outer diameter | - | bearing.od | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / closet door roller installation / Please describe just these points: is this wheel at the bottom supporting the door, or at the top hanging the door? Is the rolling surface flat or grooved? Can you measure the bracket's clear width for the wheel? If you cannot tell, please say so. | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old (broken) wheel / width from one flat face to the other, in mm | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old broken roller wheel (largest surviving piece) / outer diameter across the wheel | - | bearing.od | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old broken roller wheel / profile of the rolling surface: width of the flat or groove, and whether it has a V or rounded groove, and its depth | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old broken roller wheel / width/thickness of the wheel | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old closet door roller wheel / overall width of the wheel (face to face) and the outer diameter; also how the rim is shaped (flat tread, or a groove/V that rides a track) | - | bearing.od, bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old door roller wheel / thickness of the wheel's rolling face where it runs in the track (its width), and the depth of the groove or flange if it has one | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller and closet door / Is this wheel at the TOP suspending the door, or at the BOTTOM supporting it? What shape is its rolling edge: flat, rounded, or a groove? Can you measure the old wheel width and diameter more closely than about 16 × 50 mm? | - | bearing.od, bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller and closet track / Is this a bottom roller carrying the door's weight, or a top guide? Describe the wheel's running edge and track: flat, rounded, V groove, or U groove. If any old wheel remains, measure its diameter and width. | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller and door track / Is this wheel underneath the door carrying its weight, or a guide at the top? Is the rolling surface flat, grooved (concave), or raised/rounded (convex)? Please measure the old wheel's actual outside diameter and width, any groove width/depth, and the gap between the bracket sides where the wheel fits. | - | bearing.od, bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller wheel (or the slot it runs in) / exact width of the wheel where it contacts the track (the rolling width), to confirm it's 16 mm | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller wheel / its track / rim profile: is the tread flat, V-grooved, or U-grooved? If grooved, groove width and depth. Also the old wheel's centre hole diameter | - | bearing.bore | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller wheel / diameter of the hole through the centre (or the metal bushing's bore) | - | bearing.bore | bearing.bore | none recorded: the old wheel's hole or bushing, not the new 608 bearing's bore; the old wheel isn't recorded |
| bearing-wheel / old roller wheel / exact outer diameter, thickness/width, and whether the outer edge is flat or has a groove/channel for the track | - | bearing.od | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller wheel / exact outer diameter, width, and edge profile (flat or grooved?) | - | bearing.od, bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller wheel / exact outer diameter, width, and profile shape (flat, grooved, or rounded edge) | - | bearing.od | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller wheel / exact outer diameter, width, and profile shape (flat, grooved/convex, rimmed, etc.) | - | bearing.od, bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller wheel / exact width (thickness across the wheel) | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller wheel / outer diameter, thickness/width, and rim profile (flat, grooved, or convex/rounded to ride in a track) | - | bearing.od, bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller wheel / outer diameter, width, and edge profile (e.g. flat, concave groove, convex, or flanged) | - | bearing.od | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller wheel / overall width/thickness in mm | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller wheel / profile shape (is it flat, convex/crowned, or does it have a groove or flange?) and exact outer diameter if measurable | - | bearing.od | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller wheel / rim profile (flat, concave/U-groove, convex), exact outer diameter, width, and how it mounts to the door bracket | - | bearing.od, bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller wheel / the exact diameter and width of the remaining pieces, if measurable | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old roller wheel / width, face to face, and say whether the tread is flat, grooved or flanged | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old snapped wheel / outer diameter across the rolling surface (the part that touched the track) | - | bearing.od | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old snapped wheel / width at the groove/rolling surface (how wide the contact patch is) | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old wheel and closet door track / exact outer diameter and width of the old wheel, and whether the rim is flat, rounded, or grooved (V/U groove) to fit a rail, plus the width/shape of the track it rides in | - | bearing.od | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old wheel and closet track / Does this wheel carry the door's weight, or just guide it? Is its outside edge flat, rounded, or grooved? If grooved, measure the groove width and depth. | - | - | bearing.od | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old wheel and closet track / Is the wheel's rolling edge flat, rounded, or grooved? Does it support the door's weight, or only guide the door? Please give wheel diameter and width if you can; your approximate 50 mm diameter and 16 mm width are useful starting points. | - | bearing.od, bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / old wheel / outer profile (is the outer rim flat, concave, or V-grooved?) and exact outer diameter and width | - | bearing.od, bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / one of the 608ZZ bearings / outer diameter across the outer ring only (I have an earlier 21.2 mm reading that looks like it was taken at an angle, so please re-check it) | bearing.od | bearing.od | bearing.od | bearing.od: the 608 bearing's outside diameter, plainly; the lookup missed it because "bearings" and "608ZZ" aren't whole-word aliases |
| bearing-wheel / one of the 608ZZ bearings / width — the thickness across its two flat faces (measure it, don't assume 7 mm) | bearing.width | bearing.width | bearing.width | bearing.width: the 608 bearing's width, plainly; missed for the same plural and 608ZZ reason |
| bearing-wheel / the biggest surviving piece of the broken old wheel / the widest distance across the part that touched the track (its diameter) | - | bearing.od, bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / the broken old wheel / the tread — the surface that touches the track: is it flat, barrel/round-crowned, or does it have a groove running around the middle? Give me its width, and if there's a groove its width and depth | - | bearing.od, bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / the broken roller wheel (or its largest surviving piece) / the outside diameter across the running surface — the round face that touched the track — in mm | - | bearing.od | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / the broken roller wheel pieces / outside diameter of the round part | - | bearing.od | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / the broken roller wheel / diameter across the tread, overall width at the hub, and whether the tread is a plain flat cylinder or has a groove/flanges (a photo-level description is fine) | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / the broken roller wheel / its overall diameter, its overall width, and whether the running surface (rim) is flat across or has a groove/ridge — if grooved, the groove width and depth | - | bearing.od, bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / the broken roller wheel / outside diameter across the running surface (tread), in mm | - | bearing.od | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / the broken roller wheel / outside diameter across the tread (the part that touches the track) | - | bearing.od | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / the broken roller wheel / overall width across the hub faces | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / the broken roller wheel / the outside diameter across the tread (measured away from the break), and whether the running surface is flat or has a groove — if it has a groove, its width and depth | - | bearing.od | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / the broken roller wheel / the shape of its running surface: is it a plain flat cylinder, or is there a groove (V or curved) running around the middle? If a groove, tell me its width across and its depth | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / the broken roller's wheel / width (thickness) of the wheel | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / the broken wheel / the wheel's overall width, side face to side face, in mm | - | bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / the old broken closet-door roller wheel / the running surface: is the outer edge flat across its ~16 mm width, or does it have a groove/flange? If grooved, the groove width and depth, plus the exact outside diameter and width | - | bearing.od, bearing.width | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / the old wheel's running edge — the part that touched the track / is it a plain flat band like a bicycle tyre, or is there a groove/ridge running around it? Flat or grooved — either answer is fine | - | bearing.od | - | none recorded: asks about the broken old wheel, the door bracket or the track, which the task doesn't record; the 608 bearing isn't the old wheel |
| bearing-wheel / the two metal plates on the door that the wheel sits between / distance between the inner faces of those two plates, in mm | bearing.width | - | bearing.width | none recorded: the bracket's inside gap, not the bearing's width; the bracket isn't recorded |
| estoa-light / diffuser / dimensions or how the front and sides attach to the box | led_disk.diameter | - | - | none recorded: the diffuser is part of the design, not the person's thing; nothing recorded |
| estoa-light / own:m2x6-self-tapping / head diameter and head height | wall_screws.size | - | wall_screws.size | none recorded: the designer's own M2x6 screws for the board, not the wall screws; nothing recorded |
| estoa-light / wall mounting screws / head diameter, shaft diameter, and spacing between the two screws if already on the wall | wall_screws.size, wall_screws.spacing | wall_screws.size, wall_screws.standoff, wall_screws.spacing | wall_screws.size, wall_screws.spacing | wall_screws.size, wall_screws.spacing: the wall screws' head and shank (size) and their spacing; "wall mounting screws" isn't an alias ("wall screw" is) |
| tripod-plate / plate / size | - | tripod_clamp.plate_width | - | tripod_clamp.plate_width: the size of the missing plate is the width of plate the clamp takes, recorded as 38 mm; "plate" is an alias of the measurement, not of a thing, so the lookup found no thing |

## Real misses

| Task | Real misses (distinct requests) | Times asked | Measure calls in all |
|---|---|---|---|
| bearing-wheel | 2 | 2 | 797 |
| estoa-light | 1 | 1 | 612 |
| tripod-plate | 1 | 1 | 1329 |

| Contestant | Real misses (distinct requests) | Times asked |
|---|---|---|
| deepseek/deepseek-v4.1-flash | 2 | 2 |
| google/gemini-4-argon | 2 | 2 |

## Every version against Claude's hand keys

The p ≥ 0.8 and slot ≥ 0.9 bars were chosen on the hard key, after seeing its answers; the random key is the fresh check on them.

### Random key (200 requests)

A random 200 of the 2,688 requests (`measure_random_sample`): what ordinary use looks like.

| Version | Exactly the facts asked for | Picked a fact not asked for | Left out a fact asked for |
|---|---|---|---|
| today's lookup | 87/200 (44%) | 107 | 24 |
| GPT-6 Luna, yes/no per fact | 152/200 (76%) | 30 | 20 |
| Gemini Decision 1, yes/no per fact | 127/200 (64%) | 69 | 8 |
| Jev 1.14, yes/no per fact | 153/200 (76%) | 22 | 28 |
| Jev 1.14, yes/no per fact, p ≥ 0.8 | 143/200 (72%) | 10 | 50 |
| Jev 1.14, count + list (7b) | 137/200 (68%) | 18 | 46 |
| Jev 1.14, count + list, slot ≥ 0.9 | 130/200 (65%) | 0 | 70 |
| Jev 1.14, facts as the person says them (7c) | 146/200 (73%) | 14 | 42 |
| Jev 1.14, facts as said, p ≥ 0.8 | 134/200 (67%) | 2 | 64 |

### Hard key (107 requests)

Every turned-away request any judge picked a fact for, and the 25-request sample of Jev's disagreements: hard cases, so it compares versions; it isn't a rate.

| Version | Exactly the facts asked for | Picked a fact not asked for | Left out a fact asked for |
|---|---|---|---|
| today's lookup | 83/107 (78%) | 20 | 4 |
| GPT-6 Luna, yes/no per fact | 95/107 (89%) | 8 | 5 |
| Gemini Decision 1, yes/no per fact | 42/107 (39%) | 64 | 1 |
| Jev 1.14, yes/no per fact | 93/107 (87%) | 8 | 7 |
| Jev 1.14, yes/no per fact, p ≥ 0.8 | 100/107 (93%) | 1 | 7 |
| Jev 1.14, count + list (7b) | 49/107 (46%) | 52 | 7 |
| Jev 1.14, count + list, slot ≥ 0.9 | 97/107 (91%) | 0 | 10 |
| Jev 1.14, facts as the person says them (7c) | 99/107 (93%) | 2 | 7 |
| Jev 1.14, facts as said, p ≥ 0.8 | 97/107 (91%) | 0 | 10 |

Turned away by the lookup: count + list (7b) picked a fact for 52/358 (15%).

## Test 7d: the random 200 as single asks

479 single asks: requests Jev counted as one thing stay whole; a fresh subagent split the rest without seeing the facts, the lookup or any judge; a second fresh subagent keyed each ask from the fact list alone (`7d-asks.json`). Jev answered each with one pick: a fact, or not recorded.

| Per single ask | Right | Picked a fact not asked for | Left out the fact asked for |
|---|---|---|---|
| today's lookup, on the single ask | 192/479 (40%) | 287 | 20 |
| Jev 1.14, one pick | 413/479 (86%) | 14 | 57 |

Same reply to the designer as the key's fact would give (a fact recorded as "I can't measure that" says the same as no fact): lookup 196/479 (41%), Jev 419/479 (87%).
Of Jev's 60 asks with a different reply, the keyer marked 52 as close calls, and 29 are the clamp's plate width asked in other words.

### Whole requests, against the subagents' key (200 requests)

Each request's key is the facts of all its single asks. Same 200 requests as the random key.

| Version | Exactly the facts asked for | Picked a fact not asked for | Left out a fact asked for |
|---|---|---|---|
| today's lookup | 84/200 (42%) | 110 | 21 |
| GPT-6 Luna, yes/no per fact | 158/200 (79%) | 30 | 15 |
| Gemini Decision 1, yes/no per fact | 130/200 (65%) | 70 | 2 |
| Jev 1.14, yes/no per fact | 161/200 (80%) | 21 | 21 |
| Jev 1.14, yes/no per fact, p ≥ 0.8 | 148/200 (74%) | 9 | 46 |
| Jev 1.14, count + list (7b) | 143/200 (72%) | 19 | 41 |
| Jev 1.14, count + list, slot ≥ 0.9 | 136/200 (68%) | 0 | 64 |
| Jev 1.14, facts as the person says them (7c) | 147/200 (74%) | 17 | 40 |
| Jev 1.14, facts as said, p ≥ 0.8 | 140/200 (70%) | 2 | 59 |
| Jev 1.14, single asks (7d) | 152/200 (76%) | 12 | 40 |

The subagents' key and Claude's key agree on 184/200 (92%) of the 200 requests.
