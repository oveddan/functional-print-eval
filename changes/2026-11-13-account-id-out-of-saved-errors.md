## 2026-11-13: The provider's account id is out of saved errors (no result changed)

OpenRouter's out-of-credit reply (HTTP 402) ends with the id of the account that made the call, and the runner saved a failed call's error text as it came. 45 committed `grades.json` files carried that id in their `error` field: 41 `test-first` trials and the 4 trials of `results/first-look/servo-arm-first-look`. It's an identifier, not a key, and it can't make a call or spend credit, but it has no place in a public repo.

- The id is replaced with "[account id removed]" in those 45 files. Only the `error` text changes: every verdict, finding and count is as it was, and the trials still read as stopped by an out-of-credit error. Git history is left as it is (Dan's call).
- `pbe/runner/llm.py` now strips an account id from a failed call's error before it's raised, so a new run can't save one.
- `tests/test_runner.py` checks both: an out-of-credit reply's error keeps "HTTP 402" and loses the id, and no `grades.json` under `results/runs` or `results/first-look` names an account.
