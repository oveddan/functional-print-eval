## 2026-11-17: Estoa with the parts measured: a three-trial probe on Gemini 4 Argon, 0 of 3 pass

Dan asked to try Estoa again now that the person can give the measurements he took on 2026-11-17 (`changes/2026-11-17-estoa-measured.md`): the LED disc's diameter (242 mm) and thickness (1.56 mm), the perfboard's thickness (1.60 mm), the ESP32's height (about 18 mm from the perfboard's bottom), and the charger plug's head (11.58 × 6.44 mm, measured 2026-11-12). Before, every one of the 65 saved Estoa trials asked for the disc's diameter and was told "I can't measure that".

**Run:** `results/runs/estoa-measured`, Gemini 4 Argon, Test prints first (`can_test`), trials 1–3, the same settings as the `test-first` Estoa trials (12 turns, 32,000 max tokens). The trials ran in parallel under a $6 cap, through `pbe.eval.run_one`. They were stamped with commit e71e8ff1, a work-in-progress commit later squashed into the measurements PR (#56). Its `pbe`, `tasks`, `catalog`, `results/predictions`, `pyproject.toml` and `uv.lock` are identical to that PR's commit. It runs on main's code, so it also hears main's newer Estoa test-print replies, not the 16e6737 replies the `test-first` trials heard.

**Spend:** $1.65 ($0.12, $0.67 and $0.85).

| Trial | Verdict | Why |
|---|---|---|
| t1 | fail | R5: printed plastic stands in the perfboard's space. The same with the old 1 mm slab, so it isn't from the new reading. R1 and R2 are not graded. |
| t2 | fail | `bridges`: a roof 30.2 mm up, 116 mm², where 20% of strands land at both ends |
| t3 | fail | `bridges`: a roof 30.0 mm up, 120 mm², where 56% of strands land at both ends. R1 is not graded. |

All three asked for the disc's diameter and thickness and got them; none asked about the plug. Two of the three fail on a roof over open air about 30 mm up, as Argon's saved Estoa designs did (0 of 5 in `test-first`, 0 of 5 first prints). Three trials can't show whether the measurements help, but they don't suggest the measurements unlock Argon's Estoa passes: its failures there are about printing, not sizes.

The probe is its own group on the results site ("Estoa light box, with the parts measured", `scripts/results_site.py`). It's left out of the README's counts and of the scorecard, and the reference's run-wide tables count it as they count every saved run.
