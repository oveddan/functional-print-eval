## 2026-11-15: One set of names for the three trial conditions (no result changed)

Readers confused the three conditions because the README, the scorecard and the results site each worded them differently. They are now First print, Reprint after feedback and Test prints first, defined once in the README under "How a trial runs" and used in the scorecard, the results site and the walkthrough example.

Evidence: copy only. Run ids, JSON keys and code identifiers (`can_ask`, `loop-all`, `can_test`, `after_feedback`, `test_first`) are unchanged, and `scripts/update_tables.sh --check` and the results-site tests pass with the same counts.
