# Phase-1 Offline Scheduler

This implements the complete Phase-1 scope:
- DAG loader + validator
- Baseline list scheduling
- GA scheduling with budget/timeout control
- Unified metrics and CSV/JSON logs
- Reproducible batch script

## Run

```bash
python3 phase1_scheduler.py --input dag_data.json --algo baseline --out-prefix out/baseline
python3 phase1_scheduler.py --input dag_data.json --algo ga --seed 7 --budget-ms 300 --out-prefix out/ga
./run_phase1_experiments.sh dag_data.json out
```

## Metrics
- `schedule_length`
- `critical_path_est`
- `reg_pressure_proxy`
- `resource_conflict_proxy`
- `compile_time_ms`

GA-specific fields:
- `ga_score`
- `ga_generations_used`
