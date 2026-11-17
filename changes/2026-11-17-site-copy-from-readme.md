## 2026-11-17: Results site: its prose now copies the README's (no result changed)

The README was reworked to be shorter and story-first (`changes/2026-11-16-readme-rework.md`), and the results site still carried the older intro. The site now uses the README's own wording:

- **Opening** (`scripts/results_site/index.html`, "Why this eval"): the README's first paragraph with its links (functional purposes, a storage system, an enclosure, a replacement part), "Designing and printing these parts is slow…", and its four questions in place of the site's old three. The paragraphs on the tasks and on what a task gives the model were already the README's and stay.
- **How a trial runs**: the README's three conditions, word for word, under the intro.
- **Limits**: a new section after the scorecard, copied from the README's Limits, with its two links into `docs/reference.md` made absolute.
- **Credit**: "Made by Dan Oved", linking to https://danoved.xyz, under the title and in the footer.
- **"No final design was printed"**, the README's phrase, replaces "No complete model design was printed" in the hero, the photo label, the checks page's intro (`scripts/results_site_checks.yaml`), the index notes and the print-time definition (`scripts/results_site.py`), and two scorecard notes in `app.js`. Each says the closest check: round 3 printed six roofs cut from models' Estoa designs, and five of the six strung as the bridge check predicted.
- Dropped: the old paragraph that a functional print "is rarely one shape" (a robot arm, a light enclosure or a camera mount), which the README no longer has.
- US spelling in visible text: "millimeters" (the STL button's tooltip) and "labeled" (the checks page), plus three code comments.

The site's buttons, labels, data views and per-trial views are unchanged. Failure-class names are left as they are; the class rename lands separately.

No result changed: no grader, run, scorecard number or saved file under `results/` was touched. Evidence: `tests/test_results_site_copy.py` now pins each copied phrase to both the README and the page, the credit in both places, and US spelling across the site's files; it, `tests/test_results_site.py` and `tests/test_results_site_open_source.py` pass (73 tests), and `scripts/scorecard.py --check` passes. The site was built with `scripts/results_site.py`, served locally and checked at 1400 px and 375 px wide, with no horizontal scroll and no console errors.
