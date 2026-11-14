## 2026-11-13: Results site: a picture for each failure reason, the recorded print beside a failed check, and the 3D view kept between parts (no result changed)

Three changes to the results site, none to a grade or a count.

- **A picture for each reason.** "Why first prints don't pass" now shows a small picture beside each reason. Where one of Dan's prints shows that failure, it's his photo of it (9 reason groups, listed in `scripts/results_site_references.json` with the file each caption comes from: the README or `docs/media/photos.md`). Otherwise it's the check's own drawing of the first counted first-print design with that reason (25 more groups). 9 groups have neither, because there is nothing to draw: the code didn't run, no design was handed in, the trial was declined, or no counted first print has the reason.
- **The recorded print beside a failed check.** A trial's failed or not-graded check whose reason has a photo now shows it under "Why", captioned as one of Dan's test prints (or, for the insert posts, his own build) and as not the model's design, which wasn't printed. 468 checks across the saved trials carry one.
- **3D stays on.** Once a reader turns a part in 3D, the next part or trial opens in 3D too, until they go back to the picture.

Data schema 4: `index.json` gains `reason_pictures`; a finding gains `reference`. Seven 320 px thumbnails were added to the media host; the full photos were already there.

Evidence: `tests/test_results_site.py` (21 tests) checks that every photo is keyed by a reason the page shows and cites a record, that a drawing comes from a counted design with that reason, and that a check only gets the photo of its own reason. The page's own check (`window.resultsSiteCheck`) reports no problems.
