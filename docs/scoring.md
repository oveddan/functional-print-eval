# Scoring criteria and method

The quality bar for this eval: what makes it worth trusting, what gets reported, and how the
tasks and graders are built. Published eval guidance informs it — Anthropic's "Demystifying
evals for AI agents" most directly — but what follows is the standard this project holds itself
to, not a summary of anyone else's.

## What makes a strong eval

| Criterion | What it means here |
|---|---|
| Targets a real limitation that matters in practice, not a trick | Every task traces to a real failure (`seeds/tripod-failures.yaml`) or a real consumer request. No gotchas. |
| Clear tasks with a defensible correct answer or grading standard | Typed requirements per task; bolt reach, thread length and connectivity are arithmetic, not opinion. |
| Reliable grader, no false passes or false fails | Each task has a reference solution that must pass every gate, and known-bad designs (the tripod's own) that must fail. |
| Frontier models fail for a meaningful reason you can explain | Report failures by check type, with the reason (e.g. "assumed full thread", "never asked the desk size"). |
| Original and reproducible | Prior art and reuse are disclosed in the README; one command reproduces the main results. |

Five to ten well-made tasks beat many weak ones. Results go on frontier models, not only free
ones. Where two evals test the same thing, the clearer task design and the more rigorous grading
is the one worth keeping.

## What good looks like

| Dimension | Applied here |
|---|---|
| Problem and user value | A consumer at home asking for a printed fix. "I want to film myself at my desk" is a clear user with a clear bottleneck. |
| Solution and engineering | Structured output so graders are code; layered gates; the hidden-error printer. |
| End-to-end quality | From the consumer's brief to a printed, tested, assembled object. Real prints in the demo. |
| Measured improvement | A fair baseline, and `CHANGELOG.md` tying each change to task, grader or result evidence. |
| Reproducibility | A clean environment can run the eval and the baseline and reach the main result. |
| Insight | One observed failure mode turned into a practical lesson, e.g. "models don't plan for what they can't know before printing." |

Reproducibility means: commands, dependencies, data, versions, expected results, approximate
runtime and cost. Never include API keys.

## What gets reported

1. **Judgment over knowledge.** The interesting question is not whether a model knows a
   technique, but whether it knows what it can't know before printing. The judgment tasks are
   asking before assuming (the desk thickness) and test-printing the mechanisms but not
   everything. Framing: AI can draw a part, but does it know what it doesn't know?
2. **One headline number, honestly bounded.** Give a ceiling ("no model passed every
   requirement"), say where models are strong and weak, and report cost per task per model.
   Report all-pass rate, mean requirement pass, strongest and weakest check type.
3. **Long tasks where new facts arrive.** The hidden-error printer reports "the nut falls out"
   after the first test print, and the model has to adjust in the right direction by a sensible
   amount.
4. **Grader reliability is its own result.** Grading rules can reject valid answers, miss real
   mistakes or allow reward hacking. Deterministic graders plus reference solutions are the
   answer to that, and the README says so.
5. **Physical mistakes can't be undone.** A printed part is spent filament and hours. This eval
   catches the mistakes before anything is printed.

## Method

From Anthropic's "Demystifying evals for AI agents", plus what this eval adds:

- **Start from real failures.** 20–50 tasks is enough to begin; the tripod build supplies the first ones.
- **Write a reference solution per task.** If nothing passes, a 0% score likely means the task is broken, not the model.
- **Grade outcomes, not paths.** Check the design, the bill of materials, the manual and the test plan, not how the model got there. The exception is behavior worth scoring directly, like asking for a measurement.
- **Balance should-do and shouldn't-do cases.** Include some requests that can't be met as specified, where the right answer is to say so, and some where a test print isn't needed.
- **pass^k over pass@k.** For physical things you print once, the honest question is whether the model gets it right every time.
- **Read transcripts.** Check failures by hand before trusting a grader.
- **Simulate the user.** A second model plays the person building from the manual (stretch goal).
- **Calibrate against the expert.** The composite "good design" score should agree with Dan's hand ranking of a set of designs.
- **Keep judgment in the task and arithmetic in the grader.** The brief can be fuzzy; the grading shouldn't be.
