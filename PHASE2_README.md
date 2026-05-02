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

## PowerShell (Windows)

```powershell
./run_phase2_experiments.ps1 -Input dag_data.json -OutDir out2/p2_batch
```

## Evaluation model
- `critical_path_est`: dependency-only longest-path latency estimate.
- `makespan_est`: cycle-level simulated makespan under resource constraints.

### Resource controls
- `--issue-width`: total issue slots per cycle.
- `--type-limits`: per-op-type issue limits (JSON), e.g. `{"LD":1,"ST":1,"DEFAULT":2}`.

### Objective weights (GA/ACO)
- `--w-makespan`
- `--w-reg-pressure`
- `--w-conflict`

Example:
```bash
python3 phase2_scheduler.py \
  --input dag_data.json \
  --algo compare \
  --budget-ms 300 \
  --issue-width 2 \
  --type-limits '{"LD":1,"ST":1,"DEFAULT":2}' \
  --w-makespan 1.0 \
  --w-reg-pressure 0.1 \
  --w-conflict 0.03 \
  --out-prefix out2/demo
```
