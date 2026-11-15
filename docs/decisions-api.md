# Decisions models as judges

OpenRouter's Decisions API answers typed questions (yes/no, pick one, a scale, where in a photo) with probabilities instead of text. This page covers how it works, when this eval should use one, how two of them did on five questions whose answers we already know, and where they'd fit. Everything here comes from runs on 2026-11-12, saved under `results/judges/2026-11-12/`: $0.064 for the first five tests, $0.88 for test 7, $0.24 for 7b, $0.14 for 7c and $0.014 for 7d.

**Rule unchanged:** graders are code wherever a program can decide. A decisions model is a judge for calls no program can make, never a contestant, and the report says where one was used. On this run no judge result was used to grade a trial.

## How the API works

From OpenRouter's API reference ("Submit a decisions request") and its multimodal-decisions guide, read 2026-11-12. The model pages for GPT-6 Luna Decisions and Jev returned 404 when we fetched them, so model details come from those two docs.

- **Request:** `POST https://openrouter.ai/api/alpha/decisions` with the usual bearer key. The body has three fields:
  - `model`;
  - `state`, which is what gets judged: a string, an object, or a list of strings and image parts (`{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}`);
  - `questions`: an object keyed by your own ids.
- **Question types:**
  - `noul`: yes/no. The answer is p(yes). Optional `criteria` gives guidance for `true` and `false`.
  - `choice`: one option from `criteria` (option name → guidance). The answer has a probability for each option.
  - `score`: an ordered scale, lowest level first. The answer has a probability for each level.
  - `box`: Jev only. The answer gives the box's edges (`top`, `bottom`, `left`, `right`) as fractions of the image, measured from the top left.
- **Response:** `answers` keyed by question id, plus `usage` (input tokens, output tokens, cost in dollars) and an id. Output tokens are free.
- **Limits that bit us:**
  - Jev wants each image side between 256 and 1568 px, and doesn't apply EXIF rotation. Phone photos need their rotation baked in first. A thin crop scaled up to meet the 256 px floor can pass the 1568 px ceiling, which returns HTTP 400 ("Invalid image dimensions"). `crop_jpeg` now widens thin crops first.
  - When Luna refuses one question, the whole call fails with HTTP 502 ("OpenAI refused to answer question ..."), and the other answers are lost. The reference describes a per-question `refusal` answer instead; we didn't get one. It happened twice, both on `bridge_reasoned`, on Opus and Sonnet Estoa transcripts.
  - HTTP 402 means no credits left (the client stops the run).

The client is `pbe/judges/decisions.py`. It has typed records (`Request`, `Noul`, `Choice`, `Box`, `Decision`, `Answer`), one `decide()` call with retries and a `Budget` cap, and one function per question. The key comes from `OPENROUTER_API_KEY` or 1Password and is never printed.

## The models

The brief named three: Jev 1.14 (`typesafe/jev-1.14`), GPT-6 Luna Decisions (`openai/gpt-6-luna-decisions`) and Gemini Decision 1. Dan narrowed it to the first two mid-run, so Gemini wasn't run.

| | Jev 1.14 | GPT-6 Luna Decisions |
|---|---|---|
| Reads | text, PNG/JPEG images | text, images (up to 128 per request) |
| Box (find something in a photo) | yes | no |
| Price billed on this run, per million input tokens | $0.042 (the brief had $0.10) | $0.10 |
| Median latency per call, across the run | 0.25 to 0.30 s (0.51 s for the 13-box call) | 0.33 to 0.48 s |
| Slowest call | 1.21 s | 1.86 s |

**Usage, for context.** OpenRouter's decision-model rankings ([openrouter.ai/rankings/decisions](https://openrouter.ai/rankings/decisions), "usage data through Nov 11, 2026", read 2026-11-12) rank models by weekly requests:
- Jev 1.14 is second, with 561M requests (+17% on the week before), behind Jev 1.13 at 897M.
- GPT-6 Luna Decisions is sixth, with 37.2M (-23%).
- Gemini Decision 1 isn't in the top ten shown.
- TypeSafe had 71.1% of all decision requests in the week beginning Nov 2, and OpenAI had 1.5%.

The page shows request volume and share of spend, with no quality or preference measure. So it says what people use, not what's right on our questions. The known-answer tests below decide the recommendation.

Both cost little enough to ignore: the largest transcript (41K tokens) cost $0.0017 on Jev.

## Results on the five known-answer tests

Each row compares a model's answers with the key. **Recorded key** is the key the run used (code, or the colours `coupons/fit_cards.py` gives). **After hand check** is that key after Claude read every disagreement and corrected the key where it was wrong (`results/judges/hand-labels.yaml`, `hand_checked`, with the reason for each). **Baseline** is what you'd score by always giving the most common answer. A judge is only useful above it. Numbers are from `results/judges/2026-11-12/summary.md`.

| Test | Model | Recorded key | After hand check | Baseline | Calls | Median latency | Cost |
|---|---|---|---|---|---|---|---|
| 1. Do a design's instructions ask for supports? | Jev 1.14 | 42/44 (95%) | 43/44 (98%) | 52% | 22 | 0.26 s | $0.0010 |
| | GPT-6 Luna | 42/44 (95%) | 43/44 (98%) | 52% | 22 | 0.41 s | $0.0023 |
| 2. Dan's spoken outcomes as verdicts | Jev 1.14 | 33/40 (82%) | 33/40 (82%) | 40% | 40 | 0.24 s | $0.0007 |
| | GPT-6 Luna | 36/40 (90%) | 36/40 (90%) | 40% | 40 | 0.35 s | $0.0009 |
| 3a. Roof photos: clean or not | Jev 1.14 | 13/19 (68%) | 13/19 (68%) | 68% | 19 | 0.30 s | $0.0010 |
| | GPT-6 Luna | 13/19 (68%) | 13/19 (68%) | 68% | 19 | 0.48 s | $0.0009 |
| 3c. Roof photos with example photos: ok or failed | Jev 1.14 | 9/19 (47%) | same | 68% | 19 | 0.54 s | $0.0049 |
| | GPT-6 Luna | 10/19 (53%) | same | 68% | 19 | 0.62 s | $0.0044 |
| 3b. Box: find a cell by position | Jev 1.14 | 13/13 centres inside | same | n/a | 2 | 0.51 s | $0.0004 |
| 4. Estoa transcript checklist | Jev 1.14 | 229/246 (93%) | 250/258 (97%) | 71% | 48 | 0.27 s | $0.0098 |
| | GPT-6 Luna | 222/238 (93%) | 244/250 (98%) | 70% | 46 (2 refused) | 0.41 s | $0.0271 |
| 5a. Failure records into the 10 classes | Jev 1.14 | 49/57 (86%) | same | 23% | 57 | 0.24 s | $0.0021 |
| | GPT-6 Luna | 38/57 (67%) | same | 23% | 57 | 0.34 s | $0.0033 |
| 5b. Class held out: answers "none of these" | Jev 1.14 | 11/57 (19%) | same | n/a | 57 | 0.24 s | $0.0019 |
| | GPT-6 Luna | 40/57 (70%) | same | n/a | 57 | 0.35 s | $0.0030 |

### 1. Supports (22 submissions, two questions each)

- **The set.** 5 submissions `pbe/parts/supports.py` finds. 10 that assume supports without asking for them, e.g. "Remove supports and clean the holes". And 7 conditional or "no" phrasings of the kinds that code was written to turn down, e.g. "only if your slicer asks", "supports under the pocket would fill it".
  - The 7 false matches the brief cites aren't listed in that CHANGELOG entry, so these 7 were found by reading every saved submission that mentions supports without a plain refusal (`hand-labels.yaml`).
- **Two questions.** "Plainly asks", which is supports.py's rule, and "expects supports", which counts implied asks.
- **What the hand check found.** Both judges caught a design that plainly asks and that `supports.py` misses: Haiku 5.5 Estoa can_ask t5, loop feedback arm, step 1: "Support is needed under the roof inside the box." That's a real gap in the code's phrasings. It's recorded here and not fixed in this PR.
- **Each judge's one miss after the hand check:**
  - Luna read "either print the plate with supports under that small roof, or tell me" as a plain ask.
  - Jev read "no supports (or supports inside the pocket if the first try still fails)" as expecting supports.
- **Use.** Code stays the grader. A Jev pass over all 1140 submissions would cost about $0.05 (an estimate: about 1,000 tokens each at the rate billed here) and would flag phrasings to add to `supports.py`.

### 2. Spoken outcomes (40 outcomes)

The key is the colour `fit_cards.py` gives each outcome for its card's job, plus roof outcomes keyed by hand. The judge saw the job and Dan's words.

Every disagreement is an outcome where the code makes a stated scoring call on wording near the line, and the judges took the plain words instead:
- **"goes through when pushed"** (M8 at 8.1 mm): good, since the bolt passes by hand. Both judges said too tight.
- **"loose"** (1/4-20 at 6.6 mm): good for a pass-through hole. Both said too loose.
- **"goes in when pushed hard"** (M5 nut at 7.95 mm): good under Claude's rule that a pocket passes if the nut goes in pressed on a bolt. Both said too tight.
- **"ok; a bit loose, fixable by clipping"** (ring roof 10): the strands are loose, not the fit. Both said too loose. The four-way choice offered "too loose" for a roof, which was a flaw in how the question was written.
- **Jev alone** got two easy ones wrong: "slides through easily" as too loose, and "fits very snugly" as too tight.

The keys stand. These calls are exactly why the graders spell out each word mapping in code.

### 3. Photos

- **3a, roof looks.** Each cell was cropped from Dan's photos using Claude's box for that cell (`pbe/judges/photo_cells.py`), and the judge was asked "clean / sagging / stringy". The key is Dan's outcome read as clean or not.
  - Neither judge beat always saying "not clean". Luna never answered "clean" (0 of 19). Jev said it twice, once rightly.
  - The cells Dan called "mostly ok" or "fine" were called sagging or stringy. A stray strand reads as failure to them, while Dan judges whether the part still works.
  - **Not usable for roof verdicts.**
- **3c, the same crops with example photos.** The question was asked in Dan's terms: "ok" means a solid surface where a few stray strands are fine, "failed" means gaps, loops or tangles across the hole or pocket. Each call carried two labelled example crops of each verdict.
  - **How the examples were given.** Jev got them inside each option's `criteria` (it reads images there). Luna got them in `state`, each after a text label, before the photo to judge.
  - **Leave one out.** Examples came from other cells only, taken from other photos first (`photo_cells.references_for`). Five of the six cells that worked are in the ring-roof photo, so the ring cells' "ok" examples were GPT's roof crop and another ring roof, and their "failed" examples were two long bridges.
  - **Both did worse than without examples, and below the 68% baseline:** Luna 10 of 19, Jev 9 of 19.
  - **Why, from looking at the crops:**
    - The bridge strips look like neat parallel strands from above. Dan's verdict ("all stringy, strings break") is about strands that break when touched, which the photo doesn't show. Once "ok" was taught with ring roofs that have a few stray strands, Jev called all five strips ok.
    - The ring roofs that worked still show stray strands across the top, or are too small to read: ring roof 6 is about 56 px across before scaling up. Both judges called all five of those failed.
  - **So the photos don't carry the verdict:** half the failures were felt, not seen. Example photos can't fix that. A better test needs photos taken to show the failure: close up, square on, one cell to a photo, with strands that broke shown broken.
- **3b, Box.** One call per photo asked Jev to find each cell by its position ("the third pocket from the top in the right column of small pockets").
  - The centre of every one of the 13 boxes fell inside Claude's box. Overlap (IoU) was 0.49 to 0.91 for the ten ring roofs, and 0.41, 0.18 and 0.53 for the three long bridges, which cross each other.
  - A two-item trial run before the full run missed the 80 mm bridge, so the answers vary from run to run.
  - The ring-roof photo has no printed numbers, so cells were found by position only.
  - **Good enough to place cells on a photo for a person to confirm. Not good enough to trust for overlapping parts.**

### 4. Estoa transcript checklist (48 trials, 11 questions each)

One question per known Estoa failure that the estoa-light task can show (`pbe/judges/transcripts.py`), for example "did it ask for the USB-C plug head's size?" and "did it ask for a test print of the hanging slots?". The judge saw the conversation and tool calls, without the system prompt or private reasoning, and with a submitted design's code cut at 2500 characters.

- **Keyed by code from the tool calls (7 questions).** What the session asked `measure`, and what it sent to `print_test`, which is keyed only in `can_test` sessions.
- **The hand check found the code keys wrong 10 times, with the judges right every time.**
  - `plug_head`'s keyword matched "plugged in" and "plug mouth" (7 times).
  - `esp32_height` missed "maximum height of components" (2 times).
  - `wall_screw_size` matched "overhang" (once).
  - A keyword key over free text is itself a judge, and a worse one here.
- **The judges missed what code got right on the test prints.**
  - Keyhole tests: Sonnet `can_test` t3 and DeepSeek V4.1 Flash t1 both test-printed hanging slots or keyholes. Both judges missed both (Luna p ≤ 0.16; Jev 0.39 and 0.44).
  - Fastener test: Sonnet t3 test-printed insert holes. Luna missed it.
  - These misses came after a rerun with whole `print_test` calls. The first run cut them at 2500 characters, which hid the evidence.
  - GPT-6.1 Sol `can_test` t3 test-printed a hole gauge for the disk screws, and an M2-screw grip test on the perfboard holes. Claude counted it as a fastener test. Both judges said no.
- **Code can't key 4 questions** (plug reach, screw length, bridge reasoning, tool reach). On a hand sample of 4 transcripts, the answer was "no" in all 12 labels. Luna matched all 12, Jev 11. With every label "no", this sample can't show whether a judge finds a "yes".
  - `plug_reach` wasn't labelled. Asking where the port mouth sits is a step towards it, and the question doesn't say whether that counts. A checklist item has to be decidable from the transcript.
- **Luna refused one question twice**, which lost those two calls (see the limits above).

### 5. Failure classes, and flagging a new one (57 records)

- **The question.** One `choice` per failure record in `seeds/*-failures.yaml` (34 Estoa, 12 tripod, 8 side projects, 3 test prints): which of the 10 classes in `seeds/classes.yaml` is it, or "none of these"? Each option carries its class's name and description (`pbe/judges/failures.py`).
- **What the judge sees.** What went wrong and how it was found, not the fix. A new failure coming in from a build or a grader's finding has those two, while the fix ("ask for the size first") would give the class away. Claude's call.
- **The key** is the record's own class. A record's second class (`also:`) counts too, for the 6 records that have one.
- **5a, sorting.**
  - Jev put 49 of 57 in the class on record (86%), Luna 38 (67%). Always answering the commonest class (C1, unmeasured) would score 23%.
  - Hand check (`hand-labels.yaml`, `5-classes-notes`; the key wasn't changed): 4 of Jev's 8 misses are defensible.
    - Three went to C5 (mating envelopes) where the record says C1 (unmeasured): slots that ignored headers, a counterbore that guessed the bolt head, cable holes too tight for its bend. C5's description names exactly those things, "header height", "screw head", "cable bend".
    - The fourth, screw heads standing proud, went to C3 (stack-up).
    - So C1 and C5 overlap as written. That's a definition to sharpen, not a judge to blame.
  - Luna sent all 5 manual records (C9) to process (C10). That's a systematic misread.
- **5b, flagging something new.** Each record was judged again with its own class removed from the options. A good flagger says "none of these" or answers weakly. On the full run, it shouldn't flag records whose class was offered.

| Flag rule | Held-out class flagged | Offered class flagged (false flag) |
|---|---|---|
| Luna says none | 40/57 (70%) | 6/57 (11%) |
| Jev says none | 11/57 (19%) | 1/57 (2%) |
| Jev says none, or its pick is under 0.5 | 26/57 (46%) | 7/57 (12%) |
| Luna says none and Jev's pick is under 0.7 (threshold tuned on this run) | 34/57 (60%) | 4/57 (7%) |

- Jev rarely admits a record fits nothing: with the right class gone, it picks the nearest one.
- Luna says "none" readily. That's what flagging needs, and it's also why Luna's sorting score is lower.
- Neither flagged C5 when C5 was held out (Jev 0 of 6, Luna 1 of 6). Its records went to C1, C3 or C7, the same overlap again.
- 57 records, and only 3 to 13 per class, is small. The flag rates are a first read, not a calibration.

### 7. Matching measure requests to the person's recorded facts (2,688 requests)

Added after the five tests above, same day, on Dan's idea: could a decisions model stand in for the alias lookup in `pbe/runner/measure.py`, which answers a designer's `measure(item, what)` from the task's `hidden_facts.yaml` and says "I can't measure that" when no alias matches? The known miss was Sonnet's "screws you will hang it on" on pilot-estoa, fixed by adding "hang" to the aliases. Raw answers: `results/judges/2026-11-12/7-measure.jsonl`; report: `7-measure.md` beside it (`scripts/measure_judge_report.py`). Dan asked for Gemini Decision 1 (`google/gemini-decision-1`) to be compared too, so all three models ran. Cost $0.88 (Luna $0.47, Gemini $0.29, Jev $0.11), no failed calls, median 0.25 s (Jev) to 0.35 s per call.

- **The set.** Every `measure` call in every saved transcript under `results/runs/` (`pbe/judges/measure_calls.py`): 3,066 calls, 3,000 distinct (task, item, what). The nut-knob and m5-spacer tasks record no facts, so there is nothing to pick there; that leaves 2,688 distinct requests on bearing-wheel, estoa-light and tripod-plate. The key is what today's lookup reveals for each request, rerun on today's `hidden_facts.yaml`. It differs from the saved reply in two requests: the "hang" fix, and an empty call whose arguments didn't parse. The set is the saved trials on 2026-11-12, before round 3's trials reached main; those add 37 requests that weren't judged.
- **One yes/no per fact, not one choice.** Of the 2,330 requests the lookup answers, 1,194 reveal more than one fact ("outer diameter and width"), and a single `choice` can name only one. So each call asks one `noul` per recorded fact: "Does the designer's request ask for the bearing's od?", with the fact's note as guidance. The judge sees the person's things and the request, never a value. A fact at p ≥ 0.5 is a pick, and a pick maps to the value as recorded, word for word.

**Where the lookup answers, agreement is low, and mostly because the lookup gives more than was asked.**

| Model | Same set of facts as the lookup | Facts on the same side | Picked a fact the lookup didn't | Left out a fact the lookup gave |
|---|---|---|---|---|
| Jev 1.14 | 505/2330 (22%) | 16805/19940 (84%) | 275 (12%) | 1755 (75%) |
| GPT-6 Luna | 564/2330 (24%) | 16909/19940 (85%) | 347 (15%) | 1672 (72%) |
| Gemini Decision 1 | 664/2330 (28%) | 16984/19940 (85%) | 691 (30%) | 1329 (57%) |

- The lookup gives every fact about a thing when the request names the thing but none of its listed measurements, and its short aliases match loosely: "M8 bolt, threaded length" gets the bolt's diameter; "the bracket's axle hole" gets the bolt's diameter through the alias "axle"; "camera socket depth" gets the thread and the clamp's facts; "wires, length and thickness" gets the LED disk's and the perfboard's thickness.
- **Hand sample** (`hand-labels.yaml`, `measure_disagreement_sample`, 25 of Jev's 1,825 disagreements drawn at random): Jev was nearer to what was asked in 17, the lookup in 6, neither in 2. Jev's real misses there were plate-width questions in other words ("the slot's width across the plate", "the width between the jaws"), where the note "the width of plate it takes" didn't get through.
- **So this key isn't ground truth**, and the agreement column doesn't rank the judges. It does show a lookup problem: the person volunteers facts nobody asked for, which `measure.py`'s own docstring says it can't do. A model that asks vaguely gets the whole record. That's a follow-up for the lookup, not a judge result.

**Where the lookup says "I can't measure that" (358 requests).** Every request any model picked a fact for was read by hand against `hidden_facts.yaml` and, where the words were unclear, the transcript (`measure_no_answer`). Claude also read every turned-away Estoa and tripod request, and every bearing-wheel one that names the bearing or the bolt.

| Model | Picked a fact | Same facts as Claude's hand check | Found a recorded fact that was asked for | Picked a fact not asked for | Real misses caught |
|---|---|---|---|---|---|
| Jev 1.14 | 7 | 3 | 3 | 4 | 3 of 4 |
| GPT-6 Luna | 6 | 3 | 3 | 3 | 3 of 4 |
| Gemini Decision 1 | 54 | 3 | 4 | 51 | 4 of 4 |

- **Four real misses**, where a recorded fact was plainly asked for and the lookup turned it away:
  - "one of the 608ZZ bearings": outer diameter, and width (two requests, DeepSeek V4.1 Flash, test-first t2). "bearings" and "608ZZ" aren't whole-word aliases. All three judges caught both.
  - "wall mounting screws": head diameter, shaft diameter and spacing (Gemini 4 Argon, test-first t1). The alias is "wall screw". Jev and Luna picked exactly size and spacing; Gemini added the standoff.
  - "plate": size (Gemini 4 Argon, pilot-code tripod t2). The size of the missing plate is the width of plate the clamp takes, 38 mm, but "plate" is an alias of the measurement, not of a thing. Only Gemini caught it.
- **Per task:** 2 of 797 bearing-wheel calls, 1 of 612 Estoa calls, 1 of 1,329 tripod calls (calls to the judged requests across the trials on main). **Per contestant:** DeepSeek V4.1 Flash 2, Gemini 4 Argon 2, every other model none. Each was asked once.
- **The judges' wrong picks:** most of Gemini's 51 read the broken old wheel ("the old roller wheel's width") as the 608 bearing; the old wheel isn't recorded. Jev and Luna each took the designer's own M2 screws for the wall screws, and the bracket's inside gap for the bearing's width; Jev took the old wheel's bushing for the bearing's bore.

**Examples, from the saved run.** One row per request. The three model columns are the three judges, each asked the same yes/no per recorded fact; a cell lists the facts that judge said yes to (p(yes) ≥ 0.5), with p shown, and "–" means it said no to every fact. "Claude's hand check" is Claude reading the request against the task's `hidden_facts.yaml`: which recorded fact, if any, was plainly asked for, and what the person would have answered. It is not Dan's reading. All rows are from `7-measure.jsonl`; the hand readings are in `hand-labels.yaml`.

*Turned away by the lookup: every request Jev picked a fact for, plus the one only Gemini caught.*

| Request (item / what) | Jev 1.14 | GPT-6 Luna | Gemini Decision 1 | Claude's hand check |
|---|---|---|---|---|
| one of the 608ZZ bearings / outer diameter across the outer ring only | bearing.od 0.98 | bearing.od 1.00 | bearing.od 0.96 | **real miss**: the person would have said "about 22 mm (outside)" |
| one of the 608ZZ bearings / width, the thickness across its two flat faces | bearing.width 0.98 | bearing.width 1.00 | bearing.width 0.96 | **real miss**: "about 7 mm" |
| wall mounting screws / head diameter, shaft diameter, and spacing between the two screws | size 0.98, spacing 0.98 | size 1.00, spacing 1.00 | size 0.97, spacing 0.97, standoff 0.61 | **real miss**: "#8 round-head screws in 1/4 inch anchors; I bought ones with heads 9 mm across at most" and "I can put them wherever you say"; Gemini's standoff wasn't asked |
| plate / size (tripod) | – (0.47 at most from Luna) | – | plate_width 0.71 | **real miss**: the clamp takes a 38 mm plate |
| own:m2x6-self-tapping / head diameter and head height | wall_screws.size 0.78 | wall_screws.size 0.99 | – | wrong: the designer's own M2 screws, not the wall screws |
| the two metal plates on the door that the wheel sits between / distance between their inner faces | bearing.width 0.58 | bearing.width 0.84 | – | wrong: the bracket's gap, which isn't recorded |
| old roller wheel / diameter of the hole through the centre (or the metal bushing's bore) | bearing.bore 0.64 | – | bearing.bore 0.76 | wrong: the old wheel's hole, not the new bearing's |
| old wheel and closet track / does it carry the door's weight; is the edge flat, rounded or grooved | bearing.od 0.55 | – | – | wrong: nothing about the bearing was asked |
| old roller wheel / exact width (thickness across the wheel), and 48 more like it | – | – | bearing.width (typical) | wrong: Gemini reads the broken old wheel as the 608 bearing |
| diffuser / dimensions, or how the front and sides attach | – | led_disk.diameter 0.77 | – | wrong: the diffuser is part of the design |

*Where the lookup answered and the judges said less: from the hand sample.*

| Request (item / what) | Lookup gave | Jev 1.14 | GPT-6 Luna | Gemini Decision 1 | Nearer to what was asked |
|---|---|---|---|---|---|
| M8 bolt / threaded length, from the tip to where the threads stop | bolt.across (every bolt fact: none was named) | – | – | – | judges: threaded length isn't recorded |
| door bracket / diameter of the hole where the axle passes through | bolt.across (alias "axle") | – | – | – | judges: the bracket's hole, not the bolt |
| wires / length and thickness of the four wires from the perfboard to the LED disk | led_disk.thickness, perfboard.size, perfboard.thickness | – | – | – | judges: wires aren't recorded |
| LED disk / thickness of the board at its edge | led_disk.thickness, led_disk.hole_to_edge (alias "edge") | thickness 0.94 | thickness 1.00 | thickness 0.90, wall_screws.size 0.50 | Jev and Luna |
| camera tripod socket / depth of the 1/4-20 socket | socket_thread, plus the clamp's style and plate width | socket_thread 0.79 | socket_thread 0.90 | socket_thread 0.84 | judges: depth isn't recorded; the thread is the nearest fact |
| salvaged webcam mount bolt / total length, and whether the head is hex or round | all three bolt facts | length 0.99 | length 1.00 | length 0.97 | judges |
| tripod head quick-release slot / width of the slot across the plate | plate_width | – | plate_width 0.97 | plate_width 0.75, style 0.69 | lookup: Jev missed a plain plate-width question |
| tripod head clamp / width between the angled jaws when tightened and when open | plate_width | – | – | – | lookup: the gap between the jaws is the plate width |
| salvaged webcam-mount bolt / the shape of the head, and whether its underside is flat | head_across, head_height | head_across 0.54 | head_across 1.00 | head_across 0.67 | neither: shape isn't recorded |

*Where everyone agrees (most single-thing requests):* "608 bearing / outer diameter and width": lookup, Jev (0.98, 0.99), Luna (1.00, 1.00) and Gemini (0.98, 0.97) all give bearing.od and bearing.width.

**7b. Asked as a count, then a list (Dan's suggestion).** Instead of one yes/no per fact, one call asked: how many separate things does the request ask for (none to five or more), then "what is the 1st thing it asks for?" up to the 5th, each a pick-one over every recorded fact plus "not recorded" and "nothing more". The answer is the facts in the slots up to the count. The idea was that the facts would compete with each other and with "not recorded", where the yes/no version judges each fact alone. Jev only, all 2,688 requests, $0.24, no failed calls (`7b-measure-listed.jsonl`).

Both versions were scored against Claude's hand key: the 82 turned-away requests any judge picked a fact for (test 7b added 24, all the old wheel, the bracket or the track), plus the 25-request sample, each keyed with the facts plainly asked for. The key leans towards hard cases, so it compares versions; it isn't a rate for all requests.

| Version | Exactly the facts asked for | Picked a fact not asked for | Left out a fact asked for |
|---|---|---|---|
| Today's lookup | 83/107 (78%) | 20 | 4 |
| Jev 1.14, yes/no per fact | 93/107 (87%) | 8 | 7 |
| GPT-6 Luna, yes/no per fact | 95/107 (89%) | 8 | 5 |
| Gemini Decision 1, yes/no per fact | 42/107 (39%) | 64 | 1 |
| Jev 1.14, count + list | 49/107 (46%) | 52 | 7 |
| *With a bar, tuned on this key:* Jev, yes/no, p ≥ 0.8 | 100/107 (93%) | 1 | 7 |
| *With a bar, tuned on this key:* Jev, count + list, slot pick ≥ 0.9 | 97/107 (91%) | 0 | 10 |

- **Count + list was worse.** Once Jev counted three things in "the old roller wheel's outer diameter, width and rim profile", it filled the slots with the nearest recorded facts, the bearing's od and width, usually at p 0.4 to 0.7. The slot form pushes it to find something for each thing counted. It picked a fact for 52 of the 358 turned-away requests, against 7 for the yes/no form.
- **What it did better:** it caught "plate / size" (plate_width, 0.71), which yes/no Jev missed. It still lost the wall screws' size, putting "head diameter" in "not recorded".
- **A confidence bar helps the yes/no form most.** At p ≥ 0.8, Jev's yes/no answers match the hand key in 100 of 107. The bar drops all four wrong picks on turned-away requests (0.55 to 0.78) and keeps its three real catches (0.98). The one wrong pick left is the camera thread (0.90) for "safe usable camera-thread depth", where depth isn't recorded. All 7 misses are the clamp's plate width asked in other words. The bar was chosen after seeing these answers, so it needs a fresh set of misses to confirm.
- **What both forms still miss:** the plate-width questions in other words, including "plate / size" for yes/no Jev ("the width between the jaws", "the slot's width across the plate").

**7c. Facts shown the way the person would say them.** Test 7's yes/no per fact, with each fact shown as the person's reply ("tripod clamp plate width: 38 mm (the width of plate it takes)") instead of its name, and the state saying the person has measured only these things and nothing else (other parts, an old broken part, the space it goes in) is recorded. Jev only, $0.14, no failed calls (`7c-measure-said.jsonl`). The judge still only picks; the reply is the recorded line.

**The deciding test: a random 200, keyed by hand.** The hard key above is mostly cases where something went wrong, and where the lookup answers its own reply is the only other key. So Claude keyed a random 200 of the 2,688 requests (`hand-labels.yaml`, `measure_random_sample`, random.seed(7)): the recorded facts each plainly asks for, or none. 89 of the 200 ask for at least one recorded fact. Every version, on both keys (`7-measure.md`):

| Version | Random 200: exactly the facts asked for | Picked a fact not asked for | Left out a fact asked for | Hard 107: exactly right |
|---|---|---|---|---|
| Today's lookup | 87/200 (44%) | 107 | 24 | 83 (78%) |
| **Jev 1.14, yes/no per fact** | **153/200 (76%)** | 22 | 28 | 93 (87%) |
| GPT-6 Luna, yes/no per fact | 152/200 (76%) | 30 | 20 | 95 (89%) |
| Gemini Decision 1, yes/no per fact | 127/200 (64%) | 69 | 8 | 42 (39%) |
| Jev, yes/no, p ≥ 0.8 (bar tuned on the hard key) | 143/200 (72%) | 10 | 50 | 100 (93%) |
| Jev, count + list (7b) | 137/200 (68%) | 18 | 46 | 49 (46%) |
| Jev, count + list, slot ≥ 0.9 (tuned on the hard key) | 130/200 (65%) | 0 | 70 | 97 (91%) |
| Jev, facts as said (7c) | 146/200 (73%) | 14 | 42 | 99 (93%) |

- **On ordinary requests the lookup is exactly right less than half the time**, almost all from over-answering: 107 of the 200 got a fact nobody asked for (the bolt's diameter for its length, the camera thread for the socket's depth, the clamp's style for its jaw height).
- **Jev's plain yes/no is the best version, at 76%**, level with Luna, which can't be used (its family competes). Every other change did worse on the random key:
  - the bars tuned on the hard key drop right picks along with wrong ones, so they don't carry over;
  - count + list and facts-as-said both leave out more facts than they save in wrong picks.
- **Most of Jev's remaining errors are two clamp facts.** On the random key, 22 of the 47 requests Jev got wrong left out the clamp's plate width or style asked in other words ("the gap between the jaws with the knob loosened", "how the plate is held"); those two are 26 of the 32 facts it left out. Showing the value made this worse (31 requests, 37 facts): Jev read "38 mm, the width of plate it takes" as the plate's size, not the clamp's opening. Its wrong picks are mostly the camera thread for "how deep is the socket" (7) and the ESP32's position beside its USB port (8).
- **The key is Claude's reading.** Those clamp facts are where it's most a judgement call: Claude counted the clamp's opening as the plate width it takes, and how it tightens as its style. A stricter reading would raise Jev's score and lower the lookup's, since the lookup gives plate_width to every clamp question.

**7d. One thing per ask (Dan's suggestion), with a key nobody anchored.** Half the trouble was requests asking for several things at once. So the random 200 were split into single asks, and keyed again by readers who saw neither the systems' answers nor Claude's key (`7d-asks.json`):
1. **Detect:** Jev's count from test 7b. 77 requests asked for one thing or none and stayed whole; 123 asked for two or more.
2. **Split:** a fresh subagent rewrote those 123 into 402 single asks ("608 bearing / outer diameter", "608 bearing / width"), seeing only the request and Jev's count; never the facts, the lookup or a judge. It disagreed with Jev's count on 22. That gives 479 single asks in all.
3. **Key:** a second fresh subagent mapped each single ask to one recorded fact, or "not recorded", from the fact list alone, and marked its close calls (84). 159 asks are keyed to a fact, 320 to "not recorded".
4. **Judge:** Jev answered each single ask with one pick-one: every fact (shown as the person says it) plus "not recorded". $0.014.

| Per single ask (479) | Right | Picked a fact not asked for | Left out the fact asked for | Same reply to the designer |
|---|---|---|---|---|
| Today's lookup, on the single ask | 192 (40%) | 287 | 20 | 196 (41%) |
| **Jev 1.14, one pick** | **413 (86%)** | 14 | 57 | **419 (87%)** |

"Same reply" counts a fact recorded as "I can't measure that" as no fact, since the designer hears the same words. Always answering "not recorded" would be right on 320 of the 479 (67%), so the lookup is below that baseline and Jev well above it.

**The independent key confirms Claude's.** Per whole request (each request keyed with all its asks' facts), the subagents' key agrees with Claude's random-200 key on 184 of 200. Against it, every version keeps its place: the lookup 42%, Jev yes/no per fact 80%, Luna 79%, Gemini 65%, Jev single asks put back together 76%, 7c 74%, 7b 72%.

- **Splitting makes each question easy, and Jev gets 86% of single asks right**, against 40% for the lookup on the same asks. The lookup gives every fact about a thing whenever the ask names none of its words, and single asks rarely do.
- **Put back together, single asks score a little below yes/no per fact (76% against 80%).** They inherit 7c's wording, which shows each fact's value. Of Jev's 60 single asks with a different reply, 29 are the clamp's plate width asked in other words, and the keyer marked 52 of the 60 as close calls.
- **The split itself is a step that can go wrong.** Here a subagent did it. In live use the designer would, if the measure tool took one thing per call.

**What it means.**
- **A decisions model can replace the lookup outright, and does much better than it.** Jev's yes/no per fact gives exactly the facts asked for in 76% to 80% of ordinary requests (Claude's key, the subagents' key), against 42% to 44% for the lookup, without ever writing a value. Asked one thing at a time it gets 86% of single asks right, against 40%. It also catches the real misses (3 of the 4).
- **One thing per ask is the cleaner interface for later.** If the measure tool took one thing per call (or a list of single asks), each call is a single pick-one, the question this API is built for. That's a change to the contestant's tool, so it waits for the same wiring change.
- **The cheapest way to raise it further is in the task file, not the judge:** describe the clamp's two facts the way designers ask about them (its opening, how it holds the plate). That changes the task's facts, so it belongs with the wiring change, not here.
- **Not done in this PR:** `measure.py` is unchanged and no trial was regraded.

**The design this points to (Dan's, 2026-11-13).** Jev decides which requests to split, an LLM does the splitting, and Jev picks per single ask:
1. **Count:** Jev answers "how many things does this request ask for?". One thing goes straight to step 3.
2. **Split:** for two or more, an LLM rewrites the request as single asks in the designer's own words. It never sees the facts and answers nothing, so it can't invent a value; its failure mode is a dropped ask, which leaves the designer without an answer, never with a false one. On this data Jev's count never sent a single-thing request to be split; the splitter changed how many asks 22 of the 123 became.
3. **Pick:** Jev picks one recorded fact or "not recorded" for each single ask (86% right here, against 40% for the lookup).
4. **Reply:** the picked facts' recorded lines, word for word, as today.

The splitter should come from a family that isn't in the lineup, since it rewrites a contestant's questions. The yes/no-per-fact design (no split) scored a little higher on whole requests here (80% against 76%), mostly from the clamp's wording, so both stay candidates until the clamp facts are reworded and the random key is rerun.

**Wiring Jev in as the person, when it's done:**
- Jev only, yes/no per fact at p ≥ 0.5. Luna and Gemini Decision 1 come from families that compete in the eval (GPT-6 Luna, Gemini 4 Argon).
- The judge picks; it never writes. A pick maps to the recorded value word for word, as a lookup hit does today, and no pick means "I can't measure that".
- Each pick, and each split, is saved in the trial record (request, model, each fact's p(yes)), and a replay reads them instead of calling again, so reruns give the same answer.
- Replies change for most trials that measured, so old trials are regraded under the new person or kept apart, never mixed in one table.
- A call takes about a quarter second and costs about $0.00004, so a trial's few measure calls add nothing worth counting.
- Rerun the random key whenever a task's facts or the question's wording change; it's the gate.

## When to use which

| | Code | Decisions model | Chat model (Opus) |
|---|---|---|---|
| Decides | geometry, sizes, anything in a record's fields | a narrow label over free text or a photo | open questions, explanations, judging with reasons |
| Speed on this run | instant | 0.25 to 0.5 s per call | not measured on these keys |
| Cost on this run | nothing | $0.044 for all four tests (about 1,000 labels) | not measured on these keys |
| Output | exact, repeatable | calibrated-looking probabilities, but they vary run to run (the Box rerun) | text, which has to be parsed |
| Bias | none | Luna is GPT-6 family. GPT-6 Luna is a contestant in the nut-knob, tripod and wheel runs, so it shouldn't judge them alone | Opus is in every run, so the same applies everywhere |

- **Probabilities are useful as a triage signal, not as truth.** They were most often wrong exactly where the word mapping was a judgement call (test 2), or where evidence was long (keyhole tests at p 0.39 to 0.44).
- **A rule worth trying next:** take a judge's label only when the two models agree and both are confident, and have a person read the rest. Not yet tested against these keys.
- **Not measured: Opus on the same keys.** Whether decisions models beat a chat model here is open. The next step is to run Opus on the same 22 + 40 + 19 + 48 + 57 items and add it as a column. It costs more per call, and it's in the lineup.

## Where each would plug in

- **Checking the code's word lists (now, offline).** Run both judges over all saved submissions and outcomes; read only the items where they disagree with code. Test 1 found a `supports.py` gap this way. No judge result grades a trial.
- **Placing cells on test-print photos (Jev Box).** Claude's photo-to-cell mapping today was done by hand. Jev's boxes could pre-place cells for a person to confirm. Roof verdicts from photos stay Dan's words, which test 3a supports.
- **The test-print planning eval (`coupons/PLANNING.md`).** A checklist like test 4 is the cheap way to ask, over many transcripts, whether a designer asked for the facts and test prints Estoa's failures needed. Key every item code can decide from the tool calls, with tighter patterns than this run's. Use a judge for items that need the conversation's meaning, and only after each has a hand sample with "yes" cases in it.
- **Sorting new failures into classes, and flagging new classes (test 5).** Four steps, each done by what it's good at:
  1. **Flag.** Jev sorts each incoming failure. A Luna "none of these" puts it on a flagged list. Sources: Dan's builds, the graders' fail findings across runs, test-print outcomes.
  2. **Propose.** Once a few flagged failures look alike, a chat model proposes a class name and a definition in the shape of `classes.yaml`, and says which flagged records it covers. A decisions model can flag but not name. If Opus writes the definitions, say so: it's in the lineup, though naming a class isn't grading a contestant.
  3. **Approve.** Dan accepts, rewords or rejects it. Nothing reaches `classes.yaml` without that.
  4. **Check.** Rerun test 5 with the new class added. The flagged records should land in it, and the 57 records on file should keep their classes. That keeps the class list from drifting as it grows.

  Not built yet: there are no flagged failures to name.
- **Video, frame by frame (follow-up).** Jev reads only still images, so a clip becomes frames extracted with ffmpeg, either a few per second or at scene changes. They'd be made upright and sized like the photos, and sent as one request. Dan's test-print clips, with his spoken outcomes as the key, would make the next known-answer test. Gemini Decision 1 reads video directly, but it wasn't run.
- **Gemini on video (follow-up Dan chose, 2026-11-12).** Gemini Decision 1 takes a whole MP4, with its audio, in the request.
  - **First test:** the round 3 test-print clips (`04 Test print footage`, e.g. the bolt-hole clips IMG_6162 and 6163), asked "did the bolt go through?" with the sound off, against the outcomes already recorded. Video can show what the photos couldn't, like a strand breaking or a nut pressing in.
  - **Later uses:** sorting clips by kind and project, a usable-take score, failure checks on print timelapses cut into pieces, and checking narration takes against the script.
  - **Cost:** if it counts video the way Google's Gemini chat API does (just under 300 tokens a second), a minute is about a fifth of a cent. That's unconfirmed for Decision 1. Request size is the likely limit, so send H.264 copies cut short, never the masters, and never a public link.
- **Not for grading a design.** Nothing here supports letting a judge decide a pass.

## Recommendation

- **Jev 1.14 as the default judge.** It was as accurate as Luna after the hand check (and it's the far more used of the two on OpenRouter's rankings, which is context, not evidence), a little faster, billed at $0.042 per million tokens against $0.10, has Box, and isn't in the lineup. Luna refused a question twice; Jev refused none (its two failures were our oversized crops).
- **Use Luna as a second opinion, and as the flagger for failures that fit no class** (test 5b: 70% of held-out classes caught, 11% false flags). Never use it alone on runs where GPT-6 Luna competes.
- **Jev as the person who answers measure requests** (test 7), replacing the alias lookup when the person is next changed: on a random 200 requests it gave exactly the facts asked for in 76%, against 44% for the lookup, and it only ever picks recorded facts.
- **Keep both away from roof photos** (with or without example photos, test 3c), keep code as the grader, and keep this run's known-answer tests as the gate any new judge question has to pass first.

## Fixes after review (2026-11-12)

A code review of this PR found nine things. All are fixed. None changed a number above except test 2, which was rerun.
- **Crashes and lost results.**
  - A lost connection, a timeout, or a reply carrying an error instead of answers now becomes a recorded failed call, after retries, not a crash.
  - Every call that finished is kept when the budget or a 402 stops a run.
  - Rows are saved even if a test crashes.
- **A hard budget cap.** A call reserves the most it could cost (every byte of the request as a token, at the top price) before it starts. Calls running side by side can't pass `--budget` together. The bound is loose for photos.
- **Failed calls counted right.** A failed held-out call in test 5 goes in `5-held-out.jsonl`, not `5-classes.jsonl`. The flag-rule table leaves failed calls out instead of counting them as flags.
- **Test 4's keyword keys corrected at the source.** `transcripts.code_keys` now uses the corrected patterns: the charger plug has to be named as the thing measured, "hang" is a whole word, and "maximum height of components" counts. They agree with all 246 hand-checked keys on the 48 transcripts. The saved test 4 rows keep the keys they ran with, and `hand_checked` still corrects those.
- **Test 2, one row per record.** It used to drop any roof whose words matched one already on the strand card, which lost ring roofs 7 and 9. Now it skips only the records that card already holds. Rerun: 40 outcomes, and both judges got the 2 new ones right.
- **Smaller fixes.** The key is read through a public `llm.api_key()`. Test 1 skips submissions that never mention supports before parsing them.

## Reproducing

```bash
uv run python scripts/judge_known_answers.py --budget 3 --data-root <a checkout with round 3's records>
uv run python scripts/judge_summary.py results/judges/<date>
uv run python scripts/judge_known_answers.py --tests 7 --budget 1 --workers 12   # test 7: Jev, Luna and Gemini
uv run python scripts/measure_judge_report.py results/judges/<date>
```

`--data-root` exists because round 3's records and `supports.py` were on the unmerged round 3 branch when this ran. Photos are read from Dan's Dropbox (`06 Photos`) and converted in a temp folder; they never enter the repo. Test 4 was rerun once, with whole `print_test` calls, after the first run hid them. Test 3 was rerun once after the crop fix. The saved files are the final runs.
