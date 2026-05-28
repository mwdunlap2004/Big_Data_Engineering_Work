"""
PageRank using Spark's GraphFrames library (from graphframes import GraphFrame).

GraphFrames is loaded via --packages graphframes:graphframes:0.8.4-spark3.5-s_2.12.
Uses the custom iterative algorithm matching Tasks 1-2: rank initialized for pages
with outgoing links, pages without contributions dropped each iter.
"""

import time
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, split, lit, sum as spark_sum, desc
from pyspark.storagelevel import StorageLevel
from graphframes import GraphFrame


def main():
    start_time = time.time()

    spark = SparkSession.builder \
        .appName("PageRank-GraphFrames") \
        .master("local[2]") \
        .config("spark.driver.memory", "6g") \
        .config("spark.executor.memory", "6g") \
        .config("spark.sql.shuffle.partitions", "4") \
        .config("spark.jars.packages",
                "graphframes:graphframes:0.8.4-spark3.5-s_2.12") \
        .getOrCreate()

    raw = spark.read.text("web-BerkStan.txt") \
        .filter(~col("value").startswith("#"))
    edges = raw.select(
        split(col("value"), "\t").getItem(0).alias("src"),
        split(col("value"), "\t").getItem(1).alias("dst")
    )
    edges.persist(StorageLevel.MEMORY_AND_DISK)

    vertices = edges.select("src").distinct().toDF("id")
    vertices.persist(StorageLevel.MEMORY_AND_DISK)

    gf = GraphFrame(vertices, edges)

    out_deg = gf.outDegrees
    out_deg.persist(StorageLevel.MEMORY_AND_DISK)

    ranks = out_deg.select(
        col("id").alias("page"), lit(1.0).alias("rank")
    )
    ranks.persist(StorageLevel.MEMORY_AND_DISK)
    num_pages = ranks.count()
    print(f"Pages with outgoing links: {num_pages}")

    for i in range(10):
        contribs = ranks.alias("r") \
            .join(edges.alias("e"), col("r.page") == col("e.src")) \
            .join(out_deg.alias("o"),
                  col("e.src") == col("o.id")) \
            .select(col("e.dst"),
                    (col("r.rank") / col("o.outDegree")).alias("contrib"))

        totals = contribs.groupBy("dst").agg(
            spark_sum("contrib").alias("total_contrib"))

        new_ranks = totals.select(
            col("dst").alias("page"),
            (lit(0.15) + lit(0.85) * col("total_contrib")).alias("rank")
        )
        new_ranks.persist(StorageLevel.MEMORY_AND_DISK)

        num_active = new_ranks.count()
        print(f"Iteration {i + 1}: {num_active} pages active")

        ranks.unpersist()
        ranks = new_ranks

    ranks = ranks.orderBy(desc("rank"))

    print("\nTop 50 pages by PageRank:")
    print("Page\tRank")
    for row in ranks.limit(50).collect():
        print(f"{row.page}\t{row.rank:.10f}")

    top50 = ranks.limit(50).collect()
    with open("pagerank_graphframes_results.csv", "w") as f:
        f.write("Page,Rank\n")
        for row in top50:
            f.write(f"{row.page},{row.rank}\n")

    elapsed = time.time() - start_time

    with open("pagerank_graphframes_time.log", "w") as f:
        f.write("GraphFrames PageRank on Berkeley-Stanford Web Graph\n")
        f.write("Date: 2026-05-28\n")
        f.write("Configuration: GraphFrames 0.8.4, custom iterative algorithm, 10 iterations\n")
        f.write(f"Pages with outgoing links: {num_pages}\n")
        f.write(f"Total runtime: {elapsed:.4f} seconds\n")

    print(f"\nRuntime: {elapsed:.4f} seconds")
    print("Results saved to pagerank_graphframes_results.csv")
    print("Timing log saved to pagerank_graphframes_time.log")

    spark.stop()


if __name__ == "__main__":
    main()
