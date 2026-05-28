#!/usr/bin/env python3
"""
PageRank implementation for large-scale web graphs.
Parallelized with multiprocessing using 2 CPU cores.

Usage: python pagerank.py <graph_file>
"""

import sys
import time
import csv
import numpy as np
from multiprocessing import Pool

_OUT_EDGES = None
_OUT_DEG = None
_N = None


def init_worker(out_edges, out_deg, n):
    global _OUT_EDGES, _OUT_DEG, _N
    _OUT_EDGES = out_edges
    _OUT_DEG = out_deg
    _N = n


def worker_contrib(args):
    chunk, ranks = args
    contrib = np.zeros(_N, dtype=np.float64)
    for src in chunk:
        d = _OUT_DEG[src]
        val = ranks[src] / d
        for dst in _OUT_EDGES[src]:
            contrib[dst] += val
    return contrib


def read_graph(filename):
    nodes_set = set()
    edges_temp = []

    with open(filename, 'r') as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            parts = line.strip().split('\t')
            if len(parts) != 2:
                parts = line.strip().split()
            src, dst = int(parts[0]), int(parts[1])
            nodes_set.add(src)
            nodes_set.add(dst)
            edges_temp.append((src, dst))

    nodes = sorted(nodes_set)
    node_to_idx = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)
    del nodes_set

    out_edges = [[] for _ in range(n)]
    for src, dst in edges_temp:
        out_edges[node_to_idx[src]].append(node_to_idx[dst])
    del edges_temp

    out_edges = [list(set(e)) for e in out_edges]
    out_deg = [len(e) for e in out_edges]

    return nodes, out_edges, out_deg


def pagerank(nodes, out_edges, out_deg, num_iters, num_workers=2):
    n = len(nodes)
    sources = [i for i, d in enumerate(out_deg) if d > 0]

    ranks = np.zeros(n, dtype=np.float64)
    for s in sources:
        ranks[s] = 1.0

    active = np.zeros(n, dtype=bool)
    for s in sources:
        active[s] = True

    with Pool(num_workers, initializer=init_worker,
              initargs=(out_edges, out_deg, n)) as pool:
        for it in range(num_iters):
            t0 = time.time()

            active_srcs = [s for s in sources if active[s]]
            if not active_srcs:
                t1 = time.time()
                print(f"  Iteration {it+1}: 0 active sources, stopping ({t1-t0:.3f}s)")
                break

            chunks = np.array_split(active_srcs, num_workers)
            chunks = [c.tolist() for c in chunks]

            results = pool.map(worker_contrib, [(c, ranks) for c in chunks])
            contrib = sum(results)

            has_contrib = contrib > 0
            ranks_new = np.zeros(n, dtype=np.float64)
            ranks_new[has_contrib] = 0.15 + 0.85 * contrib[has_contrib]
            ranks = ranks_new
            active = has_contrib

            t1 = time.time()
            active_count = int(np.sum(active))
            print(f"  Iteration {it+1}: {active_count} active pages ({t1-t0:.3f}s)")

    return ranks


def save_results(nodes, ranks, output_prefix="pagerank"):
    order = np.argsort(ranks)[::-1]
    nonzero = ranks > 0
    total_active = int(np.sum(nonzero))

    print(f"\nTop 50 pages by PageRank:")
    print(f"{'#':<6} {'Node':<12} {'PageRank':<14}")
    print("-" * 34)
    for i in range(min(50, len(order))):
        idx = order[i]
        print(f"{i+1:<6} {nodes[idx]:<12} {ranks[idx]:<14.8f}")

    csv_file = f"{output_prefix}_ranks.csv"
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Node', 'PageRank'])
        for i in order:
            if ranks[i] > 0:
                writer.writerow([nodes[i], f"{ranks[i]:.10f}"])
    print(f"\nSaved {total_active} results to {csv_file}")


def main():
    if len(sys.argv) != 2:
        print("Usage: python pagerank.py <graph_file>")
        sys.exit(1)

    graph_file = sys.argv[1]
    num_iters = 10

    total_t0 = time.time()

    print("Reading graph...")
    nodes, out_edges, out_deg = read_graph(graph_file)
    print(f"  Nodes: {len(nodes)}, Edges: {sum(out_deg)}")

    print(f"\nRunning PageRank ({num_iters} iterations, 2 workers)...")
    ranks = pagerank(nodes, out_edges, out_deg, num_iters, num_workers=2)

    save_results(nodes, ranks)

    total_t1 = time.time()
    elapsed = total_t1 - total_t0

    with open("pagerank_time.log", 'w') as f:
        f.write(f"Graph file: {graph_file}\n")
        f.write(f"Iterations: {num_iters}\n")
        f.write(f"Nodes: {len(nodes)}\n")
        f.write(f"Total time: {elapsed:.4f}s\n")

    print(f"\nTime log saved to pagerank_time.log")
    print(f"Total time: {elapsed:.4f}s")


if __name__ == '__main__':
    main()
