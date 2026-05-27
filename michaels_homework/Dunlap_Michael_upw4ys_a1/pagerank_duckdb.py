import duckdb
import time
import os

def main():
    con = duckdb.connect()
    
    con.execute("""
        CREATE TABLE raw_lines (line VARCHAR)
    """)
    
    con.execute("""
        COPY raw_lines FROM 'web-BerkStan.txt' (DELIMITER '\n')
    """)
    
    con.execute("""
        CREATE TABLE edges AS
        SELECT 
            CAST(str_split(line, '\t')[1] AS BIGINT) as src,
            CAST(str_split(line, '\t')[2] AS BIGINT) as dst
        FROM raw_lines
        WHERE line NOT LIKE '#%'
          AND str_split(line, '\t')[1] != ''
          AND str_split(line, '\t')[2] != ''
    """)
    
    con.execute("DROP TABLE raw_lines")
    
    con.execute("""
        CREATE TABLE edges_distinct AS 
        SELECT DISTINCT src, dst FROM edges
    """)
    
    con.execute("DROP TABLE edges")
    
    con.execute("""
        CREATE TABLE out_degrees AS 
        SELECT src, COUNT(*) as out_degree 
        FROM edges_distinct 
        GROUP BY src
    """)
    
    num_pages = con.execute("SELECT COUNT(*) FROM out_degrees").fetchone()[0]
    print(f"Total pages with outgoing links: {num_pages}")
    
    con.execute("""
        CREATE TABLE ranks AS 
        SELECT src, 1.0 as rank 
        FROM out_degrees
    """)
    
    start_time = time.time()
    
    NUM_ITERATIONS = 10
    DAMPING = 0.85
    
    for iteration in range(NUM_ITERATIONS):
        con.execute("""
            CREATE OR REPLACE TEMP TABLE contributions AS
            SELECT e.dst, r.rank / o.out_degree as contribution
            FROM edges_distinct e
            JOIN ranks r ON e.src = r.src
            JOIN out_degrees o ON e.src = o.src
        """)
        
        con.execute("""
            CREATE OR REPLACE TEMP TABLE new_ranks AS
            SELECT dst as src, 0.15 + ? * SUM(contribution) as rank
            FROM contributions
            GROUP BY dst
        """, [DAMPING])
        
        con.execute("DROP TABLE ranks")
        con.execute("CREATE TABLE ranks AS SELECT * FROM new_ranks")
        
        count = con.execute("SELECT COUNT(*) FROM ranks").fetchone()[0]
        elapsed = time.time() - start_time
        print(f"Iteration {iteration + 1}: {count} pages, time so far: {elapsed:.1f}s")
    
    elapsed = time.time() - start_time
    print(f"\nTotal computation time: {elapsed:.2f} seconds")
    
    top_50 = con.execute("""
        SELECT src, rank FROM ranks 
        ORDER BY rank DESC 
        LIMIT 50
    """).fetchall()
    
    print("\nTop 50 pages by PageRank:")
    print(f"{'Rank':<15} {'Page ID':<15}")
    print("-" * 30)
    for row in top_50:
        print(f"{row[1]:<15.6f} {row[0]:<15}")
    
    output_dir = "pagerank_duckdb_output"
    os.makedirs(output_dir, exist_ok=True)
    
    csv_path = os.path.join(output_dir, "pagerank_results.csv")
    con.execute(f"""
        COPY (
            SELECT src as page_id, rank FROM ranks 
            ORDER BY rank DESC 
            LIMIT 50
        ) TO '{csv_path}' (HEADER, DELIMITER ',')
    """)
    
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
    
    con.close()

if __name__ == "__main__":
    main()
