#!/usr/bin/env python3
"""Phase-2 pluggable scheduler framework (offline simulation).

Major goals:
- schedule-sensitive metrics (critical-path + simulated makespan)
- configurable resource model (issue width + per-type limits)
- configurable objective weights for GA/ACO
"""
import argparse
import csv
import json
import random
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Node:
    id: int
    type: str
    latency: int
    predecessors: list[int]
    srcs: list[str]
    dest: str | None


@dataclass
class EvalConfig:
    issue_width: int = 2
    type_limits: dict[str, int] | None = None
    w_makespan: float = 1.0
    w_reg_pressure: float = 0.1
    w_conflict: float = 0.03


def load_dag(path: Path) -> dict[int, Node]:
    arr = json.loads(path.read_text())
    return {
        x["id"]: Node(
            id=x["id"],
            type=x["type"],
            latency=int(x["latency"]),
            predecessors=list(x.get("predecessors", [])),
            srcs=list(x.get("srcs", [])),
            dest=x.get("dest"),
        )
        for x in arr
    }


def successors(nodes: dict[int, Node]) -> dict[int, list[int]]:
    s = defaultdict(list)
    for nid, n in nodes.items():
        for p in n.predecessors:
            s[p].append(nid)
    return s


def topo(nodes: dict[int, Node]) -> list[int]:
    indeg = {i: len(n.predecessors) for i, n in nodes.items()}
    q = deque(sorted([i for i, d in indeg.items() if d == 0]))
    out = []
    succ = successors(nodes)
    while q:
        u = q.popleft()
        out.append(u)
        for v in succ[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if len(out) != len(nodes):
        raise ValueError("non-DAG input")
    return out


def validate(nodes: dict[int, Node]) -> None:
    ids = set(nodes)
    for n in nodes.values():
        for p in n.predecessors:
            if p not in ids:
                raise ValueError(f"missing predecessor {p}")
    topo(nodes)


def cp_scores(nodes: dict[int, Node]) -> dict[int, int]:
    succ = successors(nodes)
    order = topo(nodes)
    cp = {i: nodes[i].latency for i in nodes}
    for i in reversed(order):
        if succ[i]:
            cp[i] = nodes[i].latency + max(cp[v] for v in succ[i])
    return cp


def schedule_from_priorities(nodes: dict[int, Node], pri: dict[int, float]) -> list[int]:
    succ = successors(nodes)
    unsat = {i: len(n.predecessors) for i, n in nodes.items()}
    ready = {i for i, d in unsat.items() if d == 0}
    out = []
    while ready:
        u = max(ready, key=lambda x: (pri.get(x, 0.0), -x))
        ready.remove(u)
        out.append(u)
        for v in succ[u]:
            unsat[v] -= 1
            if unsat[v] == 0:
                ready.add(v)
    if len(out) != len(nodes):
        raise ValueError("failed schedule")
    return out


def simulate_timing(nodes: dict[int, Node], order: list[int], cfg: EvalConfig) -> tuple[dict[int, int], dict[int, int]]:
    type_limits = cfg.type_limits or {}
    finish = {}
    start = {}
    issued_total = defaultdict(int)
    issued_by_type = defaultdict(lambda: defaultdict(int))

    for nid in order:
        n = nodes[nid]
        earliest = max((finish[p] for p in n.predecessors), default=0)
        t = earliest
        limit = type_limits.get(n.type, 1)
        while True:
            if issued_total[t] < cfg.issue_width and issued_by_type[t][n.type] < limit:
                start[nid] = t
                finish[nid] = t + n.latency
                issued_total[t] += 1
                issued_by_type[t][n.type] += 1
                break
            t += 1
    return start, finish


def eval_metrics(nodes: dict[int, Node], order: list[int], cfg: EvalConfig) -> dict[str, float]:
    pos = {n: i for i, n in enumerate(order)}
    for nid, n in nodes.items():
        for p in n.predecessors:
            if pos[p] > pos[nid]:
                raise ValueError("dependency violated")

    # true critical path from dependency timing (independent from issue width)
    dep_finish = {}
    for nid in order:
        dep_start = max((dep_finish[p] for p in nodes[nid].predecessors), default=0)
        dep_finish[nid] = dep_start + nodes[nid].latency
    critical_path_est = max(dep_finish.values(), default=0)

    _, finish = simulate_timing(nodes, order, cfg)
    makespan_est = max(finish.values(), default=0)

    uses = defaultdict(int)
    for n in nodes.values():
        for s in n.srcs:
            uses[s] += 1
    live = set()
    peak = 0
    for nid in order:
        n = nodes[nid]
        if n.dest is not None:
            live.add(n.dest)
        for s in n.srcs:
            if uses[s] > 0:
                uses[s] -= 1
                if uses[s] == 0 and s in live:
                    live.remove(s)
        peak = max(peak, len(live))

    switches = sum(1 for i in range(1, len(order)) if nodes[order[i]].type != nodes[order[i - 1]].type)

    return {
        "schedule_length": float(len(order)),
        "critical_path_est": float(critical_path_est),
        "makespan_est": float(makespan_est),
        "reg_pressure_proxy": float(peak),
        "resource_conflict_proxy": float(switches),
    }


def objective(metrics: dict[str, float], cfg: EvalConfig) -> float:
    return (
        cfg.w_makespan * metrics["makespan_est"]
        + cfg.w_reg_pressure * metrics["reg_pressure_proxy"]
        + cfg.w_conflict * metrics["resource_conflict_proxy"]
    )


class Strategy(ABC):
    name = "base"

    @abstractmethod
    def schedule(self, nodes: dict[int, Node], budget_ms: int, seed: int, cfg: EvalConfig): ...


class BaselineStrategy(Strategy):
    name = "baseline"

    def schedule(self, nodes, budget_ms, seed, cfg):
        cp = cp_scores(nodes)
        order = schedule_from_priorities(nodes, cp)
        return order, {"iterations": 0.0}


class GAStrategy(Strategy):
    name = "ga"

    def __init__(self, pop=30, gens=200, mut=0.2):
        self.pop, self.gens, self.mut = pop, gens, mut

    def schedule(self, nodes, budget_ms, seed, cfg):
        rng = random.Random(seed)
        start = time.time()
        base, _ = BaselineStrategy().schedule(nodes, budget_ms, seed, cfg)

        def rand_topo():
            succ = successors(nodes)
            unsat = {i: len(n.predecessors) for i, n in nodes.items()}
            ready = [i for i, d in unsat.items() if d == 0]
            out = []
            while ready:
                u = ready.pop(rng.randrange(len(ready)))
                out.append(u)
                for v in succ[u]:
                    unsat[v] -= 1
                    if unsat[v] == 0:
                        ready.append(v)
            return out

        def score(ordr):
            return objective(eval_metrics(nodes, ordr, cfg), cfg)

        pop = [base] + [rand_topo() for _ in range(max(1, self.pop - 1))]
        gen = 0
        while gen < self.gens and (time.time() - start) * 1000 <= budget_ms:
            pop = sorted(pop, key=score)
            elite = pop[: max(2, self.pop // 5)]
            nxt = elite[:]
            while len(nxt) < self.pop:
                p1, p2 = rng.sample(elite, 2) if len(elite) > 1 else (elite[0], elite[0])
                rank2 = {n: i for i, n in enumerate(p2)}
                pri = {n: -(0.7 * p1.index(n) + 0.3 * rank2[n]) for n in nodes}
                child = schedule_from_priorities(nodes, pri)
                if rng.random() < self.mut:
                    i, j = sorted(rng.sample(range(len(child)), 2))
                    child[i], child[j] = child[j], child[i]
                    child = schedule_from_priorities(nodes, {n: -child.index(n) for n in child})
                nxt.append(child)
            pop = nxt
            gen += 1
        best = min(pop, key=score)
        return best, {"iterations": float(gen)}


class ACOStrategy(Strategy):
    name = "aco"

    def __init__(self, ants=20, epochs=80, evap=0.15, alpha=1.0, beta=2.0):
        self.ants, self.epochs, self.evap, self.alpha, self.beta = ants, epochs, evap, alpha, beta

    def schedule(self, nodes, budget_ms, seed, cfg):
        rng = random.Random(seed)
        start = time.time()
        cp = cp_scores(nodes)
        succ = successors(nodes)
        tau = {i: 1.0 for i in nodes}
        best = None
        best_score = float("inf")
        epoch = 0

        while epoch < self.epochs and (time.time() - start) * 1000 <= budget_ms:
            candidates = []
            for _ in range(self.ants):
                unsat = {i: len(n.predecessors) for i, n in nodes.items()}
                ready = {i for i, d in unsat.items() if d == 0}
                order = []
                while ready:
                    arr = list(ready)
                    weights = []
                    for n in arr:
                        eta = max(cp[n], 1.0)
                        weights.append((tau[n] ** self.alpha) * (eta ** self.beta))
                    pick = rng.random() * sum(weights)
                    idx = 0
                    for i, w in enumerate(weights):
                        pick -= w
                        if pick <= 0:
                            idx = i
                            break
                    u = arr[idx]
                    ready.remove(u)
                    order.append(u)
                    for v in succ[u]:
                        unsat[v] -= 1
                        if unsat[v] == 0:
                            ready.add(v)

                m = eval_metrics(nodes, order, cfg)
                sc = objective(m, cfg)
                candidates.append((sc, order))
                if sc < best_score:
                    best_score, best = sc, order

            for n in tau:
                tau[n] *= 1 - self.evap
            sc, order = min(candidates, key=lambda x: x[0])
            dep = 1.0 / max(sc, 1.0)
            for n in order:
                tau[n] += dep
            epoch += 1

        return (best if best is not None else topo(nodes)), {"iterations": float(epoch)}


STRATEGIES = {"baseline": BaselineStrategy, "ga": GAStrategy, "aco": ACOStrategy}


def write_csv(path: Path, row: dict):
    exists = path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            w.writeheader()
        w.writerow(row)


def run_one(nodes, strategy, budget, seed, cfg):
    t0 = time.time()
    order, extra = strategy.schedule(nodes, budget, seed, cfg)
    m = eval_metrics(nodes, order, cfg)
    m["compile_time_ms"] = round((time.time() - t0) * 1000, 3)
    m.update(extra)
    return order, m


def parse_type_limits(s: str | None) -> dict[str, int] | None:
    if not s:
        return None
    return json.loads(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="dag_data.json")
    ap.add_argument("--algo", choices=["baseline", "ga", "aco", "compare"], default="baseline")
    ap.add_argument("--budget-ms", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--issue-width", type=int, default=2)
    ap.add_argument("--type-limits", default=None, help='JSON, e.g. {"LD":1,"ST":1,"DEFAULT":2}')
    ap.add_argument("--w-makespan", type=float, default=1.0)
    ap.add_argument("--w-reg-pressure", type=float, default=0.1)
    ap.add_argument("--w-conflict", type=float, default=0.03)
    ap.add_argument("--out-prefix", default="out2/run")
    args = ap.parse_args()

    cfg = EvalConfig(
        issue_width=args.issue_width,
        type_limits=parse_type_limits(args.type_limits),
        w_makespan=args.w_makespan,
        w_reg_pressure=args.w_reg_pressure,
        w_conflict=args.w_conflict,
    )

    nodes = load_dag(Path(args.input))
    validate(nodes)

    out = Path(args.out_prefix)
    out.parent.mkdir(parents=True, exist_ok=True)
    algos = ["baseline", "ga", "aco"] if args.algo == "compare" else [args.algo]

    results = []
    for a in algos:
        strategy = STRATEGIES[a]()
        order, m = run_one(nodes, strategy, args.budget_ms, args.seed, cfg)
        payload = {
            "input": args.input,
            "algo": a,
            "seed": args.seed,
            "budget_ms": args.budget_ms,
            "issue_width": args.issue_width,
            "type_limits": cfg.type_limits,
            "weights": {
                "w_makespan": cfg.w_makespan,
                "w_reg_pressure": cfg.w_reg_pressure,
                "w_conflict": cfg.w_conflict,
            },
            "metrics": m,
            "order": order,
        }
        (out.parent / f"{out.name}_{a}.json").write_text(json.dumps(payload, indent=2))
        row = {
            "algo": a,
            "seed": args.seed,
            "budget_ms": args.budget_ms,
            "issue_width": args.issue_width,
            "type_limits": json.dumps(cfg.type_limits) if cfg.type_limits else "",
            **m,
        }
        write_csv(out.parent / "summary.csv", row)
        results.append(payload)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
