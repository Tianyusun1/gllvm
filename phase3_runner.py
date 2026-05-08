#!/usr/bin/env python3
"""Phase-3 experiment automation, aggregation, and reproducibility layer."""
import argparse
import csv
import json
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunCfg:
    input: str
    outdir: str
    seeds: list[int]
    budgets_ms: list[int]
    algos: list[str]


def load_cfg(path: Path) -> RunCfg:
    raw = json.loads(path.read_text())
    return RunCfg(
        input=raw.get("input", "dag_data.json"),
        outdir=raw.get("outdir", "out3"),
        seeds=raw.get("seeds", [1, 7, 42]),
        budgets_ms=raw.get("budgets_ms", [100, 300, 800]),
        algos=raw.get("algos", ["baseline", "ga", "aco"]),
    )


def run_phase2(cfg: RunCfg):
    outdir = Path(cfg.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    summary = outdir / "summary.csv"
    if summary.exists():
        summary.unlink()

    for seed in cfg.seeds:
        for budget in cfg.budgets_ms:
            mode = "compare" if set(cfg.algos) == {"baseline", "ga", "aco"} else None
            if mode:
                cmd = [
                    "python3", "phase2_scheduler.py",
                    "--input", cfg.input,
                    "--algo", "compare",
                    "--seed", str(seed),
                    "--budget-ms", str(budget),
                    "--out-prefix", str(outdir / f"cmp_s{seed}_b{budget}"),
                ]
                subprocess.run(cmd, check=True, capture_output=True)
            else:
                for algo in cfg.algos:
                    cmd = [
                        "python3", "phase2_scheduler.py",
                        "--input", cfg.input,
                        "--algo", algo,
                        "--seed", str(seed),
                        "--budget-ms", str(budget),
                        "--out-prefix", str(outdir / f"{algo}_s{seed}_b{budget}"),
                    ]
                    subprocess.run(cmd, check=True, capture_output=True)


def read_summary(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def aggregate(rows: list[dict]) -> list[dict]:
    groups = {}
    for r in rows:
        key = (r["algo"], int(r["budget_ms"]))
        groups.setdefault(key, []).append(r)

    out = []
    metrics = ["critical_path_est", "makespan_est", "reg_pressure_proxy", "resource_conflict_proxy", "compile_time_ms"]
    for (algo, budget), items in sorted(groups.items()):
        row = {"algo": algo, "budget_ms": budget, "n": len(items)}
        for m in metrics:
            vals = [float(x[m]) for x in items]
            row[f"{m}_mean"] = round(statistics.mean(vals), 4)
            row[f"{m}_stdev"] = round(statistics.pstdev(vals), 4)
        out.append(row)
    return out


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def write_report(path: Path, agg: list[dict]):
    lines = ["# Phase-3 Report", "", "## Aggregate by algo/budget", ""]
    for r in agg:
        lines.append(
            f"- {r['algo']} @ {r['budget_ms']}ms (n={r['n']}): "
            f"CP={r['critical_path_est_mean']}±{r['critical_path_est_stdev']}, "
            f"RegP={r['reg_pressure_proxy_mean']}±{r['reg_pressure_proxy_stdev']}, "
            f"Conflict={r['resource_conflict_proxy_mean']}±{r['resource_conflict_proxy_stdev']}, "
            f"Compile={r['compile_time_ms_mean']}±{r['compile_time_ms_stdev']} ms"
        )
    lines += ["", "## Best-by-budget (min compile time among same budget)", ""]
    by_budget = {}
    for r in agg:
        by_budget.setdefault(r["budget_ms"], []).append(r)
    for b, items in sorted(by_budget.items()):
        best = min(items, key=lambda x: x["compile_time_ms_mean"])
        lines.append(f"- budget {b}ms -> {best['algo']} (mean compile {best['compile_time_ms_mean']} ms)")
    path.write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="phase3_config.json")
    args = ap.parse_args()
    cfg = load_cfg(Path(args.config))
    run_phase2(cfg)
    outdir = Path(cfg.outdir)
    rows = read_summary(outdir / "summary.csv")
    agg = aggregate(rows)
    write_csv(outdir / "aggregate.csv", agg)
    write_report(outdir / "report.md", agg)
    print(json.dumps({"runs": len(rows), "aggregate_rows": len(agg), "outdir": cfg.outdir}, indent=2))


if __name__ == "__main__":
    main()