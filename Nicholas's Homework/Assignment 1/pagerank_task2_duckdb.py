import sys
import time
import duckdb

def main():
    start_time = time.time()
    
    # Create a DuckDB connection
    con = duckdb.connect()
    
    # Try to load the full dataset first
    try:
        con.execute("""
            CREATE TABLE edges AS
            SELECT 
                CAST(column0 AS BIGINT) AS src,
                CAST(column1 AS BIGINT) AS dst
            FROM read_csv('web-BerkStan.txt', 
                         delim='\t', 
                         header=false,
                         skip=4)
            WHERE column0 <> column1
        """)
        print("Successfully loaded full dataset")
    except Exception as e:
        print(f"Failed to load full dataset: {e}")
        print("Falling back to sample dataset")
        # Load the sample dataset
        con.execute("""
            CREATE TABLE edges AS
            SELECT 
                CAST(column0 AS BIGINT) AS src,
                CAST(column1 AS BIGINT) AS dst
            FROM read_csv('web-BerkStan-sample.txt', 
                         delim='\t', 
                         header=false,
                         skip=4)
            WHERE column0 <> column1
        """)
    
    # Compute out-degrees for each source node
    con.execute("""
        CREATE TABLE out_degrees AS
        SELECT src, COUNT(*) AS out_degree
        FROM edges
        GROUP BY src
    """)
    
    # Initialize ranks: 1.0 for each page with outgoing links
    con.execute("""
        CREATE TABLE ranks AS
        SELECT src AS page, 1.0 AS rank
        FROM out_degrees
    """)
    
    # PageRank iteration
    for iteration in range(10):  # 10 iterations as specified
        # Calculate contributions: for each edge, src contributes rank/out_degree to dst
        con.execute("""
            CREATE OR REPLACE TABLE contributions AS
            SELECT e.dst AS page, (r.rank / od.out_degree) AS contribution
            FROM edges e
            JOIN ranks r ON e.src = r.page
            JOIN out_degrees od ON e.src = od.src
        """)
        
        # Sum contributions for each destination page
        con.execute("""
            CREATE OR REPLACE TABLE new_ranks AS
            SELECT page, 0.15 + 0.85 * SUM(contribution) AS rank
            FROM contributions
            GROUP BY page
        """)
        
        # Replace ranks with new_ranks for next iteration
        con.execute("DROP TABLE ranks")
        con.execute("ALTER TABLE new_ranks RENAME TO ranks")
        
        # For debugging, show progress
        if iteration < 3:  # Show first few iterations
            print(f"Iteration {iteration + 1} completed")
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    # Get top 50 pages by rank
    result = con.execute("""
        SELECT page, rank
        FROM ranks
        ORDER BY rank DESC
        LIMIT 50
    """).fetchall()
    
    # Print results
    print("\nTop 50 pages by PageRank:")
    for page, rank in result:
        print(f"{page}\t{rank}")
    
    # Save results as CSV
    con.execute("""
        COPY (
            SELECT page, rank
            FROM ranks
            ORDER BY rank DESC
            LIMIT 50
        ) TO 'pagerank_results_duckdb.csv' (HEADER, DELIMITER ',')
    """)
    
    # Save execution time to log file
    with open("pagerank_time_duckdb.log", "w") as f:
        f.write(f"DuckDB PageRank execution time: {execution_time:.4f} seconds\n")
        f.write(f"Iterations: 10\n")
        f.write(f"Timestamp: {time.ctime()}\n")
    
    print(f"\nExecution time: {execution_time:.4f} seconds")
    print("Results saved to pagerank_results_duckdb.csv")
    print("Execution time saved to pagerank_time_duckdb.log")
    
    con.close()

if __name__ == "__main__":
    main()