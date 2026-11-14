## 2026-11-13: Five check changes from Dan's review of the Estoa failures; Estoa regraded

From Dan's marks on the Estoa review page (saved under `results/reviews/estoa-2026-11-13/`) and his answers in the session:

- **The disk is 1.6 mm thick.** R1, R2, R3 and R5 take the LED disk as the standard 1.6 mm board instead of 1.2 to 2.0. Dan: "do 1.6mm thats fair". Screws that fit 1.6 but not the whole range had been not graded.
- **R6 keyholes hang on some common nail or screw.** A keyhole passes when a wire nail, an 8d box nail, or a #6, #8 or #10 pan-head screw has a head that passes its entry with 0.2 mm a side, a shank that slides along its slot, and a head the slot holds. The slots must still run the same way, and the screw mustn't rest inside the entry. The plastic's thickness at the slot no longer fails it, because the person sets how far the fastener stands out. Dan: "r6 can hang on a common nail, tahts fine"; "Fine if the screws can just go further out". Before, every common screw from #6 to #10 had to fit, 3.5 mm out of the wall.
- **Roof slivers.** A strand lying wholly within `small_overhang_mm` (1.5 mm) of the layer below counts as anchored. Opus 5.5's Estoa t5 had failed on two 0.5 mm stubs at the corners of a 12 mm bridge whose every full strand landed (Dan: "i think it would be fine"). `tests/test_bridges.py`'s slot-cut roof now passes: its strands run wall to wall beside the slot.
- **A board within the box's outline is inside the box.** R3 and R5 no longer fail a board for an open side when it sits within the printed parts' outline seen from the front, with plastic or the wall behind it and plastic or the disk in front. GPT-6.1 Sol's 96 mm access notch and wrap-round windows had failed it (Dan: "it looks like its inside the box to me").
- **R4 passes for now.** A design with no heat-set inserts, or with inserts whose posts can't be judged for bulging, passes R4 instead of being not graded; insert holes are still checked against the 3.9 to 4.9 mm a 4 mm insert fits. Dan: "why don't we make it pass for now, and then, in the future, we can decide if we want to regrade it? I'd rather have more passing things, honestly." A later regrade can tighten it.

Regrade of every run and replay. Only Estoa moved:
- first print 1 → 5 of 30 (Opus t1, Opus t5, Sonnet 5.5 t3, GPT-6.1 Sol t2, Opus t2 as before);
- second print after feedback 5 → 12 of 26;
- with test prints 0 → 4 of 18 (Sonnet 5.5 t3, DeepSeek V4.1 Flash t2, GPT-6.1 Sol t1 and t3).

What's left not graded on the other first-print and test-first designs is R1 (where the disk's holes are). The 1.6 mm disk failed two second prints that had been not graded, by 0.4 mm each (Gemini 4 Argon t1 and Haiku 5.5 t2).
