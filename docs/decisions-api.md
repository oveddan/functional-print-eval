# Decisions models as judges

OpenRouter's Decisions API answers typed questions (yes/no, pick one, a scale, where in a photo) with probabilities instead of text. This page covers how it works, when this eval should use one, how two of them did on five questions whose answers we already know, and where they'd fit. Everything here comes from one run on 2026-11-12, saved under `results/judges/2026-11-12/`, which cost $0.064 in all.

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
```

`--data-root` exists because round 3's records and `supports.py` were on the unmerged round 3 branch when this ran. Photos are read from Dan's Dropbox (`06 Photos`) and converted in a temp folder; they never enter the repo. Test 4 was rerun once, with whole `print_test` calls, after the first run hid them. Test 3 was rerun once after the crop fix. The saved files are the final runs.
