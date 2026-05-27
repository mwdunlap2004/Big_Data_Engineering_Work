import os
import zipfile
import subprocess
import csv
import glob


ZIP_URL = "https://drive.google.com/uc?id=1vlczaocHyghEW5Q-6WprqB2nnna_wrLE"
ZIP_PATH = "stackoverflow_data.zip"
DATA_DIR = "stackoverflow_data"
KEYWORDS = ["python", "java", "javascript", "sql", "rust"]


def download_zip():
    if not os.path.exists(ZIP_PATH):
        subprocess.run(
            ["gdown", "--id", "1vlczaocHyghEW5Q-6WprqB2nnna_wrLE", "-O", ZIP_PATH],
            check=True,
            capture_output=True,
        )


def extract_zip():
    if not os.path.exists(DATA_DIR):
        with zipfile.ZipFile(ZIP_PATH, "r") as zf:
            zf.extractall(DATA_DIR)


def analyze_csvs():
    csv_paths = sorted(glob.glob(os.path.join(DATA_DIR, "**", "*.csv"), recursive=True))
    num_files = len(csv_paths)
    total_rows = 0
    keyword_counts = {kw: 0 for kw in KEYWORDS}

    for path in csv_paths:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            for row in reader:
                total_rows += 1
                row_text = " ".join(row).lower()
                for kw in KEYWORDS:
                    if kw in row_text:
                        keyword_counts[kw] += 1

    return num_files, total_rows, keyword_counts


def generate_report(num_files, total_rows, keyword_counts):
    print(f"Number of CSV files: {num_files}")
    print(f"Total number of rows: {total_rows}")
    for kw in KEYWORDS:
        print(f"Rows containing {kw}: {keyword_counts[kw]}")
    most_common = max(keyword_counts, key=keyword_counts.get)
    print(f"Most common keyword: {most_common}")


def main():
    download_zip()
    extract_zip()
    num_files, total_rows, keyword_counts = analyze_csvs()
    generate_report(num_files, total_rows, keyword_counts)


if __name__ == "__main__":
    main()
