#!/usr/bin/env python3
"""Phase-2 pluggable scheduler framework (offline simulation)."""
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


def load_dag(path: Path) -> dict[int, Node]:
    arr = json.loads(path.read_text())
    return {
        x["id"]: Node(
            x["id"],
            x["type"],
            int(x["latency"]),
            list(x.get("predecessors", [])),
            list(x.get("srcs", [])),
            x.get("dest"),
        )
        for x in arr
    }


def successors(nodes):
    s = defaultdict(list)
    for nid, n in nodes.items():
        for p in n.predecessors:
            s[p].append(nid)
    return s


def topo(nodes):
    indeg = {i: len(n.predecessors) for i, n in nodes.items()}
    q = deque(sorted([i for i, d in indeg.items() if d == 0]))
    out = []
    s = successors(nodes)
    while q:
        u = q.popleft()
        out.append(u)
        for v in s[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if len(out) != len(nodes):
        raise ValueError("non-DAG input")
    return out


def validate(nodes):
    ids = set(nodes)
    for n in nodes.values():
        for p in n.predecessors:
            if p not in ids:
                raise ValueError(f"missing predecessor {p}")
    topo(nodes)


def cp_scores(nodes):
    s = successors(nodes)
    order = topo(nodes)
    cp = {i: nodes[i].latency for i in nodes}
    for i in reversed(order):
        if s[i]:
            cp[i] = nodes[i].latency + max(cp[v] for v in s[i])
    return cp


def schedule_from_priorities(nodes, pri):
    s = successors(nodes)
    unsat = {i: len(n.predecessors) for i, n in nodes.items()}
    ready = {i for i, d in unsat.items() if d == 0}
    out = []
    while ready:
        u = max(ready, key=lambda x: (pri.get(x, 0), -x))
        ready.remove(u)
        out.append(u)
        for v in s[u]:
            unsat[v] -= 1
            if unsat[v] == 0:
                ready.add(v)
    if len(out) != len(nodes):
        raise ValueError("failed schedule")
    return out


def _simulate_makespan(nodes, order, issue_width=2, type_limit=None):
    if type_limit is None:
        type_limit = defaultdict(lambda: 1)
    finish = {}
    starts = {}
    cycle_issued = defaultdict(int)
    type_issued = defaultdict(lambda: defaultdict(int))

    for nid in order:
        n = nodes[nid]
        earliest = max((finish[p] for p in n.predecessors), default=0)
        t = earliest
        while True:
            if cycle_issued[t] < issue_width and type_issued[t][n.type] < type_limit[n.type]:
                starts[nid] = t
                finish[nid] = t + n.latency
                cycle_issued[t] += 1
                type_issued[t][n.type] += 1
                break
            t += 1
    return max(finish.values(), default=0), starts


def eval_metrics(nodes, order, issue_width=2):
    pos = {n: i for i, n in enumerate(order)}
    for nid, n in nodes.items():
        for p in n.predecessors:
            if pos[p] > pos[nid]:
                raise ValueError("dependency violated")

    critical_path = max(
        (sum(nodes[x].latency for x in [nid]) for nid in order),
        default=0,
    )
    makespan_est, _ = _simulate_makespan(nodes, order, issue_width=issue_width)

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
        "critical_path_est": float(critical_path),
        "makespan_est": float(makespan_est),
        "reg_pressure_proxy": float(peak),
        "resource_conflict_proxy": float(switches),
    }


class Strategy(ABC):
    name = "base"

    @abstractmethod
    def schedule(self, nodes, budget_ms, seed): ...


class BaselineStrategy(Strategy):
    name = "baseline"

    def schedule(self, nodes, budget_ms, seed):
        cp = cp_scores(nodes)
        order = schedule_from_priorities(nodes, cp)
        return order, {"iterations": 0.0}


class GAStrategy(Strategy):
    name = "ga"

    def __init__(self, pop=30, gens=200, mut=0.2, issue_width=2):
        self.pop, self.gens, self.mut, self.issue_width = pop, gens, mut, issue_width

    def schedule(self, nodes, budget_ms, seed):
        rng = random.Random(seed)
        start = time.time()
        base, _ = BaselineStrategy().schedule(nodes, budget_ms, seed)

        def rand_topo():
            s = successors(nodes)
            unsat = {i: len(n.predecessors) for i, n in nodes.items()}
            ready = [i for i, d in unsat.items() if d == 0]
            out = []
            while ready:
                k = rng.randrange(len(ready))
                u = ready.pop(k)
                out.append(u)
                for v in s[u]:
                    unsat[v] -= 1
                    if unsat[v] == 0:
                        ready.append(v)
            return out

        def score(ordr):
            m = eval_metrics(nodes, ordr, issue_width=self.issue_width)
            return m["makespan_est"] + 0.1 * m["reg_pressure_proxy"] + 0.03 * m["resource_conflict_proxy"]

        pop = [base] + [rand_topo() for _ in range(max(1, self.pop - 1))]
        gen = 0
        while gen < self.gens and (time.time() - start) * 1000 <= budget_ms:
            pop = sorted(pop, key=score)
            elite = pop[: max(2, self.pop // 5)]
            nxt = elite[:]
            while len(nxt) < self.pop:
                p1, p2 = rng.sample(elite, 2) if len(elite) > 1 else (elite[0], elite[0])
                r2 = {n: i for i, n in enumerate(p2)}
                pri = {n: -(0.7 * p1.index(n) + 0.3 * r2[n]) for n in nodes}
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

    def __init__(self, ants=20, epochs=80, evap=0.15, alpha=1.0, beta=2.0, issue_width=2):
        self.ants, self.epochs, self.evap, self.alpha, self.beta, self.issue_width = ants, epochs, evap, alpha, beta, issue_width

    def schedule(self, nodes, budget_ms, seed):
        rng = random.Random(seed)
        start = time.time()
        cp = cp_scores(nodes)
        s = successors(nodes)
        tau = {i: 1.0 for i in nodes}
        best = None
        best_score = 1e18
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
                    total = sum(weights)
                    pick = rng.random() * total
                    idx = 0
                    for i, w in enumerate(weights):
                        pick -= w
                        if pick <= 0:
                            idx = i
                            break
                    u = arr[idx]
                    ready.remove(u)
                    order.append(u)
                    for v in s[u]:
                        unsat[v] -= 1
                        if unsat[v] == 0:
                            ready.add(v)
                m = eval_metrics(nodes, order, issue_width=self.issue_width)
                sc = m["makespan_est"] + 0.1 * m["reg_pressure_proxy"] + 0.03 * m["resource_conflict_proxy"]
                candidates.append((sc, order))
                if sc < best_score:
                    best_score, best = sc, order
            for n in tau:
                tau[n] *= 1 - self.evap
            sc, ordr = min(candidates, key=lambda x: x[0])
            dep = 1.0 / max(sc, 1.0)
            for n in ordr:
                tau[n] += dep
            epoch += 1
        return best if best is not None else topo(nodes), {"iterations": float(epoch)}


STRATEGIES = {"baseline": BaselineStrategy, "ga": GAStrategy, "aco": ACOStrategy}


def write_csv(path, row):
    exists = path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            w.writeheader()
        w.writerow(row)


def run_one(nodes, strategy, budget, seed, issue_width):
    t = time.time()
    order, extra = strategy.schedule(nodes, budget, seed)
    m = eval_metrics(nodes, order, issue_width=issue_width)
    m["compile_time_ms"] = round((time.time() - t) * 1000, 3)
    m.update(extra)
    return order, m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="dag_data.json")
    ap.add_argument("--algo", choices=["baseline", "ga", "aco", "compare"], default="baseline")
    ap.add_argument("--budget-ms", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--issue-width", type=int, default=2)
    ap.add_argument("--out-prefix", default="out2/run")
    args = ap.parse_args()

    nodes = load_dag(Path(args.input))
    validate(nodes)
    out = Path(args.out_prefix)
    out.parent.mkdir(parents=True, exist_ok=True)
    algos = ["baseline", "ga", "aco"] if args.algo == "compare" else [args.algo]
    results = []
    for a in algos:
        strat = STRATEGIES[a](issue_width=args.issue_width) if a in {"ga", "aco"} else STRATEGIES[a]()
        order, m = run_one(nodes, strat, args.budget_ms, args.seed, issue_width=args.issue_width)
        payload = {"input": args.input, "algo": a, "seed": args.seed, "budget_ms": args.budget_ms, "issue_width": args.issue_width, "metrics": m, "order": order}
        (out.parent / f"{out.name}_{a}.json").write_text(json.dumps(payload, indent=2))
        row = {"algo": a, "seed": args.seed, "budget_ms": args.budget_ms, "issue_width": args.issue_width, **m}
        write_csv(out.parent / "summary.csv", row)
        results.append(payload)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()