#!/usr/bin/env bash
set -euo pipefail

INPUT=${1:-dag_data.json}
OUTDIR=${2:-out}

rm -f "$OUTDIR/summary.csv"

python3 phase1_scheduler.py --input "$INPUT" --algo baseline --out-prefix "$OUTDIR/baseline"

for seed in 1 7 42; do
  for budget in 100 300 800; do
    python3 phase1_scheduler.py \
      --input "$INPUT" \
      --algo ga \
      --seed "$seed" \
      --budget-ms "$budget" \
      --pop-size 30 \
      --generations 200 \
      --out-prefix "$OUTDIR/ga_s${seed}_b${budget}"
  done
done

echo "done. summary: $OUTDIR/summary.csv"
