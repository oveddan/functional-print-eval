#!/usr/bin/env bash
# Everything a reviewer can rerun from a clean clone, with no API key and no model calls:
# install, the tests, every task's reference against its checks, a regrade of every saved trial
# (on a copy, so results/ isn't touched), the results page, and the README's results table.
#
#     scripts/reproduce.sh
#
# Needs uv, git, and bubblewrap (Linux) or sandbox-exec (macOS) for building parts, plus OpenSCAD for
# the results page's pictures. Exits non-zero on the first step that fails. README.md lists each
# step's expected result and how long it took on a clean machine.
set -euo pipefail
cd "$(dirname "$0")/.."
unset OPENROUTER_API_KEY  # nothing here may call a model

TASKS="m5-spacer tripod-plate bearing-wheel nut-knob/M3 nut-knob/M5 nut-knob/M8"
FAMILIES="m5-spacer tripod-plate bearing-wheel nut-knob"

step() {
  echo
  echo "== $1 ($(date -u +%H:%M:%S) UTC)"
}

step "1. install"
uv sync

step "2. tests"
uv run pytest

step "3. every reference passes every check"
for task in $TASKS; do
  uv run python -m pbe.eval --reference --task "$task"
done

step "4. regrade every saved trial on a copy, and compare its verdicts with what's saved"
copy="$(mktemp -d)"
cp -r results/runs "$copy/runs"
for run in "$copy"/runs/*/; do
  args=()
  for family in $FAMILIES; do args+=(--task "$family"); done
  uv run python -m pbe.eval --regrade --runs-dir "$copy/runs" --run "$(basename "$run")" "${args[@]}"
done
changed=0
for summary in results/runs/*/summary.csv; do
  run="$(basename "$(dirname "$summary")")"
  if ! diff "$summary" "$copy/runs/$run/summary.csv"; then
    echo "regrade: $run's verdicts differ from what's saved (above)"
    changed=1
  fi
done
[ "$changed" = 0 ] || exit 1
echo "regrade: every saved verdict reproduces (each run's summary.csv is unchanged)"
echo "regrade: trials whose detail text changed, with the earlier text kept under regrades in grades.json:"
diff -rq -x parts -x workspace results/runs "$copy/runs" | grep -c grades.json || true

step "5. the results page"
uv run python scripts/results_page.py

step "6. the README and reference tables match the saved runs"
scripts/update_tables.sh --check

step "done"
