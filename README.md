# Print-and-Build Eval

Can a frontier model design a 3D-printed part that a person at home can print, test and assemble, when some of what decides whether it works can only be learned by printing?

A person asks in plain language for a printed fix: a camera plate, a knob with a nut pressed in, a wheel with bearings. The model gets the request, the printer and filament, and a bin of common hardware. It can ask the person to measure their own things. It hands in CadQuery code for each part, the hardware it uses, a manual, and any test prints it wants made first. Code checks then decide, part by part, whether the design would print and fit, using limits taken from real test prints on one printer. Where no print on record can decide, the check says so: **not graded**, never a pass.

> **TODO(Dan): who it's for.** One or two lines on who relies on this kind of work.
>
> **TODO(Dan): why it matters.** What a failure costs that person: filament, hours, a part that doesn't fit.

## What existed before the hackathon

I was going to be away from home, flying on Oct 30 and only returning on Nov 9, so for the whole hackathon I'd be away from my 3D printer. I wanted to be sure I could print what was needed before Oct 30, so I did the minimum to prove that: I gathered and categorized real failure cases to work out which test prints I needed, then made those prints to define the ground truth, along with the plan and supporting code, including the first checks. None of the evals were built or run by the time the hackathon started.

## Run it

Everything in this section runs from a clean clone with **no API key and no model calls**. It was tested on a fresh clone in a clean Ubuntu 24.04 container (4 cores); the times below are from that run. macOS wasn't tested on a clean machine, and neither was Docker for `can_run_code`.

### Install

You need:
- [uv](https://docs.astral.sh/uv/), which installs Python 3.12 and every Python dependency from `uv.lock` on first use;
- git;
- a sandbox for building model-written parts: **bubblewrap** (`bwrap`) on Linux, or `sandbox-exec`, which ships with macOS. Without one, parts don't build unless you set `PBE_NO_SANDBOX=1`, which is only for a throwaway container or VM;
- on Linux, `libgl1` for CadQuery's kernel, and `fontconfig` with a font for parts with text.

On Ubuntu 24.04:

```bash
sudo apt-get install -y git curl bubblewrap libgl1 fontconfig fonts-dejavu-core
```

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Ubuntu 24.04 stops unprivileged programs from making the namespaces bubblewrap needs. On a machine you can throw away (a VM or CI runner, as CI does), allow them:

```bash
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
```

Then:

```bash
git clone https://github.com/oveddan/print-build-eval.git
```

```bash
cd print-build-eval && uv sync
```

### Everything at once

```bash
scripts/reproduce.sh
```

It runs the six steps below in order and stops at the first one that fails. Expected: every step passes, ending with `done`. It took 22 minutes on the clean run.

### Step by step

| Step | Command | Expected | Time on the clean run |
|---|---|---|---|
| 1. Install | `uv sync` | Python 3.12 and the locked dependencies installed | 7 s, with a fast network |
| 2. Tests | `uv run pytest` | all pass; the Docker versions of the sandbox tests skip where Docker isn't running | 3 min 25 s: 375 passed, 55 skipped |
| 3. Every reference | `uv run python -m pbe.eval --reference --task tripod-plate` (and `m5-spacer`, `bearing-wheel`, `nut-knob/M3`, `nut-knob/M5`, `nut-knob/M8`) | each task's reference design passes every check; exit code 0 | 29 s for all six |
| 4. Regrade every saved trial, on a copy | see below | every run's `summary.csv` unchanged | 11 min 40 s for all 11 runs |
| 5. Results page | `uv run python scripts/results_page.py` | `results/local/results-page/index.html`: every trial but the 12 spacer passes, with its parts in 3D and every check | 6 min 50 s, most of it rebuilding parts |
| 6. README results | `uv run python scripts/results_table.py --check` | "README.md's results and assumptions match results/runs/" | under 1 s |

Regrading reads each saved design and grades it again with today's checks, without calling a model. Point it at a copy so `results/` isn't touched:

```bash
cp -r results/runs /tmp/runs
```

```bash
uv run python -m pbe.eval --regrade --runs-dir /tmp/runs --run pilot-tripod --task tripod-plate
```

```bash
diff results/runs/pilot-tripod/summary.csv /tmp/runs/pilot-tripod/summary.csv
```

No output from `diff` means every verdict in the run reproduced. When anything that decides a verdict changes, including a check's detail text, the trial's `grades.json` is rewritten with the earlier reading kept under `regrades`. On Linux, a few `bridges` details come out with the strand angle mirrored (the saved runs were mostly graded on macOS), so those trials' `grades.json` change while their verdicts don't. Runs that aren't model trials (`crash-replay`, `loop-sample`, `loop-sample-2`) keep their own `summary.csv`, which a regrade leaves alone.

One design by hand, with the generic checks only (the Arca plate as first drawn, and as fixed after its first print):

```bash
uv run python -m pbe.run examples/arca-plate/original.yaml examples/arca-plate/fix.yaml
```

Expected, in 5 s: the original fails `bridges` (its roof tangled when printed) and the fix passes every check, so the command exits 1.

CI runs steps 2 and 3 on every pull request and on `main` (`.github/workflows/ci.yml`), and step 6 as one of the tests.

### Running new trials (needs an API key)

Models are called through [OpenRouter](https://openrouter.ai), by API. Set `OPENROUTER_API_KEY` in your environment (if it's unset, the runner tries the 1Password CLI, which only works on Dan's machine). Never commit it.

```bash
uv run python -m pbe.eval --run my-run --task tripod-plate --model anthropic/claude-haiku-5.5 --trials 1 --budget 0.50
```

- `--condition` is `can_ask` (the default), `all_given` or `can_run_code`. Several `--model`, `--task` and `--condition` flags multiply.
- `--budget` is in US dollars for the whole run. It's checked between trials, so the last trial can run over.
- Each trial saves `transcript.json`, `submission.yaml` and `grades.json` under `results/runs/<run>/<task>/<condition>/<model>/t<n>/`, and the run gets a `summary.csv`. A stopped run resumes where it left off.
- **What it costs:** the Cost column in [Results](#results) is what OpenRouter charged for the saved trials, by task, condition and model. Divide by the Trials column for a trial's cost.
- **Prompt caching:** Claude models ask for OpenRouter's prompt caching; every model gets the same messages and tools, byte for byte (issue 34, `tests/test_caching.py`). Each trial saved since records `settings.prompt_caching`. Trials saved before had no caching, so their Claude costs are full price. `scripts/cost_report.py <run>...` gives cost per trial and per turn by model.
- **`can_run_code`** lets the model run Python before handing in. That code runs in bubblewrap on Linux, or in Docker with the image from `scripts/build_run_python_image.sh`. Docker on macOS hasn't been tested; a Linux cloud machine is the tested route. No saved run on `main` uses this condition yet.

### Building the submission ZIP

```bash
uv run python scripts/build_submission.py main
```

It packages the files tracked at that git ref into `../print-build-eval-<commit>.zip`, beside the repo, with this README at the ZIP's root (`--out` picks another path outside the repo). It writes nothing, and lists every reason, if the ZIP would be 50 MB or more, or would hold a video, `docs/context/`, `.git`, a secret, or a machine-local path such as a home folder or a LAN address. Left out on purpose, each with its reason in the script's `LEFT_OUT`: `docs/context/`, the two overnight logs, the failure atlas (`report/atlas/`) and the Estoa datasheet, which is fetched from Adafruit (product 2477) instead.

## The tasks

Each task is a folder in `tasks/`: the person's request (`brief.md`), the facts the person can measure if asked (`hidden_facts.yaml`), the checks (`requirements.yaml`), and a reference design that must pass every check (`reference.yaml`). Every task also gets the generic checks: the code builds, each part is one connected body, it fits the bed, and every overhang can be bridged (`bridges`).

| Task | The request | Graded on | Wording |
|---|---|---|---|
| `tripod-plate` | Dan's real first message: replace the lost plate that joins a camera to a borrowed tripod | a plate exists; it fits the clamp; the bolt goes through, head on the clamp side; the head fits its recess; the bolt reaches into the camera | Dan's own words, approved by him for model runs |
| `nut-knob` (M3, M5, M8) | A hand knob with a hex nut pressed in, which must stay in upside down | one part; about the right size; a pocket that takes the nut, stops it turning and stops it going through; the nut presses in and holds on this printer, or a test print would find a size that does; the bolt passes through | draft, not approved: runs are exploratory. M8 has a reference but no runs |
| `bearing-wheel` | A closet-door roller wheel on two 608 bearings and an M8 bolt | about the old wheel's size; room for both bearings; the bearings press in and stay, or a test print would find a size; the bolt goes through | written by Claude and not reviewed by Dan; the door is invented: runs are exploratory |
| `m5-spacer` | A 20 mm spacer for an M5 bolt, everything stated | one part; size; a clearance hole; round | a control: if models fail it, the harness is broken |
| `estoa-light` | The box behind Dan's Estoa wall light | 7 checks on the assembled box | built on PR #23, approved by Dan, **not merged and not run**: no results |
| `phone-stand` | A desk-clamp phone stand | its `requirements.yaml` names checks that were never built | **can't run** |

Why each is hard, and every limit's source, is in its `brief.md`. The fit limits come from test prints made on one Bambu Lab X1C in one PLA, recorded with predictions committed before printing (`results/predictions/`). Photos of those prints are hosted, not committed; `docs/media/photos.md` indexes them.

### Conditions

- **`can_ask`** (the main one): the request and the setup facts. The person's own measurements are withheld, and the model can ask for them with `measure`. The person is a lookup table, not a model: anything not on record gets "I can't measure that".
- **`all_given`**: the same, with every recorded measurement stated up front. Passing only here means the model didn't ask.
- **`can_run_code`**: `can_ask` plus a sandboxed `run_python` tool, and `submit_design` builds every part and sends build errors back.

Every condition also has `report_limitation`, which changes nothing and records what the model wanted but couldn't use.

## How grading works

- **Code, not a judge.** Every check is a program reading the built geometry (`pbe/graders/`). No LLM judges anything.
- **Three answers per check:** pass, fail, or not graded. Not graded means the test prints on record can't decide the case. It's never a pass.
- **One verdict per trial:** pass (every counted check passes), fail, not graded, or **declined**: the model handed in no final part, or a final part whose own code stops until a measurement it left blank is filled in (`pbe/graders/declined.py`). Declined is neither a pass nor a fail.
- **Test prints are graded but don't count.** The generic checks run on test prints too, and `summary.csv` lists their failures (`test_print_failed`), but a test print can't fail a trial on its own.
- **Grade the outcome, not the technique.** `bridges` asks whether every overhang will print, so a stepped roof, flipping the part or moving the feature all pass.
- **How the checks are tested** (`tests/`): each reference passes every check; versions of the real failures fail the check aimed at them and no other; simple reward hacks fail; designs unlike the reference pass; and cases between two records come back not graded.
- **No independent CAD or printing expert has reviewed the checks or the verdicts.** Dan wrote the tasks from his own builds and made the calls listed under [Limits](#limits). Claude wrote the checks, and the audits are further readings by Claude and Codex.

## Results

<!-- results:start (written by scripts/results_table.py; don't edit by hand) -->
104 trials of 12 models, from the saved runs in `results/runs/` (smoke tests left out). Each model ran 1 to 3 times per task and condition, so these are pilots: raw counts, not pass rates, and no ranking. Other is a trial with no submission or an infrastructure error. Cost is what OpenRouter charged.

| Condition | Trials | Pass | Fail | Not graded | Declined | Other | Cost |
|---|---|---|---|---|---|---|---|
| `all_given` | 10 | 1 | 7 | 1 | 1 | 0 | $1.11 |
| `can_ask` | 94 | 26 | 43 | 21 | 4 | 0 | $7.48 |
| **all** | **104** | 27 | 50 | 22 | 5 | 0 | $8.60 |

### `bearing-wheel` (draft by Claude, not reviewed by Dan: exploratory)

| Condition | Model | Trials | Pass | Fail | Not graded | Declined | Other | Cost |
|---|---|---|---|---|---|---|---|---|
| `can_ask` | anthropic/claude-haiku-5.5 | 2 | 0 | 2 | 0 | 0 | 0 | $0.02 |
| `can_ask` | anthropic/claude-opus-5.5 | 2 | 1 | 0 | 1 | 0 | 0 | $0.52 |
| `can_ask` | anthropic/claude-sonnet-5.5 | 2 | 0 | 2 | 0 | 0 | 0 | $0.25 |
| `can_ask` | deepseek/deepseek-v4-pro-0813 | 2 | 0 | 2 | 0 | 0 | 0 | $0.03 |
| `can_ask` | deepseek/deepseek-v4.1-flash | 2 | 0 | 2 | 0 | 0 | 0 | $0.12 |
| `can_ask` | google/gemini-3.8-flash | 2 | 1 | 1 | 0 | 0 | 0 | $0.19 |
| `can_ask` | google/gemini-4-argon | 2 | 0 | 0 | 2 | 0 | 0 | $0.37 |
| `can_ask` | openai/gpt-6-luna | 2 | 0 | 2 | 0 | 0 | 0 | $0.01 |
| `can_ask` | openai/gpt-6.1-sol | 2 | 1 | 0 | 1 | 0 | 0 | $0.34 |
| `can_ask` | qwen/qwen3.8-flash | 2 | 0 | 1 | 1 | 0 | 0 | $0.10 |
| `can_ask` | z-ai/glm-5.3-flash | 2 | 0 | 1 | 1 | 0 | 0 | $0.12 |

### `m5-spacer` (control, draft wording: exploratory)

| Condition | Model | Trials | Pass | Fail | Not graded | Declined | Other | Cost |
|---|---|---|---|---|---|---|---|---|
| `can_ask` | anthropic/claude-haiku-5.5 | 1 | 1 | 0 | 0 | 0 | 0 | $0.00 |
| `can_ask` | anthropic/claude-opus-5.5 | 1 | 1 | 0 | 0 | 0 | 0 | $0.06 |
| `can_ask` | anthropic/claude-sonnet-5.5 | 1 | 1 | 0 | 0 | 0 | 0 | $0.05 |
| `can_ask` | deepseek/deepseek-v4-pro-0813 | 1 | 1 | 0 | 0 | 0 | 0 | $0.00 |
| `can_ask` | deepseek/deepseek-v4.1-flash | 1 | 1 | 0 | 0 | 0 | 0 | $0.01 |
| `can_ask` | google/gemini-3.8-flash | 1 | 1 | 0 | 0 | 0 | 0 | $0.02 |
| `can_ask` | google/gemini-4-argon | 1 | 1 | 0 | 0 | 0 | 0 | $0.02 |
| `can_ask` | openai/gpt-6-luna | 1 | 1 | 0 | 0 | 0 | 0 | $0.00 |
| `can_ask` | openai/gpt-6.1-sol | 1 | 1 | 0 | 0 | 0 | 0 | $0.03 |
| `can_ask` | qwen/qwen3.8-flash | 1 | 1 | 0 | 0 | 0 | 0 | $0.01 |
| `can_ask` | x-ai/grok-4.7 | 1 | 1 | 0 | 0 | 0 | 0 | $0.06 |
| `can_ask` | z-ai/glm-5.3-flash | 1 | 1 | 0 | 0 | 0 | 0 | $0.01 |

### `nut-knob/M3` (draft, not approved by Dan: exploratory)

| Condition | Model | Trials | Pass | Fail | Not graded | Declined | Other | Cost |
|---|---|---|---|---|---|---|---|---|
| `can_ask` | anthropic/claude-haiku-5.5 | 1 | 0 | 1 | 0 | 0 | 0 | $0.01 |
| `can_ask` | anthropic/claude-opus-5.5 | 3 | 1 | 0 | 2 | 0 | 0 | $0.43 |
| `can_ask` | anthropic/claude-sonnet-5.5 | 1 | 0 | 1 | 0 | 0 | 0 | $0.06 |
| `can_ask` | deepseek/deepseek-v4-pro-0813 | 1 | 0 | 1 | 0 | 0 | 0 | $0.01 |
| `can_ask` | deepseek/deepseek-v4.1-flash | 1 | 0 | 0 | 1 | 0 | 0 | $0.01 |
| `can_ask` | google/gemini-3.8-flash | 1 | 0 | 1 | 0 | 0 | 0 | $0.08 |
| `can_ask` | google/gemini-4-argon | 1 | 0 | 0 | 1 | 0 | 0 | $0.10 |
| `can_ask` | openai/gpt-6-luna | 1 | 0 | 0 | 1 | 0 | 0 | $0.01 |
| `can_ask` | openai/gpt-6.1-sol | 1 | 1 | 0 | 0 | 0 | 0 | $0.12 |
| `can_ask` | qwen/qwen3.8-flash | 1 | 0 | 1 | 0 | 0 | 0 | $0.03 |
| `can_ask` | z-ai/glm-5.3-flash | 1 | 0 | 0 | 1 | 0 | 0 | $0.00 |

### `nut-knob/M5` (draft, not approved by Dan: exploratory)

| Condition | Model | Trials | Pass | Fail | Not graded | Declined | Other | Cost |
|---|---|---|---|---|---|---|---|---|
| `can_ask` | anthropic/claude-haiku-5.5 | 1 | 0 | 0 | 1 | 0 | 0 | $0.01 |
| `can_ask` | anthropic/claude-opus-5.5 | 1 | 1 | 0 | 0 | 0 | 0 | $0.15 |
| `can_ask` | anthropic/claude-sonnet-5.5 | 1 | 1 | 0 | 0 | 0 | 0 | $0.07 |
| `can_ask` | deepseek/deepseek-v4-pro-0813 | 1 | 0 | 0 | 1 | 0 | 0 | $0.03 |
| `can_ask` | deepseek/deepseek-v4.1-flash | 2 | 0 | 1 | 1 | 0 | 0 | $0.04 |
| `can_ask` | google/gemini-3.8-flash | 1 | 1 | 0 | 0 | 0 | 0 | $0.09 |
| `can_ask` | google/gemini-4-argon | 1 | 0 | 0 | 1 | 0 | 0 | $0.07 |
| `can_ask` | openai/gpt-6-luna | 1 | 0 | 0 | 1 | 0 | 0 | $0.01 |
| `can_ask` | openai/gpt-6.1-sol | 1 | 0 | 0 | 1 | 0 | 0 | $0.14 |
| `can_ask` | qwen/qwen3.8-flash | 1 | 0 | 1 | 0 | 0 | 0 | $0.03 |
| `can_ask` | x-ai/grok-4.7 | 1 | 0 | 0 | 1 | 0 | 0 | $0.48 |
| `can_ask` | z-ai/glm-5.3-flash | 1 | 0 | 0 | 1 | 0 | 0 | $0.00 |

### `tripod-plate` (Dan's own words, approved by Dan)

| Condition | Model | Trials | Pass | Fail | Not graded | Declined | Other | Cost |
|---|---|---|---|---|---|---|---|---|
| `all_given` | anthropic/claude-haiku-5.5 | 1 | 0 | 1 | 0 | 0 | 0 | $0.00 |
| `all_given` | anthropic/claude-opus-5.5 | 1 | 0 | 1 | 0 | 0 | 0 | $0.25 |
| `all_given` | anthropic/claude-sonnet-5.5 | 1 | 0 | 0 | 1 | 0 | 0 | $0.13 |
| `all_given` | deepseek/deepseek-v4.1-flash | 1 | 0 | 1 | 0 | 0 | 0 | $0.11 |
| `all_given` | google/gemini-3.8-flash | 1 | 0 | 1 | 0 | 0 | 0 | $0.14 |
| `all_given` | google/gemini-4-argon | 1 | 1 | 0 | 0 | 0 | 0 | $0.22 |
| `all_given` | openai/gpt-6-luna | 1 | 0 | 1 | 0 | 0 | 0 | $0.01 |
| `all_given` | openai/gpt-6.1-sol | 1 | 0 | 0 | 0 | 1 | 0 | $0.14 |
| `all_given` | qwen/qwen3.8-flash | 1 | 0 | 1 | 0 | 0 | 0 | $0.05 |
| `all_given` | z-ai/glm-5.3-flash | 1 | 0 | 1 | 0 | 0 | 0 | $0.05 |
| `can_ask` | anthropic/claude-haiku-5.5 | 3 | 0 | 3 | 0 | 0 | 0 | $0.02 |
| `can_ask` | anthropic/claude-opus-5.5 | 3 | 0 | 3 | 0 | 0 | 0 | $0.67 |
| `can_ask` | anthropic/claude-sonnet-5.5 | 3 | 0 | 3 | 0 | 0 | 0 | $0.42 |
| `can_ask` | deepseek/deepseek-v4-pro-0813 | 3 | 0 | 3 | 0 | 0 | 0 | $0.05 |
| `can_ask` | deepseek/deepseek-v4.1-flash | 3 | 1 | 2 | 0 | 0 | 0 | $0.04 |
| `can_ask` | google/gemini-3.8-flash | 3 | 2 | 1 | 0 | 0 | 0 | $0.49 |
| `can_ask` | google/gemini-4-argon | 3 | 2 | 1 | 0 | 0 | 0 | $0.46 |
| `can_ask` | openai/gpt-6-luna | 3 | 0 | 2 | 0 | 1 | 0 | $0.01 |
| `can_ask` | openai/gpt-6.1-sol | 3 | 0 | 0 | 0 | 3 | 0 | $0.25 |
| `can_ask` | qwen/qwen3.8-flash | 3 | 0 | 3 | 0 | 0 | 0 | $0.17 |
| `can_ask` | x-ai/grok-4.7 | 1 | 1 | 0 | 0 | 0 | 0 | $0.46 |
| `can_ask` | z-ai/glm-5.3-flash | 3 | 0 | 2 | 1 | 0 | 0 | $0.13 |
<!-- results:end -->

Every trial's transcript, design and grades are in `results/runs/`; the results page (step 5) shows each one with its parts in 3D. `scripts/digest.py <run> --why` prints each failure's evidence.

Two follow-up experiments on saved trials, each with its own write-up:
- **Telling the model how its test print came out** (`docs/coupon-loop.md`, run `loop-sample` and `loop-sample-2`): one more turn after a reply built from the recorded prints, against a neutral "take another look".
- **Sending a build error back once** (`docs/crash-replay.md`, run `crash-replay`): each saved crash replayed with its error.

> **TODO(Dan): where models fail.** From what you saw in the transcripts and on the results page.
>
> **TODO(Dan): the hot take.** The one lesson to remember.

## Limits

### Assumptions the verdicts rest on

These are treated as true without a print that shows them for that exact case. The full table, and the prints that would settle each, is in `docs/limitations.md`.

<!-- assumptions:start (written by scripts/results_table.py; don't edit by hand) -->
| Assumption | Check | What rests on it in the saved runs |
|---|---|---|
| The webcam bolt is 10 mm long under its head. Nobody recorded it. | tripod R5 | Every tripod R5 verdict (31 pass, 1 fail), so all 7 tripod passes |
| One 38 mm plate fit the clamp; 37 to 39 mm passes on an estimate of the jaws' travel. | tripod R2 | Every graded tripod R2 verdict (24 pass, 6 fail) |
| A roof with the bolt's hole cut through it tangles at the models' shapes and sizes, as it did on the Arca plate and coupon A's H cell (a 20 mm square with a 6 mm hole, printed once). | `bridges` | 17 trials that fail on `bridges` alone (Dan's call: they fail) |
<!-- assumptions:end -->

### Whose calls these are

From the audit of the saved failures (issue 15):
- **Dan's:** a test print can't fail a trial on its own; declining is its own verdict, never a pass; a roof with the bolt's hole cut through it fails `bridges`; nothing new is printed or measured before publishing, so what the records can't decide is not graded; one printer and one filament.
- **Claude's, delegated by Dan** ("do what you think is best"): M3 at +0.1 mm is read as unsettled, so it's not graded; DeepSeek V4.1 Flash's M5 test print labelled `final` stays a fail. These aren't Dan's expert judgment. Also Claude's: one official set of counts, with no second, more optimistic score (issue 35).

### Known limits

- **Pilots, not pass rates.** One to three trials per model per task.
- **One printer, one filament.** The fit and bridge limits hold for a Bambu Lab X1C in one PLA only.
- **One person's projects.** The tasks come from Dan's builds and mostly one agent's mistakes. Only the tripod's request was approved before it ran.
- **The phone stand can't run**, and print-settings mistakes (failure class C10) aren't tested: a submission has no field for them, and nothing is sliced.
- **Code review findings not fixed.** Two reviews of `main` (issues 2 and 4, closed as not planned) listed findings that weren't fixed; they stand as known limits. Among them, as last checked on those issues: model-written part code can still read files in the repository while it builds (it gets no network and no environment); a nut pocket 0.8 to 1.5 times the nut's size counts as nut-sized for the knob's R3, so a pocket too small for the nut can pass R3 and be left to R4; `bridges` samples one plane per layer and directions every 5°, so a feature one layer thick can be missed and verdicts can depend on the part's rotation; `bed_fit` uses the nominal bed and has no failing test. Code added since 2 November hasn't had that full review.
- **Detail text can differ by platform.** Every saved verdict reproduces on Linux as on macOS, but tied bridge directions can come out mirrored in the detail text.

## What's built and what isn't

Built: the four runnable task families above with references and checks; the runner with the lookup-table person and three conditions; sandboxed builds; regrading; the test-print loop and the crash replay; the results page; the test print designs and their recorded outcomes (`coupons/`, `results/predictions/`).

Not built: an assembly simulation (parts moving into place along the manual's steps); a printer simulator with a hidden error; any score beyond pass, fail, not graded and declined; a comparison with a hand ranking; a simulated builder. The failure atlas (`report/atlas/`) builds only on Dan's Mac: it uses `sips` and points at local photos.

## Where things are

The eval design guide suggests `tasks/`, `reference/`, `graders/`, `results/` and `transcripts/`. Here:

| Guide | This repo |
|---|---|
| `tasks/` | `tasks/<task>/brief.md` (the request), `hidden_facts.yaml` (what the person can measure), `requirements.yaml` (the checks) |
| `reference/` | `tasks/<task>/reference.yaml` |
| `graders/` | `pbe/graders/`; the submission format and building in `pbe/parts/` |
| `run_eval.py` | `pbe/eval.py` (`uv run python -m pbe.eval`), with the model loop in `pbe/runner/` |
| `requirements.txt` | `pyproject.toml` and `uv.lock` |
| `results/` | `results/runs/<run>/summary.csv` and each trial's `grades.json`; test print records in `results/predictions/` |
| `transcripts/` | every trial's `transcript.json`, beside its grades in `results/runs/` |

Also:
- `seeds/`: the real failures behind the tasks (tripod, Estoa, side projects, the test prints), each tagged with a failure class from `seeds/classes.yaml`. They're evidence, not tasks, and their `grader:` fields are planned, not built.
- `catalog/`: the hardware bin (`hardware.yaml`, with real thread lengths) and the printer (`printer.yaml`).
- `coupons/`: the test print designs and the scripts that predicted their outcomes.
- `docs/`: `scoring.md` (the quality bar), `limitations.md`, and the write-ups of each experiment. `PLAN.md` is the working plan and `CHANGELOG.md` ties every change to its evidence.
- `scripts/`: the results page, the README's results table, the reproduce script and the experiments.
- `examples/arca-plate/`: the Arca plate before and after its first print.

## Future work

- **More test prints** to turn assumptions into records: the models' roof shapes, ring roofs, finer nut clearances, the clamp's jaw travel, the bolt's length. The list is in `docs/limitations.md`.
- **Letting the model suggest hardware**, with only the printer and filament fixed (issue 12).
- **Letting the model ask clarifying questions**, not only for measurements (issue 13).
- **A research step, as a recorded lookup**, so reruns stay identical (issue 16).
- More trials per model, the Estoa task's first runs (issue 37), and the assembly simulation.

## Provenance and how AI was used

- **Tasks** come from Dan's own builds: the tripod plate (his real first message to a coding agent, and the agent's mistakes), Estoa (his wall light), and his test prints. The knob, wheel and spacer requests are drafts. Every limit a check uses traces to a test print, a datasheet or the ISO tables in `catalog/hardware.yaml`.
- **Test prints** were designed, printed and recorded before Oct 30, each with the checks' predictions committed before printing (`results/predictions/`).
- **AI use:** Claude (through Claude Code) wrote nearly all the code, checks, tests and docs, including this README, from Dan's direction, and Dan decided the calls listed above. Codex reviewed many of the pull requests, and each of its findings was checked against the code. The agent sessions behind the seeds are in Dan's private archive; their ids in the seed files are kept as opaque references.
- Models are tested only through OpenRouter's API, under its terms.

## Prior art

| Work | Licence | How it's used |
|---|---|---|
| BenchCAD (`BenchCAD/BenchCAD-main`, HF `BenchCAD/BenchCAD`) | MIT code, CC-BY data (per its README; read its LICENSE before reuse) | CadQuery sandbox, standard fastener families |
| BenchCAD 2.0 library (`BenchCAD-org/benchcad-2`) | MIT | part-family format (a build file plus a check file), cited |
| BenchCAD 2.0 harness (`BenchCAD-org/benchcad-2-main`) | none | ideas only, cited |
| CADEngBench (arXiv 2608.09296, `coderjs-lab/cadengbench`) | none | layered grading, cited and reimplemented |
| Hephaestus-CCX (arXiv 2605.17448) | — | typed requirements, cited |
| HW-Bench | — | a different scope: funded, professional hardware engineering, not something to beat. TODO(Dan): add its link and one line on its scope; this session couldn't reach its site to check |
| Epoch Furniture Assembly, IKEA-Manual, FDM-Bench, VLM DfM rules (2311.12668), FEABench, EngDesign, SKY-001, NVIDIA ASPIRE, τ-Bench and τ²-Bench, Anthropic's "Demystifying evals for AI agents" | various | read as prior art; nothing copied |

## Licence

> **TODO(Dan): the licence.** None is set yet. Check the prior-art table against whichever you choose.

## Private material

`docs/context/` holds Dan's own notes and clippings. It's private: the submission ZIP leaves it out, and it stays out of any public copy. Citations elsewhere name their source instead of pointing into it.
