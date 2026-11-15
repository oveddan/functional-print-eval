## 2026-11-14: Results site: says it is open source, with a link to the repository (no result changed)

The site now says the eval is fully open source under the MIT licence, with a link to https://github.com/oveddan/functional-print-eval, in two places: one line under the page's question, above the headline numbers, and one in the footer, which also links the LICENSE file. Both are plain HTML, so they show before any data loads. Dan asked for it before sharing the site.

Evidence: `tests/test_results_site_open_source.py` checks both places carry the wording and the link, that the header's line comes before the numbers, and that the repository's LICENSE file is the MIT licence the page names. Looked at in the browser at desktop width and at 375 px.
