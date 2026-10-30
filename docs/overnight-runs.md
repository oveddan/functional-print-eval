# Overnight runs

How to let the eval's iterate loop (run, read failures, fix a grader or prompt, log, run again) work while Dan is away. Researched 2026-10-30 from the official docs (links at the end). Where the docs are silent this says **unclear**.

## Options compared

| | Local, Mac kept awake | Cloud session, one long prompt | Cloud scheduled routine (`/schedule`) | `/loop` | Workflow tool |
|---|---|---|---|---|---|
| Setup Dan must do | Keep-awake, export key in a shell | Private GitHub repo, cloud environment, key, network allowlist | Same as cloud session, plus the routine | None extra | None extra |
| Runs if the Mac sleeps | No | Yes (continues if the app closes) | Yes | No | Only where its session lives |
| Max unattended time | Mac's uptime | **Unclear** (no documented cap; an idle VM pauses after a few minutes, and a reclaimed VM loses background commands and `/loop` tasks) | One run per hour at most; per-run length **unclear** | Recurring tasks expire after 7 days; dies with the process | No time cap; agent count is the limit |
| Fits "run, read, fix, log, repeat" | Yes | Yes, as plain sequential work | Awkward: every run is a fresh clone with no memory, so state must live in git | Yes locally, shaky in cloud | Overkill: the loop is sequential, and it costs the most (many agents) |
| Cost | Plan usage plus OpenRouter | Plan usage plus OpenRouter (no compute charge) | Same, 100 runs/hour account cap | Same | Highest; the guideline here is under 10 agents |
| Risk for this repo | None; CadQuery already works | CadQuery on the cloud image is **unverified**; Python 3.12 there is **unclear** | Same as the cloud session | Lost on sleep | Not needed |

## Recommendation

0. **Best if set up: the home server `ovedai`, under a new unprivileged account (next section).** Always on, no keep-awake; needs a one-time account setup and an `import cadquery` check.
1. **Otherwise tonight: run it locally.** Nothing here needs Dan's approval beyond keep-awake, the env already runs CadQuery, and nothing leaves the machine. Use a dedicated branch in a fresh worktree, not `main`.
2. **Cloud once it has a 10-minute smoke test.** It frees the Mac, but three things are unproven (below), and it forces a GitHub push of a repo that today has no remote. Try it for a short run before trusting it overnight.
3. **Skip the Workflow tool** for this loop, and use `/loop` only as the local driver if wanted. A single session with an explicit loop in its prompt (below) is simpler and is what both targets run.
4. A scheduled routine is a backstop at most: hourly minimum, fresh clone each run, so it can only continue from what is committed to a branch.

Unproven for cloud: (a) the docs list Python 3.x with uv but not the version, and whether `uv python install 3.12` works is unclear; (b) whether CadQuery's x86_64 Linux wheels install in the setup script was not checked; (c) maximum session length. The smoke test answers (a) and (b).

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
- **Runner ledger.** Every call adds `usage.cost` to `results/spend.json`. The runner refuses to start a call once the total reaches the cap (default $3), and the session stops. The ledger is committed with each iteration, so a cloud run that restarts from a fresh clone still sees what was spent.
- **Iteration and time limits** in the prompt (below).

Note the ledger and cap check are not in `pbe/llm.py` yet; the main session should add them before an unattended run (or the prompt's first step is to add them and commit). Today the only protection would be the key limit.

## Dan's one-time steps (each is his to do or approve)

Both targets:
1. Create the capped overnight OpenRouter key (above). Never paste it into chat or a file.

Local:
2. Approve keep-awake for the session in the desktop app (Code tab settings), or run it in a terminal tab: `caffeinate -i` while the session runs. Keep the Mac on power. (I changed no settings.)
3. In the terminal that launches Claude, `export OPENROUTER_API_KEY=...` for the capped key (from 1Password, so it never sits in a file) and start the session from there; `op read` may need an unlock that expires, so the env var is the safer path. `pbe/llm.py` already prefers the env var.
4. Create the worktree/branch: `git worktree add ../overnight -b overnight/2026-10-30` and paste the prompt there.

Cloud (only after the smoke test passes):
5. Decide whether to push. The repo has no remote. Create a **private** GitHub repo and push a branch. The repo tracks `docs/context/` (16 private source files) and 7 PNG renders in `docs/media/`. Decide first whether to push those, or push a branch with `docs/context/` removed. Alternative with no GitHub at all: `claude --cloud` from the terminal bundles a local repo (git 2.31+, at least one commit, under 100 MB), but it can only push results back if there is a GitHub remote it has push access to, so results would stay in the session transcript.
6. Install the Claude GitHub App on that private repo (or run `/web-setup`).
7. Create a cloud environment with: network access set to **Custom**, allowed domain `openrouter.ai`, and "include default list of common package managers" ticked (the default Trusted list does not include openrouter.ai); env var `OPENROUTER_API_KEY=<capped key>`; and a setup script (below).
8. Know the secret trade-off: environment variables are readable by anyone using the environment and by commands Claude runs, so the capped key is exposed to the session. The docs' safer "network secret" (the proxy adds the key to requests to listed hosts, so it never appears in the session) would need `pbe/llm.py` to send no key itself; how to configure the header is unclear, so use the capped env var for now.
9. Add a branch ruleset on GitHub protecting `main`: the cloud proxy blocks tag pushes and branch deletes but does not restrict which branch a push updates.
10. Start the session from the desktop app: choose the cloud environment, pick the repo, and paste the prompt. (Moving a local session via Open in > Cloud is possible, but how files move is unclear, so start fresh.)

Setup script for the cloud environment (runs as root, must exit 0, keep under ~5 minutes; setup scripts cannot see environment variables):

```bash
#!/bin/bash
set -e
command -v uv >/dev/null || pip install uv
uv python install 3.12 || true
uv sync --frozen
uv run python -c "import cadquery, trimesh; print('cadquery ok')"
```

If `import cadquery` fails there, stay local.

## What one overnight iteration does

1. Read `CLAUDE.md`, `PLAN.md`, `docs/scoring.md`, the tail of `CHANGELOG.md` and `results/spend.json`.
2. Run the test suite (`uv run pytest`). If it fails before any change, stop.
3. Run the eval on the current tasks and models, writing under `results/` (cost counted in the ledger).
4. Read every failure transcript. Classify each as format, design, grader bug, or task bug.
5. Make at most one fix: a grader bug, a task or prompt wording, or a measurement-table entry. Do not change what is being scored to make scores rise, and do not weaken a check without a regression test.
6. Re-run the tests and the affected tasks. Keep the change only if tests pass and no previously passing reference now fails; otherwise revert it.
7. Append a `CHANGELOG.md` entry with the evidence (run ids under `results/`, before and after), then commit once to the overnight branch.

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

Setup: read CLAUDE.md, PLAN.md, docs/scoring.md, the end of CHANGELOG.md, and docs/overnight-runs.md. Create/confirm branch overnight/<today's date> and work only there. Never touch main. Do not push (local) / push only this branch (cloud). Do not change settings or create repos.

Secrets: the key is in OPENROUTER_API_KEY. Never print, echo, log, or commit it, and never run env/printenv or any command that would show it.

Budget: hard cap $3.00 total OpenRouter spend, tracked in results/spend.json (add a ledger and a pre-call cap check to the runner first if it is not there, with a test, and commit that as the first change). Max 6 iterations, 8 hours.

Each iteration: (1) uv run pytest; (2) run the eval on the current tasks, saving under results/; (3) read every failing transcript and classify it as format, design, grader bug, or task bug; (4) make at most one fix to a grader, task wording, or measurement table, never lowering a bar just to raise scores and adding a regression test for any grader change; (5) re-run tests and the affected tasks, and revert the fix if anything that passed now fails; (6) append a CHANGELOG.md entry with the evidence (run ids, before/after) and commit once.

Stop when: spend reaches the cap, 6 iterations are done, tests are red and not fixable within the iteration, two iterations in a row find nothing worth fixing, a call fails on auth/credit, or 8 hours pass. Then write results/overnight-<date>.md (what ran, spend, what changed, what is left, anything you were unsure about) and commit it. Do not start another iteration after writing it.
```

## Follow-up: move the key to a network secret

Environment variables are readable by the session, so the capped key is exposed to it. A cloud environment's **network secret** is safer: the agent proxy attaches the secret to requests for the hosts listed (here `openrouter.ai`), and the key never appears in the session's environment or in any file. Not yet tried. To do it:
- Change `pbe/llm.py` so it sends the request without a real key (or a placeholder) when a setting such as `PBE_PROXY_KEY=1` is on, instead of failing when `OPENROUTER_API_KEY` and `op` are both missing.
- In the smoke test, check that the proxy's header injection works with OpenRouter's `Authorization: Bearer` header; the docs do not say how the header is formed (unclear).
- Keep the $3 key limit either way.

## Open questions for Dan

- Local tonight, or do the cloud smoke test first?
- If cloud: push the private repo with or without `docs/context/` and the PNG renders? (Dan 2026-10-30: pushing it all is fine.)
- 1Password in the cloud: not supported out of the box. The only route is a 1Password service account token as the env var plus the `op` CLI in the setup script, which adds a vault-wide secret and a download from a host not on the allowlist. Use the capped OpenRouter key directly instead.
- Cap: is $3 right out of the $10, and OK to create a separate capped key?

## Sources

Official docs, fetched 2026-10-30: code.claude.com/docs/en/ claude-code-on-the-web, cloud-environments, web-quickstart, routines, scheduled-tasks, workflows, tools-reference, desktop.
