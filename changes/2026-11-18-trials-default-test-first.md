## 2026-11-18: Results site: the trials list opens on Test prints first (no result changed)

The headline is the Test prints first condition, but the trials list under it opened on first prints, so a reader who went from the chart to the trials saw a different set (Dan, 2026-11-18). The list now opens on Test prints first, and its condition buttons put Test prints first on the left.

Links that are about first prints now say so instead of relying on the old default: the hero's "See a failing design" (a first print of the tripod plate), each reason under "Why first prints don't pass", and a model's name in the scorecard table and by-part panels for the four models with no test-prints-first trials. A first-print link now carries `cond=first`. A bare trial link with no condition still opens over that trial's own list, so links already shared keep working.

No grade, finding or saved run changed. Checked in a fresh headless Chrome against a local build: the list opens on 295 Test prints first trials, the failing-design and reason links open first prints, and a bare first-print trial link opens over the first prints. Site tests: 63 passed.
