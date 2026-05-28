import time
import duckdb


def main():
    start_time = time.time()

    con = duckdb.connect()
    con.execute("SET threads = 2")

    con.execute("""
        CREATE TABLE edges AS
        SELECT column0 AS src, column1 AS dst
        FROM read_csv_auto('web-BerkStan.txt', sep='\t', header=false, comment='#')
    """)

    con.execute("""
        CREATE TABLE out_deg AS
        SELECT src, CAST(COUNT(*) AS DOUBLE) AS cnt
        FROM edges
        GROUP BY src
    """)

    con.execute("""
        CREATE TABLE ranks AS
        SELECT src AS page, 1.0 AS rank
        FROM out_deg
    """)

    num_pages = con.execute("SELECT COUNT(*) FROM ranks").fetchone()[0]
    print(f"Pages with outgoing links: {num_pages}")

    for i in range(10):
        con.execute("DROP TABLE IF EXISTS contribs")
        con.execute("""
            CREATE TABLE contribs AS
            SELECT e.dst, SUM(r.rank / o.cnt) AS total_contrib
            FROM ranks r
            JOIN edges e ON r.page = e.src
            JOIN out_deg o ON r.page = o.src
            GROUP BY e.dst
        """)

        con.execute("DROP TABLE IF EXISTS new_ranks")
        con.execute("""
            CREATE TABLE new_ranks AS
            SELECT dst AS page, 0.15 + 0.85 * total_contrib AS rank
            FROM contribs
        """)

        con.execute("DROP TABLE IF EXISTS contribs")

        con.execute("DROP TABLE IF EXISTS ranks")
        con.execute("ALTER TABLE new_ranks RENAME TO ranks")

        num_active = con.execute("SELECT COUNT(*) FROM ranks").fetchone()[0]
        print(f"Iteration {i + 1}: {num_active} pages active")

    top50 = con.execute("""
        SELECT page, rank FROM ranks
        ORDER BY rank DESC
        LIMIT 50
    """).fetchall()

    print("\nTop 50 pages by PageRank:")
    print("Page\tRank")
    for page, rank in top50:
        print(f"{page}\t{rank:.10f}")

    con.execute("""
        COPY (
            SELECT page, rank FROM ranks
            ORDER BY rank DESC
            LIMIT 50
        ) TO 'pagerank_duckdb_results.csv' (HEADER, DELIMITER ',')
    """)

    elapsed = time.time() - start_time

    with open("pagerank_duckdb_time.log", "w") as f:
        f.write("DuckDB PageRank on Berkeley-Stanford Web Graph\n")
        f.write(f"Date: 2026-05-28\n")
        f.write(f"Configuration: DuckDB in-memory, 10 iterations\n")
        f.write(f"Pages with outgoing links: {num_pages}\n")
        f.write(f"Total runtime: {elapsed:.4f} seconds\n")

    print(f"\nRuntime: {elapsed:.4f} seconds")
    print("Results saved to pagerank_duckdb_results.csv")
    print("Timing log saved to pagerank_duckdb_time.log")

    con.close()


if __name__ == "__main__":
    main()
