import time
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, split, lit, sum as spark_sum, desc
from pyspark.storagelevel import StorageLevel


def main():
    start_time = time.time()

    spark = SparkSession.builder \
        .appName("PageRank") \
        .master("local[2]") \
        .config("spark.sql.shuffle.partitions", "4") \
        .getOrCreate()

    raw = spark.read.text("web-BerkStan.txt")
    raw = raw.filter(~col("value").startswith("#"))
    parts = split(col("value"), "\t")
    edges = raw.select(
        parts.getItem(0).alias("src"),
        parts.getItem(1).alias("dst")
    )
    edges.persist(StorageLevel.MEMORY_AND_DISK)

    out_deg = edges.groupBy("src").count()
    out_deg.persist(StorageLevel.MEMORY_AND_DISK)

    ranks = out_deg.select(col("src").alias("page"), lit(1.0).alias("rank"))
    ranks.persist(StorageLevel.MEMORY_AND_DISK)
    num_pages = ranks.count()
    print(f"Pages with outgoing links: {num_pages}")

    for i in range(10):
        contribs = ranks.alias("r") \
            .join(edges.alias("e"), col("r.page") == col("e.src")) \
            .join(out_deg.alias("o"), col("e.src") == col("o.src")) \
            .select(
                col("e.dst"),
                (col("r.rank") / col("o.count")).alias("contrib")
            )

        totals = contribs.groupBy("dst").agg(spark_sum("contrib").alias("total_contrib"))

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

    results = ranks.collect()
    with open("pagerank_results.csv", "w") as f:
        f.write("Page,Rank\n")
        for row in results:
            f.write(f"{row.page},{row.rank}\n")

    elapsed = time.time() - start_time

    with open("pagerank_time.log", "w") as f:
        f.write("PySpark PageRank on Berkeley-Stanford Web Graph\n")
        f.write(f"Date: 2026-05-28\n")
        f.write(f"Configuration: local[2], 10 iterations\n")
        f.write(f"Pages with outgoing links: {num_pages}\n")
        f.write(f"Total runtime: {elapsed:.4f} seconds\n")

    print(f"\nRuntime: {elapsed:.4f} seconds")
    print("Results saved to pagerank_results.csv")
    print("Timing log saved to pagerank_time.log")

    spark.stop()


if __name__ == "__main__":
    main()
