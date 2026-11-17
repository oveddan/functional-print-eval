## 2026-11-17: The failure classes use the README's plain names everywhere (no result changed)

The README (#49) named each failure class by what goes wrong. `seeds/classes.yaml` and the docs still used the old names, so a reader saw two names for one class. Now they match:

| Class | Old name | New name |
|---|---|---|
| C1 | Designing from unmeasured dimensions | Printed the wrong size for the item it holds |
| C2 | Fit clearance wrong for the printer | Pocket the wrong size for a snug fit |
| C3 | Fastener stack-up arithmetic | Fasteners don't properly connect to each other |
| C4 | Tool and hand access | Can't reach it with the tool |
| C5 | Mating-part envelopes | A cable can't reach the port it plugs into |
| C6 | Printability in the chosen orientation | Can't print the way it's oriented |
| C7 | Works in the orientation it's used | Doesn't work the way it's mounted |
| C8 | Test-plan coverage | Tested the wrong thing |
| C9 | Manual correctness | Wrong assembly instructions |
| C10 | Print process and material settings | Wrong print settings |

- `seeds/classes.yaml`: the new `name:`s. The `id:` slugs (`C1-unmeasured` and so on) stay, because saved results, seeds and requirements refer to them. C2 and C3 keep the short name; the README's examples (a nut, a bearing, a servo horn, a cable; a bolt too short to reach its nut, a thread too long or too short, an insert's post too thin or no room for it) now open their descriptions. C5's description now leads with the plug: an opening sized to the bare port, when a plug's head has to fit through it for its metal to reach the port. It still says the other parts sized without what mates with them (header height, screw head, cable bend) are filed here, because the C5 seeds and requirements weren't reclassified. C8's description says "test print" instead of "coupon".
- `docs/reference.md`'s failure-class section, rebuilt with `report/atlas/build.py --readme`; `docs/plan.md`, `docs/coupon-loop.md`, `docs/decisions-api.md` and the section comments in `seeds/estoa-failures.yaml`.
- Left alone: the class columns in `tasks/tripod-plate/brief.md` and `tasks/estoa-light/brief.md` still use the old short names. Every file in a task's folder is part of the key the results site's drawings are cached under (`scripts/results_site_media.py`'s `content_key`), so editing a brief marks every design of that task stale and needs the site's renders redrawn. `changes/history.md` and saved results under `results/` keep the names they were written with.
- The failure-sorting judge (`pbe/judges/failures.py`) reads each class's name and description from `seeds/classes.yaml`, so its next run sees the new wording. Its saved results are unchanged.

Evidence: no grade, finding or requirement moved. `scripts/scorecard.py --check`, `report/atlas/build.py --check`, and `tests/test_results_site*.py`, `tests/test_judges.py`, `tests/test_site_files_current.py` pass. The results site shows class ids, never names, so it has nothing to rename.
