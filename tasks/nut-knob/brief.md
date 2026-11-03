# Hand knob with a pressed-in $nut nut

The person's words are a draft until Dan writes or approves them.

> I want a hand knob for an $nut bolt, about $knob_d mm across, so I can tighten it without a tool. It's one printed piece. An $nut hex nut (ISO 4032) presses into the knob by hand and has to stay in when I turn the knob upside down, no glue. The nut sits fully inside the knob and can't be pushed out through the far side, and the bolt goes through the nut and out the other side.

## Why it's hard, before any model ran

The pocket has to grip a nut pressed in by hand, and how a printer sizes a hex pocket can't be
looked up. On Dan's X1C the right clearance changes with the nut, and in the opposite direction
to a rule of thumb: an M3 needs +0.2 mm over its across-flats and won't go in below that, an M5
holds at +0.0 and +0.1 and is loose at +0.2, and an M8 holds only at +0.0 (coupon B, round 1). So
no single clearance works for all three, and a person who knows printing would test-print
pockets first. The tripod build lost three rounds of prints to this (seed `nut-pocket-clearance`:
"Nut pockets at af+0.3 mm; every nut fell out"; its fix was "a calibration coupon first").

## How it's graded

A design passes the fit check if its pocket lands where the prints say the nut holds, or if it
comes with a test coupon that includes a pocket that holds and its pocket follows a param. Landing
by luck passes on one trial; pass^k across trials shows whether it was luck. A clearance no print
measured is reported as not graded, which isn't a pass. So is one coupon B calls "loose" that nobody
has turned upside down (M5 +0.2, M8 +0.1 and +0.2); +0.3 fails, because nuts fell out
at +0.3 on the tripod build (in PETG). No technique is required: the pocket can open up or down,
with or without a coupon.
