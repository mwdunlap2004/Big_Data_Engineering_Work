from pyspark.sql import SparkSession
from pyspark.sql.functions import col, split, trim
from graphframes import GraphFrame
import time
import os

def main():
    spark = SparkSession.builder \
        .appName("PageRank-GraphFrames") \
        .master("local[2]") \
        .config("spark.jars", "/tmp/graphframes-spark4_2.13-0.11.0.jar,/tmp/graphframes-graphx-spark4_2.13-0.11.0.jar") \
        .config("spark.sql.shuffle.partitions", "4") \
        .config("spark.driver.memory", "3g") \
        .config("spark.executor.memory", "3g") \
        .getOrCreate()

    sc = spark.sparkContext
    sc.setLogLevel("ERROR")

    raw_df = spark.read.text("web-BerkStan.txt")

    edges = raw_df.filter(~col("value").startswith("#")) \
                  .select(split(trim(col("value")), "\t").alias("parts")) \
                  .filter(col("parts").isNotNull() & (col("parts").getItem(0) != "")) \
                  .select(
                      col("parts").getItem(0).cast("long").alias("src"),
                      col("parts").getItem(1).cast("long").alias("dst")
                  ) \
                  .dropDuplicates()

    vertices = edges.select(col("src").alias("id")).union(
        edges.select(col("dst").alias("id"))
    ).distinct()

    num_vertices = vertices.count()
    num_edges = edges.count()
    print(f"Vertices: {num_vertices}, Edges: {num_edges}")

    g = GraphFrame(vertices, edges)

    start_time = time.time()

    NUM_ITERATIONS = 10
    RESET_PROBABILITY = 0.15

    result = g.pageRank(resetProbability=RESET_PROBABILITY, maxIter=NUM_ITERATIONS)

    elapsed = time.time() - start_time
    print(f"Total computation time: {elapsed:.2f} seconds")

    ranks_df = result.vertices.select("id", "pagerank")

    top_50 = ranks_df.orderBy(col("pagerank").desc()).limit(50).collect()

    print("\nTop 50 pages by PageRank:")
    print(f"{'Rank':<15} {'Page ID':<15}")
    print("-" * 30)
    for row in top_50:
        print(f"{row['pagerank']:<15.6f} {row['id']:<15}")

    output_dir = "pagerank_graphframes_output"
    os.makedirs(output_dir, exist_ok=True)

    csv_path = os.path.join(output_dir, "pagerank_results.csv")
    ranks_df.orderBy(col("pagerank").desc()).limit(50) \
        .withColumnRenamed("id", "page_id") \
        .withColumnRenamed("pagerank", "rank") \
        .write \
        .option("header", "true") \
        .csv(csv_path, mode="overwrite")

    print(f"\nResults saved to {csv_path}")

    log_path = os.path.join(output_dir, "pagerank_time.log")
    with open(log_path, "w") as f:
        f.write(f"PageRank computation time: {elapsed:.2f} seconds\n")
        f.write(f"Dataset: web-BerkStan.txt\n")
        f.write(f"Vertices: {num_vertices}\n")
        f.write(f"Edges: {num_edges}\n")
        f.write(f"Iterations: {NUM_ITERATIONS}\n")
        f.write(f"Reset probability: {RESET_PROBABILITY}\n")

    print(f"Timing log saved to {log_path}")

    spark.stop()

if __name__ == "__main__":
    main()
