# Notes for agents

Start with `PLAN.md` (phases, constraints, Dan's open decisions), then `docs/scoring.md` (the quality bar every task and grader is held to).

- Keep `CHANGELOG.md` current: one entry per change that affects results, with the evidence behind it.
- Never print, echo or commit API keys. Read them from 1Password at run time.
- Don't copy code from repos with no license (CADEngBench, the BenchCAD 2.0 harness). Reimplement and cite.
- `docs/context/` is private source material, copied verbatim from `~/Source/explorations/inbox/`. Don't edit it, and keep it out of public copies. New pastes from Dan go to the explorations inbox first (global rule), then get copied here if relevant.
- Graders should be code wherever possible. Use an LLM judge only where no program can decide, and say so in the report.
- Every number in the report comes from a run saved under `results/`. Don't make up illustrative numbers outside clearly labeled mockups.
- No physical work from Dan: never ask for or offer prints, coupon flips, measurements or photos, even as optional or through someone else. He closed this on 2026-10-30. Grade only from `results/predictions/`, `catalog/`, `seeds/` and his session records. Anything those can't decide is "not graded" or a labeled range estimated from recorded prints, reported as a limitation of the eval, never a to-do for him. Never imply a model's design was printed. He can still review text, such as request wording.
- Every review step also walks the scoring criteria: `docs/scoring.md` and section 5 of `docs/context/2026-10-30-guide-eval-design-guide-find-what-ai-cant-do-yet.md` (the 100-point rubric). Take each criterion in turn, answer it from evidence (a test, a run, a transcript), fix what falls short or say why it can't be fixed yet, and record one line per criterion in the log. Name what's weak instead of awarding points.
- Video: record masters in OBS as Apple VT ProRes 422 MOV, 1920x1080, 30 fps, and make H.264 copies for the report without touching the masters. Clips live in `~/Movies/print-build-eval/`, not the repo. Never give an encoder quality number without checking which way its scale runs, and check the first take's bitrate with ffprobe before the rest are shot. To watch live, open a local getUserMedia page on OBS Virtual Camera in Claude in Chrome, because the in-app browser pane blocks camera access.
- Stay inside this eval: read "the artifacts" as the eval's own, even when a request says "other artifacts". Don't go through or propose changing other projects' artifacts (Bench Parts Grid, Marea Build Book and so on). If a task could reach further, do the eval's part and stop, without scanning the rest to find out.

## Rules that also have to hold in a cloud session

A cloud session gets this file but not Dan's `~/.claude` or the memory directory, so what it needs from them is here, along with the rules above.

- Work on a branch and open a PR. Never commit to or push `main`, and commit or push only when asked or when the session's brief says to. One squashed commit per PR; update a pushed PR with `git commit --amend` and `git push --force-with-lease`, never `--force`. Restack with `git rebase --onto <base> <old-base>` and re-run the tests. Don't rewrite a branch another session is using.
- The goal is a reusable framework and honest lessons, built from a few failure classes (`seeds/classes.yaml`) and scenarios generated from them, not the best final task set. Requests describe the function in a person's own words and leave the mechanism to the model.
- Pastes from Dan go to the explorations inbox, which a cloud session can't reach. Don't save them here: say what still needs saving.
- In a cloud session `OPENROUTER_API_KEY` is a placeholder and the proxy attaches the real key, so `op` isn't needed. Spend a run with `--budget`. Commit and push results as you go, because a reclaimed VM keeps only the conversation, and `results/runs/**/parts/` isn't committed at all.
