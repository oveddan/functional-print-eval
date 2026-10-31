# Print-and-Build Eval

Can a frontier model design a 3D-printed mechanical fix that a person at home can print, test and assemble from the model's own instructions?

Scope, in Dan's words: "at home 3d printing of mechanical solutions … like for consumers". A person prompts an AI in plain language for a printed part: a mount, clamp, joint, adapter or small mechanism, on a consumer printer, with common hardware.

> Working draft. Dan rewrites any public-facing text.

## What it checks

Most CAD evals ask "is the shape right?" (overlap with a reference solid). This one asks whether a person can actually build the thing:

1. **Gates (pass/fail):** the CAD code runs and gives connected solids; parts print (no floating regions, supported overhangs, fits the bed); every bolt reaches its nut with enough thread, using real partial-thread lengths; the brief's typed requirements are met; the manual is consistent; a simulated builder working only from the manual ends with the right assembly.
2. **Score (how good):** yield under a hidden-error printer, margins, design for assembly (Boothroyd–Dewhurst part count and handling), and cost (print hours, filament, test-print waste).
3. **Validation:** the score should agree with Dan's hand ranking of a set of designs.

Tasks and failure cases come from a real project, a tripod and phone-stand mount built with an AI agent (see `seeds/tripod-failures.yaml`).

## Layout

```
tasks/<task>/     brief.md (the consumer's words), hidden_facts.yaml (revealed only if asked),
                  requirements.yaml (typed checks)
catalog/          hardware.yaml (bolts with real thread lengths), printer.yaml (error model)
seeds/            real failures (tripod, Estoa, side projects), each tagged with a general
                  failure class from classes.yaml, which maps classes to graders
docs/scoring.md   scoring criteria and method (the quality bar)
docs/context/     source notes copied from the explorations KB (private, see below)
PLAN.md           approach, phases, open decisions
CHANGELOG.md      every iteration, tied to evidence
```

```
pbe/              submission format (submission.py), hardware lookup (catalog.py),
                  sandboxed CadQuery build (build.py), geometry checks (checks.py), CLI (run.py)
examples/         submissions; arca-plate/ has the original design and the fix (backtest inputs)
report/atlas/     the failure atlas page, built from the seeds
tests/
```

Try it (needs [uv](https://docs.astral.sh/uv/); Python 3.12 and CadQuery install on first run):

```bash
uv run python -m pbe.run examples/arca-plate/original.yaml examples/arca-plate/fix.yaml
uv run pytest
```

Planned and not yet built: the model runner, the assembly simulation, the printer simulator, the report, `results/`.

## Prior art

| Work | License | How it's used |
|---|---|---|
| BenchCAD (`BenchCAD/BenchCAD-main`, HF `BenchCAD/BenchCAD`) | MIT code, CC-BY data (per README; read LICENSE before reuse) | CadQuery sandbox, standard fastener families |
| BenchCAD 2.0 library (`BenchCAD-org/benchcad-2`) | MIT | part-family format (`part.py` build + `spec.py` check) |
| BenchCAD 2.0 harness (`BenchCAD-org/benchcad-2-main`) | no license | ideas only, cited |
| CADEngBench (arXiv 2608.09296, `coderjs-lab/cadengbench`) | no license | layered grading structure, cited, reimplemented |
| Hephaestus-CCX (arXiv 2605.17448) | — | typed requirements, strict pass and mean requirement pass, cited |
| Epoch Furniture Assembly, IKEA-Manual, FDM-Bench, VLM DfM rules (2311.12668), FEABench, EngDesign, SKY-001, NVIDIA ASPIRE, τ-Bench, Anthropic "Demystifying evals for AI agents" | various | cited; prior art reviewed, nothing copied |

## Private material

`docs/context/` holds Dan's own notes, dictation and clippings. It stays out of any public copy.
