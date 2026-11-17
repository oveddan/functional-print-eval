## 2026-11-17: Test prints first: the 41 out-of-credit trials run again, every model at 5 Estoa trials, and Estoa counted as a fifth task in its headline

Three changes to the Test prints first condition (`results/runs/test-first`, `can_test`), all asked for by Dan on 2026-11-17: finish the trials the OpenRouter account's credit stopped ("let's finish the test print first runs"), bring every main model to 5 Estoa trials ("complete 5 Estoa trials for all the main models"), and count Estoa in the headline once they're in ("Yes, add it").

### The runs

- **41 reruns.** On 2026-11-08 the account ran out of credit (HTTP 402) partway through the ten-trial top-up, and 41 trials ended as infrastructure errors that every number left out: Gemini 4 Argon 12 (bearing wheel t9–t10, knob M3 t6–t10, knob M5 t6–t10), Gemini 3.8 Flash 15 (wheel, M3 and M5, t6–t10 each), DeepSeek V4.1 Flash 14 (wheel and M3 t6–t10, M5 t6–t8, tripod t10). Each was run again with the same trial number.
- **17 Estoa trials.** t4 and t5 for Gemini 4 Argon, GPT-6.1 Sol, Gemini 3.8 Flash, Opus 5.5, Sonnet 5.5 and DeepSeek V4.1 Flash, and t1–t5 for Haiku 5.5, which had none.
- **Same code as the trials they join.** The other t6–t10 trials ran at commit 16e6737 (marked dirty). Main's task briefs and test-print replies have changed since, so these runs used a checkout of 16e6737 rather than main. Before running, its code rebuilt the opening prompt of every saved finished trial from that run and replayed every tool call against the saved transcripts. All 151 four-task prompts and 900 replies matched, and so did all 18 Estoa prompts and 288 replies. So the uncommitted edits didn't touch anything the model saw. Settings were unchanged: 12 turns, 32,000 max tokens. The runner's own `run_one` ran the trials, 12 at a time, under one spending cap.
- **Graded with main's checks.** Run-time grades came from 16e6737's checks, and `pbe.eval --regrade` then graded the run again with today's. Only these 58 trials changed, mostly not graded to pass or fail as the round 3 records decide them. GPT-6.1 Sol's Estoa t5 went from fail to pass. No trial saved before today changed.
- **No infrastructure errors.** Every one of the 58 finished, and the run has no error trial left.
- **Spend:** $9.65 as recorded in the trials ($3.84 for the 41 reruns, $5.83 for the 17 Estoa trials). Add about $0.30 for three partly run attempts, stopped when the runs were moved from one process per model to a pool. Those attempts saved nothing, so they aren't in any record.
- **Slicer estimates** for the 62 new designs were added to `slice_estimates.csv` and `slice_estimates_parts.csv`. Every row already there is kept as committed. A full re-slice also refreshed their stale `verdict` column and moved some print times by a few seconds after the meshes were rebuilt, and both are left out of this change.

### What moved

The test-first rates on the four scored tasks, before and after the reruns, and then with Estoa as a fifth task:

| Model | Four tasks, before (credit errors left out) | Four tasks, after the reruns | Five tasks, Estoa included |
|---|---|---|---|
| Gemini 4 Argon | 1. 82% (23/28) | 1. 75% (30/40) | 1. 67% (30/45) |
| GPT-6.1 Sol | 2. 63% (25/40) | 3. 63% (25/40) | 2. 62% (28/45) |
| Gemini 3.8 Flash | 3. 56% (14/25) | 2. 65% (26/40) | 3. 58% (26/45) |
| Opus 5.5 | 4. 53% (21/40) | 4. 53% (21/40) | 5. 47% (21/45) |
| Sonnet 5.5 | 5. 50% (20/40) | 5. 50% (20/40) | 4. 47% (21/45) |
| DeepSeek V4.1 Flash | 6. 38% (10/26) | 6. 38% (15/40) | 6. 36% (16/45) |
| Haiku 5.5 | 7. 15% (3/20) | 7. 15% (3/20) | 7. 12% (3/25) |
| **Pooled** | **53% (116/219)** | **54% (140/260)** | **49% (145/295)** |

- **The reruns** fill in Argon, Gemini 3.8 Flash and DeepSeek to 40 trials each. Argon is still first, at 75%, down from 82%. Gemini 3.8 Flash rises to 65% and passes GPT-6.1 Sol for second. DeepSeek stays at 38%.
- **Adding Estoa** pulls every model down, since only 5 of its 35 test-first designs pass: Sol 3 of 5, Sonnet 1, DeepSeek 1, and none for Argon, Gemini 3.8 Flash, Opus or Haiku. Sol's 3 of 5 puts it back in second, ahead of Gemini 3.8 Flash. Sonnet and Opus tie at 47%, and Sonnet now comes first on the tie-break, lower cost per pass ($0.34 against $0.42). Before Estoa, Opus led Sonnet 53% to 50%.
- **Estoa itself:** 4 of 18 with test prints first before today, 5 of 35 now. Most of the new Estoa designs fail on a roof the bridge check finds unbridgeable, as the earlier ones did.
- **Cost and print hours per pass** now cover all five tasks. Estoa designs are large, and Haiku's five add 17 print hours with no pass, so Haiku goes from 2.0 to 7.6 print hours per working part. Argon goes from $0.19 to $0.42 per working part, its five Estoa trials costing $7.05.
- **How settled the order is** (the site's rank odds, now redrawn over the five tasks): Gemini 4 Argon ranks first in 65% of the redraws (98% before), GPT-6.1 Sol is in the top two in 72%, and Haiku 5.5 is last in 100%. PR #53 kept Estoa out of the redraws only because the chart then counted four tasks. Now the chart counts five, and so do the redraws.

### Code

- `scripts/scorecard.py`: a new `TEST_FIRST_TASKS` (the four scored tasks plus `estoa-light`) is what `Row.tested_trials()` counts, so the test-first ranking, the table's "All five tasks" column, the costs and print hours per pass, the pooled rate and the can't-tell line all cover Estoa. First print and Reprint after feedback stay on the four tasks, because Gemini 3.8 Flash and DeepSeek V4.1 Flash have no first-print Estoa trials. The README's improvement sentence says so, and that its change column compares four tasks with five. `estoa_line` says Estoa counts in Test prints first and stays out of the first-print columns.
- `scripts/results_site.py`: `rank_odds` redraws over `TEST_FIRST_TASKS`, and the scorecard data adds `test_first_tasks` and describes `test_first_order` as five tasks.
- `scripts/results_site/app.js`: the "scored parts" filter means the parts a condition's headline counts: five in Test prints first, four elsewhere. A headline row's link therefore opens all 45 trials it counts, and the page's own count checks agree. The headline note, the rank-odds sentence, the table caption, the filter chip and the scorecard subtitle take the number of parts from the data instead of saying "four".
- `scripts/results_table.py`: two new Estoa designs fail on `bridges` alone, on a roof with no hole in it: a thin strip across the box's wall about 30 mm up (Sonnet 5.5 t4, 24 by 4 mm, and Gemini 4 Argon t4, 46 by 5 mm, measured with `pbe.graders.bridges.overhangs`). They're added to `NOT_HOLED_ROOFS`. They still fail, but don't count among the trials resting on the holed-roof assumption in the reference's assumptions table, which now reads 115 (110 before: 5 of the new trials fail on a holed roof alone).
- `tests/test_results_site.py`: two tests pinned today's 12 excluded Argon trials and assumed some error trial existed. They now expect none.
- `assumed.json` beside each new test-first Estoa trial (`python -m pbe.assumptions --run test-first`): the reference's Estoa assumptions table now covers 49 graded designs, up from 17. Under the stated assumption (each hole at the middle of its range), 17 of the 21 R1 verdicts left not graded are decided, and all 17 pass. The site's drawings for the designs whose assumption record changed were drawn again.
- `README.md`, `docs/reference.md`: regenerated by `scripts/update_tables.sh`. The Limits line on Estoa and the reference's Estoa rows (35 test-first trials, 5 of 35, $26.08) were edited by hand.
- Site media and drawings for the 57 new designs that built are drawn and uploaded (`scripts/results_site_media.json`, `scripts/results_site_views.json`). `scripts/results_site_media.py --rounds` fails on every trial on main: `ensure_built` reads a `submission.yaml` that the test-print round folders don't have. So the new trials' timelines don't show renders of the test prints they asked for, and the rounds manifest is unchanged.

Checks: `scripts/update_tables.sh --check` passes, including the site media and views. `tests/test_results_site*.py`: 82 passed, 3 skipped. A local build of the site loads with no console errors, and a headline row opens all 45 of its trials.
