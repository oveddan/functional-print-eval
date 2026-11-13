## 2026-11-13: Main's tests green again after the R6 regrade (no result changed)

- PR #14 was merged before its CI finished, and two tests failed on main. `scripts/results_table.py` lists Gemini 4 Argon's Estoa t1 in `NOT_HOLED_ROOFS`: with R6 cleared it fails on `bridges` alone, on a 44 by 5.6 mm ledge with no hole. `tests/test_slice_estimates.py` expects the five loop-estoa feedback arms that pass after the regrade, not only Argon t2.
