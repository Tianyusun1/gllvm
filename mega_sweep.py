#!/usr/bin/env python3
"""Exhaustive stress sweep runner for Phase-2.

Runs large parameter combinations automatically and persists:
- raw summary.csv from all runs
- aggregate_by_setting.csv
- aggregate_by_algo.csv
- failures.csv
"""
import argparse
import csv
import itertools
import json
import statistics
import subprocess
from pathlib import Path


def parse_int_list(s: str) -> list[int]:
    return [int(x.strip()) for x in s.split(",") if x.strip()]


def parse_float_list(s: str) -> list[float]:
    return [float(x.strip()) for x in s.split(",") if x.strip()]


def run_cmd(cmd: list[str]) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True, p.stdout
    except subprocess.CalledProcessError as e:
        return False, (e.stderr or e.stdout or str(e))


def aggregate(rows: list[dict], by_keys: list[str]) -> list[dict]:
    metrics = ["critical_path_est", "makespan_est", "reg_pressure_proxy", "resource_conflict_proxy", "compile_time_ms"]
    groups = {}
    for r in rows:
        key = tuple(r[k] for k in by_keys)
        groups.setdefault(key, []).append(r)

    out = []
    for key, items in groups.items():
        row = {k: v for k, v in zip(by_keys, key)}
        row["n"] = len(items)
        for m in metrics:
            vals = [float(x[m]) for x in items]
            row[f"{m}_mean"] = round(statistics.mean(vals), 6)
            row[f"{m}_stdev"] = round(statistics.pstdev(vals), 6)
        out.append(row)
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="dag_data.json")
    ap.add_argument("--outdir", default="out_mega")
    ap.add_argument("--seeds", default="1,7,42,97")
    ap.add_argument("--budgets", default="50,100,200,300,500,800,1200")
    ap.add_argument("--issue-widths", default="1,2,4")
    ap.add_argument("--algos", default="baseline,ga,aco")
    ap.add_argument("--w-makespan", default="1.0")
    ap.add_argument("--w-reg-pressure", default="0.05,0.1,0.2")
    ap.add_argument("--w-conflict", default="0.01,0.03,0.05")
    ap.add_argument(
        "--type-limits-grid",
        default='{"LD":1,"ST":1,"DEFAULT":1};{"LD":1,"ST":1,"DEFAULT":2};{"LD":1,"ST":1,"DEFAULT":4}',
        help="semicolon-separated JSON objects",
    )
    args = ap.parse_args()

    seeds = parse_int_list(args.seeds)
    budgets = parse_int_list(args.budgets)
    issue_widths = parse_int_list(args.issue_widths)
    algos = [x.strip() for x in args.algos.split(",") if x.strip()]
    w_makespan = parse_float_list(args.w_makespan)
    w_reg = parse_float_list(args.w_reg_pressure)
    w_conf = parse_float_list(args.w_conflict)
    type_limits_grid = [x.strip() for x in args.type_limits_grid.split(";") if x.strip()]

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    summary_path = outdir / "summary.csv"
    if summary_path.exists():
        summary_path.unlink()

    failures = []
    total = 0
    for (seed, budget, iw, wm, wr, wc, tl, algo) in itertools.product(
        seeds, budgets, issue_widths, w_makespan, w_reg, w_conf, type_limits_grid, algos
    ):
        total += 1
        out_prefix = outdir / f"r_s{seed}_b{budget}_iw{iw}_{algo}"
        cmd = [
            "python3", "phase2_scheduler.py",
            "--input", args.input,
            "--algo", algo,
            "--seed", str(seed),
            "--budget-ms", str(budget),
            "--issue-width", str(iw),
            "--type-limits", tl,
            "--w-makespan", str(wm),
            "--w-reg-pressure", str(wr),
            "--w-conflict", str(wc),
            "--out-prefix", str(out_prefix),
        ]
        ok, msg = run_cmd(cmd)
        if not ok:
            failures.append({
                "seed": seed,
                "budget": budget,
                "issue_width": iw,
                "algo": algo,
                "w_makespan": wm,
                "w_reg_pressure": wr,
                "w_conflict": wc,
                "type_limits": tl,
                "error": msg[:1000],
            })

    rows = list(csv.DictReader(summary_path.open())) if summary_path.exists() else []
    by_setting = aggregate(rows, ["algo", "budget_ms", "issue_width", "type_limits"])
    by_algo = aggregate(rows, ["algo"])

    write_csv(outdir / "aggregate_by_setting.csv", by_setting)
    write_csv(outdir / "aggregate_by_algo.csv", by_algo)
    write_csv(outdir / "failures.csv", failures)

    meta = {
        "total_planned_runs": total,
        "successful_rows": len(rows),
        "failed_runs": len(failures),
        "outdir": str(outdir),
    }
    (outdir / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
