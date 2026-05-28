#!/usr/bin/env python3
"""
GraphFrames PageRank — replicates the custom algorithm from Tasks 1/2
using GraphFrames for graph construction and DataFrame operations for
iterative message passing.
Sinks initialized to 0.0; only nodes receiving contributions get rank > 0.

Usage: python pagerank_graphframes.py [graph_file]
"""

import time
import csv
import sys

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from graphframes import GraphFrame

GRAPH_FILE = sys.argv[1] if len(sys.argv) > 1 else 'web-BerkStan.txt'
NUM_ITERS = 10
OUTPUT_PREFIX = 'pagerank_graphframes'


def main():
    spark = (SparkSession.builder
             .appName("GraphFrames PageRank (custom algorithm)")
             .master("local[2]")
             .config("spark.driver.memory", "6g")
             .config("spark.jars.packages",
                     "io.graphframes:graphframes-spark4_2.13:0.11.0")
             .config("spark.sql.shuffle.partitions", "20")
             .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
             .config("spark.sql.adaptive.advisoryPartitionSizeInBytes", "64m")
             .getOrCreate())

    total_t0 = time.time()

    # --- Load graph -----------------------------------------------------------
    print("Loading graph into Spark DataFrame...")
    t0 = time.time()

    edges_df = (spark.read
                .option("comment", "#")
                .option("delimiter", "\t")
                .option("header", "false")
                .schema("src LONG, dst LONG")
                .csv(GRAPH_FILE)
                .distinct())
    edges_df.cache()

    out_deg_df = (edges_df
                  .groupBy("src")
                  .agg(F.count("dst").alias("out_deg")))

    all_vertices = (edges_df.selectExpr("src as id")
                    .union(edges_df.selectExpr("dst as id"))
                    .distinct())

    out_deg_vertices = out_deg_df.withColumnRenamed("src", "id")

    vertices_df = (all_vertices
                   .join(out_deg_vertices, "id", "left")
                   .select(
                       F.col("id"),
                       F.when(F.col("out_deg").isNotNull(),
                              F.lit(1.0)).otherwise(F.lit(0.0)).alias("rank"),
                       F.col("out_deg")))
    vertices_df.cache()

    n_edges = edges_df.count()
    n_nodes = vertices_df.count()
    t1 = time.time()
    print(f"  Nodes: {n_nodes:,}, Edges: {n_edges:,} ({t1 - t0:.3f}s)")

    # --- Build initial GraphFrame ---------------------------------------------
    print("Building GraphFrame...")
    g = GraphFrame(vertices_df, edges_df)

    # --- Iterative PageRank (custom algorithm) --------------------------------
    print(f"\nRunning custom PageRank via GraphFrames "
          f"({NUM_ITERS} iterations)...")
    iteration_times = []

    for it in range(NUM_ITERS):
        iter_t0 = time.time()

        # Check for active sources (rank > 0)
        active_count = (g.vertices
                        .filter(F.col("rank") > 0)
                        .count())

        if active_count == 0:
            iter_t1 = time.time()
            elapsed = iter_t1 - iter_t0
            iteration_times.append(elapsed)
            print(f"  Iteration {it + 1}: 0 active sources, stopping "
                  f"({elapsed:.3f}s)")
            break

        # Active sources with their rank and out-degree
        active = (g.vertices
                  .filter(F.col("rank") > 0)
                  .select(
                      F.col("id").alias("src"),
                      F.col("rank").alias("src_rank"),
                      F.col("out_deg").alias("src_out_deg")))

        # Compute contributions: join edges with active sources,
        # send rank/out_deg to each destination, aggregate by dst
        contributions = (
            edges_df
            .join(active, "src")
            .groupBy("dst")
            .agg(F.sum(F.col("src_rank") / F.col("src_out_deg"))
                 .alias("contrib")))

        # Update ranks:  0.15 + 0.85 * contrib  if contrib > 0, else 0.0
        new_vertices = (
            g.vertices.select("id", "out_deg")
            .join(contributions, F.col("id") == F.col("dst"), "left")
            .select(
                F.col("id"),
                F.col("out_deg"),
                F.when(
                    F.col("contrib").isNotNull() & (F.col("contrib") > 0),
                    F.lit(0.15) + F.lit(0.85) * F.col("contrib")
                ).otherwise(F.lit(0.0)).alias("rank")))

        old_vertices = g.vertices
        new_vertices = new_vertices.localCheckpoint(eager=True)
        g = GraphFrame(new_vertices, edges_df)

        iter_t1 = time.time()
        elapsed = iter_t1 - iter_t0
        iteration_times.append(elapsed)

        n_active_new = (g.vertices
                        .filter(F.col("rank") > 0)
                        .count())
        print(f"  Iteration {it + 1}: {n_active_new:,} active pages "
              f"({elapsed:.3f}s)")

    total_t1 = time.time()
    elapsed_total = total_t1 - total_t0
    page_rank_elapsed = sum(iteration_times)

    # --- Top 50 ---------------------------------------------------------------
    top50 = (g.vertices
             .filter(F.col("rank") > 0)
             .orderBy("rank", ascending=False)
             .limit(50)
             .collect())

    print(f"\nTop 50 pages by PageRank (GraphFrames, custom algorithm):")
    print(f"{'#':<6} {'Node':<12} {'PageRank':<14}")
    print("-" * 34)
    for i, row in enumerate(top50):
        print(f"{i + 1:<6} {row.id:<12} {row.rank:<14.8f}")

    # --- Save top 50 as CSV ---------------------------------------------------
    csv_file = f"{OUTPUT_PREFIX}_top50.csv"
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Node', 'PageRank'])
        for row in top50:
            writer.writerow([row.id, f"{row.rank:.10f}"])
    print(f"\nSaved top 50 results to {csv_file}")

    # --- Save time log --------------------------------------------------------
    log_file = f"{OUTPUT_PREFIX}_time.log"
    with open(log_file, 'w') as f:
        f.write(f"Graph file: {GRAPH_FILE}\n")
        f.write(f"Iterations: {NUM_ITERS}\n")
        f.write(f"Nodes: {n_nodes}\n")
        f.write(f"Edges: {n_edges}\n")
        f.write(f"PageRank compute time: {page_rank_elapsed:.4f}s\n")
        f.write(f"  Iteration times:\n")
        for i, t in enumerate(iteration_times):
            f.write(f"    Iteration {i + 1}: {t:.4f}s\n")
        f.write(f"Total program time: {elapsed_total:.4f}s\n")
    print(f"\nTime log saved to {log_file}")
    print(f"Total time: {elapsed_total:.4f}s")

    spark.stop()


if __name__ == '__main__':
    main()
