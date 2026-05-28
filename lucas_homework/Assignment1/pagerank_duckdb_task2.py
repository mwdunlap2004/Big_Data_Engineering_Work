#!/usr/bin/env python3
"""
DuckDB-based PageRank — replicates the multiprocessing algorithm for cross-verification.
Usage: python pagerank_duckdb.py [graph_file]
"""

import duckdb
import time
import csv
import sys

GRAPH_FILE = sys.argv[1] if len(sys.argv) > 1 else 'web-BerkStan.txt'
NUM_ITERS = 10
OUTPUT_PREFIX = 'pagerank_duckdb'


def main():
    con = duckdb.connect()

    total_t0 = time.time()

    # --- Load graph -----------------------------------------------------------
    print("Loading graph into DuckDB...")
    t0 = time.time()
    con.execute(f"""
        CREATE TABLE edges AS
        SELECT CAST(col1 AS BIGINT) AS src, CAST(col2 AS BIGINT) AS dst
        FROM read_csv('{GRAPH_FILE}', delim='\\t', header=false, comment='#',
                      columns={{'col1': 'VARCHAR', 'col2': 'VARCHAR'}},
                      ignore_errors=true, auto_detect=false)
    """)
    n_edges = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    t1 = time.time()
    print(f"  Edges: {n_edges:,} ({t1 - t0:.3f}s)")

    # --- Build nodes & out-degree ---------------------------------------------
    print("Building node set and out-degree...")
    t0 = time.time()
    con.execute("""
        CREATE TABLE nodes AS
        SELECT DISTINCT node FROM (
            SELECT src AS node FROM edges
            UNION
            SELECT dst AS node FROM edges
        )
    """)
    con.execute("""
        CREATE TABLE out_degree AS
        SELECT src AS node, CAST(COUNT(*) AS DOUBLE) AS degree
        FROM edges
        GROUP BY src
    """)
    n_nodes = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    t1 = time.time()
    print(f"  Nodes: {n_nodes:,} ({t1 - t0:.3f}s)")

    # --- Initialize ranks -----------------------------------------------------
    con.execute("""
        CREATE TABLE ranks AS
        SELECT n.node,
               CASE WHEN od.node IS NOT NULL THEN 1.0 ELSE 0.0 END AS rank
        FROM nodes n
        LEFT JOIN out_degree od ON n.node = od.node
    """)

    # --- Iterative PageRank ---------------------------------------------------
    print(f"\nRunning PageRank ({NUM_ITERS} iterations)...")
    for it in range(NUM_ITERS):
        iter_t0 = time.time()

        n_active = con.execute(
            "SELECT COUNT(*) FROM ranks WHERE rank > 0"
        ).fetchone()[0]

        if n_active == 0:
            iter_t1 = time.time()
            print(f"  Iteration {it + 1}: 0 active sources, stopping "
                  f"({iter_t1 - iter_t0:.3f}s)")
            break

        # Single SQL statement: compute contributions and update ranks
        con.execute("""
            CREATE OR REPLACE TABLE ranks AS
            SELECT n.node,
                   CASE WHEN c.contrib_val IS NOT NULL AND c.contrib_val > 0
                        THEN 0.15 + 0.85 * c.contrib_val
                        ELSE 0.0
                   END AS rank
            FROM nodes n
            LEFT JOIN (
                SELECT e.dst AS node,
                       SUM(r.rank / od.degree) AS contrib_val
                FROM edges e
                JOIN ranks r ON e.src = r.node
                JOIN out_degree od ON e.src = od.node
                WHERE r.rank > 0
                GROUP BY e.dst
            ) c ON n.node = c.node
        """)

        iter_t1 = time.time()
        print(f"  Iteration {it + 1}: {n_active:,} active pages "
              f"({iter_t1 - iter_t0:.3f}s)")

    total_t1 = time.time()
    elapsed = total_t1 - total_t0

    # --- Save results ---------------------------------------------------------
    top50 = con.execute("""
        SELECT node, rank
        FROM ranks
        WHERE rank > 0
        ORDER BY rank DESC
        LIMIT 50
    """).fetchall()

    print(f"\nTop 50 pages by PageRank (DuckDB):")
    print(f"{'#':<6} {'Node':<12} {'PageRank':<14}")
    print("-" * 34)
    for i, (node, rank) in enumerate(top50):
        print(f"{i + 1:<6} {node:<12} {rank:<14.8f}")

    csv_file = f"{OUTPUT_PREFIX}_ranks.csv"
    all_results = con.execute("""
        SELECT node, rank
        FROM ranks
        WHERE rank > 0
        ORDER BY rank DESC
    """).fetchall()
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Node', 'PageRank'])
        for node, rank in all_results:
            writer.writerow([node, f"{rank:.10f}"])
    print(f"\nSaved {len(all_results)} results to {csv_file}")

    log_file = f"{OUTPUT_PREFIX}_time.log"
    with open(log_file, 'w') as f:
        f.write(f"Graph file: {GRAPH_FILE}\n")
        f.write(f"Iterations: {NUM_ITERS}\n")
        f.write(f"Nodes: {n_nodes}\n")
        f.write(f"Edges: {n_edges}\n")
        f.write(f"Total time: {elapsed:.4f}s\n")
    print(f"Time log saved to {log_file}")
    print(f"Total time: {elapsed:.4f}s")


if __name__ == '__main__':
    main()
