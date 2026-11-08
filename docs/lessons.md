# What makes this kind of eval hard

Raw material for Dan to rewrite. One lesson per entry, each with its evidence. Newest at the bottom.

## Grading

**A grader built from one reference fails correct designs that don't look like it.** The nut pocket's hexagon test was aimed at one point of the opening, so it missed hexes at other rotations and read a slot's end as the pocket. GPT-6.1 Sol was told "no hex pocket" and Grok "+0.50 falls out" for designs that had neither problem. Only reading the transcripts showed it. Evidence: commit d656f47. The first hole check did the same thing to chamfered spacers (`CHANGELOG.md`).

**Each wrong design needs its own check to fail, and only that one.** Otherwise one mistake counts several times in the failures by class. Checks that need a part another check already failed now say "not graded". Evidence: `tests/test_nut_knob.py`, `tests/test_tripod_plate.py`.

**One pilot found two eval faults for 20 cents.** The tripod's "which face goes down" check assumed the widest face sits in the clamp, and failed Gemini 3.8 Flash's correct plate with a groove in its side. The person answered a question about the camera's socket with facts about the clamp. Evidence: `results/runs/pilot-tripod`, Haiku's and Gemini's t1.

**A generic check can be wrong for one role of part.** `connected_bodies` failed Opus's M3 t2 for a test print of three separate pockets, which prints fine. Evidence: `results/runs/pilot-nut-knob-2/nut-knob/M3/can_ask/anthropic__claude-opus-5.5/t2`, fixed in be8b718.

**Model code breaks a grader in more ways than a person's would.** Eight came back as 8.0 and crashed `range()`, an omitted `role` defaulted a test print to the final part, split fingers read as "no hex pocket". Each looked like a model failure until read. Evidence: commit d656f47 and 18ecc26.

**Harness failures have to look different from model failures.** A dropped connection, a stuck call or a crash in a check can otherwise read as a model's mistake or lose a paid trial. Evidence: an Opus call sat open 15 minutes and blocked the queue on 2026-11-02; trials are saved before grading so a crash doesn't lose them (`pbe/eval.py`).

**A grader's idea of a hole was a closed hole.** GPT-6 Luna's plate has a proper 6.8 mm hole, with a channel so the head slides in from the end. The channel opens the recess at the side, so the check said "no hole runs through the plate" and failed R3. Another shape nobody anticipated, found by reading the part's code. Evidence: `results/runs/pilot-tripod`, Luna t1, commit 1b4344a.

**Most of a pilot's failures can be real and still need checking.** Of the first 12 tripod trials, one failure was the check's fault. Qwen's "no hole" looked like the same fault, but its plate really is solid: its cuts went the wrong way, away from the part. Each one took reading the part's code to tell apart. Evidence: `results/runs/pilot-tripod`, Luna and Qwen t1.

## How printing and use pull against each other

**The easy way to print a part can be the wrong way to use it.** The real plate prints wide face down with its recess on the bed, so the recess's roof has to bridge over a hole. Opus avoided the roof by putting the recess on top and flipping the plate for use, which leaves the dovetail upside down in the clamp. Sonnet's dovetail is upside down too, and its roof fails. Five other models (Haiku, DeepSeek Pro and Flash, Luna, GLM) kept the recess on the bed with a plain roof, the same thing that tangled on Dan's first print. Three found a way through: Gemini 3.8 Flash and Argon print narrow face down with the recess on top, Grok stands the plate on end. Evidence: `results/runs/pilot-tripod` t1; the real plate's `arca_plate.scad`, in Dan's private local-lights repo.

**One check can decide most of a task.** `bridges` failed 8 of the 12 first trials, and for Haiku, DeepSeek Flash, Luna and GLM it's the only failure. It rests on one tangled print. So how much that print's reading is trusted changes the headline, and the report should show results with and without it. Evidence: `results/runs/pilot-tripod` t1, `catalog/printer.yaml`.

**Dropping one check doubles the passes and reorders the models.** Across 34 tripod trials, 6 pass with `bridges` and 12 without it. Opus goes from 0 of 3 to 2 of 3 and GPT-6 Luna from 0 of 3 to 1 of 3; the Gemini models and Grok barely move. Opus never met both: t1 flips the plate to dodge the roof and ends up with the dovetail upside down, t2 and t3 keep the dovetail right and fail the roof. So the ranking depends on one tangled print. Evidence: `results/runs/pilot-tripod`, `findings` in each `grades.json`.

**A model's rank doesn't carry from one part to the next.** Opus and GPT-6.1 Sol go 0 of 3 on the tripod, and on the wheel each passes once and has one trial not graded, with no failure in either. Sol, which wouldn't commit to a plate, splits the wheel into two halves so neither seat has a roof; the numbers it needed were in the request. Opus cuts a printable cone where the plain roof would be. Meanwhile Grok isn't run here, and Gemini 3.8 Flash goes from 2 of 3 to 1 of 2. Two trials a model, on a request Dan hasn't seen. Evidence: `results/runs/pilot-wheel`, `pilot-tripod`.

**The same failure shows up on a different part.** `bridges` failed many wheels too, at the same kind of place: a seat open at the bed, its roof a ring around a hole. It fails 10 of 22 wheel trials and 18 of 34 tripod trials. So this class looks general, not a tripod quirk, and it's worth a generic check. It also means the same thin record carries more weight. Evidence: `pilot-wheel`, `pilot-tripod`.

**A textbook answer can be wrong for this machine.** Haiku, DeepSeek Flash and Qwen draw the seat under the bearing's size, 21.85 to 21.9 mm, because a press fit is normally an interference. On this printer 22.0 won't take the bearing. DeepSeek Flash and Qwen even ship a coupon on t1, but it tries only sizes at or under 22.0, so it can't find one that holds. On t2 their coupons reach a size that holds, and R3 passes: the same model, a different idea of what to test. Evidence: `pilot-wheel`, `results/predictions/round2-coupons.yaml`.

## What a test print teaches

**Models know how to fix a holed roof; they don't see it coming.** 28 of 84 tripod plates have a roof with the bolt's hole through it. Of the 24 saved before the test-print sample, each told only how it printed, "loose loops and tangles around the hole; hole partly closed", with no cause or fix, 14 fixed it, against 2 after "take another look". They found four different fixes. 8 flipped the plate, 3 used a cone, 1 left a skin to push out, and 2 (Gemini 4 Argon) drew the stepped bridge the Estoa model invented after its own test wall failed. That's how Dan got there too: the model's first design failed, and the fix came after he showed it the print. Evidence: `results/runs/loop-tripod`, `docs/coupon-loop.md`.

**A fix for one failure can surface the next one.** Most fixed plates still fail on what the report never mentioned, mostly the dovetail upside down, so passes went from 0 to 3. Three revisions got worse: a lost recess, a plate in pieces, a deck too thick for the bolt. Evidence: `loop-tripod`'s `loop.json`.

**A check can fail a known fix.** R3 failed Opus's drill-out skin as "no hole runs through", though `docs/plan.md` says a drill-out layer passes and the knob's check already allowed one. The tripod check had never met one. Evidence: `CHANGELOG.md`, 2026-11-06.

## What physical truth can decide

**Most of what models try, no print has measured.** Models chose ribs, clips, snap lips and undersized pockets, and the fit table only speaks for plain pockets. On M5, 7 of 12 trials came back not graded on R4. A check must be able to say "I can't tell", and that rate is a result to report beside the pass rate. Evidence: `results/runs/pilot-nut-knob`, `summary.csv`'s `not_graded` column.

**A fit table has less in it than it seems.** Coupon B's "loose" rows were never turned upside down, so they don't answer whether a nut stays in. Grip needs tenths, and a recorded fit only speaks for what was printed. Evidence: `results/predictions/round1-coupons.yaml`, commit 18ecc26.

**A fit with room to spare can be graded from far less.** A head in a recess or a plate in a clamp is wrong by millimetres, so one printed plate gives usable limits. Evidence: seed `arca-counterbore-guessed`, `tasks/tripod-plate/brief.md`.

**Some numbers have to be assumed, and the report must say which.** Nobody recorded the webcam bolt's length, so the tripod's reach check rests on a labelled 10 mm. Evidence: `tasks/tripod-plate/hidden_facts.yaml`.

## The request

**Naming the mechanism in the request turns a design task into a sizing task.** "A hex nut presses in" hands over the hard decision. Real requests state a problem. The knob family stays as a narrow control; Dan's own prompt is the better example. Evidence: charter, "Requests describe the function"; the tripod plate's brief.

**A task's answer can leak through setup nobody thinks of as part of the request.** The webcam bolt's catalog description said "(the Arca plate, Oct 12)", in the hardware list every model sees. Evidence: fixed in be8b718.

**A literal request can point away from the good answer.** Dan's words ask to print "the part that screws in". The session's model advised against a printed thread, but no record shows one failing, so the check can't call it wrong. Evidence: session c941d075, `tasks/tripod-plate/brief.md`.

## Asking

**Asking only helps if the person can answer.** Several models asked for the nut's real size and got "I can't measure that", because the lookup table had nothing. A real person would have fetched calipers. So the table's coverage shapes the result. Evidence: `measures` in the M5 and M3 `grades.json`.

**When everyone asks, asking stops being a result.** All 34 tripod trials asked at least 3 questions, and 31 got the bolt head's size. The session this task came from asked about length only, so the transcript's mistake mostly didn't repeat. The one R4 failure had the answer; it's a CAD slip. A withheld fact only separates models if some of them don't think to ask for it. Evidence: `measures` and `revealed` in `pilot-tripod`'s `grades.json`; no head answer in DeepSeek Pro t2, Luna t2 and t3.

**A person who can't answer shapes what comes back.** The person only knows the clamp's style, so every question about its size gets the same sentence. GLM asked 20 questions in t2. Several models write it up in their limitations as measuring not working. A real friend would say "I don't have calipers". Evidence: `limitations` in DeepSeek Pro t1, DeepSeek Flash t1, GLM t1 and t2. Since 2026-11-06 the person answers the width with the standard, 38 mm, the Arca-Swiss width Dan's plate fit, so new runs won't show this.

**Declining to guess scores the same as getting it wrong.** GPT-6.1 Sol handed in only a test piece on all five trials, and said why: the clamp's size isn't known and a bad guess could drop the camera. On t4 and t5 the person told it the clamp takes 38 mm plates, and it still declined: "A nominal 38 mm width does not ensure dovetail retention". GPT-6 Luna did the same on t2. R1 fails them, next to designs with real faults. Whether that caution is a failure or the right answer to "how hard would it be" is a question for the task, not the grader. Evidence: `pilot-tripod`, Sol t1 to t5, Luna t2.

**Handing over the facts didn't help, because facts weren't the problem.** With the bolt's numbers given up front, 1 of 10 trials passes and 1 isn't graded, against 6 of 34 when models had to ask. `bridges` still fails 6 of 10, and the plates with no hole are CAD slips. It's a small sample, one trial a model, but it points the same way as the reading: on this task what separates models is printing and geometry, not finding out. Models still called `measure` when told everything, up to 10 times. Evidence: `results/runs/pilot-tripod-given`.

**A contrast can only test what its facts contain.** Nobody recorded the clamp's size, so `all_given` can't supply it, and GPT-6.1 Sol's reason for declining survives: its t1 here raises `ValueError: STOP: missing measurements` inside its own part. So this run can't say whether Sol would design a plate given the clamp's numbers. Evidence: `pilot-tripod-given`, Sol t1.

**I keep inventing requirements the records don't back.** On the wheel, I wrote that a seat must be full depth and that something must stop the bearing. Neither has a print behind it. Reading the runs caught both, and Opus's and Luna's seats and Qwen's and GLM's through bores moved from failed to not graded. A check's author has a picture of the right design, and it leaks in. The brief's table of what the records decide is the guard, but only if every verdict in the code is on it. Evidence: `CHANGELOG.md`, the wheel entries.

## Running it

**One trial isn't enough to place a model.** DeepSeek Flash failed t1 and t2 and passed t3 for $0.02. Gemini 3.8 Flash and Argon each pass 2 of 3 and fail a different check on the odd one. Opus's t1 fails only the which-face check, and its t2 and t3 fail only `bridges`, so a single trial would have named the wrong weakness. Evidence: `pilot-tripod`, t1 to t3.

**Models can't see what they built, so CAD slips look like design errors.** DeepSeek Pro's cuts missed the part (t1, bevels), ran along its length (t2, the hole) and across its end (t3, no hole at all). Gemini 3.8 Flash asked for a 17 mm recess but swapped `slot2D`'s arguments and got 12 mm. Qwen's cut went away from the part, and Gemini 3.8 Flash's cuts in another run landed 40 mm from a plate its extrude had moved. Each model's notes describe the part it meant to make. A build error comes back to the model and a geometry error doesn't, so these checks measure "knew what to do and could check it", not knowledge alone. Evidence: DeepSeek Pro t1 to t3, Gemini 3.8 Flash t2, Qwen t1.

**A review can find what pilots don't.** The code review of the tripod checks found 12 faults; only 4 of 34 verdicts changed when they were fixed, and no pass changed. The rest were waiting for a shape nobody had submitted yet. Evidence: `CHANGELOG.md`, tripod repeats entry.

**Small models find the harness's bugs cheaply.** Most runner and schema faults showed up on Haiku and DeepSeek Flash for a few cents. Evidence: `pilot-nut-knob`'s first trials.

**Reading transcripts is the bottleneck, not credit.** The run cost under $2, and most of this session's usage went on reading what came back. A script that prints each failure's reason now does the first pass. Evidence: `scripts/digest.py`.

**A variant's difficulty can differ for reasons unrelated to skill.** M5's window forgives a nominal pocket and M3's doesn't, so nominal designs pass M5 and fail M3. Passing M5 alone says little. Evidence: `pilot-nut-knob` against `pilot-nut-knob-2`.
