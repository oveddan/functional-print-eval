## 2026-11-16: US spelling in code and visible text: center, color, gray (no result changed)

Dan is American, and earlier agent sessions had drifted the repo British. `centre`, `centres`, `centred`, `centreline`, `colour`, `colours`, `coloured` and `grey` are now `center`, `color` and `gray` throughout `scripts/` (including `scripts/results_site/*.js` and `*.css`), `pbe/` and `tests/`, with compounds renamed to match (`DISK_HOLE_CENTERS`, `bolt_center`, `caption_color`, `pocket.center`, `found.center`). The definitions in `pbe/graders/` and every use in `scripts/` changed together; none is left.

A pure rename: no grade, count or table moved. The full test suite and `scripts/update_tables.sh --check` pass.

Left as it was, on purpose:

- Saved data (`results/`, `catalog/`, `seeds/`, transcripts, `scripts/results_site_media.json`, whose ids and URLs include `centre_spacer`). `catalog/hardware.yaml` keys such as `centre_to_tip` are untouched, and no code reads them under a renamed spelling.
- `tests/test_servo_arm.py` passes `centres=` because that is the parameter name in the saved reference submission; a comment says so.
- `pbe/parts/submission.py` keeps "centre" in one model-facing field description. It is part of the tool schema each model is sent, and `tests/test_prompt_rule.py` pins the prompt hashes, so changing it would change the prompt. Changing a prompt is a separate, result-affecting decision.
- Captions in `scripts/results_site_views.py` now use the US spelling in code, but the committed drawings were not redrawn (that needs an upload), so those images still show the old text until they are.
- `changes/history.md`, older change files and `CHANGELOG.md`.
