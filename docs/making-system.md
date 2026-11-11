# Making system

How this eval fits with Dan's own builds and write-ups, and the order to build it in. Dan agreed the design on 2026-11-11. This is the public part of it, with what exists marked; where his private projects, journal and media live is in his own notes, not here. The first two pieces, the live mode and the pre-print check, are built here.

## The design

### What lives where

This repo is the public part: the designer agent (`pbe/runner/agent.py`), the checks (`pbe/graders/`, `pbe/preprint.py`), the printing ground truths (`catalog/printer.yaml`, `catalog/hardware.yaml`, `catalog/connectors.yaml`, `results/predictions/`) and the failure cases (`seeds/*.yaml`). Dan's own projects, his build journal and his media are private and live outside it. Write-ups go in a separate public documentation repo, still to create. Nothing public reads from anything private.

- **The ground truths stay here, as files.** The printer's limits, the hardware and the fits from the test prints hold nothing private and are the part most useful to others, so there is one copy and every project reads it. No memory service.
- **Claude Code stays the modeling tool.** The agent is an option per part, starting with small functional parts: a bracket, a clamp, a mount. A large enclosure stays in Dan's normal process.
- **The modeling tool can differ.** The agent writes CadQuery; Dan's projects use OpenSCAD. The pre-print check reads an exported STL or STEP, so a part from either can be checked.

### One part, start to finish

1. **Ask.** What the part must do, in the person's words. The mechanism is left to the designer.
2. **Design.** Either Dan models it in Claude Code as now, or he hands the part to the eval's agent in a live session: `python -m pbe.live`. The agent's prompt, tools and hand-in format are the eval's; only who answers changes (the table below).
3. **Check.** The pre-print check runs on the design before any plastic: `python -m pbe.preprint`. A failed check sends the design back.
4. **Test print.** Only for what the records don't already decide. In a real build this is Dan's call, as part of his own build. The eval never asks for one.
5. **Build.** Print, assemble.
6. **Note.** Five lines in the journal: what we're trying to find out; what we expect; what we did; what happened, with the measurement; what's next. The expectation is written before the result.

A failure in step 5 is how the agent gets better: it becomes a case in `seeds/`, the eval reruns on several models, and the agent's prompt or tools change.

### Who answers the agent

| Tool | In the eval | In a live session |
|---|---|---|
| `measure` | The task's table of recorded measurements (`runner/measure.py`). | Dan, at the terminal or from a file of answers. The agent may send a sketch with numbered dimensions, which he answers by number. |
| `print_test` | The recorded test prints only (`coupon_loop.printed_parts_report`). | Each test piece is saved as an STL. Dan prints it or doesn't, and says how it came out. |
| Pre-print check | Its own condition, scored apart from the baseline (not built yet). | Always on: printed at the end of every live session, and a command for any STL. |
| `submit_design` | Graded by code. | Saved with its parts as STL, the transcript and `session.yaml`. |

**The sketch on `measure`** is the one thing a live session's tools add. It came from a real mix-up: asked for "number 4" on a diagram, Dan measured a hole spacing when a thread test was meant. The agent sends an SVG with each dimension numbered and a line saying what each number asks for (`runner/sketch.py`). It opens in the browser, Dan answers by number, and the drawing is kept in `sketches/` beside the transcript, so a replay shows exactly what was asked. The drawing comes from a model, so it's checked first: lines, shapes, paths and text only, under 50,000 characters, every number labelled; anything else is refused and the model is told why. A mismatch between what the agent meant and what the person measured is itself a failure worth a case, close to C1. The eval's scripted conditions don't offer the sketch, so saved results stay comparable; it could be tested later as a condition of its own.

`session.yaml` keeps every question and Dan's answer. It is itself a valid `--answers` file, so a real session can be run again with nobody answering, on the same model or another.

### What the pre-print check predicts

It measures the designed shape and compares it with what printed on Dan's printer. It is not a print simulation.

| Question | Answered from | From a bare STL or STEP? |
|---|---|---|
| Will this roof sag or tangle? | Unsupported spans in each layer, against the roofs recorded as printing clean (up to 50 mm) and the ones that tangled or strung. | yes |
| Will the nut stay in? | The pocket's size, against test print B's pockets at that nut size. | yes, with `--nut` |
| Will the bearing press in? | The seat's size, against the 608 seats test-printed in rounds 2 and 3. | yes, with `--bearing 608` |
| One body, fits the bed? | Geometry and the build volume. | yes |
| Does the bolt reach, does it go together? | Hole, recess and length from the hardware catalog; the parts placed as the design says. | no: needs the agent's hand-in for one of the eval's tasks |

Each prediction names the print it rests on. Where no recorded print is near, it says "not graded", which is never a pass. Not predicted at all: warping, bed adhesion, stringing, strength, or a material with no recorded prints.

### How a real failure becomes a case

1. **When it happens**, the journal note already has the expectation and the measurement. Nothing is reconstructed later.
2. **Add a seed.** One entry in a `seeds/` file, in the fields the existing files use: `id`, `project`, `class` (one of `seeds/classes.yaml`), `date`, `status` (failed or near-miss), `who`, `did`, `right`, `found_by`, `evidence` (the journal note's date, or the live session's folder name). The five-line note maps straight onto `did`, `right` and `found_by`.
3. **If the agent designed it**, the live session's `session.yaml` and transcript are the case's raw material: the request is the brief, and Dan's answers become the task's `hidden_facts.yaml`.
4. **If a measurement came out of it** (a pocket that held, a span that sagged), it goes in `results/predictions/` or `catalog/printer.yaml` with its source, and the checks read it from there.
5. **Rerun** the affected tasks on several models, and log the change in `CHANGELOG.md`.

Private details (prices, vendors, addresses) never cross: a seed says what was designed and what happened, as the existing ones do.

Other sources of cases, in the order they're worth building: sweeps just under and just over a known limit; scoring the decision to test (testing a feature the prints already cover wastes a print, skipping an unknown one takes a risk); and fits where several models' designs disagree.

## Build plan

Small PRs, in order. **Eval** is work in this repo. **Dan** needs him: creating a GitHub repo, or a call that's his.

| # | Where | PR | Status |
|---|---|---|---|
| 1 | Eval | This document. | built |
| 2 | Eval | Live mode: `pbe/live.py`, `pbe/runner/live.py`. | built |
| 3 | Eval | Pre-print check as a command: `pbe/preprint.py`. | built |
| 4 | Eval | Live mode that pauses: a session stops at an unanswered question, saves its state and resumes with the answer, so Claude Code can relay questions instead of Dan typing in a terminal tab. | next |
| 5 | Eval | The pre-print check as an eval condition: a tool that returns these predictions for the model's own design, scored apart from the baseline. Needs a pilot run, so a budget from Dan. | |
| 6 | Eval | More of the check from a bare shape, each with hardware the person names: bolt holes and head recesses from the hardware catalog, insert holes and USB-C openings from Estoa's records. Also `--up` for a mesh that isn't z-up. | |
| 7 | Eval | A session becomes a draft case: from a live session's folder, write a draft seed entry and a draft task folder for Dan to review the wording. | |
| 8 | Eval | Sweeps across a known limit, and scoring the decision to test. | |
| 9 | Dan | Set up the private home for his own projects and build journal. Its layout is in his notes. | waiting for Dan |
| 10 | Dan | Create the public documentation repo (below). | waiting for Dan |

Open, and Dan's: whether looser history, such as journals across years, needs a memory service. The ground truths stay as files either way.

### The public documentation repo: proposed layout

```
documentation/
  README.md              what this is, an index of write-ups
  write-ups/
    2026-11-phone-stand.md
  media.md               where each photo and clip is hosted; none are committed
```

Setup steps, for Dan:

1. Choose its name and whether it's a plain repo of Markdown or a site.
2. Create it public:
   ```bash
   gh repo create <name> --public --clone
   ```
3. Before the first push, run the same list as this repo's `docs/plan.md`, "Before publishing": no photo committed, no path that exists on one machine, nothing from a private note.
4. A write-up is an edit of several journal notes. Moving one across is deliberate, with prices, vendors and addresses removed.

## What isn't verified

- No live session has been run against a real model. The tests drive it with a scripted model.
- No model has drawn a sketch, and none has been opened in a browser by a live session: the tests use a hand-written SVG and a stand-in for the browser. Whether models draw sketches that are clear enough to answer from is untested.
- The pre-print check has been run on shapes built for its tests, the Arca plate examples and the spacer's reference. It has not been run on an STL exported from OpenSCAD, or on any of Dan's project files.
- A mesh is read as it sits in its file. A part exported in another orientation, or in inches, is read wrongly and nothing warns of it yet (PR 6).
