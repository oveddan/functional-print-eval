#!/bin/bash
# Every computed table and chart in README.md and docs/reference.md, from the saved runs. No model calls.
#
#   scripts/update_tables.sh           # rewrite them after new trials
#   scripts/update_tables.sh --slice   # slice the new designs first (needs Bambu Studio), then rewrite
#   scripts/update_tables.sh --check   # exit 1 if any of them doesn't match the saved runs (reproduce.sh, CI)
#
# What each writes:
#   scripts/scorecard.py      README.md's scorecard and docs/media/scorecard.svg
#   scripts/results_table.py  docs/reference.md's full results and assumptions
#   report/atlas/build.py     docs/reference.md's failure classes (from seeds/)
#   scripts/failure_tables.py docs/reference.md's "what went wrong" and "not graded" counts
set -euo pipefail
cd "$(dirname "$0")/.."
PILOTS="pilot-tripod pilot-tripod-given pilot-nut-knob pilot-nut-knob-2 pilot-wheel pilot-spacer pilot-code pilot-estoa loop-estoa loop-all test-first"

case "${1:-}" in
  --check)
    uv run python scripts/scorecard.py --check
    uv run python scripts/results_table.py --check
    uv run python report/atlas/build.py --check
    uv run python scripts/failure_tables.py --check
    ;;
  --slice|"")
    if [ "${1:-}" = "--slice" ]; then uv run python scripts/slice_estimates.py $PILOTS; fi
    uv run python scripts/scorecard.py --write
    uv run python scripts/results_table.py --write
    uv run python report/atlas/build.py --readme
    uv run python scripts/failure_tables.py --write
    ;;
  *) echo "usage: scripts/update_tables.sh [--slice | --check]" >&2; exit 2 ;;
esac
