# Overnight runs

How to let the eval's iterate loop (run, read failures, fix a grader or prompt, log, run again) work while Dan is away. Researched 2026-10-30 from the official docs (links at the end). Where the docs are silent this says **unclear**. The cloud parts were rechecked against the docs on 2026-11-03.

## Options compared

| | Local, Mac kept awake | Cloud session, one long prompt | Cloud scheduled routine (`/schedule`) | `/loop` | Workflow tool |
|---|---|---|---|---|---|
| Setup Dan must do | Keep-awake, export key in a shell | Cloud environment with a network secret and setup script | Same as cloud session, plus the routine | None extra | None extra |
| Runs if the Mac sleeps | No | Yes (continues if the app closes) | Yes | No | Only where its session lives |
| Max unattended time | Mac's uptime | **Unclear** (no documented cap; an idle VM pauses after a few minutes, a reclaimed VM loses background commands and `/loop` tasks, and a command moved to the background gets about 30 more minutes) | One run per hour at most; per-run length **unclear** | Recurring tasks expire after 7 days; dies with the process | No time cap; agent count is the limit |
| Fits "run, read, fix, log, repeat" | Yes | Yes, as plain sequential work | Awkward: every run is a fresh clone with no memory, so state must live in git | Yes locally, shaky in cloud | Overkill: the loop is sequential, and it costs the most (many agents) |
| Cost | Plan usage plus OpenRouter | Plan usage plus OpenRouter (no compute charge) | Same, 100 runs/hour account cap | Same | Highest; the guideline here is under 10 agents |
| Risk for this repo | None; CadQuery already works | Not yet smoke tested: CadQuery on the image, and bubblewrap inside the VM | Same as the cloud session | Lost on sleep | Not needed |

## Recommendation

0. **Best if set up: the home server `ovedai`, under a new unprivileged account (next section).** Always on, no keep-awake; needs a one-time account setup and an `import cadquery` check.
1. **Otherwise tonight: run it locally.** Nothing here needs Dan's approval beyond keep-awake, the env already runs CadQuery, and nothing leaves the machine. Use a dedicated branch in a fresh worktree, not `main`.
2. **Cloud once it has a 10-minute smoke test.** It frees the Mac. Try it for a short run before trusting it overnight.
3. **Skip the Workflow tool** for this loop, and use `/loop` only as the local driver if wanted. A single session with an explicit loop in its prompt (below) is simpler and is what both targets run.
4. A scheduled routine is a backstop at most: hourly minimum, fresh clone each run, so it can only continue from what is committed to a branch.

Checked in the first cloud session (2026-11-03, `changes/history.md`): (a) Python 3.12 is there; (b) the Linux CadQuery wheels import; (c) the VM allows bubblewrap's namespaces; the first session's setup script lacked `bubblewrap`, and in a second session, with the `apt-get` line below, it was there from the start; (d) the proxy replaces the placeholder key; (e) every reference passes, though nothing saved compares the numbers with the Mac's. Still unknown: (f) maximum session length.

## Option: the home server (`ovedai`)

Always on, no keep-awake, no GitHub push, no cloud unknowns. Facts below are from the server's own notes (`~/Source/ovedai/CLAUDE.md`, `docs/users.md`, `docs/hardware.md`); I have not logged in. It is Ubuntu on a Ryzen 7 3700X, 32 GB, with Docker and tmux. It has no Node and no system `claude`, and Claude Code installs per user with no root.

**Run it under a separate unprivileged account, not `danoved`.** `danoved` is in the `docker` group, which is root-equivalent, and the server notes say an agent running as `danoved` can reach root (and the Minecraft world, backups and the 936 GB data drive). An unattended overnight agent should not have that. The notes already describe the pattern: a second account with no sudo and no docker group, created by `./scripts/70-user-add.sh <name> [key.pub]`. A dedicated account (say `pbe`) also keeps its own `~/.claude` and archive.

Dan's steps:
1. Create the account on the server (needs root, so Dan runs it: `./scripts/70-user-add.sh pbe ~/.ssh/id_ed25519.pub`; the notes say to grant `danoved` temporary passwordless sudo only for that and revoke it after).
2. Install Claude Code for it: `ssh pbe@192.168.4.101 'curl -fsSL https://claude.ai/install.sh | bash'`, then log in once, interactively: `ssh -t pbe@192.168.4.101 'bash -lc claude'`. The login token lands in `/home/pbe/.claude`. Whether this should be Dan's own Claude account or another is his call.
3. Install `uv` as that user (`curl -LsSf https://astral.sh/uv/install.sh | sh`), copy the repo with its `.git` (no remote; `rsync -a --exclude .venv`, includes private `docs/context/`), then `uv sync --frozen` and `uv run python -c "import cadquery"`. That is the Linux x86_64 CadQuery check; I expect it to work but have not verified it. The 3.12 interpreter is downloaded by `uv`, so the account needs outbound internet.
4. **Connect by the LAN address `192.168.4.101` when scripting or at home.** Tailscale SSH on this box is in check mode: a tailnet connection re-demands browser re-auth about every 12 hours, and a non-interactive command hangs on it. Over the tailnet, a human at a keyboard can click through it, but do not start the run from a script that way. New accounts are deliberately off the tailnet, so `pbe` is reached from `danoved`'s tailnet hop to `localhost`, or from inside the house.
5. `ssh pbe@192.168.4.101`, `tmux new -s overnight`, `export OPENROUTER_API_KEY=...` (the capped key; `op read` will not unlock unattended; the server notes say credential files are the user's to write, never an agent's), `git switch -c overnight/<date>`, run `claude`, paste the prompt below, detach with `Ctrl-b d`. Without tmux the run dies when SSH drops.
6. Pre-approve `uv run`, `pytest` and `git commit` for the repo on the server. If the session stops for an approval overnight, the run stalls.
7. Morning: `git log overnight/<date>` and `results/overnight-<date>.md`, then fetch the branch back to the Mac.

Optional: add the server as a saved SSH connection in the desktop app to watch the session there (an app setting, Dan's to change). The desktop app currently shows no saved SSH connections.

## Spending cap: three layers

- **OpenRouter key limit (the hard one).** Create a *separate* OpenRouter API key for overnight use with a credit limit of about $3 (as I understand OpenRouter keys, a per-key limit can be set in the dashboard; check it exists there). Even a runaway loop cannot exceed it. Put only this key in the environment, never the main key.
- **Run budget.** `pbe/eval.py --budget` stops a run once its saved `cost_usd` totals reach the budget, checked before each trial, so the last trial can overshoot. It is per run, so it doesn't cap several runs together: the key limit does.
- **Iteration and time limits** in the prompt (below).


## Dan's one-time steps (each is his to do or approve)

Both targets:
1. Create the capped overnight OpenRouter key (above). Never paste it into chat or a file.

Local:
2. Approve keep-awake for the session in the desktop app (Code tab settings), or run it in a terminal tab: `caffeinate -i` while the session runs. Keep the Mac on power. (I changed no settings.)
3. In the terminal that launches Claude, `export OPENROUTER_API_KEY=...` for the capped key (from 1Password, so it never sits in a file) and start the session from there; `op read` may need an unlock that expires, so the env var is the safer path. `pbe/runner/llm.py` already prefers the env var.
4. Create the worktree/branch: `git worktree add ../overnight -b overnight/2026-10-30` and paste the prompt there.

Cloud:
5. Make sure the Claude GitHub App is installed on `oveddan/functional-print-eval`, or run `/web-setup`.
6. Create a new cloud environment, because a network secret applies to every session in its environment:
   - **Network access:** the default. Package managers and GitHub are covered, and a network secret's host is reachable whatever this is set to.
   - **Network secret:** type Bearer, allowed website `openrouter.ai`, header `Authorization`, prefix `Bearer`, and the capped key as the value. The key stays outside the VM.
   - **Environment variable:** `OPENROUTER_API_KEY=proxy-injected`, a placeholder so `pbe/runner/llm.py` doesn't reach for `op`.
   - **Do not set `PBE_NO_SANDBOX`.** If bubblewrap can't run there, the run should stop rather than go on without a sandbox.
   - **Setup script:** below.
7. Keep sessions off `main` by instruction (`CLAUDE.md`). GitHub rulesets aren't available on this private repo without Pro, and the cloud proxy doesn't restrict which branch a push updates.
8. Start the session from the desktop app under **Cloud**, on a branch that has `.claude/settings.json`. The `SessionStart` hook in it runs `uv sync --frozen`.

Setup script for the cloud environment (runs as root on Ubuntu 24.04, must exit 0, keep under about 5 minutes to be cached; it can't see the environment's variables):

```bash
#!/bin/bash
set -e
apt-get update
apt-get install -y bubblewrap libgl1 openscad xvfb
uv python install 3.12
```

`libgl1` is a precaution that hasn't been shown to be needed. `openscad` and `xvfb` are only for gallery renders.

## Cloud smoke test

Ask a first session in the new environment to do this and report each result:

1. `check-tools`, then `uv run python -c "import cadquery; from pbe.parts import build; print(build.sandbox())"`. It must print `bwrap`.
2. `uv run pytest`. The sandbox tests skip when there's no sandbox, so check they ran.
3. `uv run python -m pbe.eval --reference --task <each task>`. Every reference must pass as it does on the Mac.
4. One cheap trial: `uv run python -m pbe.eval --run cloud-smoke --task m5-spacer --model anthropic/claude-haiku-5.5 --trials 1 --budget 0.50`. A 401 means the proxy didn't replace the placeholder header.
5. Commit and push `results/runs/cloud-smoke` to the session's branch.

A run stopped by a reclaimed VM resumes: trials already saved are skipped. Results survive only if pushed, and `results/runs/**/parts/` isn't committed, so meshes have to be rebuilt with `--regrade`. The atlas's photos (`report/atlas/examples.yaml`) aren't in the repo, so the atlas doesn't build in the cloud.

## What one overnight iteration does

1. Read `CLAUDE.md`, `docs/plan.md`, `docs/scoring.md` and the newest entries in `changes/` (`uv run python scripts/changelog.py | head -200`), and add up the saved `cost_usd` of runs so far.
2. Run the test suite (`uv run pytest`). If it fails before any change, stop.
3. Run the eval on the current tasks and models with `--budget`, writing under `results/`.
4. Read every failure transcript. Classify each as format, design, grader bug, or task bug.
5. Make at most one fix: a grader bug, a task or prompt wording, or a measurement-table entry. Do not change what is being scored to make scores rise, and do not weaken a check without a regression test.
6. Re-run the tests and the affected tasks. Keep the change only if tests pass and no previously passing reference now fails; otherwise revert it.
7. Add a change file, `changes/<YYYY-MM-DD>-<slug>.md` (see `changes/README.md`), with the evidence (run ids under `results/`, before and after), then commit once to the overnight branch.

**Stops when any of these holds:** total spend reaches the cap; 6 iterations done; tests fail and cannot be fixed in the same iteration, or fail after a revert; two iterations in a row find no failure worth fixing; a call fails with auth or credit errors; or 8 hours elapsed. On stopping it writes `results/overnight-<date>.md` (what ran, spend, what changed, what is left) and commits it.

## Guardrails

- Never print, echo, log or commit a key. Do not run `env`, `printenv`, `set` or `op read` with output visible, and keep keys out of transcripts and result files.
- Commit each iteration to `overnight/<date>`. Never touch `main`, never push to it, never force-push, never create repos or change settings. Local: no push at all. Cloud: push only that branch.
- Follow `CLAUDE.md`: every number in the report comes from a saved run; graders stay code wherever possible and any LLM judge is named; don't copy unlicensed code; don't edit `docs/context/`.
- Squash the branch into one commit per PR before it is proposed (Dan's stacked-branch rule); the per-iteration commits are for overnight traceability only.
- Do not install other tools or fetch anything beyond the package installs and `openrouter.ai`.

## Prompt to paste

```
You are running the print-build-eval iterate loop unattended overnight. Nobody can answer questions until morning, so decide with the rules below and write down what you decided.

Setup: read CLAUDE.md, docs/plan.md, docs/scoring.md, the newest entries in changes/, and docs/overnight-runs.md. Create/confirm branch overnight/<today's date> and work only there. Never touch main. Do not push (local) / push only this branch (cloud). Do not change settings or create repos.

Secrets: the key is in OPENROUTER_API_KEY. Never print, echo, log, or commit it, and never run env/printenv or any command that would show it.

Budget: hard cap $3.00 total OpenRouter spend. Pass --budget to each run and add up the runs' saved cost_usd before starting another. Max 6 iterations, 8 hours.

Each iteration: (1) uv run pytest; (2) run the eval on the current tasks, saving under results/; (3) read every failing transcript and classify it as format, design, grader bug, or task bug; (4) make at most one fix to a grader, task wording, or measurement table, never lowering a bar just to raise scores and adding a regression test for any grader change; (5) re-run tests and the affected tasks, and revert the fix if anything that passed now fails; (6) add a change file under changes/ (format in changes/README.md) with the evidence (run ids, before/after) and commit once.

Stop when: spend reaches the cap, 6 iterations are done, tests are red and not fixable within the iteration, two iterations in a row find nothing worth fixing, a call fails on auth/credit, or 8 hours pass. Then write results/overnight-<date>.md (what ran, spend, what changed, what is left, anything you were unsure about) and commit it. Do not start another iteration after writing it.
```

## Open questions for Dan

- Cap: is a separate capped key's limit right for the runs planned?

## Sources

Official docs, fetched 2026-10-30, cloud pages again on 2026-11-03: code.claude.com/docs/en/ claude-code-on-the-web, cloud-environments, web-quickstart, routines, scheduled-tasks, workflows, tools-reference, desktop.
