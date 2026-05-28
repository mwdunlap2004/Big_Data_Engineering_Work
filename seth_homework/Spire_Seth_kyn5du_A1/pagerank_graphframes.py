"""
PageRank using Spark's GraphFrames library via JVM bridge.

Python's graphframes package is incompatible with Python 3.14
(pickle RecursionError on RDD serialization). This implementation
accesses GraphFrames' Scala API through Py4J's JVM bridge, which
avoids Python pickle entirely since all GraphX computation runs
in the JVM.

Note: GraphFrames' built-in pageRank uses the standard PageRank
formula (0.15/N + 0.85*sum). To match our custom algorithm from
Tasks 1-2 (0.15 + 0.85*sum), we scale the results by N (total
pages with outgoing links), making them mathematically equivalent.
"""

import time
from pyspark.sql import SparkSession
from pyspark.sql.functions import split, col, desc, lit


def main():
    start_time = time.time()

    spark = SparkSession.builder \
        .appName("PageRank-GraphFrames") \
        .master("local[2]") \
        .config("spark.driver.memory", "6g") \
        .config("spark.executor.memory", "6g") \
        .config("spark.sql.shuffle.partitions", "4") \
        .config("spark.jars.packages", "graphframes:graphframes:0.8.4-spark3.5-s_2.12") \
        .getOrCreate()

    raw = spark.read.text("web-BerkStan.txt") \
        .filter(~col("value").startswith("#"))
    edges = raw.select(
        split(col("value"), "\t").getItem(0).alias("src"),
        split(col("value"), "\t").getItem(1).alias("dst")
    )
    edges.cache()

    vertices = edges.select("src").distinct().toDF("id")
    vertices.cache()

    jvm = spark.sparkContext._jvm
    jgf = jvm.org.graphframes.GraphFrame(vertices._jdf, edges._jdf)

    jout = jgf.outDegrees()
    from pyspark.sql import DataFrame as PyDF
    out_deg = PyDF(jout, spark).withColumnRenamed("outDegree", "cnt")
    out_deg.cache()
    num_pages = out_deg.count()
    print(f"Pages with outgoing links: {num_pages}")

    jresult = jgf.pageRank().resetProbability(0.15).maxIter(10).run()

    jranks = jresult.vertices()
    gf_ranks = PyDF(jranks, spark)
    gf_ranks.cache()

    gf_ranks = gf_ranks.join(out_deg, gf_ranks.id == out_deg.id) \
        .select(gf_ranks.id.alias("page"), col("pagerank"), col("cnt"))

    gf_ranks = gf_ranks.withColumn("rank",
        col("pagerank") * lit(num_pages))

    gf_ranks = gf_ranks.select("page", "rank").orderBy(desc("rank"))

    print("\nTop 50 pages by PageRank:")
    print("Page\tRank")
    for row in gf_ranks.limit(50).collect():
        print(f"{row.page}\t{row.rank:.10f}")

    top50 = gf_ranks.limit(50).collect()
    with open("pagerank_graphframes_results.csv", "w") as f:
        f.write("Page,Rank\n")
        for row in top50:
            f.write(f"{row.page},{row.rank}\n")

    elapsed = time.time() - start_time

    with open("pagerank_graphframes_time.log", "w") as f:
        f.write("GraphFrames PageRank on Berkeley-Stanford Web Graph\n")
        f.write("Date: 2026-05-28\n")
        f.write("Configuration: GraphFrames built-in pageRank via JVM bridge, 10 iterations\n")
        f.write(f"Pages with outgoing links (N): {num_pages}\n")
        f.write(f"Total runtime: {elapsed:.4f} seconds\n")

    print(f"\nRuntime: {elapsed:.4f} seconds")
    print("Results saved to pagerank_graphframes_results.csv")
    print("Timing log saved to pagerank_graphframes_time.log")

    spark.stop()


if __name__ == "__main__":
    main()
