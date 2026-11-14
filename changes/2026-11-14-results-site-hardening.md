## 2026-11-14: Results site: a security and code review, and the fixes from it (no result changed)

A read-only security and correctness review of the site's scripts, generator and deploy workflow, done because the site publishes text written by models (transcripts, their code, part names, provider errors) and is about to be shared.

**What it found sound.** No path takes model-written or provider-written text into the page as HTML: `h()` makes every string a text node, and `innerHTML` is used only for the built-in icon paths. Every picture, mesh and transcript address in the built data points at the media host or this repository. URL parameters are checked against lookup tables before use. Across all 1,207 files of the built site and the three committed manifests there is no home-folder path, email address, API key, token, account id or internal address.

**What it found wrong, each confirmed in the code before fixing:**

- **A 3D view that finished loading after the reader switched tabs landed in the wrong view.** The reviewer reproduced it by slowing the mesh downloads to 4 s, clicking "Assembled", then a part: the part's picture gained the assembled view's canvas and its controls. The stage is reused by every view of a trial, so "is the stage still on the page" could not tell a late mount from the current one. Each mount now takes a turn number, and one that finishes after the view moved on is disposed. Re-run with the same 4 s delay: the part's view shows its picture and its own two controls, with no canvas; switching away from a part's 3D view mid-load leaves exactly one canvas, the new part's.
- **The WebGL context wasn't released when a mesh turned out empty.** No saved design reaches that path today; it is released there now.
- **A link could put up to any length of its own text on the page**, as text, in the "this link asked for something that isn't here" notice. The notice now repeats at most 40 characters of a value.
- **The build job had publishing rights.** `pages: write` and `id-token: write` were set for the whole workflow, so the job that installs dependencies and runs the repo's code held them on every pull request. They are on the deploy job only. A deploy on main is also no longer cancelled by a newer push partway through.
- **The 3D library was pinned by version but not by content.** The five three.js files the site loads from the CDN now each have a hash in the import map. The hashes match the same files fetched from a second CDN. In the browser the 3D view and the STL export load with no errors, and a copy of the page with two wrong hashes had both files refused.

**Not done.** No Content-Security-Policy: one is possible through a `<meta>` tag, but it would need a hash of the import map that changes whenever that block does, and it wasn't tested. The workflow's actions are pinned to major versions, not commit ids. The deploy job's narrower permissions follow GitHub's documented pattern but can't be exercised on a pull request, where deploy is skipped; the first merge to main is their test, and if they were wrong the site would stay at its previous version.

Evidence: `tests/test_results_site.py` has four new tests (every three.js file the scripts import has a hash; the late-mount guard; only the deploy job can publish; the 40-character limit). The page's own count check reports 0 problems.
