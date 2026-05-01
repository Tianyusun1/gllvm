# Phase-2 Pluggable Scheduler Framework

Phase-2 delivers a pluggable scheduling framework with a strategy interface and unified comparison flow.

## Implemented
- Strategy interface (`Strategy`) and 3 strategies: `baseline`, `ga`, `aco`
- Unified metrics + per-run JSON + summary CSV
- `compare` mode to run all strategies under same seed/budget
- Batch runner script for multi-seed/multi-budget experiments

## Run
```bash
python3 phase2_scheduler.py --input dag_data.json --algo compare --seed 7 --budget-ms 300 --out-prefix out2/demo
./run_phase2_experiments.sh dag_data.json out2
```
