#!/usr/bin/env python3
"""Generate publication-ready plots from Phase-3 aggregate CSV.

Outputs PNG figures into a target directory:
- compile_time_vs_budget.png
- resource_conflict_vs_budget.png
- reg_pressure_vs_budget.png
- critical_path_vs_budget.png
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path


def load_rows(path: Path):
    with path.open() as f:
        return list(csv.DictReader(f))


def group_by_algo(rows):
    g = defaultdict(list)
    for r in rows:
        g[r["algo"]].append(r)
    for algo in g:
        g[algo] = sorted(g[algo], key=lambda x: int(x["budget_ms"]))
    return g


def plot_metric(grouped, metric_mean, metric_std, ylabel, outpath: Path):
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as e:
        raise SystemExit("matplotlib is required. Install with: pip install matplotlib") from e

    plt.figure(figsize=(7, 4.5))
    for algo, items in grouped.items():
        x = [int(r["budget_ms"]) for r in items]
        y = [float(r[metric_mean]) for r in items]
        e = [float(r[metric_std]) for r in items]
        plt.errorbar(x, y, yerr=e, marker="o", capsize=4, label=algo)
    plt.xlabel("Budget (ms)")
    plt.ylabel(ylabel)
    plt.title(f"{ylabel} vs Budget")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(outpath, dpi=180)
    plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aggregate", default="out3/aggregate.csv", help="Phase-3 aggregate CSV")
    ap.add_argument("--outdir", default="out3/figures", help="Output figure dir")
    args = ap.parse_args()

    rows = load_rows(Path(args.aggregate))
    grouped = group_by_algo(rows)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    plot_metric(grouped, "compile_time_ms_mean", "compile_time_ms_stdev", "Compile Time (ms)", outdir / "compile_time_vs_budget.png")
    plot_metric(grouped, "resource_conflict_proxy_mean", "resource_conflict_proxy_stdev", "Resource Conflict Proxy", outdir / "resource_conflict_vs_budget.png")
    plot_metric(grouped, "reg_pressure_proxy_mean", "reg_pressure_proxy_stdev", "Register Pressure Proxy", outdir / "reg_pressure_vs_budget.png")
    plot_metric(grouped, "critical_path_est_mean", "critical_path_est_stdev", "Critical Path Estimate", outdir / "critical_path_vs_budget.png")

    print(f"Generated figures in: {outdir}")


if __name__ == "__main__":
    main()
