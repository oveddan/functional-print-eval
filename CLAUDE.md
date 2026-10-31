# Notes for agents

Start with `PLAN.md` (phases, constraints, Dan's open decisions), then `docs/scoring.md` (the quality bar every task and grader is held to).

- Keep `CHANGELOG.md` current: one entry per change that affects results, with the evidence behind it.
- Never print, echo or commit API keys. Read them from 1Password at run time.
- Don't copy code from repos with no license (CADEngBench, the BenchCAD 2.0 harness). Reimplement and cite.
- `docs/context/` is private source material, copied verbatim from `~/Source/explorations/inbox/`. Don't edit it, and keep it out of public copies. New pastes from Dan go to the explorations inbox first (global rule), then get copied here if relevant.
- Graders should be code wherever possible. Use an LLM judge only where no program can decide, and say so in the report.
- Every number in the report comes from a run saved under `results/`. Don't make up illustrative numbers outside clearly labeled mockups.
