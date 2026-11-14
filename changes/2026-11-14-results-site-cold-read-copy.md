## 2026-11-14: Results site: copy fixes from a cold read by two other models (no result changed)

GPT-6.1 Sol and Gemini 4 Argon read the live site cold. The Print Build Eval session checked what they raised and passed on six points; each was checked again here against the repository and the live site before changing anything.

- **"Nothing a model designed was printed" was too absolute.** Round 3 printed six roof sections cut from models' own Estoa designs (README, "The test prints behind the checks"). The page, the data's notes and the checks page now say no complete model design was printed, and the page links the round.
- **The pass definition** now says a pass holds under the assumptions listed in the reference, with a link to that section of `docs/reference.md`.
- **How the simulated person answers.** It was said to answer "only from Dan's recorded test prints". Where a roof wasn't printed its answer is the bridge check's prediction (`pbe/runner/coupon_loop.py`, basis "bridge check prediction"), which trial pages already label. The glossary and the trial page now say so.
- **"Why this eval"** carries the README's new opening (its first three paragraphs and the three questions, from PR #38), with the link to how it works.
- **Footer:** a link to the reference beside the README's, and a pointer to "Run it".
- **"Show the system prompt"** needed no fix. On the live address it loads (6,741 characters after opening it, no errors); "Loading…" is only what the closed section holds before it is opened.

Evidence: `tests/test_results_site_copy.py` checks the old absolute sentences are gone from the site's files, that both links point at anchors that exist in `docs/reference.md` and the README, and the footer's two pointers. Looked at in the browser.
