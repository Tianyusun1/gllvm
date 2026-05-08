#!/usr/bin/env bash
set -euo pipefail
INPUT=${1:-dag_data.json}
OUTDIR=${2:-out2}
rm -f "$OUTDIR/summary.csv" || true
mkdir -p "$OUTDIR"
for seed in 1 7 42; do
  for budget in 100 300 800; do
    python3 phase2_scheduler.py --input "$INPUT" --algo compare --seed "$seed" --budget-ms "$budget" --out-prefix "$OUTDIR/cmp_s${seed}_b${budget}"
  done
done
echo "Phase2 done: $OUTDIR/summary.csv"
