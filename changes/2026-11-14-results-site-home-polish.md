## 2026-11-14: Results site: home page and trial lists, fixes left over from two design reviews (no result changed)

Front-end only (`scripts/results_site/app.js`, `style.css`, `index.html`); no grader, catalog or saved result is touched. The scorecard chart was redrawn in its own change (bars as pass rate); its touch targets are finished here, below. Measured on a local build of this branch against the build of its base, in the in-app browser at 375 and 1280 px, light and dark.

**What looks clickable now is, and the reverse.**
- A reason under a model's name in the trial list is drawn as the filter button it is (border, filter icon, an inverted pressed state with a close icon). Clicking it used to move the clicked control 97 px (390 to 293 px from the top of the window, tripod plate, fails); the page is now scrolled by the change, so it stays put (390 to 390 in two tries) and keeps the keyboard focus.
- In the one-line view each mark is one trial and opens it (466 marks for 466 first prints); the model's name is its own link to that model's row of pictures. Before, the whole line was a single link.
- "The person couldn't tell in N of M" in the table is plain muted text: no filter can express it, so it is no longer coloured like a link.
- Model names in the scorecard table and in "By model and part" link to that model's trials, as the chart's do (22 new links).

**One "didn't pass".** The table's mini bars, the by-part bars and the bar beside a model's row draw it hollow (the sunk fill with an outline), as the chart does, instead of a faint red. The dataviz skill's palette validator, all pairs, worst pair under simulated red-green colour blindness (target 8 or more):

| | before | after, the fill | after, the outline |
|---|---|---|---|
| light, on `#ffffff` | 1.1 (faint red against the second-print green) | 14.9 | 10.1 |
| dark, on `#1b1f23` | 2.2 | 12.8 | 5.6 |

Normal vision, worst pair: light 13.0 before, 19.2 after (fill); dark 10.8 before, 20.7 after (fill). The dark outline alone is 5.6 against the second-print green: it is a 1 px line around a hollow piece beside solid ones, so the shape carries it, but it is under the target and is named here. The validator still fails the lightness band and the chroma floor in both themes: "didn't pass" is a neutral on purpose and the two greens are the site's existing verdict colours, which this change doesn't move. In forced-colours mode the four pieces are solid, striped, hatched and hollow in the system's colours (written, not seen: the browser pane can't emulate that mode).

**Phone length (375 px).** The scorecard table and "By model and part" are behind labelled disclosures, closed on phones, always open above 760 px, opened by a link to `#scorecard-table` or `#by-task`.

| | before | after |
|---|---|---|
| page height | 21,182 px | 15,299 px |
| where the trials start | 14,882 px | 6,502 px |
| scorecard section | 7,754 px | 3,394 px |
| by model and part | 4,157 px | 138 px |

"Browse the trials" lands with the top of the trials 20 px from the top of the window. The page is still long because each one-line row is now about 133 px on a phone (44 px marks), where it was one link.

**Touch targets (375 px, coarse pointer).** Outside the chart, every control is 44 px tall or more: the marks are 30 by 44, the reason buttons, disclosure summaries, model-name links and "See where trial N fails" 44. Of 830 controls 69 are under 44: 66 in the chart (left to its own branch) and three links inside paragraphs. Before, 69 of 340.

**A chosen reason shows what it looks like.** With `?reason=` set, that reason's picture and caption sit above its designs, labelled as in "Why first prints don't pass" (one of Dan's test prints, from Dan's own build, or the check's drawing of one design, not printed), with a button back to every reason.

**Copy.** Reason labels in the reasons list and the one-line rows wrap instead of ending in "…" (0 clipped at 1280 px). A grader's id on the end of a reason ("… (bridges)", on 83 saved issues) is dropped from the home page's labels.

**Keyboard.** Tabbed through at 1280 px: every control takes focus, shows a ring and has a name (828 controls, none unnamed). Choosing a reason in the "Why" panel, "Show every reason", the pictures/one-line switch and "Clear the filters" used to drop the focus to the top of the page when the list re-drew; each now moves it to the control that took its place. Closing a trial opened from a mark returns the focus to that mark. At 200% zoom of 1280 px (640 px wide) nothing scrolls sideways.

**The page's own check.** `window.resultsSiteCheck`: 1,935 comparisons and 223 links (1,913 and 201 before), 0 problems; plus a check on the list now on the page, that each one-line row's link opens as many designs as it has marks (516 links, 0 problems). `tests/test_results_site.py` passes (30).

**Added when this was put on top of the chart redraw** (a clean rebase, then checked in the browser, because a clean rebase proves nothing about the page):

- **The chart's touch targets.** On a touch screen 66 of the chart's controls were under 44 px tall (bar pieces 34 px, names, totals, and the two counts under each bar). All are 44 px or taller now. Every count under a bar is a link to its designs and, on touch, a chip; that also covers the bar pieces too narrow to tap (one pass of 40 is 8 px wide), which keep their true width so the bar's length stays the pass rate. Five pieces are still under 24 px wide, each with its chip beside it.
- **What that cost.** The chart is 3,834 px tall on a 375 px touch screen, against 3,196 px before the targets, so about 640 px longer. To claw some back, the cost label that repeated on all 12 rows is said once above them; without that the chart was 4,053 px. The room reserved for the chart on a touch phone is 3,900 px, so nothing below it jumps when it draws.
- **Disclosure labels** read the same open or closed ("The table: 11 models, all three conditions", with + or − beside it); "Show the table" was wrong once it was showing.

Re-checked on top of the stack: the one-line view has 466 marks opening 466 different trials; clicking a reason under a model's name moves it 1 px (398 to 397) and keeps focus; a link to `#scorecard-table` or `#by-task` opens its disclosure on a phone; `?reason=holed-roof` shows the reason's photo and caption above its designs; the page's own check reports 0 problems of 1,973 comparisons and 242 links. This reason button is probably the list Dan reported he couldn't click under "Gemini 4 Argon": it jumped 97 px from under the cursor on a click.
