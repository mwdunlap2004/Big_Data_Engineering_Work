#!/usr/bin/env python3
import csv
import os
import time
from pathlib import Path

import duckdb


def load_edges(path: Path):
    edges = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line or line.startswith("#"):
                continue
            parts = line.strip().split()
            if len(parts) != 2:
                continue
            src, dst = parts
            edges.append((int(src), int(dst)))
    return edges


def write_top50_csv(rows, out_csv: Path):
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page", "rank"])
        for page, rank in rows[:50]:
            w.writerow([page, rank])


def write_time_log(seconds: float, out_log: Path, label: str):
    out_log.parent.mkdir(parents=True, exist_ok=True)
    out_log.write_text(f"{label}_seconds={seconds:.6f}\n", encoding="utf-8")


def run_pyspark_custom(data_file: Path, out_dir: Path, iterations: int = 10):
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder
        .appName("PageRankCustom")
        .master("local[2]")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )
    sc = spark.sparkContext
    sc.setLogLevel("ERROR")

    lines = sc.textFile(str(data_file)).filter(lambda x: x and not x.startswith("#"))
    edges = lines.map(lambda x: x.strip().split()).filter(lambda x: len(x) == 2).map(lambda x: (int(x[0]), int(x[1]))).cache()

    links = edges.groupByKey().mapValues(lambda d: list(d)).cache()
    ranks = links.mapValues(lambda _: 1.0)

    t0 = time.perf_counter()
    for _ in range(iterations):
        contribs = links.join(ranks).flatMap(
            lambda kv: ((dst, kv[1][1] / len(kv[1][0])) for dst in kv[1][0]) if len(kv[1][0]) > 0 else []
        )
        ranks = contribs.reduceByKey(lambda a, b: a + b).mapValues(lambda s: 0.15 + 0.85 * s)
    elapsed = time.perf_counter() - t0

    top50 = ranks.takeOrdered(50, key=lambda x: -x[1])
    print("\n[PySpark Custom] Top 50")
    for row in top50:
        print(row)

    write_top50_csv(top50, out_dir / "task1_pyspark_top50.csv")
    write_time_log(elapsed, out_dir / "task1_pyspark_time.log", "task1_pyspark")

    spark.stop()
    return top50, elapsed


def run_duckdb(data_file: Path, out_dir: Path, iterations: int = 10):
    con = duckdb.connect(database=":memory:")
    con.execute("CREATE TABLE edges(src BIGINT, dst BIGINT)")
    con.execute(
        """
        INSERT INTO edges
        SELECT CAST(column0 AS BIGINT), CAST(column1 AS BIGINT)
        FROM read_csv(?, delim='\t', header=false, comment='#')
        """,
        [str(data_file)],
    )

    con.execute("CREATE TABLE outdeg AS SELECT src, COUNT(*) AS deg FROM edges GROUP BY src")
    con.execute("CREATE TABLE ranks AS SELECT src AS page, 1.0 AS rank FROM outdeg")

    t0 = time.perf_counter()
    for _ in range(iterations):
        con.execute(
            """
            CREATE OR REPLACE TABLE ranks AS
            SELECT c.page, 0.15 + 0.85 * SUM(c.contrib) AS rank
            FROM (
              SELECT e.dst AS page, r.rank / o.deg AS contrib
              FROM edges e
              JOIN outdeg o ON e.src = o.src
              JOIN ranks r ON e.src = r.page
            ) c
            GROUP BY c.page
            """
        )
    elapsed = time.perf_counter() - t0

    top50 = con.execute("SELECT page, rank FROM ranks ORDER BY rank DESC LIMIT 50").fetchall()
    print("\n[DuckDB] Top 50")
    for row in top50:
        print(row)

    write_top50_csv(top50, out_dir / "task2_duckdb_top50.csv")
    write_time_log(elapsed, out_dir / "task2_duckdb_time.log", "task2_duckdb")
    con.close()
    return top50, elapsed


def run_graphframes(data_file: Path, out_dir: Path, iterations: int = 10):
    from pyspark.sql import SparkSession, functions as F
    from graphframes import GraphFrame

    spark = (
        SparkSession.builder
        .appName("PageRankGraphFrames")
        .master("local[2]")
        .config("spark.ui.enabled", "false")
        .config("spark.jars.packages", "io.graphframes:graphframes-spark3_2.12:0.9.3")
        .config("spark.driver.memory", "12g")
        .config("spark.executor.memory", "12g")
        .config("spark.driver.extraJavaOptions", "-XX:ReservedCodeCacheSize=512m")
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")

    edges = (
        spark.read.text(str(data_file))
        .filter(~F.col("value").startswith("#"))
        .select(F.split(F.col("value"), "\\s+").alias("parts"))
        .filter(F.size("parts") == 2)
        .select(F.col("parts")[0].alias("src"), F.col("parts")[1].alias("dst"))
    )

    vertices = edges.select(F.col("src").alias("id")).distinct()
    g = GraphFrame(vertices, edges)

    t0 = time.perf_counter()
    pr = g.pageRank(resetProbability=0.15, maxIter=iterations)
    ranks_df = pr.vertices.select(F.col("id").alias("page"), F.col("pagerank").alias("rank"))
    # Match assignment rule: keep only pages receiving contributions.
    ranks_df = ranks_df.join(edges.select(F.col("dst").alias("page")).distinct(), on="page", how="inner")
    top50_rows = ranks_df.orderBy(F.col("rank").desc()).limit(50).collect()
    elapsed = time.perf_counter() - t0

    top50 = [(int(r["page"]), float(r["rank"])) for r in top50_rows]
    print("\n[GraphFrames] Top 50")
    for row in top50:
        print(row)

    write_top50_csv(top50, out_dir / "task3_graphframes_top50.csv")
    write_time_log(elapsed, out_dir / "task3_graphframes_time.log", "task3_graphframes")

    spark.stop()
    return top50, elapsed


def write_transcript_md(out_dir: Path):
    md = out_dir / "task3_session_transcript.md"
    md.write_text(
        """# Session Transcript (Task 1-3)\n\n"
        "## User Request\n"
        "- Deploy Spark/PySpark and implement PageRank in PySpark, DuckDB, and GraphFrames.\n"
        "- Run 10 iterations and save top-50 CSVs and timing logs for each implementation.\n\n"
        "## Actions Performed\n"
        "1. Installed Python packages: `pyspark`, `duckdb`, `pyarrow`, `graphframes`; pinned `pyspark==3.5.1` for GraphFrames compatibility.\n"
        "2. Downloaded dataset `web-BerkStan.txt.gz` and decompressed to `web-BerkStan.txt`.\n"
        "3. Implemented custom PySpark PageRank (local[2], 10 iterations).\n"
        "4. Implemented DuckDB SQL iterative PageRank (10 iterations).\n"
        "5. Implemented GraphFrames PageRank API run (10 iterations).\n"
        "6. Saved top-50 CSV outputs and timing logs for all three tasks.\n\n"
        "## Generated Outputs\n"
        "- `outputs/task1_pyspark_top50.csv`\n"
        "- `outputs/task1_pyspark_time.log`\n"
        "- `outputs/task2_duckdb_top50.csv`\n"
        "- `outputs/task2_duckdb_time.log`\n"
        "- `outputs/task3_graphframes_top50.csv`\n"
        "- `outputs/task3_graphframes_time.log`\n"
        """,
        encoding="utf-8",
    )


def write_html_report(out_dir: Path):
    import pandas as pd

    t1 = pd.read_csv(out_dir / "task1_pyspark_top50.csv")
    t2 = pd.read_csv(out_dir / "task2_duckdb_top50.csv")
    t3 = pd.read_csv(out_dir / "task3_graphframes_top50.csv")

    def read_time(p: Path):
        return p.read_text(encoding="utf-8").strip().split("=")[-1]

    time1 = read_time(out_dir / "task1_pyspark_time.log")
    time2 = read_time(out_dir / "task2_duckdb_time.log")
    time3 = read_time(out_dir / "task3_graphframes_time.log")

    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>PageRank Assignment Report</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 24px; background: linear-gradient(120deg, #f4f7fb, #ffffff); color: #1f2937; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
    .card {{ background: #fff; border: 1px solid #d1d5db; border-radius: 10px; padding: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: 4px 6px; text-align: left; }}
    .meta {{ margin: 8px 0 16px; }}
  </style>
</head>
<body>
  <h1>PageRank Implementation Report</h1>
  <p class=\"meta\">Dataset: web-BerkStan | Iterations: 10 | Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
  <h2>Performance</h2>
  <ul>
    <li>PySpark (custom): {time1} seconds</li>
    <li>DuckDB (SQL iterative): {time2} seconds</li>
    <li>GraphFrames PageRank API: {time3} seconds</li>
  </ul>
  <h2>Reasoning and Findings</h2>
  <p>DuckDB is often fastest for single-machine analytical loops due to vectorized execution and low orchestration overhead. Custom PySpark can be slower locally because of RDD shuffle/serialization overhead, but it reflects distributed execution structure. GraphFrames simplifies implementation and can be competitive, though it still inherits Spark job overhead and graph construction costs. Rank order should broadly agree across methods, with small numeric differences caused by implementation details and floating-point accumulation.</p>
  <h2>Top-50 Side by Side</h2>
  <div class=\"grid\">
    <div class=\"card\"><h3>Task 1: PySpark</h3>{t1.to_html(index=False)}</div>
    <div class=\"card\"><h3>Task 2: DuckDB</h3>{t2.to_html(index=False)}</div>
    <div class=\"card\"><h3>Task 3: GraphFrames</h3>{t3.to_html(index=False)}</div>
  </div>
</body>
</html>
"""
    (out_dir / "task4_report.html").write_text(html, encoding="utf-8")


def main():
    base = Path(__file__).resolve().parent
    data_file = base / "web-BerkStan.txt"
    out_dir = base / "outputs"

    if not data_file.exists():
        raise FileNotFoundError(f"Missing dataset: {data_file}")

    run_pyspark_custom(data_file, out_dir, iterations=10)
    run_duckdb(data_file, out_dir, iterations=10)
    run_graphframes(data_file, out_dir, iterations=10)
    write_transcript_md(base)
    write_html_report(out_dir)
    print("\nAll tasks completed. Outputs written to:", out_dir)


if __name__ == "__main__":
    main()
