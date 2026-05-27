#!/usr/bin/env python3
import os
import csv
import zipfile
import requests
from pathlib import Path


def download_from_gdrive(file_id, destination):
    import re
    session = requests.Session()
    URL = "https://drive.google.com/uc?export=download"

    html = session.get(URL, params={"id": file_id}).text

    action = ""
    params = {}
    match = re.search(
        r'<form[^>]*action="([^"]+)"[^>]*method="get"[^>]*>', html
    )
    if match:
        action = match.group(1)
        for hidden in re.finditer(
            r'<input type="hidden" name="([^"]+)" value="([^"]*)">', html
        ):
            params[hidden.group(1)] = hidden.group(2)

    if action and params:
        response = session.get(action, params=params, stream=True)
    else:
        fallback = f"https://drive.usercontent.google.com/download"
        confirm = None
        for key, value in session.cookies.items():
            if key.startswith("download_warning"):
                confirm = value
                break
        response = session.get(
            fallback,
            params={
                "id": file_id, "export": "download",
                "confirm": confirm or "t",
            },
            stream=True,
        )

    response.raise_for_status()
    with open(destination, "wb") as f:
        for chunk in response.iter_content(chunk_size=32768):
            if chunk:
                f.write(chunk)


def extract_zip(zip_path, extract_dir):
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)


def main():
    file_id = "1vlczaocHyghEW5Q-6WprqB2nnna_wrLE"
    zip_name = "stackoverflow_data.zip"
    extract_dir = "stackoverflow_data"

    if not os.path.exists(zip_name):
        download_from_gdrive(file_id, zip_name)

    if not os.path.exists(extract_dir):
        extract_zip(zip_name, extract_dir)

    csv_files = sorted(Path(extract_dir).rglob("*.csv"))
    num_files = len(csv_files)
    total_rows = 0
    keywords = ["python", "java", "javascript", "sql", "rust"]
    counts = {kw: 0 for kw in keywords}

    for fpath in csv_files:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            for row in reader:
                total_rows += 1
                row_text = " ".join(row).lower()
                for kw in keywords:
                    if kw in row_text:
                        counts[kw] += 1

    most_common = max(counts, key=counts.get)

    print(f"Number of CSV files: {num_files}")
    print(f"Total number of rows: {total_rows}")
    for kw in keywords:
        print(f"Rows containing {kw}: {counts[kw]}")
    print(f"Most common keyword: {most_common}")


if __name__ == "__main__":
    main()
