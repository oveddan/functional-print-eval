## 2026-11-13: Results site: fixes from two design reviews (no result changed)

Two reviews of the site, one a design and accessibility critique and one adversarial (three first-time visitors: a phone reader with 20 seconds, an ML engineer, a hobbyist), both run in the browser at desktop and 375 px in light and dark. The changes to the intro and the reason pictures they asked for are in those two entries. This one holds the rest:

- **A link to a failure reason lands on its designs.** With a reason chosen, the list of every reason no longer opens by itself; the first design was about 1,300 px below the heading on desktop and 3,300 px on a phone, and is now 195 px below it on desktop.
- **"Why first prints don't pass" says which designs it counts.** It counts every model's first prints (466, from 11 models) while the numbers at the top count the 7 headline models (281). The line under the heading now says so, so 345 of 466 no longer reads as contradicting 105 of 281.
- **The design stays in view beside its checks** on a wide, tall window, where the left half of a trial was empty once the picture scrolled away.
- **The 3D view's help text** gives touch gestures on a touch screen in place of wheel and right-drag.
- **Reason labels** get more room before they are cut off.

Not done, and why: the third headline number (test prints first, where in 155 of 219 trials the person couldn't say how a test piece came out) is still at the top, which a reviewer called noise; whether to move it is Dan's call. The check drawings are still small until enlarged; jargon in the checks' "Found" lines comes from the graders' own text; the animated first photo has no pause control. Screen readers, tabbing through the whole page and a real phone were not checked.

Evidence: looked at each fix in the browser; `tests/test_results_site.py` passes; the page's own check reports no problems.
