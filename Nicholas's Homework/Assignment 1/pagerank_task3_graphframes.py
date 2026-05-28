import sys
import time
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit, split
from graphframes import GraphFrame

def main():
    start_time = time.time()
    
    # Initialize Spark session with 2 cores and GraphFrames package
    spark = SparkSession.builder \
        .appName("PageRank") \
        .master("local[2]") \
        .config("spark.jars.packages", "graphframes:graphframes:0.8.1-spark3.0-s_2.12") \
        .getOrCreate()
    
    # Read the dataset
    lines = spark.read.text("web-BerkStan.txt")
    
    # Skip comment lines and parse edges (tab-separated)
    edges = lines.filter(~col("value").startswith("#")) \
        .select(
            split(col("value"), "\t")[0].cast("long").alias("src"),
            split(col("value"), "\t")[1].cast("long").alias("dst")
        )
    
    # Filter out self-loops
    edges = edges.filter(col("src") != col("dst"))
    
    # Create vertices DataFrame (all unique nodes that appear as src or dst)
    vertices = edges.select("src").union(edges.select("dst")).distinct() \
        .withColumnRenamed("src", "id")
    
    # Create GraphFrame
    graph = GraphFrame(vertices, edges)
    
    # Run PageRank using GraphFrames library
    # We'll run it for 10 iterations as specified
    results = graph.pageRank(resetProbability=0.15, maxIter=10)
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    # Get top 50 pages by rank
    top_50 = results.vertices.orderBy(col("pagerank").desc()).limit(50)
    
    # Print results
    print("\nTop 50 pages by PageRank:")
    top_50.select("id", "pagerank").show(truncate=False)
    
    # Save results as CSV
    top_50.select("id", "pagerank").coalesce(1).write.mode("overwrite").option("header", "true").csv("pagerank_results_graphframes")
    
    # Save execution time to log file
    with open("pagerank_time_graphframes.log", "w") as f:
        f.write(f"GraphFrames PageRank execution time: {execution_time:.4f} seconds\n")
        f.write(f"Iterations: 10\n")
        f.write(f"Timestamp: {time.ctime()}\n")
    
    print(f"\nExecution time: {execution_time:.4f} seconds")
    print("Results saved to pagerank_results_graphframes/")
    print("Execution time saved to pagerank_time_graphframes.log")
    
    spark.stop()

if __name__ == "__main__":
    main()