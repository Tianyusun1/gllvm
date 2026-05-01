#!/usr/bin/env python3
import argparse
import csv
import json
import random
import time
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
    raw = json.loads(path.read_text())
    nodes: dict[int, Node] = {}
    for item in raw:
        nodes[item["id"]] = Node(
            id=item["id"],
            type=item["type"],
            latency=int(item["latency"]),
            predecessors=list(item.get("predecessors", [])),
            srcs=list(item.get("srcs", [])),
            dest=item.get("dest"),
        )
    return nodes


def successors(nodes: dict[int, Node]) -> dict[int, list[int]]:
    succ = defaultdict(list)
    for nid, n in nodes.items():
        for p in n.predecessors:
            succ[p].append(nid)
    return succ


def topological_order(nodes: dict[int, Node]) -> list[int]:
    indeg = {nid: len(n.predecessors) for nid, n in nodes.items()}
    q = deque(sorted([nid for nid, d in indeg.items() if d == 0]))
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
        raise ValueError("Graph contains cycle or invalid predecessors")
    return out


def criticality(nodes: dict[int, Node]) -> dict[int, int]:
    order = topological_order(nodes)
    succ = successors(nodes)
    cp = {nid: nodes[nid].latency for nid in nodes}
    for nid in reversed(order):
        if succ[nid]:
            cp[nid] = nodes[nid].latency + max(cp[s] for s in succ[nid])
    return cp


def ready_list(nodes: dict[int, Node]) -> list[int]:
    return [nid for nid, n in nodes.items() if not n.predecessors]


def schedule_from_priority(nodes: dict[int, Node], priorities: dict[int, float]) -> list[int]:
    succ = successors(nodes)
    unsat = {nid: len(n.predecessors) for nid, n in nodes.items()}
    ready = set(ready_list(nodes))
    out = []
    while ready:
        chosen = max(ready, key=lambda n: (priorities.get(n, 0.0), -n))
        ready.remove(chosen)
        out.append(chosen)
        for v in succ[chosen]:
            unsat[v] -= 1
            if unsat[v] == 0:
                ready.add(v)
    if len(out) != len(nodes):
        raise ValueError("Could not produce full schedule")
    return out


def baseline_schedule(nodes: dict[int, Node]) -> list[int]:
    cp = criticality(nodes)
    return schedule_from_priority(nodes, {nid: cp[nid] for nid in nodes})


def evaluate_schedule(nodes: dict[int, Node], order: list[int]) -> dict[str, float]:
    pos = {nid: i for i, nid in enumerate(order)}
    for nid, n in nodes.items():
        for p in n.predecessors:
            if pos[p] > pos[nid]:
                raise ValueError(f"Invalid order: pred {p} after {nid}")

    finish = {}
    for nid in order:
        n = nodes[nid]
        start = max((finish[p] for p in n.predecessors), default=0)
        finish[nid] = start + n.latency
    critical_path = max(finish.values(), default=0)

    # simple pressure proxy by live virtual dests
    live = set()
    max_live = 0
    uses = defaultdict(int)
    for n in nodes.values():
        for s in n.srcs:
            uses[s] += 1
    for nid in order:
        n = nodes[nid]
        if n.dest is not None:
            live.add(n.dest)
        for s in n.srcs:
            if uses[s] > 0:
                uses[s] -= 1
                if uses[s] == 0 and s in live:
                    live.remove(s)
        max_live = max(max_live, len(live))

    type_switches = 0
    for i in range(1, len(order)):
        if nodes[order[i]].type != nodes[order[i - 1]].type:
            type_switches += 1

    return {
        "schedule_length": float(len(order)),
        "critical_path_est": float(critical_path),
        "reg_pressure_proxy": float(max_live),
        "resource_conflict_proxy": float(type_switches),
    }


def random_topo(nodes: dict[int, Node], rng: random.Random) -> list[int]:
    succ = successors(nodes)
    unsat = {nid: len(n.predecessors) for nid, n in nodes.items()}
    ready = [nid for nid in nodes if unsat[nid] == 0]
    out = []
    while ready:
        idx = rng.randrange(len(ready))
        chosen = ready.pop(idx)
        out.append(chosen)
        for v in succ[chosen]:
            unsat[v] -= 1
            if unsat[v] == 0:
                ready.append(v)
    return out


def ga_schedule(nodes: dict[int, Node], pop_size: int, generations: int, mutation: float, budget_ms: int, seed: int) -> tuple[list[int], dict[str, float]]:
    rng = random.Random(seed)
    start = time.time()
    base = baseline_schedule(nodes)

    def fitness(order: list[int]) -> tuple[float, dict[str, float]]:
        m = evaluate_schedule(nodes, order)
        score = m["critical_path_est"] + 0.2 * m["reg_pressure_proxy"] + 0.05 * m["resource_conflict_proxy"]
        return score, m

    population = [base] + [random_topo(nodes, rng) for _ in range(max(1, pop_size - 1))]
    scored = [(fitness(ind)[0], ind, fitness(ind)[1]) for ind in population]
    scored.sort(key=lambda x: x[0])

    def crossover(p1: list[int], p2: list[int]) -> list[int]:
        rank = {nid: i for i, nid in enumerate(p2)}
        priorities = {nid: - (0.7 * p1.index(nid) + 0.3 * rank[nid]) for nid in nodes}
        return schedule_from_priority(nodes, priorities)

    def mutate(ind: list[int]) -> list[int]:
        if rng.random() > mutation:
            return ind
        i, j = sorted(rng.sample(range(len(ind)), 2))
        cand = ind[:]
        cand[i], cand[j] = cand[j], cand[i]
        # repair using priorities derived from possibly invalid order
        priorities = {nid: -cand.index(nid) for nid in cand}
        return schedule_from_priority(nodes, priorities)

    gen = 0
    while gen < generations:
        if (time.time() - start) * 1000 > budget_ms:
            break
        elite_count = max(2, pop_size // 5)
        elites = [x[1] for x in scored[:elite_count]]
        new_pop = elites[:]
        while len(new_pop) < pop_size:
            p1, p2 = rng.sample(elites, 2) if len(elites) > 1 else (elites[0], elites[0])
            child = mutate(crossover(p1, p2))
            new_pop.append(child)
        scored = [(fitness(ind)[0], ind, fitness(ind)[1]) for ind in new_pop]
        scored.sort(key=lambda x: x[0])
        gen += 1

    best_score, best_order, best_metrics = scored[0]
    best_metrics = dict(best_metrics)
    best_metrics["ga_score"] = float(best_score)
    best_metrics["ga_generations_used"] = float(gen)
    return best_order, best_metrics


def validate(nodes: dict[int, Node]) -> list[str]:
    errs = []
    ids = set(nodes)
    for nid, n in nodes.items():
        for p in n.predecessors:
            if p not in ids:
                errs.append(f"node {nid} has missing predecessor {p}")
    try:
        topological_order(nodes)
    except Exception as e:
        errs.append(str(e))
    return errs


def write_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload, indent=2))


def write_csv(path: Path, row: dict):
    exists = path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            w.writeheader()
        w.writerow(row)


def main():
    ap = argparse.ArgumentParser(description="Phase-1 offline scheduler (baseline/GA)")
    ap.add_argument("--input", default="dag_data.json")
    ap.add_argument("--algo", choices=["baseline", "ga"], default="baseline")
    ap.add_argument("--budget-ms", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--pop-size", type=int, default=24)
    ap.add_argument("--generations", type=int, default=50)
    ap.add_argument("--mutation", type=float, default=0.2)
    ap.add_argument("--out-prefix", default="out/run")
    args = ap.parse_args()

    nodes = load_dag(Path(args.input))
    errs = validate(nodes)
    if errs:
        raise SystemExit("Validation failed: " + "; ".join(errs))

    t0 = time.time()
    if args.algo == "baseline":
        order = baseline_schedule(nodes)
        metrics = evaluate_schedule(nodes, order)
    else:
        order, metrics = ga_schedule(nodes, args.pop_size, args.generations, args.mutation, args.budget_ms, args.seed)
    compile_ms = (time.time() - t0) * 1000
    metrics["compile_time_ms"] = float(round(compile_ms, 3))

    out_prefix = Path(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "input": args.input,
        "algo": args.algo,
        "seed": args.seed,
        "budget_ms": args.budget_ms,
        "order": order,
        "metrics": metrics,
    }
    write_json(out_prefix.with_suffix(".json"), result)
    row = {"algo": args.algo, "seed": args.seed, "budget_ms": args.budget_ms, **metrics}
    write_csv(out_prefix.parent / "summary.csv", row)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
