# Phase-3 Reproducibility & Analysis

Phase-3 adds experiment orchestration and aggregate analysis on top of Phase-2.

## Features
- Config-driven experiment matrix (`phase3_config.json`)
- Automatic execution over seed x budget x strategy
- Aggregate statistics (`mean`, `stdev`) into `aggregate.csv`
- Human-readable report generation (`report.md`)

## Run
```bash
python3 phase3_runner.py --config phase3_config.json
```

Outputs in `out3/` by default:
- `summary.csv` (raw runs from phase2)
- `aggregate.csv` (grouped stats)
- `report.md` (analysis summary)


## Plotting

```bash
python3 plot_results.py --aggregate out3/aggregate.csv --outdir out3/figures
```

If matplotlib is missing:

```bash
pip install matplotlib
```

## Mega sweep (full stress test)

Run exhaustive grid search and persist all results:

```bash
python3 mega_sweep.py --input dag_data.json --outdir out_mega
```

Outputs:
- `out_mega/summary.csv`
- `out_mega/aggregate_by_setting.csv`
- `out_mega/aggregate_by_algo.csv`
- `out_mega/failures.csv`
- `out_mega/meta.json`
