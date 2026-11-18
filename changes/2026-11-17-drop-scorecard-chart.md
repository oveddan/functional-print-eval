## 2026-11-17: Results site: the scorecard's "First print, then reprint after feedback" chart is gone; the three-condition table stays (no result changed)

The front page showed two rankings that disagreed: the headline (test prints first, five tasks, Estoa included) and, just under it, the scorecard chart (first print plus one reprint after feedback, four tasks, 11 models). A reader skimming the page sees Argon at 69% in one and 80% in the other, under different orders. Dan found the three conditions side by side confusing, so the chart is removed. The first print and reprint numbers stay in the scorecard's three-condition table (folded on a phone), which every cell still links from.

How it was chosen: Jev, GPT-6 Luna Decisions and Gemini Decision 1 were asked which results blocks to keep for the launch. All three put dropping the chart first or tied for first (47%, 99% and 51% for "drop the chart, keep the table"; keeping everything got 0–6%). They split on dropping the table as well, so it stays folded.

The by-part panels labeled the Estoa row "not in the totals", which stopped being true when Estoa joined the test-prints-first headline (PR #55). It now says "in the test prints first total only".

The chart's code, styles, in-page self-check and the phone-height reservations held for it while the page loads go with it (Codex, PR #61: those reservations would have left a blank gap of several thousand pixels on a phone), and so do its two site tests and the chart's 44 px touch-target assertion. No grade, finding or saved run changed. Checked in a local build: the scorecard opens on the table, the page reports no mismatches, and at 375 px the folded scorecard is 81 px tall with no sideways scroll. Site tests: 63 passed.
