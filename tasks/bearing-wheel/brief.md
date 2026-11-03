# Bearing wheel

**UNREVIEWED WORDING.** Claude wrote this request on 2026-11-03 for an exploratory run. Dan hasn't seen it. The door, the old wheel's size and the bolt are invented; the bearings and how they fit on this printer are real. Results from it are learning, not results to publish, until Dan has reviewed the wording.

> The roller wheel on my sliding closet door snapped. I've got two 608 skateboard bearings and an M8 bolt I could use. Could I 3D print a new wheel that spins on the bolt? The old one was about 50 mm across and about 16 mm wide.

The request states a problem and leaves the mechanism to the model. The hardware list, which every task gets, has the 608.

## Why it's hard

Round 2 printed plain round seats and pressed real bearings in. The nominal 22.0 mm won't take the bearing, so a design drawn from the catalog's size fails; there's no rule of thumb that gives 22.1 to 22.3 without printing (class C2).

A seat on each side of a wheel forces one seat to open at the bed, and its roof has a hole in it. That's the bridged-hole problem the Arca plate's first print tangled on (C6). 16 mm is just room for two 7 mm bearings, so the easy answers run out: a model can step the roof, split the wheel in two, or stack both bearings from one side.

## What class each check belongs to

| Check | Class | Asks |
|---|---|---|
| R1 | C5 | About 40 to 60 mm across, at most 20 mm wide |
| R2 | C5 | Depth for two 7 mm bearings |
| R3 | C2 | Each seat is a size that holds, or a coupon finds one and a param applies it |
| R4 | C3 | An M8 bolt passes |
| `bridges` | C6 | Generic check, on every task |

## What the records decide

| Reading | Verdict | Where it comes from |
|---|---|---|
| Seat 22.0 mm or under | fails R3 | Round 2: 22.0 won't go in |
| Seat over 22.0, under 22.1 | not graded | Nothing printed |
| Seat 22.1, 22.2, 22.3 | passes R3 | Round 2: each went in and held upside down |
| Seat over 22.3 | not graded | Nothing printed. Some way above it must be loose, but no print says where |
| Ribs, lobes or a slot in the seat | not graded | Only plain round seats were printed |
| Seat 0.1 to 0.5 mm short of the bearings | not graded on R2 | Nothing printed. GPT-6 Luna's 6.8 mm seats leave the bearing 0.2 mm proud, which no record rules out |
| A through bore with no shoulder | not graded on R2 | Only the press fit places the bearings. Round 2's seats had floors, and no print tried this |
| Bolt hole under 8.0 mm | fails R4 | The bolt is 8 mm |
| Bolt hole 8.0 to 8.4 mm | not graded | No print of a hole this size against an M8 |
| Bolt hole 8.4 mm or more | passes R4 | ISO 273's fine clearance hole |

R1's numbers are the invented request's, so a wider wheel failing says only that the model didn't follow the request. Both seats in round 2 were one coupon, in black PLA; the seats' depth and which face opened at the bed weren't varied.

## Not checked

Whether the middle of the wheel presses on the bearing's inner ring, which would stop it spinning freely once the bolt is tight. A shoulder should touch only the outer ring. Nothing recorded says how much that matters on a printed wheel, so it's reported from the runs, not graded.

## Known limits

A tyre ring and a hub nested inside it, as two final parts, add up to too wide a wheel on R1. A through window 20 to 26 mm across could be read as the bore, though at 50 mm across there's hardly room for one. A short too-tight ring inside a seat much deeper than it needs isn't seen.
