"""Download the IBM Telco Customer Churn dataset from Kaggle.

The single public, real dataset this project uses as its subscriber
dimension table. Requires a Kaggle API token — see
https://www.kaggle.com/settings/api — set via KAGGLE_API_TOKEN or
~/.kaggle/access_token.

Usage:
    uv run python -m project_helios.ingest.kaggle_churn --out data/raw
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

DATASET = "blastchar/telco-customer-churn"
EXPECTED_FILE = "WA_Fn-UseC_-Telco-Customer-Churn.csv"


def download(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / EXPECTED_FILE
    if target.exists():
        return target

    subprocess.run(
        ["kaggle", "datasets", "download", "-d", DATASET, "-p", str(out_dir), "--unzip"],
        check=True,
    )
    if not target.exists():
        raise FileNotFoundError(f"Expected {target} after download but it wasn't there")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    path = download(args.out)
    print(f"Churn dataset at {path}")


if __name__ == "__main__":
    main()
