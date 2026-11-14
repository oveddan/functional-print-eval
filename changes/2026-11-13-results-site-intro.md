## 2026-11-13: Results site: an introduction with photos, and a title, text and image for shared links (no result changed)

The site now opens with the eval's name and its question, "Can a language model design a part that prints and works?", then the three pass rates as before. Under them are four photos of test prints (a plate of small pieces, a roof that printed as loose loops, the roof strip, and a wall with USB-C openings), labelled as test prints the designs are graded against so nobody reads them as a model's design, and then "Why this eval": four short paragraphs in the README's own words.

A first draft put the paragraphs and photos above the numbers. Two design reviews of it said the same thing: on a phone the first pass rate was about 1,150 px down, below the first screen. The numbers now start 196 px down at 375 px wide. The photos first included the Estoa light and the story of how the project started; Dan asked for the story to be left out, so they are test prints only.

A link to the site now unfurls with a title, a description and a 1200 by 630 image made from three of the test-print photos (Open Graph and Twitter card tags, plus a canonical address). The title and description state the headline rates, filled in when the site is built from the same scorecard numbers the page shows (`share_text` in `scripts/results_site.py`), so they can't drift from the results. The image is on the media host, not in the repo.

The three headline rates are no longer the page's `h1`; the eval's name is, and the rates are a labelled group.

Evidence: `tests/test_results_site.py` checks the page has one `h1` and the share tags, and that the share text carries the scorecard's own first-print and after-feedback rates; looked at in the browser at desktop width and at 375 px, with no sideways scroll, and the page's own check reports no problems.
