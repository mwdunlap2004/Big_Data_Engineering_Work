import sys
import time
from pyspark import SparkContext

def main():
    start_time = time.time()
    
    # Initialize Spark context with 2 cores
    sc = SparkContext("local[2]", "PageRank")
    
    # Read the sample dataset
    lines = sc.textFile("web-BerkStan-sample.txt")
    
    # Skip comment lines and parse edges (tab-separated)
    edges = lines.filter(lambda line: not line.startswith("#")) \
        .map(lambda line: line.split("\t")) \
        .map(lambda parts: (int(parts[0]), int(parts[1]))) \
        .filter(lambda src_dst: src_dst[0] != src_dst[1])  # Remove self-loops
    
    # Compute out-degrees for each source node
    out_degrees = edges.map(lambda src_dst: (src_dst[0], 1)) \
        .reduceByKey(lambda a, b: a + b)
    
    # Initialize ranks: 1.0 for each page with outgoing links
    ranks = out_degrees.map(lambda src_degree: (src_degree[0], 1.0))
    
    # PageRank iteration
    for iteration in range(10):  # 10 iterations as specified
        # Calculate contributions: for each edge, src contributes rank/out_degree to dst
        contributions = edges.join(ranks) \
            .join(out_degrees) \
            .map(lambda src_dst_rank_degree: 
                (src_dst_rank_degree[1][0][0],  # dst
                 src_dst_rank_degree[1][0][1] / src_dst_rank_degree[1][1])  # rank/out_degree
            ) \
            .reduceByKey(lambda a, b: a + b)
        
        # Calculate new ranks: 0.15 + 0.85 * sum_contributions
        ranks = contributions.map(lambda page_contrib: 
            (page_contrib[0], 0.15 + 0.85 * page_contrib[1])
        )
        
        # For debugging, show progress
        if iteration < 3:  # Show first few iterations
            print(f"Iteration {iteration + 1} completed")
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    # Get top 50 pages by rank
    top_50 = ranks.takeOrdered(50, key=lambda x: -x[1])
    
    # Print results
    print("\nTop 50 pages by PageRank:")
    for page, rank in top_50:
        print(f"{page}\t{rank}")
    
    # Save results as CSV
    with open("pagerank_results_pyspark_sample.csv", "w") as f:
        f.write("page,rank\n")
        for page, rank in top_50:
            f.write(f"{page},{rank}\n")
    
    # Save execution time to log file
    with open("pagerank_time_pyspark_sample.log", "w") as f:
        f.write(f"PySpark PageRank execution time: {execution_time:.4f} seconds\n")
        f.write(f"Iterations: 10\n")
        f.write(f"Timestamp: {time.ctime()}\n")
    
    print(f"\nExecution time: {execution_time:.4f} seconds")
    print("Results saved to pagerank_results_pyspark_sample.csv")
    print("Execution time saved to pagerank_time_pyspark_sample.log")
    
    sc.stop()

if __name__ == "__main__":
    main()