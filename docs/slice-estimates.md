# Slicer estimates: print time and filament per design

The README asks which model gets to a working print fastest, cheapest and with the least material. Grading says whether a design would print and fit; it says nothing about how long the print takes or how much filament it uses. `scripts/slice_estimates.py` adds that, from Bambu Studio's slicer run offline on the saved designs.

**These are slicer estimates, not measured prints.** Nothing was printed, weighed or timed, and nothing was sent to a printer. They change no verdict, no `grades.json` and no `summary.csv`.

## What was looked at first (2026-11-06)

| Option | Licence | Headless? | Used? |
|---|---|---|---|
| Bambu Studio's command line (`BambuStudio --slice`), installed here as 02.08.02.61 | AGPL-3.0 | Yes: loads presets as JSON, slices, writes G-code and a `result.json`, no window | **Yes**, called as a program; no code copied |
| OrcaSlicer's command line (a Bambu Studio fork, same flags) | AGPL-3.0 | Yes | No: not installed, and Bambu Studio is what Dan's test prints were sliced in |
| Community MCP servers: `bambu-printer-mcp` (several forks), `mcp-3D-printer-server`, `orca-mcp` | Third-party, unofficial | They call the same slicer command lines and parse the G-code header | No: they add printer control (LAN print, pause, stop), which this eval must never touch, and nothing over calling the slicer directly |
| A Bambu Lab MCP server of Bambu's own | — | None found | — |

No MCP server for a printer or slicer is configured on this Mac.

## Method

1. **The design's meshes.** For each saved trial with a design, the parts are built from `submission.yaml` in the eval's sandbox, the same way the results page builds them, into the trial's `parts/` (not committed). A part that doesn't build is recorded as `not_built` with its error, the same failure the `builds` check records.
2. **On the bed, as designed.** The eval's format says z = 0 is the bed face, so each part is only moved down until its lowest point is at z = 0. It's never turned (`--orient 0`); the slicer centres it on the plate (`--arrange 1`).
3. **One fixed setup**, the one Dan's test prints used (`catalog/printer.yaml`): machine **Bambu Lab X1 Carbon 0.4 nozzle**, process **0.20mm Standard @BBL X1C** (0.2 mm layers, 2 walls, 15% infill, supports off) and filament **Generic PLA High Speed @BBL X1C** (1.24 g/cm³, 1.75 mm), Bambu's stock system presets with one change, step 5.
4. **Presets written out in full.** The command line doesn't follow a preset's `inherits` chain: loaded as it is, the PLA preset slices with a density of 0, so every part weighs 0 g. The script resolves each preset's parents and its `include` templates (where the X1C's start and end G-code live) into one JSON file. Checked against a project Dan saved from the Bambu Studio app on 2026-10-14 with the same machine and process presets: every machine setting, start G-code included, is identical, and the process settings differ only in how numbers are written (`0.0` against `0%`).
5. **The printer's start and end sequences left out.** The X1C's start G-code homes, cleans the nozzle, runs its calibrations and draws a purge line; its end G-code parks and cools. That's the printer's routine, the same for every design and different on another printer, so the machine preset's `machine_start_gcode` and `machine_end_gcode` are emptied before slicing (Dan, 2026-11-06). Neither time nor filament counts them. Everything the slicer plans for the part itself, first layer included, is unchanged.
6. **Each part alone, and each trial's parts together.** Every part is sliced alone for its own row. Then a trial's final parts are sliced together on one plate and its test prints on another, as someone would print them, and the trial's totals come from those plates (codex review of #52 and #53, 2026-11-06). Adding up parts sliced alone overstates the time: the slicer slows a small part's layers to let them cool, and a plate of several parts gives each layer that time while the nozzle works on the others. On the five runs, a plate of several final parts took 1 to 10% less time than its parts alone (median 4.5%, 25 trials), with the same filament to within 0.05 g. A group of one part is its own slice. Bambu Studio slices each plate in a temporary folder with its own data folder, so Dan's app settings are neither read nor changed. The script reads the G-code header: printing time, filament length and weight, layer count. A slicer warning (floating regions, cantilevers) is kept.

## Output

Next to each run's `summary.csv`:

- `slice_estimates_parts.csv`, one row per part: `status` (`sliced`, `not_built` or `not_sliced`), `error`, `warning`, `print_s` (Bambu's "model printing time"), `filament_m`, `filament_g`, `layers`, `height_mm`.
- `slice_estimates.csv`, one row per trial with a design, joined to `summary.csv` by task, condition, model and trial: totals for the final parts' plate, the test prints' plate (role `coupon`) and both. If any part didn't build or slice, the trial's totals are blank and `parts_not_sliced` says how many: a sum missing a part would read as the whole design. `plates` counts the beds a trial needs. Parts that don't fit on one bed together are spread by the slicer over more plates, with no error, and every plate is counted; none spilled on these runs. If a plate didn't slice, the totals are blank too and `plate_error` says why; none failed. A trial with no test print has 0 for its test print totals. A trial with no design (no submission, an error, or a design with no parts) has no row.

## The first runs (2026-11-06)

Bambu Studio 02.08.02.61 on `pilot-tripod`, `pilot-tripod-given`, `pilot-nut-knob`, `pilot-nut-knob-2` and `pilot-wheel`: 119 trials with a design, 252 parts, 231 sliced. All 21 that weren't are parts whose code doesn't build, and each matches the saved verdict: the `builds` check's failure, `test_print_failed` for a test print, or the decline of GPT-6.1 Sol's plate, whose code stops on purpose. No part that built failed to slice. 14 sliced parts carry a warning about floating regions or cantilevers.

Final parts are a median 12 minutes and 8 g for a tripod plate, 5 minutes and 1.5 g for an M3 knob, 8 minutes and 3.7 g for an M5 knob, and 15 minutes and 11 g for a bearing wheel's parts. In trials that also hand in a test print, it adds a median 4 to 7 minutes per task: about the knob's own time for an M3 knob, a third of it for the wheel. Among passing designs the test print can outweigh the design. GPT-6.1 Sol's passing M3 knob prints in 4.0 minutes, but its test strip takes 18 more; Opus 5.5's passing M3 knob and test print together take 8.4. Numbers are in each run's `slice_estimates.csv`; how the report uses them is a separate decision.

## Run it

```bash
uv run python scripts/slice_estimates.py pilot-tripod
```

About 6 seconds per trial on an M-series Mac, most of it building the parts. Needs Bambu Studio; `BAMBU_STUDIO` points at another install (the `.app`, or the program itself), and `BAMBU_STUDIO_PROFILES` at its `profiles/BBL` folder if that isn't found beside it. `tests/test_slice_estimates.py` covers reading the header, resolving presets, leaving out the start and end G-code, finding the presets and the per-trial totals, and, where Bambu Studio is installed, slices a 20 mm cube and checks that two parts on one plate take less time than each alone.

## Limits

- **An estimate of one slicer's plan, not a print.** No print in the records was timed or weighed against these numbers, so their error on this printer is unknown. Bambu's estimator models acceleration but not every wait.
- **No start-up time or purge.** A real X1C print also spends about 7 minutes (the slicer's own timing of the stock start G-code, before heating) and 0.32 to 0.33 g of purge per plate. Leaving the sequences out is a choice, so that a design's numbers don't carry the printer's routine; the cost of a separate test print plate is not counted. Against slicing with them (the first version of this script), each part's `print_s` changed by a median −11 s (from −19 s to +15 s; every increase was on a part over 12 minutes, by at most 1%), and its `filament_g` fell by 0.32 to 0.33 g. Layer counts didn't change.
- **One way of grouping parts.** A trial's totals assume its final parts go on one plate and its test prints on another. Printing every part on one plate, or each alone, gives other times; filament stays the same.
- **As oriented by the model, supports off.** A part that needs supports in that orientation is sliced without them, and the slicer's warning is kept in `warning`. Whether those overhangs print is the `bridges` check's call, not this script's; the estimate is the material and time for the design as handed in.
- **Stock settings.** A person could pick more walls, other infill or a draft profile. Comparisons between models hold for this one setup.
- **Repeats agree to within a few seconds.** Slicing the five runs again gave identical filament for every part, and the same time for 213 of 231 parts; the rest differ by 1 to 3 s.
- **Not every saved run.** Run on `pilot-tripod`, `pilot-tripod-given`, `pilot-nut-knob`, `pilot-nut-knob-2` and `pilot-wheel`. The spacer, `can_run_code` and smoke runs can be added by naming them.
- **Needs a desktop app.** Bambu Studio's command line ships inside its macOS, Windows and Linux (AppImage) apps; the eval's Docker image doesn't include it, so this step isn't part of `scripts/reproduce.sh`.
