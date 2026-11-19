## 2026-11-18: Closed models run on their maker's servers, after Amazon Bedrock stopped GPT-6.2 Sol asking for test prints; new-model trials for GPT-6.2 Sol and Gemini 4 Hydrogen (no published result changed)

Three models OpenRouter added after launch were smoke-tested with test prints first (`can_test`), asked for by Dan on 2026-11-18. One of them, GPT-6.2 Sol, did far worse than GPT-6.1 Sol until its trials were pinned to OpenAI's servers. The cause was the host OpenRouter picked, not the model, the prompt or the grading. The published `test-first` run is unchanged.

### What we saw

GPT-6.2 Sol's first 40 trials (`results/runs/smoke-new-models-unpinned/`, M5 and M3 knobs, tripod plate, bearing wheel, Estoa) passed 15 of the 35 on the four tasks other than M5, against GPT-6.1 Sol's 18 of 35. It asked for a test print in only 16 of the 40. GPT-6.1 Sol had asked in all 45 of its published trials.

### What we checked, in order

- **Grading.** All 45 of GPT-6.1 Sol's published `test-first` trials were regraded with today's checks on a copy (`pbe.eval --regrade --runs-dir <copy>`). None changed.
- **Prompt and tools.** The opening messages of GPT-6.1 Sol's and GPT-6.2 Sol's trials were compared task by task. The request and the tool definitions match exactly. The system prompt differs only in the servo horn's catalog entry (hub readings and the clamp-screw note, 2026-11-11), which none of these tasks uses.
- **Settings.** The same in both: 12 turns, 32,000 max tokens, the provider's default temperature, no prompt caching.
- **Host.** Each saved call records the host that served it. All 221 of GPT-6.1 Sol's calls went to OpenAI. GPT-6.2 Sol's went to OpenAI (16 trials), Amazon Bedrock (21), Azure (1) and Bedrock with Azure (2), alternating minute by minute across every task, so the time and the task don't explain the split. On Bedrock: no test print in any trial, the first design submission rejected as malformed in all 23 (none on OpenAI or Azure), a median of about 25 reasoning tokens a trial against about 650, and 5 of 23 passed. On OpenAI or Azure: 16 of 17 asked for a test print, and 12 of 17 passed.
- **A planned side-by-side.** Ten M3 knob trials pinned to Bedrock (`results/runs/host-bedrock/`, a new `PBE_PROVIDER` setting) against the ten pinned to OpenAI: 0 of 10 asked for a test print and 0 of 10 passed on Bedrock, against 10 of 10 and 6 of 10 on OpenAI. All 10 Bedrock trials had their first submission rejected and reasoned 0 tokens.
- **What the model sees on Bedrock** (`results/runs/host-bedrock/probes/`). Asked to repeat submit_design's format back, the model on OpenAI named every field and `kind`'s three values. On Bedrock it said `params` is "any". The same request reached Bedrock 543 tokens shorter.
- **Why the format is lost.** `params` maps names the model chooses to entries, written as `additionalProperties`. With `params` rewritten as a list of entries with fixed fields, Bedrock passed the whole format through. Our map shape is what Bedrock's conversion drops.
- **Does the list form fix the trials?** No. Two M3 trials on Bedrock with list-form tools (`results/runs/host-bedrock-list/`, a `PBE_PARAMS_AS_LIST` setting): both submissions valid on the first try, but 0 reasoning, no measurement and no test print, and both handed in a 5.40 or 5.45 mm pocket for the 5.5 mm nut on the first turn. Both failed R4.
- **Does asking for reasoning fix it?** No. Two trials with `reasoning.effort` set to medium (`results/runs/host-bedrock-reasoning/`) and two with that and the list form (`results/runs/host-bedrock-list-reasoning/`): no test print, 0 to 12 reasoning tokens, all four failed R4. A direct probe: asked for high effort, OpenAI reasoned 74 tokens on a short question and Bedrock 0. Through OpenRouter, Bedrock runs GPT-6.2 Sol without reasoning whatever is asked.

So on Bedrock the model loses the tools' formats and its reasoning, and without them it never asks for a test print and guesses a nut pocket too tight to take the nut. `docs/media/host-comparison.svg` (`scripts/host_figures.py`) draws it as two funnels, OpenAI's 10 M3 trials against the 10 planned ones on Bedrock: trials, asked for a test print first, design passed. `docs/media/host-post.png` (`scripts/host_post_image.py`) is the image for the post: each server as a pipeline (reasoning, test prints, first submission, result) with every trial charted. Its layout is one of seven Gemini 4 Argon designed through OpenRouter from the post and the facts; Dan picked it after a Decisions-model poll. Both read their numbers from the saved runs.

### The fix

`pbe/runner/llm.py` pins OpenAI models to OpenAI and Google models to Google Vertex or Google AI Studio, with no fallback to another host. Open-weight models (DeepSeek) and Claude are left as before. The published runs already ran on these hosts, so the pin keeps the trial conditions they ran under. It changes only the request's `provider` field (`tests/test_provider_pin.py`, and `tests/test_caching.py` now sets that field aside when it compares bodies). `PBE_PROVIDER`, `PBE_PARAMS_AS_LIST` and `PBE_REASONING_EFFORT` exist only for host experiments and are never set for a leaderboard run; with none set, every model is sent exactly the tools it was sent before.

### New-model trials (`results/runs/smoke-new-models/`)

All with test prints first, run at this change's code, every OpenAI call on OpenAI and every Google call on Google.

| Model | Tripod plate | Bearing wheel | Knob M3 | Estoa | Knob M5 | Cost |
|---|---|---|---|---|---|---|
| GPT-6.2 Sol | 9/10 | 8/10 | 6/10 | 5/5 | not rerun | $2.10 |
| Gemini 4 Hydrogen | not run | not run | 4/5 | 0/5 | 1/1 | $9.25 |

GPT-6.2 Sol asked for a test print in 34 of its 35 trials. Its four-task rate is 80% (28/35), against GPT-6.1 Sol's 51% (18/35) and Gemini 4 Argon's 60% (21/35) on the same four tasks. These trials aren't in the published table, which still counts five tasks including M5, and no table or site page reads this run.

- **Gemini 4 Hydrogen on Estoa:** it reasoned until the 32,000-token output cap cut it off (`finish_reason` "length", about 200 s and $0.24 a call, an empty reply) on 28 of its 53 Estoa calls: 7, 6 and 9 of the 12 turns in the three trials that handed in no design, 5 of 10 and 1 of 7 in the two that did, which then failed `bridges`. The runner answers an empty reply with "Please use your tools" and counts the turn, as it does for every model; the model is told its 12-turn limit once, in the system prompt, with no countdown. It asked for a test print in one of the five. Its Estoa trials cost $1.62 each on average, so a full 35-trial run (10 each on the three smaller tasks, 5 on Estoa) would cost about $14.
- **Gemini 4 Carbon** was stopped after its first trial hung for about 30 minutes. OpenRouter showed its two main Google endpoints at 7% and 23% uptime then. It saved nothing.
- GPT-6.2 Sol's M5 trials (2 of 5 passed, 3 on Bedrock) are only in the unpinned run; M5 wasn't rerun because Dan dropped it from what new models are tested on.
- Spend: GPT-6.2 Sol unpinned $1.62 and pinned $2.10; the Bedrock experiments $0.34; Gemini 4 Hydrogen $9.25; probes under $0.04.
