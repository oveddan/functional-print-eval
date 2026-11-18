## 2026-11-17: Estoa: Dan's readings of the LED disc, the perfboard and the ESP32 in the checks and in what the person says, and the disc's holes where Estoa printed them (no result changed)

Dan measured the parts the Estoa trials kept asking about, in the eval session on 2026-11-17:

| Reading | Value | Before | Trials that asked and got no number |
|---|---|---|---|
| LED disc diameter | 242 mm | not measured; the Estoa build took 242 from the product listing | 65 of 65 |
| LED disc thickness | 1.56 mm | not measured; the checks took the standard 1.6 mm (Dan, 2026-11-13) | 64 of 65 |
| Perfboard thickness | 1.60 mm | not measured; R5 took it as at least 1 mm | 62 of 65 |
| ESP32's tallest point, from the perfboard's bottom | about 18 mm, so about 16.4 mm above its top | "about 16 mm" above the perfboard | — |

He gave 250.4 mm and then 240.5 mm for the diameter before 242. Both were corrected in the session, and neither is used.

**The disc's holes.** R1's range for each hole's center was 16.60 to 17.11 mm from the disc's center. That was the spread between Dan's direct reading (30.2 mm between the holes' inner edges, so 33.5 mm center to center) and his edge readings on a 242 mm disc (33.9). The measured 242 mm doesn't settle which is right, since the far end of the range already used 242. **Dan's call (2026-11-17):** "whatever the Estoa print did for the center holes, that's the correct size". Estoa printed them 16.81 and 17.11 mm from the center (`disk_puck.scad`, on the 242 mm disc), so the range is now 16.81 to 17.11 mm. Which hole is which in a design isn't recorded, so each can be anywhere in that range. The stated assumption moves with it, to the middle, 16.96 mm.

**In the checks** (`tasks/estoa-light/requirements.yaml`):
- R1, R2, R3 and R5 take the disc as 242 mm across (`board_radius`, `disk_radius` 121.0, up from "at least" 120.5) and 1.56 mm thick.
- R5's slab is the perfboard's 1.60 mm, up from 1.0.
- R5's room, and R2's possible ESP32, go up to 16.4 mm, from 16.
- R1 and R2 use the narrowed hole range.

**In what the person says** (`tasks/estoa-light/hidden_facts.yaml`): the disc's diameter and thickness, the perfboard's thickness and the ESP32's height now have the readings. The charger plug's head, which Dan measured on 2026-11-12 for R3 (11.58 × 6.44 mm with about 7.5 mm of bare metal, `catalog/connectors.yaml`), is added as a new item. 52 of the 65 saved Estoa trials asked about the plug or cable and heard nothing. None of this reaches a saved trial: its conversation stays as it ran, and only later runs hear the readings.

**Regrade.** Every saved Estoa trial was graded again: `pilot-estoa`, `pilot-estoa-carbon` and `test-first`, 61 with a design. So was every arm of `loop-estoa`, 78 with a design, regraded with `coupon_loop.grade` and saved in place, as PR #20 did. No verdict changed anywhere: no pass, fail or not graded moved, in the first prints, the reprints after feedback or the test-prints-first trials. The findings' text did change: the new range, room and thicknesses. The 21 R1 verdicts left not graded stay that way: the narrowed range still holds the spot where those designs' screws stop going in. The assumption records (`assumed.json`) were made again with the new range and midpoint, for the first prints too, so the reference's Estoa assumptions table now covers all 61 designs (49 before). Under the assumption, R1 is decided for 21 of the 26 not graded, all 21 passing. R2's assumption decides none (2 pass and 2 fail of 49 before): its remaining not-graded verdicts rest on the heights of the parts on the perfboard, not on the holes.

Why nothing moved: the readings are close to what the checks already assumed. The disc is 0.04 mm thinner than 1.6. Its edge was already within 0.5 mm. And no saved design puts plastic within a millimeter of the old R5 limits. Most Estoa failures are roofs over open air (31 of 41) and the plug's opening (9), which none of these readings touch.

Checks: `scripts/update_tables.sh --check` passes. `tests/test_estoa_light.py` expects the person's new answers (it pinned "I can't measure that" for the disc's thickness). `tests/test_prompt_rule.py` has the new hash for Estoa's all-given prompt, which lists every fact the person knows.
