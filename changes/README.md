# Change files

The eval's changelog: one file per change that affects results, with the evidence behind it. Each PR adds its own file here, so parallel and stacked PRs never edit the same one.

- Name: `<YYYY-MM-DD>-<slug>.md`, the date the change was made, the slug a few lower-case words joined by dashes.
- First line: `## <YYYY-MM-DD>: <what changed>`, the same date. Say "(no result changed)" at the end of it when none did.
- Then the entry: what changed, why, and the evidence (run ids under `results/`, verdicts before and after, the test that covers it).
- To correct an entry before its PR merges, edit its file. Once merged, add a new entry rather than rewriting the old one, unless it's a typo.

The changelog lists entries newest day first; entries from the same day come in reverse order of file name, not of time.

`history.md` holds the entries written before change files, newest first. Leave it alone.

`CHANGELOG.md` is built from this folder and isn't committed:

```bash
uv run python scripts/changelog.py --write
```

CI fails a PR that changes `results/`, `pbe/graders/` or `catalog/` without adding a change file, or that adds a badly formed one (`scripts/changelog.py --check`).
