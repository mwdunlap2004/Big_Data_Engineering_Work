from pyspark import SparkConf, SparkContext
import time
import os

def main():
    conf = SparkConf() \
        .setAppName("PageRank") \
        .setMaster("local[2]") \
        .set("spark.local.dir", "/home/ubuntu/spark-tmp") \
        .set("spark.driver.memory", "3g") \
        .set("spark.executor.memory", "3g") \
        .set("spark.sql.shuffle.partitions", "4")
    
    sc = SparkContext(conf=conf)
    sc.setLogLevel("WARN")
    
    lines = sc.textFile("web-BerkStan.txt")
    
    links = lines.filter(lambda l: not l.startswith("#")) \
                 .map(lambda l: l.strip().split("\t")) \
                 .filter(lambda p: len(p) == 2 and p[0] != "" and p[1] != "") \
                 .map(lambda p: (int(p[0]), int(p[1]))) \
                 .distinct() \
                 .groupByKey() \
                 .cache()
    
    num_pages = links.count()
    print(f"Total pages with outgoing links: {num_pages}")
    
    ranks = links.mapValues(lambda _: 1.0)
    
    start_time = time.time()
    
    NUM_ITERATIONS = 10
    DAMPING = 0.85
    
    for iteration in range(NUM_ITERATIONS):
        contribs = links.join(ranks).flatMap(
            lambda x: [(dest, x[1][1] / len(x[1][0])) for dest in x[1][0]]
        )
        
        ranks = contribs.reduceByKey(lambda a, b: a + b) \
                        .mapValues(lambda s: 0.15 + DAMPING * s)
        
        ranks.cache()
        count = ranks.count()
        ranks.unpersist()
        
        print(f"Iteration {iteration + 1}: {count} pages, time so far: {time.time() - start_time:.1f}s")
    
    elapsed = time.time() - start_time
    print(f"\nTotal computation time: {elapsed:.2f} seconds")
    
    top_50 = ranks.takeOrdered(50, key=lambda x: -x[1])
    
    print("\nTop 50 pages by PageRank:")
    print(f"{'Rank':<15} {'Page ID':<15}")
    print("-" * 30)
    for page_id, rank_val in top_50:
        print(f"{rank_val:<15.6f} {page_id:<15}")
    
    output_dir = "pagerank_output"
    os.makedirs(output_dir, exist_ok=True)
    
    csv_path = os.path.join(output_dir, "pagerank_results.csv")
    with open(csv_path, "w", newline="") as f:
        f.write("page_id,rank\n")
        for page_id, rank_val in top_50:
            f.write(f"{page_id},{rank_val}\n")
    
    print(f"\nResults saved to {csv_path}")
    
    log_path = os.path.join(output_dir, "pagerank_time.log")
    with open(log_path, "w") as f:
        f.write(f"PageRank computation time: {elapsed:.2f} seconds\n")
        f.write(f"Dataset: web-BerkStan.txt\n")
        f.write(f"Total pages with outgoing links: {num_pages}\n")
        f.write(f"Pages in final iteration: {count}\n")
        f.write(f"Iterations: {NUM_ITERATIONS}\n")
        f.write(f"Damping factor: {DAMPING}\n")
    
    print(f"Timing log saved to {log_path}")
    
    sc.stop()

if __name__ == "__main__":
    main()
