---
name: try-a-print-request
description: Run the print-build-eval agent on a 3D-print request someone writes themselves (not one of the repo's fixed tasks), and read back the verdict, each general check, the parts' STL files and the cost. Use when someone asks to "try my own request", "run the eval on my prompt", "see what a model designs for X", or wants a quick model trial on a part idea of their own.
---

# Try a print request

The eval's tasks (`tasks/*/`) each come with hidden measurements, task checks and recorded test prints. This runs the same agent on a request someone writes themselves instead. The request becomes a throwaway task with nothing hidden and no checks of its own, so **only the general checks grade it**: `builds`, `connected_bodies`, `bed_fit` and `bridges`. Nothing checks that the part fits or does what was asked.

## Before running

1. **Get the request in the person's own words.** Don't rewrite it into a spec; the eval's point is that the model works out the mechanism. Ask them to put every measurement that matters in it: the model can call `measure`, but nobody answers (it hears that it can't be measured), so anything left out is a guess.
2. **Pick a model**, an OpenRouter id such as `anthropic/claude-sonnet-5.5` or `anthropic/claude-haiku-5.5`.
3. **Agree a budget and get a yes before spending.** A trial calls a paid API. `--budget` is US dollars for the one trial (default 0.50); no new model call starts once it's spent, so the last call can run over it. In the eval's saved `can_ask` trials the median trial cost under a cent on Haiku 5.5, about $0.08 on Sonnet 5.5 and $0.17 on Opus 5.5; the dearest single trials were $0.57 (Sonnet, Opus) and $1.01 (Gemini 4 Argon). A request of your own may take more turns than those tasks did.
4. **An OpenRouter API key.** Every model is called through [OpenRouter](https://openrouter.ai), which bills per call. To get one: make an account at openrouter.ai, add credits, and create a key in its settings. Then set it in the shell that runs the command, with `export OPENROUTER_API_KEY=<your key>` or by putting `OPENROUTER_API_KEY=<your key>` in front of the command. If the variable isn't set, the runner tries the 1Password CLI at the reference in `pbe/runner/llm.py` (`OP_REF`), and otherwise stops with an error that says how to set it. Never print, echo, log or commit the key, and don't write it to a file in the repo.

## Run

```bash
uv run python -m pbe.try_request "I want a hook for my bike helmet that screws under my desk..." --model anthropic/claude-sonnet-5.5 --budget 0.50
```

If you keep the key in 1Password, read it inline for the one command (use your own item's reference):

```bash
OPENROUTER_API_KEY="$(op read op://<vault>/OpenRouter/credential)" uv run python -m pbe.try_request "..." --model anthropic/claude-haiku-5.5 --budget 0.25
```

Options: `--condition` is one of `pbe.runner.agent.CONDITIONS` (default `can_ask`; `can_run_code` also lets the model run Python and needs the code sandbox), `--max-turns`, `--max-tokens`, and `--out <folder>` to choose where it's saved. In the saved trials the median took 40 s (Haiku) to 12 min (Qwen 3.8 Flash), and the slowest 37 min, so run it in the background.

## Read the output

- **First line:** the model, condition, outcome (`submitted`, `no_submission`, or `error` for an API failure or a reached budget) and the verdict.
- **Verdict:** `pass` means every general check passed, not that the part works. `fail` names a check that failed. `not graded` means no recorded test print decides that check for this geometry (for example a ledge narrower than any roof seen to tangle), so the eval can't say either way. `declined` means the model handed in a design but held back the part itself because something it needed wasn't known.
- **One line per check and part:** `pass`, `FAIL` or `not graded`, the check, the part, and what it found. A finding marked "test print, not counted" is on a test piece the model added, and doesn't count.
- **asked to measure:** what the model wanted to know. Each one is something the request could have said.
- **Parts:** each built part's STL, with its role (`final`, or `coupon` for a test print). Open them in a slicer or viewer to look at the design.
- **Cost** (what OpenRouter charged), turns and time, and the folder it's saved in: `transcript.json` (the whole conversation), `submission.yaml` (the design and its CadQuery code), `grades.json` and `parts/`.

Tries are saved under `results/local/try/`, which git ignores. They're not part of the eval's results: never cite one in the report or copy it into `results/runs/`.
