## 2026-11-14: Results site: a model's own part id is no longer rewritten when "coupon" becomes "test print" (no result changed)

The site shows "test print" where saved text says "coupon". The two helpers that do it (`reader_words` in the generator, `reader` in the page's `util.js`) replaced the letters wherever they appeared, including inside a model's own part id. On the built site that left about 170 strings wrong:

- 131 where an id was mangled, for example `nut_fit_coupon` shown as "nut_fit_test print" in "asks for test prints: …" lines and `unloaded_plate_coupon` as "unloaded_plate_test print" in a declined trial's summary. These have been on the live site since the first site PR.
- 38 more in the assembled 3D views' captions and the note under a passing design's STL button, which are in a later PR: where a model named a part just `coupon`, the grader's "test coupon coupon would find a size that holds" came out as "test print test print" or "test test print test print". That is where the fault was noticed.

Now only the word standing alone changes. An id that contains it is left as written, and where a model's part is named exactly "coupon" the grader's phrase reads: test print “coupon” would find a size that holds. The line "asks for test prints: …", which the site writes itself, no longer passes the ids through the helper at all.

Found while checking the top of the stack in the browser: one caption read "test test print test print would find a size".

Evidence: a scan of every string in the built site (1,196 trial files and the index) for the three garbled forms finds 0, down from about 170. `tests/test_results_site.py` has a new test with nine cases for the generator's helper and a scan of every trial summary; the page's helper was run on the same cases with Node (7 of 7). One test from the 3D-views fixes asserted the old behaviour (no "coupon" anywhere in the note, which only held because ids were being mangled); it now asserts the word is gone outside quoted ids.

Codex's review found one fault, fixed before merging: the drawing script's own helper (`results_site_views.reader_words_keeping`) protects part ids with `\x00N\x00` tokens before calling `reader_words`, whose restore step took them for its own and raised `IndexError` on "test coupon coupon has 4 pocket(s)", which could stop a drawing run. The two now use different markers; the reported case returns "test print coupon has 4 pocket(s)", and a test covers a foreign token.
